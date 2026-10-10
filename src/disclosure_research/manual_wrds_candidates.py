"""Bounded, provisional numerical candidates from a hash-bound manual source stage.

This is not an import-market adapter. It supplies neither historical availability
nor approved identities, terminal events, labels, or a research-ready universe.
"""

import hashlib
import json
import math
import re
import tempfile
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .manual_wrds_intake import DAILY_FIELDS, _fd_identity, _hash, _identity, _iso, _private_directory
from .market_data import development_return_end
from .protocol import canonical_hash, verify_lock
from .timing import calendar
from .universe import year_start_window

STAGE_STATUS = "RAW_MANUAL_WRDS_SOURCE_PROJECTION_NOT_SOURCE_APPROVED"
STATUS = "PROVISIONAL_MANUAL_WRDS_NUMERICAL_CANDIDATES_NOT_SOURCE_APPROVED"
PROVENANCE = ("source_sha256", "source_inventory_sha256", "source_csv_record",
              "in_requested_window")
_BATCH = 50_000
_BATCH_BYTES = 32 * 1024 * 1024
_PART_ROWS = 250_000
_HASH = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[1-9][0-9]*")
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?")
_FLAG_CODES = {
    "return_missing_flag": {"NA", "MV", "NT", "NS", "MP", "RA", "GP", "DP", "DM", "DG"},
    "price_flag": {"TR", "BA", "NT", "DA", "SU", "MP", "DP", "HA", "DM"},
}

CANDIDATE_SCHEMA = pa.schema([
    ("security_id", pa.string()), ("source_permco", pa.string()), ("session", pa.string()),
    ("projection_sha256", pa.string()), ("projection_record_count", pa.int64()),
    ("projection_source_file_count", pa.int64()),
    ("security_session_projection_variants", pa.int64()),
    ("representative_source_sha256", pa.string()),
    ("representative_source_inventory_sha256", pa.string()),
    ("representative_source_csv_record", pa.int64()),
    ("return_missing_flag", pa.string()), ("price_flag", pa.string()),
    ("delisting_flag", pa.string()),
    ("total_return_candidate", pa.float64()), ("return_status", pa.string()),
    ("market_cap_usd_candidate", pa.float64()), ("capitalization_status", pa.string()),
    ("closing_price_volume_usd_candidate", pa.float64()), ("liquidity_status", pa.string()),
    ("delisting_status", pa.string()),
])


def _inside(root: Path, name: str) -> Path:
    if (not isinstance(name, str) or not name or len(name) > 512 or "\\" in name
            or Path(name).is_absolute()
            or any(part in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", part)
                   for part in name.split("/"))):
        raise ValueError("Stage part must use a safe relative file path")
    path = root / name
    current = root
    for part in name.split("/"):
        current /= part
        if current.is_symlink():
            raise ValueError("Stage part paths may not traverse symbolic links")
    if not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError("Stage part must be a regular file inside its bundle")
    return path


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Source-stage receipt has duplicate JSON keys")
        result[key] = value
    return result


def _unchanged(guards: dict[Path, tuple]) -> None:
    if any(_identity(path) != expected for path, expected in guards.items()):
        raise ValueError("A source-stage file changed during candidate construction")


def _stage_inputs(stage: Path, config: dict):
    stage = stage.resolve()
    receipt_path = _inside(stage, "receipt.json")
    guards = {receipt_path: _identity(receipt_path)}
    if guards[receipt_path][2] > 16 * 1024 * 1024:
        raise ValueError("Source-stage receipt exceeds the bounded metadata size")
    with receipt_path.open("rb") as handle:
        if _fd_identity(handle) != guards[receipt_path]:
            raise ValueError("Source-stage receipt changed before reading")
        receipt_bytes = handle.read(16 * 1024 * 1024 + 1)
        if (len(receipt_bytes) > 16 * 1024 * 1024
                or _fd_identity(handle) != guards[receipt_path]
                or _identity(receipt_path) != guards[receipt_path]):
            raise ValueError("Source-stage receipt changed while reading or exceeded its size limit")
    manifest = json.loads(receipt_bytes, object_pairs_hook=_unique_json)
    if (manifest.get("schema_version") != 1 or manifest.get("status") != STAGE_STATUS
            or manifest.get("protocol_sha256") != canonical_hash(config)
            or manifest.get("model_ready") is not False
            or manifest.get("source_approvals") != 0
            or manifest.get("final_period_opened") is not False):
        raise ValueError("Source stage does not match the unapproved development contract")
    request = manifest["request"]
    start, end = _iso(request["start"], "Stage start"), _iso(request["end"], "Stage end")
    limit = development_return_end(config)
    first = year_start_window(config["initial_train_start"], config)["liquidity_start"]
    if (start < first or start > end or end > limit
            or request["last_permitted_development_return_date"] != limit
            or request.get("first_permitted_request_date", first) != first):
        raise ValueError("Source-stage request exceeds the locked development window")
    projection = manifest["projection"]
    if (projection.get("fields") != list(DAILY_FIELDS)
            or projection.get("provenance_fields") != list(PROVENANCE)
            or projection.get("all_source_records_preserved") is not True
            or projection.get("duplicate_rows_retained") is not True
            or projection.get("duplicate_comparison_scope")
            != "required_13_fields_in_canonical_order"):
        raise ValueError("Source projection or preservation contract is unsupported")
    reconciled = manifest["reconciliation"].get("requested_window_numerically_reconciled")
    if not isinstance(reconciled, bool):
        raise ValueError("Source stage must explicitly report benchmark reconciliation")
    sources = {}
    for item in manifest["sources"]:
        if item["role"] != "daily":
            continue
        pair = (item["source_sha256"], item["inventory_receipt_sha256"])
        if (not all(isinstance(value, str) and _HASH.fullmatch(value) for value in pair)
                or pair in sources or type(item["rows"]) is not int or item["rows"] < 1):
            raise ValueError("Daily source provenance is missing, duplicated, or invalid")
        sources[pair] = item["rows"]
    parts, names = [], set()
    for item in projection["parts"]:
        if item["file"] in names:
            raise ValueError("A source projection part is listed more than once")
        names.add(item["file"])
        path = _inside(stage, item["file"])
        guards[path] = _identity(path)
        if (type(item["rows"]) is not int or item["rows"] < 1
                or type(item["bytes"]) is not int or item["bytes"] != guards[path][2]
                or not isinstance(item["sha256"], str) or not _HASH.fullmatch(item["sha256"])
                or _hash(path) != item["sha256"]):
            raise ValueError("Source projection size or SHA-256 does not match its receipt")
        parquet = pq.ParquetFile(path)
        schema = parquet.schema_arrow
        expected = {**{name: pa.string() for name in DAILY_FIELDS},
                    "source_sha256": pa.string(), "source_inventory_sha256": pa.string(),
                    "source_csv_record": pa.int64(), "in_requested_window": pa.bool_()}
        if (schema.names != list(expected)
                or any(schema.field(name).type != kind for name, kind in expected.items())
                or parquet.metadata.num_rows != item["rows"]):
            raise ValueError("Source projection schema or row count does not match its receipt")
        parts.append((path, item["rows"]))
    if not parts or not sources:
        raise ValueError("A nonempty daily source projection is required")
    _unchanged(guards)
    return manifest, receipt_bytes, parts, sources, guards


def _preflight(parts, sources, manifest) -> dict:
    """Visit dates and provenance in every part before interpreting any value."""
    request = manifest["request"]
    start, end = request["start"], request["end"]
    limit = request["last_permitted_development_return_date"]
    counts, dates = Counter(), Counter()
    total = requested = 0
    columns = ["dlycaldt", *PROVENANCE]
    for path, expected in parts:
        seen = 0
        for batch in pq.ParquetFile(path).iter_batches(batch_size=_BATCH, columns=columns):
            if any(batch.column(i).null_count for i in range(batch.num_columns)):
                raise ValueError("Source dates and provenance may not be null")
            for row in batch.to_pylist():
                day = _iso(row["dlycaldt"], "Projected DlyCalDt")
                if day > limit:
                    raise ValueError("Projected date exceeds development; holdout blocked")
                inside = start <= day <= end
                if row["in_requested_window"] != inside:
                    raise ValueError("Projected requested-window flag contradicts the date")
                pair = row["source_sha256"], row["source_inventory_sha256"]
                if (pair not in sources or row["source_csv_record"] < 2
                        or row["source_csv_record"] > sources[pair] + 1):
                    raise ValueError("Projected record does not match bound source provenance")
                if row["source_csv_record"] != counts[pair] + 2:
                    raise ValueError("Source CSV record provenance is repeated, missing, or out of order")
                counts[pair] += 1
                dates[day] += 1
                seen += 1
                requested += int(inside)
        if seen != expected:
            raise ValueError("Projected part row count changed during date preflight")
        total += seen
    projection = manifest["projection"]
    if (dict(counts) != sources or total != projection["rows"]
            or requested != projection["requested_rows"]):
        raise ValueError("Projected counts disagree with the source-stage receipt")
    expected_sessions = {s for s in calendar().sessions.strftime("%Y-%m-%d") if start <= s <= end}
    actual = {day for day in dates if start <= day <= end}
    return {"source_rows": total, "requested_rows": requested,
            "outside_request_rows_retained_in_source_stage": total - requested,
            "expected_sessions": len(expected_sessions), "requested_dates": len(actual),
            "missing_expected_sessions": len(expected_sessions - actual),
            "unexpected_requested_dates": len(actual - expected_sessions)}


def _number(value: str) -> tuple[Decimal | None, str | None]:
    if not value.strip():
        return None, "missing_numeric_value"
    if len(value) > 256 or not _NUMBER.fullmatch(value):
        return None, "unsupported_numeric_text"
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None, "unsupported_numeric_text"
    if not number.is_finite():
        return None, "nonfinite_value"
    if not number.is_zero() and abs(number.adjusted()) > 10_000:
        return None, "numeric_exponent_outside_candidate_range"
    return number, None


def _as_float(value: Decimal, *, positive: bool = False):
    try:
        numeric = float(value)
    except (OverflowError, ValueError):
        return None
    if (not math.isfinite(numeric) or (positive and numeric <= 0)
            or (not value.is_zero() and numeric == 0)):
        return None
    return numeric


def _candidate(row: dict, sessions: set[str]) -> dict:
    representative = row["representative"]
    out = {
        "security_id": row["permno"], "source_permco": row["permco"],
        "session": row["dlycaldt"], "projection_sha256": row["projection_sha256"],
        "projection_record_count": row["record_count"],
        "projection_source_file_count": row["source_file_count"],
        "security_session_projection_variants": row["variants"],
        "representative_source_sha256": representative["source_sha256"],
        "representative_source_inventory_sha256": representative["source_inventory_sha256"],
        "representative_source_csv_record": representative["source_csv_record"],
        "return_missing_flag": row["dlyretmissflg"], "price_flag": row["dlyprcflg"],
        "delisting_flag": row["dlydelflg"], "total_return_candidate": None,
        "market_cap_usd_candidate": None, "closing_price_volume_usd_candidate": None,
        "delisting_status": ("PAYOFF_AND_TERMINATION_REVIEW_REQUIRED" if row["dlydelflg"] == "Y"
                             else "NO_DELISTING_FLAG_ON_RECORD" if row["dlydelflg"] == "N"
                             else "UNSUPPORTED_DELISTING_FLAG"),
    }
    shared = ("conflicting_security_date_projection" if row["variants"] > 1 else
              "invalid_permanent_identifier" if not (_ID.fullmatch(row["permno"])
                                                     and _ID.fullmatch(row["permco"])) else
              "not_an_exchange_session" if row["dlycaldt"] not in sessions else None)
    if shared:
        out.update(return_status=shared, capitalization_status=shared, liquidity_status=shared)
        return out

    reason = ("unresolved_return_flag" if row["dlyretmissflg"] != "NA" else
              "unsupported_delisting_flag" if row["dlydelflg"] not in {"N", "Y"} else None)
    if not reason:
        value, reason = _number(row["dlyret"])
        if not reason and value < Decimal(-1):
            reason = "return_below_minus_one"
        if not reason:
            out["total_return_candidate"] = _as_float(value)
            if out["total_return_candidate"] is None:
                reason = "not_representable_as_finite_float"
    out["return_status"] = reason or "CANDIDATE_REQUIRES_SOURCE_REVIEW"

    cap, reason = _number(row["dlycap"])
    if not reason and cap <= 0:
        reason = "nonpositive_capitalization"
    if not reason:
        with localcontext() as context:
            context.prec = max(34, len(cap.as_tuple().digits) + 4)
            out["market_cap_usd_candidate"] = _as_float(cap * 1000, positive=True)
        if out["market_cap_usd_candidate"] is None:
            reason = "not_representable_as_positive_finite_float"
    out["capitalization_status"] = reason or "CANDIDATE_REQUIRES_SOURCE_REVIEW"

    reason = "unsupported_liquidity_price_flag" if row["dlyprcflg"] not in {"TR", "BA"} else None
    if not reason:
        price, reason = _number(row["dlyprc"])
        if not reason and price <= 0:
            reason = "nonpositive_ciz_price"
    if not reason:
        volume, reason = _number(row["dlyvol"])
        if not reason and volume < 0:
            reason = "negative_volume"
    if not reason:
        with localcontext() as context:
            context.prec = max(34, len(price.as_tuple().digits) + len(volume.as_tuple().digits) + 2)
            proxy = _as_float(price * volume, positive=volume > 0)
        out["closing_price_volume_usd_candidate"] = proxy
        if proxy is None:
            reason = "not_representable_as_nonnegative_finite_float"
    out["liquidity_status"] = reason or "CANDIDATE_REQUIRES_SOURCE_REVIEW"
    return out


def _month_windows(start: str, end: str):
    current = date.fromisoformat(start)
    last = date.fromisoformat(end)
    while current <= last:
        next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
        through = min(last, next_month - timedelta(days=1))
        yield current.isoformat(), through.isoformat()
        current = next_month


def build_candidates(stage_directory: str | Path, *, output: str | Path,
                     config: dict, repo_root: str | Path) -> dict:
    """Create source-bound candidates; never mark a row or bundle model-ready."""
    repo = Path(repo_root).resolve()
    verify_lock(config, repo / "configs" / "protocol.lock.json")
    out = _private_directory(output, repo)
    manifest, source_receipt, parts, sources, guards = _stage_inputs(Path(stage_directory), config)
    coverage = _preflight(parts, sources, manifest)
    _unchanged(guards)
    sessions = set(calendar().sessions.strftime("%Y-%m-%d"))
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".wrds-candidates-", dir=out.parent) as temp:
        work = Path(temp)
        bundle = work / "bundle"
        bundle.mkdir(mode=0o700)
        (bundle / "candidates").mkdir(mode=0o700)
        snapshot = bundle / "source_stage_receipt.json"
        snapshot.write_bytes(source_receipt)
        snapshot.chmod(0o400)
        db = duckdb.connect(str(work / "work.duckdb"), config={
            "memory_limit": "1GB", "threads": 2, "preserve_insertion_order": False,
            "temp_directory": str(work / "spill"),
        })
        try:
            db.read_parquet([str(path) for path, _ in parts]).create_view("raw")
            nulls = " OR ".join(f'"{field}" IS NULL' for field in DAILY_FIELDS)
            if db.execute(f"SELECT COUNT(*) FROM raw WHERE {nulls}").fetchone()[0]:
                raise ValueError("Raw projected source fields may not contain nulls")
            lengths = " + ".join(f'length("{field}")' for field in DAILY_FIELDS)
            largest_row = db.execute(f"SELECT MAX({lengths}) FROM raw").fetchone()[0]
            if 4 * largest_row + 4096 > _BATCH_BYTES:
                raise ValueError("One source row exceeds the candidate reader byte budget")
            batch_rows = min(_BATCH, _BATCH_BYTES // (4 * largest_row + 4096))
            fields = ", ".join(f'"{name}"' for name in DAILY_FIELDS)
            representative = ("struct_pack(source_sha256 := source_sha256, "
                              "source_inventory_sha256 := source_inventory_sha256, "
                              "source_csv_record := source_csv_record)")
            order = ["dlycaldt", "permno", *[name for name in DAILY_FIELDS
                                           if name not in {"dlycaldt", "permno"}]]
            projected = ", ".join(f'p."{name}"' for name in DAILY_FIELDS)
            outputs, counts = [], {name: Counter() for name in
                                   ("return_status", "capitalization_status", "liquidity_status",
                                    "delisting_status", "return_missing_flag", "price_flag")}
            candidate_rows = part_rows = 0
            conflict_keys = distinct = raw_count = partitions = 0
            writer = path = None

            def close_part():
                nonlocal writer, part_rows
                if writer is None:
                    return
                writer.close()
                path.chmod(0o400)
                outputs.append({"file": str(path.relative_to(bundle)), "rows": part_rows,
                                "bytes": path.stat().st_size, "sha256": _hash(path)})
                writer, part_rows = None, 0

            try:
                # A security/date key belongs to exactly one month. Grouping
                # across every source inside each month preserves exact global
                # duplicate/conflict semantics without one 23-million-key hash table.
                for first, last in _month_windows(manifest["request"]["start"], manifest["request"]["end"]):
                    db.execute(f"CREATE OR REPLACE TABLE projections AS SELECT {fields}, "
                               "COUNT(*)::BIGINT record_count, "
                               "COUNT(DISTINCT source_sha256)::BIGINT source_file_count, "
                               f"arg_min({representative}, {representative}) representative "
                               f"FROM raw WHERE in_requested_window AND dlycaldt BETWEEN ? AND ? GROUP BY {fields}",
                               [first, last])
                    db.execute("CREATE OR REPLACE TABLE conflicts AS SELECT permno, dlycaldt, "
                               "COUNT(*)::BIGINT variants FROM projections "
                               "GROUP BY permno, dlycaldt HAVING COUNT(*) > 1")
                    conflict_keys += db.execute("SELECT COUNT(*) FROM conflicts").fetchone()[0]
                    distinct += db.execute("SELECT COUNT(*) FROM projections").fetchone()[0]
                    raw_count += db.execute("SELECT COALESCE(SUM(record_count),0) FROM projections").fetchone()[0]
                    partitions += 1
                    cursor = db.execute("SELECT p.*, COALESCE(c.variants,1)::BIGINT variants, "
                                        f"sha256(to_json(list_value({projected}))) projection_sha256 "
                                        "FROM projections p LEFT JOIN conflicts c USING(permno,dlycaldt) "
                                        + "ORDER BY " + ", ".join(f'p."{name}"' for name in order))
                    for batch in cursor.fetch_record_batch(batch_rows):
                        rows = [_candidate(row, sessions) for row in batch.to_pylist()]
                        for row in rows:
                            for name, count in counts.items():
                                value = row[name]
                                if name in _FLAG_CODES and value not in _FLAG_CODES[name]:
                                    value = "__UNRECOGNIZED__"
                                count[value] += 1
                        table = pa.Table.from_pylist(rows, schema=CANDIDATE_SCHEMA)
                        offset = 0
                        while offset < len(rows):
                            if writer is None:
                                path = bundle / "candidates" / f"part-{len(outputs) + 1:06d}.parquet"
                                writer = pq.ParquetWriter(path, CANDIDATE_SCHEMA, compression="zstd")
                            size = min(len(rows) - offset, _PART_ROWS - part_rows)
                            writer.write_table(table.slice(offset, size))
                            part_rows += size
                            offset += size
                            if part_rows == _PART_ROWS:
                                close_part()
                        candidate_rows += len(rows)
                close_part()
            finally:
                if writer is not None:
                    writer.close()
            if candidate_rows != distinct:
                raise ValueError("Candidate outputs do not account for every distinct projection")
            if raw_count != coverage["requested_rows"]:
                raise ValueError("Monthly deduplication did not account for every requested source record")
        finally:
            db.close()
        _unchanged(guards)
        receipt = {
            "schema_version": 1, "status": STATUS, "created_at": datetime.now(timezone.utc).isoformat(),
            "protocol_sha256": canonical_hash(config), "code_sha256": _hash(Path(__file__)),
            "source_stage_directory": str(Path(stage_directory).resolve()),
            "source_stage_receipt_sha256": hashlib.sha256(source_receipt).hexdigest(),
            "source_stage_receipt_snapshot": "source_stage_receipt.json",
            "request": manifest["request"], "coverage": coverage,
            "reconciliation": {"requested_window_numerically_reconciled":
                               manifest["reconciliation"]["requested_window_numerically_reconciled"],
                               "details_in_bound_source_stage_receipt": True},
            "projection": {"candidate_rows": candidate_rows, "source_records": raw_count,
                           "equivalent_13_field_record_excess": raw_count - candidate_rows,
                           "conflicting_security_date_keys": conflict_keys,
                           "all_conflicting_projections_retained_with_numeric_candidates_withheld": True,
                           "comparison_scope": "exact_raw_required_13_fields_only",
                           "full_delivered_row_equality_claimed": False,
                           "fingerprint": "sha256 of UTF-8 DuckDB JSON array in canonical 13-field order",
                           "all_original_record_provenance_retained_in_bound_source_stage": True,
                           "representative_rule": "lexicographic source SHA, inventory SHA, CSV record tuple",
                           "parts": outputs},
            "counts": {key: dict(sorted(value.items())) for key, value in counts.items()},
            "policies": {
                "returns": "DlyRet unchanged only for NA and finite value >= -1; no separate DLRET added",
                "numeric_text": "up to 256 ASCII decimal/scientific-notation characters, without whitespace",
                "float_conversion": "nonzero values that overflow or underflow to zero are withheld",
                "capitalization": "positive DlyCap * 1000 USD; missing/zero/negative/overflow withheld",
                "liquidity": "positive DlyPrc * nonnegative raw DlyVol; TR/BA only; recorded zero volume retained",
                "ciz_price": "negative prices withheld; no absolute-value repair",
                "delisting": "Y is a candidate requiring payoff and termination review; no terminal_event supplied",
                "conflicts": "all numerical candidates withheld for every conflicting security/date projection",
                "source_verification": "stage receipt and Parquet hashes verified; original CSV hashes bind through upstream stage",
                "outside_request": "excluded from candidate calculation and preserved in upstream raw projection",
                "aggregate_flags": "documented code sets plus __UNRECOGNIZED__ bucket; exact flags remain in private rows",
            },
            "processing": {"duckdb_memory_limit": "1GB", "duckdb_threads": 2,
                           "grouping_partitions": partitions, "grouping_partition_unit": "calendar_month",
                           "source_ordinals_verified_in_streaming_order": True,
                           "maximum_observed_raw_row_characters": largest_row,
                           "arrow_reader_batch_rows": batch_rows,
                           "estimated_python_batch_byte_target": _BATCH_BYTES,
                           "maximum_output_part_rows": _PART_ROWS},
            "model_ready": False, "source_approvals": 0, "prior_arithmetic_review_modified": False,
            "historical_identity_supplied": False, "historical_availability_supplied": False,
            "approved_terminal_events_supplied": False, "actual_event_labels_generated": False,
            "final_period_opened": False,
        }
        (bundle / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        (bundle / "receipt.json").chmod(0o400)
        bundle.rename(out)
    return receipt
