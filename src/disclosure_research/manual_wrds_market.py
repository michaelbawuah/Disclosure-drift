"""Offline raw inventory of a manually exported dlycaldt/vwretd market file.

This is source preservation, not market-series normalization. Every source date
is checked before any return is interpreted numerically. All rows, including
duplicates and extra early dates, remain in the guarded private source copy.
"""

import csv
import gzip
import io
import json
import math
import re
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .manual_wrds_intake import _copy_source, _hash, _identity, _iso, _private_directory
from .market_data import development_return_end
from .protocol import canonical_hash, verify_lock
from .timing import calendar
from .universe import year_start_window

MARKET_FIELDS = ("dlycaldt", "vwretd")
_BATCH = 5000
_MAX_BATCH_BYTES = 8 * 1024 * 1024
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?")


@contextmanager
def _market_rows(path: Path):
    with path.open("rb") as raw:
        compressed = raw.read(2) == b"\x1f\x8b"
        raw.seek(0)
        binary = gzip.GzipFile(fileobj=raw) if compressed else raw
        with io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as text:
            reader = csv.reader(text, strict=True)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise ValueError("Market source is empty; a header is required") from exc
            canonical = [field.lower() for field in header]
            if len(set(canonical)) != len(canonical):
                raise ValueError("Market source has ambiguous duplicate headers")
            if len(canonical) != 2 or set(canonical) != set(MARKET_FIELDS):
                raise ValueError("Market inventory requires exactly dlycaldt and vwretd")
            date_index, return_index = canonical.index("dlycaldt"), canonical.index("vwretd")

            def checked():
                for record_number, row in enumerate(reader, start=2):
                    if len(row) != 2:
                        raise ValueError(f"Market CSV record {record_number} has the wrong field count")
                    yield row[date_index], row[return_index]

            yield header, checked()


def _return_classification(value: str) -> tuple[str, bool]:
    text = value.strip()
    if not text:
        return "blank", False
    if not _NUMBER.fullmatch(text):
        # Recognize textual NaN/Infinity, but do not accept Python-only numeric
        # spellings such as 1_000 as vendor numeric literals.
        if re.fullmatch(r"[+-]?(?:nan|inf(?:inity)?)", text, flags=re.I):
            return "nonfinite_numeric", False
        return "malformed", False
    try:
        number = float(text)
        exact = Decimal(text)
    except (ValueError, InvalidOperation):
        return "malformed", False
    if not math.isfinite(number):
        return "nonfinite_numeric", False
    # Decimal comparison catches a value just below -1 even if float conversion
    # would round it to exactly -1. No normalized return is saved or printed.
    return "finite_numeric", exact < Decimal(-1)


def _date_pass(snapshot: Path, db, last_permitted: str):
    rows, dates = 0, Counter()

    def flush():
        db.executemany("INSERT INTO dates VALUES (?,?) ON CONFLICT(day) "
                       "DO UPDATE SET n=n+excluded.n", dates.items())
        db.commit()
        dates.clear()

    with _market_rows(snapshot) as (header, records):
        for day, _ in records:
            _iso(day, "Source DlyCalDt")
            if day > last_permitted:
                raise ValueError("Market source extends beyond the development return window; holdout blocked")
            dates[day] += 1
            rows += 1
            if rows % _BATCH == 0:
                flush()
        flush()
    if rows == 0:
        raise ValueError("Market source contains no data records")
    return header, rows


def _value_pass(snapshot: Path, db, expected_rows: int, start: str, end: str):
    kinds = ("blank", "malformed", "nonfinite_numeric", "finite_numeric")
    all_stats, requested_stats = dict.fromkeys(kinds, 0), dict.fromkeys(kinds, 0)
    all_stats["finite_numeric_below_minus_one"] = requested_stats["finite_numeric_below_minus_one"] = 0
    rows, batch, batch_bytes = 0, [], 0

    def flush():
        nonlocal batch_bytes
        db.executemany("INSERT INTO projections VALUES (?,?,1) "
                       "ON CONFLICT(day,return_text) DO UPDATE SET n=n+1", batch)
        db.commit()
        batch.clear()
        batch_bytes = 0

    with _market_rows(snapshot) as (_, records):
        for day, value in records:
            kind, below = _return_classification(value)
            all_stats[kind] += 1
            all_stats["finite_numeric_below_minus_one"] += below
            if start <= day <= end:
                requested_stats[kind] += 1
                requested_stats["finite_numeric_below_minus_one"] += below
            batch.append((day, value))
            batch_bytes += len(day) + len(value)
            rows += 1
            if len(batch) == _BATCH or batch_bytes >= _MAX_BATCH_BYTES:
                flush()
        flush()
    if rows != expected_rows:
        raise ValueError("Market snapshot row count changed between date and value passes")
    return all_stats, requested_stats


def _counts(db, start=None, end=None):
    where, params = ("WHERE day BETWEEN ? AND ?", (start, end)) if start else ("", ())
    rows, projections = db.execute(
        f"SELECT COALESCE(SUM(n),0), COUNT(*) FROM projections {where}", params).fetchone()
    dates, repeated, conflicts, conflicting_rows = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(records>1),0), COALESCE(SUM(variants>1),0), "
        "COALESCE(SUM(CASE WHEN variants>1 THEN records ELSE 0 END),0) FROM "
        f"(SELECT SUM(n) records, COUNT(*) variants FROM projections {where} GROUP BY day)",
        params).fetchone()
    return {"rows": rows, "distinct_dates": dates, "dates_with_multiple_rows": repeated,
            "duplicate_date_row_excess": rows - dates, "distinct_full_rows": projections,
            "exact_full_duplicate_row_excess": rows - projections,
            "dates_with_distinct_return_texts": conflicts,
            "rows_on_dates_with_distinct_return_texts": conflicting_rows,
            "raw_text_conflicts_adjudicated": False}


def _preserve_sql(sql_source, out):
    result = {"provided": sql_source is not None, "preserved_file": None, "sha256": None,
              "bytes": None, "status": "not_supplied", "sql_interpreted": False,
              "sql_executed": False, "vendor_source_identifier": None,
              "vendor_execution_verified": False, "vendor_vintage_verified": False,
              "source_completeness_verified": False}
    if sql_source is None:
        return result, None
    try:
        original = Path(sql_source).resolve(strict=True)
        pending = out / "query.pending"
        digest, byte_count = _copy_source(original, pending)
        snapshot = pending.rename(out / "query.sql")
        identity = _identity(snapshot)
        if _hash(snapshot) != digest:
            raise ValueError("SQL snapshot changed")
        result.update(preserved_file="query.sql", sha256=digest, bytes=byte_count,
                      status="preserved_without_semantic_interpretation")
        return result, (snapshot, identity, digest)
    except (OSError, ValueError):
        result["status"] = "unavailable_or_copy_integrity_failed"
        return result, None


def inventory_market(source, *, request_start: str, request_end: str, output,
                     config: dict, repo_root=".", sql_source=None) -> dict:
    """Preserve and inventory the observed two-column independent-index export."""
    verify_lock(config, Path(repo_root) / "configs" / "protocol.lock.json")
    start, end = _iso(request_start, "Request start"), _iso(request_end, "Request end")
    first_permitted = year_start_window(config["initial_train_start"], config)["liquidity_start"]
    last_permitted = development_return_end(config)
    if start < first_permitted or start > end or end > last_permitted:
        raise ValueError("Market request must stay inside the frozen development source envelope")
    out = _private_directory(output, repo_root)
    original = Path(source).resolve(strict=True)
    if not original.is_file():
        raise ValueError("Market source must be an existing regular file")
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    snapshot = out / "source.bin"
    digest, byte_count = _copy_source(original, snapshot)
    with snapshot.open("rb") as handle:
        compressed = handle.read(2) == b"\x1f\x8b"
    snapshot = snapshot.rename(out / ("source.csv.gz" if compressed else "source.csv"))
    identity = _identity(snapshot)

    def guard_snapshot():
        if _identity(snapshot) != identity or _hash(snapshot) != digest:
            raise ValueError("Market snapshot changed; no inventory receipt may be issued")

    guard_snapshot()
    with tempfile.TemporaryDirectory(prefix="market-inventory-", dir=out) as temporary:
        with closing(sqlite3.connect(str(Path(temporary) / "inventory.sqlite3"))) as db:
            db.execute("PRAGMA cache_size=-16384")
            db.execute("PRAGMA temp_store=FILE")
            db.execute("CREATE TABLE dates(day TEXT PRIMARY KEY,n INTEGER NOT NULL) WITHOUT ROWID")
            db.execute("CREATE TABLE projections(day TEXT,return_text TEXT,n INTEGER NOT NULL, "
                       "PRIMARY KEY(day,return_text)) WITHOUT ROWID")
            header, rows = _date_pass(snapshot, db, last_permitted)
            guard_snapshot()
            return_counts, requested_return_counts = _value_pass(snapshot, db, rows, start, end)
            guard_snapshot()
            all_rows, requested = _counts(db), _counts(db, start, end)
            first, last, distinct_dates = db.execute("SELECT MIN(day),MAX(day),COUNT(*) FROM dates").fetchone()
            requested_first, requested_last = db.execute(
                "SELECT MIN(day),MAX(day) FROM dates WHERE day BETWEEN ? AND ?", (start, end)).fetchone()
            before = db.execute("SELECT COALESCE(SUM(n),0) FROM dates WHERE day<?", (start,)).fetchone()[0]
            after = db.execute("SELECT COALESCE(SUM(n),0) FROM dates WHERE day>?", (end,)).fetchone()[0]
            sessions = set(calendar().sessions.strftime("%Y-%m-%d"))
            calendar_start, calendar_end = min(sessions), max(sessions)
            expected = {day for day in sessions if start <= day <= end}
            missing = expected.copy()
            non_session_dates = non_session_rows = 0
            outside_calendar_dates = outside_calendar_rows = 0
            for day, count in db.execute("SELECT day,n FROM dates"):
                missing.discard(day)
                if day < calendar_start or day > calendar_end:
                    outside_calendar_dates += 1
                    outside_calendar_rows += count
                elif day not in sessions:
                    non_session_dates += 1
                    non_session_rows += count
    sql, sql_guard = _preserve_sql(sql_source, out)
    guard_snapshot()
    if sql_guard is not None:
        sql_path, sql_identity, sql_digest = sql_guard
        if _identity(sql_path) != sql_identity or _hash(sql_path) != sql_digest:
            sql.update(preserved_file=None, sha256=None, bytes=None,
                       status="sql_snapshot_changed_after_copy")
    receipt = {
        "schema_version": 1, "status": "RAW_MANUAL_WRDS_MARKET_INVENTORY_NOT_SOURCE_APPROVED",
        "created_at": datetime.now(timezone.utc).isoformat(), "protocol_sha256": canonical_hash(config),
        "source": {"preserved_file": snapshot.name, "sha256": digest, "bytes": byte_count,
                   "compression": "gzip" if compressed else "none", "observed_header": header,
                   "declared_source_role": "independent_daily_market_index",
                   "independent_export_verified": False, "source_release": None,
                   "release_evidence": None, "vendor_library": None, "vendor_table": None,
                   "vendor_query_submitted_at": None, "vendor_query_completed_at": None,
                   "vendor_downloaded_at": None, "vendor_execution_verified": False},
        "request": {"start": start, "end": end, "bounds_are_caller_declarations": True,
                    "first_permitted_request_date": first_permitted,
                    "last_permitted_development_return_date": last_permitted},
        "actual_coverage": {"first_date": first, "last_date": last, "distinct_dates": distinct_dates,
                            "rows_before_request": before, "rows_after_request": after,
                            "non_xnys_date_count": non_session_dates, "non_xnys_row_count": non_session_rows,
                            "outside_calendar_date_count": outside_calendar_dates,
                            "outside_calendar_row_count": outside_calendar_rows,
                            "calendar_covered_session_start": calendar_start,
                            "calendar_covered_session_end": calendar_end},
        "requested_coverage": {"first_date": requested_first, "last_date": requested_last,
                               "expected_xnys_sessions": len(expected), "missing_xnys_sessions": sorted(missing)},
        "all_rows": all_rows, "requested_slice": requested,
        "return_classifications": return_counts, "requested_return_classifications": requested_return_counts,
        "row_equality": "exact parsed DlyCalDt and vwretd text; spelling differences remain distinct",
        "numeric_classification": "finite float-representable numeric literal; exact decimal comparison with -1",
        "sql": sql, "complete_date_pass_before_numeric_interpretation": True,
        "source_snapshot_hash_verified_after_each_pass": True,
        "source_completeness_verified": False, "source_return_convention_verified": False,
        "rows_dropped": 0, "values_filled": 0, "values_normalized": 0,
        "model_ready": False, "source_approvals": 0, "prior_arithmetic_review_modified": False,
    }
    with (out / "receipt.json").open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, allow_nan=False)
        handle.write("\n")
    (out / "receipt.json").chmod(0o600)
    return receipt
