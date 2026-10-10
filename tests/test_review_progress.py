import copy
import json
from datetime import datetime, timedelta, timezone
from zipfile import ZipFile

import pytest

from disclosure_research.market_data import sha256
from disclosure_research.pilot_audit import MEASURES
from disclosure_research.review_progress import (
    ARCHIVE_PREFIX,
    USER_REVIEW_SCOPE,
    independent_header_clock,
    inspect_names_query,
    record_user_arithmetic_review,
    verify_recheck_results,
)


def encoded(value):
    return (json.dumps(value, allow_nan=False) + "\n").encode()


@pytest.fixture
def reviewed_packet(tmp_path):
    # All invented values are for contract testing, not research review evidence.
    traces = [{"event_id": f"0000000001-19-{i:06d}", "evidence_id": f"{i:064d}"}
              for i in range(20)]
    results = [dict(t, issues=[], diffs={k: 0.0 for k in MEASURES}, max_diff=0.0) for t in traces]
    templates = [dict(t, controls_verdict="pending", label_verdict="pending") for t in traces]
    def jsonl(rows):
        return b"".join(encoded(r) for r in rows)
    packet = tmp_path / "packet"
    packet.mkdir()
    original = {"review.html": b"Synthetic test packet",
                "independent_traces.jsonl": jsonl(traces),
                "trace_reviews.template.jsonl": jsonl(templates)}
    for name, raw in original.items():
        (packet / name).write_bytes(raw)
    receipt = encoded({"files": {name: sha256(raw) for name, raw in original.items()}})
    (packet / "audit_summary.json").write_bytes(receipt)
    data = {f"original_fixed20/{name}": raw for name, raw in original.items()}
    data.update({"original_fixed20/audit_summary.json": receipt,
                 "user_recheck_results.json": encoded(results),
                 "user_submission/pilot-recheck.py": b"# Synthetic fixture; never execute\n",
                 "user_submission/review-verdicts-DRAFT.jsonl": jsonl(templates)})
    data["followup_summary.json"] = encoded({
        "original_arithmetic_receipt_sha256": sha256(receipt),
        "submitted_recheck": {
            "results_sha256": sha256(data["user_recheck_results.json"]),
            "submitted_draft_sha256": sha256(data["user_submission/review-verdicts-DRAFT.jsonl"])}})
    manifest = {name: {"bytes": len(raw), "sha256": sha256(raw)} for name, raw in data.items()}
    data["delivery_manifest.json"] = encoded(manifest)
    archive = tmp_path / "submission.zip"
    with ZipFile(archive, "w") as z:
        for name, raw in data.items():
            z.writestr(ARCHIVE_PREFIX + name, raw)
    statement = tmp_path / "statement.json"
    statement.write_bytes(encoded({"reviewer_type": "human", "reviewer": "Invented fixture reviewer",
                                  "verdict": "pass", "scope": USER_REVIEW_SCOPE,
                                  "statement": "Synthetic test of recording an explicit prior pass.",
                                  "source_kind": "prior_user_message",
                                  "source_reference": "synthetic fixture message",
                                  "original_reviewed_at": None}))
    return archive, packet, statement, tmp_path / "record", traces, results


def test_exact_review_preserves_unknown_time_and_does_not_promote_scope(reviewed_packet):
    archive, packet, statement, output, traces, _ = reviewed_packet
    result = record_user_arithmetic_review(archive, packet, statement, output)
    assert result["user_arithmetic_and_packet_timing_passes"] == 20
    assert result["original_review_time_unknown"] is True
    assert result["original_reviewed_at"] is None
    assert result["legacy_full_source_trace_review_imported"] is False
    assert result["new_human_raw_source_reviews"] == 0
    assert result["new_human_identity_reviews"] == 0
    rows = [json.loads(r) for r in (output / "user_arithmetic_reviews.recorded.jsonl").read_text().splitlines()]
    assert [(r["event_id"], r["evidence_id"]) for r in rows] == [(r["event_id"], r["evidence_id"]) for r in traces]
    assert all(r["reviewer_type"] == "human" and r["recorded_by"] == "assistant" for r in rows)
    assert all("controls_verdict" not in r and r["raw_csv_review_verdict"] == "not_declared" for r in rows)
    with pytest.raises(ValueError, match="Preserve"):
        record_user_arithmetic_review(archive, packet, statement, output)


def test_changed_local_packet_cannot_receive_prior_verdict(reviewed_packet):
    archive, packet, statement, output, _, _ = reviewed_packet
    (packet / "review.html").write_text("changed")
    with pytest.raises(ValueError, match="Original packet changed"):
        record_user_arithmetic_review(archive, packet, statement, output)
    assert not output.exists()


@pytest.mark.parametrize("mutation", ["duplicate", "missing_measure", "nan", "wrong_max", "wrong_evidence", "issues"])
def test_recheck_results_reject_unsupported_passes(reviewed_packet, mutation):
    *_, traces, results = reviewed_packet
    rows = copy.deepcopy(results)
    if mutation == "duplicate":
        rows[-1] = rows[0]
    elif mutation == "missing_measure":
        del rows[0]["diffs"]["target"]
    elif mutation == "nan":
        rows[0]["diffs"]["target"] = float("nan")
    elif mutation == "wrong_max":
        rows[0]["max_diff"] = 1e-16
    elif mutation == "wrong_evidence":
        rows[0]["evidence_id"] = "not the reviewed evidence"
    else:
        rows[0]["issues"] = ["one return was altered"]
    with pytest.raises(ValueError):
        verify_recheck_results(rows, traces)


def test_user_statement_cannot_be_extended_to_identity_or_future_timestamp(reviewed_packet):
    archive, packet, statement, output, _, _ = reviewed_packet
    declared = json.loads(statement.read_bytes())
    declared["scope"] = USER_REVIEW_SCOPE + ["historical_identity"]
    statement.write_bytes(encoded(declared))
    with pytest.raises(ValueError, match="scope"):
        record_user_arithmetic_review(archive, packet, statement, output)
    declared["scope"] = USER_REVIEW_SCOPE
    declared["original_reviewed_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    statement.write_bytes(encoded(declared))
    with pytest.raises(ValueError, match="future"):
        record_user_arithmetic_review(archive, packet, statement, output)


def test_reproduction_must_match_all_saved_values(reviewed_packet, tmp_path):
    archive, packet, statement, output, _, results = reviewed_packet
    results[0]["diffs"]["target"] = 1e-16
    results[0]["max_diff"] = 1e-16
    repeated = tmp_path / "repeated.json"
    repeated.write_bytes(encoded(results))
    with pytest.raises(ValueError, match="differs from the saved"):
        record_user_arithmetic_review(archive, packet, statement, output, repeated)


def test_independent_original_header_clock_handles_holiday_and_excludes_reference_return(tmp_path):
    url = "https://www.sec.gov/Archives/edgar/data/1/original.hdr.sgml"
    raw = b"<ACCEPTANCE-DATETIME>20200214163000\n"
    key = sha256(url.encode())
    (tmp_path / f"{key}.bin").write_bytes(raw)
    (tmp_path / f"{key}.json").write_bytes(encoded({"url": url, "sha256": sha256(raw)}))
    row = {"accession": "synthetic", "evidence_id": "fixture", "header_url": url,
           "header_sha256": sha256(raw), "acceptance_timestamp": "2020-02-14T16:30:00-05:00",
           "api_timestamp": "2020-02-14T21:30:00Z", "reference_session": "2020-02-19",
           "controls_through": "2020-02-18", "label_end": "2020-03-18"}
    check = independent_header_clock(row, tmp_path)
    assert check["source_clock_pass"] is True
    assert check["public_dissemination_verified"] is False
    row["label_end"] = "2020-03-17"
    with pytest.raises(ValueError, match="Stored event clock differs"):
        independent_header_clock(row, tmp_path)


def test_names_query_cannot_claim_other_columns_or_population(tmp_path):
    query, names = tmp_path / "query.sql", tmp_path / "names.csv"
    query.write_text("SELECT crsp_a_stock.wrds_names_query.permno, "
                     "crsp_a_stock.wrds_names_query.ticker FROM crsp_a_stock.wrds_names_query "
                     "WHERE permno IN ('1','2')")
    names.write_text("permno,ticker\n1,A\n2,B\n")
    result = inspect_names_query(query, names)
    assert result["query_csv_selector_and_columns_match"] is True
    assert result["source_release_verified"] is False
    names.write_text("permno,ticker\n1,A\n3,C\n")
    with pytest.raises(ValueError, match="identifiers differ"):
        inspect_names_query(query, names)
