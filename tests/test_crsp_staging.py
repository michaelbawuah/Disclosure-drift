"""Invented CSVs exercise the vendor boundary; no licensed source rows in tests."""

import csv
import json

import duckdb
import numpy as np
import pandas as pd
import pytest

from disclosure_research.cli import main
from disclosure_research.crsp_staging import DAILY_FIELDS, inspect_daily, stage_crsp
from disclosure_research.market import make_label
from disclosure_research.market_data import sha256, validate_manifest
from disclosure_research.protocol import load_protocol
from disclosure_research.timing import EventWindow


def write_csv(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def source(tmp_path):
    daily = tmp_path / "invented_daily.csv"
    names = tmp_path / "invented_names.csv"
    rows = []
    for session, value in [("2021-01-04", "0.01"), ("2021-01-05", "0.02"),
                           ("2021-01-06", "-0.50")]:
        rows.append(dict(zip(DAILY_FIELDS, ["10001", "12345678", "FAKE", "20001", session,
                                           "Y" if session == "2021-01-06" else "N",
                                           "" if session == "2021-01-06" else "125.5",
                                           value, "NA", "0.001"], strict=True)))
    write_csv(daily, rows)
    histories = [
        {"permno": "10001", "permco": "20001", "secinfostartdt": "2020-01-01",
         "secinfoenddt": "2021-01-04", "siccd": "1234", "hdrsiccd": "9999"},
        {"permno": "10001", "permco": "20001", "secinfostartdt": "2021-01-05",
         "secinfoenddt": "2025-12-31", "siccd": "5678", "hdrsiccd": "9999"},
    ]
    write_csv(names, histories)
    return daily, names, tmp_path / "staged", load_protocol(), rows, histories


def stage(source):
    daily, names, output, config, _, _ = source
    return stage_crsp(daily, names, output, config, "2021-01-04", "2021-01-08")


def test_staging_preserves_source_and_keeps_unapproved_provenance(source):
    daily, names, output, _, _, _ = source
    before = daily.read_bytes(), names.read_bytes()
    receipt = stage(source)
    assert before == (daily.read_bytes(), names.read_bytes())
    assert [x["sha256"] for x in receipt["raw_exports"]] == [sha256(x) for x in before]
    assert receipt["raw_exports"][0]["source_table"] is None
    assert receipt["source_release"] is None and receipt["source_export_timestamp"] is None
    assert not receipt["import_ready"] and not receipt["model_ready"]
    assert not receipt["terminal_handling_verified"]  # even a Y row is not independent proof
    assert receipt["coverage"]["missing_security_sessions"] == 0
    assert receipt["coverage"]["missing_benchmark_sessions"] == 2
    assert not (output / "source_manifest.json").exists()
    with pytest.raises(ValueError, match="data kind"):
        validate_manifest(receipt)
    with duckdb.connect(str(output / "staging.duckdb"), read_only=True) as con:
        assert con.sql("SELECT count(*) FROM daily_returns").fetchone()[0] == 3
        assert con.sql("SELECT count(*) FROM market_returns").fetchone()[0] == 3
        assert con.sql("SELECT count(*) FROM security_snapshots").fetchone()[0] == 3
    frame = pd.read_parquet(output / "daily_returns.parquet")
    assert frame.source_return_missing_flag.tolist() == ["NA"] * 3
    assert frame.source_csv_row.tolist() == [2, 3, 4]


def test_units_and_inclusive_historical_industry_boundaries(source):
    stage(source)
    snapshots = pd.read_parquet(source[2] / "security_snapshots.parquet")
    assert snapshots.market_cap_usd.iloc[0] == 125500.0
    assert snapshots.industry.tolist() == ["1234", "5678", "5678"]
    assert pd.isna(snapshots.market_cap_usd.iloc[-1])
    assert not snapshots.valid_market_cap.iloc[-1]


def test_terminal_return_used_once_and_cash_stays_flat(source):
    daily, _, _, config, _, _ = source
    tables, _, _ = inspect_daily(daily, config, "2021-01-04", "2021-01-08")
    window = EventWindow("2020-12-30", "2021-01-04", "2021-01-04T14:30:00+00:00",
                         "2020-12-31", "2021-01-07", ("2021-01-05", "2021-01-06", "2021-01-07"))
    benchmark = pd.DataFrame({"session": list(window.return_sessions), "total_return": [0.0] * 3})
    result = make_label(tables["daily_returns"], benchmark, window)
    assert result["stock_return"] == pytest.approx(-0.49)
    assert tables["daily_returns"].total_return.iloc[-1] == -0.5


def test_absent_terminal_row_reports_tail_gap_without_inventing_payoff(source):
    daily, _, _, config, rows, _ = source
    write_csv(daily, rows[:-1])
    tables, summary, _ = inspect_daily(daily, config, "2021-01-04", "2021-01-08")
    assert summary["terminal_rows"] == 0 and summary["missing_security_sessions"] == 3
    assert summary["coverage"][0]["first_missing_session"] == "2021-01-06"
    assert len(tables["daily_returns"]) == 2
    assert not summary["terminal_handling_verified"]


def test_blank_ticker_and_zero_da_price_preserve_cash_return(source):
    daily, _, _, config, rows, _ = source
    for row in rows:
        row.update(DlyPrc="25", DlyPrevPrc="25", DlyPrcFlg="TR")
    # Invented cash consideration is 26 on a prior value of 25. DA is not a zero payoff.
    rows[-1].update(Ticker="", DlyPrc="0", DlyPrcFlg="DA", DlyRet="0.04", DlyCap="")
    write_csv(daily, rows)
    tables, summary, _ = inspect_daily(daily, config, "2021-01-04", "2021-01-08")
    assert summary["terminal_rows"] == 1 and summary["missing_security_sessions"] == 0
    assert tables["daily_returns"].total_return.iloc[-1] == pytest.approx(26 / 25 - 1)
    assert pd.isna(tables["capitalizations"].market_cap_usd.iloc[-1])
    assert not tables["capitalizations"].valid_market_cap.iloc[-1]
    window = EventWindow("2020-12-30", "2021-01-04", "2021-01-04T14:30:00+00:00",
                         "2020-12-31", "2021-01-08",
                         ("2021-01-05", "2021-01-06", "2021-01-07", "2021-01-08"))
    benchmark = pd.DataFrame({"session": list(window.return_sessions), "total_return": [0.0] * 4})
    label = make_label(tables["daily_returns"], benchmark, window)
    assert label["stock_return"] == pytest.approx(1.02 * (26 / 25) - 1)


@pytest.mark.parametrize("field,value,pattern", [
    ("DlyRetMissFlg", "MP", "Unresolved"), ("DlyRetMissFlg", "", "Unresolved"),
    ("DlyDelFlg", "X", "Unsupported"), ("DlyRet", "", "finite"),
    ("DlyRet", "-1.01", "at least"), ("DlyRet", "inf", "finite"),
    ("vwretd", "nan", "numeric"), ("DlyCap", "-5", "at least"),
    ("PERMNO", "10001.0", "identifiers"), ("DlyCalDt", "2021-01-09", "non-XNYS"),
])
def test_invalid_fields_refused_without_publishing(source, field, value, pattern):
    daily, _, output, _, rows, _ = source
    rows[0][field] = value
    write_csv(daily, rows)
    with pytest.raises(ValueError, match=pattern):
        stage(source)
    assert not output.exists()


def test_holdout_guard_precedes_return_parsing(source):
    daily, _, _, config, rows, _ = source
    rows[0].update(DlyCalDt="2023-01-03", DlyRet="not-a-return", DlyDelFlg="INVALID")
    write_csv(daily, rows)
    with pytest.raises(ValueError, match="holdout blocked"):
        inspect_daily(daily, config, "2021-01-04", "2023-01-04")


@pytest.mark.parametrize("case,pattern", [
    ("duplicate", "Duplicate"), ("benchmark", "Conflicting"),
    ("post_terminal", "post-terminal"), ("overlap", "Overlapping"),
    ("names_gap", "Missing dated"), ("permco", "PERMCO mismatch"),
    ("names_absent", "Missing Names"), ("names_reversed", "Reversed"),
])
def test_relational_integrity(source, case, pattern):
    daily, names, _, _, rows, histories = source
    if case == "duplicate":
        rows.append(rows[0].copy())
    elif case == "benchmark":
        rows.append({**rows[0], "PERMNO": "10002", "vwretd": "0.002"})
    elif case == "post_terminal":
        rows[0]["DlyDelFlg"] = "Y"
    elif case == "overlap":
        histories[1]["secinfostartdt"] = "2021-01-04"
    elif case == "names_gap":
        histories[1]["secinfostartdt"] = "2021-01-06"
    elif case == "permco":
        histories[1]["permco"] = "30001"
    elif case == "names_absent":
        for h in histories:
            h["permno"] = "10002"
    else:
        histories[1]["secinfoenddt"] = "2020-12-31"
    write_csv(daily, rows)
    write_csv(names, histories)
    with pytest.raises(ValueError, match=pattern):
        stage(source)


def test_consistent_benchmark_duplicates_are_collapsed(source):
    daily, _, _, config, rows, _ = source
    write_csv(daily, rows + [{**r, "PERMNO": "10002"} for r in rows])
    tables, summary, _ = inspect_daily(daily, config, "2021-01-04", "2021-01-08")
    assert len(tables["daily_returns"]) == 6 and len(tables["market_returns"]) == 3
    assert summary["terminal_rows"] == 2


@pytest.mark.parametrize("zero", ["0", ""])
def test_bad_size_snapshot_is_flagged_not_filled(source, zero):
    daily, _, _, config, rows, _ = source
    rows[0]["DlyCap"] = zero
    write_csv(daily, rows)
    tables, summary, _ = inspect_daily(daily, config, "2021-01-04", "2021-01-08")
    assert summary["invalid_or_missing_capitalizations"] == 2
    assert not tables["capitalizations"].valid_market_cap.iloc[0]
    if zero == "":
        assert np.isnan(tables["capitalizations"].market_cap_usd.iloc[0])


def test_existing_staging_is_preserved_and_cli_writes_receipt(source):
    daily, names, output, _, _, _ = source
    assert main(["stage-crsp", "--daily", str(daily), "--names", str(names),
                 "--request-start", "2021-01-04", "--request-end", "2021-01-08",
                 "--output", str(output)]) == 0
    original = (output / "staging_receipt.json").read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        stage(source)
    assert (output / "staging_receipt.json").read_bytes() == original
    assert json.loads(original)["human_reviews_completed"] == 0
