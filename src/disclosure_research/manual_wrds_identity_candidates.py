"""Offline, unapproved identity evidence from annual Names and full CCM history.

Company-header CIKs remain header observations. No historical CIK, knowledge
timestamp, approved security link, universe selection or market outcome is made.
"""

import csv
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pyarrow as pa
import pyarrow.parquet as pq

from . import manual_wrds_liquidity_candidates as liquidity
from .manual_wrds_intake import _copy_source, _hash, _identity, _iso, _private_directory
from .manual_wrds_metadata import (
    BOUND_KINDS,
    CCM_FIELDS,
    INTERVAL_KINDS,
    NAMES_FIELDS,
    _bound_kind,
    _interval_kind,
    _metadata_rows,
    _raw_tuple,
)
from .manual_wrds_stage import _read_receipt, _safe_source
from .market_data import development_return_end
from .protocol import canonical_hash, verify_lock
from .universe import aware_timestamp, year_start_window

STATUS = "ANNUAL_MANUAL_WRDS_IDENTITY_EVIDENCE_NOT_SOURCE_APPROVED"
YEARS = tuple(range(2010, 2022))
_BATCH = 4096
_BYTES = 8 * 1024 * 1024
_MAX_PARTS = 100_000
_MAX_SEC_BYTES = 16 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}")
_RAW = {name: "ccm_header_cik_raw" if name == "cik" else f"ccm_{name}_raw" for name in CCM_FIELDS}
_LINK_FLAGS = {"linkprim": {"C", "P", "N", "J"},
               "linktype": {"NU", "LU", "NR", "LC", "LX", "LD", "LN", "LS"}}
SEC_FIELDS = tuple("""cik name accessionNumber reportDate acceptance_date acceptance_timestamp
    source_url header_url download_sha256 header_sha256 risk_source_url risk_source_sha256
    extraction_status risk_token_count extraction_version resolution_method resolution_rule_id
    extraction_start extraction_end""".split())


def _field(name, kind=pa.string(), nullable=False):
    return pa.field(name, kind, nullable=nullable)


_CCM_PROVENANCE = [_field("ccm_source_sha256"), _field("ccm_inventory_sha256"),
                   _field("ccm_source_csv_record", pa.int64())]
_NAMES_PROVENANCE = [_field("names_source_sha256"), _field("names_inventory_sha256"),
                     _field("names_source_csv_record", pa.int64())]
_UNKNOWN = [_field("known_at", nullable=True), _field("available_at", nullable=True),
            _field("identity_approved", pa.bool_())]
CCM_SCHEMA = pa.schema([
    *_CCM_PROVENANCE, *[_field(name) for name in _RAW.values()],
    _field("full_delivered_row_sha256"),
    *[_field(name, nullable=True) for name in ("permno_comparison_key", "permco_comparison_key", "header_cik_comparison_key")],
    *[_field(name) for name in ("permno_grammar", "permco_grammar", "header_cik_grammar",
                               "link_start_kind", "link_end_kind", "inventory_requested_interval_kind")],
    *_UNKNOWN,
])
PAIR_SCHEMA = pa.schema([
    _field("candidate_year", pa.int16()), _field("selection_asof"), _field("information_cutoff"),
    *_NAMES_PROVENANCE, *_CCM_PROVENANCE,
    *[_field(name) for name in ("names_permno_raw", "names_permco_raw", "ccm_lpermno_raw", "ccm_lpermco_raw",
                               "ccm_gvkey_raw", "ccm_liid_raw", "ccm_linkprim_raw", "ccm_linktype_raw",
                               "ccm_linkdt_raw", "ccm_linkenddt_raw", "ccm_header_cik_raw")],
    _field("header_cik_comparison_key", nullable=True),
    *[_field(name) for name in ("id_comparison", "permco_comparison", "date_relation", "header_cik_grammar",
                               "names_candidate_status")],
    _field("candidate_search", pa.bool_()), _field("names_ambiguous", pa.bool_()),
    _field("ordinary_listing_candidate", pa.bool_()), *_UNKNOWN,
])
_ANNUAL_COUNTS = (
    "names_record_count", "names_distinct_projection_count", "names_exact_duplicate_record_excess",
    "raw_names_ids_sharing_comparison_key", "related_pair_rows", "related_ccm_records",
    "candidate_pair_rows", "candidate_ccm_records", "finite_candidate_ccm_records",
    "open_marker_candidate_ccm_records", "other_unresolved_candidate_ccm_records",
    "before_selection_context_ccm_records", "after_selection_context_ccm_records", "reversed_context_ccm_records",
    "candidate_nonblank_raw_gvkeys", "candidate_header_cik_keys", "candidate_blank_header_cik_records",
    "candidate_unsupported_header_cik_records", "candidate_permco_disagreement_pairs",
    "candidate_permco_unresolved_pairs", "sec_manifest_discovery_pairs", "sec_manifest_discovery_filings",
)
ANNUAL_SCHEMA = pa.schema([
    _field("candidate_year", pa.int16()), _field("selection_asof"), _field("information_cutoff"),
    _field("names_permno_raw"), _field("permno_comparison_key", nullable=True), _field("permno_grammar"),
    *[_field(name, pa.int64()) for name in _ANNUAL_COUNTS],
    _field("names_ambiguous", pa.bool_()), _field("ordinary_listing_candidate", pa.bool_()),
    _field("evidence_status"), _field("listing_candidate_receipt_sha256"), _field("ccm_inventory_sha256"),
    *_UNKNOWN,
])
SEC_MATCH_SCHEMA = pa.schema([
    _field("candidate_year", pa.int16()), *_NAMES_PROVENANCE, *_CCM_PROVENANCE,
    _field("sec_manifest_sha256"), _field("sec_manifest_csv_record", pa.int64()),
    *[_field(name) for name in ("accession", "sec_filer_cik_raw", "sec_filer_cik_comparison_key",
                               "ccm_header_cik_raw", "cik_comparison", "recorded_acceptance_date",
                               "recorded_acceptance_timestamp", "ccm_relation_at_acceptance")],
    _field("ccm_date_compatible_at_acceptance", pa.bool_()),
    _field("names_secinfo_covers_acceptance", pa.bool_()),
    _field("original_sec_bytes_reread", pa.bool_()), *_UNKNOWN,
])
SEC_COVERAGE_SCHEMA = pa.schema([
    _field("sec_manifest_sha256"), _field("sec_manifest_csv_record", pa.int64()),
    _field("acceptance_year", pa.int16()), _field("accession"), _field("sec_filer_cik_raw"),
    _field("sec_filer_cik_comparison_key"), _field("recorded_acceptance_date"),
    _field("discovery_pair_rows", pa.int64()), _field("distinct_raw_names_ids", pa.int64()),
    _field("distinct_ccm_records", pa.int64()), _field("coverage_status"),
    _field("original_sec_bytes_reread", pa.bool_()), *_UNKNOWN,
])


def _integer_key(raw, *, cik=False):
    """Comparison syntax only: no floating conversion, trimming or ID approval."""
    if not raw.strip():
        return None, "blank"
    if not re.fullmatch(r"[0-9]{1," + ("10" if cik else "20") + "}", raw):
        return None, "unsupported_text"
    significant = raw.lstrip("0")
    if not significant:
        return None, "zero_identifier"
    return significant.zfill(10) if cik else significant, "positive_ascii_integer"


def _id_comparison(left, right, left_key, right_key):
    if left_key is None or right_key is None:
        return "UNRESOLVED_IDENTIFIER"
    if left_key != right_key:
        return "DIFFERENT_VALID_COMPARISON_KEYS"
    return "EXACT_RAW_TEXT" if left == right else "LEADING_ZERO_COMPARISON_ONLY"


def _relation(left, right, day):
    """Date-compatible search evidence; nonfinite bounds never become dates."""
    first, last = _bound_kind(left), _bound_kind(right)
    finite_first, finite_last = first == "finite_iso_date", last == "finite_iso_date"
    if finite_first and finite_last and left > right:
        return "REVERSED_FINITE_CONTEXT", False
    if finite_first and left > day:
        return "AFTER_SELECTION_CONTEXT", False
    if finite_last and right < day:
        return "BEFORE_SELECTION_CONTEXT", False
    if finite_first and finite_last:
        return "FINITE_INCLUSIVE_CANDIDATE", True
    if first in {"literal_B", "literal_E"} or last in {"literal_B", "literal_E"}:
        return "OPEN_MARKER_BOUNDS_UNRESOLVED_CANDIDATE", True
    return "OTHER_BOUNDS_UNRESOLVED_CANDIDATE", True


def _unknown():
    return {"known_at": None, "available_at": None, "identity_approved": False}


class _Writer:
    def __init__(self, out, folder, schema):
        self.out, self.folder, self.schema = out, folder, schema
        (out / folder).mkdir(mode=0o700)
        self.parts, self.buffer, self.rows, self.buffer_bytes = [], [], 0, 0

    def append(self, row):
        self.buffer.append(row)
        self.buffer_bytes += 4 * sum(len(value) for value in row.values() if isinstance(value, str)) + 512
        if len(self.buffer) >= _BATCH or self.buffer_bytes >= _BYTES:
            self.flush()

    def flush(self, *, empty=False):
        if not self.buffer and not empty:
            return
        if len(self.parts) >= _MAX_PARTS:
            raise ValueError("Identity evidence exceeds the bounded output manifest limit")
        name = f"{self.folder}/part-{len(self.parts) + 1:06d}.parquet"
        path = self.out / name
        with path.open("xb") as handle:
            pq.write_table(pa.Table.from_pylist(self.buffer, schema=self.schema), handle, compression="zstd")
            handle.flush()
            os.fsync(handle.fileno())
        path.chmod(0o400)
        self.parts.append({"file": name, "sha256": _hash(path), "bytes": path.stat().st_size, "rows": len(self.buffer)})
        self.rows += len(self.buffer)
        self.buffer.clear()
        self.buffer_bytes = 0

    def finish(self):
        self.flush(empty=not self.parts and not self.buffer)
        return {"parts": self.parts, "rows": self.rows, "fields": self.schema.names}


def _load_ccm(directory, config):
    directory = Path(directory).resolve(strict=True)
    receipt_path = directory / "receipt.json"
    receipt, raw, identity = _read_receipt(receipt_path)
    if (type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1
            or receipt.get("role") != "ccm"
            or receipt.get("status") != "RAW_MANUAL_WRDS_METADATA_INVENTORY_NOT_SOURCE_APPROVED"
            or receipt.get("protocol_sha256") != canonical_hash(config)
            or receipt.get("model_ready") is not False
            or type(receipt.get("source_approvals")) is not int or receipt["source_approvals"] != 0
            or receipt.get("prior_arithmetic_review_modified") is not False
            or any(type(receipt.get(field)) is not int or receipt[field] != 0
                   for field in ("rows_dropped", "values_filled", "values_normalized"))):
        raise ValueError("CCM inventory must match the unapproved frozen metadata contract")
    source = receipt["source"]
    path = _safe_source(directory, source["preserved_file"])
    source_identity = _identity(path)
    if (not isinstance(source.get("sha256"), str) or not _SHA.fullmatch(source["sha256"])
            or type(source.get("bytes")) is not int or source["bytes"] != source_identity[2]
            or _hash(path) != source["sha256"] or _identity(path) != source_identity):
        raise ValueError("CCM source size or hash disagrees with its preserved inventory")
    header = source["observed_header"]
    if (not isinstance(header, list) or not 12 <= len(header) <= 256
            or not all(isinstance(field, str) for field in header)
            or len({field.lower() for field in header}) != len(header)
            or set(CCM_FIELDS) - {field.lower() for field in header}
            or source.get("required_column_count") != len(CCM_FIELDS)
            or source.get("delivered_column_count") != len(header)):
        raise ValueError("CCM receipt lacks the required distinct fields and delivered header")
    count = receipt["all_rows"]["rows"]
    if type(count) is not int or count < 0:
        raise ValueError("CCM receipt requires a nonnegative source record count")
    request = receipt["request"]
    start, end = _iso(request["start"], "CCM request start"), _iso(request["end"], "CCM request end")
    if start > end or end > development_return_end(config) or request.get("complete_source_history_preserved") is not True:
        raise ValueError("CCM inventory request or original-history declaration is unsupported")
    return {"directory": directory, "receipt": receipt, "raw": raw, "receipt_path": receipt_path,
            "receipt_identity": identity, "receipt_sha256": hashlib.sha256(raw).hexdigest(),
            "path": path, "identity": source_identity, "sha256": source["sha256"]}


def _guard_ccm(source, *, rehash=False):
    current = _safe_source(source["directory"], source["receipt"]["source"]["preserved_file"])
    if (current != source["path"] or _identity(current) != source["identity"]
            or _identity(source["receipt_path"]) != source["receipt_identity"]):
        raise ValueError("CCM source or receipt changed during identity-evidence construction")
    if rehash and (_hash(current) != source["sha256"] or _identity(current) != source["identity"]
                  or _hash(source["receipt_path"]) != source["receipt_sha256"]
                  or _identity(source["receipt_path"]) != source["receipt_identity"]):
        raise ValueError("CCM source or receipt hash changed during identity-evidence construction")


def _index_ccm(db, source):
    raw_fields = ",".join(f'"{field}" TEXT NOT NULL' for field in CCM_FIELDS)
    derived = "permno_key,permco_key,cik_key,permno_kind,permco_kind,cik_kind,gvkey_kind,start_kind,end_kind,interval_kind,row_sha256"
    db.execute(f"CREATE TABLE ccm(record INTEGER PRIMARY KEY,{raw_fields},"
               + ",".join(f"{field} TEXT" for field in derived.split(",")) + ")")
    receipt = source["receipt"]
    request = receipt["request"]
    bounds = {field: {**dict.fromkeys(BOUND_KINDS, 0), "first_finite_date": None, "last_finite_date": None}
              for field in ("linkdt", "linkenddt")}
    intervals = dict.fromkeys(INTERVAL_KINDS, 0)
    flags = {name: Counter() for name in _LINK_FLAGS}
    grammars = {name: Counter() for name in ("lpermno", "lpermco", "gvkey", "cik")}
    with _metadata_rows(source["path"], "ccm") as (header, canonical, records):
        if header != receipt["source"]["observed_header"]:
            raise ValueError("Actual CCM header disagrees with the preserved inventory")
        columns = {field: {"blank": 0, "nonblank": 0} for field in canonical}
        indices = {field: canonical.index(field) for field in CCM_FIELDS}
        batch, batch_bytes, rows = [], 0, 0
        for record, raw in enumerate(records, 2):
            values = {field: raw[index] for field, index in indices.items()}
            for field, value in zip(canonical, raw, strict=True):
                columns[field]["blank" if not value.strip() else "nonblank"] += 1
            for field in bounds:
                value, kind = values[field], _bound_kind(values[field])
                bounds[field][kind] += 1
                if kind == "finite_iso_date":
                    for name, function in (("first_finite_date", min), ("last_finite_date", max)):
                        prior = bounds[field][name]
                        bounds[field][name] = value if prior is None else function(prior, value)
            interval = _interval_kind(values["linkdt"], values["linkenddt"], request["start"], request["end"])
            intervals[interval] += 1
            keys = {field: _integer_key(values[field], cik=field == "cik") for field in grammars}
            for field, (_, kind) in keys.items():
                grammars[field][kind] += 1
            for field, allowed in _LINK_FLAGS.items():
                value = values[field]
                flags[field][value if value in allowed else "__BLANK__" if not value.strip() else "__UNRECOGNIZED__"] += 1
            entry = (record, *[values[field] for field in CCM_FIELDS],
                     keys["lpermno"][0], keys["lpermco"][0], keys["cik"][0],
                     keys["lpermno"][1], keys["lpermco"][1], keys["cik"][1], keys["gvkey"][1],
                     _bound_kind(values["linkdt"]), _bound_kind(values["linkenddt"]), interval,
                     hashlib.sha256(_raw_tuple(raw).encode()).hexdigest())
            batch.append(entry)
            batch_bytes += 4 * sum(len(value) for value in entry if isinstance(value, str)) + 128
            rows += 1
            if len(batch) >= _BATCH or batch_bytes >= _BYTES:
                db.executemany("INSERT INTO ccm VALUES (" + ",".join("?" for _ in entry) + ")", batch)
                batch.clear()
                batch_bytes = 0
        if batch:
            db.executemany("INSERT INTO ccm VALUES (" + ",".join("?" for _ in batch[0]) + ")", batch)
    if (rows != receipt["all_rows"]["rows"] or columns != receipt["columns"] or bounds != receipt["date_bounds"]
            or intervals != receipt["interval_classifications"]["linkdt/linkenddt"]):
        raise ValueError("Actual CCM row, column or bound counts disagree with its inventory")
    db.execute("CREATE INDEX ccm_permno ON ccm(permno_key)")
    db.commit()
    return {"source_rows": rows, "date_bounds": bounds, "inventory_interval_counts": intervals,
            "identifier_grammar_counts": {key: dict(value) for key, value in grammars.items()},
            "link_flag_counts": {key: dict(value) for key, value in flags.items()}}


def _index_names(db, names):
    db.execute("CREATE TABLE names(year INTEGER,record INTEGER,permno TEXT,permco TEXT,permno_key TEXT,"
               "permco_key TEXT,permno_kind TEXT,info_start TEXT,info_end TEXT,status TEXT,ambiguous INTEGER,"
               "ordinary INTEGER,declared_count INTEGER,declared_variants INTEGER,projection TEXT,"
               "PRIMARY KEY(year,record)) WITHOUT ROWID")
    columns = [*NAMES_FIELDS, "candidate_year", "source_csv_record", "candidate_status",
               "ambiguous_security_year", "ordinary_candidate", "security_year_record_count",
               "security_year_distinct_projection_count"]
    for batch in liquidity._batches(names, columns):
        entries = []
        for row in batch.to_pylist():
            permno, kind = _integer_key(row["permno"])
            permco, _ = _integer_key(row["permco"])
            entries.append((row["candidate_year"], row["source_csv_record"], row["permno"], row["permco"],
                            permno, permco, kind, row["secinfostartdt"], row["secinfoenddt"], row["candidate_status"],
                            int(row["ambiguous_security_year"]), int(row["ordinary_candidate"]),
                            row["security_year_record_count"], row["security_year_distinct_projection_count"],
                            _raw_tuple([row[field] for field in NAMES_FIELDS])))
        db.executemany("INSERT INTO names VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", entries)
    db.execute("CREATE INDEX names_raw_id ON names(year,permno)")
    mismatch = db.execute(
        "SELECT 1 FROM names GROUP BY year,permno HAVING MIN(declared_count)<>COUNT(*) "
        "OR MAX(declared_count)<>COUNT(*) OR MIN(declared_variants)<>COUNT(DISTINCT projection) "
        "OR MAX(declared_variants)<>COUNT(DISTINCT projection) LIMIT 1"
    ).fetchone()
    if mismatch is not None:
        raise ValueError("Names actual overlap groups disagree with their declared projection counts")
    db.execute("CREATE TABLE aliases AS SELECT year,permno_key,COUNT(DISTINCT permno) n FROM names "
               "WHERE permno_key IS NOT NULL GROUP BY year,permno_key")
    db.execute("CREATE UNIQUE INDEX alias_key ON aliases(year,permno_key)")
    db.commit()


def _sec_manifest(source_path, out, db, config):
    db.execute("CREATE TABLE sec(record INTEGER PRIMARY KEY,year INTEGER,cik_raw TEXT,cik_key TEXT,"
               "accession TEXT UNIQUE,day TEXT,stamp TEXT)")
    if source_path is None:
        return {"provided": False, "sha256": None, "rows": 0, "snapshot": None,
                "original_sec_bytes_reread": False}, None
    source = Path(source_path).resolve(strict=True)
    identity = _identity(source)
    if identity[2] > _MAX_SEC_BYTES:
        raise ValueError("SEC source manifest exceeds the bounded metadata size")
    snapshot = out / "input_receipts/sec_manifest.csv"
    digest, size = _copy_source(source, snapshot)
    with snapshot.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("SEC manifest must contain its explicit header") from exc
        if tuple(header) != SEC_FIELDS:
            raise ValueError("SEC manifest must use the supported filing-source schema")
        rows = 0
        for record, values in enumerate(reader, 2):
            if len(values) != len(header):
                raise ValueError("SEC manifest record width disagrees with its header")
            row = dict(zip(header, values, strict=True))
            day = _iso(row["acceptance_date"], "SEC acceptance date")
            year = int(day[:4])
            if not config["initial_train_start"] <= year <= config["development_end"]:
                raise ValueError("SEC manifest includes a filing outside development; final period blocked")
            stamp = aware_timestamp(row["acceptance_timestamp"], "Recorded SEC acceptance timestamp")
            if stamp.tz_convert("America/New_York").date().isoformat() != day:
                raise ValueError("SEC manifest acceptance date and recorded timestamp disagree")
            _iso(row["reportDate"], "SEC recorded report date")
            key, kind = _integer_key(row["cik"], cik=True)
            if kind != "positive_ascii_integer" or not _ACCESSION.fullmatch(row["accessionNumber"]):
                raise ValueError("SEC manifest filer CIK or accession has unsupported syntax")
            for field in ("source_url", "header_url", "risk_source_url"):
                url = urlsplit(row[field])
                if (url.scheme != "https" or url.hostname not in {"sec.gov", "www.sec.gov"}
                        or url.username is not None or url.password is not None or url.query or url.fragment
                        or not url.path.startswith("/Archives/edgar/data/")):
                    raise ValueError("SEC manifest requires recorded official SEC archive URLs")
            for field in ("download_sha256", "header_sha256", "risk_source_sha256"):
                if not _SHA.fullmatch(row[field]):
                    raise ValueError("SEC manifest source hashes must be recorded SHA-256 strings")
            try:
                db.execute("INSERT INTO sec VALUES (?,?,?,?,?,?,?)", (record, year, row["cik"], key,
                           row["accessionNumber"], day, row["acceptance_timestamp"]))
            except sqlite3.IntegrityError as exc:
                raise ValueError("SEC manifest repeats an accession; original filing identity is ambiguous") from exc
            rows += 1
    db.execute("CREATE INDEX sec_cik_year ON sec(cik_key,year)")
    db.commit()
    return {"provided": True, "sha256": digest, "rows": rows,
            "snapshot": {"file": "input_receipts/sec_manifest.csv", "sha256": digest, "bytes": size},
            "original_sec_bytes_reread": False, "recorded_source_hashes_verified_against_original_bytes": False}, (source, identity, digest)


def _guard_sec(guard):
    if guard is not None:
        source, identity, digest = guard
        if _identity(source) != identity or _hash(source) != digest or _identity(source) != identity:
            raise ValueError("SEC manifest changed during identity-evidence construction")


def _provenance(ccm, names):
    source = names.receipt["source"]
    return {"ccm_source_sha256": ccm["sha256"], "ccm_inventory_sha256": ccm["receipt_sha256"],
            "names_source_sha256": source["source_sha256"], "names_inventory_sha256": source["inventory_receipt_sha256"]}


def _write_ccm(db, out, source):
    writer = _Writer(out, "ccm_records", CCM_SCHEMA)
    for row in db.execute("SELECT * FROM ccm ORDER BY record"):
        writer.append({"ccm_source_sha256": source["sha256"], "ccm_inventory_sha256": source["receipt_sha256"],
                       "ccm_source_csv_record": row["record"], **{target: row[field] for field, target in _RAW.items()},
                       "full_delivered_row_sha256": row["row_sha256"], "permno_comparison_key": row["permno_key"],
                       "permco_comparison_key": row["permco_key"], "header_cik_comparison_key": row["cik_key"],
                       "permno_grammar": row["permno_kind"], "permco_grammar": row["permco_kind"],
                       "header_cik_grammar": row["cik_kind"], "link_start_kind": row["start_kind"],
                       "link_end_kind": row["end_kind"], "inventory_requested_interval_kind": row["interval_kind"],
                       **_unknown()})
    return writer.finish()


def _write_pairs(db, out, ccm, names, windows):
    writer = _Writer(out, "relationships", PAIR_SCHEMA)
    db.execute("CREATE TABLE pairs(year INTEGER,nrecord INTEGER,crecord INTEGER,relation TEXT,candidate INTEGER,"
               "permco_comparison TEXT,PRIMARY KEY(year,nrecord,crecord)) WITHOUT ROWID")
    binding = _provenance(ccm, names)
    query = ("SELECT n.year,n.record nrecord,n.permno npermno,n.permco npermco,n.permno_key nkey,"
             "n.permco_key npco,n.status,n.ambiguous,n.ordinary,c.* FROM names n JOIN ccm c "
             "ON n.permno_key=c.permno_key WHERE n.year=? ORDER BY n.record,c.record")
    counts = Counter()
    for year, window in windows.items():
        for row in db.execute(query, (year,)):
            relation, candidate = _relation(row["linkdt"], row["linkenddt"], window["selection_asof"])
            company = _id_comparison(row["npermco"], row["lpermco"], row["npco"], row["permco_key"])
            db.execute("INSERT INTO pairs VALUES (?,?,?,?,?,?)", (year, row["nrecord"], row["record"],
                       relation, int(candidate), company))
            writer.append({"candidate_year": year, "selection_asof": window["selection_asof"],
                           "information_cutoff": window["information_cutoff"], **binding,
                           "names_source_csv_record": row["nrecord"], "ccm_source_csv_record": row["record"],
                           "names_permno_raw": row["npermno"], "names_permco_raw": row["npermco"],
                           **{f"ccm_{field}_raw": row[field] for field in (
                               "lpermno", "lpermco", "gvkey", "liid", "linkprim", "linktype", "linkdt", "linkenddt")},
                           "ccm_header_cik_raw": row["cik"], "header_cik_comparison_key": row["cik_key"],
                           "header_cik_grammar": row["cik_kind"], "date_relation": relation, "candidate_search": candidate,
                           "id_comparison": _id_comparison(row["npermno"], row["lpermno"], row["nkey"], row["permno_key"]),
                           "permco_comparison": company, "names_candidate_status": row["status"],
                           "names_ambiguous": bool(row["ambiguous"]), "ordinary_listing_candidate": bool(row["ordinary"]),
                           **_unknown()})
            counts[relation] += 1
        db.commit()
    return writer.finish(), dict(counts)


def _write_sec_matches(db, out, ccm, names, sec):
    writer = _Writer(out, "sec_discovery", SEC_MATCH_SCHEMA)
    db.execute("CREATE TABLE discoveries(year INTEGER,nrecord INTEGER,crecord INTEGER,srecord INTEGER,"
               "PRIMARY KEY(year,nrecord,crecord,srecord)) WITHOUT ROWID")
    binding = _provenance(ccm, names)
    query = ("SELECT p.year,p.nrecord,p.crecord,c.cik,c.cik_key,c.linkdt,c.linkenddt,n.info_start,n.info_end,"
             "s.record srecord,s.cik_raw,s.cik_key skey,s.accession,s.day,s.stamp FROM pairs p JOIN ccm c "
             "ON c.record=p.crecord JOIN names n ON n.year=p.year AND n.record=p.nrecord JOIN sec s "
             "ON s.year=p.year AND s.cik_key=c.cik_key WHERE p.candidate=1 ORDER BY p.year,p.nrecord,p.crecord,s.record")
    for row in db.execute(query):
        relation, compatible = _relation(row["linkdt"], row["linkenddt"], row["day"])
        db.execute("INSERT INTO discoveries VALUES (?,?,?,?)", (row["year"], row["nrecord"], row["crecord"], row["srecord"]))
        writer.append({"candidate_year": row["year"], **binding, "names_source_csv_record": row["nrecord"],
                       "ccm_source_csv_record": row["crecord"], "sec_manifest_sha256": sec["sha256"],
                       "sec_manifest_csv_record": row["srecord"], "accession": row["accession"],
                       "sec_filer_cik_raw": row["cik_raw"], "sec_filer_cik_comparison_key": row["skey"],
                       "ccm_header_cik_raw": row["cik"],
                       "cik_comparison": _id_comparison(row["cik"], row["cik_raw"], row["cik_key"], row["skey"]),
                       "recorded_acceptance_date": row["day"], "recorded_acceptance_timestamp": row["stamp"],
                       "ccm_relation_at_acceptance": relation, "ccm_date_compatible_at_acceptance": compatible,
                       "names_secinfo_covers_acceptance": row["info_start"] <= row["day"] <= row["info_end"],
                       "original_sec_bytes_reread": False, **_unknown()})
    db.execute("CREATE INDEX discoveries_manifest ON discoveries(srecord)")
    db.commit()
    coverage = _Writer(out, "sec_manifest_coverage", SEC_COVERAGE_SCHEMA)
    statuses = Counter()
    query = ("SELECT s.*,COUNT(d.nrecord) matches,COUNT(DISTINCT n.permno) securities,"
             "COUNT(DISTINCT d.crecord) ccm_records FROM sec s LEFT JOIN discoveries d ON d.srecord=s.record "
             "LEFT JOIN names n ON n.year=d.year AND n.record=d.nrecord GROUP BY s.record ORDER BY s.record")
    for row in db.execute(query):
        status = "HEADER_CIK_DISCOVERY_ONLY" if row["matches"] else "NO_SAME_YEAR_HEADER_CIK_CANDIDATE_DISCOVERY"
        statuses[status] += 1
        coverage.append({"sec_manifest_sha256": sec["sha256"], "sec_manifest_csv_record": row["record"],
                         "acceptance_year": row["year"], "accession": row["accession"], "sec_filer_cik_raw": row["cik_raw"],
                         "sec_filer_cik_comparison_key": row["cik_key"], "recorded_acceptance_date": row["day"],
                         "discovery_pair_rows": row["matches"], "distinct_raw_names_ids": row["securities"],
                         "distinct_ccm_records": row["ccm_records"], "coverage_status": status,
                         "original_sec_bytes_reread": False, **_unknown()})
    return writer.finish(), coverage.finish(), dict(statuses)


def _write_annual(db, out, ccm, names, windows):
    writer = _Writer(out, "annual_evidence", ANNUAL_SCHEMA)
    summaries = {year: {"year": year, "security_year_rows": 0, "names_record_count": 0,
                        "related_pair_rows": 0, "candidate_pair_rows": 0, "names_ambiguous_rows": 0,
                        "ordinary_listing_candidate_rows": 0, "evidence_status_counts": Counter()}
                 for year in YEARS}
    conditions = {
        "candidate_ccm_records": "p.candidate=1",
        "finite_candidate_ccm_records": "p.relation='FINITE_INCLUSIVE_CANDIDATE'",
        "open_marker_candidate_ccm_records": "p.relation='OPEN_MARKER_BOUNDS_UNRESOLVED_CANDIDATE'",
        "other_unresolved_candidate_ccm_records": "p.relation='OTHER_BOUNDS_UNRESOLVED_CANDIDATE'",
        "before_selection_context_ccm_records": "p.relation='BEFORE_SELECTION_CONTEXT'",
        "after_selection_context_ccm_records": "p.relation='AFTER_SELECTION_CONTEXT'",
        "reversed_context_ccm_records": "p.relation='REVERSED_FINITE_CONTEXT'",
        "candidate_blank_header_cik_records": "p.candidate=1 AND c.cik_kind='blank'",
        "candidate_unsupported_header_cik_records": "p.candidate=1 AND c.cik_kind NOT IN ('blank','positive_ascii_integer')",
    }
    expressions = ",".join(f"COUNT(DISTINCT CASE WHEN {condition} THEN c.record END) {field}"
                           for field, condition in conditions.items())
    query = (
        "SELECT n.year,n.permno,n.permno_key,n.permno_kind,COUNT(DISTINCT n.record) names_record_count,"
        "COUNT(DISTINCT n.projection) names_distinct_projection_count,"
        "COUNT(DISTINCT n.record)-COUNT(DISTINCT n.projection) names_exact_duplicate_record_excess,"
        "COALESCE(a.n,0) raw_names_ids_sharing_comparison_key,MAX(n.ambiguous) ambiguous,MAX(n.ordinary) ordinary,"
        "COUNT(p.crecord) related_pair_rows,COUNT(DISTINCT p.crecord) related_ccm_records,"
        "COALESCE(SUM(p.candidate),0) candidate_pair_rows," + expressions + ","
        "COUNT(DISTINCT CASE WHEN p.candidate=1 AND c.gvkey_kind<>'blank' THEN c.gvkey END) candidate_nonblank_raw_gvkeys,"
        "COUNT(DISTINCT CASE WHEN p.candidate=1 THEN c.cik_key END) candidate_header_cik_keys,"
        "SUM(CASE WHEN p.candidate=1 AND p.permco_comparison='DIFFERENT_VALID_COMPARISON_KEYS' THEN 1 ELSE 0 END) candidate_permco_disagreement_pairs,"
        "SUM(CASE WHEN p.candidate=1 AND p.permco_comparison='UNRESOLVED_IDENTIFIER' THEN 1 ELSE 0 END) candidate_permco_unresolved_pairs "
        "FROM names n LEFT JOIN pairs p ON p.year=n.year AND p.nrecord=n.record LEFT JOIN ccm c ON c.record=p.crecord "
        "LEFT JOIN aliases a ON a.year=n.year AND a.permno_key=n.permno_key GROUP BY n.year,n.permno ORDER BY n.year,n.permno"
    )
    for row in db.execute(query):
        candidates = row["candidate_ccm_records"]
        if row["permno_key"] is None:
            status = "UNRESOLVED_NAMES_IDENTIFIER"
        elif not row["related_ccm_records"]:
            status = "NO_RELATED_CCM_RECORD"
        elif not candidates:
            status = "DATED_CONTEXT_ONLY_NO_JANUARY1_CANDIDATE"
        elif row["ambiguous"] or row["raw_names_ids_sharing_comparison_key"] > 1 or candidates > 1:
            status = "MULTIPLE_OR_AMBIGUOUS_CANDIDATE_EVIDENCE"
        elif not row["candidate_header_cik_keys"]:
            status = "SINGLE_CANDIDATE_HEADER_CIK_MISSING_OR_UNSUPPORTED"
        else:
            status = "SINGLE_CANDIDATE_REQUIRES_HISTORICAL_IDENTITY_EVIDENCE"
        matches = db.execute(
            "SELECT COUNT(*),COUNT(DISTINCT d.srecord) FROM discoveries d JOIN names n "
            "ON n.year=d.year AND n.record=d.nrecord WHERE n.year=? AND n.permno=?", (row["year"], row["permno"])
        ).fetchone()
        window = windows[row["year"]]
        result = {"candidate_year": row["year"], "selection_asof": window["selection_asof"],
                  "information_cutoff": window["information_cutoff"], "names_permno_raw": row["permno"],
                  "permno_comparison_key": row["permno_key"], "permno_grammar": row["permno_kind"],
                  **{field: row[field] for field in _ANNUAL_COUNTS if not field.startswith("sec_manifest_")},
                  "sec_manifest_discovery_pairs": matches[0], "sec_manifest_discovery_filings": matches[1],
                  "names_ambiguous": bool(row["ambiguous"]), "ordinary_listing_candidate": bool(row["ordinary"]),
                  "evidence_status": status, "listing_candidate_receipt_sha256": names.sha256,
                  "ccm_inventory_sha256": ccm["receipt_sha256"], **_unknown()}
        writer.append(result)
        summary = summaries[row["year"]]
        summary["security_year_rows"] += 1
        for field in ("names_record_count", "related_pair_rows", "candidate_pair_rows"):
            summary[field] += row[field]
        summary["names_ambiguous_rows"] += bool(row["ambiguous"])
        summary["ordinary_listing_candidate_rows"] += bool(row["ordinary"])
        summary["evidence_status_counts"][status] += 1
    return writer.finish(), list(summaries.values())


def build_identity_candidates(ccm_inventory, listing_candidates, *, output, config, repo_root=".", sec_manifest=None):
    """Preserve all dated candidate evidence without creating accepted identity links."""
    repo = Path(repo_root).resolve()
    verify_lock(config, repo / "configs/protocol.lock.json")
    if (config["initial_train_start"], config["development_end"], config["holdout_start"]) != (2010, 2021, 2022):
        raise ValueError("Identity evidence requires frozen 2010–2021 selection years")
    out = _private_directory(output, repo)
    out.parent.mkdir(parents=True, exist_ok=True)
    windows = {year: year_start_window(year, config) for year in YEARS}
    with tempfile.TemporaryDirectory(prefix=".wrds-identity-", dir=out.parent) as temporary:
        work, bundle = Path(temporary), Path(temporary) / "bundle"
        bundle.mkdir(mode=0o700)
        (bundle / "input_receipts").mkdir(mode=0o700)
        (bundle / "names_evidence").mkdir(mode=0o700)
        with closing(sqlite3.connect(str(work / "evidence.sqlite3"))) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA cache_size=-16384")
            db.execute("PRAGMA temp_store=FILE")
            # An optional final-period filing is refused before vendor inputs are opened.
            sec, sec_guard = _sec_manifest(sec_manifest, bundle, db, config)
            names = liquidity._load(listing_candidates, "listing", config)
            ccm = _load_ccm(ccm_inventory, config)
            if any(out.is_relative_to(directory) for directory in (names.directory, ccm["directory"])):
                raise ValueError("Identity output must remain separate from its preserved input bundles")
            snapshots = [
                liquidity._save_bytes(bundle, "input_receipts/ccm_inventory.json", ccm["raw"]),
                liquidity._save_bytes(bundle, "input_receipts/listing_candidates.json", names.raw),
                liquidity._save_bytes(bundle, "input_receipts/names_inventory.json", names.chain_raw),
            ]
            ccm_counts = _index_ccm(db, ccm)
            name_counts = liquidity._listing_preflight(names, windows)
            _guard_ccm(ccm)
            liquidity._guard([names])
            liquidity._validate_listing_values(names)
            _index_names(db, names)
            detail_parts = []
            for index, (path, specification) in enumerate(names.parts, 1):
                name = f"names_evidence/part-{index:06d}.parquet"
                digest, size = _copy_source(path, bundle / name)
                if digest != specification["sha256"] or size != specification["bytes"]:
                    raise ValueError("Names detail copy differs from its bound source part")
                detail_parts.append({"file": name, "sha256": digest, "bytes": size, "rows": specification["rows"],
                                     "upstream_part": specification["file"]})
            ccm_table = _write_ccm(db, bundle, ccm)
            relationships, relation_counts = _write_pairs(db, bundle, ccm, names, windows)
            discoveries, manifest_coverage, manifest_counts = _write_sec_matches(db, bundle, ccm, names, sec)
            annual, summaries = _write_annual(db, bundle, ccm, names, windows)
            related_ccm = db.execute("SELECT COUNT(DISTINCT crecord) FROM pairs").fetchone()[0]
            candidate_ccm = db.execute("SELECT COUNT(DISTINCT crecord) FROM pairs WHERE candidate=1").fetchone()[0]
        _guard_ccm(ccm, rehash=True)
        liquidity._guard([names], rehash=True)
        _guard_sec(sec_guard)
        tables = {"ccm_records": ccm_table, "relationships": relationships,
                  "annual_evidence": annual, "sec_discovery": discoveries, "sec_manifest_coverage": manifest_coverage,
                  "names_evidence": {"parts": detail_parts, "rows": sum(name_counts.values()),
                                     "upstream_parquet_bytes_preserved": True}}
        checks = [*snapshots, *[part for table in tables.values() for part in table["parts"]]]
        if sec["snapshot"]:
            checks.append(sec["snapshot"])
        for specification in checks:
            path = bundle / specification["file"]
            if path.stat().st_size != specification["bytes"] or _hash(path) != specification["sha256"]:
                raise ValueError("Private identity evidence or its receipt snapshot changed")
        if (ccm_table["rows"] != ccm_counts["source_rows"] or manifest_coverage["rows"] != sec["rows"]
                or sum(row["names_record_count"] for row in summaries) != sum(name_counts.values())):
            raise ValueError("Identity evidence does not account for every source or manifest record")
        receipt = {
            "schema_version": 1, "status": STATUS, "created_at": datetime.now(timezone.utc).isoformat(),
            "protocol_sha256": canonical_hash(config), "years": list(YEARS),
            "inputs": {"ccm_inventory_directory": str(ccm["directory"]), "ccm_inventory_sha256": ccm["receipt_sha256"],
                       "ccm_source_sha256": ccm["sha256"], "ccm_source_bytes": ccm["identity"][2],
                       "ccm_source_preserved_file": ccm["receipt"]["source"]["preserved_file"],
                       "ccm_observed_header": ccm["receipt"]["source"]["observed_header"],
                       "listing_candidates_directory": str(names.directory), "listing_candidates_sha256": names.sha256},
            "input_receipts": snapshots, "sec_manifest": sec, "tables": tables,
            "source_inventory": {**ccm_counts, "ccm_records_with_any_related_names_snapshot": related_ccm,
                                 "ccm_records_with_no_related_names_snapshot": ccm_table["rows"] - related_ccm,
                                 "ccm_records_in_any_date_compatible_candidate_search": candidate_ccm,
                                 "all_original_ccm_records_retained": True,
                                 "full_delivered_source_retained_unchanged_in_inventory": True},
            "year_summaries": summaries, "date_relation_counts": relation_counts,
            "sec_manifest_coverage_counts": manifest_counts,
            "policies": {
                "identifiers": "comparison keys only: nonzero ASCII digits, 1–20 characters for PERMNO/PERMCO; 1–10 for CIK; leading zeros removed for security keys and ten-digit padding for CIK; raw strings unchanged",
                "unsupported_identifiers": "blank, zero, whitespace-padded, negative, decimal and scientific strings retained but never joined",
                "bounds": "inclusive finite comparisons; B/E/blank/other bounds retained literally; no finite dates or infinities assigned",
                "candidate_search": "all identifier-related records retained; known finite before/after or reversed intervals are context only; unresolved bounds are search possibilities when no finite bound contradicts the selection date",
                "context_is_historical_knowledge": False,
                "link_type_primary_or_share_class_filters": False,
                "duplicates": "all source record occurrences and Names overlaps retained; related and candidate source-record counts are separate from pair multiplicities",
                "full_delivered_row_fingerprint": "SHA-256 of the complete parsed CCM row as compact ensure_ascii JSON in original delivered column order; this does not deduplicate any record",
                "header_cik": "current company-header observation only, never an established historical CIK",
                "sec_discovery": "same acceptance year and comparison-key agreement with a CCM header CIK among January 1 search candidates; acceptance-date interval checks are diagnostics only",
                "sec_evidence": "recorded manifest metadata and source-hash declarations only; original filing/header bytes not reread or independently verified",
                "availability": "known_at and available_at remain NULL; neither SEC acceptance nor retrieval time supplies link availability",
                "ordinary_listing_status": "retained as a diagnostic; does not filter CCM relationships or choose a security class",
            },
            "processing": {"sqlite_cache_kib": 16384, "sqlite_temp_store": "FILE",
                           "batch_rows": _BATCH, "batch_byte_target": _BYTES,
                           "source_bounds_complete_before_matching": True,
                           "source_and_output_hashes_verified_before_completion": True},
            "original_sec_bytes_reread": False, "approved_security_links_created": 0,
            "historical_cik_supplied": False, "historical_availability_supplied": False,
            "source_population_completeness_verified": False, "universe_membership_created": False,
            "returns_read": False, "market_outcomes_read": False, "model_ready": False, "source_approvals": 0,
            "prior_arithmetic_review_modified": False, "final_period_opened": False,
        }
        liquidity._save_bytes(bundle, "receipt.json", (json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
        if out.exists():
            raise ValueError("Identity output appeared during construction; it must not be overwritten")
        bundle.rename(out)
    return receipt


def aggregate_summary(receipt):
    """Counts, hashes, headers and fixed statuses only; no source identifiers."""
    return {"status": receipt["status"], "protocol_sha256": receipt["protocol_sha256"], "years": receipt["years"],
            "ccm_source_sha256": receipt["inputs"]["ccm_source_sha256"],
            "ccm_observed_header": receipt["inputs"]["ccm_observed_header"],
            "table_rows": {name: table["rows"] for name, table in receipt["tables"].items()},
            "source_inventory": receipt["source_inventory"], "year_summaries": receipt["year_summaries"],
            "date_relation_counts": receipt["date_relation_counts"],
            "sec_manifest_coverage_counts": receipt["sec_manifest_coverage_counts"],
            "original_sec_bytes_reread": False, "historical_cik_supplied": False,
            "approved_security_links_created": 0, "model_ready": False, "source_approvals": 0,
            "prior_arithmetic_review_modified": False, "final_period_opened": False}
