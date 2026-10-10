"""Private, exact diagnostics for a preserved manual WRDS benchmark discrepancy.

Only dates, provenance, and attached benchmark text are grouped. Original stock
records stay in the source stage. Rounded agreement is diagnostic evidence only;
it never substitutes for exact equality or grants source approval.
"""

import hashlib
import os
import re
import sqlite3
import tempfile
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, Inexact, InvalidOperation, ROUND_HALF_EVEN, localcontext
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .manual_wrds_candidates import _inside, _preflight, _stage_inputs, _unchanged
from .manual_wrds_intake import DAILY_FIELDS, _hash, _identity, _iso, _private_directory
from .manual_wrds_market import _market_rows
from .manual_wrds_stage import _read_receipt, _safe_source, _write_json
from .protocol import canonical_hash, verify_lock
from .timing import calendar

STATUS = "PRIVATE_MANUAL_WRDS_BENCHMARK_DIAGNOSTIC_NOT_SOURCE_APPROVED"
_SHA = re.compile(r"[0-9a-f]{64}")
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?")
_HEADER = re.compile(r"[A-Za-z_][A-Za-z_0-9]{0,127}")
_MAX_TEXT = 256
_MAX_EXPONENT = 1000
_MAX_PRECISION = 2500
_BATCH = 4096
_ROUND_PLACES = (4, 5, 6, 7, 8, 10, 12)
MISMATCH_SCHEMA = pa.schema([
    ("date", pa.string()), ("daily_source_sha256", pa.string()),
    ("daily_inventory_receipt_sha256", pa.string()),
    ("market_source_sha256", pa.string()), ("market_inventory_receipt_sha256", pa.string()),
    ("market_source_csv_record", pa.int64()),
    ("daily_raw_text", pa.string()), ("market_raw_text", pa.string()),
    ("daily_minus_independent_exact", pa.string()), ("daily_rows_affected", pa.int64()),
    ("daily_decimal_quantum_exponent", pa.int32()),
    ("market_decimal_quantum_exponent", pa.int32()),
    ("daily_literal_significant_digits", pa.int32()),
    ("market_literal_significant_digits", pa.int32()),
    ("daily_scientific_notation", pa.bool_()), ("market_scientific_notation", pa.bool_()),
    ("coarser_source_quantum_exponent", pa.int32()),
    ("equal_at_coarser_source_quantum", pa.bool_()),
    *[(f"equal_at_{places}_decimal_places", pa.bool_()) for places in _ROUND_PLACES],
])


def _number(raw):
    """Parse bounded decimal text without any intermediate binary float."""
    if not isinstance(raw, str) or len(raw) > _MAX_TEXT or not _NUMBER.fullmatch(raw.strip()):
        raise ValueError("Benchmark text is missing, invalid, or exceeds the diagnostic bound")
    try:
        number = Decimal(raw.strip())
    except InvalidOperation as exc:
        raise ValueError("Benchmark decimal text is invalid") from exc
    if (not number.is_finite() or abs(number.as_tuple().exponent) > _MAX_EXPONENT
            or abs(number.adjusted()) > _MAX_EXPONENT):
        raise ValueError("Benchmark decimal exponent exceeds the exact diagnostic bound")
    if number < -1:
        raise ValueError("Benchmark return is below minus one")
    return number


def _difference(daily, independent):
    precision = max(34, max(daily.adjusted(), independent.adjusted())
                    - min(daily.as_tuple().exponent, independent.as_tuple().exponent) + 2)
    if precision > _MAX_PRECISION:
        raise ValueError("Exact difference exceeds the diagnostic working-precision bound")
    with localcontext() as context:
        context.prec = precision
        context.traps[Inexact] = True
        return daily - independent


def _rounded_equal(daily, independent, exponent):
    with localcontext() as context:
        context.prec = _MAX_PRECISION
        context.traps[Inexact] = False
        quantum = Decimal((0, (1,), exponent))
        return daily.quantize(quantum, rounding=ROUND_HALF_EVEN) == independent.quantize(
            quantum, rounding=ROUND_HALF_EVEN)


def _snapshot(path, raw):
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o400)


def _inventory_bindings(stage, manifest, bundle, guards, hashes):
    """Bind every staged receipt and the actual preserved independent market."""
    items = manifest["sources"]
    if not isinstance(items, list) or not 2 <= len(items) <= 65:
        raise ValueError("Source stage requires bounded daily sources and one market source")
    counts, seen, bindings = Counter(), set(), []
    market = None
    for item in items:
        role = item.get("role")
        if role not in {"daily", "market"}:
            raise ValueError("Unsupported source role in stage receipt")
        counts[role] += 1
        pair = item.get("source_sha256"), item.get("inventory_receipt_sha256")
        if (not all(isinstance(value, str) and _SHA.fullmatch(value) for value in pair)
                or pair[0] in seen):
            raise ValueError("Source hashes are invalid or the same source is supplied twice")
        seen.add(pair[0])
        path = _inside(stage, item["inventory_receipt_file"])
        receipt, raw, identity = _read_receipt(path)
        if hashlib.sha256(raw).hexdigest() != pair[1]:
            raise ValueError("Staged inventory receipt does not match its bound hash")
        guards[path], hashes[path] = identity, pair[1]
        status = ("RAW_MANUAL_WRDS_INVENTORY_NOT_AUDIT_APPROVED" if role == "daily"
                  else "RAW_MANUAL_WRDS_MARKET_INVENTORY_NOT_SOURCE_APPROVED")
        if (type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1
                or receipt.get("status") != status
                or receipt.get("protocol_sha256") != manifest["protocol_sha256"]
                or receipt.get("model_ready") is not False):
            raise ValueError("Inventory receipt has an unsupported source or protocol contract")
        source = receipt["source"]
        if (source.get("sha256") != pair[0]
                or source.get("preserved_file") != item.get("preserved_file")
                or type(source.get("bytes")) is not int or source["bytes"] < 1
                or source["bytes"] != item.get("source_bytes")
                or source.get("observed_header") != item.get("observed_header")
                or type(item.get("rows")) is not int or item["rows"] < 1
                or receipt["all_rows"].get("rows") != item["rows"]
                or type(item.get("requested_rows")) is not int
                or not 0 <= item["requested_rows"] <= item["rows"]
                or item.get("inventory_row_count_verified") is not True
                or item.get("original_source_retained_in_place") is not True):
            raise ValueError("Stage source declaration disagrees with its inventory receipt")
        header = source["observed_header"]
        if (not isinstance(header, list) or not 1 <= len(header) <= 256
                or not all(isinstance(field, str) and _HEADER.fullmatch(field) for field in header)
                or len({field.lower() for field in header}) != len(header)):
            raise ValueError("Bound source header is invalid or ambiguous")
        canonical = {field.lower() for field in header}
        if role == "market":
            if canonical != {"dlycaldt", "vwretd"} or item.get("allow_extra_columns") is not False:
                raise ValueError("Independent market schema must contain exactly its two fields")
        else:
            projection = receipt.get("projection")
            extra = len(header) != len(DAILY_FIELDS)
            if (not set(DAILY_FIELDS).issubset(canonical)
                    or type(item.get("allow_extra_columns")) is not bool
                    or (extra and item["allow_extra_columns"] is not True)
                    or (projection is not None and (
                        projection.get("fields") != list(DAILY_FIELDS)
                        or projection.get("allow_extra_columns") != item["allow_extra_columns"]
                        or projection.get("extra_columns")
                        != [field for field in header if field.lower() not in DAILY_FIELDS]))
                    or (projection is None and item["allow_extra_columns"])):
                raise ValueError("Daily receipt does not authorize its declared field projection")
        start = _iso(receipt["request"]["start"], "Inventory request start")
        end = _iso(receipt["request"]["end"], "Inventory request end")
        if start > end or end > manifest["request"]["last_permitted_development_return_date"]:
            raise ValueError("Inventory receipt request exceeds the development boundary")
        relative = f"input_receipts/{role}-{counts[role]:03d}.json"
        _snapshot(bundle / relative, raw)
        binding = {"role": role, "source_sha256": pair[0], "inventory_receipt_sha256": pair[1],
                   "inventory_receipt_snapshot": relative, "source_bytes": source["bytes"],
                   "rows": item["rows"], "requested_rows": item["requested_rows"]}
        bindings.append(binding)
        if role == "market":
            directory = Path(item["inventory_directory"]).resolve(strict=True)
            original_receipt = _inside(directory, "receipt.json")
            _, original_raw, original_identity = _read_receipt(original_receipt)
            if original_raw != raw:
                raise ValueError("Preserved market inventory differs from the staged receipt")
            guards[original_receipt], hashes[original_receipt] = original_identity, pair[1]
            original_source = _safe_source(directory, source["preserved_file"])
            source_identity = _identity(original_source)
            if source_identity[2] != source["bytes"] or _hash(original_source) != pair[0]:
                raise ValueError("Preserved independent market bytes or hash do not match")
            guards[original_source], hashes[original_source] = source_identity, pair[0]
            market = {"source": original_source, "directory": directory,
                      "receipt_path": original_receipt, "receipt": receipt, "stage_item": item,
                      "binding": binding}
    if counts["market"] != 1 or not counts["daily"]:
        raise ValueError("Exactly one independent market source is required")
    return bindings, market


def _guard(stage, manifest, market, guards, hashes, *, rehash=False):
    _inside(stage, "receipt.json")
    for item in manifest["projection"]["parts"]:
        _inside(stage, item["file"])
    for item in manifest["sources"]:
        _inside(stage, item["inventory_receipt_file"])
    if (_inside(market["directory"], "receipt.json") != market["receipt_path"]
            or _safe_source(market["directory"], market["receipt"]["source"]["preserved_file"])
            != market["source"]):
        raise ValueError("Preserved market path changed during the diagnostic")
    _unchanged(guards)
    if rehash:
        for path, expected in hashes.items():
            if _hash(path) != expected:
                raise ValueError("A bound input hash changed during the diagnostic")
        _unchanged(guards)


def _market_date_preflight(market, db, manifest):
    request = manifest["request"]
    start, end, limit = request["start"], request["end"], request["last_permitted_development_return_date"]
    rows = requested = 0
    db.execute("CREATE TABLE market(day TEXT PRIMARY KEY,record INTEGER NOT NULL,value TEXT) WITHOUT ROWID")
    with _market_rows(market["source"]) as (header, records):
        if header != market["receipt"]["source"]["observed_header"]:
            raise ValueError("Independent market header disagrees with its inventory")
        for record, (raw_date, _) in enumerate(records, start=2):
            day = _iso(raw_date, "Independent market DlyCalDt")
            if day > limit:
                raise ValueError("Independent market date exceeds development; holdout blocked")
            try:
                db.execute("INSERT INTO market(day,record) VALUES (?,?)", (day, record))
            except sqlite3.IntegrityError as exc:
                raise ValueError("Independent market contains duplicate dates") from exc
            rows += 1
            requested += start <= day <= end
    db.commit()
    first, last, distinct = db.execute("SELECT MIN(day),MAX(day),COUNT(*) FROM market").fetchone()
    actual = {"first_date": first, "last_date": last, "distinct_dates": distinct}
    item = market["stage_item"]
    if (not rows or rows != item["rows"] or requested != item["requested_rows"]
            or any(market["receipt"]["actual_coverage"].get(key) != value for key, value in actual.items())
            or any(item["actual_coverage"].get(key) != value for key, value in actual.items())):
        raise ValueError("Independent market date coverage disagrees with the bound receipts")
    expected = {s for s in calendar().sessions.strftime("%Y-%m-%d") if start <= s <= end}
    missing = expected.copy()
    unexpected = 0
    for (day,) in db.execute("SELECT day FROM market WHERE day BETWEEN ? AND ?", (start, end)):
        missing.discard(day)
        unexpected += day not in expected
    return {"source_rows": rows, "requested_rows": requested,
            "outside_request_rows_preserved_in_market_source": rows - requested,
            "expected_sessions": len(expected), "requested_dates": requested,
            "missing_expected_sessions": len(missing), "unexpected_requested_dates": unexpected}


def _market_values(market, db):
    rows = 0
    with _market_rows(market["source"]) as (header, records):
        if header != market["receipt"]["source"]["observed_header"]:
            raise ValueError("Independent market header changed after preflight")
        for record, (day, raw) in enumerate(records, start=2):
            _number(raw)
            cursor = db.execute("UPDATE market SET value=? WHERE day=? AND record=? AND value IS NULL",
                                (raw, day, record))
            if cursor.rowcount != 1:
                raise ValueError("Independent market date or record changed after preflight")
            rows += 1
    db.commit()
    if (rows != market["stage_item"]["rows"]
            or db.execute("SELECT COUNT(*) FROM market WHERE value IS NULL").fetchone()[0]):
        raise ValueError("Independent market record count changed after preflight")


def _stats():
    return {"mismatch_dates": 0, "daily_rows_affected": 0,
            "positive_difference_dates": 0, "negative_difference_dates": 0}


def _compare(db, market_db, market, path, source_bindings):
    counts = {"compared_daily_rows": 0, "exact_text_equal_rows": 0, "numeric_equal_rows": 0,
              "numeric_equal_text_different_rows": 0, "numeric_mismatch_rows": 0,
              "mismatch_dates": 0, "mismatching_date_source_pairs": 0,
              "mismatching_raw_text_groups": 0, "daily_dates_with_distinct_raw_texts": 0,
              "positive_difference_dates": 0, "negative_difference_dates": 0,
              "positive_difference_daily_rows": 0, "negative_difference_daily_rows": 0}
    years, sources = {}, {s["source_sha256"]: _stats() for s in source_bindings if s["role"] == "daily"}
    rounding = {str(p): {"equal_mismatch_dates": 0, "equal_affected_daily_rows": 0} for p in _ROUND_PLACES}
    quantum_counts = {"daily_raw_group_counts": Counter(), "market_raw_group_counts": Counter(),
                      "coarser_quantum_equal_raw_groups": 0, "coarser_quantum_equal_daily_rows": 0}
    previous_day = previous_mismatch_day = previous_mismatch_pair = None
    day_number = day_raw = independent = market_raw = market_record = None
    day_has_text_variants = False
    minimum = maximum = None
    buffered, written = [], 0
    cursor = db.execute("SELECT * FROM benchmark_groups ORDER BY session_date,source_sha256,source_inventory_sha256,raw_text")
    with pq.ParquetWriter(path, MISMATCH_SCHEMA, compression="zstd") as writer:
        while batch := cursor.fetchmany(_BATCH):
            for day, source, inventory, raw, rows in batch:
                daily = _number(raw)
                if day != previous_day:
                    previous_day, day_number, day_raw, day_has_text_variants = day, daily, raw, False
                    found = market_db.execute("SELECT value,record FROM market WHERE day=?", (day,)).fetchone()
                    if found is None:
                        raise ValueError("Independent market is missing a requested projected date")
                    market_raw, market_record = found
                    independent = _number(market_raw)
                else:
                    if daily != day_number:
                        raise ValueError("Daily sources have conflicting numeric benchmarks for one date")
                    if raw != day_raw and not day_has_text_variants:
                        counts["daily_dates_with_distinct_raw_texts"] += 1
                        day_has_text_variants = True
                counts["compared_daily_rows"] += rows
                if daily == independent:
                    counts["numeric_equal_rows"] += rows
                    counts["exact_text_equal_rows" if raw == market_raw else
                           "numeric_equal_text_different_rows"] += rows
                    continue
                difference = _difference(daily, independent)
                absolute = difference.copy_abs()
                minimum = absolute if minimum is None or absolute < minimum else minimum
                maximum = absolute if maximum is None or absolute > maximum else maximum
                sign = "positive" if difference > 0 else "negative"
                counts["numeric_mismatch_rows"] += rows
                counts["mismatching_raw_text_groups"] += 1
                counts[f"{sign}_difference_daily_rows"] += rows
                year = years.setdefault(day[:4], _stats())
                source_stats = sources[source]
                year["daily_rows_affected"] += rows
                source_stats["daily_rows_affected"] += rows
                new_date = day != previous_mismatch_day
                if new_date:
                    counts["mismatch_dates"] += 1
                    counts[f"{sign}_difference_dates"] += 1
                    year["mismatch_dates"] += 1
                    year[f"{sign}_difference_dates"] += 1
                    previous_mismatch_day = day
                if (day, source) != previous_mismatch_pair:
                    counts["mismatching_date_source_pairs"] += 1
                    source_stats["mismatch_dates"] += 1
                    source_stats[f"{sign}_difference_dates"] += 1
                    previous_mismatch_pair = day, source
                daily_tuple, market_tuple = daily.as_tuple(), independent.as_tuple()
                coarser = max(daily_tuple.exponent, market_tuple.exponent)
                coarser_equal = _rounded_equal(daily, independent, coarser)
                quantum_counts["daily_raw_group_counts"][str(daily_tuple.exponent)] += 1
                quantum_counts["market_raw_group_counts"][str(market_tuple.exponent)] += 1
                quantum_counts["coarser_quantum_equal_raw_groups"] += int(coarser_equal)
                quantum_counts["coarser_quantum_equal_daily_rows"] += rows * coarser_equal
                result = {
                    "date": day, "daily_source_sha256": source,
                    "daily_inventory_receipt_sha256": inventory,
                    "market_source_sha256": market["binding"]["source_sha256"],
                    "market_inventory_receipt_sha256": market["binding"]["inventory_receipt_sha256"],
                    "market_source_csv_record": market_record,
                    "daily_raw_text": raw, "market_raw_text": market_raw,
                    "daily_minus_independent_exact": str(difference), "daily_rows_affected": rows,
                    "daily_decimal_quantum_exponent": daily_tuple.exponent,
                    "market_decimal_quantum_exponent": market_tuple.exponent,
                    "daily_literal_significant_digits": len(daily_tuple.digits),
                    "market_literal_significant_digits": len(market_tuple.digits),
                    "daily_scientific_notation": "e" in raw.lower(),
                    "market_scientific_notation": "e" in market_raw.lower(),
                    "coarser_source_quantum_exponent": coarser,
                    "equal_at_coarser_source_quantum": coarser_equal,
                }
                for places in _ROUND_PLACES:
                    equal = _rounded_equal(daily, independent, -places)
                    result[f"equal_at_{places}_decimal_places"] = equal
                    rounding[str(places)]["equal_mismatch_dates"] += int(equal and new_date)
                    rounding[str(places)]["equal_affected_daily_rows"] += rows * equal
                buffered.append(result)
                if len(buffered) >= _BATCH:
                    writer.write_table(pa.Table.from_pylist(buffered, schema=MISMATCH_SCHEMA))
                    written += len(buffered)
                    buffered.clear()
        if buffered:
            writer.write_table(pa.Table.from_pylist(buffered, schema=MISMATCH_SCHEMA))
            written += len(buffered)
    path.chmod(0o400)
    return {
        "counts": counts, "mismatches_by_year": dict(sorted(years.items())),
        "mismatches_by_source_sha256": dict(sorted(sources.items())),
        "exact_difference": {"direction": "daily_attached_minus_independent_market",
                             "minimum_absolute": None if minimum is None else str(minimum),
                             "maximum_absolute": None if maximum is None else str(maximum)},
        "rounding_diagnostics": {
            "scope": "exactly mismatching requested dates and their repeated daily rows only",
            "mode": "ROUND_HALF_EVEN applied separately to both exact source decimals",
            "decimal_places": rounding,
            "source_text_quantum": {
                **{key: dict(sorted(value.items())) if isinstance(value, Counter) else value
                   for key, value in quantum_counts.items()},
                "definition": "Decimal literal exponent; trailing zeros retained, scientific exponent applied",
                "coarser_rule": "quantize both values to 10 ** max(source literal exponents)",
                "scope": "mismatching date/source/raw-text groups, not distinct dates",
                "vendor_storage_precision_verified": False,
            },
            "diagnostic_only": True, "acceptance_rule": False,
            "source_discrepancy_explained": False,
        },
        "table": {"file": path.name, "rows": written, "bytes": path.stat().st_size,
                  "sha256": _hash(path), "grain": "requested date, daily source/receipt hash, raw benchmark text",
                  "contains_security_identifiers": False, "private_only": True},
    }


def audit_benchmark(stage_directory, *, output, config, repo_root="."):
    """Audit attached versus independent benchmark text without altering sources."""
    repo, stage = Path(repo_root).resolve(), Path(stage_directory).resolve(strict=True)
    verify_lock(config, repo / "configs" / "protocol.lock.json")
    out = _private_directory(output, repo)
    if out.is_relative_to(stage):
        raise ValueError("Diagnostic output must be outside the preserved source-stage bundle")
    manifest, stage_bytes, parts, sources, guards = _stage_inputs(stage, config)
    hashes = {stage / "receipt.json": hashlib.sha256(stage_bytes).hexdigest(),
              **{path: item["sha256"] for (path, _), item in zip(
                  parts, manifest["projection"]["parts"], strict=True)}}
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".wrds-benchmark-audit-", dir=out.parent) as temporary:
        work = Path(temporary)
        bundle = work / "bundle"
        bundle.mkdir(mode=0o700)
        (bundle / "input_receipts").mkdir(mode=0o700)
        _snapshot(bundle / "source_stage_receipt.json", stage_bytes)
        bindings, market = _inventory_bindings(stage, manifest, bundle, guards, hashes)
        if out.is_relative_to(market["directory"]):
            raise ValueError("Diagnostic output must be outside the preserved market inventory")
        _guard(stage, manifest, market, guards, hashes)
        daily_coverage = _preflight(parts, sources, manifest)
        market_db = sqlite3.connect(str(work / "market.sqlite3"))
        db = None
        try:
            market_db.execute("PRAGMA cache_size=-16384")
            market_db.execute("PRAGMA temp_store=FILE")
            market_coverage = _market_date_preflight(market, market_db, manifest)
            _guard(stage, manifest, market, guards, hashes)
            db = duckdb.connect(str(work / "audit.duckdb"), config={
                "memory_limit": "1GB", "threads": 2, "preserve_insertion_order": False,
                "temp_directory": str(work / "spill"),
            })
            db.read_parquet([str(path) for path, _ in parts]).create_view("raw")
            nulls = " OR ".join(f'"{field}" IS NULL' for field in DAILY_FIELDS)
            if db.execute(f"SELECT COUNT(*) FROM raw WHERE {nulls}").fetchone()[0]:
                raise ValueError("Source projection contains null required raw fields")
            # _preflight verifies each source's consecutive CSV ordinals across
            # all parts. A second global 23-million-record hash table is unnecessary.
            date_cursor = db.execute("SELECT DISTINCT dlycaldt FROM raw WHERE in_requested_window")
            while date_batch := date_cursor.fetchmany(_BATCH):
                for (day,) in date_batch:
                    if market_db.execute("SELECT 1 FROM market WHERE day=?", (day,)).fetchone() is None:
                        raise ValueError("Independent market is missing a requested projected date")
            longest = db.execute("SELECT COALESCE(MAX(length(vwretd)),0) FROM raw "
                                 "WHERE in_requested_window").fetchone()[0]
            if longest > _MAX_TEXT:
                raise ValueError("Attached benchmark text exceeds the bounded diagnostic length")
            # Both complete date passes and all provenance checks precede parsing.
            _guard(stage, manifest, market, guards, hashes)
            _market_values(market, market_db)
            _guard(stage, manifest, market, guards, hashes)
            db.execute("CREATE TABLE benchmark_groups AS SELECT dlycaldt AS session_date,source_sha256,"
                       "source_inventory_sha256,vwretd AS raw_text,COUNT(*)::BIGINT AS n "
                       "FROM raw WHERE in_requested_window GROUP BY ALL")
            result = _compare(db, market_db, market, bundle / "mismatches.parquet", bindings)
            if result["counts"]["compared_daily_rows"] != daily_coverage["requested_rows"]:
                raise ValueError("Benchmark groups do not account for every requested source row")
        finally:
            if db is not None:
                db.close()
            market_db.close()
        _guard(stage, manifest, market, guards, hashes, rehash=True)
        for binding in bindings:
            if _hash(bundle / binding["inventory_receipt_snapshot"]) != binding["inventory_receipt_sha256"]:
                raise ValueError("Diagnostic inventory receipt snapshot changed")
        if _hash(bundle / "source_stage_receipt.json") != hashes[stage / "receipt.json"]:
            raise ValueError("Diagnostic stage receipt snapshot changed")
        complete = not any(coverage[key] for coverage in (daily_coverage, market_coverage)
                           for key in ("missing_expected_sessions", "unexpected_requested_dates"))
        receipt = {
            "schema_version": 1, "status": STATUS, "created_at": datetime.now(timezone.utc).isoformat(),
            "protocol_sha256": canonical_hash(config), "code_sha256": _hash(Path(__file__)),
            "source_stage_directory": str(stage), "source_stage_receipt_sha256": hashes[stage / "receipt.json"],
            "source_stage_receipt_snapshot": "source_stage_receipt.json", "sources": bindings,
            "independent_market_preserved_source": str(market["source"]),
            "request": manifest["request"],
            "coverage": {"daily_projection": daily_coverage, "independent_market": market_coverage},
            **result,
            "reconciliation": {
                "exact_observed_benchmark_values_equal": result["counts"]["numeric_mismatch_rows"] == 0,
                "requested_window_numerically_reconciled": bool(
                    complete and result["counts"]["numeric_mismatch_rows"] == 0),
                "upstream_requested_window_numerically_reconciled":
                    manifest["reconciliation"]["requested_window_numerically_reconciled"],
                "source_discrepancy_explained": False, "tolerance_acceptance_used": False,
                "fallback_used": False, "source_replacement_used": False,
            },
            "processing": {"complete_all_source_date_pass_before_numeric_interpretation": True,
                           "stage_parts_and_input_receipts_rehashed_before_and_after": True,
                           "preserved_independent_market_source_rehashed_before_and_after": True,
                           "daily_original_csv_rehashed_by_this_diagnostic": False,
                           "daily_origin_binding": "verified Parquet and staged inventory receipt hashes",
                           "source_ordinals_verified_in_streaming_order": True,
                           "duckdb_memory_limit": "1GB", "duckdb_threads": 2,
                           "sqlite_cache_kib": 16384, "group_reader_and_writer_batch_rows": _BATCH,
                           "numeric_text_maximum_characters": _MAX_TEXT,
                           "numeric_exponent_and_adjusted_exponent_absolute_limit": _MAX_EXPONENT,
                           "decimal_working_precision_limit": _MAX_PRECISION,
                           "binary_float_intermediates_used": False},
            "model_ready": False, "source_approvals": 0, "final_period_opened": False,
            "prior_arithmetic_review_modified": False, "original_sources_modified": False,
            "values_filled": 0, "values_replaced": 0, "approved_returns_created": False,
        }
        _write_json(bundle / "receipt.json", receipt)
        if out.exists() or _private_directory(out, repo) != out:
            raise ValueError("Diagnostic output is no longer a new private directory")
        bundle.rename(out)
    return receipt


def aggregate_summary(receipt):
    """Whitelist aggregates; no raw values, dates, identifiers, or local paths."""
    return {key: receipt[key] for key in (
        "status", "protocol_sha256", "coverage", "counts", "mismatches_by_year",
        "mismatches_by_source_sha256", "exact_difference", "rounding_diagnostics", "reconciliation",
        "model_ready", "source_approvals", "final_period_opened", "prior_arithmetic_review_modified",
    )}
