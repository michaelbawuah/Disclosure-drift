import copy
import json

import httpx
import pandas as pd
import pytest

from disclosure_research.audit import build_audit
from disclosure_research.edgar import SecClient
from disclosure_research.extraction import VERSION, TOKEN, clean_html, extract_risk_factors, pair_filings
from disclosure_research.ingest import ingest_smoke
from disclosure_research.references import load_reference_rules, resolve_section, sha256


ACCESSION = "0000000123-19-000001"
DIRECTORY = "https://www.sec.gov/Archives/edgar/data/123/000000012319000001/"
PRIMARY = DIRECTORY + "annual.htm"
EXHIBIT = DIRECTORY + "risks.htm"
INDEX = DIRECTORY + ACCESSION + "-index.html"
BODY = "supply competition operations " * 100


def make_case(exhibit=False):
    pointer = "Refer to Exhibit 99 for the risk disclosures." if exhibit else "Pages 4-5"
    raw = (f"<h2>Item 1A. Risk Factors</h2><p>{pointer}</p>"
           "<h2>Item 1B. Unresolved Staff Comments</h2><p>None.</p>"
           f"<h1>RISK FACTORS</h1><p>{BODY}</p><h1>PROPERTIES</h1><p>EXCLUDED PROPERTY</p>").encode()
    source = (f"<h1>Exhibit 99</h1><p>{BODY}</p><h2>END OF RISKS</h2><p>EXCLUDED APPENDIX</p>".encode()
              if exhibit else raw)
    normalized = clean_html(source)
    start = normalized.index("supply competition")
    end = normalized.index("END OF RISKS" if exhibit else "PROPERTIES")
    text = normalized[start:end].strip(" .:-\n")
    index = ('<table><tr><td>2</td><td>Cautionary statement</td><td><a href="risks.htm">risks.htm</a>'
             '</td><td>EX-99</td><td>1000</td></tr></table>').encode()
    rule = {"accession": ACCESSION, "primary_url": PRIMARY, "primary_sha256": sha256(raw),
            "primary_reference_sha256": sha256(extract_risk_factors(raw).text),
            "kind": "same_accession_exhibit_range" if exhibit else "same_document_range",
            "source_url": EXHIBIT if exhibit else PRIMARY, "source_sha256": sha256(source),
            "start_offset": start, "end_offset": end, "token_count": len(TOKEN.findall(text)),
            "text_sha256": sha256(text), "boundary_notes": "Synthetic body only; exclude adjacent section."}
    if exhibit:
        rule.update(index_url=INDEX, index_sha256=sha256(index))
    documents = {PRIMARY: raw, EXHIBIT: source, INDEX: index}
    return raw, rule, documents


def write_rules(path, rules):
    path.write_text(json.dumps({"schema_version": 1, "normalizer_version": VERSION, "rules": rules}))
    return load_reference_rules(path)


def test_unknown_page_reference_stays_flagged_without_a_rule():
    raw, _, _ = make_case()
    result = resolve_section(raw, PRIMARY, ACCESSION, {})
    assert result.extraction.status == "review"
    assert result.method == "numbered_item1a"


@pytest.mark.parametrize("exhibit", [False, True])
def test_resolves_only_the_registered_body_and_records_actual_source(tmp_path, exhibit):
    raw, rule, docs = make_case(exhibit)
    rules = write_rules(tmp_path / "rules.json", [rule])
    result = resolve_section(raw, PRIMARY, ACCESSION, rules, lambda url: (docs[url], {}))
    assert result.extraction.status == "ok"
    assert result.extraction.text == BODY.strip()
    assert result.source_url == (EXHIBIT if exhibit else PRIMARY)
    assert result.index_url == (INDEX if exhibit else "")
    assert "pending" in result.extraction.reason
    assert result.rule_id


def test_changed_primary_source_cannot_reuse_a_rule():
    raw, rule, _ = make_case()
    with pytest.raises(ValueError, match="Primary source differs"):
        resolve_section(raw + b" ", PRIMARY, ACCESSION, {ACCESSION: rule})


@pytest.mark.parametrize("field,value", [("end_offset", 999999), ("text_sha256", "0" * 64),
                                        ("token_count", 301)])
def test_invalid_boundary_or_content_evidence_is_rejected(field, value):
    raw, rule, _ = make_case()
    rule[field] = value
    with pytest.raises(ValueError, match="range is outside|Resolved text differs"):
        resolve_section(raw, PRIMARY, ACCESSION, {ACCESSION: rule})


def test_rule_cannot_override_a_substantive_numbered_section():
    raw, rule, _ = make_case()
    raw = raw.replace(b"Pages 4-5", BODY.encode())
    rule.update(primary_sha256=sha256(raw), primary_reference_sha256=sha256(extract_risk_factors(raw).text))
    with pytest.raises(ValueError, match="Numbered Item 1A reference"):
        resolve_section(raw, PRIMARY, ACCESSION, {ACCESSION: rule})


@pytest.mark.parametrize("source", ["https://example.org/risks.htm",
                                    DIRECTORY.replace("000000012319000001", "000000012320000001") + "risks.htm",
                                    "https://www.sec.gov/Archives/edgar/data/999/000000099919000001/risks.htm"])
def test_exhibit_cannot_escape_original_accession(source):
    raw, rule, _ = make_case(True)
    rule["source_url"] = source
    calls = []
    with pytest.raises(ValueError, match="original accession directory"):
        resolve_section(raw, PRIMARY, ACCESSION, {ACCESSION: rule}, lambda url: calls.append(url))
    assert calls == []


@pytest.mark.parametrize("mode", ["wrong_type", "duplicate", "changed_index", "changed_exhibit"])
def test_exhibit_requires_unique_typed_index_membership_and_source_hash(mode):
    raw, rule, docs = make_case(True)
    if mode == "wrong_type":
        docs[INDEX] = docs[INDEX].replace(b"EX-99", b"EX-13")
        rule["index_sha256"] = sha256(docs[INDEX])
    elif mode == "duplicate":
        docs[INDEX] = docs[INDEX] + docs[INDEX]
        rule["index_sha256"] = sha256(docs[INDEX])
    elif mode == "changed_index":
        docs[INDEX] += b" "
    else:
        docs[EXHIBIT] += b" "
    with pytest.raises(ValueError, match="unique EX-99|index differs|Risk source differs"):
        resolve_section(raw, PRIMARY, ACCESSION, {ACCESSION: rule}, lambda url: (docs[url], {}))


def test_loader_rejects_duplicate_accessions_and_stale_normalizer(tmp_path):
    _, rule, _ = make_case()
    path = tmp_path / "rules.json"
    with pytest.raises(ValueError, match="unique"):
        write_rules(path, [rule, rule])
    path.write_text(json.dumps({"schema_version": 1, "normalizer_version": "unregistered", "rules": [rule]}))
    with pytest.raises(ValueError, match="normalizer"):
        load_reference_rules(path)


def test_ingestion_and_offline_audit_preserve_exhibit_sources_and_original_timing(tmp_path, monkeypatch):
    raw, rule, docs = make_case(True)
    header_url = DIRECTORY + ACCESSION + ".hdr.sgml"
    docs[header_url] = b"<ACCEPTANCE-DATETIME>20190301100000"
    original = {"cik": "0000000123", "accessionNumber": ACCESSION, "form": "10-K",
                "filingDate": "2019-03-01", "reportDate": "2018-12-31",
                "acceptanceDateTime": "2019-03-01T15:00:00Z", "source_url": PRIMARY, "header_url": header_url}
    monkeypatch.setattr("disclosure_research.ingest.list_original_filings", lambda *args: [original])
    client = SecClient(tmp_path / "cache", "Test test@example.org", sleep=lambda _: None,
                       transport=httpx.MockTransport(lambda r: httpx.Response(200, content=docs[str(r.url)])))
    rule_path = tmp_path / "rules.json"
    rules = write_rules(rule_path, [rule])
    config = {"companies": [{"cik": "0000000123", "name": "Synthetic"}], "purpose": "test",
              "filing_year_start": 2019, "filing_year_end": 2019, "pair_year_start": 2019, "pair_year_end": 2019}
    summary = ingest_smoke(config, client, tmp_path / "data", rules)
    assert not summary["failures"] and summary["reference_resolutions"] == 1
    frame = pd.read_parquet(tmp_path / "data/filings.parquet")
    assert frame.iloc[0].risk_source_url == EXHIBIT
    assert frame.iloc[0].reference_session == "2019-03-05"
    assert frame.iloc[0].acceptance_timestamp == "2019-03-01T10:00:00-05:00"
    kwargs = {"filings": tmp_path / "data/filings.parquet", "cache": client.cache_dir,
              "output": tmp_path / "audit", "development_end": 2021, "resolutions": rule_path}
    audit = build_audit(**kwargs)
    assert audit["automated_evidence_ok"] == 1 and audit["human_reviews_complete"] == 0
    packet = (tmp_path / "audit/audit.html").read_text()
    assert EXHIBIT in packet and INDEX in packet
    review = json.loads((tmp_path / "audit/reviews.template.jsonl").read_text())
    review.update(reviewer="Synthetic reviewer", reviewer_type="human", reviewed_at="2026-10-09T22:00:00Z",
                  boundary_verdict="pass", timing_verdict="pass", notes="Synthetic fixture only")
    review_path = tmp_path / "reviews.jsonl"
    review_path.write_text(json.dumps(review) + "\n")
    assert build_audit(**kwargs, reviews=review_path)["human_reviews_complete"] == 1
    changed = copy.deepcopy(rule)
    changed["boundary_notes"] += " Revised boundary rationale."
    write_rules(rule_path, [changed])
    assert build_audit(**kwargs, reviews=review_path)["human_reviews_complete"] == 0
    evidence = pd.read_parquet(tmp_path / "audit/filing_evidence.parquet").iloc[0]
    assert "stale_review_fingerprint" in evidence.blocking_issues
    assert "stored_resolution_differs_from_sources" in evidence.blocking_issues


def test_annual_pair_retains_actual_sources_and_flags_method_transition():
    current = {"cik": "0000000123", "accessionNumber": ACCESSION, "acceptance_date": "2019-03-01",
               "reportDate": "2018-12-31", "extraction_status": "ok", "risk_text": BODY,
               "source_url": PRIMARY, "risk_source_url": EXHIBIT,
               "resolution_method": "same_accession_exhibit_range", "reference_session": "2019-03-05",
               "label_end": "2019-04-02"}
    previous = {**current, "accessionNumber": "0000000123-18-000001", "acceptance_date": "2018-03-01",
                "reportDate": "2017-12-31", "risk_source_url": PRIMARY, "resolution_method": "numbered_item1a"}
    pairs, _ = pair_filings([previous, current], 2019, 2019)
    assert pairs[0]["risk_source_url"] == EXHIBIT
    assert pairs[0]["resolution_method_changed"] is True
