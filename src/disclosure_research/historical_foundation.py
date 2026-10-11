"""Reconcile saved annual evidence without approving historical identities.

Only completed metadata bundles and an already source-verified SEC report are
read. Daily values, provisional means/ranks, and original SEC bodies are not.
"""

import gzip
import hashlib
import io
import json
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from . import manual_wrds_identity_candidates as identity
from . import manual_wrds_liquidity_candidates as liquidity
from . import manual_wrds_listing_candidates as listing
from . import sec_identity_evidence as sec
from .manual_wrds_candidates import _inside
from .manual_wrds_intake import _hash, _identity, _private_directory
from .manual_wrds_metadata import CCM_FIELDS, NAMES_FIELDS, _bound_kind, _interval_kind
from .protocol import canonical_hash, verify_lock
from .universe import aware_timestamp, year_start_window

STATUS = "HISTORICAL_FOUNDATION_EVIDENCE_NOT_SOURCE_APPROVED"
_MAX_REPORT = 64 * 1024 * 1024
_MAX_ROWS = 5_000_000
LIQUIDITY_COLUMNS = [
    "candidate_year", "security_id", "selection_asof", "selection_session", "information_cutoff",
    "liquidity_start", "liquidity_end", "expected_sessions", "observed_sessions",
    "unambiguous_sessions", "conflicting_sessions", "numerically_valid_sessions", "withheld_sessions",
    "missing_sessions", "meets_numeric_minimum_40", "coverage_status", "listing_record_count",
    "listing_distinct_projection_count", "listing_candidate_status", "ambiguous_listing",
    "ordinary_listing_candidate", "rank_eligible_by_candidate_policy", "known_at", "available_at", "numerical_candidate_receipt_sha256",
    "listing_candidate_receipt_sha256", "liquidity_projection_evidence_sha256",
]


def _f(name, kind=pa.string(), nullable=False):
    return pa.field(name, kind, nullable=nullable)


ANNUAL_SCHEMA = pa.schema([
    _f("candidate_year", pa.int16()), _f("security_id"), _f("selection_asof"), _f("information_cutoff"),
    _f("identity_present", pa.bool_()), _f("liquidity_present", pa.bool_()),
    _f("identity_evidence_status"), _f("ordinary_numeric_candidate", pa.bool_()),
    _f("rank_eligible_by_candidate_policy", pa.bool_()),
    _f("meets_numeric_minimum_40", pa.bool_()), _f("source_bound_discoveries", pa.int64()),
    _f("source_bound_filings", pa.int64()), _f("class_observation_counts_json"), _f("evidence_gaps_json"),
    _f("identity_evidence_json", nullable=True), _f("liquidity_metadata_json", nullable=True),
    _f("identity_receipt_sha256"), _f("liquidity_receipt_sha256"), _f("sec_evidence_sha256"),
    _f("known_at", nullable=True), _f("available_at", nullable=True), _f("identity_approved", pa.bool_()),
])
DISCOVERY_SCHEMA = pa.schema([
    *identity.SEC_MATCH_SCHEMA,
    _f("status"), _f("names_permno_raw"), _f("names_issuernm_raw"), _f("names_ticker_raw"),
    _f("names_shareclass_raw"), _f("ccm_gvkey_raw"), _f("ccm_linkdt_raw"), _f("ccm_linkenddt_raw"),
    _f("original_filer_name"), _f("original_filer_ordinal", pa.int64()),
    _f("primary_source_sha256"), _f("header_source_sha256"), _f("sec_evidence_sha256"),
    _f("class_observations_json"), _f("evidence_id"),
])
COVERAGE_SCHEMA = pa.schema([
    *identity.SEC_COVERAGE_SCHEMA, _f("primary_source_sha256"), _f("header_source_sha256"),
    _f("sec_evidence_sha256"), _f("source_report_bound", pa.bool_()),
])


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


@dataclass
class _Bundle:
    directory: Path
    receipt: dict
    raw: bytes
    sha256: str
    guards: dict = field(default_factory=dict)
    parts: list = field(default_factory=list)


def _bundle(directory, digest, status, config):
    path = Path(directory)
    _require(not path.is_symlink(), "A completed bundle cannot be a symbolic link")
    path = path.resolve(strict=True)
    guards = {}
    receipt, raw = liquidity._read_bound(path, "receipt.json", guards)
    _require(hashlib.sha256(raw).hexdigest() == liquidity._sha(digest), "Completed receipt pin differs")
    liquidity._contract(receipt, status, config)
    _require(receipt.get("years") == list(identity.YEARS)
             and receipt.get("prior_arithmetic_review_modified") is False,
             "Completed evidence must preserve the development years and previous review")
    return _Bundle(path, receipt, raw, digest, guards)


def _parts(bundle, table, schema):
    """The identity contract permits schema-bearing zero-row parts."""
    total = liquidity._integer(table["rows"], "Table rows")
    specs = table["parts"]
    _require(total <= _MAX_ROWS and isinstance(specs, list) and len(specs) <= 100_000,
             "Completed table exceeds bounded metadata limits")
    result, seen, count = [], set(), 0
    for spec in specs:
        name = spec["file"]
        _require(name not in seen, "Completed part path is repeated")
        seen.add(name)
        path = _inside(bundle.directory, name)
        before = _identity(path)
        rows = liquidity._integer(spec["rows"], "Part rows")
        digest = liquidity._sha(spec["sha256"])
        _require(before[2] == liquidity._integer(spec["bytes"], "Part bytes")
                 and _hash(path) == digest and _identity(path) == before,
                 "Completed part differs from its byte binding")
        parquet = pq.ParquetFile(path)
        _require(parquet.schema_arrow.equals(schema, check_metadata=False)
                 and parquet.metadata.num_rows == rows, "Completed part schema or row count differs")
        bundle.guards[path] = before, digest
        result.append((path, spec))
        count += rows
    _require(count == total, "Completed parts do not account for every declared row")
    return result


def _rows(bundle, parts, columns):
    reader = _Bundle(bundle.directory, bundle.receipt, bundle.raw, bundle.sha256, bundle.guards, parts)
    for batch in liquidity._batches(reader, columns):
        for index, column in enumerate(batch.schema):
            _require(column.nullable or batch.column(index).null_count == 0,
                     "A required evidence value is null")
        for row in batch.to_pylist():
            for name in ("known_at", "available_at"):
                _require(name not in row or row[name] is None, "Historical availability must remain unknown")
            _require("identity_approved" not in row or row["identity_approved"] is False,
                     "Candidate evidence cannot contain approved identities")
            yield row


def _snapshot(bundle, specification):
    value, raw = liquidity._read_bound(bundle.directory, specification["file"], bundle.guards)
    _require(hashlib.sha256(raw).hexdigest() == specification["sha256"]
             and len(raw) == specification["bytes"], "Receipt snapshot differs from its binding")
    return value, raw


def _sec_input(report_path, report_sha256, manifest_path, manifest_sha256, config):
    """Complete public date/source preflight before a vendor bundle is opened."""
    manifest, manifest_guard = sec._manifest(manifest_path, manifest_sha256, config)
    path = Path(report_path).absolute()
    before = sec._regular(path, _MAX_REPORT)
    compressed = sec._BoundedFile(path, before, _MAX_REPORT).read_bytes()
    _require(hashlib.sha256(compressed).hexdigest() == liquidity._sha(report_sha256),
             "SEC report input hash differs")
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        raw = stream.read(_MAX_REPORT + 1)
    _require(len(raw) <= _MAX_REPORT, "Decompressed SEC evidence exceeds its size bound")
    report = json.loads(raw)
    liquidity._contract(report, sec.STATUS, config)
    _require(report.get("manifest_sha256") == manifest_sha256
             and report.get("original_sec_bytes_reread") is True
             and report.get("historical_security_links_created") == 0
             and report.get("human_reviews_created") == 0
             and report.get("prior_arithmetic_review_modified") is False,
             "SEC evidence must be the unapproved original-source report")
    records = report["records"]
    _require(isinstance(records, list) and len(records) == len(manifest), "SEC report coverage differs")
    by_record, filers = {}, {}
    for source, record in zip(manifest, records, strict=True):
        ordinal = source["manifest_csv_record"]
        _require(record["manifest_csv_record"] == ordinal
                 and record["accession"] == source["accessionNumber"]
                 and record["manifest_cik_raw"] == source["cik"]
                 and record["acceptance_date"] == source["acceptance_date"]
                 and record["recorded_acceptance_timestamp"] == source["acceptance_timestamp"]
                 and record["known_at"] is None and record["available_at"] is None
                 and record["security_link_created"] is False, "SEC report record differs from original manifest")
        for field_name, url_name, sha_name in (("primary_source", "source_url", "download_sha256"),
                                               ("header_source", "header_url", "header_sha256")):
            bound = record[field_name]
            _require(bound["url"] == source[url_name] and bound["sha256"] == source[sha_name]
                     and bound["original_bytes_reverified"] is True, "SEC source declarations differ")
        head = record["header_identity"]
        matching = [filer for filer in head["filers"] if filer["matches_manifest_cik"]]
        key = identity._integer_key(source["cik"], cik=True)[0]
        _require(head["header_identity_consistent"] is True and head["matching_filer_count"] == 1
                 and len(matching) == 1 and matching[0]["filer_fields_unambiguous"] is True
                 and matching[0]["cik_comparison_key"] == key,
                 "SEC report lacks one consistent original legal filer")
        clock = record["acceptance_clock"]
        _require(clock["matches_manifest"] is True
                 and aware_timestamp(clock["interpreted_acceptance_timestamp"], "SEC clock")
                 == aware_timestamp(source["acceptance_timestamp"], "Manifest clock"),
                 "SEC report acceptance clock differs")
        _require(isinstance(record["cover_evidence"].get("facts"), list)
                 and isinstance(record["cover_evidence"].get("contexts"), list), "SEC cover evidence is malformed")
        by_record[ordinal], filers[ordinal] = record, matching[0]
    _require(report["summary"]["filings"] == len(records), "SEC summary count differs")
    return {"records": by_record, "filers": filers, "manifest": manifest, "manifest_sha256": manifest_sha256, "raw": compressed,
            "sha256": report_sha256, "json_sha256": hashlib.sha256(raw).hexdigest(),
            "guards": {manifest_guard[0]: (manifest_guard[1], manifest_guard[2]), path: (before, report_sha256)}}


def _load_inputs(identity_directory, identity_digest, liquidity_directory, liquidity_digest, sec_input, config):
    ident = _bundle(identity_directory, identity_digest, identity.STATUS, config)
    liq = _bundle(liquidity_directory, liquidity_digest, liquidity.STATUS, config)
    _require(ident.directory != liq.directory, "The two evidence bundles must be distinct")
    for name in ("approved_security_links_created", "source_approvals"):
        _require(type(ident.receipt.get(name)) is int and ident.receipt[name] == 0, "Identity source remains unapproved")
    _require(ident.receipt.get("historical_availability_supplied") is False
             and ident.receipt.get("original_sec_bytes_reread") is False
             and liq.receipt.get("historical_availability_verified") is False
             and liq.receipt.get("issuer_grouping_performed") is False
             and liq.receipt.get("issuer_limit_applied") is False, "Completed evidence scope changed")
    for item in (ident, liq):
        paths = [spec["file"] for spec in item.receipt["input_receipts"]]
        _require(len(paths) == len(set(paths)), "Receipt snapshot path is repeated")
    identity_snapshots = {item["file"]: _snapshot(ident, item) for item in ident.receipt["input_receipts"]}
    liquidity_snapshots = {item["file"]: _snapshot(liq, item) for item in liq.receipt["input_receipts"]}
    names_receipt, names_raw = identity_snapshots["input_receipts/listing_candidates.json"]
    ccm_receipt, ccm_raw = identity_snapshots["input_receipts/ccm_inventory.json"]
    names_inventory, names_inventory_raw = identity_snapshots["input_receipts/names_inventory.json"]
    names_digest = hashlib.sha256(names_raw).hexdigest()
    _require(names_raw == liquidity_snapshots["input_receipts/listing.json"][1]
             and names_inventory_raw == liquidity_snapshots["input_receipts/listing_source.json"][1]
             and names_digest == ident.receipt["inputs"]["listing_candidates_sha256"]
             and names_digest == liq.receipt["inputs"]["listing"]["receipt_sha256"],
             "Annual inputs must use the exact same Names source and candidate receipt")
    liquidity._contract(names_receipt, liquidity.LISTING_STATUS, config)
    _require(names_receipt["candidate_policy"] == listing.POLICY
             and names_receipt["candidate_policy_sha256"] == canonical_hash(listing.POLICY)
             and names_receipt["source"]["inventory_receipt_sha256"] == hashlib.sha256(names_inventory_raw).hexdigest()
             and names_receipt["source"]["source_sha256"] == names_inventory["source"]["sha256"]
             and hashlib.sha256(ccm_raw).hexdigest() == ident.receipt["inputs"]["ccm_inventory_sha256"]
             and ccm_receipt["source"]["sha256"] == ident.receipt["inputs"]["ccm_source_sha256"],
             "Preserved source receipt lineage differs")
    manifest = ident.receipt["sec_manifest"]
    _require(manifest["provided"] is True and manifest["sha256"] == sec_input["manifest_sha256"]
             and manifest["rows"] == len(sec_input["manifest"]), "SEC manifest binding differs between inputs")
    spec = manifest["snapshot"]
    manifest_path = _inside(ident.directory, spec["file"])
    before = _identity(manifest_path)
    _require(before[2] == spec["bytes"] and _hash(manifest_path) == manifest["sha256"]
             and spec["sha256"] == manifest["sha256"], "Private SEC manifest snapshot differs")
    ident.guards[manifest_path] = before, spec["sha256"]
    schemas = {"ccm_records": identity.CCM_SCHEMA, "relationships": identity.PAIR_SCHEMA,
               "annual_evidence": identity.ANNUAL_SCHEMA, "sec_discovery": identity.SEC_MATCH_SCHEMA,
               "sec_manifest_coverage": identity.SEC_COVERAGE_SCHEMA, "names_evidence": listing.CANDIDATE_SCHEMA}
    tables = {name: _parts(ident, ident.receipt["tables"][name], schema) for name, schema in schemas.items()}
    liq_parts = _parts(liq, liq.receipt["annual_liquidity"], liquidity.ANNUAL_SCHEMA)
    copied_names = _parts(liq, liq.receipt["listing_evidence"], listing.CANDIDATE_SCHEMA)
    def signature(parts):
        return [(p[1]["sha256"], p[1]["bytes"], p[1]["rows"]) for p in parts]
    original = names_receipt["projection"]["parts"]
    _require(signature(tables["names_evidence"]) == signature(copied_names)
             == [(p["sha256"], p["bytes"], p["rows"]) for p in original], "Copied Names parts differ")
    names = _Bundle(ident.directory, names_receipt, names_raw, names_digest, ident.guards, tables["names_evidence"])
    return ident, liq, tables, liq_parts, names, ccm_receipt


def _index_sources(db, ident, tables, names, ccm_receipt, windows):
    liquidity._listing_preflight(names, windows)
    liquidity._validate_listing_values(names)
    identity._index_names(db, names)
    db.execute("CREATE TABLE ccm(record INTEGER PRIMARY KEY," + ",".join(f'"{name}" TEXT' for name in CCM_FIELDS)
               + ",permno_key TEXT,permco_key TEXT,cik_key TEXT,gvkey_kind TEXT,cik_kind TEXT)")
    source, inventory = ident.receipt["inputs"]["ccm_source_sha256"], ident.receipt["inputs"]["ccm_inventory_sha256"]
    expected = 2
    for row in _rows(ident, tables["ccm_records"], identity.CCM_SCHEMA.names):
        _require(row["ccm_source_csv_record"] == expected and row["ccm_source_sha256"] == source
                 and row["ccm_inventory_sha256"] == inventory, "CCM occurrence lineage is incomplete")
        expected += 1
        raw = {name: row[identity._RAW[name]] for name in CCM_FIELDS}
        keys = {name: identity._integer_key(raw[name], cik=name == "cik") for name in ("lpermno", "lpermco", "cik", "gvkey")}
        for raw_name, prefix in (("lpermno", "permno"), ("lpermco", "permco"), ("cik", "header_cik")):
            _require(row[prefix + "_comparison_key"] == keys[raw_name][0]
                     and row[prefix + "_grammar"] == keys[raw_name][1], "CCM identifier declaration differs")
        _require(row["link_start_kind"] == _bound_kind(raw["linkdt"])
                 and row["link_end_kind"] == _bound_kind(raw["linkenddt"])
                 and row["inventory_requested_interval_kind"] == _interval_kind(
                     raw["linkdt"], raw["linkenddt"], ccm_receipt["request"]["start"], ccm_receipt["request"]["end"]),
                 "CCM date declaration differs")
        liquidity._sha(row["full_delivered_row_sha256"])
        values = [row["ccm_source_csv_record"], *[raw[name] for name in CCM_FIELDS],
                  keys["lpermno"][0], keys["lpermco"][0], keys["cik"][0], keys["gvkey"][1], keys["cik"][1]]
        db.execute("INSERT INTO ccm VALUES (" + ",".join("?" for _ in values) + ")", values)
    _require(expected - 2 == ccm_receipt["all_rows"]["rows"], "CCM inventory occurrence count differs")
    db.execute("CREATE INDEX ccm_security ON ccm(permno_key)")
    db.execute("CREATE TABLE pairs(year INTEGER,nrecord INTEGER,crecord INTEGER,relation TEXT,candidate INTEGER,"
               "permco_comparison TEXT,PRIMARY KEY(year,nrecord,crecord)) WITHOUT ROWID")
    relation_counts = Counter()
    for row in _rows(ident, tables["relationships"], identity.PAIR_SCHEMA.names):
        year, nr, cr = row["candidate_year"], row["names_source_csv_record"], row["ccm_source_csv_record"]
        _require(year in windows, "Relationship year is outside development")
        name = db.execute("SELECT * FROM names WHERE year=? AND record=?", (year, nr)).fetchone()
        ccm = db.execute("SELECT * FROM ccm WHERE record=?", (cr,)).fetchone()
        _require(name is not None and ccm is not None and name["permno_key"] is not None
                 and name["permno_key"] == ccm["permno_key"], "Relationship source occurrence is missing or unrelated")
        relation, candidate = identity._relation(ccm["linkdt"], ccm["linkenddt"], windows[year]["selection_asof"])
        pco = identity._id_comparison(name["permco"], ccm["lpermco"], name["permco_key"], ccm["permco_key"])
        expected_row = {"candidate_year": year, "selection_asof": windows[year]["selection_asof"],
                        "information_cutoff": windows[year]["information_cutoff"],
                        "names_source_sha256": names.receipt["source"]["source_sha256"],
                        "names_inventory_sha256": names.receipt["source"]["inventory_receipt_sha256"],
                        "names_source_csv_record": nr, "ccm_source_sha256": source, "ccm_inventory_sha256": inventory,
                        "ccm_source_csv_record": cr, "names_permno_raw": name["permno"], "names_permco_raw": name["permco"],
                        **{f"ccm_{key}_raw": ccm[key] for key in ("lpermno", "lpermco", "gvkey", "liid", "linkprim", "linktype", "linkdt", "linkenddt")},
                        "ccm_header_cik_raw": ccm["cik"], "header_cik_comparison_key": ccm["cik_key"],
                        "header_cik_grammar": ccm["cik_kind"], "date_relation": relation, "candidate_search": candidate,
                        "id_comparison": identity._id_comparison(name["permno"], ccm["lpermno"], name["permno_key"], ccm["permno_key"]),
                        "permco_comparison": pco, "names_candidate_status": name["status"],
                        "names_ambiguous": bool(name["ambiguous"]), "ordinary_listing_candidate": bool(name["ordinary"]),
                        **identity._unknown()}
        _require(row == expected_row, "Relationship values differ from their exact source occurrences")
        db.execute("INSERT INTO pairs VALUES (?,?,?,?,?,?)", (year, nr, cr, relation, int(candidate), pco))
        relation_counts[relation] += 1
    expected_count = db.execute("SELECT COUNT(*) FROM names n JOIN ccm c ON n.permno_key=c.permno_key").fetchone()[0]
    _require(expected_count == sum(relation_counts.values())
             and dict(relation_counts) == ident.receipt["date_relation_counts"], "Relationship coverage is incomplete")
    db.commit()


def _discoveries(db, bundle, ident, tables, names, sec_input):
    from .sec_class_observations import observe_security_classes

    db.execute("CREATE TABLE discoveries(year INTEGER,nrecord INTEGER,crecord INTEGER,srecord INTEGER,"
               "PRIMARY KEY(year,nrecord,crecord,srecord)) WITHOUT ROWID")
    db.execute("CREATE TABLE discovery_stats(year INTEGER,security TEXT,srecord INTEGER,statuses TEXT)")
    db.execute("CREATE TABLE sec(record INTEGER PRIMARY KEY,year INTEGER,cik TEXT)")
    for source in sec_input["manifest"]:
        db.execute("INSERT INTO sec VALUES (?,?,?)", (source["manifest_csv_record"], int(source["acceptance_date"][:4]),
                                                     identity._integer_key(source["cik"], cik=True)[0]))
    writer = identity._Writer(bundle, "filing_candidate_corroboration", DISCOVERY_SCHEMA)
    cover_counts, coverage_details = Counter(), {}
    for row in _rows(ident, tables["sec_discovery"], identity.SEC_MATCH_SCHEMA.names):
        year, nr, cr, sr = (row[k] for k in ("candidate_year", "names_source_csv_record", "ccm_source_csv_record", "sec_manifest_csv_record"))
        pair = db.execute("SELECT * FROM pairs WHERE year=? AND nrecord=? AND crecord=?", (year, nr, cr)).fetchone()
        name = db.execute("SELECT * FROM names WHERE year=? AND record=?", (year, nr)).fetchone()
        ccm = db.execute("SELECT * FROM ccm WHERE record=?", (cr,)).fetchone()
        _require(pair is not None and pair["candidate"] == 1 and sr in sec_input["records"], "SEC discovery references no candidate")
        record, filer = sec_input["records"][sr], sec_input["filers"][sr]
        relation, compatible = identity._relation(ccm["linkdt"], ccm["linkenddt"], record["acceptance_date"])
        covers = name["info_start"] <= record["acceptance_date"] <= name["info_end"]
        _require(year == int(record["acceptance_date"][:4]) and ccm["cik_key"] == filer["cik_comparison_key"],
                 "SEC discovery is not the same-year original header-CIK observation")
        expected = {"candidate_year": year, "names_source_sha256": names.receipt["source"]["source_sha256"],
                    "names_inventory_sha256": names.receipt["source"]["inventory_receipt_sha256"], "names_source_csv_record": nr,
                    "ccm_source_sha256": ident.receipt["inputs"]["ccm_source_sha256"],
                    "ccm_inventory_sha256": ident.receipt["inputs"]["ccm_inventory_sha256"], "ccm_source_csv_record": cr,
                    "sec_manifest_sha256": ident.receipt["sec_manifest"]["sha256"], "sec_manifest_csv_record": sr,
                    "accession": record["accession"], "sec_filer_cik_raw": record["manifest_cik_raw"],
                    "sec_filer_cik_comparison_key": filer["cik_comparison_key"], "ccm_header_cik_raw": ccm["cik"],
                    "cik_comparison": identity._id_comparison(ccm["cik"], record["manifest_cik_raw"], ccm["cik_key"], filer["cik_comparison_key"]),
                    "recorded_acceptance_date": record["acceptance_date"],
                    "recorded_acceptance_timestamp": record["recorded_acceptance_timestamp"],
                    "ccm_relation_at_acceptance": relation, "ccm_date_compatible_at_acceptance": compatible,
                    "names_secinfo_covers_acceptance": covers, "original_sec_bytes_reread": False, **identity._unknown()}
        _require(row == expected, "SEC discovery source/date binding differs")
        names_row = dict(zip(NAMES_FIELDS, json.loads(name["projection"]), strict=True))
        names_row.update(source_sha256=expected["names_source_sha256"], source_inventory_sha256=expected["names_inventory_sha256"],
                         source_csv_record=nr, candidate_year=year)
        observations = observe_security_classes(record, names_row, filer)
        _require(isinstance(observations, list) and all(isinstance(o, dict) and isinstance(o.get("status"), str) for o in observations),
                 "Class observer must return explicit observation statuses")
        statuses = Counter(o["status"] for o in observations)
        cover_counts.update(statuses)
        result = {**row, "status": "ORIGINAL_FILER_CORROBORATED_HEADER_CIK_DISCOVERY_ONLY",
                  "names_permno_raw": name["permno"], "names_issuernm_raw": names_row["issuernm"],
                  "names_ticker_raw": names_row["ticker"], "names_shareclass_raw": names_row["shareclass"],
                  "ccm_gvkey_raw": ccm["gvkey"], "ccm_linkdt_raw": ccm["linkdt"], "ccm_linkenddt_raw": ccm["linkenddt"],
                  "original_filer_name": filer["conformed_name_raw_values"][0], "original_filer_ordinal": filer["filer_ordinal"],
                  "primary_source_sha256": record["primary_source"]["sha256"], "header_source_sha256": record["header_source"]["sha256"],
                  "sec_evidence_sha256": sec_input["sha256"], "class_observations_json": _json(observations)}
        result["evidence_id"] = canonical_hash(result)
        writer.append(result)
        db.execute("INSERT INTO discoveries VALUES (?,?,?,?)", (year, nr, cr, sr))
        db.execute("INSERT INTO discovery_stats VALUES (?,?,?,?)", (year, name["permno"], sr, _json(statuses)))
        info = coverage_details.setdefault(sr, {"pairs": 0, "names": set(), "ccm": set()})
        info["pairs"] += 1
        info["names"].add(name["permno"])
        info["ccm"].add(cr)
    expected_count = db.execute("SELECT COUNT(*) FROM pairs p JOIN ccm c ON c.record=p.crecord "
                                "JOIN sec s ON s.year=p.year AND s.cik=c.cik_key WHERE p.candidate=1").fetchone()[0]
    _require(expected_count == writer.rows + len(writer.buffer), "Existing SEC discovery coverage is incomplete")
    db.execute("CREATE INDEX discovery_security ON discovery_stats(year,security)")
    db.execute("CREATE INDEX discoveries_manifest ON discoveries(srecord)")
    output = writer.finish()
    coverage = identity._Writer(bundle, "filing_coverage", COVERAGE_SCHEMA)
    seen, coverage_counts = set(), Counter()
    for row in _rows(ident, tables["sec_manifest_coverage"], identity.SEC_COVERAGE_SCHEMA.names):
        sr = row["sec_manifest_csv_record"]
        _require(sr in sec_input["records"] and sr not in seen, "SEC coverage repeats or invents a filing")
        seen.add(sr)
        record = sec_input["records"][sr]
        info = coverage_details.get(sr, {"pairs": 0, "names": set(), "ccm": set()})
        status = "HEADER_CIK_DISCOVERY_ONLY" if info["pairs"] else "NO_SAME_YEAR_HEADER_CIK_CANDIDATE_DISCOVERY"
        expected = {"sec_manifest_sha256": ident.receipt["sec_manifest"]["sha256"], "sec_manifest_csv_record": sr,
                    "acceptance_year": int(record["acceptance_date"][:4]), "accession": record["accession"],
                    "sec_filer_cik_raw": record["manifest_cik_raw"],
                    "sec_filer_cik_comparison_key": sec_input["filers"][sr]["cik_comparison_key"],
                    "recorded_acceptance_date": record["acceptance_date"], "discovery_pair_rows": info["pairs"],
                    "distinct_raw_names_ids": len(info["names"]), "distinct_ccm_records": len(info["ccm"]),
                    "coverage_status": status, "original_sec_bytes_reread": False, **identity._unknown()}
        _require(row == expected, "SEC complete coverage accounting differs")
        coverage_counts[status] += 1
        coverage.append({**row, "primary_source_sha256": record["primary_source"]["sha256"],
                         "header_source_sha256": record["header_source"]["sha256"], "sec_evidence_sha256": sec_input["sha256"],
                         "source_report_bound": True})
    _require(seen == set(sec_input["records"]) and dict(coverage_counts) == ident.receipt["sec_manifest_coverage_counts"],
             "Every original SEC filing must remain in the coverage ledger")
    db.commit()
    return output, coverage.finish(), dict(cover_counts), dict(coverage_counts)


def _annual_inputs(db, ident, tables, liq, liq_parts, names, windows, work):
    db.execute("CREATE TABLE existing_annual(year INTEGER,security TEXT,payload TEXT,PRIMARY KEY(year,security)) WITHOUT ROWID")
    for row in _rows(ident, tables["annual_evidence"], identity.ANNUAL_SCHEMA.names):
        db.execute("INSERT INTO existing_annual VALUES (?,?,?)", (row["candidate_year"], row["names_permno_raw"], _json(row)))
    # Recompute only the existing source-count/status contract, using the same
    # validated occurrence tables. This does not run candidate matching again.
    check = work / "annual-validation"
    check.mkdir()
    recomputed, summaries = identity._write_annual(db, check, {"receipt_sha256": ident.receipt["inputs"]["ccm_inventory_sha256"]}, names, windows)
    for part in recomputed["parts"]:
        for row in pq.read_table(check / part["file"]).to_pylist():
            stored = db.execute("SELECT payload FROM existing_annual WHERE year=? AND security=?",
                                (row["candidate_year"], row["names_permno_raw"])).fetchone()
            _require(stored is not None and json.loads(stored[0]) == row, "Annual identity counts or source declarations differ")
    _require(recomputed["rows"] == ident.receipt["tables"]["annual_evidence"]["rows"]
             and summaries == ident.receipt["year_summaries"], "Annual identity source accounting differs")
    db.execute("CREATE TABLE annual_liquidity(year INTEGER,security TEXT,payload TEXT,PRIMARY KEY(year,security)) WITHOUT ROWID")
    counts = Counter()
    numeric_counts, eligible_counts = Counter(), Counter()
    for row in _rows(liq, liq_parts, LIQUIDITY_COLUMNS):
        year, security = row["candidate_year"], row["security_id"]
        _require(year in windows and isinstance(security, str), "Annual liquidity date or raw identifier is invalid")
        window = windows[year]
        _require(all(row[name] == window[name] for name in ("selection_asof", "selection_session", "information_cutoff", "liquidity_start", "liquidity_end"))
                 and row["expected_sessions"] == 60, "Annual liquidity calendar differs")
        for key in ("observed_sessions", "unambiguous_sessions", "conflicting_sessions", "numerically_valid_sessions", "withheld_sessions", "missing_sessions"):
            _require(0 <= row[key] <= 60, "Liquidity coverage count exceeds the annual window")
        _require(row["observed_sessions"] + row["missing_sessions"] == 60
                 and row["numerically_valid_sessions"] + row["withheld_sessions"] + row["conflicting_sessions"] == row["observed_sessions"]
                 and row["unambiguous_sessions"] + row["conflicting_sessions"] == row["observed_sessions"]
                 and row["meets_numeric_minimum_40"] == (row["numerically_valid_sessions"] >= 40),
                 "Liquidity session accounting differs")
        _require(row["listing_candidate_receipt_sha256"] == names.sha256
                 and row["numerical_candidate_receipt_sha256"] == liq.receipt["inputs"]["numerical"]["receipt_sha256"],
                 "Annual liquidity source receipts differ")
        liquidity._sha(row["liquidity_projection_evidence_sha256"])
        group = db.execute("SELECT COUNT(*) n,COUNT(DISTINCT projection) variants,MAX(ordinary) ordinary FROM names WHERE year=? AND permno=?", (year, security)).fetchone()
        _require(row["listing_record_count"] == group["n"] and row["listing_distinct_projection_count"] == group["variants"]
                 and row["ambiguous_listing"] == (group["n"] > 1)
                 and row["ordinary_listing_candidate"] == bool(group["ordinary"]), "Liquidity Names coverage differs")
        _require(row["rank_eligible_by_candidate_policy"] ==
                 (group["n"] == 1 and bool(group["ordinary"]) and row["meets_numeric_minimum_40"]),
                 "Stored candidate rank eligibility differs from its metadata policy")
        db.execute("INSERT INTO annual_liquidity VALUES (?,?,?)", (year, security, _json(row)))
        counts[year] += 1
        numeric_counts[year] += row["meets_numeric_minimum_40"]
        eligible_counts[year] += row["rank_eligible_by_candidate_policy"]
    _require([r["year"] for r in liq.receipt["year_summaries"]] == list(identity.YEARS), "Liquidity year summaries differ")
    for summary in liq.receipt["year_summaries"]:
        _require(counts[summary["year"]] == summary["security_year_rows"]
                 and numeric_counts[summary["year"]] == summary["numeric_minimum_met_securities"]
                 and eligible_counts[summary["year"]] == summary["ranked_candidate_securities"],
                 "Liquidity annual row or eligibility totals differ")
    db.commit()


def _emit_annual(db, out, ident, liq, sec_input, windows):
    writer = identity._Writer(out, "annual_foundation", ANNUAL_SCHEMA)
    only = identity._Writer(out, "liquidity_only_coverage", ANNUAL_SCHEMA)
    counts = Counter(dict.fromkeys(("annual_union_rows", "identity_rows", "liquidity_rows", "liquidity_only_rows",
                                   "identity_only_rows", "numeric_minimum_rows", "ordinary_numeric_candidate_rows", "rank_eligible_rows",
                                   "annual_rows_with_original_sec_discovery"), 0))
    crosses, gaps_total, year_counts = Counter(), Counter(), Counter()
    query = ("WITH keys AS (SELECT year,security FROM existing_annual UNION SELECT year,security FROM annual_liquidity) "
             "SELECT k.year,k.security,i.payload identity_payload,l.payload liquidity_payload FROM keys k "
             "LEFT JOIN existing_annual i USING(year,security) LEFT JOIN annual_liquidity l USING(year,security) "
             "ORDER BY k.year,k.security COLLATE BINARY")
    for item in db.execute(query):
        year, security = item["year"], item["security"]
        annual = json.loads(item["identity_payload"]) if item["identity_payload"] is not None else None
        numerical = json.loads(item["liquidity_payload"]) if item["liquidity_payload"] is not None else None
        status = annual["evidence_status"] if annual else "NO_ANNUAL_NAMES_IDENTITY_EVIDENCE"
        enough = bool(numerical and numerical["meets_numeric_minimum_40"])
        ordinary = bool(numerical and enough and numerical["ordinary_listing_candidate"] and numerical["listing_record_count"] == 1)
        rank_eligible = bool(numerical and numerical["rank_eligible_by_candidate_policy"])
        observations, filings, class_counts = 0, set(), Counter()
        for discovery in db.execute("SELECT srecord,statuses FROM discovery_stats WHERE year=? AND security=?", (year, security)):
            observations += 1
            filings.add(discovery["srecord"])
            class_counts.update(json.loads(discovery["statuses"]))
        gaps = ["HISTORICAL_IDENTITY_AVAILABILITY_UNKNOWN", "LISTING_AVAILABILITY_UNKNOWN",
                "LIQUIDITY_AVAILABILITY_UNKNOWN", "SOURCE_RELEASE_UNVERIFIED", "HISTORICAL_CIK_LINK_UNAPPROVED"]
        if not annual:
            gaps.append("NO_ANNUAL_NAMES_IDENTITY_EVIDENCE")
        else:
            if annual["candidate_ccm_records"] == 0:
                gaps.append("NO_JANUARY1_CCM_CANDIDATE")
            if annual["candidate_ccm_records"] > 1 or annual["names_ambiguous"] or annual["raw_names_ids_sharing_comparison_key"] > 1:
                gaps.append("MULTIPLE_OR_AMBIGUOUS_CANDIDATE_EVIDENCE")
            if not annual["candidate_header_cik_keys"]:
                gaps.append("MISSING_USABLE_CANDIDATE_HEADER_CIK")
            if annual["open_marker_candidate_ccm_records"] or annual["other_unresolved_candidate_ccm_records"]:
                gaps.append("CANDIDATE_LINK_BOUNDS_UNRESOLVED")
        if not numerical:
            gaps.append("NO_ANNUAL_LIQUIDITY_METADATA")
        elif not enough:
            gaps.append("FEWER_THAN_40_NUMERICALLY_VALID_SESSIONS")
        if not observations:
            gaps.append("NO_SAME_YEAR_ORIGINAL_SEC_DISCOVERY_IN_SAVED_COHORT")
        else:
            gaps.append("SAME_YEAR_SEC_OBSERVATION_AFTER_INFORMATION_CUTOFF")
        row = {"candidate_year": year, "security_id": security, "selection_asof": windows[year]["selection_asof"],
               "information_cutoff": windows[year]["information_cutoff"], "identity_present": annual is not None,
               "liquidity_present": numerical is not None, "identity_evidence_status": status,
               "ordinary_numeric_candidate": ordinary, "meets_numeric_minimum_40": enough,
               "rank_eligible_by_candidate_policy": rank_eligible,
               "source_bound_discoveries": observations, "source_bound_filings": len(filings),
               "class_observation_counts_json": _json(class_counts), "evidence_gaps_json": _json(sorted(gaps)),
               "identity_evidence_json": item["identity_payload"], "liquidity_metadata_json": item["liquidity_payload"],
               "identity_receipt_sha256": ident.sha256, "liquidity_receipt_sha256": liq.sha256,
               "sec_evidence_sha256": sec_input["sha256"], **identity._unknown()}
        writer.append(row)
        if annual is None:
            only.append(row)
        counts["annual_union_rows"] += 1
        counts["identity_rows"] += annual is not None
        counts["liquidity_rows"] += numerical is not None
        counts["liquidity_only_rows"] += annual is None
        counts["identity_only_rows"] += numerical is None
        counts["numeric_minimum_rows"] += enough
        counts["ordinary_numeric_candidate_rows"] += ordinary
        counts["rank_eligible_rows"] += rank_eligible
        counts["annual_rows_with_original_sec_discovery"] += observations > 0
        bounds = ("NO_IDENTITY" if annual is None else "UNRESOLVED" if annual["open_marker_candidate_ccm_records"]
                  or annual["other_unresolved_candidate_ccm_records"] else "FINITE_ONLY" if annual["finite_candidate_ccm_records"] else "NO_CANDIDATE")
        crosses[(status, enough, ordinary, rank_eligible, bounds, bool(observations))] += 1
        gaps_total.update(gaps)
        year_counts[year] += 1
    cross_rows = [{"identity_evidence_status": key[0], "meets_numeric_minimum_40": key[1],
                   "ordinary_numeric_candidate": key[2], "rank_eligible_by_candidate_policy": key[3], "candidate_bound_scope": key[4],
                   "original_sec_discovery_present": key[5], "rows": value} for key, value in sorted(crosses.items())]
    return writer.finish(), only.finish(), dict(counts), cross_rows, dict(gaps_total), dict(year_counts)


def build_historical_foundation_review(identity_directory, liquidity_directory, *, identity_receipt_sha256,
                                       liquidity_receipt_sha256, sec_evidence_path, sec_evidence_sha256,
                                       sec_manifest_path, sec_manifest_sha256, output, config, repo_root="."):
    repo = Path(repo_root).resolve()
    verify_lock(config, repo / "configs/protocol.lock.json")
    _require((config["initial_train_start"], config["development_end"], config["holdout_start"],
              config["liquidity_lookback_sessions"], config["liquidity_min_valid_sessions"]) == (2010, 2021, 2022, 60, 40),
             "Foundation evidence requires the frozen development years and windows")
    out = _private_directory(output, repo)
    public = _sec_input(sec_evidence_path, sec_evidence_sha256, sec_manifest_path, sec_manifest_sha256, config)
    ident, liq, tables, liq_parts, names, ccm_receipt = _load_inputs(
        identity_directory, identity_receipt_sha256, liquidity_directory, liquidity_receipt_sha256, public, config)
    _require(not any(out.is_relative_to(item.directory) for item in (ident, liq)), "Output must be separate from input bundles")
    windows = {year: year_start_window(year, config) for year in identity.YEARS}
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".historical-foundation-", dir=out.parent) as temporary:
        work, bundle = Path(temporary), Path(temporary) / "bundle"
        bundle.mkdir(mode=0o700)
        (bundle / "input_receipts").mkdir(mode=0o700)
        snapshots = [liquidity._save_bytes(bundle, "input_receipts/identity.json", ident.raw),
                     liquidity._save_bytes(bundle, "input_receipts/liquidity.json", liq.raw),
                     liquidity._save_bytes(bundle, "input_receipts/sec_evidence.json.gz", public["raw"])]
        with closing(sqlite3.connect(work / "review.sqlite3")) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA cache_size=-16384")
            db.execute("PRAGMA temp_store=FILE")
            _index_sources(db, ident, tables, names, ccm_receipt, windows)
            discoveries, coverage, class_counts, sec_coverage = _discoveries(db, bundle, ident, tables, names, public)
            _annual_inputs(db, ident, tables, liq, liq_parts, names, windows, work)
            annual, only, counts, crosses, gaps, annual_years = _emit_annual(db, bundle, ident, liq, public, windows)
        liquidity._guard([ident, liq], rehash=True)
        sec._guard(public["guards"])
        outputs = {"annual_foundation": annual, "liquidity_only_coverage": only,
                   "filing_candidate_corroboration": discoveries, "filing_coverage": coverage}
        _require(counts.get("identity_rows", 0) == ident.receipt["tables"]["annual_evidence"]["rows"]
                 and counts.get("liquidity_rows", 0) == liq.receipt["annual_liquidity"]["rows"],
                 "Full outer annual accounting lost input rows")
        receipt = {"schema_version": 1, "status": STATUS, "created_at": datetime.now(timezone.utc).isoformat(),
                   "protocol_sha256": canonical_hash(config), "years": list(identity.YEARS),
                   "inputs": {"identity_receipt_sha256": ident.sha256, "liquidity_receipt_sha256": liq.sha256,
                              "listing_receipt_sha256": names.sha256, "sec_evidence_sha256": public["sha256"],
                              "sec_evidence_json_sha256": public["json_sha256"], "sec_manifest_sha256": sec_manifest_sha256},
                   "input_receipts": snapshots, "tables": outputs, "counts": counts,
                   "cross_tabulation": crosses, "evidence_gap_counts": gaps, "annual_union_by_year": annual_years,
                   "class_observation_counts": class_counts, "sec_manifest_coverage_counts": sec_coverage,
                   "source_relationship_rows_verified": ident.receipt["tables"]["relationships"]["rows"],
                   "source_ccm_rows_verified": ident.receipt["tables"]["ccm_records"]["rows"],
                   "input_files_rehashed": len(ident.guards) + len(liq.guards) + len(public["guards"]),
                   "liquidity_columns_read": LIQUIDITY_COLUMNS,
                   "policies": {"annual_join": "full outer on exact raw security identifier and development year",
                                "sec_discovery": "only existing source-bound relationships; no new CIK assignments",
                                "class_observations": "context-bound lexical observations, not identity or class approval",
                                "availability": "all known_at and available_at remain null; SEC observations never supply historical availability",
                                "sec_source_scope": "saved original-source report hashes verified; original documents not reread in this execution",
                                "population": "saved annual observations only; no issuer grouping or 500-issuer selection"},
                   "original_sec_bytes_reread": False, "saved_sec_report_bytes_verified": True,
                   "daily_source_values_read": False, "liquidity_mean_or_rank_values_read": False,
                   "existing_rank_eligibility_boolean_read": True,
                   "market_returns_read": False, "historical_cik_links_created": 0, "source_approvals": 0,
                   "human_reviews_created": 0, "known_at_inferred": False, "available_at_inferred": False,
                   "model_ready": False, "prior_arithmetic_review_modified": False, "final_period_opened": False}
        for spec in [*snapshots, *[part for table in outputs.values() for part in table["parts"]]]:
            path = bundle / spec["file"]
            _require(path.stat().st_size == spec["bytes"] and _hash(path) == spec["sha256"], "Output evidence changed before publication")
        liquidity._save_bytes(bundle, "receipt.json", (json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
        _require(not out.exists(), "Foundation output appeared during construction")
        bundle.rename(out)
    return receipt


def aggregate_summary(receipt):
    """No vendor identifiers, source rows, private paths or value series."""
    keys = ("status", "protocol_sha256", "years", "inputs", "counts", "cross_tabulation", "evidence_gap_counts",
            "annual_union_by_year", "class_observation_counts", "sec_manifest_coverage_counts",
            "source_relationship_rows_verified", "source_ccm_rows_verified", "input_files_rehashed",
            "original_sec_bytes_reread", "saved_sec_report_bytes_verified", "daily_source_values_read",
            "liquidity_mean_or_rank_values_read", "existing_rank_eligibility_boolean_read", "market_returns_read", "historical_cik_links_created",
            "source_approvals", "human_reviews_created", "known_at_inferred", "available_at_inferred",
            "model_ready", "prior_arithmetic_review_modified", "final_period_opened")
    return {key: receipt[key] for key in keys}
