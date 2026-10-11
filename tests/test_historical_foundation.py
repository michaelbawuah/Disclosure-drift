"""Synthetic source integrations and concrete reconciliation failure cases."""

import gzip
import hashlib
import json
import runpy
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from disclosure_research import historical_foundation as foundation
from disclosure_research import manual_wrds_identity_candidates as identity
from disclosure_research import manual_wrds_liquidity_candidates as liquidity
from disclosure_research.protocol import load_protocol, write_lock

# Reuse the synthetic source generators; production inputs are never opened.
from test_manual_wrds_identity_candidates import _ccm, _inputs, _name
from test_manual_wrds_liquidity_candidates import _daily, _numerical, _window
from test_sec_identity_evidence import _build as _sec_build
from test_sec_identity_evidence import _html
from test_sec_identity_evidence import _inputs as _sec_inputs


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def make_inputs(tmp_path):
    def make(*, names=None, ccm=None, daily=None):
        (tmp_path / "configs").mkdir(exist_ok=True)
        write_lock(load_protocol(), tmp_path / "configs/protocol.lock.json")
        (tmp_path / "configs/protocol.json").write_text(json.dumps(load_protocol()))
        sec_inputs = _sec_inputs(tmp_path, changes={
            "risk_source_url": "https://www.sec.gov/Archives/edgar/data/123/example.htm",
            "risk_source_sha256": hashlib.sha256(_html()).hexdigest()})
        report = _sec_build(sec_inputs)
        report_path = tmp_path / "sec.json.gz"
        report_path.write_bytes(gzip.compress(json.dumps(report).encode(), mtime=0))
        sources = _inputs(tmp_path, names=names, ccm=ccm)
        ident = tmp_path / "data/identity"
        identity.build_identity_candidates(*sources, output=ident, config=load_protocol(), repo_root=tmp_path,
                                           sec_manifest=sec_inputs["manifest"])
        daily = daily if daily is not None else [_daily(day) for day in _window()["sessions"][:40]]
        numeric = _numerical(tmp_path, daily)
        liq = tmp_path / "data/liquidity"
        liquidity.build_liquidity_candidates(numeric, sources[1], output=liq, config=load_protocol(), repo_root=tmp_path)
        return {"identity_directory": ident, "liquidity_directory": liq,
                "identity_receipt_sha256": _sha(ident / "receipt.json"),
                "liquidity_receipt_sha256": _sha(liq / "receipt.json"), "sec_evidence_path": report_path,
                "sec_evidence_sha256": _sha(report_path), "sec_manifest_path": sec_inputs["manifest"],
                "sec_manifest_sha256": sec_inputs["manifest_sha256"], "output": tmp_path / "data/foundation",
                "config": load_protocol(), "repo_root": tmp_path}
    return make


def _table(args, receipt, name):
    return [row for part in receipt["tables"][name]["parts"]
            for row in pq.read_table(args["output"] / part["file"]).to_pylist()]


def _mutate_part(args, table_name, update, *, role="identity", rebind=True):
    directory = args[role + "_directory"]
    receipt = json.loads((directory / "receipt.json").read_text())
    table = receipt["tables"][table_name] if role == "identity" else receipt[table_name]
    part = table["parts"][0]
    path = directory / part["file"]
    original = pq.read_table(path)
    rows = original.to_pylist()
    update(rows)
    path.chmod(0o600)
    pq.write_table(pa.Table.from_pylist(rows, schema=original.schema), path)
    if rebind:
        part.update(sha256=_sha(path), bytes=path.stat().st_size, rows=len(rows))
        receipt_path = directory / "receipt.json"
        receipt_path.chmod(0o600)
        receipt_path.write_text(json.dumps(receipt))
        args[role + "_receipt_sha256"] = _sha(receipt_path)


def test_actual_upstream_join_source_bindings_and_private_outputs(make_inputs):
    daily = [_daily(day, security=security) for security in ("10", "20") for day in _window()["sessions"][:40]]
    args = make_inputs(names=[_name("10"), _name("30")], ccm=[_ccm("10"), _ccm("30", cik="")], daily=daily)
    receipt = foundation.build_historical_foundation_review(**args)
    assert receipt["counts"] == {"annual_union_rows": 3, "identity_rows": 2, "liquidity_rows": 3,
                                 "liquidity_only_rows": 1, "identity_only_rows": 0, "numeric_minimum_rows": 2,
                                 "ordinary_numeric_candidate_rows": 1, "rank_eligible_rows": 1,
                                 "annual_rows_with_original_sec_discovery": 1}
    assert sum(row["rows"] for row in receipt["cross_tabulation"]) == 3
    assert receipt["source_relationship_rows_verified"] == 2
    rows = {row["security_id"]: row for row in _table(args, receipt, "annual_foundation")}
    assert rows["20"]["identity_evidence_status"] == "NO_ANNUAL_NAMES_IDENTITY_EVIDENCE"
    assert rows["30"]["identity_evidence_status"] == "SINGLE_CANDIDATE_HEADER_CIK_MISSING_OR_UNSUPPORTED"
    assert rows["10"]["source_bound_discoveries"] == 1
    assert [row["security_id"] for row in _table(args, receipt, "liquidity_only_coverage")] == ["20"]
    found = _table(args, receipt, "filing_candidate_corroboration")
    assert len(found) == 1 and found[0]["names_permno_raw"] == "10"
    assert json.loads(found[0]["class_observations_json"])
    assert found[0]["primary_source_sha256"] == json.loads(gzip.decompress(args["sec_evidence_path"].read_bytes()))["records"][0]["primary_source"]["sha256"]
    for name in receipt["tables"]:
        for row in _table(args, receipt, name):
            assert row["known_at"] is None and row["available_at"] is None and row["identity_approved"] is False
    for path in args["output"].rglob("*"):
        assert path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o400)
    assert receipt["market_returns_read"] is False and receipt["original_sec_bytes_reread"] is False
    assert receipt["liquidity_mean_or_rank_values_read"] is False
    assert "candidate_security_rank" not in receipt["liquidity_columns_read"]
    assert "mean_closing_price_volume_usd_candidate" not in receipt["liquidity_columns_read"]
    with pytest.raises(ValueError, match="exists"):
        foundation.build_historical_foundation_review(**args)


def test_raw_identifier_aliases_remain_distinct_and_multiple_ccm_occurrences_remain(make_inputs):
    args = make_inputs(names=[_name("10"), _name("0010")], ccm=[_ccm("10"), _ccm("0010", gvkey="005678", linkenddt="E")])
    receipt = foundation.build_historical_foundation_review(**args)
    rows = _table(args, receipt, "annual_foundation")
    assert {row["security_id"] for row in rows} == {"10", "0010"}
    assert all(row["identity_evidence_status"] == "MULTIPLE_OR_AMBIGUOUS_CANDIDATE_EVIDENCE" for row in rows)
    assert receipt["source_relationship_rows_verified"] == 4
    assert receipt["tables"]["filing_candidate_corroboration"]["rows"] == 4
    assert rows[0]["known_at"] is None


def test_empty_discovery_and_names_snapshot_parts_preserve_filing_and_daily_coverage(make_inputs):
    args = make_inputs(names=[_name(secinfostartdt="2021-06-01", secinfoenddt="2021-06-30")], ccm=[_ccm("999", cik="")])
    receipt = foundation.build_historical_foundation_review(**args)
    assert receipt["counts"]["identity_rows"] == 0
    assert receipt["counts"]["liquidity_only_rows"] == 1
    assert receipt["tables"]["filing_candidate_corroboration"]["rows"] == 0
    assert receipt["tables"]["filing_candidate_corroboration"]["parts"][0]["rows"] == 0
    assert len(_table(args, receipt, "filing_coverage")) == 1
    assert receipt["sec_manifest_coverage_counts"] == {"NO_SAME_YEAR_HEADER_CIK_CANDIDATE_DISCOVERY": 1}


def test_january_descriptor_is_not_stretched_to_filing_date(make_inputs):
    args = make_inputs(names=[_name(secinfoenddt="2021-01-31")])
    receipt = foundation.build_historical_foundation_review(**args)
    discovery = _table(args, receipt, "filing_candidate_corroboration")[0]
    assert discovery["names_secinfo_covers_acceptance"] is False
    row = _table(args, receipt, "annual_foundation")[0]
    assert "SAME_YEAR_SEC_OBSERVATION_AFTER_INFORMATION_CUTOFF" in json.loads(row["evidence_gaps_json"])
    assert row["known_at"] is None


@pytest.mark.parametrize("table,field,value", [
    ("relationships", "names_permno_raw", "999"),
    ("relationships", "candidate_search", False),
    ("annual_evidence", "candidate_ccm_records", 8),
    ("sec_discovery", "recorded_acceptance_date", "2021-02-14"),
    ("sec_discovery", "names_source_csv_record", 99),
    ("sec_manifest_coverage", "distinct_ccm_records", 9),
    ("ccm_records", "known_at", "2010-01-01T00:00:00Z"),
])
def test_rebound_bad_source_or_count_declarations_fail_closed(make_inputs, table, field, value):
    args = make_inputs()
    _mutate_part(args, table, lambda rows: rows[0].update({field: value}))
    with pytest.raises(ValueError):
        foundation.build_historical_foundation_review(**args)
    assert not args["output"].exists()


def test_tampered_part_and_stale_report_pins_fail(make_inputs):
    args = make_inputs()
    args["sec_evidence_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="report input hash"):
        foundation.build_historical_foundation_review(**args)
    args["sec_evidence_sha256"] = _sha(args["sec_evidence_path"])
    _mutate_part(args, "annual_evidence", lambda rows: rows[0].update(candidate_ccm_records=8), rebind=False)
    with pytest.raises(ValueError, match="byte binding"):
        foundation.build_historical_foundation_review(**args)


def test_final_period_manifest_rejected_before_vendor_bundle_access(make_inputs, monkeypatch):
    args = make_inputs()
    path = args["sec_manifest_path"]
    text = path.read_text().replace("2021-02-15", "2022-02-15")
    path.write_text(text)
    args["sec_manifest_sha256"] = _sha(path)
    monkeypatch.setattr(foundation, "_bundle", lambda *a, **k: pytest.fail("Vendor bundle opened before final-period rejection"))
    with pytest.raises(ValueError, match="development filings only"):
        foundation.build_historical_foundation_review(**args)


def test_source_report_record_must_match_manifest_even_with_new_pin(make_inputs):
    args = make_inputs()
    report = json.loads(gzip.decompress(args["sec_evidence_path"].read_bytes()))
    report["records"][0]["primary_source"]["sha256"] = "a" * 64
    args["sec_evidence_path"].write_bytes(gzip.compress(json.dumps(report).encode(), mtime=0))
    args["sec_evidence_sha256"] = _sha(args["sec_evidence_path"])
    with pytest.raises(ValueError, match="source declarations"):
        foundation.build_historical_foundation_review(**args)


def test_stored_eligibility_flag_cannot_override_bound_metadata(make_inputs):
    args = make_inputs()
    _mutate_part(args, "annual_liquidity", lambda rows: rows[0].update(rank_eligible_by_candidate_policy=False), role="liquidity")
    with pytest.raises(ValueError, match="rank eligibility"):
        foundation.build_historical_foundation_review(**args)


def test_cli_error_is_aggregate_only(make_inputs, monkeypatch, capsys):
    args = make_inputs()
    monkeypatch.chdir(args["repo_root"])
    script = Path(__file__).resolve().parents[1] / "scripts/build_historical_foundation.py"
    main = runpy.run_path(str(script))["main"]
    argv = ["--identity", str(args["identity_directory"]), "--identity-receipt-sha256", "0" * 64,
            "--liquidity", str(args["liquidity_directory"]), "--liquidity-receipt-sha256", args["liquidity_receipt_sha256"],
            "--sec-evidence", str(args["sec_evidence_path"]), "--sec-evidence-sha256", args["sec_evidence_sha256"],
            "--sec-manifest", str(args["sec_manifest_path"]), "--sec-manifest-sha256", args["sec_manifest_sha256"],
            "--output", str(args["output"])]
    assert main(argv) == 1
    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "HISTORICAL_FOUNDATION_FAILED"
    assert "PRIVATE" not in output and str(args["repo_root"]) not in output
