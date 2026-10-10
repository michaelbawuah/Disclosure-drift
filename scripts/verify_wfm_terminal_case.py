"""Verify the delivered WFM cash-merger case; do not add it to the study sample.

Public output is aggregate QA. Detailed arithmetic stays under ignored data/.
Artificial event clocks exercise the label engine with actual development returns;
they are not SEC filing observations or evidence of forecasting performance.
"""

import argparse
import csv
import io
import json
import math
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from disclosure_research.crsp_staging import inspect_daily
from disclosure_research.market import make_label
from disclosure_research.market_data import sha256
from disclosure_research.protocol import canonical_hash, load_protocol, verify_lock
from disclosure_research.timing import NY, event_window

SOURCES = {
    "crsp_delisting_check.csv":
        "5e8f8d3c721e6212410c545de90e37a16423b698ab10e746c2a3851da0c4b760",
    "crsp_delisting_check_permno.csv":
        "d1a6f564a75fecf20d5d041d95057dcac92f5b582d47e09580947287e015535a",
    "crsp_daily_pilot.csv":
        "884faf245e5b03bffcd1217a3be802dff91433319de05494da9ce6beac67d0d6",
}
PRIMARY_SOURCES = {
    "cash_merger": "https://www.sec.gov/Archives/edgar/data/865436/"
                   "000114420417045261/v474128_8k.htm",
    "price_flags": "https://www.crsp.org/wp-content/uploads/appendix/FlagType_PC.html",
    "date_convention": "https://www.crsp.org/wp-content/uploads/appendix/FlagType_MU.html",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def compound(values) -> Decimal:
    result = Decimal(1)
    for value in values:
        result *= 1 + Decimal(value)
    return result - 1


def verify(root: Path, output: Path) -> dict:
    require(not output.exists(), "Output already exists; preserve the prior QA run")
    config = load_protocol(root / "configs/protocol.json")
    verify_lock(config, root / "configs/protocol.lock.json")
    directory = root / "data/raw/wrds/2026-10-10"
    frames, inputs = {}, {}
    for name, expected_hash in SOURCES.items():
        source = directory / name
        raw = source.read_bytes()
        require(sha256(raw) == expected_hash, f"Received source changed: {name}")
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        require(all(row["DlyCalDt"][:4] <= str(config["development_end"]) for row in rows),
                "Source dates exceed development; no returns inspected")
        frames[name] = rows
        inputs[name] = {"sha256": expected_hash, "bytes": len(raw), "rows": len(rows)}
    old, new, pilot = (frames[name] for name in SOURCES)
    require(len(new) == 11 and new[:-1] == old, "Original rows changed or terminal row absent")
    terminal = new[-1]
    require(all(row["PERMNO"] == "77281" and row["PERMCO"] == "11310" and
                row["HdrCUSIP"] == "96683710" for row in new), "Source identity changed")
    require(all(row["Ticker"] == "WFM" and row["DlyDelFlg"] == "N" and
                row["DlyPrcFlg"] == "TR" for row in old), "Original flags changed")
    require(terminal["DlyCalDt"] == "2017-08-28" and terminal["DlyDelFlg"] == "Y" and
            terminal["DlyPrcFlg"] == "DA" and terminal["Ticker"] == "" and
            terminal["DlyCap"] == "" and Decimal(terminal["DlyPrc"]) == 0,
            "Expected blank-ticker, missing-capitalization DA terminal row not found")
    require(terminal["DlyPrevPrc"] == old[-1]["DlyPrc"], "Prior-price continuity failed")

    # Cash consideration comes from Item 2.01 of the SEC source, independently of DlyRet.
    cash_payoff = Decimal("42.00")
    expected_terminal = cash_payoff / Decimal(terminal["DlyPrevPrc"]) - 1
    terminal_error = abs(expected_terminal - Decimal(terminal["DlyRet"]))
    precision = Decimal("0.0000005")
    require(terminal_error <= precision, "Terminal return disagrees with external cash payoff")
    ordinary_error = max(abs(Decimal(row["DlyPrc"]) / Decimal(row["DlyPrevPrc"]) - 1 -
                             Decimal(row["DlyRet"])) for row in old)
    require(ordinary_error <= precision, "Ordinary price arithmetic exceeds delivered precision")

    benchmark = {}
    for row in pilot:
        session, value = row["DlyCalDt"], row["vwretd"]
        require(session not in benchmark or benchmark[session] == value,
                "Pilot benchmark conflicts across securities")
        benchmark[session] = value
    require(all(benchmark.get(row["DlyCalDt"]) == row["vwretd"] for row in new),
            "WFM benchmark differs from the pilot")
    benchmark_frame = pd.DataFrame({"session": list(benchmark),
                                    "total_return": [float(v) for v in benchmark.values()]})
    tables, coverage, _ = inspect_daily(directory / "crsp_delisting_check_permno.csv",
                                        config, "2017-08-14", "2017-09-08")
    old_tables, old_coverage, _ = inspect_daily(directory / "crsp_delisting_check.csv",
                                               config, "2017-08-14", "2017-09-08")
    require(coverage["terminal_rows"] == 1 and coverage["missing_security_sessions"] == 0,
            "Incomplete source coverage through terminal event")
    require(old_coverage["terminal_rows"] == 0 and old_coverage["missing_security_sessions"] == 9,
            "Original incomplete export no longer reproduces")
    stock = tables["daily_returns"]
    require(stock.total_return.tolist() == [float(row["DlyRet"]) for row in new],
            "Normalizer changed delivered returns")
    require(stock.terminal_event.tolist() == [False] * 10 + [True], "Terminal flag changed")
    require(pd.isna(tables["capitalizations"].market_cap_usd.iloc[-1]) and
            not tables["capitalizations"].valid_market_cap.iloc[-1],
            "Missing terminal capitalization became a valid size observation")

    by_session = {row["DlyCalDt"]: row for row in new}
    traces, public_cases = [], []
    for name, accepted, reference, cash_sessions in [
        ("ordinary_plus_terminal", "2017-08-10T12:00:00", "2017-08-14", 10),
        ("terminal_only", "2017-08-23T12:00:00", "2017-08-25", 19),
    ]:
        window = event_window(datetime.fromisoformat(accepted).replace(tzinfo=NY))
        require(window.reference_session == reference and len(window.return_sessions) == 20,
                "QA clock/calendar changed")
        require(sum(s > terminal["DlyCalDt"] for s in window.return_sessions) == cash_sessions,
                "Unexpected cash continuation length")
        expected_stock = compound(by_session[s]["DlyRet"] for s in window.return_sessions
                                  if s <= terminal["DlyCalDt"])
        expected_market = compound(benchmark[s] for s in window.return_sessions)
        result = make_label(stock, benchmark_frame, window)
        for key, expected in [("stock_return", expected_stock),
                              ("market_return", expected_market),
                              ("target", expected_stock - expected_market)]:
            require(math.isclose(result[key], float(expected), rel_tol=0, abs_tol=1e-12),
                    f"Independent Decimal reconciliation failed: {name}/{key}")
        try:
            make_label(old_tables["daily_returns"], benchmark_frame, window)
        except ValueError as exc:
            require("Missing stock session 2017-08-28" in str(exc),
                    "Original file failed for an unexpected reason")
        else:
            raise ValueError("Original export falsely passed without terminal evidence")
        traces.append({"case": name, "clock_kind": "artificial QA clock; no real SEC event",
                       "acceptance_timestamp": accepted + "-04:00", "result": result,
                       "independent_stock_return": str(expected_stock),
                       "independent_market_return": str(expected_market),
                       "cash_continuation_sessions": cash_sessions})
        public_cases.append({"case": name, "horizon_sessions": 20,
                             "cash_continuation_sessions": cash_sessions,
                             "decimal_reconciliation_passed": True,
                             "old_export_rejected_for_missing_terminal": True})
    private = {"data_kind": "REAL_SOURCE_QA_NOT_FILING_LABELS", "traces": traces,
               "terminal_row": terminal, "cash_consideration_usd": str(cash_payoff),
               "expected_terminal_return": str(expected_terminal),
               "terminal_abs_rounding_error": str(terminal_error)}
    private_bytes = (json.dumps(private, indent=2) + "\n").encode()
    summary = {
        "case": "Whole Foods cash merger; actual development-source terminal QA",
        "status": "automated_terminal_case_passed", "inputs": inputs,
        "original_rows_unchanged": 10, "added_terminal_rows": 1,
        "terminal_session": terminal["DlyCalDt"], "terminal_ticker_blank": True,
        "terminal_price_flag": "DA", "zero_price_not_used_as_payoff": True,
        "terminal_capitalization_retained_missing": True,
        "return_rounding_tolerance": str(precision),
        "ordinary_price_arithmetic_max_abs_error": str(ordinary_error),
        "terminal_cash_arithmetic_abs_error": str(terminal_error),
        "terminal_cash_arithmetic_verified": True, "benchmark_rows_matching_pilot": 11,
        "missing_security_sessions_through_terminal": coverage["missing_security_sessions"],
        "benchmark_tail_missing_from_wfm_export": coverage["missing_benchmark_sessions"],
        "benchmark_tail_source": "crsp_daily_pilot.csv; no benchmark forward fill",
        "delivered_returns_unchanged": True, "legacy_dlret_added": False,
        "qa_cases": public_cases, "source_references": PRIMARY_SOURCES,
        "source_interpretation": "assistant-reviewed; external cash amount is a QA comparator, "
                                 "not an imputed or replacement return",
        "query_metadata": "Original ticker query documented separately; PERMNO query "
                          "ID/SQL and exact vendor release remain unverified",
        "private_trace_sha256": sha256(private_bytes),
        "verification_script_sha256": sha256(Path(__file__).read_bytes()),
        "normalization_code_sha256": sha256((root / "src/disclosure_research/crsp_staging.py")
                                             .read_bytes()),
        "label_code_sha256": sha256((root / "src/disclosure_research/market.py").read_bytes()),
        "protocol_sha256": canonical_hash(config), "human_reviews_completed": 0,
        "research_sample_extended": False, "actual_filing_labels_generated": False,
        "historical_cik_mapping_approved": False, "model_ready": False,
        "final_period_opened": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        staging = Path(temporary) / "case"
        staging.mkdir()
        (staging / "qa_trace.json").write_bytes(private_bytes)
        (staging / "qa_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        require(not output.exists(), "Output appeared during verification; preserving it")
        staging.rename(output)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/reviews/wfm-terminal-v1"))
    args = parser.parse_args()
    print(json.dumps(verify(Path("."), args.output), indent=2))
