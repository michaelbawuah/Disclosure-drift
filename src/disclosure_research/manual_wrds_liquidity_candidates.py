"""Bounded annual liquidity evidence from two unapproved development bundles.

Historical availability and issuer identity remain unknown. The output ranks
observed securities under an explicit candidate policy and is not a universe.
"""

import hashlib
import json
import math
import os
import re
import sqlite3
import struct
import tempfile
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from . import manual_wrds_candidates as numerical
from . import manual_wrds_listing_candidates as listing
from .manual_wrds_intake import _copy_source, _hash, _identity, _iso, _private_directory
from .manual_wrds_metadata import NAMES_FIELDS
from .manual_wrds_stage import _read_receipt
from .market_data import development_return_end
from .protocol import canonical_hash, verify_lock
from .universe import year_start_window

STATUS = "ANNUAL_MANUAL_WRDS_LIQUIDITY_CANDIDATES_NOT_SOURCE_APPROVED"
LISTING_STATUS = "DATED_NAMES_LISTING_CANDIDATES_NOT_SOURCE_APPROVED"
YEARS = tuple(range(2010, 2022))
_BATCH = 4096
_BATCH_BYTES = 16 * 1024 * 1024
_MAX_PARTS = 100_000
_SHA = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[1-9][0-9]*")
_VALUE = "closing_price_volume_usd_candidate"
_ADMITTED = "CANDIDATE_REQUIRES_SOURCE_REVIEW"
_CONFLICT = "conflicting_security_date_projection"
_LIQUIDITY_STATUSES = {
    _ADMITTED, _CONFLICT, "invalid_permanent_identifier", "not_an_exchange_session",
    "unsupported_liquidity_price_flag", "missing_numeric_value", "unsupported_numeric_text",
    "nonfinite_value", "numeric_exponent_outside_candidate_range", "nonpositive_ciz_price",
    "negative_volume", "not_representable_as_nonnegative_finite_float",
}
_DAILY_META = [
    "security_id", "source_permco", "session", "projection_sha256", "projection_record_count",
    "projection_source_file_count", "security_session_projection_variants",
    "representative_source_sha256", "representative_source_inventory_sha256",
    "representative_source_csv_record", "price_flag", "liquidity_status",
]
_COUNTS = (
    "observed_sessions", "distinct_projection_rows", "source_records",
    "equivalent_13_field_record_excess", "unambiguous_sessions", "conflicting_sessions",
    "numerically_valid_sessions", "withheld_sessions", "missing_sessions",
    "zero_volume_candidate_sessions", "trade_price_valid_sessions", "bid_ask_valid_sessions",
)
ANNUAL_SCHEMA = pa.schema([
    pa.field("candidate_year", pa.int16(), nullable=False),
    pa.field("security_id", pa.string(), nullable=False),
    *[pa.field(name, pa.string(), nullable=False) for name in (
        "selection_asof", "selection_session", "information_cutoff", "liquidity_start", "liquidity_end")],
    pa.field("expected_sessions", pa.int16(), nullable=False),
    *[pa.field(name, pa.int64(), nullable=False) for name in _COUNTS],
    pa.field("mean_closing_price_volume_usd_candidate", pa.float64()),
    pa.field("positive_mean_rounded_to_zero", pa.bool_(), nullable=False),
    pa.field("meets_numeric_minimum_40", pa.bool_(), nullable=False),
    pa.field("coverage_status", pa.string(), nullable=False),
    pa.field("withheld_reason_counts", pa.string(), nullable=False),
    pa.field("listing_record_count", pa.int64(), nullable=False),
    pa.field("listing_distinct_projection_count", pa.int64(), nullable=False),
    pa.field("listing_candidate_status", pa.string(), nullable=False),
    pa.field("ambiguous_listing", pa.bool_(), nullable=False),
    pa.field("ordinary_listing_candidate", pa.bool_(), nullable=False),
    pa.field("rank_eligible_by_candidate_policy", pa.bool_(), nullable=False),
    pa.field("candidate_security_rank", pa.int64()),
    pa.field("known_at", pa.string()),
    pa.field("available_at", pa.string()),
    pa.field("numerical_candidate_receipt_sha256", pa.string(), nullable=False),
    pa.field("listing_candidate_receipt_sha256", pa.string(), nullable=False),
    pa.field("liquidity_projection_evidence_sha256", pa.string(), nullable=False),
])


@dataclass
class _Input:
    role: str
    directory: Path
    receipt: dict
    raw: bytes
    sha256: str
    parts: list
    guards: dict
    chain: dict
    chain_raw: bytes
    chain_name: str


def _integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} requires a bounded nonnegative integer")
    return value


def _sha(value):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError("A source binding requires an actual SHA-256 declaration")
    return value


def _read_bound(directory, name, guards):
    path = numerical._inside(directory, name)
    receipt, raw, identity = _read_receipt(path)
    guards[path] = (identity, hashlib.sha256(raw).hexdigest())
    return receipt, raw


def _contract(receipt, status, config):
    if (type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1
            or receipt.get("status") != status
            or receipt.get("protocol_sha256") != canonical_hash(config)
            or receipt.get("model_ready") is not False
            or type(receipt.get("source_approvals")) is not int or receipt["source_approvals"] != 0
            or receipt.get("final_period_opened") is not False):
        raise ValueError("Upstream bundle does not match the unapproved frozen development contract")


def _parts(directory, projection, total, expected_schema, guards):
    specifications = projection.get("parts")
    if not isinstance(specifications, list) or len(specifications) > _MAX_PARTS:
        raise ValueError("Upstream part manifest is missing or exceeds the metadata limit")
    result, names, rows = [], set(), 0
    for item in specifications:
        name = item["file"]
        if name in names:
            raise ValueError("An upstream part is listed more than once")
        names.add(name)
        path = numerical._inside(directory, name)
        identity = _identity(path)
        count = _integer(item["rows"], "Part rows", 1)
        digest = _sha(item["sha256"])
        if (_integer(item["bytes"], "Part bytes") != identity[2]
                or _hash(path) != digest or _identity(path) != identity):
            raise ValueError("Upstream part size or hash changed or disagrees with its receipt")
        parquet = pq.ParquetFile(path)
        if (not parquet.schema_arrow.equals(expected_schema, check_metadata=False)
                or parquet.metadata.num_rows != count):
            raise ValueError("Upstream part schema or row count disagrees with its receipt")
        guards[path] = (identity, digest)
        result.append((path, item))
        rows += count
    if rows != total:
        raise ValueError("Upstream parts do not account for the declared row count")
    return result


def _load(directory, role, config):
    directory = Path(directory).resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("Candidate input must be an existing directory")
    guards = {}
    receipt, raw = _read_bound(directory, "receipt.json", guards)
    status = numerical.STATUS if role == "numerical" else LISTING_STATUS
    _contract(receipt, status, config)
    if receipt.get("prior_arithmetic_review_modified") is not False:
        raise ValueError("Upstream must leave the prior arithmetic review unchanged")
    projection = receipt["projection"]
    if role == "numerical":
        chain_name = receipt["source_stage_receipt_snapshot"]
        chain, chain_raw = _read_bound(directory, chain_name, guards)
        if hashlib.sha256(chain_raw).hexdigest() != receipt["source_stage_receipt_sha256"]:
            raise ValueError("Numerical source-stage receipt binding does not match")
        _contract(chain, numerical.STAGE_STATUS, config)
        request = receipt["request"]
        first = year_start_window(2010, config)["liquidity_start"]
        start, end = _iso(request["start"], "Request start"), _iso(request["end"], "Request end")
        limit = development_return_end(config)
        if (request != chain["request"] or start < first or start > end or end > limit
                or request["last_permitted_development_return_date"] != limit
                or request.get("first_permitted_request_date", first) != first):
            raise ValueError("Numerical request exceeds or disagrees with the development envelope")
        reconciled = receipt["reconciliation"]["requested_window_numerically_reconciled"]
        if (type(reconciled) is not bool
                or reconciled != chain["reconciliation"]["requested_window_numerically_reconciled"]):
            raise ValueError("Numerical benchmark reconciliation declaration disagrees with its source")
        if (projection.get("comparison_scope") != "exact_raw_required_13_fields_only"
                or projection.get("full_delivered_row_equality_claimed") is not False
                or projection.get("all_conflicting_projections_retained_with_numeric_candidates_withheld") is not True
                or receipt.get("historical_availability_supplied") is not False
                or receipt.get("historical_identity_supplied") is not False):
            raise ValueError("Numerical projection or unresolved-source policy is unsupported")
        total = _integer(projection["candidate_rows"], "Numerical candidate rows")
        _integer(projection["source_records"], "Represented source records")
        schema = numerical.CANDIDATE_SCHEMA
    else:
        if (receipt.get("years") != list(YEARS) or receipt.get("candidate_policy") != listing.POLICY
                or receipt.get("candidate_policy_sha256") != canonical_hash(listing.POLICY)
                or receipt.get("known_at_supplied_or_inferred") is not False
                or receipt.get("complete_source_date_pass_before_classification") is not True
                or receipt.get("cik_mapping_created") is not False
                or receipt.get("universe_membership_created") is not False):
            raise ValueError("Names candidates do not match the supported annual candidate policy")
        if (projection.get("raw_fields") != list(NAMES_FIELDS)
                or projection.get("derived_fields") != [field.name for field in listing._EXTRA_FIELDS]
                or projection.get("all_matching_source_record_year_pairs_retained") is not True
                or projection.get("exact_duplicate_records_retained") is not True
                or projection.get("duplicate_comparison_scope")
                != "exact parsed text across all 24 canonical Names fields"
                or projection.get("ambiguous_overlaps_withheld_from_ordinary_candidates") is not True):
            raise ValueError("Names raw projection or overlap policy is unsupported")
        source = receipt["source"]
        chain_name = source["inventory_receipt_file"]
        chain, chain_raw = _read_bound(directory, chain_name, guards)
        if (hashlib.sha256(chain_raw).hexdigest() != source["inventory_receipt_sha256"]
                or chain.get("schema_version") != 1 or chain.get("role") != "names"
                or chain.get("status") != "RAW_MANUAL_WRDS_METADATA_INVENTORY_NOT_SOURCE_APPROVED"
                or chain.get("protocol_sha256") != canonical_hash(config)
                or _sha(source["source_sha256"]) != chain["source"]["sha256"]
                or source["source_rows"] != chain["all_rows"]["rows"]
                or source["observed_header"] != chain["source"]["observed_header"]):
            raise ValueError("Names source inventory receipt binding does not match")
        total = _integer(projection["rows"], "Names snapshot rows")
        if receipt.get("known_at_null_rows") != total:
            raise ValueError("Every Names historical availability value must remain unknown")
        schema = listing.CANDIDATE_SCHEMA
    parts = _parts(directory, projection, total, schema, guards)
    return _Input(role, directory, receipt, raw, hashlib.sha256(raw).hexdigest(),
                  parts, guards, chain, chain_raw, chain_name)


def _guard(inputs, *, rehash=False):
    for item in inputs:
        for path, (identity, digest) in item.guards.items():
            current = numerical._inside(item.directory, path.relative_to(item.directory).as_posix())
            if current != path or _identity(path) != identity:
                raise ValueError("An upstream candidate file changed during liquidity construction")
            if rehash and (_hash(path) != digest or _identity(path) != identity):
                raise ValueError("An upstream candidate hash changed during liquidity construction")


def _batches(item, columns):
    for path, specification in item.parts:
        rows = 0
        for batch in pq.ParquetFile(path).iter_batches(batch_size=_BATCH, columns=columns):
            if batch.nbytes > _BATCH_BYTES:
                raise ValueError("An upstream reader batch exceeds the bounded Arrow byte budget")
            rows += batch.num_rows
            yield batch
        if rows != specification["rows"]:
            raise ValueError("Upstream row counts changed during streaming preflight")


def _numerical_preflight(item, work):
    sources = {}
    for source in item.chain["sources"]:
        if source["role"] == "daily":
            pair = (_sha(source["source_sha256"]), _sha(source["inventory_receipt_sha256"]))
            if pair in sources or len(sources) >= 64:
                raise ValueError("Numerical source provenance is duplicated or unbounded")
            sources[pair] = _integer(source["rows"], "Original source rows", 1)
    if not sources:
        raise ValueError("Numerical candidates require bound original daily sources")
    request = item.receipt["request"]
    counts, prices, dates = Counter(), Counter(), Counter()
    total = represented = conflicts = 0
    previous = None
    variants = group_rows = 0
    with closing(sqlite3.connect(str(work / "projection-preflight.sqlite3"))) as db:
        db.execute("PRAGMA cache_size=-4096")
        db.execute("PRAGMA temp_store=FILE")
        db.execute("CREATE TABLE hashes(value TEXT PRIMARY KEY) WITHOUT ROWID")
        for batch in _batches(item, _DAILY_META):
            if any(column.null_count for column in batch.columns):
                raise ValueError("Numerical dates, statuses and provenance must not be null")
            for row in batch.to_pylist():
                day = _iso(row["session"], "Numerical session")
                if not request["start"] <= day <= request["end"]:
                    raise ValueError("Numerical date lies outside the development request; holdout blocked")
                if any(len(row[field]) > 1024 for field in ("security_id", "source_permco", "price_flag")):
                    raise ValueError("Numerical identifier or flag exceeds the bounded text budget")
                pair = row["representative_source_sha256"], row["representative_source_inventory_sha256"]
                if (pair not in sources or not 2 <= row["representative_source_csv_record"] <= sources[pair] + 1):
                    raise ValueError("Numerical representative provenance is outside its bound source")
                _sha(row["projection_sha256"])
                repetitions = _integer(row["projection_record_count"], "Projection repetitions", 1)
                source_count = _integer(row["projection_source_file_count"], "Projection source count", 1)
                declared = _integer(row["security_session_projection_variants"], "Projection variants", 1)
                if source_count > min(repetitions, len(sources)) or row["liquidity_status"] not in _LIQUIDITY_STATUSES:
                    raise ValueError("Numerical projection counts or liquidity status are unsupported")
                key = day, row["security_id"]
                if key != previous:
                    if previous is not None and (key < previous or group_rows != variants):
                        raise ValueError("Numerical security/session ordering or variant count is inconsistent")
                    previous, variants, group_rows = key, declared, 0
                    if variants > 1:
                        conflicts += 1
                        db.execute("DELETE FROM hashes")
                if declared != variants or (row["liquidity_status"] == _CONFLICT) != (variants > 1):
                    raise ValueError("Numerical key conflict declarations are inconsistent")
                group_rows += 1
                if variants == 1 and group_rows > 1:
                    raise ValueError("Numerical candidate projection is duplicated")
                if variants > 1:
                    try:
                        db.execute("INSERT INTO hashes VALUES (?)", (row["projection_sha256"],))
                    except sqlite3.IntegrityError as exc:
                        raise ValueError("Numerical conflict group repeats an identical projection") from exc
                counts[row["liquidity_status"]] += 1
                prices[row["price_flag"] if row["price_flag"] in numerical._FLAG_CODES["price_flag"]
                       else "__UNRECOGNIZED__"] += 1
                dates[day] += 1
                total += 1
                represented += repetitions
        if previous is not None and group_rows != variants:
            raise ValueError("Numerical final key variant count is inconsistent")
    projection = item.receipt["projection"]
    if (total != projection["candidate_rows"] or represented != projection["source_records"]
            or represented - total != projection["equivalent_13_field_record_excess"]
            or conflicts != projection["conflicting_security_date_keys"]
            or dict(counts) != item.receipt["counts"]["liquidity_status"]
            or dict(prices) != item.receipt["counts"]["price_flag"]):
        raise ValueError("Numerical counts disagree with the bound candidate receipt")
    return {"rows": total, "represented_source_records": represented,
            "conflicting_security_session_keys": conflicts, "dates": dates}


def _listing_preflight(item, windows):
    source = item.receipt["source"]
    expected_pair = source["source_sha256"], source["inventory_receipt_sha256"]
    maximum = _integer(source["source_rows"], "Names original rows", 1) + 1
    columns = ["candidate_year", "selection_asof", "selection_session", "information_cutoff", "known_at",
               "source_sha256", "source_inventory_sha256", "source_csv_record",
               "secinfostartdt", "secinfoenddt", "securitybegdt", "securityenddt"]
    counts, previous = Counter(), None
    for batch in _batches(item, columns):
        for column in columns:
            nulls = batch.column(columns.index(column)).null_count
            if (column == "known_at" and nulls != batch.num_rows) or (column != "known_at" and nulls):
                raise ValueError("Names dates/provenance are required and known_at must remain null")
        for row in batch.to_pylist():
            year = row["candidate_year"]
            if year not in windows:
                raise ValueError("Names snapshots must remain in 2010 through 2021; holdout blocked")
            window = windows[year]
            if any(row[field] != window[field] for field in (
                    "selection_asof", "selection_session", "information_cutoff")):
                raise ValueError("Names selection date or calendar cutoff contradicts the frozen window")
            for field in ("secinfostartdt", "secinfoenddt", "securitybegdt", "securityenddt"):
                _iso(row[field], "Names interval bound")
            if (row["secinfostartdt"] > row["secinfoenddt"] or row["securitybegdt"] > row["securityenddt"]
                    or not row["secinfostartdt"] <= window["selection_asof"] <= row["secinfoenddt"]):
                raise ValueError("Names interval is reversed or does not cover the selection date")
            pair = row["source_sha256"], row["source_inventory_sha256"]
            ordinal = row["source_csv_record"]
            key = year, ordinal
            if pair != expected_pair or not 2 <= ordinal <= maximum or (previous is not None and key <= previous):
                raise ValueError("Names source provenance is invalid, repeated, or out of order")
            previous = key
            counts[year] += 1
    summaries = item.receipt["year_summaries"]
    if (not isinstance(summaries, list) or [row["year"] for row in summaries] != list(YEARS)
            or any(counts[entry["year"]] != entry["candidate_snapshot_rows"] for entry in summaries)
            or sum(counts.values()) != item.receipt["projection"]["rows"]):
        raise ValueError("Names annual row counts disagree with the candidate receipt")
    return counts


def _validate_listing_values(item):
    """Check the supported classifications only after both full date passes."""
    for batch in _batches(item, listing.CANDIDATE_SCHEMA.names):
        if any(batch.column(i).null_count for i, field in enumerate(batch.schema) if field.name != "known_at"):
            raise ValueError("Names raw metadata and classification diagnostics must be present")
        for row in batch.to_pylist():
            if len(row["permno"]) > 1024:
                raise ValueError("Names identifier exceeds the bounded text budget")
            n = _integer(row["security_year_record_count"], "Names group rows", 1)
            variants = _integer(row["security_year_distinct_projection_count"], "Names group variants", 1)
            classification = listing._classify(row)
            status = listing._candidate_status(row, classification, n > 1)
            if (variants > n or row["classification_status"] != classification or row["candidate_status"] != status
                    or row["ordinary_candidate"] != (status == "ORDINARY_CORPORATE_COMMON_CANDIDATE")
                    or row["ambiguous_security_year"] != (n > 1)
                    or row["recognized_us_venue"] != (row["primaryexch"] in listing.POLICY["primaryexch"])
                    or row["dated_active_trading"] != (row["tradingstatusflg"] == "A")
                    or row["securitylife_covers_selection"] !=
                    (row["securitybegdt"] <= row["selection_asof"] <= row["securityenddt"])):
                raise ValueError("Names classification or overlap diagnostics contradict the bound policy")


def _mean(values):
    """Round the exact mean of at most 60 delivered binary64 values once."""
    if not values:
        return None, False
    if len(values) > 60:
        raise ValueError("A security has more than the frozen number of valid sessions")
    exact = sum((Fraction.from_float(value) for value in values), Fraction()) / len(values)
    result = float(exact)
    if not math.isfinite(result) or result < 0:
        raise ValueError("A finite nonnegative candidate mean could not be represented")
    return result, exact > 0 and result == 0


def _value(row):
    if row["security_session_projection_variants"] > 1:
        return None, _CONFLICT
    if row["liquidity_status"] != _ADMITTED:
        return None, "upstream_" + row["liquidity_status"]
    if not _ID.fullmatch(row["security_id"]) or not _ID.fullmatch(row["source_permco"]):
        return None, "invalid_candidate_identifier"
    if row["price_flag"] not in {"TR", "BA"}:
        return None, "unsupported_candidate_price_flag"
    value = row[_VALUE]
    if value is None:
        return None, "missing_candidate_value"
    if not math.isfinite(value):
        return None, "nonfinite_candidate_value"
    if value < 0:
        return None, "negative_candidate_value"
    return value, "NUMERIC_CANDIDATE_REQUIRES_SOURCE_REVIEW"


def _empty(year, security, window, inputs):
    return {
        "candidate_year": year, "security_id": security,
        **{key: value for key, value in window.items() if key != "sessions"},
        "expected_sessions": 60, **dict.fromkeys(_COUNTS, 0), "missing_sessions": 60,
        "mean_closing_price_volume_usd_candidate": None, "positive_mean_rounded_to_zero": False,
        "meets_numeric_minimum_40": False, "coverage_status": "NO_WINDOW_DAILY_CANDIDATES",
        "withheld_reason_counts": "{}", "listing_record_count": 0, "listing_distinct_projection_count": 0,
        "listing_candidate_status": "NO_DATED_NAMES_CANDIDATE", "ambiguous_listing": False,
        "ordinary_listing_candidate": False, "rank_eligible_by_candidate_policy": False,
        "candidate_security_rank": None, "known_at": None, "available_at": None,
        "numerical_candidate_receipt_sha256": inputs[0].sha256,
        "listing_candidate_receipt_sha256": inputs[1].sha256,
        "liquidity_projection_evidence_sha256": hashlib.sha256(b"").hexdigest(),
    }


def _store(db, row):
    db.execute("INSERT OR REPLACE INTO annual VALUES (?,?,?,?,?)", (
        row["candidate_year"], row["security_id"], json.dumps(row, sort_keys=True, allow_nan=False),
        row["mean_closing_price_volume_usd_candidate"], int(row["rank_eligible_by_candidate_policy"])))


def _aggregate_daily(db, records, year, window, inputs):
    previous = current = None
    values, reasons = [], Counter()
    digest = hashlib.sha256()

    def finish():
        if current is None:
            return
        valid = current["numerically_valid_sessions"]
        current["missing_sessions"] = 60 - current["observed_sessions"]
        if (current["missing_sessions"] < 0 or valid + current["withheld_sessions"]
                + current["conflicting_sessions"] != current["observed_sessions"]):
            raise ValueError("Annual session accounting violates the exact 60-session window")
        mean, rounded = _mean(values)
        current.update(mean_closing_price_volume_usd_candidate=mean, positive_mean_rounded_to_zero=rounded,
                       meets_numeric_minimum_40=valid >= 40,
                       coverage_status=("MEETS_NUMERIC_MINIMUM_REQUIRES_SOURCE_REVIEW" if valid >= 40
                                        else "BELOW_NUMERIC_MINIMUM"),
                       withheld_reason_counts=json.dumps(dict(sorted(reasons.items())), separators=(",", ":")),
                       liquidity_projection_evidence_sha256=digest.hexdigest())
        _store(db, current)

    for batch in records:
        if batch.nbytes > _BATCH_BYTES:
            raise ValueError("Liquidity reader batch exceeds the bounded Arrow byte budget")
        for row in batch.to_pylist():
            security = row["security_id"]
            if current is None or security != current["security_id"]:
                finish()
                current = _empty(year, security, window, inputs)
                previous, values, reasons, digest = None, [], Counter(), hashlib.sha256()
            if row["session"] not in window["sessions"]:
                raise ValueError("Liquidity aggregation read a date outside its exact historical window")
            raw_value = row[_VALUE]
            evidence = [row[field] for field in _DAILY_META]
            evidence.append(None if raw_value is None else struct.pack(">d", raw_value).hex())
            digest.update(json.dumps(evidence, ensure_ascii=True, separators=(",", ":")).encode() + b"\n")
            current["distinct_projection_rows"] += 1
            current["source_records"] += row["projection_record_count"]
            current["equivalent_13_field_record_excess"] += row["projection_record_count"] - 1
            if row["session"] == previous:
                continue
            previous = row["session"]
            current["observed_sessions"] += 1
            if row["security_session_projection_variants"] > 1:
                current["conflicting_sessions"] += 1
                reasons[_CONFLICT] += 1
                continue
            current["unambiguous_sessions"] += 1
            value, reason = _value(row)
            if value is None:
                current["withheld_sessions"] += 1
                reasons[reason] += 1
            else:
                values.append(value)
                current["numerically_valid_sessions"] += 1
                current["zero_volume_candidate_sessions"] += value == 0
                current["trade_price_valid_sessions"] += row["price_flag"] == "TR"
                current["bid_ask_valid_sessions"] += row["price_flag"] == "BA"
    finish()
    db.commit()


def _attach_listings(engine, db, year, window, inputs):
    raw = ",".join(f'"{field}"' for field in NAMES_FIELDS)
    query = (
        "SELECT permno,COUNT(*) n,COUNT(DISTINCT to_json(list_value(" + raw + "))) variants,"
        "MIN(security_year_record_count),MAX(security_year_record_count),"
        "MIN(security_year_distinct_projection_count),MAX(security_year_distinct_projection_count),"
        "MIN(candidate_status),BOOL_AND(ordinary_candidate) FROM names WHERE candidate_year=? GROUP BY permno"
    )
    for batch in engine.execute(query, [year]).fetch_record_batch(_BATCH):
        for record in batch.to_pylist():
            security, n, variants, minimum, maximum, vmin, vmax, status, ordinary = record.values()
            if minimum != n or maximum != n or vmin != variants or vmax != variants:
                raise ValueError("Names actual overlap groups disagree with their declared projection counts")
            existing = db.execute("SELECT payload FROM annual WHERE year=? AND security=?", (year, security)).fetchone()
            row = json.loads(existing[0]) if existing else _empty(year, security, window, inputs)
            row.update(listing_record_count=n, listing_distinct_projection_count=variants,
                       listing_candidate_status="AMBIGUOUS_DATED_RECORDS" if n > 1 else status,
                       ambiguous_listing=n > 1, ordinary_listing_candidate=n == 1 and ordinary,
                       rank_eligible_by_candidate_policy=n == 1 and ordinary and row["meets_numeric_minimum_40"])
            _store(db, row)
    db.commit()


class _Writer:
    def __init__(self, out):
        self.out, self.parts, self.rows, self.bytes = out, [], 0, 0
        self.buffer = []

    def append(self, row):
        self.buffer.append(row)
        self.bytes += 4 * sum(len(value) for value in row.values() if isinstance(value, str)) + 512
        if len(self.buffer) >= _BATCH or self.bytes >= _BATCH_BYTES:
            self.flush()

    def flush(self):
        if not self.buffer:
            return
        if len(self.parts) >= _MAX_PARTS:
            raise ValueError("Annual output exceeds the bounded part-manifest limit")
        relative = f"annual_liquidity/part-{len(self.parts) + 1:06d}.parquet"
        path = self.out / relative
        with path.open("xb") as handle:
            pq.write_table(pa.Table.from_pylist(self.buffer, schema=ANNUAL_SCHEMA), handle, compression="zstd")
            handle.flush()
            os.fsync(handle.fileno())
        path.chmod(0o400)
        self.parts.append({"file": relative, "sha256": _hash(path), "bytes": path.stat().st_size,
                           "rows": len(self.buffer)})
        self.rows += len(self.buffer)
        self.buffer.clear()
        self.bytes = 0


def _emit(db, out, windows, dates, request):
    summaries = {year: {
        "year": year, **{key: value for key, value in window.items() if key != "sessions"},
        "expected_sessions": 60,
        "window_sessions_with_any_daily_candidate": sum(day in dates for day in window["sessions"]),
        "window_sessions_without_any_daily_candidate": sum(day not in dates for day in window["sessions"]),
        "request_covers_entire_window": request["start"] <= window["liquidity_start"]
        and window["liquidity_end"] <= request["end"],
        "security_year_rows": 0, "names_only_securities": 0, "daily_only_securities": 0,
        "names_and_daily_securities": 0, "ambiguous_listing_securities": 0,
        "ordinary_listing_candidates": 0, "numeric_minimum_met_securities": 0,
        "ranked_candidate_securities": 0, "positive_means_rounded_to_zero": 0,
        **dict.fromkeys(_COUNTS, 0), "listing_status_counts": Counter(),
        "coverage_status_counts": Counter(), "withheld_reason_counts": Counter(),
    } for year, window in windows.items()}
    query = (
        "WITH ranked AS (SELECT year,security,ROW_NUMBER() OVER (PARTITION BY year "
        "ORDER BY mean DESC,security COLLATE BINARY ASC) rank FROM annual WHERE rankable=1) "
        "SELECT a.payload,r.rank FROM annual a LEFT JOIN ranked r USING(year,security) "
        "ORDER BY a.year,a.security COLLATE BINARY"
    )
    writer = _Writer(out)
    for payload, rank in db.execute(query):
        row = json.loads(payload)
        row["candidate_security_rank"] = rank
        writer.append(row)
        summary = summaries[row["candidate_year"]]
        names, daily = row["listing_record_count"] > 0, row["observed_sessions"] > 0
        summary["security_year_rows"] += 1
        summary["names_only_securities"] += names and not daily
        summary["daily_only_securities"] += daily and not names
        summary["names_and_daily_securities"] += names and daily
        summary["ambiguous_listing_securities"] += row["ambiguous_listing"]
        summary["ordinary_listing_candidates"] += row["ordinary_listing_candidate"]
        summary["numeric_minimum_met_securities"] += row["meets_numeric_minimum_40"]
        summary["ranked_candidate_securities"] += rank is not None
        summary["positive_means_rounded_to_zero"] += row["positive_mean_rounded_to_zero"]
        for field in _COUNTS:
            summary[field] += row[field]
        summary["listing_status_counts"][row["listing_candidate_status"]] += 1
        summary["coverage_status_counts"][row["coverage_status"]] += 1
        summary["withheld_reason_counts"].update(json.loads(row["withheld_reason_counts"]))
    writer.flush()
    return writer, list(summaries.values())


def _save_bytes(out, name, raw):
    path = out / name
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o400)
    return {"file": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def build_liquidity_candidates(numerical_candidates, listing_candidates, *, output, config, repo_root="."):
    """Produce a provisional observed-security ranking with unresolved availability."""
    repo = Path(repo_root).resolve()
    verify_lock(config, repo / "configs/protocol.lock.json")
    if (config["initial_train_start"], config["development_end"], config["holdout_start"],
            config["liquidity_lookback_sessions"], config["liquidity_min_valid_sessions"]) != (2010, 2021, 2022, 60, 40):
        raise ValueError("Annual liquidity candidates require frozen 2010–2021 and 60/40 windows")
    out = _private_directory(output, repo)
    inputs = [_load(numerical_candidates, "numerical", config), _load(listing_candidates, "listing", config)]
    if inputs[0].directory == inputs[1].directory or any(out.is_relative_to(item.directory) for item in inputs):
        raise ValueError("Liquidity output must be separate from its preserved input bundles")
    windows = {year: year_start_window(year, config) for year in YEARS}
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".wrds-liquidity-", dir=out.parent) as temporary:
        work = Path(temporary)
        bundle = work / "bundle"
        bundle.mkdir(mode=0o700)
        for folder in ("annual_liquidity", "listing_evidence", "input_receipts"):
            (bundle / folder).mkdir(mode=0o700)
        snapshots = []
        for item in inputs:
            snapshots.append(_save_bytes(bundle, f"input_receipts/{item.role}.json", item.raw))
            snapshots.append(_save_bytes(bundle, f"input_receipts/{item.role}_source.json", item.chain_raw))
        coverage = _numerical_preflight(inputs[0], work)
        listing_counts = _listing_preflight(inputs[1], windows)
        _guard(inputs)
        _validate_listing_values(inputs[1])
        details = []
        for index, (path, specification) in enumerate(inputs[1].parts, start=1):
            name = f"listing_evidence/part-{index:06d}.parquet"
            digest, size = _copy_source(path, bundle / name)
            if digest != specification["sha256"] or size != specification["bytes"]:
                raise ValueError("Names detail copy changed from its bound source part")
            details.append({"file": name, "sha256": digest, "bytes": size, "rows": specification["rows"],
                            "upstream_part": specification["file"]})
        with closing(sqlite3.connect(str(work / "annual.sqlite3"))) as db:
            db.execute("PRAGMA cache_size=-16384")
            db.execute("PRAGMA temp_store=FILE")
            db.execute("CREATE TABLE annual(year INTEGER,security TEXT,payload TEXT,mean REAL,rankable INTEGER,"
                       "PRIMARY KEY(year,security)) WITHOUT ROWID")
            engine = duckdb.connect(str(work / "work.duckdb"), config={
                "memory_limit": "1GB", "threads": 2, "preserve_insertion_order": False,
                "temp_directory": str(work / "spill"),
            })
            try:
                for name, item, schema in (("daily", inputs[0], numerical.CANDIDATE_SCHEMA),
                                           ("names", inputs[1], listing.CANDIDATE_SCHEMA)):
                    if item.parts:
                        engine.read_parquet([str(path) for path, _ in item.parts]).create_view(name)
                    else:
                        engine.from_arrow(pa.Table.from_batches([], schema=schema)).create_view(name)
                engine.execute("CREATE TABLE window_sessions(session VARCHAR PRIMARY KEY)")
                selected = ",".join(f'd."{field}"' for field in [*_DAILY_META, _VALUE])
                for year, window in windows.items():
                    engine.execute("DELETE FROM window_sessions")
                    engine.executemany("INSERT INTO window_sessions VALUES (?)", [(day,) for day in window["sessions"]])
                    records = engine.execute(
                        f"SELECT {selected} FROM daily d JOIN window_sessions w USING(session) "
                        "ORDER BY d.security_id,d.session,d.projection_sha256"
                    ).fetch_record_batch(_BATCH)
                    _aggregate_daily(db, records, year, window, inputs)
                    _attach_listings(engine, db, year, window, inputs)
            finally:
                engine.close()
            writer, summaries = _emit(db, bundle, windows, coverage["dates"], inputs[0].receipt["request"])
        _guard(inputs, rehash=True)
        for specification in [*snapshots, *details, *writer.parts]:
            path = bundle / specification["file"]
            if path.stat().st_size != specification["bytes"] or _hash(path) != specification["sha256"]:
                raise ValueError("A completed private output or receipt snapshot changed")
        receipt = {
            "schema_version": 1, "status": STATUS, "created_at": datetime.now(timezone.utc).isoformat(),
            "protocol_sha256": canonical_hash(config), "years": list(YEARS),
            "inputs": {item.role: {"directory": str(item.directory), "receipt_sha256": item.sha256,
                       "status": item.receipt["status"], "parts": len(item.parts)} for item in inputs},
            "input_receipts": snapshots,
            "input_preflight": {"numerical_rows": coverage["rows"],
                                "represented_source_records": coverage["represented_source_records"],
                                "conflicting_security_session_keys": coverage["conflicting_security_session_keys"],
                                "names_snapshot_rows": sum(listing_counts.values()),
                                "all_input_dates_before_numerical_values": True,
                                "upstream_parts_and_receipts_rehashed_before_completion": True,
                                "original_csv_files_reopened": False},
            "annual_liquidity": {"parts": writer.parts, "rows": writer.rows,
                                 "fields": ANNUAL_SCHEMA.names,
                                 "security_population": "union of January 1 Names snapshots and exact-window daily candidates"},
            "listing_evidence": {"parts": details, "rows": sum(listing_counts.values()),
                                 "all_upstream_rows_and_ambiguities_retained": True,
                                 "upstream_parquet_bytes_preserved": True},
            "year_summaries": summaries,
            "reconciliation": inputs[0].receipt["reconciliation"],
            "policies": {
                "windows": "fixed 2010–2021; exact preceding 60 XNYS sessions from year_start_window",
                "minimum": "40 finite nonnegative, unambiguous, source-review liquidity candidates; no imputation",
                "mean_precision": "exact rational sum of delivered IEEE 754 binary64 values divided by valid session count, rounded once to binary64",
                "mean_reconstructs_raw_decimal_values": False,
                "duplicates": "collapsed exact required-13-field repetitions count once per security/session; raw repetition counts never weight the mean",
                "conflicts": "all variants withheld; one conflicting session regardless of variant count or agreement of price-volume values",
                "zero": "zero proxy is a recorded-zero-volume candidate under the upstream positive-price policy; missing sessions are separate",
                "rank": "all observed unambiguous ordinary listing candidates with at least 40 numeric-valid sessions; descending candidate mean, ascending exact raw security ID",
                "rank_ties": "equality of the reported binary64 means; SQLite BINARY raw-string ordering",
                "daily_provenance": "bound numerical receipt and parts retain projection hashes and representative source SHA/inventory SHA/CSV ordinal; per-window ordered evidence digest binds every observed projection",
                "evidence_digest": "SHA-256 of newline-delimited compact ASCII JSON arrays in security/session/projection-SHA order; fields are daily_evidence_fields, with candidate float encoded as big-endian binary64 hex or null",
                "daily_evidence_fields": [*_DAILY_META, _VALUE],
                "listing_overlap": "every Names row preserved; any multiple-record security/year is withheld from ranking, including exact repeats",
                "historical_availability": "known_at and available_at remain NULL; calendar information_cutoff is not evidence of availability",
                "source_conventions_and_population_reviewed": False,
                "benchmark_reconciliation_changed": False,
            },
            "processing": {"duckdb_memory_limit": "1GB", "duckdb_threads": 2,
                           "duckdb_sort_partition": "one frozen year window at a time",
                           "sqlite_cache_kib": 16384, "arrow_batch_rows": _BATCH,
                           "arrow_batch_byte_limit": _BATCH_BYTES, "maximum_mean_values_in_memory": 60},
            "known_at_null_rows": writer.rows, "available_at_null_rows": writer.rows,
            "historical_availability_verified": False, "cik_mapping_created": False,
            "issuer_grouping_performed": False, "issuer_limit_applied": False,
            "universe_membership_created": False, "model_ready": False, "source_approvals": 0,
            "prior_arithmetic_review_modified": False, "final_period_opened": False,
        }
        _save_bytes(bundle, "receipt.json", (json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
        if out.exists():
            raise ValueError("Liquidity output appeared during construction; it must not be overwritten")
        bundle.rename(out)
    return receipt


def aggregate_summary(receipt):
    """Expose bounded counts and policy state, without raw IDs, flags or values."""
    return {"status": receipt["status"], "protocol_sha256": receipt["protocol_sha256"],
            "years": receipt["years"], "annual_security_rows": receipt["annual_liquidity"]["rows"],
            "annual_parts": len(receipt["annual_liquidity"]["parts"]),
            "names_detail_rows": receipt["listing_evidence"]["rows"],
            "year_summaries": receipt["year_summaries"],
            "requested_window_numerically_reconciled":
            receipt["reconciliation"]["requested_window_numerically_reconciled"],
            "model_ready": False, "source_approvals": 0, "issuer_grouping_performed": False,
            "issuer_limit_applied": False, "historical_availability_verified": False,
            "prior_arithmetic_review_modified": False, "final_period_opened": False}
