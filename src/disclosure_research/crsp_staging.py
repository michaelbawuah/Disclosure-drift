"""Stage observed WRDS CIZ exports without certifying identity or terminal coverage.

This deliberately does not create an import-market manifest or CIK links.
Raw CSV bytes remain the authority; missing codes are never inferred as null/zero.
"""

import csv
import io
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from .market_data import development_return_end, iso_dates, sha256
from .protocol import canonical_hash
from .timing import calendar

DAILY_FIELDS = """PERMNO HdrCUSIP Ticker PERMCO DlyCalDt DlyDelFlg
DlyCap DlyRet DlyRetMissFlg vwretd""".split()
NAME_FIELDS = """permno permco secinfostartdt secinfoenddt siccd""".split()
SOURCE_DOCS = [
    "https://www.crsp.org/crsp_pdf/crsp-us-stock-indexes-databases-guide-flat-file-format-2-0/",
    "https://wrds-www.wharton.upenn.edu/documents/2084/Webinar.pdf",
]


def _csv(path: str | Path, required: list[str]) -> tuple[pd.DataFrame, bytes]:
    raw = Path(path).read_bytes()
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    header = next(reader, [])
    if len(header) != len(set(header)) or set(required) - set(header):
        raise ValueError("CSV has duplicate columns or is missing required source fields")
    rows = list(reader)
    if not rows or any(len(row) != len(header) for row in rows):
        raise ValueError("CSV is empty or has inconsistent row widths")
    # No automatic NA inference, whitespace repair or identifier coercion.
    return pd.DataFrame(rows, columns=header), raw


def _ids(values: pd.Series, label: str) -> None:
    if not values.str.fullmatch(r"[1-9]\d*").all():
        raise ValueError(f"{label} requires positive integer identifiers as source strings")


def _numeric(values: pd.Series, label: str, minimum: float) -> pd.Series:
    try:
        numeric = pd.to_numeric(values, errors="raise").astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not np.isfinite(numeric).all() or (numeric < minimum).any():
        raise ValueError(f"{label} must be finite and at least {minimum}")
    return numeric


def inspect_daily(path: str | Path, config: dict, request_start: str,
                  request_end: str) -> tuple[dict, dict, bytes]:
    """Normalize supported fields; report gaps against an explicit request window.

    A Y row carries its own return. Never add DLRET or invent a payoff when it is
    absent. A lack of Y rows is not evidence that terminal handling was verified.
    """
    raw_frame, raw = _csv(path, DAILY_FIELDS)
    bounds = pd.Series([request_start, request_end])
    iso_dates(bounds, "request bounds")
    if request_start > request_end:
        raise ValueError("Request dates are reversed")
    iso_dates(raw_frame.DlyCalDt, "CRSP.DlyCalDt", sessions=True)
    # Reject a holdout request/row before interpreting any return values or flags.
    if max(request_end, raw_frame.DlyCalDt.max()) > development_return_end(config):
        raise ValueError("CRSP dates exceed the development label window; holdout blocked")
    if not raw_frame.DlyCalDt.between(request_start, request_end).all():
        raise ValueError("CSV dates fall outside the declared request window")
    _ids(raw_frame.PERMNO, "PERMNO")
    _ids(raw_frame.PERMCO, "PERMCO")
    if raw_frame.duplicated(["PERMNO", "DlyCalDt"]).any():
        raise ValueError("Duplicate CRSP security/session keys")
    if not raw_frame.DlyDelFlg.isin(["N", "Y"]).all():
        raise ValueError("Unsupported DlyDelFlg; resolve source flags before staging")
    if not raw_frame.DlyRetMissFlg.eq("NA").all():
        raise ValueError("Unresolved DlyRetMissFlg; missing returns must not become zero")

    daily = pd.DataFrame({
        "security_id": raw_frame.PERMNO, "session": raw_frame.DlyCalDt,
        "total_return": _numeric(raw_frame.DlyRet, "DlyRet", -1),
        "terminal_event": raw_frame.DlyDelFlg.eq("Y"),
        "source_delisting_flag": raw_frame.DlyDelFlg,
        "source_return_missing_flag": raw_frame.DlyRetMissFlg,
        "source_csv_row": np.arange(2, len(raw_frame) + 2),
    })
    benchmark = pd.DataFrame({
        "session": raw_frame.DlyCalDt,
        "total_return": _numeric(raw_frame.vwretd, "vwretd", -1),
    })
    if benchmark.groupby("session").total_return.nunique().gt(1).any():
        raise ValueError("Conflicting benchmark returns across securities on the same date")
    benchmark = benchmark.drop_duplicates("session").sort_values("session").reset_index(drop=True)

    cap = pd.Series(np.nan, index=raw_frame.index, dtype=float)
    present = raw_frame.DlyCap.ne("")
    cap.loc[present] = _numeric(raw_frame.loc[present, "DlyCap"], "DlyCap", 0) * 1000
    if not np.isfinite(cap.loc[present]).all():
        raise ValueError("DlyCap USD conversion overflow")
    capitalizations = pd.DataFrame({
        "security_id": raw_frame.PERMNO, "session": raw_frame.DlyCalDt,
        "market_cap_usd": cap, "valid_market_cap": cap.notna() & cap.gt(0),
        "source_permco": raw_frame.PERMCO, "source_csv_row": daily.source_csv_row,
    })
    expected = [s for s in calendar().sessions.strftime("%Y-%m-%d")
                if request_start <= s <= request_end]
    if not expected:
        raise ValueError("Request window contains no configured exchange sessions")
    coverage = []
    for security_id, group in daily.groupby("security_id", sort=True):
        terminal = group.loc[group.terminal_event, "session"].tolist()
        if len(terminal) > 1 or (terminal and group.session.max() > terminal[0]):
            raise ValueError(f"Multiple terminal events or post-terminal rows: {security_id}")
        needed = [s for s in expected if not terminal or s <= terminal[0]]
        missing = sorted(set(needed) - set(group.session))
        coverage.append({"security_id": security_id, "rows": len(group),
                         "first_session": group.session.min(), "last_session": group.session.max(),
                         "terminal_session": terminal[0] if terminal else None,
                         "missing_requested_sessions_through_terminal": len(missing),
                         "first_missing_session": missing[0] if missing else None})
    summary = {
        "rows": len(daily), "securities": len(coverage),
        "request_start": request_start, "request_end": request_end,
        "request_dates_provenance": "caller-declared; vendor query parameters not certified",
        "expected_exchange_sessions": len(expected), "coverage": coverage,
        "missing_security_sessions": sum(c["missing_requested_sessions_through_terminal"]
                                         for c in coverage),
        "benchmark_sessions": len(benchmark),
        "missing_benchmark_sessions": len(set(expected) - set(benchmark.session)),
        "terminal_rows": int(daily.terminal_event.sum()),
        "invalid_or_missing_capitalizations": int((~capitalizations.valid_market_cap).sum()),
        "source_return_missing_flag_counts": raw_frame.DlyRetMissFlg.value_counts().to_dict(),
        "terminal_handling_verified": False,
    }
    tables = {"daily_returns": daily.sort_values(["security_id", "session"]).reset_index(drop=True),
              "market_returns": benchmark, "capitalizations": capitalizations}
    return tables, summary, raw


def _snapshots(capitalizations: pd.DataFrame, names_path: str | Path) -> tuple[pd.DataFrame, bytes]:
    names, raw = _csv(names_path, NAME_FIELDS)
    for key in ["permno", "permco"]:
        _ids(names[key], key)
    for field in ["secinfostartdt", "secinfoenddt"]:
        iso_dates(names[field], field)
    if (names.secinfostartdt > names.secinfoenddt).any():
        raise ValueError("Reversed Names interval")
    if not names.siccd.str.fullmatch(r"\d{1,4}").all():
        raise ValueError("Missing or unsupported historical SIC code")
    histories = {}
    for permno, group in names.groupby("permno", sort=False):
        history = group.sort_values("secinfostartdt").reset_index(drop=True)
        if (history.secinfostartdt.iloc[1:].to_numpy() <=
                history.secinfoenddt.iloc[:-1].to_numpy()).any():
            raise ValueError(f"Overlapping Names intervals: {permno}")
        histories[permno] = history
    parts = []
    for permno, group in capitalizations.groupby("security_id", sort=False):
        if permno not in histories:
            raise ValueError(f"Missing Names history: {permno}")
        history = histories[permno]
        positions = np.searchsorted(history.secinfostartdt, group.session, side="right") - 1
        if (positions < 0).any():
            raise ValueError(f"Missing dated Names match: {permno}")
        matched = history.iloc[positions]
        if (group.session.to_numpy() > matched.secinfoenddt.to_numpy()).any():
            raise ValueError(f"Missing dated Names match: {permno}")
        if (group.source_permco.to_numpy() != matched.permco.to_numpy()).any():
            raise ValueError(f"Daily/Names PERMCO mismatch: {permno}")
        out = group.copy()
        out["industry"] = matched.siccd.to_numpy()
        out["industry_scheme"] = "SIC"
        out["source_name_start"] = matched.secinfostartdt.to_numpy()
        out["source_name_end"] = matched.secinfoenddt.to_numpy()
        parts.append(out)
    return pd.concat(parts).sort_values(["security_id", "session"]).reset_index(drop=True), raw


def stage_crsp(daily_path: str | Path, names_path: str | Path, output: str | Path,
               config: dict, request_start: str, request_end: str) -> dict:
    """Create private Parquet/DuckDB staging with an explicit incomplete provenance receipt."""
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; preserve the prior staging run")
    tables, summary, daily_raw = inspect_daily(daily_path, config, request_start, request_end)
    snapshots, names_raw = _snapshots(tables.pop("capitalizations"), names_path)
    tables["security_snapshots"] = snapshots
    receipt = {
        "schema_version": 1, "data_kind": "CRSP_SOURCE_STAGING_NOT_AUDIT_APPROVED",
        "staged_at": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": canonical_hash(config),
        "normalization_code_sha256": sha256(Path(__file__).read_bytes()),
        "raw_exports": [
            {"filename": Path(daily_path).name, "sha256": sha256(daily_raw),
             "source_table": None},
            {"filename": Path(names_path).name, "sha256": sha256(names_raw),
             "source_table": None},
        ],
        "source_release": None, "source_export_timestamp": None, "query_id": None,
        "source_documentation": SOURCE_DOCS, "coverage": summary,
        "field_mapping": {"total_return": "DlyRet unchanged; no separate DLRET added",
                          "terminal_event": "DlyDelFlg == Y; requires external coverage audit",
                          "market_return": "vwretd; identical duplicates collapsed by session",
                          "market_cap_usd": "DlyCap * 1000; missing/zero remain invalid",
                          "industry": "siccd from inclusive dated Names match; no header SIC"},
        "historical_cik_mapping_approved": False, "point_in_time_availability_verified": False,
        "terminal_handling_verified": False, "import_ready": False, "model_ready": False,
        "human_reviews_completed": 0, "actual_event_labels_generated": False,
        "final_period_opened": False,
        "remaining": ["exact release/query metadata", "terminal-payoff coverage audit",
                      "historical CIK/security mapping", "point-in-time availability audit",
                      "independent filing and label/control reviews"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".crsp-stage-", dir=output.parent) as temp:
        stage = Path(temp) / "bundle"
        stage.mkdir()
        for name, table in tables.items():
            table.to_parquet(stage / f"{name}.parquet", index=False)
        with duckdb.connect(str(stage / "staging.duckdb")) as con:
            for name, table in tables.items():
                con.register("source_frame", table)
                con.execute(f"CREATE TABLE {name} AS SELECT * FROM source_frame")
        receipt["table_sha256"] = {name: sha256((stage / f"{name}.parquet").read_bytes())
                                   for name in tables}
        receipt["duckdb_sha256"] = sha256((stage / "staging.duckdb").read_bytes())
        (stage / "staging_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        stage.rename(output)
    return receipt
