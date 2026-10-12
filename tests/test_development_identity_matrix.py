"""Synthetic integration and interval-mutation tests for retrospective identity matrix."""

import csv
import gzip
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from disclosure_research.controls import control_sessions
from disclosure_research.development_identity_matrix import (
    _CCM_FIELDS,
    _inspect_window_names,
    _same_company_security_context,
    _render_private_review,
    run_development_identity_matrix,
)
from disclosure_research.pilot_issuer_anchor import run_pilot_anchor
from disclosure_research.protocol import canonical_hash
from disclosure_research.tenk_symbol_corrob import run_tenk_symbol_corrob
from disclosure_research.timing import event_window
from test_pilot_issuer_anchor import example as issuer_fixture  # noqa: F401


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _fact(symbol, *, hidden=False):
    return {
        "concept_qname_raw": "dei:TradingSymbol",
        "text_from_parsed_html": symbol, "contextref_raw": "SyntheticCommonMember",
        "lexical_issues": [], "nil_attributes_raw": [],
        "inside_hidden_element": hidden, "hidden_by_inline_style_observed": hidden,
        "security_link_created": False, "interpreted_xbrl_value": None,
    }


@pytest.fixture
def prepared(issuer_fixture):  # noqa: F811
    x = issuer_fixture
    root = x["repo"]
    config = x["config"]
    df = pd.read_parquet(x["market"] / "candidate_calculations.parquet")
    times = [event_window(datetime.fromisoformat(stamp)) for stamp in df.acceptance_timestamp]
    df["reference_session"] = [w.reference_session for w in times]
    df["controls_asof"] = [w.controls_through for w in times]
    df["label_end"] = [w.label_end for w in times]
    df["control_history_start"] = [control_sessions(w)[0] for w in times]
    df["header_cik_differs"] = df["cik"].eq(df.iloc[0].cik)
    df["open_end_unresolved"] = True
    df.to_parquet(x["market"] / "candidate_calculations.parquet", index=False)
    market_receipt_file = x["market"] / "audit_summary.json"
    market_receipt = json.loads(market_receipt_file.read_text())
    market_receipt["files"]["candidate_calculations.parquet"] = _sha(
        x["market"] / "candidate_calculations.parquet"
    )
    market_receipt_file.write_text(json.dumps(market_receipt))
    # Retain the previous 215 invented original SEC records, but add three
    # original-cover lexical symbol occurrences in 2020 for the test scenario.
    source = json.loads(gzip.decompress(x["sec_gzip"].read_bytes()))
    source["xbrl_fact_values_interpreted"] = False
    for row in source["records"]:
        row["cover_evidence"] = {"facts": []}
    current = {r["accession"]: r for r in source["records"]}
    rows2020 = df[df["acceptance_timestamp"].str.startswith("2020")].head(3)
    for i, item in enumerate(rows2020.itertuples()):
        cik_i = int(item.candidate_permno) - 5000
        sym = f"Q{cik_i:02d}"
        if i == 0:
            facts = [_fact(sym)]
        elif i == 1:
            facts = [_fact(sym, hidden=True)]
        else:
            facts = [_fact(sym), _fact("UNMATCHED-SECOND-CLASS")]
        current[item.event_id]["cover_evidence"]["facts"] = facts
    original_bytes = json.dumps(source).encode()
    x["sec_gzip"].write_bytes(gzip.compress(original_bytes, mtime=0))
    pub = json.loads(x["sec_execution"].read_text())
    pub["publication"] = {
        "sha256": _sha(x["sec_gzip"]),
        "bytes": x["sec_gzip"].stat().st_size,
        "uncompressed_sha256": hashlib.sha256(original_bytes).hexdigest(),
        "uncompressed_bytes": len(original_bytes),
    }
    x["sec_execution"].write_text(json.dumps(pub))
    with x["names"].open(encoding="utf-8", newline="") as file:
        fields = next(csv.reader(file))
    name_receipt = {
        "status": "RAW_MANUAL_WRDS_METADATA_INVENTORY_NOT_SOURCE_APPROVED",
        "model_ready": False, "source_approvals": 0,
        "protocol_sha256": canonical_hash(config),
        "source": {"observed_header": fields, "sha256": _sha(x["names"]),
                   "bytes": x["names"].stat().st_size},
        "all_rows": {"rows": 20},
    }
    inventory = x["names"].parent / "original_names_inventory.json"
    inventory.write_text(json.dumps(name_receipt))
    x["inventory"] = inventory
    # Two independent original CCM files with identical schema, 19 + 1 rows.
    ccm_dir = root / "data" / "ccm"
    ccm_dir.mkdir(parents=True)
    ccm_records = []
    for i in range(20):
        row = {key: "" for key in _CCM_FIELDS}
        row.update({
            "gvkey": f"{i+1:06d}", "cik": f"{1200000000+i:010d}",
            "LPERMNO": str(5000+i), "LPERMCO": str(8000+i),
            "LINKPRIM": "P", "LINKTYPE": "LU", "LIID": "01",
            "LINKDT": "2010-01-01", "LINKENDDT": "E",
        })
        if i == 0:
            row["cik"] = "0000001111"  # explicit successor/current header conflict
        ccm_records.append(row)
    files = []
    for name, subset in (("crsp_ccm_pilot.csv", ccm_records[1:]),
                         ("crsp_ccm_xom.csv", ccm_records[:1])):
        p = ccm_dir / name
        with p.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(_CCM_FIELDS))
            writer.writeheader()
            writer.writerows(subset)
        files.append(p)
    ccm_summary_path = root / "reports" / "identity_pilot_summary.json"
    ccm_summary_path.write_text(json.dumps({
        "source_hashes": {"ccm": {p.name: _sha(p) for p in files}}
    }))
    x["ccm"] = files
    x["ccm_summary"] = ccm_summary_path
    anchor_output = root / "outputs" / "anchor"
    anchor_output.parent.mkdir(parents=True, exist_ok=True)
    run_pilot_anchor(
        x["market"], x["ownership"], x["names"], x["sec_gzip"], x["sec_execution"],
        anchor_output, config=config, repo_root=root,
        ownership_receipt_sha256=_sha(x["ownership"] / "receipt.json"),
        candidate_receipt_sha256=_sha(x["market"] / "audit_summary.json"),
    )
    x["anchor"] = anchor_output
    tenk_output = root / "outputs" / "tenk"
    run_tenk_symbol_corrob(
        x["market"], x["sec_gzip"], x["sec_execution"], x["names"], _sha(x["names"]),
        inventory, tenk_output, config=config, repo_root=root,
    )
    x["tenk"] = tenk_output
    x["output"] = root / "outputs" / "matrix"
    return x


def execute(x):
    return run_development_identity_matrix(
        x["market"], x["names"], x["inventory"], x["ccm"], x["ccm_summary"],
        x["sec_gzip"], x["sec_execution"], x["tenk"], x["anchor"], x["output"],
        config=x["config"], repo_root=x["repo"],
    )


def test_event_matrix_81_session_coverage_source_provenance_and_closed_gates(prepared):
    result = execute(prepared)
    observed = result["counts"]
    assert result["issuer_count"] == 20
    assert observed["events"] == 135
    assert observed["required_session_checks"] == 10935
    assert observed["unique_names_descriptors_at_81_required_sessions"] == 135
    assert observed["unique_ccm_link_candidate_at_acceptance"] == 135
    assert observed["permanent_company_ID_consistent_for_all_81_sessions"] == 135
    assert observed["original_filing_CIK_and_clock_validated_by_prior_SEC_source_report"] == 135
    assert observed["current_ccm_company_header_CIK_differences"] == 7
    assert observed["open_ended_CCM_links"] == 135
    assert observed["dated_names_descriptor_transition_windows"] == 0
    assert observed["eight_char_cusip_change_windows"] == 0
    assert observed["events_with_alternative_active_CRSP_PERMNO_same_company"] == 0
    assert observed["events_with_blank_original_names_shareclass"] == 135
    assert (
        observed["events_with_both_prior_Q4_filing_date_anchor_and_10K_cover_symbol"]
        + observed["events_with_only_10K_cover_symbol_no_prior_Q4_anchor"]
        + observed["events_with_only_prior_Q4_filing_date_anchor_no_10K_cover_symbol"]
        + observed["events_with_neither_prior_Q4_anchor_nor_direct_10K_cover_symbol"]
    ) == 135
    assert observed["original_10k_trading_symbol_fact_events"] == 3
    assert observed["original_10k_exact_date_symbol_candidate_matches"] == 3
    assert observed["original_10k_single_clean_nonhidden_symbol_candidate_matches"] == 1
    assert observed["original_10k_multiple_distinct_symbols"] == 1
    assert observed["original_10k_hidden_symbol_facts"] == 1
    assert not result["model_ready"] and not result["final_period_opened"]
    assert result["primary_empirical_milestones_completed"] == []
    assert not result["historical_security_link_effective_interval_approved"]
    assert not result["historical_known_at_established"]
    output = prepared["output"]
    assert output.stat().st_mode & 0o077 == 0
    receipt = json.loads((output / "receipt.json").read_text())
    for fn, values in receipt["files"].items():
        path = output / fn
        assert values["sha256"] == _sha(path)
        assert values["bytes"] == path.stat().st_size
        assert path.stat().st_mode & 0o222 == 0
    queue = [json.loads(v) for v in (output / "review_queue_private.jsonl").read_text().splitlines()]
    html = (output / "private_review.html").read_text()
    assert "Historical Identity Review Queue" in html
    assert "read-only" in html
    assert "Source evidence only" in html
    assert "<script" not in html.lower()
    assert len(queue) == 135
    assert len({row["observation_id"] for row in queue}) == 135
    assert all(row["historical_known_at"] is None and row["market_available_at"] is None
               and not row["historical_CIK_to_PERMNO_approved"] for row in queue)
    assert all("HISTORICAL_CIK_TO_SECURITY_KNOWN_AT_UNKNOWN" in row["review_flags"]
               for row in queue)
    public = (output / "public_summary.json").read_text()
    for forbidden in ("original_SEC_CIK", "candidate_CRSP_PERMNO", "original_CCM_GVKEY",
                      "observed_names_CUSIP8_raw"):
        assert forbidden not in public


def test_unreviewed_vendor_ccm_end_marker_is_not_inferred_finite(prepared):
    result = execute(prepared)
    assert result["counts"]["open_ended_CCM_links"] == 135
    assert result["source_version_and_historical_revisions_approved"] is False


def test_duplicate_output_refused(prepared):
    execute(prepared)
    with pytest.raises(ValueError, match="new private"):
        execute(prepared)


def test_tampered_m5_parquet_source_is_refused(prepared):
    p = prepared["market"] / "candidate_calculations.parquet"
    p.write_bytes(p.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="M5 candidate table"):
        execute(prepared)


def test_tampered_names_csv_is_refused(prepared):
    prepared["names"].write_text(prepared["names"].read_text() + "\n")
    with pytest.raises(ValueError, match="Source Names CSV"):
        execute(prepared)


def test_tampered_ccm_is_refused(prepared):
    p = prepared["ccm"][0]
    p.write_text(p.read_text() + "\n")
    with pytest.raises(ValueError, match="CCM source SHA"):
        execute(prepared)


def test_modified_10k_private_symbol_rows_are_refused(prepared):
    p = prepared["tenk"] / "private_filing_symbol_contexts.jsonl"
    p.chmod(0o600)
    p.write_text(p.read_text() + "\n")
    with pytest.raises(ValueError, match="Private evidence SHA-256"):
        execute(prepared)


def test_modified_2019q4_anchor_receipt_refused(prepared):
    p = prepared["anchor"] / "receipt.json"
    p.chmod(0o600)
    data = json.loads(p.read_text())
    data["security_links_approved"] = 1
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Private evidence restriction"):
        execute(prepared)


def test_holdout_event_blocked_despite_rehashing_m5_source(prepared):
    p = prepared["market"] / "candidate_calculations.parquet"
    frame = pd.read_parquet(p)
    frame.loc[0, "acceptance_timestamp"] = "2025-09-01T13:00:00-04:00"
    frame.to_parquet(p, index=False)
    receipt = prepared["market"] / "audit_summary.json"
    payload = json.loads(receipt.read_text())
    payload["files"]["candidate_calculations.parquet"] = _sha(p)
    receipt.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Holdout or outside-year filing"):
        execute(prepared)


def test_issuer_pair_collision_refused(prepared):
    p = prepared["market"] / "candidate_calculations.parquet"
    frame = pd.read_parquet(p)
    frame.loc[frame["cik"].eq(frame.iloc[0].cik), "candidate_permno"] = frame.iloc[1].candidate_permno
    frame.to_parquet(p, index=False)
    receipt = prepared["market"] / "audit_summary.json"
    payload = json.loads(receipt.read_text())
    payload["files"]["candidate_calculations.parquet"] = _sha(p)
    receipt.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="candidate PERMNO per CIK"):
        execute(prepared)


def _name(start, end, *, ordinal, permco="1", cusip="12345678", symbol="ABC"):
    return {
        "_source_record": ordinal, "secinfostartdt": start, "secinfoenddt": end,
        "securitybegdt": "2015-01-01", "securityenddt": "2025-12-31",
        "permco": permco, "cusip": cusip, "tradingsymbol": symbol,
    }


def test_interval_changing_descriptors_without_cusip_churn_is_visible():
    records = [
        _name("2017-01-01", "2017-01-02", ordinal=1),
        _name("2017-01-03", "2017-01-05", ordinal=2),
    ]
    out = _inspect_window_names(records,
                                ["2017-01-02", "2017-01-03", "2017-01-04"],
                                "1")
    assert out["source_records"] == [1, 2]
    assert out["cusip8_raw"] == ["12345678"]
    assert out["trading_symbols_raw"] == ["ABC"]


def test_missing_descriptor_source_date_is_not_imputed():
    records = [_name("2017-01-01", "2017-01-01", ordinal=1),
               _name("2017-01-03", "2017-01-05", ordinal=2)]
    with pytest.raises(ValueError, match="missing or ambiguous"):
        _inspect_window_names(records, ["2017-01-01", "2017-01-02", "2017-01-03"], "1")


def test_overlapping_descriptor_rejected():
    records = [_name("2017-01-01", "2017-01-03", ordinal=1),
               _name("2017-01-02", "2017-01-05", ordinal=2)]
    with pytest.raises(ValueError, match="missing or ambiguous"):
        _inspect_window_names(records, ["2017-01-01", "2017-01-02", "2017-01-03"], "1")


def test_permco_disagreement_rejected():
    rows = [_name("2017-01-01", "2017-01-03", ordinal=1, permco="NOT_EXPECTED")]
    with pytest.raises(ValueError, match="PERMCO conflict"):
        _inspect_window_names(rows, ["2017-01-01", "2017-01-02"], "1")


def test_cusip_identifier_change_is_preserved():
    records = [_name("2017-01-01", "2017-01-01", ordinal=1),
               _name("2017-01-02", "2017-01-05", ordinal=2, cusip="87654321")]
    result = _inspect_window_names(records, ["2017-01-01", "2017-01-02"], "1")
    assert len(result["cusip8_raw"]) == 2
    assert result["source_records"] == [1, 2]



def test_other_same_company_permanent_security_is_flagged_as_context_not_an_identity():
    source_rows = [
        {"permno": "10", "secinfostartdt": "2010-01-01", "secinfoenddt": "2020-01-01"},
        {"permno": "20", "secinfostartdt": "2011-01-01", "secinfoenddt": "2019-12-31"},
        {"permno": "30", "secinfostartdt": "2019-05-01", "secinfoenddt": "2019-10-01"},
    ]
    assert _same_company_security_context(source_rows, "10", "2019-07-01") == ["20", "30"]
    assert _same_company_security_context(source_rows, "10", "2019-12-31") == ["20"]
    assert _same_company_security_context(source_rows, "10", "2020-01-01") == []



def test_readonly_html_escapes_forged_symbol_markup():
    event = {
        "observation_id": "example-1", "year": 2019,
        "acceptance_timestamp": "2019-06-01T12:00:00-04:00",
        "review_flags": ["<script>alert(1)</script>"],
        "original_SEC_CIK": "0000012345", "candidate_CRSP_PERMNO": "12345",
        "original_CCM_source_file": "sample.csv", "original_CCM_source_record": 5,
        "source_names_record_ordinals": [2],
        "observed_names_CUSIP8_raw": ["<script>attack</script>"],
        "alternative_active_same_PERMCO_security_ids_raw": [],
        "selected_original_names_shareclass_raw": "",
        "selected_original_names_sharetype_raw": "NS",
        "original_10k_symbol_fact_count": 0,
        "2019q4_issuer_anchor_reported_before_10k": False,
    }
    html = _render_private_review([event], {"example-1": {
        "primary_source": {"url": "https://www.sec.gov/Archives/edgar/data/1/source.htm"},
        "header_source": {"url": "https://evil.example/attack"},
    }})
    assert "&lt;script&gt;attack&lt;/script&gt;" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script" not in html.lower()
    assert "evil.example" not in html
    assert "www.sec.gov/Archives/edgar/data/" in html
