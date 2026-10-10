import csv
import gzip
import hashlib
import io
import json
import runpy
from pathlib import Path

import pytest

from disclosure_research import manual_wrds_market as market
from disclosure_research.protocol import load_protocol, write_lock


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "configs").mkdir()
    write_lock(load_protocol(), tmp_path / "configs" / "protocol.lock.json")
    return tmp_path


def source(repo, records, *, compressed=False, header=("dlycaldt", "vwretd")):
    content = io.StringIO(newline="")
    writer = csv.writer(content)
    writer.writerow(header)
    for day, value in records:
        values = {"dlycaldt": day, "vwretd": value}
        writer.writerow([values.get(field.lower(), "invented") for field in header])
    raw = content.getvalue().encode()
    path = repo / "invented-download.bin"
    path.write_bytes(gzip.compress(raw, mtime=0) if compressed else raw)
    return path


def inventory(repo, path, *, sql=None):
    return market.inventory_market(path, request_start="2009-10-07", request_end="2009-10-09",
                                   output=repo / "data" / "inventory", config=load_protocol(),
                                   repo_root=repo, sql_source=sql)


@pytest.mark.parametrize("compressed", [False, True])
def test_preserves_bytes_reordered_headers_early_rows_and_private_aggregates(repo, compressed):
    records = [("2009-07-10", "0.01234567890123456789"), ("2009-10-07", "0.002")]
    path = source(repo, records, compressed=compressed, header=("VWRETD", "DlyCalDt"))
    result = inventory(repo, path)
    saved = repo / "data" / "inventory" / result["source"]["preserved_file"]
    assert saved.read_bytes() == path.read_bytes()
    assert saved.stat().st_mode & 0o222 == 0
    assert result["source"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["source"]["observed_header"] == ["VWRETD", "DlyCalDt"]
    assert result["actual_coverage"]["rows_before_request"] == 1
    assert result["all_rows"]["rows"] == 2 and result["requested_slice"]["rows"] == 1
    assert result["requested_coverage"]["missing_xnys_sessions"] == ["2009-10-08", "2009-10-09"]
    assert "0.01234567890123456789" not in json.dumps(result)
    assert result["source"]["vendor_table"] is None
    assert result["source"]["independent_export_verified"] is False
    assert result["model_ready"] is False and result["source_approvals"] == 0
    assert result["prior_arithmetic_review_modified"] is False
    assert json.loads((saved.parent / "receipt.json").read_text()) == result
    assert not list(saved.parent.glob("market-inventory-*"))


def test_exact_duplicates_and_distinct_return_texts_are_separate(repo):
    path = source(repo, [("2009-10-07", "0.01"), ("2009-10-07", "0.01"),
                         ("2009-10-07", "0.010"), ("2009-10-08", "0.02")])
    counts = inventory(repo, path)["all_rows"]
    assert counts == {"rows": 4, "distinct_dates": 2, "dates_with_multiple_rows": 1,
                      "duplicate_date_row_excess": 2, "distinct_full_rows": 3,
                      "exact_full_duplicate_row_excess": 1, "dates_with_distinct_return_texts": 1,
                      "rows_on_dates_with_distinct_return_texts": 3,
                      "raw_text_conflicts_adjudicated": False}


def test_blank_malformed_nonfinite_and_below_minus_one_are_counted_without_filling(repo):
    values = ["", " ", "NA", ".A", "1_000", "https://example.invalid/session-secret",
              "NaN", "-Infinity", "1e999", "-1", "-1.000000000000000000000001", "0.25"]
    path = source(repo, [("2009-10-07", value) for value in values])
    result = inventory(repo, path)
    assert result["return_classifications"] == {
        "blank": 2, "malformed": 4, "nonfinite_numeric": 3, "finite_numeric": 3,
        "finite_numeric_below_minus_one": 1}
    assert result["requested_return_classifications"] == result["return_classifications"]
    assert "session-secret" not in json.dumps(result)
    assert result["values_filled"] == result["values_normalized"] == result["rows_dropped"] == 0


@pytest.mark.parametrize("day", ["2022-02-03", "2025-01-02", "2009-02-30", "", "2009-7-10"])
def test_every_date_is_validated_before_any_return_interpretation(repo, monkeypatch, day):
    path = source(repo, [("2009-10-07", "not-a-return"), (day, "secret-return")])
    monkeypatch.setattr(market, "_return_classification", lambda _: pytest.fail("Values opened too early"))
    with pytest.raises(ValueError):
        inventory(repo, path)
    assert not (repo / "data" / "inventory" / "receipt.json").exists()


def test_non_session_dates_are_preserved_and_counted(repo):
    path = source(repo, [("2009-10-10", "0.1"), ("2009-10-07", "0.2")])
    result = inventory(repo, path)
    assert result["actual_coverage"]["non_xnys_date_count"] == 1
    assert result["actual_coverage"]["non_xnys_row_count"] == 1
    assert result["actual_coverage"]["rows_after_request"] == 1
    assert result["all_rows"]["rows"] == 2


def test_pre_2008_dates_are_outside_calendar_coverage_not_declared_non_sessions(repo):
    path = source(repo, [("2007-10-08", "0.1"), ("2007-10-08", "0.1"),
                         ("2009-10-10", "0.2"), ("2009-10-07", "0.3")])
    result = inventory(repo, path)
    coverage = result["actual_coverage"]
    assert coverage["outside_calendar_date_count"] == 1
    assert coverage["outside_calendar_row_count"] == 2
    assert coverage["non_xnys_date_count"] == 1
    assert coverage["non_xnys_row_count"] == 1
    assert coverage["calendar_covered_session_start"] > "2007-10-08"
    assert result["all_rows"]["rows"] == 4
    assert result["requested_slice"]["rows"] == 1
    assert result["rows_dropped"] == 0


@pytest.mark.parametrize("header", [("dlycaldt",), ("dlycaldt", "vwretd", "VWRETD"),
                                    ("dlycaldt", "vwretd", "IndNo"), ("date", "return")])
def test_missing_ambiguous_or_unobserved_schema_refused(repo, header):
    path = source(repo, [("2009-10-07", "0.1")], header=header)
    with pytest.raises(ValueError, match="exactly|headers"):
        inventory(repo, path)


def test_malformed_rows_not_dropped(repo):
    path = source(repo, [("2009-10-07", "0.1")])
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="field count"):
        inventory(repo, path)


def test_optional_sql_preserved_but_source_identity_and_execution_remain_unknown(repo):
    sql = repo / "query-input.sql"
    sql.write_text("SELECT * FROM invented_secret_table; -- https://example.invalid/session-secret\n")
    result = inventory(repo, source(repo, [("2009-10-07", "0.1")]), sql=sql)
    assert (repo / "data" / "inventory" / "query.sql").read_bytes() == sql.read_bytes()
    assert result["sql"]["sha256"] == hashlib.sha256(sql.read_bytes()).hexdigest()
    assert result["sql"]["status"] == "preserved_without_semantic_interpretation"
    assert result["sql"]["vendor_source_identifier"] is None
    assert result["sql"]["sql_executed"] is False
    assert "session-secret" not in json.dumps(result) and "invented_secret_table" not in json.dumps(result)


def test_missing_optional_sql_does_not_block_market_preservation(repo):
    result = inventory(repo, source(repo, [("2009-10-07", "0.1")]), sql=repo / "absent.sql")
    assert result["sql"]["status"] == "unavailable_or_copy_integrity_failed"
    assert result["all_rows"]["rows"] == 1


def test_snapshot_mutation_after_date_pass_refused_before_values(repo, monkeypatch):
    path = source(repo, [("2009-10-07", "0.1")])
    original = market._date_pass

    def mutate(snapshot, db, last):
        result = original(snapshot, db, last)
        snapshot.chmod(0o600)
        snapshot.write_bytes(snapshot.read_bytes().replace(b"0.1", b"0.2"))
        return result

    monkeypatch.setattr(market, "_date_pass", mutate)
    monkeypatch.setattr(market, "_return_classification", lambda _: pytest.fail("Must guard before numbers"))
    with pytest.raises(ValueError, match="snapshot changed"):
        inventory(repo, path)


def test_protocol_lock_private_directory_request_bounds_and_overwrite(repo):
    arguments = dict(request_start="2009-10-07", request_end="2022-02-02",
                     output=repo / "data" / "inventory", config=load_protocol(), repo_root=repo)
    with pytest.raises(ValueError, match="Protocol has changed"):
        market.inventory_market(repo / "absent", **{**arguments, "config": {**load_protocol(), "seed": 1}})
    with pytest.raises(ValueError, match="source envelope"):
        market.inventory_market(repo / "absent", **{**arguments, "request_end": "2022-02-03"})
    with pytest.raises(ValueError, match="private directory"):
        market.inventory_market(repo / "absent", **{**arguments, "output": repo / "reports" / "unsafe"})
    path = source(repo, [("2009-10-07", "0.1")])
    inventory(repo, path)
    with pytest.raises(ValueError, match="output exists"):
        inventory(repo, path)


def test_disk_duplicate_accumulation_across_tiny_batches(repo, monkeypatch):
    monkeypatch.setattr(market, "_BATCH", 2)
    monkeypatch.setattr(market, "_MAX_BATCH_BYTES", 1)
    path = source(repo, [("2009-10-07", "0.1")] * 5)
    assert inventory(repo, path)["all_rows"]["exact_full_duplicate_row_excess"] == 4


def test_cli_help_is_offline(capsys):
    main = runpy.run_path(str(Path("scripts/wrds_manual_market.py")))["main"]
    with pytest.raises(SystemExit) as code:
        main(["inventory", "--help"])
    assert code.value.code == 0
    output = capsys.readouterr().out
    assert "--sql" in output and "--request-start" in output and "--source" in output
