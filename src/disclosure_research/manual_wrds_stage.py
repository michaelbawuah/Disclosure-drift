"""Bounded offline projection of preserved manual WRDS development sources.

This is a raw-source stage, not normalization or an approved market provider.
Every input receives a complete date-only preflight before any return is parsed.
Original files remain in their inventory bundles; private Parquet parts retain
every daily CSV record, the thirteen required strings, and record provenance.
"""

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path, PurePosixPath

import pyarrow as pa
import pyarrow.parquet as pq

from .manual_wrds_intake import DAILY_FIELDS, _fd_identity, _hash, _identity, _iso, _private_directory, _rows
from .manual_wrds_market import _market_rows, _return_classification
from .market_data import development_return_end
from .protocol import canonical_hash, verify_lock
from .timing import calendar
from .universe import year_start_window

_MAX_RECEIPT_BYTES = 2 * 1024 * 1024
_MAX_SOURCES = 64
_BATCH_ROWS = 25_000
_BATCH_BYTES = 8 * 1024 * 1024
_MAX_PARTS = 100_000
_SHA = re.compile(r"[0-9a-f]{64}")
_PATH_PART = re.compile(r"[A-Za-z0-9_.-]{1,128}")
_KINDS = ("blank", "malformed", "nonfinite_numeric", "finite_numeric", "finite_numeric_below_minus_one")
PROVENANCE_FIELDS = ("source_sha256", "source_inventory_sha256", "source_csv_record", "in_requested_window")
PARQUET_SCHEMA = pa.schema(
    [pa.field(field, pa.string(), nullable=False) for field in DAILY_FIELDS]
    + [pa.field("source_sha256", pa.string(), nullable=False),
       pa.field("source_inventory_sha256", pa.string(), nullable=False),
       pa.field("source_csv_record", pa.int64(), nullable=False),
       pa.field("in_requested_window", pa.bool_(), nullable=False)]
)


class SourceStageError(ValueError):
    """An aggregate-only validation failure; original inventories are untouched."""

    def __init__(self, message, *, evidence=None):
        super().__init__(message)
        self.evidence = evidence or {}


@dataclass
class _Bundle:
    source_id: str
    role: str
    directory: Path
    receipt: dict
    receipt_path: Path
    receipt_identity: tuple
    receipt_sha256: str
    receipt_snapshot: Path
    source: Path
    source_identity: tuple
    source_sha256: str
    allow_extra_columns: bool
    rows: int = 0
    requested_rows: int = 0


def _integer(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Inventory receipt has duplicate JSON keys")
        result[key] = value
    return result


def _read_receipt(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Inventory receipt must be an ordinary file")
    before = _identity(path)
    if before[2] > _MAX_RECEIPT_BYTES:
        raise ValueError("Inventory receipt exceeds the bounded metadata limit")
    with path.open("rb") as handle:
        if _fd_identity(handle) != before:
            raise ValueError("Inventory receipt changed before reading")
        raw = handle.read(_MAX_RECEIPT_BYTES + 1)
        if len(raw) > _MAX_RECEIPT_BYTES or _fd_identity(handle) != before or _identity(path) != before:
            raise ValueError("Inventory receipt changed while reading")
    try:
        receipt = json.loads(raw, object_pairs_hook=_unique_json)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Inventory receipt is not valid JSON") from exc
    if not isinstance(receipt, dict):
        raise ValueError("Inventory receipt must be a JSON object")
    return receipt, raw, before


def _safe_source(directory, value):
    if not isinstance(value, str) or len(value) > 512 or "\\" in value:
        raise ValueError("Preserved source path must be a safe relative path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or not relative.parts or any(
        part in (".", "..") or not _PATH_PART.fullmatch(part) for part in value.split("/")
    ):
        raise ValueError("Preserved source path must be a safe relative path")
    current = directory
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Preserved source path may not use symbolic links")
    resolved = current.resolve(strict=True)
    if not resolved.is_relative_to(directory) or not resolved.is_file():
        raise ValueError("Preserved source must be an ordinary file within its inventory")
    return resolved


def _guard(bundle, *, rehash=False):
    current = _safe_source(bundle.directory, bundle.receipt["source"]["preserved_file"])
    if current != bundle.source or _identity(current) != bundle.source_identity:
        raise ValueError("Preserved source changed during staging")
    if _identity(bundle.receipt_path) != bundle.receipt_identity:
        raise ValueError("Input inventory receipt changed during staging")
    if rehash:
        if _hash(current) != bundle.source_sha256 or _identity(current) != bundle.source_identity:
            raise ValueError("Preserved source hash changed during staging")
        if (_hash(bundle.receipt_path) != bundle.receipt_sha256
                or _identity(bundle.receipt_path) != bundle.receipt_identity
                or _hash(bundle.receipt_snapshot) != bundle.receipt_sha256):
            raise ValueError("Input inventory receipt or its snapshot changed during staging")


def _load_bundle(directory, role, number, out, protocol_sha256, last_permitted):
    directory = Path(directory).resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("Inventory input must be a directory")
    receipt_path = directory / "receipt.json"
    receipt, raw, receipt_identity = _read_receipt(receipt_path)
    status = ("RAW_MANUAL_WRDS_INVENTORY_NOT_AUDIT_APPROVED" if role == "daily"
              else "RAW_MANUAL_WRDS_MARKET_INVENTORY_NOT_SOURCE_APPROVED")
    if (type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1
            or receipt.get("status") != status or receipt.get("protocol_sha256") != protocol_sha256):
        raise ValueError("Inventory schema, source role, or frozen protocol does not match")
    source = receipt.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("sha256"), str) or not _SHA.fullmatch(source["sha256"]):
        raise ValueError("Inventory source hash is missing or invalid")
    _integer(source.get("bytes"), "Source bytes")
    header = source.get("observed_header")
    if not isinstance(header, list) or not all(isinstance(field, str) for field in header):
        raise ValueError("Inventory observed header must be a list of field names")
    if not isinstance(receipt.get("all_rows"), dict) or not isinstance(receipt.get("actual_coverage"), dict):
        raise ValueError("Inventory row-count and coverage declarations must be objects")
    _integer(receipt["all_rows"].get("rows"), "Inventory row count")
    request = receipt.get("request", {})
    if not isinstance(request, dict):
        raise ValueError("Inventory request declaration must be an object")
    declared_start = _iso(request.get("start"), "Inventory request start")
    declared_end = _iso(request.get("end"), "Inventory request end")
    if declared_start > declared_end or declared_end > last_permitted:
        raise ValueError("Inventory request exceeds the development envelope")
    allow_extra = False
    if role == "daily":
        projection = receipt.get("projection")
        if projection is not None:
            if (not isinstance(projection, dict) or projection.get("fields") != list(DAILY_FIELDS)
                    or type(projection.get("allow_extra_columns")) is not bool):
                raise ValueError("Daily inventory projection declaration is invalid")
            allow_extra = projection["allow_extra_columns"]
            extras = [field for field in header if field.lower() not in DAILY_FIELDS]
            if projection.get("extra_columns") != extras:
                raise ValueError("Daily inventory extra-column declaration disagrees with its header")
        if len(header) != len(DAILY_FIELDS) and not allow_extra:
            raise ValueError("Extra daily columns require explicit allowance in the input receipt")
        if "delivered_column_count" in source and source["delivered_column_count"] != len(header):
            raise ValueError("Inventory delivered header count disagrees with its header")
    path = _safe_source(directory, source.get("preserved_file"))
    identity = _identity(path)
    if identity[2] != source["bytes"]:
        raise ValueError("Preserved source byte count disagrees with its receipt")
    source_id = f"{role}-{number:03d}"
    snapshot = out / "input_receipts" / f"{source_id}.json"
    with snapshot.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    snapshot.chmod(0o400)
    bundle = _Bundle(source_id, role, directory, receipt, receipt_path, receipt_identity,
                     hashlib.sha256(raw).hexdigest(), snapshot, path, identity, source["sha256"], allow_extra)
    _guard(bundle, rehash=True)
    return bundle


def _reader(bundle):
    if bundle.role == "daily":
        return _rows(bundle.source, allow_extra_columns=bundle.allow_extra_columns)
    return _market_rows(bundle.source)


def _date_preflight(bundle, db, start, end, last_permitted):
    _guard(bundle)
    rows, requested_rows, dates = 0, 0, Counter()

    def flush():
        db.executemany("INSERT INTO dates VALUES (?,?,?,?) ON CONFLICT(source_id,day) "
                       "DO UPDATE SET n=n+excluded.n",
                       ((bundle.source_id, bundle.role, day, count) for day, count in dates.items()))
        db.commit()
        dates.clear()

    with _reader(bundle) as (header, records):
        if header != bundle.receipt["source"]["observed_header"]:
            raise ValueError("Preserved source header disagrees with its inventory receipt")
        for record in records:
            day = _iso(record[4] if bundle.role == "daily" else record[0], "Source DlyCalDt")
            if day > last_permitted:
                raise ValueError("Source extends beyond development returns; final-period access blocked")
            rows += 1
            requested_rows += start <= day <= end
            dates[day] += 1
            if rows % _BATCH_ROWS == 0:
                flush()
        flush()
    _guard(bundle)
    if not rows or rows != bundle.receipt["all_rows"]["rows"]:
        raise ValueError("Preserved source record count disagrees with its inventory receipt")
    actual = db.execute("SELECT MIN(day),MAX(day),COUNT(*) FROM dates WHERE source_id=?",
                        (bundle.source_id,)).fetchone()
    recorded = bundle.receipt.get("actual_coverage", {})
    if any(recorded.get(key) != value for key, value in zip(
        ("first_date", "last_date", "distinct_dates"), actual, strict=True
    )):
        raise ValueError("Preserved source date coverage disagrees with its inventory receipt")
    bundle.rows, bundle.requested_rows = rows, requested_rows


@lru_cache(maxsize=8192)
def _short_return(text):
    kind, below = _return_classification(text)
    return kind, Decimal(text.strip()) if kind == "finite_numeric" else None, below


def _exact_return(text):
    if len(text) <= 128:
        return _short_return(text)
    kind, below = _return_classification(text)
    return kind, Decimal(text.strip()) if kind == "finite_numeric" else None, below


def _class_counts():
    return dict.fromkeys(_KINDS, 0)


def _add_class(counts, kind, below):
    counts[kind] += 1
    counts["finite_numeric_below_minus_one"] += bool(below)


def _market_values(bundle, db, start, end):
    _guard(bundle)
    rows, batch, batch_bytes = 0, [], 0
    all_counts, requested_counts = _class_counts(), _class_counts()

    def flush():
        nonlocal batch_bytes
        db.executemany("INSERT INTO market_values VALUES (?,?,1) ON CONFLICT(day,return_text) "
                       "DO UPDATE SET n=n+1", batch)
        db.commit()
        batch.clear()
        batch_bytes = 0

    with _market_rows(bundle.source) as (header, records):
        if header != bundle.receipt["source"]["observed_header"]:
            raise ValueError("Market source header changed after date preflight")
        for day, value in records:
            kind, _, below = _exact_return(value)
            _add_class(all_counts, kind, below)
            if start <= day <= end:
                _add_class(requested_counts, kind, below)
            batch.append((day, value))
            batch_bytes += 4 * (len(day) + len(value))
            rows += 1
            if len(batch) >= _BATCH_ROWS or batch_bytes >= _BATCH_BYTES:
                flush()
        flush()
    _guard(bundle)
    if rows != bundle.rows:
        raise ValueError("Market record count changed after date preflight")
    dates, duplicate_dates, row_excess, text_conflicts = db.execute(
        "SELECT COUNT(*),COALESCE(SUM(n>1),0),COALESCE(SUM(n-1),0),COALESCE(SUM(variants>1),0) "
        "FROM (SELECT SUM(n) n,COUNT(*) variants FROM market_values GROUP BY day)"
    ).fetchone()
    invalid = sum(all_counts[key] for key in _KINDS if key != "finite_numeric")
    evidence = {"rows": rows, "distinct_dates": dates, "duplicate_dates": duplicate_dates,
                "duplicate_date_row_excess": row_excess, "dates_with_conflicting_raw_text": text_conflicts,
                "return_classifications": all_counts, "requested_return_classifications": requested_counts,
                "invalid_rows": invalid, "unique_dates_and_valid_returns": not (duplicate_dates or invalid)}
    if duplicate_dates or invalid:
        raise SourceStageError("Independent market requires unique dates and finite returns at least -1",
                               evidence={"independent_market": evidence})
    return evidence


def _decimal_key(number):
    # Unlike Decimal.normalize(), this does not round to the active context.
    sign, digits, exponent = number.as_tuple()
    coefficient = "".join(map(str, digits)).rstrip("0")
    if not coefficient:
        return "0"
    return f"{sign}:{coefficient}:{exponent + len(digits) - len(coefficient)}"


class _ProjectionWriter:
    def __init__(self, out):
        self.out = out
        self.columns = {field.name: [] for field in PARQUET_SCHEMA}
        self.buffer_bytes = 0
        self.parts = []
        self.rows = 0

    def append(self, values, bundle, record_number, in_window):
        for field, value in zip(DAILY_FIELDS, values, strict=True):
            self.columns[field].append(value)
        self.columns["source_sha256"].append(bundle.source_sha256)
        self.columns["source_inventory_sha256"].append(bundle.receipt_sha256)
        self.columns["source_csv_record"].append(record_number)
        self.columns["in_requested_window"].append(in_window)
        self.buffer_bytes += 4 * sum(map(len, values)) + 160
        if len(self.columns["source_csv_record"]) >= _BATCH_ROWS or self.buffer_bytes >= _BATCH_BYTES:
            self.flush()

    def flush(self):
        count = len(self.columns["source_csv_record"])
        if not count:
            return
        if len(self.parts) >= _MAX_PARTS:
            raise ValueError("Projection exceeds bounded part-manifest limit")
        relative = f"projections/part-{len(self.parts) + 1:06d}.parquet"
        path = self.out / relative
        with path.open("xb") as handle:
            pq.write_table(pa.Table.from_pydict(self.columns, schema=PARQUET_SCHEMA), handle,
                           compression="zstd")
            handle.flush()
            os.fsync(handle.fileno())
        path.chmod(0o400)
        self.parts.append({"file": relative, "sha256": _hash(path), "bytes": path.stat().st_size, "rows": count})
        self.rows += count
        for values in self.columns.values():
            values.clear()
        self.buffer_bytes = 0


def _project_daily(bundles, market, db, writer, start, end):
    counts = {"requested_daily_rows": 0, "rows_with_market_date": 0, "rows_missing_market_date": 0,
              "comparable_rows": 0, "numeric_equal_rows": 0, "exact_text_equal_rows": 0,
              "numeric_equal_text_different_rows": 0, "numeric_mismatch_rows": 0}
    classes = _class_counts()
    raw_batch, numeric_batch, issues = Counter(), Counter(), Counter()
    batch_rows = batch_bytes = 0

    @lru_cache(maxsize=4096)
    def market_value(day):
        result = db.execute("SELECT return_text FROM market_values WHERE day=?", (day,)).fetchone()
        return None if result is None else (result[0], _exact_return(result[0])[1])

    def flush():
        nonlocal batch_rows, batch_bytes
        for table, values in (("daily_benchmark_text", raw_batch), ("daily_benchmark_numeric", numeric_batch)):
            db.executemany(f"INSERT INTO {table} VALUES (?,?,?) ON CONFLICT(day,value) "
                           "DO UPDATE SET n=n+excluded.n",
                           ((day, value, n) for (day, value), n in values.items()))
            values.clear()
        db.executemany("INSERT INTO issues VALUES (?,?,?) ON CONFLICT(day,kind) "
                       "DO UPDATE SET n=n+excluded.n",
                       ((day, kind, n) for (day, kind), n in issues.items()))
        issues.clear()
        db.commit()
        batch_rows = batch_bytes = 0

    for bundle in bundles:
        _guard(bundle)
        rows = 0
        with _rows(bundle.source, allow_extra_columns=bundle.allow_extra_columns) as (header, records):
            if header != bundle.receipt["source"]["observed_header"]:
                raise ValueError("Daily source header changed after date preflight")
            for record_number, values in enumerate(records, start=2):
                day, text = values[4], values[12]
                in_window = start <= day <= end
                writer.append(values, bundle, record_number, in_window)
                rows += 1
                if in_window:
                    counts["requested_daily_rows"] += 1
                    raw_batch[day, text] += 1
                    kind, number, below = _exact_return(text)
                    _add_class(classes, kind, below)
                    valid = kind == "finite_numeric" and not below
                    if valid:
                        numeric_batch[day, _decimal_key(number)] += 1
                    else:
                        issues[day, "invalid_daily_benchmark"] += 1
                    independent = market_value(day)
                    if independent is None:
                        counts["rows_missing_market_date"] += 1
                        issues[day, "missing_market"] += 1
                    else:
                        counts["rows_with_market_date"] += 1
                        if valid:
                            counts["comparable_rows"] += 1
                            if number == independent[1]:
                                counts["numeric_equal_rows"] += 1
                                if text == independent[0]:
                                    counts["exact_text_equal_rows"] += 1
                                else:
                                    counts["numeric_equal_text_different_rows"] += 1
                                    issues[day, "numeric_equal_text_different"] += 1
                            else:
                                counts["numeric_mismatch_rows"] += 1
                                issues[day, "numeric_mismatch"] += 1
                    batch_bytes += 4 * len(text) + 128
                    batch_rows += 1
                    if batch_rows >= _BATCH_ROWS or batch_bytes >= _BATCH_BYTES:
                        flush()
        flush()
        writer.flush()
        _guard(bundle)
        if rows != bundle.rows:
            raise ValueError("Daily record count changed after date preflight")
    for kind in ("missing_market", "invalid_daily_benchmark", "numeric_mismatch", "numeric_equal_text_different"):
        counts[f"{kind}_dates"] = db.execute("SELECT COUNT(*) FROM issues WHERE kind=?", (kind,)).fetchone()[0]
    for table, label in (("daily_benchmark_text", "distinct_raw_texts"),
                         ("daily_benchmark_numeric", "conflicting_numeric_values")):
        counts[f"daily_dates_with_{label}"] = db.execute(
            f"SELECT COUNT(*) FROM (SELECT day FROM {table} GROUP BY day HAVING COUNT(*)>1)"
        ).fetchone()[0]
    counts["daily_benchmark_classifications"] = classes
    counts["independent_market"] = market
    counts["comparison"] = "exact Decimal numeric equality; source text equality reported separately"
    counts["scope"] = "all daily rows in the requested window, including repeated records"
    counts["fallback_used"] = False
    counts["reconciliation_passed"] = not (
        counts["rows_missing_market_date"] or counts["numeric_mismatch_rows"]
        or counts["invalid_daily_benchmark_dates"] or counts["daily_dates_with_conflicting_numeric_values"]
    )
    return counts


def _coverage(db, role, start, end, source_id=None):
    sessions = set(calendar().sessions.strftime("%Y-%m-%d"))
    first_session, last_session = min(sessions), max(sessions)
    expected = {day for day in sessions if start <= day <= end}
    missing = expected.copy()
    actual_first = actual_last = requested_first = requested_last = None
    dates = requested_dates = rows = requested_rows = before = after = non_sessions = non_session_rows = outside = outside_rows = 0
    where, params = ("role=?", (role,)) if source_id is None else ("source_id=?", (source_id,))
    for day, count in db.execute(f"SELECT day,SUM(n) FROM dates WHERE {where} GROUP BY day ORDER BY day", params):
        actual_first = actual_first or day
        actual_last = day
        dates += 1
        rows += count
        if start <= day <= end:
            requested_first = requested_first or day
            requested_last = day
            requested_dates += 1
            requested_rows += count
            missing.discard(day)
        elif day < start:
            before += count
        else:
            after += count
        if day < first_session or day > last_session:
            outside += 1
            outside_rows += count
        elif day not in sessions:
            non_sessions += 1
            non_session_rows += count
    return {"first_date": actual_first, "last_date": actual_last, "distinct_dates": dates, "rows": rows,
            "requested_first_date": requested_first, "requested_last_date": requested_last,
            "requested_distinct_dates": requested_dates, "requested_rows": requested_rows,
            "rows_before_request": before, "rows_after_request": after,
            "expected_xnys_sessions": len(expected), "missing_xnys_sessions": sorted(missing),
            "covered_xnys_sessions": len(expected) - len(missing),
            "non_xnys_date_count": non_sessions, "non_xnys_row_count": non_session_rows,
            "outside_calendar_date_count": outside, "outside_calendar_row_count": outside_rows}


def _overlap(db, start, end):
    result = {}
    for label, where, params in (("all_source_dates", "", ()),
                                  ("requested_dates", "AND day BETWEEN ? AND ?", (start, end))):
        dates, rows = db.execute(
            "SELECT COUNT(*),COALESCE(SUM(n),0) FROM (SELECT day,SUM(n) n FROM dates "
            f"WHERE role='daily' {where} GROUP BY day HAVING COUNT(*)>1)", params
        ).fetchone()
        result[label] = {"dates_in_multiple_daily_batches": dates, "rows_on_shared_dates": rows}
    result["overlap_is_date_coverage_not_security_row_equality"] = True
    return result


def _write_json(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o400)


def stage_manual_development(daily_inventories, market_inventory, *, request_start, request_end,
                             output, config, repo_root="."):
    """Project preserved daily records and reconcile their attached benchmark.

    Successful projection can contain explicit reconciliation issues. It never
    grants source approval. Invalid or duplicate independent-market records stop
    the operation before daily return interpretation or Parquet projection.
    """
    verify_lock(config, Path(repo_root) / "configs" / "protocol.lock.json")
    start, end = _iso(request_start, "Request start"), _iso(request_end, "Request end")
    first_permitted = year_start_window(config["initial_train_start"], config)["liquidity_start"]
    last_permitted = development_return_end(config)
    if start < first_permitted or start > end or end > last_permitted:
        raise ValueError("Stage request must stay within the frozen development source envelope")
    if not isinstance(daily_inventories, (list, tuple)) or not 1 <= len(daily_inventories) <= _MAX_SOURCES:
        raise ValueError("Supply between 1 and 64 daily inventory directories")
    out = _private_directory(output, repo_root)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    (out / "input_receipts").mkdir(mode=0o700)
    (out / "projections").mkdir(mode=0o700)
    protocol_sha256 = canonical_hash(config)
    bundles = [_load_bundle(directory, "daily", index, out, protocol_sha256, last_permitted)
               for index, directory in enumerate(daily_inventories, start=1)]
    market_bundle = _load_bundle(market_inventory, "market", 1, out, protocol_sha256, last_permitted)
    all_bundles = [*bundles, market_bundle]
    if len({bundle.source_sha256 for bundle in all_bundles}) != len(all_bundles):
        raise ValueError("The same preserved source was supplied more than once")
    with tempfile.TemporaryDirectory(prefix="source-stage-", dir=out) as temporary:
        with closing(sqlite3.connect(str(Path(temporary) / "stage.sqlite3"))) as db:
            db.execute("PRAGMA cache_size=-16384")
            db.execute("PRAGMA temp_store=FILE")
            db.execute("CREATE TABLE dates(source_id TEXT,role TEXT,day TEXT,n INTEGER NOT NULL,"
                       "PRIMARY KEY(source_id,day)) WITHOUT ROWID")
            db.execute("CREATE TABLE market_values(day TEXT,return_text TEXT,n INTEGER NOT NULL,"
                       "PRIMARY KEY(day,return_text)) WITHOUT ROWID")
            for table in ("daily_benchmark_text", "daily_benchmark_numeric"):
                db.execute(f"CREATE TABLE {table}(day TEXT,value TEXT,n INTEGER NOT NULL,"
                           "PRIMARY KEY(day,value)) WITHOUT ROWID")
            db.execute("CREATE TABLE issues(day TEXT,kind TEXT,n INTEGER NOT NULL,"
                       "PRIMARY KEY(day,kind)) WITHOUT ROWID")
            # This complete ALL-source preflight is deliberately separate from
            # every numeric operation. Later batches cannot expose holdout values.
            for bundle in all_bundles:
                _date_preflight(bundle, db, start, end, last_permitted)
            for bundle in all_bundles:
                _guard(bundle)
            try:
                market = _market_values(market_bundle, db, start, end)
            except SourceStageError as exc:
                for bundle in all_bundles:
                    _guard(bundle, rehash=True)
                _write_json(out / "stage_failure.json", {
                    "schema_version": 1, "status": "INDEPENDENT_MARKET_INVALID_STAGE_REFUSED",
                    "protocol_sha256": protocol_sha256,
                    "complete_all_source_date_pass_before_numeric_interpretation": True,
                    **exc.evidence, "model_ready": False, "source_approvals": 0,
                    "prior_arithmetic_review_modified": False, "final_period_opened": False,
                })
                raise
            writer = _ProjectionWriter(out)
            reconciliation = _project_daily(bundles, market, db, writer, start, end)
            daily_coverage, market_coverage = _coverage(db, "daily", start, end), _coverage(db, "market", start, end)
            reconciliation["requested_window_numerically_reconciled"] = bool(
                reconciliation["reconciliation_passed"]
                and not daily_coverage["missing_xnys_sessions"]
                and not market_coverage["missing_xnys_sessions"]
            )
            if writer.rows != sum(bundle.rows for bundle in bundles):
                raise ValueError("Projection did not preserve every daily source record")
            sources = []
            for bundle in all_bundles:
                sources.append({"source_id": bundle.source_id, "role": bundle.role,
                                "inventory_directory": str(bundle.directory),
                                "inventory_receipt_file": str(bundle.receipt_snapshot.relative_to(out)),
                                "inventory_receipt_sha256": bundle.receipt_sha256,
                                "preserved_file": bundle.receipt["source"]["preserved_file"],
                                "source_sha256": bundle.source_sha256, "source_bytes": bundle.source_identity[2],
                                "observed_header": bundle.receipt["source"]["observed_header"],
                                "allow_extra_columns": bundle.allow_extra_columns,
                                "rows": bundle.rows, "requested_rows": bundle.requested_rows,
                                "actual_coverage": _coverage(db, bundle.role, start, end, bundle.source_id),
                                "inventory_row_count_verified": True, "original_source_retained_in_place": True})
            receipt = {
                "schema_version": 1, "status": "RAW_MANUAL_WRDS_SOURCE_PROJECTION_NOT_SOURCE_APPROVED",
                "created_at": datetime.now(timezone.utc).isoformat(), "protocol_sha256": protocol_sha256,
                "code_sha256": _hash(Path(__file__)),
                "request": {"start": start, "end": end, "first_permitted_request_date": first_permitted,
                            "last_permitted_development_return_date": last_permitted},
                "sources": sources,
                "projection": {"fields": list(DAILY_FIELDS), "provenance_fields": list(PROVENANCE_FIELDS),
                               "parts": writer.parts, "rows": writer.rows,
                               "requested_rows": sum(bundle.requested_rows for bundle in bundles),
                               "all_source_records_preserved": True, "duplicate_rows_retained": True,
                               "duplicate_comparison_scope": "required_13_fields_in_canonical_order",
                               "stage_security_key_duplicates_recomputed": False,
                               "full_delivered_row_duplicates_checked": False,
                               "extra_delivered_fields_retained_in_original_sources": True,
                               "source_csv_record_numbering": "CSV header is record 1; multiline values do not add records",
                               "licensed_raw_projection_private_only": True},
                "coverage": {"daily_union": daily_coverage, "independent_market": market_coverage,
                             "batch_overlap": _overlap(db, start, end),
                             "security_universe_completeness_verified": False},
                "reconciliation": reconciliation,
                "complete_all_source_date_pass_before_numeric_interpretation": True,
                "source_hashes_verified_before_and_after_staging": True,
                "input_receipts_snapshotted_and_hash_bound": True,
                "rows_dropped": 0, "values_filled": 0, "values_normalized": 0,
                "source_flags_interpreted": False, "approved_returns_created": False,
                "labels_created": False, "universe_created": False,
                "model_ready": False, "source_approvals": 0,
                "prior_arithmetic_review_modified": False, "final_period_opened": False,
            }
    for bundle in all_bundles:
        _guard(bundle, rehash=True)
    _write_json(out / "receipt.json", receipt)
    return receipt


def aggregate_summary(receipt):
    """CLI-safe output: no source rows, identifiers, paths, or arbitrary metadata."""
    return {"status": receipt["status"], "protocol_sha256": receipt["protocol_sha256"],
            "daily_source_count": sum(source["role"] == "daily" for source in receipt["sources"]),
            "source_sha256": [source["source_sha256"] for source in receipt["sources"]],
            "projection_rows": receipt["projection"]["rows"],
            "requested_projection_rows": receipt["projection"]["requested_rows"],
            "parquet_parts": len(receipt["projection"]["parts"]),
            "coverage": receipt["coverage"], "reconciliation": receipt["reconciliation"],
            "model_ready": False, "source_approvals": 0,
            "prior_arithmetic_review_modified": False, "final_period_opened": False}
