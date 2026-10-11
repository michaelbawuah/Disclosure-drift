"""Synthetic-only checks for the annual candidate consumer and its source gates."""

import copy
import csv
import hashlib
import io
import json
import runpy
from fractions import Fraction
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from disclosure_research import manual_wrds_candidates as numerical
from disclosure_research import manual_wrds_liquidity_candidates as liquidity
from disclosure_research import manual_wrds_listing_candidates as listing
from disclosure_research.manual_wrds_intake import DAILY_FIELDS
from disclosure_research.manual_wrds_metadata import NAMES_FIELDS, inventory_metadata
from disclosure_research.manual_wrds_stage import PARQUET_SCHEMA
from disclosure_research.market_data import development_return_end
from disclosure_research.protocol import canonical_hash, load_protocol, write_lock
from disclosure_research.universe import year_start_window


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "configs").mkdir()
    config = load_protocol()
    write_lock(config, tmp_path / "configs/protocol.lock.json")
    (tmp_path / "configs/protocol.json").write_text(json.dumps(config))
    return tmp_path


def _window(year=2021):
    return year_start_window(year, load_protocol())


def _daily(day, security="10", **changes):
    row = dict(zip(DAILY_FIELDS, (
        security, "900", "PRIVATE-CUSIP", "PRIVATE-TICKER", day, "10", "10", "TR",
        ".01", "NA", "N", "1000", ".001",
    ), strict=True))
    row.update(changes)
    return row


def _name(security="10", **changes):
    row = dict.fromkeys(NAMES_FIELDS, "")
    row.update(permno=security, permco="900", secinfostartdt="2021-01-01", secinfoenddt="2021-12-31",
               securitybegdt="1925-01-01", securityenddt="2025-12-31", issuernm="PRIVATE INVENTED ISSUER",
               ticker="PRIVATE\nMULTILINE", cusip="12345678", securitytype="EQTY", securitysubtype="COM",
               sharetype="NS", issuertype="CORP", primaryexch="N", tradingstatusflg="A",
               hdrprimaryexch="X", hdrsiccd="9999", siccd="1234", usincflg="N", securityactiveflg="N")
    row.update(changes)
    return row


def _numerical(repo, rows, request=None):
    window = _window()
    request = request or (window["liquidity_start"], window["liquidity_end"])
    stage = repo / "data/stage"
    (stage / "projections").mkdir(parents=True)
    source_sha = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    records = [{**row, "source_sha256": source_sha, "source_inventory_sha256": "b" * 64,
                "source_csv_record": index,
                "in_requested_window": request[0] <= row["dlycaldt"] <= request[1]}
               for index, row in enumerate(rows, 2)]
    path = stage / "projections/part-000001.parquet"
    pq.write_table(pa.Table.from_pylist(records, schema=PARQUET_SCHEMA), path)
    part = {"file": "projections/part-000001.parquet", "rows": len(records),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
    requested = sum(record["in_requested_window"] for record in records)
    receipt = {
        "schema_version": 1, "status": numerical.STAGE_STATUS, "protocol_sha256": canonical_hash(load_protocol()),
        "model_ready": False, "source_approvals": 0, "final_period_opened": False,
        "request": {"start": request[0], "end": request[1],
                    "last_permitted_development_return_date": development_return_end(load_protocol())},
        "projection": {"fields": list(DAILY_FIELDS), "provenance_fields": list(numerical.PROVENANCE),
                       "all_source_records_preserved": True, "duplicate_rows_retained": True,
                       "duplicate_comparison_scope": "required_13_fields_in_canonical_order",
                       "parts": [part], "rows": len(records), "requested_rows": requested},
        "sources": [{"role": "daily", "source_sha256": source_sha,
                     "inventory_receipt_sha256": "b" * 64, "rows": len(records)}],
        "reconciliation": {"requested_window_numerically_reconciled": False},
    }
    (stage / "receipt.json").write_text(json.dumps(receipt))
    output = repo / "data/numerical"
    numerical.build_candidates(stage, output=output, config=load_protocol(), repo_root=repo)
    return output


def _listing(repo, rows):
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow([field.upper() for field in reversed(NAMES_FIELDS)])
    writer.writerows([[row[field] for field in reversed(NAMES_FIELDS)] for row in rows])
    source = repo / "invented-names.csv"
    source.write_bytes(text.getvalue().encode())
    inventory = repo / "data/names-inventory"
    inventory_metadata(source, role="names", request_start="2009-10-07", request_end="2022-02-02",
                       output=inventory, config=load_protocol(), repo_root=repo)
    output = repo / "data/listing"
    listing.build_listing_candidates(inventory, output=output, config=load_protocol(), repo_root=repo)
    return output


def _inputs(repo, daily=None, names=None, request=None):
    daily = daily if daily is not None else [_daily(day) for day in _window()["sessions"][:40]]
    names = names if names is not None else [_name()]
    return _numerical(repo, daily, request), _listing(repo, names)


def _run(repo, inputs, **options):
    return liquidity.build_liquidity_candidates(*inputs, **{
        "output": repo / "data/liquidity", "config": load_protocol(), "repo_root": repo, **options})


def _rows(repo, receipt):
    return [row for part in receipt["annual_liquidity"]["parts"]
            for row in pq.read_table(repo / "data/liquidity" / part["file"]).to_pylist()]


def _receipt(directory):
    return json.loads((directory / "receipt.json").read_text())


def _save_receipt(directory, receipt):
    path = directory / "receipt.json"
    path.chmod(0o600)
    path.write_text(json.dumps(receipt))


def _change_part(directory, change, index=0, change_receipt=None):
    receipt = _receipt(directory)
    part = receipt["projection"]["parts"][index]
    path = directory / part["file"]
    original = pq.read_table(path)
    rows = original.to_pylist()
    change(rows)
    path.chmod(0o600)
    pq.write_table(pa.Table.from_pylist(rows, schema=original.schema), path)
    path.chmod(0o400)
    part.update(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), rows=len(rows))
    if change_receipt:
        change_receipt(receipt)
    _save_receipt(directory, receipt)


def test_real_upstream_integration_private_bytes_calendar_nulls_and_provenance(repo, monkeypatch):
    monkeypatch.setattr(liquidity, "_BATCH", 2)
    inputs = _inputs(repo, names=[_name(secinfostartdt="2010-01-01", secinfoenddt="2025-12-31")])
    originals = {path: path.read_bytes() for directory in inputs for path in directory.rglob("*") if path.is_file()}
    receipt = _run(repo, inputs)
    rows = _rows(repo, receipt)
    assert [row["candidate_year"] for row in rows] == list(range(2010, 2022))
    assert receipt["years"] == list(range(2010, 2022))
    assert receipt["annual_liquidity"]["rows"] == 12
    assert receipt["known_at_null_rows"] == receipt["available_at_null_rows"] == 12
    assert receipt["reconciliation"] == _receipt(inputs[0])["reconciliation"]
    assert receipt["reconciliation"]["requested_window_numerically_reconciled"] is False
    assert receipt["input_preflight"]["all_input_dates_before_numerical_values"] is True
    assert receipt["input_preflight"]["original_csv_files_reopened"] is False
    output = repo / "data/liquidity"
    for part in receipt["annual_liquidity"]["parts"]:
        path = output / part["file"]
        assert pq.read_schema(path) == liquidity.ANNUAL_SCHEMA
        assert part["rows"] <= 2
        assert part["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert part["bytes"] == path.stat().st_size
    for source, detail in zip(_receipt(inputs[1])["projection"]["parts"], receipt["listing_evidence"]["parts"], strict=True):
        assert (output / detail["file"]).read_bytes() == originals[inputs[1] / source["file"]]
    assert (output / "input_receipts/numerical.json").read_bytes() == originals[inputs[0] / "receipt.json"]
    assert (output / "input_receipts/listing.json").read_bytes() == originals[inputs[1] / "receipt.json"]
    assert all(path.read_bytes() == raw for path, raw in originals.items())
    assert all(path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o400)
               for path in [output, *output.rglob("*")])
    for row in rows:
        window = _window(row["candidate_year"])
        assert all(row[key] == value for key, value in window.items() if key != "sessions")
        assert row["known_at"] is row["available_at"] is None
        assert row["numerical_candidate_receipt_sha256"] == hashlib.sha256(originals[inputs[0] / "receipt.json"]).hexdigest()
        assert row["listing_candidate_receipt_sha256"] == hashlib.sha256(originals[inputs[1] / "receipt.json"]).hexdigest()
        assert "cik" not in row and "issuer_rank" not in row
    assert rows[-1]["candidate_security_rank"] == 1
    assert all(row["candidate_security_rank"] is None for row in rows[:-1])
    assert receipt["model_ready"] is False and receipt["source_approvals"] == 0
    assert receipt["prior_arithmetic_review_modified"] is False
    assert receipt["final_period_opened"] is False
    assert receipt["issuer_grouping_performed"] is receipt["issuer_limit_applied"] is False


def test_union_session_accounting_repeats_conflicts_zero_and_names_ambiguity(repo):
    days = _window()["sessions"]
    daily = [_daily(day) for day in days[:40]]
    daily += [_daily(days[0]), _daily(days[40], dlyvol="0", dlyprcflg="BA"),
              _daily(days[41]), _daily(days[41], ticker="SAME-LIQUIDITY-DIFFERENT-RAW-PROJECTION"),
              _daily(days[42], dlyprcflg="DA")]
    daily += [_daily(day, "20", dlyvol="20") for day in days[:40]]
    daily += [_daily(day, "40") for day in days[:40]]
    inputs = _inputs(repo, daily, [_name(), _name("30"), _name("40"), _name("40")])
    receipt = _run(repo, inputs)
    rows = {row["security_id"]: row for row in _rows(repo, receipt)}
    assert set(rows) == {"10", "20", "30", "40"}
    row = rows["10"]
    assert row["observed_sessions"] == 43
    assert row["distinct_projection_rows"] == 44
    assert row["source_records"] == 45
    assert row["equivalent_13_field_record_excess"] == 1
    assert row["unambiguous_sessions"] == 42
    assert row["numerically_valid_sessions"] == 41
    assert row["conflicting_sessions"] == row["withheld_sessions"] == 1
    assert row["missing_sessions"] == 17
    assert row["zero_volume_candidate_sessions"] == row["bid_ask_valid_sessions"] == 1
    assert row["trade_price_valid_sessions"] == 40
    assert row["mean_closing_price_volume_usd_candidate"] == float(Fraction(4000, 41))
    assert row["candidate_security_rank"] == 1
    assert json.loads(row["withheld_reason_counts"]) == {
        "conflicting_security_date_projection": 1, "upstream_unsupported_liquidity_price_flag": 1}
    assert rows["20"]["listing_candidate_status"] == "NO_DATED_NAMES_CANDIDATE"
    assert rows["20"]["meets_numeric_minimum_40"] is True and rows["20"]["candidate_security_rank"] is None
    assert rows["30"]["missing_sessions"] == 60 and rows["30"]["observed_sessions"] == 0
    assert rows["30"]["mean_closing_price_volume_usd_candidate"] is None
    assert rows["40"]["listing_record_count"] == 2 and rows["40"]["listing_distinct_projection_count"] == 1
    assert rows["40"]["ambiguous_listing"] is True and rows["40"]["candidate_security_rank"] is None
    assert receipt["listing_evidence"]["rows"] == 4
    summary = receipt["year_summaries"][-1]
    assert summary["names_only_securities"] == summary["daily_only_securities"] == 1
    assert summary["names_and_daily_securities"] == 2


def test_duplicate_weights_never_satisfy_minimum_and_forty_zero_values_do(repo):
    days = _window()["sessions"]
    daily = [_daily(days[0])] * 100 + [_daily(day) for day in days[1:39]]
    daily += [_daily(day, "20", dlyvol="0", dlyprcflg="BA") for day in days[:40]]
    rows = {row["security_id"]: row for row in _rows(repo, _run(repo, _inputs(repo, daily, [_name(), _name("20")])))}
    assert rows["10"]["source_records"] == 138 and rows["10"]["numerically_valid_sessions"] == 39
    assert rows["10"]["meets_numeric_minimum_40"] is False
    assert rows["20"]["zero_volume_candidate_sessions"] == 40
    assert rows["20"]["mean_closing_price_volume_usd_candidate"] == 0
    assert rows["20"]["candidate_security_rank"] == 1


def test_raw_security_ties_and_scope_categories_never_become_issuer_selection(repo):
    days = _window()["sessions"][:40]
    daily = [_daily(day, security) for security in ("2", "10", "30", "40", "50") for day in days]
    names = [_name("2"), _name("10", hdrprimaryexch="PRIVATE-FUTURE", hdrsiccd="PRIVATE-FUTURE"),
             _name("30", issuertype="REIT"), _name("40", sharetype="AD"), _name("50", tradingstatusflg="S")]
    receipt = _run(repo, _inputs(repo, daily, names))
    rows = {row["security_id"]: row for row in _rows(repo, receipt)}
    assert rows["10"]["candidate_security_rank"] == 1 and rows["2"]["candidate_security_rank"] == 2
    assert rows["30"]["listing_candidate_status"] == "SCOPE_REVIEW_REIT_COMMON"
    assert rows["40"]["listing_candidate_status"] == "SCOPE_REVIEW_ADR_COMMON"
    assert rows["50"]["listing_candidate_status"] == "DATED_SUSPENDED"
    assert all(rows[key]["candidate_security_rank"] is None for key in ("30", "40", "50"))


def test_future_only_daily_security_cannot_enter_earlier_year_union(repo):
    days = _window()["sessions"]
    daily = [_daily(day) for day in days[:40]] + [_daily("2021-01-04", "FUTURE-ONLY-PRIVATE")]
    receipt = _run(repo, _inputs(repo, daily, request=(days[0], "2021-01-04")))
    assert [row["security_id"] for row in _rows(repo, receipt)] == ["10"]
    assert receipt["input_preflight"]["numerical_rows"] == 41
    assert receipt["year_summaries"][-1]["observed_sessions"] == 40


def test_partial_request_records_global_calendar_gaps_without_filling(repo):
    days = _window()["sessions"]
    receipt = _run(repo, _inputs(repo, [_daily(day) for day in days[-10:]], request=(days[-10], days[-1])))
    row = _rows(repo, receipt)[0]
    assert row["numerically_valid_sessions"] == 10 and row["missing_sessions"] == 50
    summary = receipt["year_summaries"][-1]
    assert summary["request_covers_entire_window"] is False
    assert summary["window_sessions_with_any_daily_candidate"] == 10
    assert summary["window_sessions_without_any_daily_candidate"] == 50


@pytest.mark.parametrize("bad,reason", [
    (None, "missing_candidate_value"), (float("nan"), "nonfinite_candidate_value"),
    (float("inf"), "nonfinite_candidate_value"), (-1.0, "negative_candidate_value"),
])
def test_invalid_bound_candidate_values_are_withheld_and_never_satisfy_minimum(repo, bad, reason):
    inputs = _inputs(repo)
    _change_part(inputs[0], lambda rows: rows[0].update(closing_price_volume_usd_candidate=bad))
    receipt = _run(repo, inputs)
    row = _rows(repo, receipt)[0]
    assert row["numerically_valid_sessions"] == 39 and row["withheld_sessions"] == 1
    assert row["candidate_security_rank"] is None
    assert json.loads(row["withheld_reason_counts"]) == {reason: 1}


def test_float_mean_is_reproducible_correctly_rounded_and_does_not_overflow_finite_mean():
    values = [1e308, 1e308, 0.1, 0.2, 1e-300]
    expected = float(sum((Fraction.from_float(value) for value in values), Fraction()) / len(values))
    assert liquidity._mean(values) == liquidity._mean(list(reversed(values))) == (expected, False)
    assert liquidity._mean([1e308] * 60) == (1e308, False)
    assert liquidity._mean([float.fromhex("0x0.0000000000001p-1022"), 0.0, 0.0]) == (0.0, True)


@pytest.mark.parametrize("role,change", [
    (0, lambda rows: rows[-1].update(session="2022-03-01")),
    (1, lambda rows: rows[-1].update(candidate_year=2022)),
    (1, lambda rows: rows[-1].update(secinfoenddt="B")),
    (1, lambda rows: rows[-1].update(known_at="2020-12-31T21:00:00Z")),
    (1, lambda rows: rows[-1].update(information_cutoff="2021-01-01T00:00:00Z")),
])
def test_every_input_date_and_availability_gate_precedes_any_numeric_work(repo, monkeypatch, role, change):
    inputs = _inputs(repo)
    _change_part(inputs[role], change)
    def forbidden(*args, **kwargs):
        raise AssertionError("Numerical work must wait for every input date")
    monkeypatch.setattr(liquidity, "_value", forbidden)
    monkeypatch.setattr(liquidity, "_mean", forbidden)
    with pytest.raises(ValueError):
        _run(repo, inputs)
    assert not (repo / "data/liquidity").exists()


@pytest.mark.parametrize("role,key,value", [
    (0, "status", "APPROVED"), (1, "status", "APPROVED"),
    (0, "model_ready", True), (1, "source_approvals", 1),
    (0, "protocol_sha256", "0" * 64), (1, "final_period_opened", True),
    (1, "prior_arithmetic_review_modified", True),
])
def test_exact_upstream_contracts_are_required(repo, role, key, value):
    inputs = _inputs(repo)
    receipt = _receipt(inputs[role])
    receipt[key] = value
    _save_receipt(inputs[role], receipt)
    with pytest.raises(ValueError):
        _run(repo, inputs)


@pytest.mark.parametrize("role", [0, 1])
def test_actual_part_hash_and_safe_relative_path_are_required(repo, role):
    inputs = _inputs(repo)
    receipt = _receipt(inputs[role])
    part = inputs[role] / receipt["projection"]["parts"][0]["file"]
    original = part.read_bytes()
    part.chmod(0o600)
    part.write_bytes(original + b"PRIVATE-TAMPERING")
    with pytest.raises(ValueError, match="hash"):
        _run(repo, inputs)
    part.write_bytes(original)
    receipt["projection"]["parts"][0]["file"] = "../escape.parquet"
    _save_receipt(inputs[role], receipt)
    with pytest.raises(ValueError, match="safe relative"):
        _run(repo, inputs)


def test_exact_schema_and_declared_part_row_count_are_required(repo):
    inputs = _inputs(repo)
    receipt = _receipt(inputs[0])
    spec = receipt["projection"]["parts"][0]
    path = inputs[0] / spec["file"]
    table = pq.read_table(path)
    path.chmod(0o600)
    pq.write_table(table.drop(["price_flag"]), path)
    spec.update(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    _save_receipt(inputs[0], receipt)
    with pytest.raises(ValueError, match="schema or row count"):
        _run(repo, inputs)


def test_numerical_provenance_and_duplicate_projection_metadata_fail_closed(repo):
    inputs = _inputs(repo)
    _change_part(inputs[0], lambda rows: rows[0].update(representative_source_csv_record=1_000_000))
    with pytest.raises(ValueError, match="provenance"):
        _run(repo, inputs)


def test_numerical_variant_counts_cannot_be_used_to_hide_a_duplicate(repo):
    inputs = _inputs(repo)
    def duplicate(rows):
        rows[1].update(rows[0])
    _change_part(inputs[0], duplicate)
    with pytest.raises(ValueError, match="duplicated"):
        _run(repo, inputs)


def test_declared_names_overlap_must_match_actual_full_projection_group(repo):
    inputs = _inputs(repo)
    _change_part(inputs[1], lambda rows: rows[0].update(
        security_year_record_count=2, ambiguous_security_year=True, ordinary_candidate=False,
        candidate_status="AMBIGUOUS_DATED_RECORDS"))
    with pytest.raises(ValueError, match="actual overlap"):
        _run(repo, inputs)


@pytest.mark.parametrize("role,chain", [(0, "source_stage_receipt.json"), (1, "input_receipts/names.json")])
def test_upstream_source_receipt_snapshots_are_hash_bound(repo, role, chain):
    inputs = _inputs(repo)
    path = inputs[role] / chain
    path.chmod(0o600)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="binding"):
        _run(repo, inputs)


def test_mutation_after_date_preflight_is_rejected_before_values(repo, monkeypatch):
    inputs = _inputs(repo)
    original = liquidity._listing_preflight
    def mutate(*args):
        result = original(*args)
        path = inputs[0] / "receipt.json"
        path.chmod(0o600)
        path.write_bytes(path.read_bytes() + b" ")
        return result
    monkeypatch.setattr(liquidity, "_listing_preflight", mutate)
    with pytest.raises(ValueError, match="changed"):
        _run(repo, inputs)
    assert not (repo / "data/liquidity").exists()


@pytest.mark.parametrize("target", ["input", "snapshot", "detail"])
def test_final_hash_checks_catch_mutation_during_aggregation(repo, monkeypatch, target):
    inputs = _inputs(repo)
    original = liquidity._emit
    def mutate(db, out, *args):
        result = original(db, out, *args)
        if target == "input":
            path = inputs[0] / _receipt(inputs[0])["projection"]["parts"][0]["file"]
        elif target == "snapshot":
            path = out / "input_receipts/numerical.json"
        else:
            path = out / "listing_evidence/part-000001.parquet"
        path.chmod(0o600)
        path.write_bytes(path.read_bytes() + b"PRIVATE-TAMPERING")
        return result
    monkeypatch.setattr(liquidity, "_emit", mutate)
    with pytest.raises(ValueError, match="changed"):
        _run(repo, inputs)
    assert not (repo / "data/liquidity").exists()


def test_frozen_years_and_window_sizes_still_hold_with_a_rewritten_lock(repo):
    inputs = _inputs(repo)
    config = copy.deepcopy(load_protocol())
    config["liquidity_lookback_sessions"] = 59
    (repo / "configs/protocol.lock.json").unlink()
    write_lock(config, repo / "configs/protocol.lock.json")
    with pytest.raises(ValueError, match="frozen"):
        _run(repo, inputs, config=config)


def test_output_refuses_public_nested_and_existing_locations(repo):
    inputs = _inputs(repo)
    with pytest.raises(ValueError, match="private"):
        _run(repo, inputs, output=repo / "docs/published")
    with pytest.raises(ValueError, match="separate"):
        _run(repo, inputs, output=inputs[0] / "nested")
    _run(repo, inputs)
    with pytest.raises(ValueError, match="exists"):
        _run(repo, inputs)


def test_empty_listing_snapshots_leave_daily_only_security_visible(repo):
    receipt = _run(repo, _inputs(repo, names=[_name(secinfostartdt="2022-01-01", secinfoenddt="2025-12-31")]))
    row = _rows(repo, receipt)[0]
    assert row["listing_record_count"] == 0 and row["candidate_security_rank"] is None
    assert receipt["listing_evidence"]["rows"] == 0


def test_zero_numerical_candidate_rows_leave_names_only_security_visible(repo):
    days = _window()["sessions"]
    inputs = _inputs(repo, daily=[_daily("2020-01-02")], request=(days[0], days[-1]))
    receipt = _run(repo, inputs)
    row = _rows(repo, receipt)[0]
    assert row["listing_record_count"] == 1 and row["observed_sessions"] == 0
    assert row["missing_sessions"] == 60 and receipt["input_preflight"]["numerical_rows"] == 0


def test_more_than_five_hundred_securities_are_ranked_without_issuer_cutoff(repo):
    securities = [str(10_000 + index) for index in range(501)]
    days = _window()["sessions"][:40]
    inputs = _inputs(repo, [_daily(day, security) for security in securities for day in days],
                     [_name(security) for security in securities])
    receipt = _run(repo, inputs)
    rows = _rows(repo, receipt)
    assert len(rows) == 501 and max(row["candidate_security_rank"] for row in rows) == 501
    assert receipt["issuer_limit_applied"] is False


def test_cli_is_aggregate_only_on_success_and_sanitizes_failure(repo, monkeypatch, capsys):
    inputs = _inputs(repo, daily=[_daily(_window()["sessions"][0], "PRIVATE-IDENTIFIER",
                                      dlyprcflg="https://private.example/secret")])
    script = Path(__file__).resolve().parents[1] / "scripts/wrds_manual_liquidity_candidates.py"
    main = runpy.run_path(str(script))["main"]
    monkeypatch.chdir(repo)
    args = ["--numerical-candidates", str(inputs[0]), "--listing-candidates", str(inputs[1]),
            "--output", str(repo / "data/liquidity")]
    assert main(args) == 0
    printed = capsys.readouterr().out
    summary = json.loads(printed)
    assert summary["source_approvals"] == 0
    assert "PRIVATE" not in printed and "private.example" not in printed
    assert str(repo) not in printed and "mean_closing" not in printed
    assert main(args) == 1
    error = capsys.readouterr().out
    assert json.loads(error)["status"] == "LIQUIDITY_CANDIDATES_FAILED"
    assert str(repo) not in error
    with pytest.raises(SystemExit):
        main([*args, "--years", "2022"])
