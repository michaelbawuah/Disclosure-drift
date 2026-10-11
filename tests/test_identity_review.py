"""Identity failures must stay visible even when a ticker or header CIK matches."""

import json
from pathlib import Path

import pandas as pd
import pytest

from disclosure_research.identity_review import _header, build_identity_review
from disclosure_research.cli import main
from disclosure_research.market_data import sha256
from disclosure_research.protocol import load_protocol


@pytest.fixture
def inputs(tmp_path):
    cache, audit = tmp_path / "cache", tmp_path / "audit"
    cache.mkdir()
    audit.mkdir()
    filings, evidence = [], []
    for year, digest in [(2020, "2" * 64), (2021, "1" * 64)]:
        accession = f"0000000001-{year % 100}-000001"
        url = f"https://www.sec.gov/Archives/invented/{accession}.hdr.sgml"
        raw = (f"<ACCESSION-NUMBER>{accession}\n<TYPE>10-K\n<FILER><COMPANY-DATA>\n"
               "<CONFORMED-NAME>Invented & Company\n<CIK>0000000001\n"
               "</COMPANY-DATA></FILER>").encode()
        key = sha256(url.encode())
        (cache / f"{key}.bin").write_bytes(raw)
        (cache / f"{key}.json").write_text(json.dumps({"url": url, "sha256": sha256(raw)}))
        filings.append({"accessionNumber": accession, "cik": "0000000001",
                        "acceptance_timestamp": f"{year}-07-02T18:30:00-04:00",
                        "source_url": "https://www.sec.gov/Archives/invented/annual.htm",
                        "header_url": url, "header_sha256": sha256(raw)})
        evidence.append({"accession": accession, "cik": "0000000001", "evidence_id": digest,
                         "automated_evidence_ok": True})
    filings_path = tmp_path / "filings.parquet"
    pd.DataFrame(filings).to_parquet(filings_path, index=False)
    pd.DataFrame(evidence).to_parquet(audit / "filing_evidence.parquet", index=False)
    pairs = tmp_path / "filing_pairs.parquet"
    pd.DataFrame([{"accession": filings[1]["accessionNumber"], "previous_accession": filings[0]["accessionNumber"],
                   "cik": "0000000001"}]).to_parquet(pairs, index=False)
    source_hash = sha256(filings_path.read_bytes())
    (audit / "audit_summary.json").write_text(json.dumps({"source_table_sha256": source_hash,
        "pair_table_sha256": sha256(pairs.read_bytes()),
        "evidence_table_sha256": sha256((audit / "filing_evidence.parquet").read_bytes())}))
    events = tmp_path / "events.parquet"
    pd.DataFrame([{"event_id": filings[1]["accessionNumber"], "cik": "0000000001",
                   "previous_accession": filings[0]["accessionNumber"], "data_kind": "REAL_FILING_EVENTS",
                   "acceptance_timestamp": filings[1]["acceptance_timestamp"],
                   "filing_source_table_sha256": source_hash,
                   "current_evidence_id": "1" * 64, "previous_evidence_id": "2" * 64}]).to_parquet(events, index=False)
    companies = tmp_path / "companies.json"
    companies.write_text(json.dumps({"companies": [{"cik": "0000000001", "ticker": "SAME"}]}))
    ccm = tmp_path / "ccm.csv"
    common = {"gvkey": "000123", "conm": "Invented Company", "tic": "SAME", "cusip": "123456789",
              "cik": "0000000001", "LINKPRIM": "P", "LIID": "01", "LINKTYPE": "LU",
              "LPERMNO": "12345", "LPERMCO": "99", "LINKDT": "2010-01-01", "LINKENDDT": "E"}
    pd.DataFrame([common, {**common, "LINKTYPE": "NU", "LPERMNO": "", "LPERMCO": "",
                           "LINKDT": "2000-01-01", "LINKENDDT": "2009-12-31"}]).to_csv(ccm, index=False)
    names = tmp_path / "names.csv"
    n = {"permno": "12345", "permco": "99", "secinfostartdt": "2010-01-01",
         "secinfoenddt": "2021-06-30", "cusip": "12345678", "ticker": "OLD",
         "issuernm": "Invented Old Name", "shareclass": "", "securitytype": "EQTY",
         "securitysubtype": "COM", "sharetype": "NS", "siccd": "1234"}
    pd.DataFrame([n, {**n, "secinfostartdt": "2021-07-01", "secinfoenddt": "2021-12-31",
                      "ticker": "NEW", "issuernm": "Invented New Name"}]).to_csv(names, index=False)
    return {"events_path": events, "filings_path": filings_path, "audit_path": audit,
            "companies_path": companies, "ccm_paths": [ccm], "names_path": names,
            "cache": cache, "output": tmp_path / "review", "config": load_protocol()}


def source_edit(path, operation):
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame = operation(frame)
    frame.to_csv(path, index=False)


def queue(inputs):
    return pd.read_parquet(inputs["output"] / "event_identity_queue.parquet").iloc[0]


def test_dated_evidence_keeps_markers_and_never_approves_links(inputs):
    summary = build_identity_review(**inputs)
    assert summary["filing_headers_identity_consistent"] == 2
    assert summary["events_with_one_candidate_security"] == 1
    assert summary["events_with_interval_coverage_issues"] == 0
    assert summary["ccm_rows_without_security_id"] == 1
    assert summary["candidate_rows_with_unresolved_end_marker"] == 1
    assert not summary["market_returns_loaded"] and not summary["model_ready"]
    assert summary["approved_security_links_created"] == summary["human_reviews_completed"] == 0
    assert not (inputs["output"] / "security_links.parquet").exists()
    row = queue(inputs)
    assert row.required_sessions == 81
    assert row.controls_asof == "2021-07-06" and row.reference_session == "2021-07-07"
    assert row.label_end == "2021-08-04"
    assert row.identity_review == "pending" and not row.identity_approved
    candidate = pd.read_parquet(inputs["output"] / "candidate_links.parquet").iloc[0]
    assert candidate.ccm_link_end_raw == "E"
    assert json.loads(candidate.names_source_records) == [2, 3]
    assert summary == json.loads((inputs["output"] / "identity_summary.json").read_text())
    for name, digest in summary["files"].items():
        assert sha256((inputs["output"] / name).read_bytes()) == digest
    template = json.loads((inputs["output"] / "identity_reviews.template.jsonl").read_text())
    assert template["identity_verdict"] == "pending" and template["selected_permno"] == ""
    assert template["evidence_id"] == row.evidence_id


def test_explicit_discovery_cik_does_not_rewrite_historical_cik(inputs):
    source_edit(inputs["ccm_paths"][0], lambda f: f.assign(cik="0000000002"))
    inputs["companies_path"].write_text(json.dumps({"companies": [
        {"cik": "0000000001", "discovery_cik": "0000000002", "ticker": "SAME"}]}))
    summary = build_identity_review(**inputs)
    row = queue(inputs)
    assert summary["events_with_header_cik_difference"] == 1
    assert row.cik == "0000000001" and row.review_priority == "resolve_header_cik"
    assert not row.identity_approved


def test_same_ticker_without_cik_evidence_does_not_make_a_candidate(inputs):
    source_edit(inputs["ccm_paths"][0], lambda f: f.assign(cik="0000000002"))
    summary = build_identity_review(**inputs)
    assert summary["events_without_candidate_security"] == 1
    assert queue(inputs).review_priority == "resolve_missing_candidate"
    assert "No candidate security" in (inputs["output"] / "identity_review.html").read_text()


def test_multiple_securities_are_all_retained_without_picking_first(inputs):
    source_edit(inputs["ccm_paths"][0], lambda f: pd.concat([f, f.iloc[[0]].assign(LPERMNO="54321", LIID="02")]))
    build_identity_review(**inputs)
    row = queue(inputs)
    assert row.candidate_security_count == 2
    assert row.review_priority == "resolve_multiple_candidates"
    assert not row.identity_approved


@pytest.mark.parametrize("problem", ["gap", "overlap", "permco", "link_start", "link_end"])
def test_interior_gaps_ambiguity_and_link_bounds_remain_visible(inputs, problem):
    if problem in {"gap", "overlap", "permco"}:
        def edit(f):
            if problem == "gap":
                f.loc[0, "secinfoenddt"] = "2021-06-28"
            elif problem == "overlap":
                f.loc[0, "secinfoenddt"] = "2021-07-02"
            else:
                f.loc[0, "permco"] = "999"
            return f
        source_edit(inputs["names_path"], edit)
    else:
        def edit(f):
            f.loc[0, "LINKDT" if problem == "link_start" else "LINKENDDT"] = "2021-07-01"
            return f
        source_edit(inputs["ccm_paths"][0], edit)
    summary = build_identity_review(**inputs)
    assert summary["events_with_interval_coverage_issues"] == 1
    assert queue(inputs).review_priority == "resolve_interval_coverage"


def test_corrupt_cached_header_cannot_be_consistent(inputs):
    next(inputs["cache"].glob("*.bin")).write_bytes(b"changed")
    summary = build_identity_review(**inputs)
    assert summary["filing_headers_identity_consistent"] == 1
    assert queue(inputs).review_priority == "resolve_sec_header"


def test_holdout_is_blocked_before_vendor_sources_are_opened(inputs):
    events = pd.read_parquet(inputs["events_path"])
    events.loc[0, "acceptance_timestamp"] = "2022-01-03T10:00:00-05:00"
    events.to_parquet(inputs["events_path"], index=False)
    inputs["ccm_paths"] = [Path("does-not-exist.csv")]
    with pytest.raises(ValueError, match="holdout"):
        build_identity_review(**inputs)
    assert not inputs["output"].exists()


@pytest.mark.parametrize("problem,pattern", [("hash", "bound"), ("evidence", "stale"),
                                           ("timestamp", "timestamp")])
def test_event_provenance_cannot_be_changed(inputs, problem, pattern):
    events = pd.read_parquet(inputs["events_path"])
    key, value = {"hash": ("filing_source_table_sha256", "9" * 64),
                  "evidence": ("previous_evidence_id", "9" * 64),
                  "timestamp": ("acceptance_timestamp", "2021-07-02T17:30:00-04:00")}[problem]
    events.loc[0, key] = value
    events.to_parquet(inputs["events_path"], index=False)
    with pytest.raises(ValueError, match=pattern):
        build_identity_review(**inputs)
    assert not inputs["output"].exists()


@pytest.mark.parametrize("problem,pattern", [("unknown_end", "ISO"), ("reversed", "Reversed"),
                                            ("duplicate", "Duplicate"), ("id", "identifiers")])
def test_malformed_source_records_are_not_silently_fixed(inputs, problem, pattern):
    def edit(f):
        if problem == "unknown_end":
            f.loc[0, "LINKENDDT"] = "?"
        elif problem == "reversed":
            f.loc[0, "LINKENDDT"] = "2001-01-01"
        elif problem == "id":
            f.loc[0, "LPERMNO"] = "12345.0"
        else:
            return pd.concat([f, f.iloc[[0]]])
        return f
    source_edit(inputs["ccm_paths"][0], edit)
    with pytest.raises(ValueError, match=pattern):
        build_identity_review(**inputs)
    assert not inputs["output"].exists()


def test_packet_escapes_source_text_and_preserves_prior_output(inputs):
    source_edit(inputs["names_path"], lambda f: f.assign(issuernm="<script>alert(1)</script>"))
    build_identity_review(**inputs)
    html = (inputs["output"] / "identity_review.html").read_text()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "<script>" not in html
    before = (inputs["output"] / "identity_summary.json").read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        build_identity_review(**inputs)
    assert before == (inputs["output"] / "identity_summary.json").read_bytes()


def test_previous_accession_must_match_the_audited_annual_pair(inputs):
    events = pd.read_parquet(inputs["events_path"])
    events.loc[0, "previous_accession"] = events.loc[0, "event_id"]
    events.loc[0, "previous_evidence_id"] = events.loc[0, "current_evidence_id"]
    events.to_parquet(inputs["events_path"], index=False)
    with pytest.raises(ValueError, match="audited annual pair"):
        build_identity_review(**inputs)


@pytest.mark.parametrize("problem", ["cik", "accession", "multiple_filers"])
def test_hash_consistent_but_wrong_header_identity_is_flagged(inputs, problem):
    filings = pd.read_parquet(inputs["filings_path"])
    url = filings.loc[0, "header_url"]
    key = sha256(url.encode())
    raw = (inputs["cache"] / f"{key}.bin").read_text()
    if problem == "cik":
        raw = raw.replace("<CIK>0000000001", "<CIK>0000000002")
    elif problem == "accession":
        raw = raw.replace("<ACCESSION-NUMBER>0000000001-20-000001", "<ACCESSION-NUMBER>another-accession")
    else:
        raw += "<FILER><COMPANY-DATA><CIK>0000000001</COMPANY-DATA></FILER>"
    digest = sha256(raw.encode())
    (inputs["cache"] / f"{key}.bin").write_text(raw)
    (inputs["cache"] / f"{key}.json").write_text(json.dumps({"url": url, "sha256": digest}))
    filings.loc[0, "header_sha256"] = digest
    filings.to_parquet(inputs["filings_path"], index=False)
    source_hash = sha256(inputs["filings_path"].read_bytes())
    events = pd.read_parquet(inputs["events_path"])
    events["filing_source_table_sha256"] = source_hash
    events.to_parquet(inputs["events_path"], index=False)
    summary_path = inputs["audit_path"] / "audit_summary.json"
    summary = json.loads(summary_path.read_text())
    summary["source_table_sha256"] = source_hash
    summary_path.write_text(json.dumps(summary))
    result = build_identity_review(**inputs)
    assert result["filing_headers_identity_consistent"] == 1
    assert queue(inputs).review_priority == "resolve_sec_header"


def test_cli_reproduces_the_same_packet_without_network_or_returns(inputs, capsys):
    first = build_identity_review(**inputs)
    second_output = inputs["output"].with_name("cli-review")
    argv = ["review-identities"]
    for flag, key in [("events", "events_path"), ("filings", "filings_path"), ("audit", "audit_path"),
                      ("companies", "companies_path"), ("names", "names_path"), ("cache", "cache")]:
        argv.extend([f"--{flag}", str(inputs[key])])
    argv.extend(["--ccm", *map(str, inputs["ccm_paths"]), "--output", str(second_output)])
    assert main(argv) == 0
    second = json.loads(capsys.readouterr().out)
    assert first == second


def test_header_retains_distinct_cofiler_and_keeps_only_unique_original_match(inputs):
    filing = pd.read_parquet(inputs["filings_path"]).iloc[0].to_dict()
    key = sha256(filing["header_url"].encode())
    path = inputs["cache"] / f"{key}.bin"
    raw = path.read_bytes() + (b"<FILER><COMPANY-DATA><CIK>0000000002\n"
                               b"<CONFORMED-NAME>Other Co-Filer\n</COMPANY-DATA></FILER>")
    path.write_bytes(raw)
    filing["header_sha256"] = sha256(raw)
    (inputs["cache"] / f"{key}.json").write_text(json.dumps({"url": filing["header_url"], "sha256": sha256(raw)}))
    result = _header(filing, inputs["cache"])
    assert result["header_identity_ok"] is True
    assert result["header_cik"] == "0000000001" and result["header_name"] == "Invented & Company"
    assert result["header_filer_count"] == 2 and result["matching_filer_count"] == 1
    context = json.loads(result["header_filers_json"])
    assert [row["matches_manifest_cik"] for row in context] == [True, False]
    # A second occurrence of the original filer remains ambiguous, even when
    # every source byte/hash is valid; the existing review gate stays closed.
    raw += b"<FILER><COMPANY-DATA><CIK>0000000001\n<CONFORMED-NAME>Repeated Original\n</COMPANY-DATA></FILER>"
    path.write_bytes(raw)
    filing["header_sha256"] = sha256(raw)
    (inputs["cache"] / f"{key}.json").write_text(json.dumps({"url": filing["header_url"], "sha256": sha256(raw)}))
    repeated = _header(filing, inputs["cache"])
    assert repeated["header_identity_ok"] is False and repeated["matching_filer_count"] == 2
    assert len(json.loads(repeated["header_filers_json"])) == 3
