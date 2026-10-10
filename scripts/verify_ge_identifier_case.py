"""Recheck GE's 2021 CUSIP transition against the received, private pilot data.

This is source/staging QA, not a split-return calculation or CIK-link approval.
Print aggregate evidence only; never publish vendor observations.
"""

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from disclosure_research.protocol import canonical_hash, load_protocol, verify_lock
from disclosure_research.timing import calendar


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify(root: Path = Path(".")) -> dict:
    config = load_protocol(root / "configs/protocol.json")
    verify_lock(config, root / "configs/protocol.lock.json")
    start, end, transition = "2021-07-26", "2021-08-06", "2021-08-02"
    require(int(end[:4]) <= config["development_end"], "Case exceeds development period")
    paths = {
        "names": root / "data/raw/wrds/2026-10-09/crsp_names_pilot.csv",
        "daily": root / "data/raw/wrds/2026-10-10/crsp_daily_pilot.csv",
        "staged_returns": root / "data/staging/crsp-pilot-v1/daily_returns.parquet",
        "staged_snapshots": root / "data/staging/crsp-pilot-v1/security_snapshots.parquet",
    }
    inputs = {key: {"path": str(path.relative_to(root)),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
              for key, path in paths.items()}
    # Pin the delivered sources rather than silently applying this receipt to a new export.
    require(inputs["names"]["sha256"] ==
            "6faf8d24087c2abb67d1b3c4895857188cddc4b23b272b4f067e9c85bc7c59a1",
            "Names source differs from the received pilot")
    require(inputs["daily"]["sha256"] ==
            "884faf245e5b03bffcd1217a3be802dff91433319de05494da9ce6beac67d0d6",
            "Daily source differs from the received pilot")
    names = pd.read_csv(paths["names"], dtype=str, keep_default_na=False)
    raw = pd.read_csv(paths["daily"], dtype=str, keep_default_na=False)
    require(raw.DlyCalDt.str[:4].astype(int).le(config["development_end"]).all(),
            "Daily source includes observations outside development")
    raw["source_csv_row"] = raw.index + 2
    rows = raw.loc[raw.PERMNO.eq("12060") & raw.DlyCalDt.between(start, end)]
    rows = rows.sort_values("DlyCalDt").reset_index(drop=True)
    sessions = calendar().sessions_in_range(start, end).strftime("%Y-%m-%d").tolist()
    require(rows.DlyCalDt.tolist() == sessions, "GE source sessions missing or duplicated")
    require(len(sessions) == 10, "Unexpected exchange calendar for the fixed case")
    require(rows.PERMCO.eq("20792").all(), "GE source company identifier changed")
    require(rows.DlyDelFlg.eq("N").all() & rows.DlyRetMissFlg.eq("NA").all(),
            "Unexpected terminal or missing-return flags")

    with duckdb.connect() as con:
        tables = {}
        for key in ("staged_returns", "staged_snapshots"):
            tables[key] = con.execute(
                "SELECT * FROM read_parquet(?) WHERE security_id = ? "
                "AND session BETWEEN ? AND ? ORDER BY session",
                [str(paths[key]), "12060", start, end],
            ).df()
    staged, snapshots = tables["staged_returns"], tables["staged_snapshots"]
    for table in (staged, snapshots):
        require(table.session.tolist() == sessions, "Staged sessions missing or duplicated")
        require(table.source_csv_row.tolist() == rows.source_csv_row.tolist(),
                "Staged source row references differ")
    require(staged.total_return.tolist() == [float(value) for value in rows.DlyRet],
            "Staged daily returns differ from delivered numeric values")
    require(not staged.terminal_event.any() and staged.source_delisting_flag.eq("N").all()
            and staged.source_return_missing_flag.eq("NA").all(),
            "Staging changed source flags")

    ge = names.loc[names.permno.eq("12060")]
    intervals, header_disagreements = set(), 0
    for i, row in rows.iterrows():
        match = ge.loc[(ge.secinfostartdt <= row.DlyCalDt) &
                       (ge.secinfoenddt >= row.DlyCalDt)]
        require(len(match) == 1, "Missing or ambiguous dated Names match")
        name, snapshot = match.iloc[0], snapshots.iloc[i]
        require(name.permco == row.PERMCO == snapshot.source_permco,
                "Names/daily/snapshot company identifiers disagree")
        expected_cusip = "36960410" if row.DlyCalDt < transition else "36960430"
        require(name.cusip == expected_cusip, "CUSIP transition differs from the case")
        require(snapshot.source_name_start == name.secinfostartdt and
                snapshot.source_name_end == name.secinfoenddt and
                snapshot.industry == name.siccd and snapshot.industry_scheme == "SIC",
                "Snapshot does not use the dated Names record")
        intervals.add((name.secinfostartdt, name.secinfoenddt))
        header_disagreements += int(row.HdrCUSIP != name.cusip)
    require(len(intervals) == 2, "Case does not cross exactly two Names intervals")
    old, new = sorted(intervals)
    require(old[1] == "2021-08-01" and new[0] == transition and
            date.fromisoformat(old[1]) + timedelta(days=1) == date.fromisoformat(new[0]),
            "Names transition has a gap or wrong boundary")
    require(rows.HdrCUSIP.eq("36960430").all() and header_disagreements == 5,
            "Observed current-header versus dated-identifier pattern changed")
    return {
        "case": "GE 2021 reverse-split CUSIP transition; fixed development-period source QA",
        "status": "automated_identifier_and_staging_checks_passed",
        "window_start": start, "window_end": end, "transition_session": transition,
        "expected_sessions": len(sessions), "source_rows": len(rows),
        "dated_names_intervals": len(intervals), "unique_names_match_each_session": True,
        "continuous_permno_and_permco": True, "header_vs_dated_cusip_disagreements":
            header_disagreements,
        "staged_returns_unchanged": True, "dated_snapshots_and_source_rows_match": True,
        "source_reference": "https://www.sec.gov/Archives/edgar/data/40545/"
                            "000120677421001925/ge3936671-8k.htm",
        "source_reference_usage": "Item 3.03 assistant-inspected for date and new CUSIP; "
                                  "the script does not certify the SEC text",
        "inputs": inputs,
        "verification_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "protocol_sha256": canonical_hash(config), "human_reviews_completed": 0,
        "historical_cik_mapping_approved": False, "split_return_arithmetic_verified": False,
        "terminal_handling_verified": False, "actual_event_labels_generated": False,
        "model_fitted": False, "final_period_returns_used": False,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
