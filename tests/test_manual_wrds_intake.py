import csv
import gzip
import hashlib
import io
import json
import runpy
from pathlib import Path

import pytest

from disclosure_research import manual_wrds_intake as intake
from disclosure_research.protocol import load_protocol


def row(day="2009-10-07", permno="10001", **changes):
    result = dict(zip(intake.DAILY_FIELDS, [
        permno, "20001", "01234567", "INVENTED", day, "20.5", "3000", "T",
        "0.01", "NA", "N", "123.4", "0.005",
    ], strict=True))
    result.update(changes)
    return result


def source(tmp_path, rows, *, compressed=False, header=None):
    header = header or list(intake.DAILY_FIELDS)
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(header)
    for record in rows:
        writer.writerow([record[column.lower()] for column in header])
    content = text.getvalue().encode()
    path = tmp_path / ("invented.csv.gz" if compressed else "invented.csv")
    path.write_bytes(gzip.compress(content, mtime=0) if compressed else content)
    return path


def run(tmp_path, path, **options):
    return intake.inventory_daily(path, config=load_protocol(), repo_root=tmp_path,
                                  output=tmp_path / "data" / "inventory",
                                  request_start="2009-10-07", request_end="2009-10-09", **options)


@pytest.mark.parametrize("compressed", [False, True])
def test_preserves_bytes_and_extra_early_rows_with_case_and_column_order(tmp_path, compressed):
    path = source(tmp_path, [row("2009-07-10"), row(), row("2009-10-08")],
                  compressed=compressed, header=[field.upper() for field in reversed(intake.DAILY_FIELDS)])
    receipt = run(tmp_path, path)
    saved = tmp_path / "data" / "inventory" / receipt["source"]["preserved_file"]
    assert saved.read_bytes() == path.read_bytes()
    assert receipt["source"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert receipt["actual_coverage"]["first_date"] == "2009-07-10"
    assert receipt["actual_coverage"]["rows_before_request"] == 1
    assert receipt["requested_slice"]["rows"] == 2
    assert receipt["requested_coverage"]["missing_xnys_sessions"] == ["2009-10-09"]
    assert receipt["source"]["vendor_query_submitted_at"] is None
    assert receipt["source"]["source_release"] is None
    assert receipt["human_approvals"] == 0 and receipt["model_ready"] is False
    assert json.loads((saved.parent / "receipt.json").read_text()) == receipt
    assert sorted(item.name for item in saved.parent.iterdir()) == sorted([saved.name, "receipt.json"])


def test_counts_duplicate_full_rows_and_conflicting_key_variants(tmp_path):
    path = source(tmp_path, [row(), row(), row(dlyret="0.02"), row("2009-10-08"),
                             row("2009-10-08"), row("2009-10-09", "10002")])
    counts = run(tmp_path, path)["all_rows"]
    assert counts == {"rows": 6, "distinct_security_identifiers": 2,
                      "distinct_security_date_keys": 3, "duplicate_security_date_keys": 2,
                      "duplicate_security_date_row_excess": 3, "distinct_full_projected_rows": 4,
                      "exact_full_projected_duplicate_row_excess": 2,
                      "conflicting_security_date_keys": 1, "rows_in_conflicting_security_date_keys": 3,
                      "conflicting_projection_excess": 1}


@pytest.mark.parametrize("day", ["2022-02-03", "2025-01-02", "2009-02-30", "", "2009-7-10"])
def test_all_dates_checked_before_any_numeric_value(tmp_path, monkeypatch, day):
    path = source(tmp_path, [row(dlyret="not a number"), row(day)])

    def forbidden(_):
        raise AssertionError("Numeric interpretation must not happen before every date is validated")

    monkeypatch.setattr(intake, "_numeric_kind", forbidden)
    with pytest.raises(ValueError):
        run(tmp_path, path)
    assert not (tmp_path / "data" / "inventory" / "receipt.json").exists()


def test_numeric_and_flag_inventory_preserves_missing_nonfinite_and_special_codes(tmp_path):
    path = source(tmp_path, [row(dlyret="", dlyretmissflg="NT"),
                             row("2009-10-08", dlyret="0.0001", dlyretmissflg="MP"),
                             row("2009-10-09", dlyret="NaN", dlyretmissflg="GP"),
                             row("2009-10-09", "10002", dlyret=".A", dlyretmissflg="unknown")])
    result = run(tmp_path, path)
    assert result["columns"]["dlyret"] == {
        "blank": 1, "finite_numeric": 1, "nonfinite_numeric": 1, "non_numeric": 1}
    assert result["flags"]["dlyretmissflg"]["source_code_counts"] == {
        "GP": 1, "MP": 1, "NT": 1, "unknown": 1}
    assert result["source_flags_interpreted"] is False
    assert result["values_normalized"] == result["values_filled"] == result["rows_dropped"] == 0


def test_arbitrary_flag_text_is_counted_without_echoing_it(tmp_path):
    path = source(tmp_path, [row(dlyretmissflg="https://example.invalid/session-secret")])
    result = run(tmp_path, path)
    assert "session-secret" not in json.dumps(result)
    assert result["flags"]["dlyretmissflg"]["rows_with_unreported_code_text"] == 1


@pytest.mark.parametrize("header", [list(intake.DAILY_FIELDS)[:-1],
                                    [*intake.DAILY_FIELDS, "PERMNO"],
                                    [*intake.DAILY_FIELDS, "extra"]])
def test_rejects_missing_extra_or_ambiguous_headers(tmp_path, header):
    path = tmp_path / "bad.csv"
    path.write_text(",".join(header) + "\n")
    with pytest.raises(ValueError, match="fields|headers"):
        run(tmp_path, path)


def test_malformed_and_blank_records_are_not_silently_dropped(tmp_path):
    path = source(tmp_path, [row()])
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="field count"):
        run(tmp_path, path)


def test_snapshot_mutation_after_date_pass_is_caught_before_numbers(tmp_path, monkeypatch):
    path = source(tmp_path, [row()])
    original_pass = intake._date_pass

    def mutate(snapshot, db, last, **kwargs):
        result = original_pass(snapshot, db, last, **kwargs)
        snapshot.chmod(0o600)
        snapshot.write_bytes(snapshot.read_bytes().replace(b"0.01", b"0.02"))
        return result

    monkeypatch.setattr(intake, "_date_pass", mutate)
    monkeypatch.setattr(intake, "_numeric_kind", lambda _: pytest.fail("Must guard before numbers"))
    with pytest.raises(ValueError, match="snapshot changed"):
        run(tmp_path, path)


def test_source_change_during_copy_prevents_receipt(tmp_path, monkeypatch):
    path = source(tmp_path, [row()])
    original_identity = intake._identity
    calls = 0

    def changed_identity(candidate):
        nonlocal calls
        result = original_identity(candidate)
        if candidate == path:
            calls += 1
            if calls == 2:
                return (*result[:-1], result[-1] + 1)
        return result

    monkeypatch.setattr(intake, "_identity", changed_identity)
    with pytest.raises(ValueError, match="changed during"):
        run(tmp_path, path)
    assert not (tmp_path / "data" / "inventory" / "receipt.json").exists()


def test_overwrite_and_public_output_are_refused(tmp_path):
    path = source(tmp_path, [row()])
    run(tmp_path, path)
    with pytest.raises(ValueError, match="output exists"):
        run(tmp_path, path)
    with pytest.raises(ValueError, match="private directory"):
        intake.inventory_daily(path, config=load_protocol(), repo_root=tmp_path,
                               request_start="2009-10-07", request_end="2009-10-09",
                               output=tmp_path / "reports" / "unsafe")


def test_future_request_refused_before_source_open(tmp_path):
    with pytest.raises(ValueError, match="development return window"):
        intake.inventory_daily(tmp_path / "does-not-exist.csv", config=load_protocol(),
                               repo_root=tmp_path, request_start="2022-01-01", request_end="2022-12-31",
                               output=tmp_path / "data" / "blocked")
    assert not (tmp_path / "data").exists()


def test_batches_and_disk_uniqueness(tmp_path, monkeypatch):
    monkeypatch.setattr(intake, "_BATCH", 2)
    path = source(tmp_path, [row(), row(), row(), row("2009-10-08"), row("2009-10-08")])
    result = run(tmp_path, path)
    assert result["all_rows"]["exact_full_projected_duplicate_row_excess"] == 3
    assert result["flags"]["dlyretmissflg"]["source_code_counts"] == {"NA": 5}


def test_cli_help_is_offline_and_contains_required_interface(capsys):
    main = runpy.run_path(str(Path("scripts/wrds_manual_inventory.py")))["main"]
    with pytest.raises(SystemExit) as status:
        main(["manualdaily", "inventory", "--help"])
    assert status.value.code == 0
    output = capsys.readouterr().out
    assert "--request-start" in output and "--request-end" in output and "--source" in output
    assert "--allow-extra-columns" in output


@pytest.mark.parametrize("compressed", [False, True])
def test_explicit_extra_columns_preserves_all_96_fields_but_only_compares_required_projection(tmp_path, compressed):
    extras = {f"extra_{index}": f"private value {index}" for index in range(83)}
    first = row(**extras)
    second = {**first, "extra_0": "distinct private source text"}
    header = ["EXTRA_0", *[field.upper() for field in reversed(intake.DAILY_FIELDS)],
              *[field.upper() for field in extras if field != "extra_0"]]
    path = source(tmp_path, [first, second], compressed=compressed, header=header)
    result = run(tmp_path, path, allow_extra_columns=True)
    saved = tmp_path / "data" / "inventory" / result["source"]["preserved_file"]
    assert saved.read_bytes() == path.read_bytes()
    assert result["source"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["source"]["observed_header"] == header
    assert result["source"]["delivered_column_count"] == 96
    assert result["projection"]["fields"] == list(intake.DAILY_FIELDS)
    assert result["projection"]["column_count"] == 13
    assert len(result["projection"]["extra_columns"]) == 83
    assert result["projection"]["extra_columns"][0] == "EXTRA_0"
    assert result["projection"]["all_delivered_columns_preserved"] is True
    assert result["projection"]["extra_column_values_interpreted"] is False
    assert result["full_delivered_row_duplicates_checked"] is False
    assert result["all_rows"]["rows"] == 2
    assert result["all_rows"]["exact_full_projected_duplicate_row_excess"] == 1
    assert result["all_rows"]["conflicting_security_date_keys"] == 0
    assert result["rows_dropped"] == result["values_normalized"] == 0
    assert "distinct private source text" not in json.dumps(result)


def test_extra_columns_do_not_hide_required_field_conflicts(tmp_path):
    path = source(tmp_path, [row(extra="one"), row(dlyret="0.02", extra="two")],
                  header=[*intake.DAILY_FIELDS, "extra"])
    result = run(tmp_path, path, allow_extra_columns=True)
    assert result["all_rows"]["conflicting_security_date_keys"] == 1
    assert result["all_rows"]["exact_full_projected_duplicate_row_excess"] == 0


def test_extra_columns_require_opt_in_and_cannot_replace_required_fields(tmp_path):
    path = source(tmp_path, [row(extra="private")], header=[*intake.DAILY_FIELDS, "extra"])
    with pytest.raises(ValueError, match="allow-extra-columns"):
        run(tmp_path, path)
    other = tmp_path / "other"
    other.mkdir()
    path = source(other, [row(extra="private")], header=[*intake.DAILY_FIELDS[:-1], "extra"])
    with pytest.raises(ValueError, match="all 13"):
        run(other, path, allow_extra_columns=True)


@pytest.mark.parametrize("extra_headers", [["PERMNO"], ["unsafe header"], ["https://example.invalid/token"],
                                           ["x" * 129], [f"extra_{i}" for i in range(244)]])
def test_opt_in_still_rejects_duplicate_unsafe_and_excessive_headers(tmp_path, extra_headers):
    path = tmp_path / "bad.csv"
    path.write_text(",".join([*intake.DAILY_FIELDS, *extra_headers]) + "\n")
    with pytest.raises(ValueError, match="headers|field names"):
        run(tmp_path, path, allow_extra_columns=True)


def test_extra_columns_still_require_complete_date_pass_before_numeric_interpretation(tmp_path, monkeypatch):
    path = source(tmp_path, [row(extra="private"), row("2022-02-03", extra="private")],
                  header=[*intake.DAILY_FIELDS, "extra"])
    monkeypatch.setattr(intake, "_numeric_kind", lambda _: pytest.fail("Cannot interpret values before date guard"))
    with pytest.raises(ValueError, match="holdout blocked"):
        run(tmp_path, path, allow_extra_columns=True)


def test_strict_13_fields_report_full_delivered_row_comparison(tmp_path):
    result = run(tmp_path, source(tmp_path, [row()]))
    assert result["full_delivered_row_duplicates_checked"] is True
    assert result["projection"]["extra_columns"] == []
    assert result["projection"]["allow_extra_columns"] is False


def test_extra_column_option_requires_a_boolean_before_source_open(tmp_path):
    with pytest.raises(ValueError, match="explicit boolean"):
        run(tmp_path, tmp_path / "missing.csv", allow_extra_columns="yes")
