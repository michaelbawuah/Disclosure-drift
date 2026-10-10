"""Synthetic-only checks for raw-source staging and benchmark reconciliation."""

import csv
import gzip
import hashlib
import io
import json
import runpy
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from disclosure_research import manual_wrds_stage as stage
from disclosure_research.manual_wrds_intake import DAILY_FIELDS
from disclosure_research.protocol import canonical_hash, load_protocol, write_lock


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "configs").mkdir()
    config = load_protocol()
    write_lock(config, tmp_path / "configs" / "protocol.lock.json")
    (tmp_path / "configs" / "protocol.json").write_text(json.dumps(config))
    return tmp_path


def daily(day="2009-10-07", value="0.01", **changes):
    row = dict(zip(DAILY_FIELDS, (
        "invented-security-secret", "20001", "12345678", "INVENTED", day,
        "20", "100", "T", "raw-stock-return-secret", "UNRESOLVED", "N", "2000", value,
    ), strict=True))
    row.update(changes)
    return row


def bundle(repo, name, rows, *, role="daily", header=None, compressed=False, allow_extra=False):
    header = list(header or (DAILY_FIELDS if role == "daily" else ("dlycaldt", "vwretd")))
    content = io.StringIO(newline="")
    writer = csv.writer(content)
    writer.writerow(header)
    for row in rows:
        writer.writerow([row.get(field.lower(), "extra-raw-private-value") for field in header])
    raw = content.getvalue().encode()
    if compressed:
        raw = gzip.compress(raw, mtime=0)
    directory = repo / "data" / name
    directory.mkdir(parents=True)
    source = directory / "source.bin"
    source.write_bytes(raw)
    source.chmod(0o400)
    dates = sorted({row["dlycaldt"] for row in rows})
    receipt = {
        "schema_version": 1,
        "status": ("RAW_MANUAL_WRDS_INVENTORY_NOT_AUDIT_APPROVED" if role == "daily"
                   else "RAW_MANUAL_WRDS_MARKET_INVENTORY_NOT_SOURCE_APPROVED"),
        "protocol_sha256": canonical_hash(load_protocol()),
        "source": {"preserved_file": source.name, "sha256": hashlib.sha256(raw).hexdigest(),
                   "bytes": len(raw), "observed_header": header, "source_release": None},
        "request": {"start": "2009-10-07", "end": "2009-10-09"},
        "actual_coverage": {"first_date": dates[0], "last_date": dates[-1], "distinct_dates": len(dates)},
        "all_rows": {"rows": len(rows)}, "model_ready": False,
    }
    if role == "daily" and allow_extra:
        receipt["projection"] = {
            "fields": list(DAILY_FIELDS), "allow_extra_columns": True,
            "extra_columns": [field for field in header if field.lower() not in DAILY_FIELDS],
        }
    (directory / "receipt.json").write_text(json.dumps(receipt))
    return directory


def market(repo, rows=None, **options):
    return bundle(repo, "market", rows or [{"dlycaldt": "2009-10-07", "vwretd": "0.01"}],
                  role="market", **options)


def run(repo, dailies, independent, **options):
    arguments = {"request_start": "2009-10-07", "request_end": "2009-10-09",
                 "output": repo / "data" / "stage", "config": load_protocol(), "repo_root": repo}
    return stage.stage_manual_development(dailies, independent, **{**arguments, **options})


def change_receipt(directory, change):
    path = directory / "receipt.json"
    receipt = json.loads(path.read_text())
    change(receipt)
    path.write_text(json.dumps(receipt))


def replace_source(directory, before, after, *, update_receipt=False):
    path = directory / "source.bin"
    raw = path.read_bytes().replace(before, after)
    path.chmod(0o600)
    path.write_bytes(raw)
    path.chmod(0o400)
    if update_receipt:
        change_receipt(directory, lambda value: value["source"].update(
            sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)))


@pytest.mark.parametrize("compressed", [False, True])
def test_raw_records_parts_provenance_hashes_and_exact_decimal_comparison(repo, monkeypatch, compressed):
    monkeypatch.setattr(stage, "_BATCH_ROWS", 2)
    header = [field.upper() for field in reversed(DAILY_FIELDS)] + ["ExtraField"]
    repeated = daily(value="0.010", ticker="INVENTED\nMULTILINE")
    first = bundle(repo, "first", [daily("2007-10-08"),
                                  {**repeated, "extrafield": "first-private-extra"},
                                  {**repeated, "extrafield": "second-private-extra"}],
                   header=header, compressed=compressed, allow_extra=True)
    second = bundle(repo, "second", [daily(value="1e-2", permno="different-private-security"),
                                    daily("2009-10-08", "0.02"), daily("2009-10-09", "0.03")])
    independent = market(repo, [{"dlycaldt": f"2009-10-0{day}", "vwretd": value}
                               for day, value in [(7, "0.01"), (8, "0.02"), (9, "0.03")]],
                         header=("VWRETD", "DlyCalDt"), compressed=compressed)
    originals = {path: (path / "source.bin").read_bytes() for path in (first, second, independent)}
    receipt_bytes = {path: (path / "receipt.json").read_bytes() for path in originals}
    result = run(repo, [first, second], independent)
    output = repo / "data" / "stage"
    assert result["projection"]["rows"] == 6
    assert result["projection"]["requested_rows"] == 5
    assert result["projection"]["duplicate_rows_retained"] is True
    assert result["projection"]["full_delivered_row_duplicates_checked"] is False
    assert result["coverage"]["daily_union"]["outside_calendar_date_count"] == 1
    assert result["coverage"]["daily_union"]["non_xnys_date_count"] == 0
    assert result["coverage"]["daily_union"]["missing_xnys_sessions"] == []
    assert result["coverage"]["batch_overlap"]["requested_dates"] == {
        "dates_in_multiple_daily_batches": 1, "rows_on_shared_dates": 3}
    compared = result["reconciliation"]
    assert compared["numeric_equal_rows"] == 5
    assert compared["numeric_equal_text_different_rows"] == 3
    assert compared["exact_text_equal_rows"] == 2
    assert compared["numeric_mismatch_rows"] == 0
    assert compared["daily_dates_with_distinct_raw_texts"] == 1
    assert compared["daily_dates_with_conflicting_numeric_values"] == 0
    assert compared["requested_window_numerically_reconciled"] is True
    staged = []
    for part in result["projection"]["parts"]:
        path = output / part["file"]
        table = pq.read_table(path)
        assert table.schema == stage.PARQUET_SCHEMA
        assert part["rows"] == table.num_rows <= 2
        assert part["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert part["bytes"] == path.stat().st_size
        assert path.stat().st_mode & 0o222 == 0
        staged.extend(table.to_pylist())
    assert [row["source_csv_record"] for row in staged] == [2, 3, 4, 2, 3, 4]
    assert [row["in_requested_window"] for row in staged] == [False, True, True, True, True, True]
    assert staged[1]["ticker"] == "INVENTED\nMULTILINE"
    assert staged[1]["dlyret"] == "raw-stock-return-secret"
    assert staged[1]["dlyretmissflg"] == "UNRESOLVED"
    assert {key: staged[1][key] for key in DAILY_FIELDS} == {key: staged[2][key] for key in DAILY_FIELDS}
    assert "ExtraField" not in staged[1]
    for binding in result["sources"]:
        directory = Path(binding["inventory_directory"])
        assert (directory / "source.bin").read_bytes() == originals[directory]
        assert (output / binding["inventory_receipt_file"]).read_bytes() == receipt_bytes[directory]
        assert binding["source_sha256"] == hashlib.sha256(originals[directory]).hexdigest()
        if binding["role"] == "daily":
            records = [row for row in staged if row["source_sha256"] == binding["source_sha256"]]
            assert len(records) == binding["rows"]
            assert all(row["source_inventory_sha256"] == binding["inventory_receipt_sha256"] for row in records)
    public = json.dumps(stage.aggregate_summary(result))
    assert all(secret not in public for secret in ("invented-security-secret", "raw-stock-return-secret",
                                                 "private-extra", "MULTILINE", str(repo)))
    assert result["model_ready"] is False and result["source_approvals"] == 0
    assert result["prior_arithmetic_review_modified"] is False and result["final_period_opened"] is False
    assert result["rows_dropped"] == result["values_filled"] == result["values_normalized"] == 0
    assert not list(output.glob("source-stage-*"))
    assert json.loads((output / "receipt.json").read_text()) == result


def test_numeric_precision_conflicts_missing_market_and_gaps_are_explicit(repo):
    path = bundle(repo, "daily", [daily(), daily(value="0.010000000000000000000000000001"),
                                  daily("2009-10-08", "0.02"), daily("2009-10-08", "")])
    result = run(repo, [path], market(repo))
    compared = result["reconciliation"]
    assert compared["numeric_mismatch_rows"] == compared["numeric_mismatch_dates"] == 1
    assert compared["daily_dates_with_conflicting_numeric_values"] == 1
    assert compared["rows_missing_market_date"] == 2 and compared["missing_market_dates"] == 1
    assert compared["daily_benchmark_classifications"]["blank"] == 1
    assert compared["reconciliation_passed"] is False
    assert compared["requested_window_numerically_reconciled"] is False
    assert compared["fallback_used"] is False
    assert result["projection"]["rows"] == 4


def test_equal_observed_cells_do_not_certify_missing_expected_sessions(repo):
    result = run(repo, [bundle(repo, "daily", [daily()])], market(repo))
    assert result["reconciliation"]["reconciliation_passed"] is True
    assert result["reconciliation"]["requested_window_numerically_reconciled"] is False
    assert result["coverage"]["daily_union"]["missing_xnys_sessions"] == ["2009-10-08", "2009-10-09"]


@pytest.mark.parametrize("value,kind", [("", "blank"), (".A", "malformed"), ("NaN", "nonfinite_numeric"),
                                        ("1e999", "nonfinite_numeric"),
                                        ("-1.000000000000000000001", "finite_numeric_below_minus_one")])
def test_invalid_daily_benchmark_is_retained_without_approval(repo, value, kind):
    result = run(repo, [bundle(repo, "daily", [daily(value=value)])], market(repo))
    assert result["reconciliation"]["daily_benchmark_classifications"][kind] == 1
    assert result["reconciliation"]["invalid_daily_benchmark_dates"] == 1
    assert result["reconciliation"]["requested_window_numerically_reconciled"] is False
    part = repo / "data" / "stage" / result["projection"]["parts"][0]["file"]
    assert pq.read_table(part, columns=["vwretd"])["vwretd"].to_pylist() == [value]


@pytest.mark.parametrize("values", [["0.01", "0.01"], ["0.01", "0.010"], [""], ["NaN"],
                                      ["-1.000000000000000000001"], ["malformed-private-text"]])
def test_invalid_or_duplicate_market_refuses_daily_projection_with_aggregate_evidence(repo, monkeypatch, values):
    path = bundle(repo, "daily", [daily()])
    independent = market(repo, [{"dlycaldt": "2009-10-07", "vwretd": value} for value in values])
    monkeypatch.setattr(stage, "_project_daily", lambda *args: pytest.fail("Invalid market reached projection"))
    with pytest.raises(stage.SourceStageError, match="Independent market"):
        run(repo, [path], independent)
    out = repo / "data" / "stage"
    assert not (out / "receipt.json").exists()
    assert list((out / "projections").iterdir()) == []
    failure = json.loads((out / "stage_failure.json").read_text())
    assert failure["independent_market"]["unique_dates_and_valid_returns"] is False
    assert "malformed-private-text" not in json.dumps(failure)


@pytest.mark.parametrize("bad_day", ["2022-02-03", "2025-01-02", "2009-02-30", "2009-1-2", ""])
@pytest.mark.parametrize("location", ["later_daily", "market"])
def test_all_sources_dates_are_preflighted_before_any_numeric_value(repo, monkeypatch, bad_day, location):
    paths = [bundle(repo, "first", [daily(value="private-not-a-number")])]
    if location == "later_daily":
        paths.append(bundle(repo, "second", [daily(bad_day)]))
        independent = market(repo)
    else:
        independent = market(repo, [{"dlycaldt": bad_day, "vwretd": "private-not-a-number"}])
    monkeypatch.setattr(stage, "_exact_return", lambda _: pytest.fail("Numeric value opened before ALL dates"))
    with pytest.raises(ValueError):
        run(repo, paths, independent)
    assert not (repo / "data" / "stage" / "receipt.json").exists()
    assert list((repo / "data" / "stage" / "projections").iterdir()) == []


def test_hash_mismatch_is_refused_before_dates_or_values(repo, monkeypatch):
    path = bundle(repo, "daily", [daily()])
    replace_source(path, b"0.01", b"0.02")
    monkeypatch.setattr(stage, "_date_preflight", lambda *args: pytest.fail("Unbound source opened"))
    with pytest.raises(ValueError, match="hash changed"):
        run(repo, [path], market(repo))


@pytest.mark.parametrize("target", ["source", "receipt"])
def test_earlier_input_mutation_during_later_date_pass_blocks_all_values(repo, monkeypatch, target):
    first = bundle(repo, "first", [daily()])
    second = bundle(repo, "second", [daily("2009-10-08")])
    original = stage._date_preflight

    def mutate(current, *args):
        result = original(current, *args)
        if current.source_id == "daily-002":
            if target == "source":
                replace_source(first, b"0.01", b"0.02")
            else:
                change_receipt(first, lambda value: value.update(unreviewed_change=True))
        return result

    monkeypatch.setattr(stage, "_date_preflight", mutate)
    monkeypatch.setattr(stage, "_exact_return", lambda _: pytest.fail("Mutation must block numerical values"))
    with pytest.raises(ValueError, match="changed during staging"):
        run(repo, [first, second], market(repo))


def test_mutation_after_projection_prevents_success_receipt(repo, monkeypatch):
    path = bundle(repo, "daily", [daily()])
    original = stage._project_daily

    def mutate(*args):
        result = original(*args)
        replace_source(path, b"0.01", b"0.02")
        return result

    monkeypatch.setattr(stage, "_project_daily", mutate)
    with pytest.raises(ValueError, match="changed during staging"):
        run(repo, [path], market(repo))
    assert not (repo / "data" / "stage" / "receipt.json").exists()


@pytest.mark.parametrize("kind", ["header", "record_width", "count", "date_coverage", "extra_allowance"])
def test_header_width_count_coverage_and_extra_opt_in_are_verified(repo, monkeypatch, kind):
    path = bundle(repo, "daily", [daily()], header=(*DAILY_FIELDS, "Extra") if kind == "extra_allowance" else None)
    if kind == "header":
        replace_source(path, b"permno,", b"PERMNO,", update_receipt=True)
    elif kind == "record_width":
        replace_source(path, b"raw-stock-return-secret,", b"raw-stock-return-secret,unannounced-column,", update_receipt=True)
    elif kind == "count":
        change_receipt(path, lambda value: value["all_rows"].update(rows=2))
    elif kind == "date_coverage":
        change_receipt(path, lambda value: value["actual_coverage"].update(last_date="2009-10-08"))
    monkeypatch.setattr(stage, "_exact_return", lambda _: pytest.fail("Schema failed before values"))
    with pytest.raises(ValueError):
        run(repo, [path], market(repo))


@pytest.mark.parametrize("source_path", ["../source.bin", "/tmp/source.bin", "nested/../source.bin", "a//b", "a\\b"])
def test_unsafe_receipt_relative_source_paths_refused(repo, source_path):
    path = bundle(repo, "daily", [daily()])
    change_receipt(path, lambda value: value["source"].update(preserved_file=source_path))
    with pytest.raises(ValueError, match="safe relative path"):
        run(repo, [path], market(repo))


def test_symlink_source_refused_and_repeated_source_not_double_counted(repo):
    path = bundle(repo, "daily", [daily()])
    independent = market(repo)
    (path / "alias.bin").symlink_to(path / "source.bin")
    change_receipt(path, lambda value: value["source"].update(preserved_file="alias.bin"))
    with pytest.raises(ValueError, match="symbolic links"):
        run(repo, [path], independent)
    change_receipt(path, lambda value: value["source"].update(preserved_file="source.bin"))
    with pytest.raises(ValueError, match="more than once"):
        run(repo, [path, path], independent, output=repo / "data" / "second-stage")


def test_protocol_schema_bounds_private_output_and_overwrite_guards(repo):
    path = bundle(repo, "daily", [daily()])
    independent = market(repo)
    with pytest.raises(ValueError, match="Protocol has changed"):
        run(repo, [path], independent, config={**load_protocol(), "seed": 1})
    for options in ({"request_start": "2009-10-06"}, {"request_end": "2022-02-03"},
                    {"request_start": "2010-01-01", "request_end": "2009-10-09"}):
        with pytest.raises(ValueError, match="development source envelope"):
            run(repo, [path], independent, **options)
    with pytest.raises(ValueError, match="private directory"):
        run(repo, [path], independent, output=repo / "reports" / "public")
    run(repo, [path], independent)
    with pytest.raises(ValueError, match="output exists"):
        run(repo, [path], independent)
    change_receipt(path, lambda value: value.update(protocol_sha256="0" * 64))
    with pytest.raises(ValueError, match="frozen protocol"):
        run(repo, [path], independent, output=repo / "data" / "new-stage")


def test_cli_prints_only_aggregates_and_reports_failure_without_raw_exception_text(repo, monkeypatch, capsys):
    main = runpy.run_path(str(Path("scripts/wrds_manual_stage.py").resolve()))["main"]
    path = bundle(repo, "daily", [daily()])
    independent = market(repo)
    monkeypatch.chdir(repo)
    arguments = ["stage", "--daily-inventory", str(path), "--market-inventory", str(independent),
                 "--request-start", "2009-10-07", "--request-end", "2009-10-09",
                 "--output", "data/cli-stage"]
    assert main(arguments) == 0
    printed = capsys.readouterr().out
    assert "invented-security-secret" not in printed and "raw-stock-return-secret" not in printed
    assert "source_csv_record" not in printed and str(repo) not in printed
    assert json.loads(printed)["projection_rows"] == 1
    assert main(arguments) == 1
    failure = json.loads(capsys.readouterr().out)
    assert failure["status"] == "SOURCE_STAGE_FAILED" and failure["error_type"] == "ValueError"
    assert str(repo) not in json.dumps(failure)
