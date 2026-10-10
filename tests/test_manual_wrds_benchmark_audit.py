"""Invented-source tests only; no licensed data or remote services are accessed."""

import csv
import gzip
import hashlib
import io
import json
import runpy
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from disclosure_research import manual_wrds_benchmark_audit as audit
from disclosure_research import manual_wrds_stage as source_stage
from disclosure_research.manual_wrds_intake import DAILY_FIELDS
from disclosure_research.protocol import canonical_hash, load_protocol, write_lock


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "configs").mkdir()
    config = load_protocol()
    write_lock(config, tmp_path / "configs/protocol.lock.json")
    (tmp_path / "configs/protocol.json").write_text(json.dumps(config))
    return tmp_path


def _daily(day="2020-01-02", value="0.012341", **changes):
    row = dict(zip(DAILY_FIELDS, (
        "INVENTED-SECURITY-SECRET", "201", "PRIVATE-CUSIP", "PRIVATE-TICKER", day,
        "20", "100", "TR", "STOCK-RETURN-SECRET", "NA", "N", "1000", value,
    ), strict=True))
    row.update(changes)
    return row


def _inventory(repo, name, rows, role="daily", *, compressed=False):
    header = list(DAILY_FIELDS if role == "daily" else ("dlycaldt", "vwretd"))
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(header)
    writer.writerows([[row[field] for field in header] for row in rows])
    raw = text.getvalue().encode()
    if compressed:
        raw = gzip.compress(raw, mtime=0)
    directory = repo / "data" / name
    directory.mkdir(parents=True)
    (directory / "source.bin").write_bytes(raw)
    days = sorted({row["dlycaldt"] for row in rows})
    receipt = {
        "schema_version": 1,
        "status": ("RAW_MANUAL_WRDS_INVENTORY_NOT_AUDIT_APPROVED" if role == "daily"
                   else "RAW_MANUAL_WRDS_MARKET_INVENTORY_NOT_SOURCE_APPROVED"),
        "protocol_sha256": canonical_hash(load_protocol()),
        "source": {"preserved_file": "source.bin", "sha256": hashlib.sha256(raw).hexdigest(),
                   "bytes": len(raw), "observed_header": header},
        "request": {"start": "2020-01-02", "end": "2020-01-03"},
        "actual_coverage": {"first_date": days[0], "last_date": days[-1], "distinct_dates": len(days)},
        "all_rows": {"rows": len(rows)}, "model_ready": False,
    }
    (directory / "receipt.json").write_text(json.dumps(receipt))
    return directory


def _stage(repo, daily_groups=None, market_rows=None, *, compressed=False):
    groups = daily_groups or [[_daily(), _daily("2020-01-03", "0.020000")]]
    paths = [_inventory(repo, f"daily-{i}", rows) for i, rows in enumerate(groups)]
    market_rows = market_rows or [{"dlycaldt": "2020-01-02", "vwretd": "0.012340"},
                                  {"dlycaldt": "2020-01-03", "vwretd": "0.020000"}]
    independent = _inventory(repo, "market", market_rows, "market", compressed=compressed)
    directory = repo / "data/stage"
    receipt = source_stage.stage_manual_development(
        paths, independent, request_start="2020-01-02", request_end="2020-01-03",
        output=directory, config=load_protocol(), repo_root=repo)
    return directory, receipt


def _run(repo, directory):
    return audit.audit_benchmark(directory, output=repo / "data/audit", config=load_protocol(), repo_root=repo)


def _save_receipt(directory, manifest):
    path = directory / "receipt.json"
    path.chmod(0o600)
    path.write_text(json.dumps(manifest))


def _change_part(directory, manifest, change, index=0):
    spec = manifest["projection"]["parts"][index]
    path = directory / spec["file"]
    table = pq.read_table(path)
    rows = table.to_pylist()
    change(rows)
    path.chmod(0o600)
    schema = pa.schema([field.with_nullable(True) if any(row[field.name] is None for row in rows)
                        else field for field in table.schema])
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)
    spec.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
    _save_receipt(directory, manifest)


def _change_market(directory, manifest, rows):
    item = next(item for item in manifest["sources"] if item["role"] == "market")
    inventory = Path(item["inventory_directory"])
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(["dlycaldt", "vwretd"])
    writer.writerows(rows)
    raw = text.getvalue().encode()
    (inventory / "source.bin").write_bytes(raw)
    receipt = json.loads((inventory / "receipt.json").read_text())
    receipt["source"].update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    receipt["all_rows"]["rows"] = len(rows)
    days = sorted({day for day, _ in rows})
    actual = {"first_date": days[0], "last_date": days[-1], "distinct_dates": len(days)}
    receipt["actual_coverage"] = actual
    receipt_raw = json.dumps(receipt).encode()
    (inventory / "receipt.json").write_bytes(receipt_raw)
    snapshot = directory / item["inventory_receipt_file"]
    snapshot.chmod(0o600)
    snapshot.write_bytes(receipt_raw)
    item.update(source_sha256=receipt["source"]["sha256"], source_bytes=len(raw), rows=len(rows),
                requested_rows=sum("2020-01-02" <= day <= "2020-01-03" for day, _ in rows),
                inventory_receipt_sha256=hashlib.sha256(receipt_raw).hexdigest())
    item["actual_coverage"].update(actual)
    _save_receipt(directory, manifest)


@pytest.mark.parametrize("compressed", [False, True])
def test_exact_private_report_counts_provenance_rounding_and_original_preservation(repo, monkeypatch, compressed):
    monkeypatch.setattr(source_stage, "_BATCH_ROWS", 2)
    monkeypatch.setattr(audit, "_BATCH", 1)
    directory, stage_receipt = _stage(repo, [[_daily(), _daily(),
                                             _daily("2020-01-03", "0.020000"),
                                             _daily("2007-01-03", "UNINTERPRETED-EARLY-SECRET")]],
                                      compressed=compressed)
    inputs = {path: path.read_bytes() for path in (repo / "data").rglob("*") if path.is_file()}
    receipt = _run(repo, directory)
    counts = receipt["counts"]
    assert counts["compared_daily_rows"] == 3
    assert counts["numeric_mismatch_rows"] == 2
    assert counts["mismatch_dates"] == counts["mismatching_date_source_pairs"] == 1
    assert counts["numeric_equal_rows"] == counts["exact_text_equal_rows"] == 1
    assert counts["positive_difference_dates"] == 1
    assert counts["negative_difference_dates"] == 0
    assert receipt["exact_difference"]["minimum_absolute"] == "0.000001"
    assert receipt["exact_difference"]["maximum_absolute"] == "0.000001"
    assert receipt["mismatches_by_year"]["2020"]["daily_rows_affected"] == 2
    source = stage_receipt["sources"][0]["source_sha256"]
    assert receipt["mismatches_by_source_sha256"][source]["mismatch_dates"] == 1
    assert receipt["rounding_diagnostics"]["decimal_places"]["4"]["equal_mismatch_dates"] == 1
    assert receipt["rounding_diagnostics"]["decimal_places"]["5"]["equal_affected_daily_rows"] == 2
    assert receipt["rounding_diagnostics"]["decimal_places"]["6"]["equal_mismatch_dates"] == 0
    assert receipt["rounding_diagnostics"]["acceptance_rule"] is False
    assert receipt["reconciliation"]["requested_window_numerically_reconciled"] is False
    assert receipt["coverage"]["daily_projection"]["outside_request_rows_retained_in_source_stage"] == 1
    output = repo / "data/audit"
    table = pq.read_table(output / "mismatches.parquet")
    assert table.schema == audit.MISMATCH_SCHEMA
    row = table.to_pylist()[0]
    assert row["daily_raw_text"] == "0.012341" and row["market_raw_text"] == "0.012340"
    assert row["daily_minus_independent_exact"] == "0.000001"
    assert row["daily_rows_affected"] == 2 and row["market_source_csv_record"] == 2
    assert row["daily_inventory_receipt_sha256"] == stage_receipt["sources"][0]["inventory_receipt_sha256"]
    assert row["market_source_sha256"] == stage_receipt["sources"][-1]["source_sha256"]
    assert row["daily_decimal_quantum_exponent"] == row["market_decimal_quantum_exponent"] == -6
    assert row["equal_at_5_decimal_places"] is True
    assert row["equal_at_coarser_source_quantum"] is False
    assert receipt["table"]["sha256"] == hashlib.sha256((output / "mismatches.parquet").read_bytes()).hexdigest()
    assert (output / "source_stage_receipt.json").read_bytes() == inputs[directory / "receipt.json"]
    assert all(path.read_bytes() == original for path, original in inputs.items())
    assert all(path.stat().st_mode & 0o777 == 0o400 for path in output.rglob("*") if path.is_file())
    assert output.stat().st_mode & 0o777 == 0o700
    assert receipt["processing"]["binary_float_intermediates_used"] is False
    assert receipt["model_ready"] is False and receipt["source_approvals"] == 0
    assert receipt["final_period_opened"] is False and receipt["values_replaced"] == 0
    assert json.loads((output / "receipt.json").read_text()) == receipt
    assert not list(output.parent.glob(".wrds-benchmark-audit-*"))
    public = json.dumps(audit.aggregate_summary(receipt))
    assert all(secret not in public for secret in (
        "0.012341", "0.012340", "2020-01-02", "INVENTED-SECURITY", "PRIVATE-CUSIP",
        "PRIVATE-TICKER", "STOCK-RETURN-SECRET", "UNINTERPRETED-EARLY", str(repo)))
    with pytest.raises(ValueError, match="exists"):
        _run(repo, directory)


def test_exact_decimal_nonfloat_difference_and_text_only_variants(repo):
    value = "0.1000000000000000000000000000001"
    assert float(value) == float("0.1")
    directory, _ = _stage(repo, [[_daily(value=value), _daily("2020-01-03", "0.0200")],
                                [_daily("2020-01-03", "2e-2", permno="SECOND-PRIVATE")]],
                           [{"dlycaldt": "2020-01-02", "vwretd": "0.1"},
                            {"dlycaldt": "2020-01-03", "vwretd": "0.02"}])
    receipt = _run(repo, directory)
    counts = receipt["counts"]
    assert counts["numeric_mismatch_rows"] == 1
    assert counts["numeric_equal_text_different_rows"] == 2
    assert counts["daily_dates_with_distinct_raw_texts"] == 1
    assert receipt["exact_difference"]["minimum_absolute"] == "1E-31"
    assert receipt["rounding_diagnostics"]["decimal_places"]["12"]["equal_mismatch_dates"] == 1
    row = pq.read_table(repo / "data/audit/mismatches.parquet").to_pylist()[0]
    assert row["daily_minus_independent_exact"] == "1E-31"
    assert row["equal_at_coarser_source_quantum"] is True
    assert receipt["reconciliation"]["exact_observed_benchmark_values_equal"] is False


def test_mismatch_dates_count_once_across_sources_and_raw_spelling_groups(repo):
    directory, stage_receipt = _stage(repo, [[_daily(), _daily(value="1.2341e-2")],
                                            [_daily(permno="SECOND-PRIVATE"),
                                             _daily("2020-01-03", "0.019999")]])
    receipt = _run(repo, directory)
    assert receipt["counts"]["mismatch_dates"] == 2
    assert receipt["counts"]["mismatching_date_source_pairs"] == 3
    assert receipt["counts"]["mismatching_raw_text_groups"] == 4
    assert receipt["counts"]["numeric_mismatch_rows"] == 4
    assert receipt["counts"]["positive_difference_dates"] == receipt["counts"]["negative_difference_dates"] == 1
    assert receipt["rounding_diagnostics"]["decimal_places"]["5"]["equal_mismatch_dates"] == 2
    source = stage_receipt["sources"][1]["source_sha256"]
    assert receipt["mismatches_by_source_sha256"][source]["mismatch_dates"] == 2


@pytest.mark.parametrize("across_sources", [False, True])
def test_numeric_source_conflict_is_rejected_and_no_bundle_is_published(repo, across_sources):
    rows = [_daily(), _daily(value="0.012342")]
    groups = [[row] for row in rows] if across_sources else [rows]
    directory, _ = _stage(repo, groups)
    with pytest.raises(ValueError, match="conflicting numeric"):
        _run(repo, directory)
    assert not (repo / "data/audit").exists()


@pytest.mark.parametrize("kind", ["future", "malformed", "provenance", "duplicate_record", "null_date"])
def test_complete_projection_date_and_provenance_preflight_precedes_any_decimal(repo, monkeypatch, kind):
    directory, manifest = _stage(repo)
    changes = {
        "future": lambda rows: rows[-1].update(dlycaldt="2022-02-03", in_requested_window=False),
        "malformed": lambda rows: rows[-1].update(dlycaldt="2020-1-03"),
        "provenance": lambda rows: rows[-1].update(source_inventory_sha256="c" * 64),
        "duplicate_record": lambda rows: rows[-1].update(source_csv_record=2),
        "null_date": lambda rows: rows[-1].update(dlycaldt=None),
    }
    _change_part(directory, manifest, changes[kind])
    def forbidden(_):
        pytest.fail("Numeric interpretation happened before complete source preflight")
    monkeypatch.setattr(audit, "_number", forbidden)
    with pytest.raises(ValueError):
        _run(repo, directory)
    assert not (repo / "data/audit").exists()


@pytest.mark.parametrize("rows", [
    [("2020-01-02", "PRIVATE-BAD-NUMBER"), ("2022-02-03", "PRIVATE-BAD-NUMBER")],
    [("2020-01-02", "PRIVATE-BAD-NUMBER"), ("2020-1-03", "PRIVATE-BAD-NUMBER")],
    [("2020-01-02", "PRIVATE-BAD-NUMBER"), ("2020-01-02", "PRIVATE-BAD-NUMBER")],
    [("2020-01-02", "PRIVATE-BAD-NUMBER")],
])
def test_market_all_date_duplicate_and_missing_checks_precede_any_decimal(repo, monkeypatch, rows):
    directory, manifest = _stage(repo)
    _change_market(directory, manifest, rows)
    def forbidden(_):
        pytest.fail("Numeric interpretation happened before complete independent-market date preflight")
    monkeypatch.setattr(audit, "_number", forbidden)
    with pytest.raises(ValueError):
        _run(repo, directory)


@pytest.mark.parametrize("value", ["", "NaN", "Infinity", "PRIVATE-BAD-NUMBER", "1_000", "1e-1001",
                                    "0e1000000000", "1" * 257, "-1.000000000000000000000000001"])
def test_invalid_or_unbounded_daily_decimal_is_refused(repo, value):
    directory, _ = _stage(repo, [[_daily(value=value)]])
    with pytest.raises(ValueError):
        _run(repo, directory)
    assert not (repo / "data/audit").exists()


@pytest.mark.parametrize("value", ["", "NaN", "1e-1001", "-1.000000000000000000000000001"])
def test_bound_market_values_are_revalidated_after_date_preflight(repo, value):
    directory, manifest = _stage(repo)
    _change_market(directory, manifest, [("2020-01-02", value), ("2020-01-03", "0.02")])
    with pytest.raises(ValueError):
        _run(repo, directory)


@pytest.mark.parametrize("target", ["part", "inventory_snapshot", "market_receipt", "market_source"])
def test_actual_hash_and_receipt_binding_tampering_is_rejected(repo, target):
    directory, manifest = _stage(repo)
    market = manifest["sources"][-1]
    path = {
        "part": directory / manifest["projection"]["parts"][0]["file"],
        "inventory_snapshot": directory / manifest["sources"][0]["inventory_receipt_file"],
        "market_receipt": Path(market["inventory_directory"]) / "receipt.json",
        "market_source": Path(market["inventory_directory"]) / market["preserved_file"],
    }[target]
    path.chmod(0o600)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        _run(repo, directory)
    assert not (repo / "data/audit").exists()


def test_market_relative_path_escape_and_symlink_are_rejected(repo):
    directory, manifest = _stage(repo)
    item = manifest["sources"][-1]
    inventory = Path(item["inventory_directory"])
    source = inventory / "source.bin"
    other = repo / "data/other.bin"
    source.rename(other)
    source.symlink_to(other)
    with pytest.raises(ValueError, match="symbolic"):
        _run(repo, directory)
    source.unlink()
    other.rename(source)
    receipt = json.loads((inventory / "receipt.json").read_text())
    receipt["source"]["preserved_file"] = "../market/source.bin"
    raw = json.dumps(receipt).encode()
    (inventory / "receipt.json").write_bytes(raw)
    snapshot = directory / item["inventory_receipt_file"]
    snapshot.chmod(0o600)
    snapshot.write_bytes(raw)
    item.update(preserved_file="../market/source.bin", inventory_receipt_sha256=hashlib.sha256(raw).hexdigest())
    _save_receipt(directory, manifest)
    with pytest.raises(ValueError, match="safe relative"):
        _run(repo, directory)


def test_final_guard_detects_source_mutation_during_comparison(repo, monkeypatch):
    directory, manifest = _stage(repo)
    market_source = Path(manifest["sources"][-1]["inventory_directory"]) / "source.bin"
    original = audit._compare
    def mutate(*args):
        result = original(*args)
        market_source.write_bytes(market_source.read_bytes() + b"\n")
        return result
    monkeypatch.setattr(audit, "_compare", mutate)
    with pytest.raises(ValueError, match="changed"):
        _run(repo, directory)
    assert not (repo / "data/audit").exists()


def test_final_part_rehash_is_performed_in_addition_to_identity_guards(repo, monkeypatch):
    directory, manifest = _stage(repo)
    part = directory / manifest["projection"]["parts"][0]["file"]
    original = audit._hash
    monkeypatch.setattr(audit, "_hash", lambda path: "0" * 64 if path == part else original(path))
    with pytest.raises(ValueError, match="bound input hash"):
        _run(repo, directory)


def test_equal_values_with_session_gap_do_not_reconcile_whole_requested_window(repo):
    directory, _ = _stage(repo, [[_daily(value="0.012340")]])
    receipt = _run(repo, directory)
    assert receipt["counts"]["numeric_mismatch_rows"] == 0
    assert receipt["table"]["rows"] == 0
    assert receipt["exact_difference"]["maximum_absolute"] is None
    assert receipt["reconciliation"]["exact_observed_benchmark_values_equal"] is True
    assert receipt["reconciliation"]["requested_window_numerically_reconciled"] is False
    assert receipt["model_ready"] is False
    assert pq.read_table(repo / "data/audit/mismatches.parquet").num_rows == 0


def test_cli_emits_aggregate_only_success_and_sanitized_failure(repo, monkeypatch, capsys):
    script = Path(__file__).parents[1] / "scripts/wrds_manual_benchmark_audit.py"
    main = runpy.run_path(str(script))["main"]
    directory, _ = _stage(repo)
    monkeypatch.chdir(repo)
    args = ["--stage", str(directory), "--output", str(repo / "data/audit")]
    assert main(args) == 0
    public = capsys.readouterr().out
    assert json.loads(public)["counts"]["numeric_mismatch_rows"] == 1
    assert all(secret not in public for secret in ("0.012341", "0.012340", "PRIVATE-TICKER", str(repo)))
    def failure(*_, **__):
        raise ValueError("PRIVATE-RAW-RETURN-AND-SECURITY")
    monkeypatch.setitem(main.__globals__, "audit_benchmark", failure)
    assert main(args) == 1
    failed = capsys.readouterr().out
    assert "PRIVATE-RAW" not in failed
    assert json.loads(failed)["error_type"] == "ValueError"


def test_reject_public_or_nested_preserved_output(repo):
    directory, _ = _stage(repo)
    for output in (repo / "public/audit", directory / "diagnostic", repo / "data/market/audit"):
        with pytest.raises(ValueError):
            audit.audit_benchmark(directory, output=output, config=load_protocol(), repo_root=repo)
