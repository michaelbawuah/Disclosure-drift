import json
from dataclasses import asdict

import httpx
import pandas as pd
import pytest

from disclosure_research.audit import build_audit, load_reviews, select_review_pairs
from disclosure_research.edgar import SecClient
from disclosure_research.extraction import extract_risk_factors
from disclosure_research.timing import acceptance_from_header, event_window


@pytest.fixture
def audit_input(tmp_path):
    source_url = "https://www.sec.gov/Archives/example/annual.htm"
    header_url = "https://www.sec.gov/Archives/example/header.sgml"
    raw = ("<h2>Item 1A. Risk Factors</h2><p>" + "supply competition " * 150 +
           "</p><h2>Item 1B. Unresolved Staff Comments</h2><p>None.</p>").encode()
    header = b"<ACCEPTANCE-DATETIME>20190301100000"
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=raw if str(r.url) == source_url else header))
    client = SecClient(tmp_path / "cache", "Research test@example.org", transport=transport,
                       sleep=lambda _: None)
    _, body_meta = client.fetch(source_url)
    _, header_meta = client.fetch(header_url)
    accepted = acceptance_from_header(header.decode())
    window = event_window(accepted)
    extracted = extract_risk_factors(raw)
    row = {"accessionNumber": "0000000123-19-000001", "cik": "0000000123",
           "name": "Synthetic <script>company</script>", "filingDate": "2019-03-01",
           "reportDate": "2018-12-31", "source_url": source_url, "header_url": header_url,
           "download_sha256": body_meta["sha256"], "header_sha256": header_meta["sha256"],
           "risk_text": extracted.text, "risk_token_count": extracted.token_count,
           "extraction_version": extracted.version, "extraction_status": extracted.status,
           "acceptance_timestamp": accepted.isoformat(), "acceptanceDateTime": "2019-03-01T15:00:00Z",
           **{k: v for k, v in asdict(window).items() if k != "return_sessions"}}
    filings = tmp_path / "filings.parquet"
    pd.DataFrame([row]).to_parquet(filings, index=False)
    return {"filings": filings, "cache": tmp_path / "cache", "output": tmp_path / "audit",
            "development_end": 2021}


def completed_review(audit_input, reviewer_type="human"):
    build_audit(**audit_input)
    record = json.loads((audit_input["output"] / "reviews.template.jsonl").read_text())
    record.update(reviewer="Fixture reviewer", reviewer_type=reviewer_type,
                  reviewed_at="2026-10-09T20:00:00+00:00", boundary_verdict="pass",
                  timing_verdict="pass", notes="Synthetic fixture only; reviewed boundaries and header.")
    path = audit_input["output"] / "reviews.jsonl"
    path.write_text(json.dumps(record) + "\n")
    return path


def test_offline_audit_checks_sources_and_keeps_manual_review_pending(audit_input):
    summary = build_audit(**audit_input)
    assert summary["filings"] == summary["automated_evidence_ok"] == 1
    assert summary["human_reviews_complete"] == 0 and summary["manual_audit"] == "pending"
    html = (audit_input["output"] / "audit.html").read_text()
    assert "&lt;script&gt;company&lt;/script&gt;" in html and "<script>company" not in html
    evidence = pd.read_parquet(audit_input["output"] / "filing_evidence.parquet").iloc[0]
    assert evidence.verified_source and evidence.verified_header
    assert sum(len(evidence[k].split()) for k in ["start_context", "section_start", "section_end", "end_context"]) <= 24
    coverage = pd.read_parquet(audit_input["output"] / "coverage.parquet")
    assert coverage.automated_consistency_ok.tolist() == [1]


@pytest.mark.parametrize("reviewer_type, expected_human", [("human", 1), ("assistant", 0)])
def test_only_human_review_counts_as_human_signoff(audit_input, reviewer_type, expected_human):
    reviews = completed_review(audit_input, reviewer_type)
    summary = build_audit(**audit_input, reviews=reviews)
    assert summary["human_reviews_complete"] == expected_human
    assert summary["assistant_reviews_complete"] == 1 - expected_human
    assert reviews.exists()
    assert json.loads(reviews.read_text())["boundary_verdict"] == "pass"


def test_changed_text_invalidates_a_previous_review(audit_input):
    reviews = completed_review(audit_input)
    frame = pd.read_parquet(audit_input["filings"])
    frame.loc[0, "risk_text"] += " altered text"
    frame.to_parquet(audit_input["filings"], index=False)
    summary = build_audit(**audit_input, reviews=reviews)
    assert summary["human_reviews_complete"] == 0
    evidence = pd.read_parquet(audit_input["output"] / "filing_evidence.parquet").iloc[0]
    assert "stale_review_fingerprint" in evidence.blocking_issues
    assert "stored_extraction_differs_from_source" in evidence.blocking_issues


def test_corrupted_cache_is_reported_without_false_signoff(audit_input):
    reviews = completed_review(audit_input)
    for source in audit_input["cache"].glob("*.bin"):
        source.write_bytes(b"tampered")
    summary = build_audit(**audit_input, reviews=reviews)
    assert summary["filings_with_blocking_issues"] == 1
    assert summary["human_reviews_complete"] == 0


def test_audit_rejects_final_period_filings(audit_input):
    frame = pd.read_parquet(audit_input["filings"])
    frame.loc[0, "acceptance_date"] = "2022-03-01"
    frame.to_parquet(audit_input["filings"], index=False)
    with pytest.raises(ValueError, match="development-year"):
        build_audit(**audit_input)


def test_reviews_require_unique_named_evidence_with_notes(audit_input):
    reviews = completed_review(audit_input)
    contents = reviews.read_text()
    reviews.write_text(contents + contents)
    with pytest.raises(ValueError, match="Duplicate"):
        load_reviews(reviews)
    record = json.loads(contents)
    record["notes"] = ""
    reviews.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="named reviewer and notes"):
        load_reviews(reviews)


def test_pair_review_sample_is_stable_and_covers_issuers():
    pairs = pd.DataFrame([{"cik": str(cik), "accession": f"{cik}-{year}",
                           "previous_accession": f"{cik}-{year - 1}",
                           "acceptance_date": f"{year}-03-01", "source_url": "https://www.sec.gov/current",
                           "previous_source_url": "https://www.sec.gov/previous"}
                          for cik in range(20) for year in range(2015, 2022)])
    first = select_review_pairs(pairs)
    second = select_review_pairs(pairs.sample(frac=1, random_state=4))
    assert len(first) == 30 and first.cik.nunique() == 20
    assert first.accession.tolist() == second.accession.tolist()


def test_pair_table_cannot_reference_unrelated_filings(audit_input):
    paired = audit_input["filings"].with_name("filing_pairs.parquet")
    pd.DataFrame([{"accession": "unknown", "previous_accession": "also-unknown"}]).to_parquet(paired)
    with pytest.raises(ValueError, match="outside the audited"):
        build_audit(**audit_input)
