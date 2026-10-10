"""Provisional annual listing evidence from preserved, dated Names metadata.

This module creates no universe membership or historical availability claim.
Every full source interval is validated before classification. All matching
Names records, including duplicates and overlaps, remain in private snapshots.
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
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .manual_wrds_intake import _hash, _identity, _iso, _private_directory
from .manual_wrds_metadata import NAMES_FIELDS, _metadata_rows
from .manual_wrds_stage import _read_receipt, _safe_source, _write_json
from .protocol import canonical_hash, verify_lock
from .universe import year_start_window

YEARS = tuple(range(2010, 2022))
_BATCH_ROWS = 5000
_BATCH_BYTES = 8 * 1024 * 1024
_MAX_PARTS = 100_000
_SHA = re.compile(r"[0-9a-f]{64}")
_PERMNO = re.compile(r"[0-9]{1,20}")
_BOUNDS = ("secinfostartdt", "secinfoenddt", "securitybegdt", "securityenddt")
KNOWN_CODES = {
    "securitytype": ("DERV", "EQTY", "FUND", "N/A"),
    "securitysubtype": ("ATR", "CEF", "COM", "ETF", "ETV", "UNK"),
    "sharetype": ("AD", "CE", "N/A", "NS", "SB", "UG"),
    "issuertype": ("ACOR", "CORP", "N/A", "REIT"),
    "primaryexch": ("A", "B", "I", "N", "Q", "R", "X"),
    "tradingstatusflg": ("A", "D", "H", "S", "X"),
    "securityactiveflg": ("N", "Y"),
    "usincflg": ("N", "X", "Y"),
}
POLICY = {
    "id": "dated_names_ordinary_corporate_common_candidates_v1",
    "years": list(YEARS), "selection_date": "January 1",
    "securitytype": ["EQTY"], "securitysubtype": ["COM"], "sharetype": ["NS"],
    "issuertype": ["ACOR", "CORP"], "primaryexch": ["A", "B", "I", "N", "Q", "R"],
    "tradingstatusflg": ["A"], "usincflg_filter": None,
    "securityactiveflg_filter": None, "header_exchange_or_sic_used": False,
    "secinfo_interval_inclusive": True, "securitylife_is_diagnostic_only": True,
    "overlapping_records_including_exact_repeats_are_ambiguous": True,
    "ordinary_subset_is_not_the_complete_protocol_universe": True,
    "conditionaltype_available": False, "regular_way_trading_verified": False,
    "known_at_inferred": False,
    "official_definition_urls": [
        "https://www.crsp.org/wp-content/uploads/appendix/FlagType_S3.html",
        "https://www.crsp.org/wp-content/uploads/appendix/FlagType_S2.html",
        "https://www.crsp.org/wp-content/uploads/appendix/FlagType_S4.html",
        "https://www.crsp.org/wp-content/uploads/appendix/FlagType_IT.html",
        "https://www.crsp.org/wp-content/uploads/appendix/FlagType_EC.html",
        "https://www.crsp.org/wp-content/uploads/appendix/FlagType_TS.html",
        "https://www.crsp.org/wp-content/uploads/appendix/FlagType_YN.html",
        "https://www.crsp.org/wp-content/uploads/appendix/FlagType_FK.html",
        "https://www.crsp.org/wp-content/uploads/ShareCode.html",
    ],
    "definition_version_bound_to_vendor_release": False,
}
_EXTRA_FIELDS = [
    pa.field("source_sha256", pa.string(), nullable=False),
    pa.field("source_inventory_sha256", pa.string(), nullable=False),
    pa.field("source_csv_record", pa.int64(), nullable=False),
    pa.field("candidate_year", pa.int16(), nullable=False),
    pa.field("selection_asof", pa.string(), nullable=False),
    pa.field("information_cutoff", pa.string(), nullable=False),
    pa.field("selection_session", pa.string(), nullable=False),
    pa.field("known_at", pa.string(), nullable=True),
    pa.field("classification_status", pa.string(), nullable=False),
    pa.field("candidate_status", pa.string(), nullable=False),
    pa.field("ordinary_candidate", pa.bool_(), nullable=False),
    pa.field("recognized_us_venue", pa.bool_(), nullable=False),
    pa.field("dated_active_trading", pa.bool_(), nullable=False),
    pa.field("ambiguous_security_year", pa.bool_(), nullable=False),
    pa.field("security_year_record_count", pa.int64(), nullable=False),
    pa.field("security_year_distinct_projection_count", pa.int64(), nullable=False),
    pa.field("securitylife_covers_selection", pa.bool_(), nullable=False),
]
CANDIDATE_SCHEMA = pa.schema(
    [pa.field(field, pa.string(), nullable=False) for field in NAMES_FIELDS] + _EXTRA_FIELDS
)


@dataclass
class _Source:
    directory: Path
    receipt: dict
    receipt_path: Path
    receipt_identity: tuple
    receipt_sha256: str
    receipt_snapshot: Path
    path: Path
    identity: tuple
    sha256: str


def _guard(source, *, rehash=False):
    path = _safe_source(source.directory, source.receipt["source"]["preserved_file"])
    if path != source.path or _identity(path) != source.identity:
        raise ValueError("Preserved Names source changed during candidate generation")
    if _identity(source.receipt_path) != source.receipt_identity:
        raise ValueError("Names inventory receipt changed during candidate generation")
    if rehash:
        if _hash(path) != source.sha256 or _identity(path) != source.identity:
            raise ValueError("Preserved Names source hash disagrees with its inventory")
        if (_hash(source.receipt_path) != source.receipt_sha256
                or _identity(source.receipt_path) != source.receipt_identity
                or _hash(source.receipt_snapshot) != source.receipt_sha256):
            raise ValueError("Names receipt or its preserved snapshot changed")


def _load_source(directory, out, config):
    directory = Path(directory).resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("Names inventory must be a directory")
    receipt_path = directory / "receipt.json"
    receipt, raw, identity = _read_receipt(receipt_path)
    if (type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1
            or receipt.get("role") != "names"
            or receipt.get("status") != "RAW_MANUAL_WRDS_METADATA_INVENTORY_NOT_SOURCE_APPROVED"
            or receipt.get("protocol_sha256") != canonical_hash(config)):
        raise ValueError("Names inventory schema, role, status, or frozen protocol does not match")
    metadata = receipt.get("source")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("sha256"), str) or not _SHA.fullmatch(metadata["sha256"]):
        raise ValueError("Names inventory source hash is invalid")
    if type(metadata.get("bytes")) is not int or metadata["bytes"] < 0:
        raise ValueError("Names source byte count is invalid")
    header = metadata.get("observed_header")
    if (not isinstance(header, list) or len(header) != len(NAMES_FIELDS)
            or not all(isinstance(field, str) for field in header)
            or {field.lower() for field in header} != set(NAMES_FIELDS)):
        raise ValueError("Names inventory must declare the exact 24 distinct source fields")
    for key in ("required_column_count", "delivered_column_count"):
        if metadata.get(key) != len(NAMES_FIELDS):
            raise ValueError("Names inventory column counts disagree with its schema")
    counts = receipt.get("all_rows")
    if not isinstance(counts, dict) or type(counts.get("rows")) is not int or counts["rows"] < 1:
        raise ValueError("Names inventory source record count is invalid")
    bounds = receipt.get("date_bounds")
    if not isinstance(bounds, dict) or not all(isinstance(bounds.get(field), dict) for field in _BOUNDS):
        raise ValueError("Names inventory date-bound counts are missing")
    path = _safe_source(directory, metadata.get("preserved_file"))
    source_identity = _identity(path)
    if source_identity[2] != metadata["bytes"]:
        raise ValueError("Preserved Names source byte count disagrees with its receipt")
    snapshot = out / "input_receipts" / "names.json"
    with snapshot.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    snapshot.chmod(0o400)
    source = _Source(directory, receipt, receipt_path, identity, hashlib.sha256(raw).hexdigest(),
                     snapshot, path, source_identity, metadata["sha256"])
    _guard(source, rehash=True)
    return source


def _date_preflight(source, db):
    """Store raw records on disk while checking ALL dates, without classification."""
    _guard(source)
    rows, batch, batch_bytes = 0, [], 0
    bounds = {field: {"first_finite_date": None, "last_finite_date": None} for field in _BOUNDS}

    def flush():
        nonlocal batch_bytes
        db.executemany("INSERT INTO source_rows VALUES (?,?,?,?,?,?,?)", batch)
        db.commit()
        batch.clear()
        batch_bytes = 0

    with _metadata_rows(source.path, "names") as (header, canonical, records):
        if header != source.receipt["source"]["observed_header"]:
            raise ValueError("Names source header disagrees with its inventory")
        indices = [canonical.index(field) for field in NAMES_FIELDS]
        for record_number, delivered in enumerate(records, start=2):
            values = [delivered[index] for index in indices]
            row = dict(zip(NAMES_FIELDS, values, strict=True))
            for field in _BOUNDS:
                value = _iso(row[field], f"Names {field}")
                current = bounds[field]
                current["first_finite_date"] = min(current["first_finite_date"] or value, value)
                current["last_finite_date"] = max(current["last_finite_date"] or value, value)
            if row["secinfostartdt"] > row["secinfoenddt"] or row["securitybegdt"] > row["securityenddt"]:
                raise ValueError("Names source contains a reversed metadata interval")
            payload = json.dumps(values, ensure_ascii=True, separators=(",", ":"))
            batch.append((record_number, row["permno"], row["secinfostartdt"], row["secinfoenddt"],
                          row["securitybegdt"], row["securityenddt"], payload))
            batch_bytes += 4 * len(payload) + 256
            rows += 1
            if len(batch) >= _BATCH_ROWS or batch_bytes >= _BATCH_BYTES:
                flush()
        flush()
    _guard(source, rehash=True)
    if rows != source.receipt["all_rows"]["rows"]:
        raise ValueError("Names source record count disagrees with its inventory")
    for field, actual in bounds.items():
        declared = source.receipt["date_bounds"][field]
        if declared.get("finite_iso_date") != rows or any(declared.get(key) != value for key, value in actual.items()):
            raise ValueError("Names date-bound counts or coverage disagree with the inventory")
    return {"rows": rows, "date_bounds": bounds}


def _classify(row):
    """Classify only after the full source interval preflight has succeeded."""
    security, subtype, share, issuer = (row[field] for field in
                                         ("securitytype", "securitysubtype", "sharetype", "issuertype"))
    if security != "EQTY" or subtype != "COM":
        if security in ("FUND", "DERV") or (security == "EQTY" and subtype in ("ATR", "CEF", "ETF", "ETV")):
            return "KNOWN_NON_COMMON_CLASSIFICATION"
        return "UNRESOLVED_SECURITY_CLASSIFICATION"
    special = {"AD": "ADR", "SB": "BENEFICIAL_INTEREST", "CE": "CERTIFICATE", "UG": "UNIT"}
    if share in special:
        return f"SCOPE_REVIEW_{special[share]}_COMMON"
    if issuer == "REIT":
        return "SCOPE_REVIEW_REIT_COMMON"
    if share == "NS" and issuer in ("ACOR", "CORP"):
        return "ORDINARY_CORPORATE_COMMON_CLASSIFICATION"
    return "SCOPE_REVIEW_UNKNOWN_COMMON_FORM"


def _candidate_status(row, classification, ambiguous):
    permno = row["permno"]
    if not _PERMNO.fullmatch(permno) or not permno.strip("0"):
        return "UNRESOLVED_SECURITY_IDENTIFIER"
    if ambiguous:
        return "AMBIGUOUS_DATED_RECORDS"
    if classification != "ORDINARY_CORPORATE_COMMON_CLASSIFICATION":
        return classification
    if row["primaryexch"] not in POLICY["primaryexch"]:
        return "UNRESOLVED_LISTING_VENUE"
    trading = row["tradingstatusflg"]
    if trading != "A":
        return {"D": "DATED_DELISTED", "H": "DATED_HALTED", "S": "DATED_SUSPENDED"}.get(
            trading, "UNRESOLVED_TRADING_STATUS")
    return "ORDINARY_CORPORATE_COMMON_CANDIDATE"


class _Writer:
    def __init__(self, out):
        self.out, self.parts, self.rows, self.buffer_bytes = out, [], 0, 0
        self.columns = {field.name: [] for field in CANDIDATE_SCHEMA}

    def append(self, row):
        for field in CANDIDATE_SCHEMA:
            self.columns[field.name].append(row[field.name])
        self.buffer_bytes += 4 * sum(len(value) for value in row.values() if isinstance(value, str)) + 256
        if len(self.columns["candidate_year"]) >= _BATCH_ROWS or self.buffer_bytes >= _BATCH_BYTES:
            self.flush()

    def flush(self):
        count = len(self.columns["candidate_year"])
        if not count:
            return
        if len(self.parts) >= _MAX_PARTS:
            raise ValueError("Listing candidates exceed the bounded part-manifest limit")
        relative = f"candidates/part-{len(self.parts) + 1:06d}.parquet"
        path = self.out / relative
        with path.open("xb") as handle:
            pq.write_table(pa.Table.from_pydict(self.columns, schema=CANDIDATE_SCHEMA), handle, compression="zstd")
            handle.flush()
            os.fsync(handle.fileno())
        path.chmod(0o400)
        self.parts.append({"file": relative, "sha256": _hash(path), "bytes": path.stat().st_size, "rows": count})
        self.rows += count
        for values in self.columns.values():
            values.clear()
        self.buffer_bytes = 0


def _year_summary(year, window):
    return {"year": year, "selection_asof": window["selection_asof"],
            "information_cutoff": window["information_cutoff"],
            "selection_session": window["selection_session"],
            "candidate_snapshot_rows": 0, "ordinary_candidate_rows": 0,
            "status_counts": Counter(), "classification_counts": Counter(),
            "securitylife_does_not_cover_selection_rows": 0,
            "known_flag_counts": {field: {"known_code_counts": dict.fromkeys(codes, 0),
                                           "unknown_or_blank_rows": 0} for field, codes in KNOWN_CODES.items()}}


def _emit_candidates(source, db, out, windows):
    summaries = {year: _year_summary(year, window) for year, window in windows.items()}
    db.execute("CREATE TABLE matches(year INTEGER,record INTEGER,permno TEXT,"
               "PRIMARY KEY(year,record)) WITHOUT ROWID")
    db.execute("INSERT INTO matches SELECT y.year,s.record,s.permno FROM years y JOIN source_rows s "
               "ON s.info_start<=y.asof AND s.info_end>=y.asof")
    db.execute("CREATE TABLE groups(year INTEGER,permno TEXT,n INTEGER,variants INTEGER,"
               "PRIMARY KEY(year,permno)) WITHOUT ROWID")
    db.execute("INSERT INTO groups SELECT m.year,m.permno,COUNT(*),COUNT(DISTINCT s.payload) "
               "FROM matches m JOIN source_rows s ON s.record=m.record GROUP BY m.year,m.permno")
    db.commit()
    writer = _Writer(out)
    query = ("SELECT m.year,s.record,s.payload,g.n,g.variants FROM matches m "
             "JOIN source_rows s ON s.record=m.record "
             "JOIN groups g ON g.year=m.year AND g.permno=m.permno ORDER BY m.year,m.record")
    for year, record, payload, count, variants in db.execute(query):
        row = dict(zip(NAMES_FIELDS, json.loads(payload), strict=True))
        classification = _classify(row)
        status = _candidate_status(row, classification, count > 1)
        window = windows[year]
        ordinary = status == "ORDINARY_CORPORATE_COMMON_CANDIDATE"
        life_covers = row["securitybegdt"] <= window["selection_asof"] <= row["securityenddt"]
        summary = summaries[year]
        summary["candidate_snapshot_rows"] += 1
        summary["ordinary_candidate_rows"] += ordinary
        summary["status_counts"][status] += 1
        summary["classification_counts"][classification] += 1
        summary["securitylife_does_not_cover_selection_rows"] += not life_covers
        for field, counts in summary["known_flag_counts"].items():
            if row[field] in counts["known_code_counts"]:
                counts["known_code_counts"][row[field]] += 1
            else:
                counts["unknown_or_blank_rows"] += 1
        row.update(source_sha256=source.sha256, source_inventory_sha256=source.receipt_sha256,
                   source_csv_record=record, candidate_year=year,
                   selection_asof=window["selection_asof"], information_cutoff=window["information_cutoff"],
                   selection_session=window["selection_session"], known_at=None,
                   classification_status=classification, candidate_status=status, ordinary_candidate=ordinary,
                   recognized_us_venue=row["primaryexch"] in POLICY["primaryexch"],
                   dated_active_trading=row["tradingstatusflg"] == "A",
                   ambiguous_security_year=count > 1, security_year_record_count=count,
                   security_year_distinct_projection_count=variants, securitylife_covers_selection=life_covers)
        writer.append(row)
    writer.flush()
    for year, summary in summaries.items():
        groups, ambiguous, ambiguous_rows, duplicate_excess, conflicting = db.execute(
            "SELECT COUNT(*),COALESCE(SUM(n>1),0),COALESCE(SUM(CASE WHEN n>1 THEN n ELSE 0 END),0),"
            "COALESCE(SUM(n-variants),0),COALESCE(SUM(variants>1),0) FROM groups WHERE year=?", (year,)
        ).fetchone()
        summary.update(distinct_raw_permno_groups=groups, ambiguous_security_year_groups=ambiguous,
                       ambiguous_candidate_rows=ambiguous_rows,
                       exact_24_field_duplicate_snapshot_excess=duplicate_excess,
                       security_year_groups_with_different_24_field_projections=conflicting)
        summary["status_counts"] = dict(summary["status_counts"])
        summary["classification_counts"] = dict(summary["classification_counts"])
    expected = db.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    source_rows_matched = db.execute("SELECT COUNT(DISTINCT record) FROM matches").fetchone()[0]
    if expected != writer.rows:
        raise ValueError("Not every dated Names record was preserved in candidate snapshots")
    return writer, list(summaries.values()), source_rows_matched


def build_listing_candidates(names_inventory, *, output, config, repo_root="."):
    """Build unapproved 2010–2021 annual metadata snapshots, without any CIK join."""
    verify_lock(config, Path(repo_root) / "configs" / "protocol.lock.json")
    if (config["initial_train_start"] != 2010 or config["development_end"] != 2021
            or config["holdout_start"] != 2022):
        raise ValueError("Listing candidates require frozen development years 2010 through 2021")
    windows = {year: year_start_window(year, config) for year in YEARS}
    out = _private_directory(output, repo_root)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    (out / "input_receipts").mkdir(mode=0o700)
    (out / "candidates").mkdir(mode=0o700)
    source = _load_source(names_inventory, out, config)
    with tempfile.TemporaryDirectory(prefix="listing-candidates-", dir=out) as temporary:
        with closing(sqlite3.connect(str(Path(temporary) / "candidates.sqlite3"))) as db:
            db.execute("PRAGMA cache_size=-16384")
            db.execute("PRAGMA temp_store=FILE")
            db.execute("CREATE TABLE source_rows(record INTEGER PRIMARY KEY,permno TEXT,info_start TEXT,"
                       "info_end TEXT,life_start TEXT,life_end TEXT,payload TEXT)")
            db.execute("CREATE TABLE years(year INTEGER PRIMARY KEY,asof TEXT)")
            db.executemany("INSERT INTO years VALUES (?,?)",
                           ((year, window["selection_asof"]) for year, window in windows.items()))
            actual = _date_preflight(source, db)
            # No classification occurs above this point, even for an early row
            # whose later source records contain malformed or unresolved bounds.
            _guard(source)
            writer, summaries, matched = _emit_candidates(source, db, out, windows)
    _guard(source, rehash=True)
    receipt = {
        "schema_version": 1, "status": "DATED_NAMES_LISTING_CANDIDATES_NOT_SOURCE_APPROVED",
        "created_at": datetime.now(timezone.utc).isoformat(), "protocol_sha256": canonical_hash(config),
        "years": list(YEARS), "candidate_policy": POLICY, "candidate_policy_sha256": canonical_hash(POLICY),
        "source": {"inventory_directory": str(source.directory), "preserved_file": source.receipt["source"]["preserved_file"],
                   "source_sha256": source.sha256, "source_bytes": source.identity[2],
                   "inventory_receipt_file": "input_receipts/names.json", "inventory_receipt_sha256": source.receipt_sha256,
                   "observed_header": source.receipt["source"]["observed_header"],
                   "source_rows": actual["rows"], "source_rows_with_annual_snapshot": matched,
                   "source_rows_without_annual_snapshot": actual["rows"] - matched,
                   "actual_date_bounds": actual["date_bounds"],
                   "full_history_retained_in_original": True, "original_source_rows_removed": 0,
                   "inventory_row_and_date_counts_verified": True,
                   "source_release": None, "vendor_execution_verified": False,
                   "historical_field_lineage_verified": False},
        "projection": {"raw_fields": list(NAMES_FIELDS), "derived_fields": [field.name for field in _EXTRA_FIELDS],
                       "parts": writer.parts, "rows": writer.rows,
                       "all_matching_source_record_year_pairs_retained": True,
                       "exact_duplicate_records_retained": True,
                       "duplicate_comparison_scope": "exact parsed text across all 24 canonical Names fields",
                       "security_year_grouping": "exact raw PERMNO text and development year; no identifier coercion",
                       "ambiguous_overlaps_withheld_from_ordinary_candidates": True,
                       "source_csv_record_numbering": "Header is CSV record 1; multiline values do not add records",
                       "licensed_metadata_private_only": True},
        "year_summaries": summaries,
        "complete_source_date_pass_before_classification": True,
        "source_hash_verified_before_after_preflight_and_after_output": True,
        "unresolved_or_reversed_source_bounds_inferred": False,
        "information_cutoff_is_calendar_metadata_not_known_at": True,
        "known_at_supplied_or_inferred": False, "known_at_null_rows": writer.rows,
        "values_filled": 0, "raw_values_normalized": 0,
        "final_exclusions_created": False, "cik_mapping_created": False,
        "universe_membership_created": False, "liquidity_or_rank_computed": False,
        "source_population_completeness_verified": False,
        "model_ready": False, "source_approvals": 0,
        "prior_arithmetic_review_modified": False, "final_period_opened": False,
    }
    _write_json(out / "receipt.json", receipt)
    return receipt


def aggregate_summary(receipt):
    """Bounded public summary; source identifiers and raw metadata stay private."""
    return {"status": receipt["status"], "protocol_sha256": receipt["protocol_sha256"],
            "source_sha256": receipt["source"]["source_sha256"],
            "source_rows": receipt["source"]["source_rows"],
            "source_rows_with_annual_snapshot": receipt["source"]["source_rows_with_annual_snapshot"],
            "source_rows_without_annual_snapshot": receipt["source"]["source_rows_without_annual_snapshot"],
            "candidate_snapshot_rows": receipt["projection"]["rows"],
            "parquet_parts": len(receipt["projection"]["parts"]), "year_summaries": receipt["year_summaries"],
            "known_at_null_rows": receipt["known_at_null_rows"],
            "model_ready": False, "source_approvals": 0,
            "prior_arithmetic_review_modified": False, "final_period_opened": False}
