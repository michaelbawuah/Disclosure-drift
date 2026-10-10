"""Offline raw WRDS daily-file inventory, with no normalization or source approval.

The original bytes are copied once to a new private directory. A complete
date-only pass must succeed before any value is interpreted as a number.
SQLite stores exact parsed-row uniqueness on disk; no full data frame is built.
"""

import csv
import gzip
import hashlib
import io
import json
import math
import os
import re
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from .market_data import development_return_end
from .protocol import canonical_hash
from .timing import calendar

DAILY_FIELDS = (
    "permno", "permco", "hdrcusip", "ticker", "dlycaldt", "dlyprc", "dlyvol",
    "dlyprcflg", "dlyret", "dlyretmissflg", "dlydelflg", "dlycap", "vwretd",
)
FLAG_FIELDS = ("dlyprcflg", "dlyretmissflg", "dlydelflg")
_BATCH = 5000
_MAX_HEADERS = 256
_HEADER = re.compile(r"[A-Za-z_][A-Za-z_0-9]{0,127}")


def _iso(value: str, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{label} must be a complete YYYY-MM-DD date")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} is not a valid calendar date") from exc
    return value


def _identity(path: Path):
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _fd_identity(handle):
    stat = os.fstat(handle.fileno())
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _copy_source(source: Path, destination: Path) -> tuple[str, int]:
    before = _identity(source)
    digest = hashlib.sha256()
    with source.open("rb") as original, destination.open("xb") as saved:
        if _fd_identity(original) != before:
            raise ValueError("Source changed before its byte-preserving copy")
        for block in iter(lambda: original.read(1024 * 1024), b""):
            saved.write(block)
            digest.update(block)
        saved.flush()
        os.fsync(saved.fileno())
        if _fd_identity(original) != before or _identity(source) != before:
            raise ValueError("Source changed during its byte-preserving copy")
    destination.chmod(0o400)
    return digest.hexdigest(), before[2]


@contextmanager
def _rows(path: Path, *, allow_extra_columns: bool = False):
    with path.open("rb") as raw:
        compressed = raw.read(2) == b"\x1f\x8b"
        raw.seek(0)
        binary = gzip.GzipFile(fileobj=raw) if compressed else raw
        with io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as text:
            reader = csv.reader(text, strict=True)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise ValueError("Source is empty; a daily header is required") from exc
            if not 1 <= len(header) <= _MAX_HEADERS or not all(_HEADER.fullmatch(field) for field in header):
                raise ValueError("Daily headers must be at most 256 plain field names of at most 128 characters")
            canonical = [column.lower() for column in header]
            if len(set(canonical)) != len(canonical):
                raise ValueError("Daily source has ambiguous duplicate headers")
            if set(DAILY_FIELDS) - set(canonical):
                raise ValueError("Daily inventory requires all 13 declared daily fields")
            if not allow_extra_columns and len(canonical) != len(DAILY_FIELDS):
                raise ValueError("Daily inventory requires exactly 13 fields unless --allow-extra-columns is explicit")
            indices = [canonical.index(column) for column in DAILY_FIELDS]

            def checked():
                for record_number, row in enumerate(reader, start=2):
                    if len(row) != len(header):
                        raise ValueError(f"CSV record {record_number} has the wrong field count")
                    yield [row[index] for index in indices]

            yield header, checked()


def _numeric_kind(value: str) -> str:
    if not value.strip():
        return "blank"
    try:
        number = float(value)
    except ValueError:
        return "non_numeric"
    return "finite_numeric" if math.isfinite(number) else "nonfinite_numeric"


def _private_directory(output, repo_root) -> Path:
    out, repo = Path(output).resolve(), Path(repo_root).resolve()
    if not any(out.is_relative_to(repo / folder) and out != repo / folder
               for folder in ("data", "outputs")):
        raise ValueError("Manual inventory must use a new private directory under data/ or outputs/")
    if out.exists():
        raise ValueError("Inventory output exists; preserve it and use a new path")
    return out


def _insert_dates(db, counts):
    db.executemany("INSERT INTO dates VALUES (?, ?) ON CONFLICT(day) "
                   "DO UPDATE SET n=n+excluded.n", counts.items())


def _date_pass(snapshot: Path, db, last_permitted: str, *, allow_extra_columns: bool = False) -> tuple[list[str], int]:
    counts, rows = Counter(), 0
    with _rows(snapshot, allow_extra_columns=allow_extra_columns) as (header, records):
        for row in records:
            day = _iso(row[DAILY_FIELDS.index("dlycaldt")], "Source DlyCalDt")
            if day > last_permitted:
                raise ValueError("Source extends beyond the development return window; holdout blocked")
            counts[day] += 1
            rows += 1
            if rows % _BATCH == 0:
                _insert_dates(db, counts)
                counts.clear()
        _insert_dates(db, counts)
    if not rows:
        raise ValueError("Daily source contains no data records")
    db.commit()
    return header, rows


def _value_pass(snapshot: Path, db, expected_rows: int, *, allow_extra_columns: bool = False):
    columns = {column: {kind: 0 for kind in
                       ("blank", "finite_numeric", "nonfinite_numeric", "non_numeric")}
               for column in DAILY_FIELDS}
    batch, flags, rows = [], Counter(), 0

    def flush():
        db.executemany("INSERT INTO projections VALUES (?, ?, ?, 1) "
                       "ON CONFLICT(permno, day, payload) DO UPDATE SET n=n+1", batch)
        db.executemany("INSERT INTO flags VALUES (?, ?, ?) "
                       "ON CONFLICT(field, code) DO UPDATE SET n=n+excluded.n",
                       [(field, code, count) for (field, code), count in flags.items()])
        db.commit()
        batch.clear()
        flags.clear()

    with _rows(snapshot, allow_extra_columns=allow_extra_columns) as (_, records):
        for row in records:
            for field, value in zip(DAILY_FIELDS, row, strict=True):
                columns[field][_numeric_kind(value)] += 1
                if field in FLAG_FIELDS:
                    flags[field, value] += 1
            batch.append((row[0], row[4], json.dumps(row, ensure_ascii=True, separators=(",", ":"))))
            rows += 1
            if len(batch) == _BATCH:
                flush()
        flush()
    if rows != expected_rows:
        raise ValueError("Snapshot row count changed between date and value passes")
    return columns


def _duplicate_counts(db, start=None, end=None) -> dict:
    where, params = ("WHERE day BETWEEN ? AND ?", (start, end)) if start else ("", ())
    rows, projections = db.execute(
        f"SELECT COALESCE(SUM(n), 0), COUNT(*) FROM projections {where}", params).fetchone()
    keys, duplicates, conflicts, conflict_rows = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(records > 1), 0), "
        "COALESCE(SUM(variants > 1), 0), "
        "COALESCE(SUM(CASE WHEN variants > 1 THEN records ELSE 0 END), 0) FROM "
        f"(SELECT SUM(n) records, COUNT(*) variants FROM projections {where} "
        "GROUP BY permno, day)", params).fetchone()
    securities = db.execute(
        f"SELECT COUNT(DISTINCT permno) FROM projections {where}", params).fetchone()[0]
    return {"rows": rows, "distinct_security_identifiers": securities,
            "distinct_security_date_keys": keys, "duplicate_security_date_keys": duplicates,
            "duplicate_security_date_row_excess": rows - keys,
            "distinct_full_projected_rows": projections,
            "exact_full_projected_duplicate_row_excess": rows - projections,
            "conflicting_security_date_keys": conflicts,
            "rows_in_conflicting_security_date_keys": conflict_rows,
            "conflicting_projection_excess": projections - keys}


def _flag_counts(db) -> dict:
    result = {}
    for field in FLAG_FIELDS:
        values = {}
        unreported_rows = 0
        distinct_codes = 0
        # Bound JSON size and avoid copying arbitrary text (for example URLs)
        # out of a malformed field. Such rows still remain in the source copy.
        for code, count in db.execute("SELECT code, n FROM flags WHERE field=? ORDER BY code",
                                      (field,)):
            distinct_codes += 1
            if len(values) < 64 and (not code or re.fullmatch(r"[A-Za-z0-9_.+\-]{1,12}", code)):
                values[code] = count
            else:
                unreported_rows += count
        result[field] = {"source_code_counts": values, "distinct_source_codes": distinct_codes,
                         "rows_with_unreported_code_text": unreported_rows,
                         "source_codes_interpreted": False}
    return result


def inventory_daily(source, *, request_start: str, request_end: str, output,
                    config: dict, repo_root=".", allow_extra_columns: bool = False) -> dict:
    """Preserve and inventory a manual development-only CSV or gzip download.

    Output is a new directory containing ``source.csv[.gz]`` and ``receipt.json``.
    Failed input leaves no success receipt. Extra early rows are retained and
    counted separately; no row is dropped, filled, or made model-ready. Extra
    columns require explicit opt-in; all source bytes remain preserved, while
    duplicate comparisons and numeric inventory use the 13 required fields.
    """
    if type(allow_extra_columns) is not bool:
        raise ValueError("allow_extra_columns must be an explicit boolean")
    start = _iso(request_start, "Request start")
    end = _iso(request_end, "Request end")
    last_permitted = development_return_end(config)
    if start > end or end > last_permitted:
        raise ValueError("Request must be ordered and inside the development return window")
    out = _private_directory(output, repo_root)
    original = Path(source).resolve(strict=True)
    if not original.is_file():
        raise ValueError("Source must be an existing regular file")
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    # Derive compression from the same preserved bytes as the recorded hash.
    # Inspecting the live file separately would allow a type/signature race.
    snapshot = out / "source.bin"
    digest, byte_count = _copy_source(original, snapshot)
    with snapshot.open("rb") as handle:
        compressed = handle.read(2) == b"\x1f\x8b"
    snapshot = snapshot.rename(out / ("source.csv.gz" if compressed else "source.csv"))
    snapshot_identity = _identity(snapshot)

    def guard_snapshot():
        if _identity(snapshot) != snapshot_identity or _hash(snapshot) != digest:
            raise ValueError("Source snapshot changed; no inventory receipt may be issued")

    with tempfile.TemporaryDirectory(prefix="inventory-", dir=out) as temporary:
        with closing(sqlite3.connect(str(Path(temporary) / "inventory.sqlite3"))) as db:
            db.execute("PRAGMA cache_size=-16384")
            db.execute("PRAGMA temp_store=FILE")
            db.execute("CREATE TABLE dates(day TEXT PRIMARY KEY, n INTEGER NOT NULL) WITHOUT ROWID")
            db.execute("CREATE TABLE projections(permno TEXT, day TEXT, payload TEXT, n INTEGER NOT NULL, "
                       "PRIMARY KEY(permno, day, payload)) WITHOUT ROWID")
            db.execute("CREATE TABLE flags(field TEXT, code TEXT, n INTEGER NOT NULL, "
                       "PRIMARY KEY(field, code)) WITHOUT ROWID")
            guard_snapshot()
            header, rows = _date_pass(snapshot, db, last_permitted,
                                      allow_extra_columns=allow_extra_columns)
            guard_snapshot()
            columns = _value_pass(snapshot, db, rows, allow_extra_columns=allow_extra_columns)
            guard_snapshot()
            all_counts = _duplicate_counts(db)
            slice_counts = _duplicate_counts(db, start, end)
            first, last, distinct_dates = db.execute(
                "SELECT MIN(day), MAX(day), COUNT(*) FROM dates").fetchone()
            requested_first, requested_last, requested_dates = db.execute(
                "SELECT MIN(day), MAX(day), COUNT(*) FROM dates WHERE day BETWEEN ? AND ?",
                (start, end)).fetchone()
            before = db.execute("SELECT COALESCE(SUM(n), 0) FROM dates WHERE day < ?", (start,)).fetchone()[0]
            after = db.execute("SELECT COALESCE(SUM(n), 0) FROM dates WHERE day > ?", (end,)).fetchone()[0]
            valid_sessions = set(calendar().sessions.strftime("%Y-%m-%d"))
            expected = {day for day in valid_sessions if start <= day <= end}
            missing = expected.copy()
            non_session_dates = non_session_rows = 0
            for day, count in db.execute("SELECT day, n FROM dates"):
                missing.discard(day)
                if day not in valid_sessions:
                    non_session_dates += 1
                    non_session_rows += count
            flags = _flag_counts(db)

    receipt = {
        "schema_version": 1, "status": "RAW_MANUAL_WRDS_INVENTORY_NOT_AUDIT_APPROVED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": canonical_hash(config),
        "source": {"preserved_file": snapshot.name, "sha256": digest, "bytes": byte_count,
                   "compression": "gzip" if compressed else "none", "observed_header": header,
                   "delivered_column_count": len(header),
                   "source_release": None, "release_evidence": None,
                   "vendor_query_sql": None, "vendor_query_submitted_at": None,
                   "vendor_query_completed_at": None, "vendor_downloaded_at": None,
                   "declared_acquisition_method": "user_supplied_manual_download",
                   "vendor_library": None, "vendor_table": None,
                   "all_securities_query_verified": False},
        "request": {"start": start, "end": end,
                    "date_bounds_are_caller_declarations": True,
                    "last_permitted_development_return_date": last_permitted},
        "actual_coverage": {"first_date": first, "last_date": last,
                            "distinct_dates": distinct_dates, "rows_before_request": before,
                            "rows_after_request": after, "non_xnys_date_count": non_session_dates,
                            "non_xnys_row_count": non_session_rows},
        "requested_coverage": {"first_date": requested_first, "last_date": requested_last,
                               "distinct_dates": requested_dates,
                               "expected_xnys_sessions": len(expected),
                               "missing_xnys_sessions": sorted(missing),
                               "coverage_does_not_establish_security_universe_completeness": True},
        "all_rows": all_counts, "requested_slice": slice_counts,
        "columns": columns, "flags": flags,
        "projection": {"fields": list(DAILY_FIELDS), "column_count": len(DAILY_FIELDS),
                       "allow_extra_columns": allow_extra_columns,
                       "extra_columns": [field for field in header if field.lower() not in DAILY_FIELDS],
                       "all_delivered_columns_preserved": True,
                       "extra_column_values_interpreted": False,
                       "duplicate_counts_scope": "required_13_fields_in_canonical_order"},
        "full_delivered_row_duplicates_checked": len(header) == len(DAILY_FIELDS),
        "row_equality": "exact parsed text across the 13 required projected fields; extra delivered fields excluded",
        "security_key_equality": "exact PERMNO text and validated ISO DlyCalDt; no identifier coercion",
        "numeric_classification": "blank, finite float, nonfinite float, or nonnumeric; values unchanged",
        "complete_date_pass_before_numeric_interpretation": True,
        "source_snapshot_hash_verified_after_each_pass": True,
        "rows_dropped": 0, "values_filled": 0, "values_normalized": 0,
        "source_flags_interpreted": False, "model_ready": False, "human_approvals": 0,
    }
    guard_snapshot()
    receipt_path = out / "receipt.json"
    with receipt_path.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, allow_nan=False)
        handle.write("\n")
    receipt_path.chmod(0o600)
    return receipt
