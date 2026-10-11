"""Small invented source bundles only; never licensed data or remote services."""

import csv
import hashlib
import json
import runpy
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from disclosure_research import manual_wrds_benchmark_audit as audit
from disclosure_research import manual_wrds_benchmark_source_evidence as evidence
from disclosure_research.manual_wrds_intake import DAILY_FIELDS, inventory_daily
from disclosure_research.manual_wrds_market import inventory_market
from disclosure_research.manual_wrds_stage import stage_manual_development
from disclosure_research.protocol import load_protocol, write_lock


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "configs").mkdir()
    config = load_protocol()
    write_lock(config, tmp_path / "configs/protocol.lock.json")
    (tmp_path / "configs/protocol.json").write_text(json.dumps(config))
    return tmp_path


def _save(path, value):
    if path.exists():
        path.chmod(0o600)
    path.write_text(json.dumps(value))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _daily(day, value, security="PRIVATE-SECURITY"):
    return dict(zip(DAILY_FIELDS, (security, "100", "PRIVATE-CUSIP", "PRIVATE-TICKER", day,
                                   "20", "100", "TR", ".01", "NA", "N", "2000", value), strict=True))


def _csv(path, fields, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _prepared(repo, *, overlap=False, exact=False, high_precision=False, sql=True):
    config = load_protocol()
    days = ("2020-01-02", "2020-01-03", "2020-01-06")
    market_values = ("0.012340", "-0.004320", "0.020000")
    daily_values = market_values if exact else ("0.012341", "-0.004321", "0.020000")
    if high_precision:
        market_values = ("0.123456789012345678901234567890123456", *market_values[1:])
        daily_values = ("0.123456789012345678901234567890123457", *daily_values[1:])
    first = [_daily(day, value) for day, value in zip(days, daily_values, strict=True)]
    second = [_daily(days[-1], market_values[-1], "ANOTHER-PRIVATE-SECURITY")]
    if overlap:
        second.insert(0, _daily(days[0], daily_values[0], "ANOTHER-PRIVATE-SECURITY"))
    inventories = []
    for index, rows in enumerate((first, second)):
        path = repo / f"invented-daily-{index}.csv"
        _csv(path, DAILY_FIELDS, rows)
        output = repo / f"data/daily-{index}"
        inventory_daily(path, request_start=days[0], request_end=days[-1], output=output,
                        config=config, repo_root=repo)
        inventories.append(output)
    path = repo / "invented-market.csv"
    _csv(path, ("dlycaldt", "vwretd"), [{"dlycaldt": day, "vwretd": value}
                                        for day, value in zip(days, market_values, strict=True)])
    sql_path = repo / "invented-query.sql"
    sql_path.write_text("-- PRIVATE SQL COMMENT\nSELECT dlycaldt,vwretd FROM invented.wrds_dailyindexret_query;\n")
    market = repo / "data/market"
    inventory_market(path, request_start=days[0], request_end=days[-1], output=market,
                     config=config, repo_root=repo, sql_source=sql_path if sql else None)
    stage = repo / "data/stage"
    stage_manual_development(inventories, market, request_start=days[0], request_end=days[-1],
                             output=stage, config=config, repo_root=repo)
    directory = repo / "data/audit"
    audit.audit_benchmark(stage, output=directory, config=config, repo_root=repo)
    query = repo / "data/query-evidence"
    query.mkdir()
    image = query / "input-parameters.png"
    image.write_bytes(b"\x89PNG\r\nPRIVATE INVENTED SCREENSHOT BYTES")
    inventory = json.loads((inventories[0] / "receipt.json").read_text())
    source_sha = inventory["source"]["sha256"]
    observation = {
        "schema_version": 1, "query_id": 123, "displayed_result_rows": 3,
        "observed_parameters": {"file": "wrds_dsfv2_query", "library": "PRIVATE-PARAMETER", "method": "3"},
        "local_inventory_comparison": {"source_sha256": source_sha, "inventory_rows": 3, "rows_match_displayed_result": True},
        "requested_date_range_visible": {"start": days[0], "end": days[-1]},
        "displayed_times_timezone": None, "displayed_times_not_converted_to_utc": True,
        "source_release": None, "method_code_semantics_verified": False,
        "source_completeness_verified": False, "all_securities_selection_verified": False,
        "prior_arithmetic_review_modified": False, "model_ready": False, "source_approvals": 0,
        "screenshots": [{"file": image.name, "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                         "bytes": image.stat().st_size, "byte_identical_to_user_attachment": True}],
    }
    observed_sha = _save(query / "observation.json", observation)
    reconciliation = {
        "schema_version": 1, "query_job_id": "123", "displayed_query_rows": 3,
        "inventoried_source_rows": 3, "row_counts_equal": True,
        "inventory_receipt_sha256": hashlib.sha256((inventories[0] / "receipt.json").read_bytes()).hexdigest(),
        "query_observation_sha256": observed_sha, "preserved_source_sha256": source_sha,
        "source_inventory_status": inventory["status"], "association_scope": "displayed row count only; no certified byte binding",
        "model_ready": False, "source_approvals": 0,
    }
    _save(query / "inventory-reconciliation-v1.json", reconciliation)
    return directory, query


def _run(repo, prepared, **options):
    directory, query = prepared
    return evidence.build_source_evidence(directory, **{
        "audit_receipt_sha256": hashlib.sha256((directory / "receipt.json").read_bytes()).hexdigest(),
        "output": repo / "data/packet", "config": load_protocol(), "repo_root": repo,
        "query_evidence": [query], **options})


def _change_table(directory, mutate, *, receipt_change=None):
    receipt = json.loads((directory / "receipt.json").read_text())
    path = directory / receipt["table"]["file"]
    table = pq.read_table(path)
    rows = table.to_pylist()
    mutate(rows)
    path.chmod(0o600)
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), path)
    receipt["table"].update(rows=len(rows), bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    if receipt_change:
        receipt_change(receipt)
    _save(directory / "receipt.json", receipt)


def test_complete_private_packet_reuses_real_small_audit_preserves_all_sources_and_never_opens_raw_inputs(repo, monkeypatch):
    prepared = _prepared(repo)
    directory, query = prepared
    originals = {path: path.read_bytes() for path in [*(directory.rglob("*")), *(query.rglob("*"))] if path.is_file()}
    original_open = Path.open
    forbidden_paths = set((repo / "data").glob("*/source.csv")) | set((repo / "data/stage").rglob("*.parquet"))
    def guarded_open(path, *args, **kwargs):
        assert path not in forbidden_paths, "Packet must never reopen original CSV or source-stage Parquet"
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(evidence, "_BATCH", 1)
    receipt = _run(repo, prepared)
    out = repo / "data/packet"
    assert receipt["audit_counts"]["mismatch_dates"] == 2
    assert len(receipt["mismatches_by_source_sha256"]) == 2
    assert any(row["mismatch_dates"] == 0 for row in receipt["mismatches_by_source_sha256"].values())
    assert (out / "audit/mismatches.parquet").read_bytes() == originals[directory / "mismatches.parquet"]
    assert all(path.read_bytes() == value for path, value in originals.items())
    assert all(path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o400)
               for path in [out, *out.rglob("*")])
    for item in receipt["files"]:
        path = out / item["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
        assert path.stat().st_size == item["bytes"]
    sources = json.loads((out / "source_evidence.json").read_text())
    assert len(sources) == 3 and sum(row["sql_file"] is not None for row in sources) == 1
    assert all(row["vendor_schema_version_evidence"] is None for row in sources)
    assert all(row["vendor_release_or_vintage_evidence"] is None for row in sources)
    observation = next(row["query_observations"][0] for row in sources if row["query_observations"])
    assert observation["query_to_csv_byte_binding_certified"] is False
    assert observation["row_counts_equal"] is True
    assert observation["displayed_times_timezone"] is None
    assert receipt["model_ready"] is False and receipt["source_approvals"] == 0
    assert receipt["reconciliation"]["requested_window_numerically_reconciled"] is False
    assert receipt["vendor_question_sent"] is False
    assert receipt["raw_source_csv_files_opened"] is receipt["source_stage_parquet_opened"] is False
    public = (out / "public_summary.json").read_text() + (out / "vendor_question_draft.md").read_text()
    assert all(secret not in public for secret in ("PRIVATE-SECURITY", "PRIVATE-PARAMETER", "PRIVATE SQL COMMENT",
                                                 "PRIVATE INVENTED SCREENSHOT", "2020-01-02", "0.012341", str(repo)))
    assert "query_id" not in public
    assert "DRAFT" in public and "NOT SENT" in public


def test_decimal_detail_beyond_float_and_default_precision_is_rechecked_exactly(repo):
    receipt = _run(repo, _prepared(repo, high_precision=True))
    assert receipt["exact_difference"]["minimum_absolute"] == "1E-36"
    assert receipt["mismatch_detail_recomputed_exactly"] is True
    assert receipt["rounding_diagnostics"]["acceptance_rule"] is False
    assert receipt["reconciliation"]["source_discrepancy_explained"] is False


def test_empty_mismatch_table_and_missing_optional_query_documents_remain_truthful(repo):
    receipt = _run(repo, _prepared(repo, exact=True, sql=False), query_evidence=[])
    assert receipt["audit_counts"]["mismatch_dates"] == 0
    assert receipt["exact_difference"]["maximum_absolute"] is None
    assert receipt["reconciliation"]["exact_observed_benchmark_values_equal"] is True
    assert receipt["source_evidence_counts"]["sources_with_bound_sql"] == 0
    assert receipt["source_evidence_counts"]["sources_with_query_displays"] == 0
    assert receipt["model_ready"] is False and receipt["source_approvals"] == 0


@pytest.mark.parametrize("pin", [None, "0" * 64])
def test_recorded_audit_hash_is_required_even_if_internal_receipt_is_self_consistent(repo, pin):
    prepared = _prepared(repo)
    with pytest.raises(ValueError, match="hash"):
        _run(repo, prepared, audit_receipt_sha256=pin)
    assert not (repo / "data/packet").exists()


@pytest.mark.parametrize("change", [
    lambda rows: rows[-1].update(date="2022-03-01"),
    lambda rows: rows[-1].update(date="not-a-date"),
    lambda rows: rows[-1].update(daily_inventory_receipt_sha256="0" * 64),
    lambda rows: rows[-1].update(market_source_csv_record=9999),
])
def test_entire_mismatch_date_and_provenance_pass_precedes_decimal(repo, monkeypatch, change):
    prepared = _prepared(repo)
    _change_table(prepared[0], change)
    def forbidden(*args, **kwargs):
        raise AssertionError("All mismatch dates and provenance must precede Decimal")
    monkeypatch.setattr(audit, "_number", forbidden)
    with pytest.raises(ValueError):
        _run(repo, prepared)
    assert not (repo / "data/packet").exists()


@pytest.mark.parametrize("change", [
    lambda rows: rows[0].update(daily_minus_independent_exact="0"),
    lambda rows: rows[0].update(equal_at_6_decimal_places=True),
    lambda rows: rows[0].update(daily_raw_text="1e1001"),
    lambda rows: rows[0].update(daily_raw_text="NaN"),
    lambda rows: rows[0].update(market_raw_text="-1.1"),
    lambda rows: rows[0].update(daily_rows_affected=2),
])
def test_exact_saved_diagnostics_cannot_be_replaced_by_tolerance_or_fabricated_arithmetic(repo, change):
    prepared = _prepared(repo)
    _change_table(prepared[0], change)
    with pytest.raises(ValueError):
        _run(repo, prepared)
    assert not (repo / "data/packet").exists()


@pytest.mark.parametrize("kind", ["daily", "market"])
def test_same_date_source_conflicts_are_rejected(repo, kind):
    prepared = _prepared(repo, overlap=True)
    field = "daily_raw_text" if kind == "daily" else "market_raw_text"
    _change_table(prepared[0], lambda rows: rows[1].update({field: "0.099999"}))
    with pytest.raises(ValueError, match="conflict|disagree"):
        _run(repo, prepared)


def test_duplicate_or_out_of_order_mismatch_group_cannot_be_hidden_in_rehashed_table(repo):
    prepared = _prepared(repo)
    _change_table(prepared[0], lambda rows: rows.reverse())
    with pytest.raises(ValueError, match="order"):
        _run(repo, prepared)


@pytest.mark.parametrize("target", ["mismatches.parquet", "source_stage_receipt.json", "input_receipts/daily-001.json"])
def test_actual_saved_audit_files_must_match_hashes(repo, target):
    prepared = _prepared(repo)
    path = prepared[0] / target
    path.chmod(0o600)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash"):
        _run(repo, prepared)


def test_market_sql_must_match_its_existing_inventory_hash(repo):
    prepared = _prepared(repo)
    path = repo / "data/market/query.sql"
    path.chmod(0o600)
    path.write_bytes(path.read_bytes() + b"PRIVATE SQL TAMPERING")
    with pytest.raises(ValueError, match="hash"):
        _run(repo, prepared)


@pytest.mark.parametrize("field,value", [
    ("query_observation_sha256", "0" * 64), ("inventory_receipt_sha256", "0" * 64),
    ("preserved_source_sha256", "0" * 64), ("row_counts_equal", False), ("source_approvals", 1),
])
def test_query_association_needs_actual_observation_and_inventory_bindings(repo, field, value):
    prepared = _prepared(repo)
    path = prepared[1] / "inventory-reconciliation-v1.json"
    data = json.loads(path.read_text())
    data[field] = value
    _save(path, data)
    with pytest.raises(ValueError):
        _run(repo, prepared)


def test_query_screenshot_actual_hash_is_verified_without_image_interpretation(repo):
    prepared = _prepared(repo)
    (prepared[1] / "input-parameters.png").write_bytes(b"PRIVATE ALTERED IMAGE")
    with pytest.raises(ValueError, match="hash"):
        _run(repo, prepared)


def test_reconciliation_unrecognized_fields_cannot_leak_through_public_whitelist(repo):
    prepared = _prepared(repo)
    path = prepared[0] / "receipt.json"
    data = json.loads(path.read_text())
    data["reconciliation"]["private_return"] = "PRIVATE LEAK ATTEMPT"
    _save(path, data)
    with pytest.raises(ValueError, match="Boolean"):
        _run(repo, prepared)


@pytest.mark.parametrize("target", ["input", "copied"])
def test_final_input_and_output_mutation_prevents_successful_packet(repo, monkeypatch, target):
    prepared = _prepared(repo)
    original = evidence._vendor_question
    def mutate(summary):
        if target == "input":
            path = prepared[0] / "mismatches.parquet"
        else:
            path = next((repo / "data").glob(".wrds-benchmark-evidence-*/bundle/audit/mismatches.parquet"))
        path.chmod(0o600)
        path.write_bytes(path.read_bytes() + b"PRIVATE TAMPERING")
        return original(summary)
    monkeypatch.setattr(evidence, "_vendor_question", mutate)
    with pytest.raises(ValueError, match="changed"):
        _run(repo, prepared)
    assert not (repo / "data/packet").exists()


def test_output_paths_and_evidence_relative_paths_are_safe(repo):
    prepared = _prepared(repo)
    with pytest.raises(ValueError, match="private"):
        _run(repo, prepared, output=repo / "docs/public")
    with pytest.raises(ValueError, match="separate"):
        _run(repo, prepared, output=prepared[0] / "nested")
    receipt_path = prepared[0] / "receipt.json"
    data = json.loads(receipt_path.read_text())
    data["table"]["file"] = "../escape.parquet"
    _save(receipt_path, data)
    with pytest.raises(ValueError, match="safe relative"):
        _run(repo, prepared)


def test_cli_success_is_aggregate_only_failure_is_sanitized_and_existing_output_preserved(repo, monkeypatch, capsys):
    prepared = _prepared(repo)
    script = Path(__file__).resolve().parents[1] / "scripts/wrds_manual_benchmark_source_evidence.py"
    main = runpy.run_path(str(script))["main"]
    monkeypatch.chdir(repo)
    args = ["--audit", str(prepared[0]), "--audit-receipt-sha256", hashlib.sha256((prepared[0] / "receipt.json").read_bytes()).hexdigest(),
            "--query-evidence", str(prepared[1]), "--output", str(repo / "data/packet")]
    assert main(args) == 0
    printed = capsys.readouterr().out
    assert "PRIVATE-PARAMETER" not in printed and "0.012341" not in printed and str(repo) not in printed
    assert json.loads(printed)["vendor_question_sent"] is False
    original = (repo / "data/packet/receipt.json").read_bytes()
    assert main(args) == 1
    failure = capsys.readouterr().out
    assert json.loads(failure)["status"] == "BENCHMARK_SOURCE_EVIDENCE_FAILED"
    assert str(repo) not in failure and "PRIVATE" not in failure
    assert (repo / "data/packet/receipt.json").read_bytes() == original
