"""Reconcile existing filing discoveries with complete dated Names descriptors.

This reads metadata only. Every original discovery and unmatched SEC filing is
retained; neither a descriptor match nor a text change approves a security link.
"""

import hashlib
import json
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa

from . import historical_foundation as foundation
from . import manual_wrds_identity_candidates as identity
from . import manual_wrds_liquidity_candidates as liquidity
from . import manual_wrds_listing_candidates as listing
from .controls import control_sessions
from .manual_wrds_candidates import _inside
from .manual_wrds_intake import _hash, _identity, _private_directory
from .manual_wrds_metadata import NAMES_FIELDS
from .market_data import development_return_end
from .protocol import canonical_hash, verify_lock
from .timing import event_window
from .universe import aware_timestamp

STATUS = "DATED_NAMES_FILING_EVIDENCE_NOT_SOURCE_APPROVED"
ROLES = ("acceptance", "control", "reference", "label")
DESCRIPTOR_FIELDS = (
    "permco", "cusip", "ticker", "issuernm", "shareclass", "usincflg", "issuertype",
    "securitytype", "securitysubtype", "sharetype", "siccd", "primaryexch",
    "tradingsymbol", "naics", "tradingstatusflg",
)
_f, _require, _json = foundation._f, foundation._require, foundation._json
POINT_SCHEMA = pa.schema([
    _f("discovery_evidence_id"), _f("accession"), _f("sec_manifest_csv_record", pa.int64()),
    _f("role"), _f("role_ordinal", pa.int16()), _f("date"),
    _f("matching_records", pa.int64()), _f("distinct_raw_projections", pa.int64()),
    _f("match_status"), _f("identifier_comparison"), _f("source_records_json"),
    _f("snapshot_comparisons_json"), _f("known_at", nullable=True),
    _f("available_at", nullable=True), _f("identity_approved", pa.bool_()),
])
NAMES_SCHEMA = pa.schema([
    *[_f(field) for field in NAMES_FIELDS], _f("source_csv_record", pa.int64()),
    _f("source_sha256"), _f("source_inventory_sha256"),
    _f("used_as_annual_snapshot", pa.bool_()), _f("used_at_requested_date", pa.bool_()),
    _f("known_at", nullable=True), _f("available_at", nullable=True),
    _f("identity_approved", pa.bool_()),
])
SUMMARY_SCHEMA = pa.schema([
    _f("discovery_evidence_id"), _f("accession"), _f("sec_manifest_csv_record", pa.int64()),
    _f("annual_names_source_csv_record", pa.int64()),
    _f("original_snapshot_covers_acceptance", pa.bool_()),
    _f("acceptance_match_status"), _f("reference_match_status"),
    _f("requested_points", pa.int64()), _f("unique_requested_dates", pa.int64()),
    _f("missing_points", pa.int64()), _f("ambiguous_points", pa.int64()),
    _f("identifier_variant_points", pa.int64()), _f("descriptor_text_change_points", pa.int64()),
    _f("permco_text_change_points", pa.int64()), _f("full_window_status"),
    _f("matching_source_records_json"), _f("role_counts_json"),
    _f("known_at", nullable=True), _f("available_at", nullable=True),
    _f("identity_approved", pa.bool_()),
])


def _load_foundation(directory, digest, config):
    bundle = foundation._bundle(directory, digest, foundation.STATUS, config)
    for field in ("historical_cik_links_created", "human_reviews_created"):
        _require(type(bundle.receipt.get(field)) is int and bundle.receipt[field] == 0,
                 "Foundation evidence cannot contain new links or reviews")
    for field in ("known_at_inferred", "available_at_inferred", "original_sec_bytes_reread"):
        _require(bundle.receipt.get(field) is False, "Foundation evidence scope changed")
    snapshots = {}
    for spec in bundle.receipt["input_receipts"]:
        if spec["file"].endswith(".json"):
            snapshots[spec["file"]] = foundation._snapshot(bundle, spec)
        else:
            _require(spec["file"] == "input_receipts/sec_evidence.json.gz", "Unknown foundation snapshot")
            path = _inside(bundle.directory, spec["file"])
            before = _identity(path)
            _require(before[2] == spec["bytes"] and before[2] <= foundation._MAX_REPORT,
                     "Foundation SEC snapshot exceeds its declared size")
            raw = path.read_bytes()
            _require(hashlib.sha256(raw).hexdigest() == spec["sha256"] and _identity(path) == before,
                     "Foundation SEC snapshot byte binding differs")
            bundle.guards[path] = before, spec["sha256"]
            snapshots[spec["file"]] = None, raw
    _require(len(snapshots) == len(bundle.receipt["input_receipts"]), "Repeated foundation snapshot")
    upstream, raw = snapshots["input_receipts/identity.json"]
    liquidity._contract(upstream, identity.STATUS, config)
    _require(hashlib.sha256(raw).hexdigest() == bundle.receipt["inputs"]["identity_receipt_sha256"],
             "Foundation identity receipt binding differs")
    specs = [spec for spec in upstream["input_receipts"]
             if spec["file"] == "input_receipts/names_inventory.json"]
    _require(len(specs) == 1, "Foundation lacks one original Names inventory binding")
    return bundle, specs[0], snapshots


def _foundation_tables(bundle):
    schemas = {"annual_foundation": foundation.ANNUAL_SCHEMA,
               "liquidity_only_coverage": foundation.ANNUAL_SCHEMA,
               "filing_candidate_corroboration": foundation.DISCOVERY_SCHEMA,
               "filing_coverage": foundation.COVERAGE_SCHEMA}
    _require(set(bundle.receipt["tables"]) == set(schemas), "Foundation tables differ")
    # Hash every completed part, but interpret only the two filing metadata tables.
    return {name: foundation._parts(bundle, bundle.receipt["tables"][name], schema)
            for name, schema in schemas.items()}


def _points(discovery, config):
    accepted = aware_timestamp(discovery["recorded_acceptance_timestamp"], "SEC acceptance")
    window = event_window(accepted.to_pydatetime(), config["reference_session_offset"], config["horizon_sessions"])
    _require(window.acceptance_date == discovery["recorded_acceptance_date"]
             and config["initial_train_start"] <= int(window.acceptance_date[:4]) <= config["development_end"],
             "Discovery acceptance is outside development or differs from its clock")
    points = [("acceptance", 1, window.acceptance_date)]
    points.extend(("control", i, day) for i, day in enumerate(control_sessions(window), 1))
    points.append(("reference", 1, window.reference_session))
    points.extend(("label", i, day) for i, day in enumerate(window.return_sessions, 1))
    _require(max(day for _, _, day in points) <= development_return_end(config),
             "Requested descriptor dates exceed development source bounds")
    return points


def _raw_name(row):
    return dict(zip(NAMES_FIELDS, json.loads(row["payload"]), strict=True))


def _index_comparison_keys(db):
    db.execute("CREATE TABLE name_keys(record INTEGER PRIMARY KEY,comparison_key TEXT)")
    batch = []
    for row in db.execute("SELECT record,permno FROM source_rows ORDER BY record"):
        batch.append((row["record"], identity._integer_key(row["permno"])[0]))
        if len(batch) == 5000:
            db.executemany("INSERT INTO name_keys VALUES (?,?)", batch)
            batch.clear()
    db.executemany("INSERT INTO name_keys VALUES (?,?)", batch)
    db.execute("CREATE INDEX key_lookup ON name_keys(comparison_key)")
    db.execute("CREATE TABLE touched(record INTEGER PRIMARY KEY,snapshot INTEGER,requested INTEGER)")


def _touch(db, ordinal, *, snapshot=False, requested=False):
    db.execute("INSERT INTO touched VALUES (?,?,?) ON CONFLICT(record) DO UPDATE SET "
               "snapshot=MAX(snapshot,excluded.snapshot),requested=MAX(requested,excluded.requested)",
               (ordinal, int(snapshot), int(requested)))


def _check_discovery(row, source, db, public):
    original = dict(row)
    digest = original.pop("evidence_id")
    _require(canonical_hash(original) == digest, "Original discovery fingerprint differs")
    _require(row["names_source_sha256"] == source.sha256
             and row["names_inventory_sha256"] == source.receipt_sha256,
             "Discovery uses different original Names bytes or inventory")
    record = public["records"].get(row["sec_manifest_csv_record"])
    _require(record is not None and row["accession"] == record["accession"]
             and row["recorded_acceptance_date"] == record["acceptance_date"]
             and row["recorded_acceptance_timestamp"] == record["recorded_acceptance_timestamp"]
             and row["sec_manifest_sha256"] == public["manifest_sha256"]
             and row["sec_evidence_sha256"] == public["sha256"]
             and row["primary_source_sha256"] == record["primary_source"]["sha256"]
             and row["header_source_sha256"] == record["header_source"]["sha256"],
             "Discovery differs from bound original SEC evidence")
    snapshot = db.execute("SELECT * FROM source_rows WHERE record=?", (row["names_source_csv_record"],)).fetchone()
    _require(snapshot is not None, "Original annual Names occurrence is missing")
    name = _raw_name(snapshot)
    for field in ("permno", "issuernm", "ticker", "shareclass"):
        _require(name[field] == row[f"names_{field}_raw"], "Annual snapshot text differs from original Names row")
    year = row["candidate_year"]
    _require(year == int(row["recorded_acceptance_date"][:4])
             and snapshot["info_start"] <= f"{year}-01-01" <= snapshot["info_end"],
             "Original Names snapshot does not cover its January selection")
    covers = snapshot["info_start"] <= row["recorded_acceptance_date"] <= snapshot["info_end"]
    _require(covers is row["names_secinfo_covers_acceptance"], "Original annual acceptance diagnostic changed")
    _require(identity._integer_key(name["permno"])[0] is not None, "Discovery has an unsupported security identifier")
    _touch(db, snapshot["record"], snapshot=True)
    return name


def _observe_point(db, discovery, snapshot, role, ordinal, day):
    key = identity._integer_key(snapshot["permno"])[0]
    matches = db.execute("SELECT s.* FROM source_rows s JOIN name_keys k ON k.record=s.record "
                         "WHERE k.comparison_key=? AND s.info_start<=? AND s.info_end>=? ORDER BY s.record",
                         (key, day, day)).fetchall()
    _require(len(matches) <= 100_000, "Descriptor overlap exceeds bounded evidence limit")
    distinct = len({row["payload"] for row in matches})
    status = ("MISSING" if not matches else "UNIQUE_RECORD" if len(matches) == 1 else
              "AMBIGUOUS_EXACT_DUPLICATES" if distinct == 1 else "AMBIGUOUS_DISTINCT_RECORDS")
    raw_ids = {row["permno"] for row in matches}
    comparison = ("NO_MATCH" if not matches else "EXACT_RAW_ONLY" if raw_ids == {snapshot["permno"]} else
                  "ALIAS_RAW_ONLY" if snapshot["permno"] not in raw_ids else "MIXED_RAW_VARIANTS")
    changes = []
    for record in matches:
        name = _raw_name(record)
        changed = [field for field in NAMES_FIELDS if name[field] != snapshot[field]]
        changes.append({"source_csv_record": record["record"], "changed_raw_fields": changed,
                        "changed_descriptor_fields": [field for field in DESCRIPTOR_FIELDS if field in changed],
                        "permco_text_equal": name["permco"] == snapshot["permco"],
                        "securitylife_covers_date": name["securitybegdt"] <= day <= name["securityenddt"]})
        _touch(db, record["record"], requested=True)
    return {"discovery_evidence_id": discovery["evidence_id"], "accession": discovery["accession"],
            "sec_manifest_csv_record": discovery["sec_manifest_csv_record"], "role": role,
            "role_ordinal": ordinal, "date": day, "matching_records": len(matches),
            "distinct_raw_projections": distinct, "match_status": status, "identifier_comparison": comparison,
            "source_records_json": _json([row["record"] for row in matches]),
            "snapshot_comparisons_json": _json(changes), **identity._unknown()}


def _emit(bundle, parts, source, db, public, output, config):
    original = identity._Writer(output, "original_discoveries", foundation.DISCOVERY_SCHEMA)
    coverage = identity._Writer(output, "original_filing_coverage", foundation.COVERAGE_SCHEMA)
    points_writer = identity._Writer(output, "date_evidence", POINT_SCHEMA)
    summary_writer = identity._Writer(output, "discovery_summary", SUMMARY_SCHEMA)
    names_writer = identity._Writer(output, "names_records", NAMES_SCHEMA)
    seen, per_filing, status_counts, role_counts = set(), {}, Counter(), {role: Counter() for role in ROLES}
    counts = Counter(discoveries=0, original_snapshot_acceptance_gaps=0,
                     original_snapshot_gaps_with_unique_full_history_acceptance=0,
                     discoveries_with_complete_unambiguous_coverage=0, discoveries_with_missing_points=0,
                     discoveries_with_ambiguous_points=0, discoveries_with_identifier_variants=0,
                     discoveries_with_descriptor_text_changes=0, discoveries_with_permco_text_changes=0)
    for discovery in foundation._rows(bundle, parts["filing_candidate_corroboration"], foundation.DISCOVERY_SCHEMA.names):
        _require(discovery["evidence_id"] not in seen, "Original discovery is repeated")
        seen.add(discovery["evidence_id"])
        snapshot = _check_discovery(discovery, source, db, public)
        original.append(discovery)
        info = per_filing.setdefault(discovery["sec_manifest_csv_record"], {"rows": 0, "names": set(), "ccm": set()})
        info["rows"] += 1
        info["names"].add(discovery["names_permno_raw"])
        info["ccm"].add(discovery["ccm_source_csv_record"])
        points = [_observe_point(db, discovery, snapshot, *point) for point in _points(discovery, config)]
        missing = sum(point["match_status"] == "MISSING" for point in points)
        ambiguous = sum(point["matching_records"] > 1 for point in points)
        variants = sum(point["identifier_comparison"] in {"ALIAS_RAW_ONLY", "MIXED_RAW_VARIANTS"} for point in points)
        descriptor = sum(any(change["changed_descriptor_fields"] for change in json.loads(point["snapshot_comparisons_json"])) for point in points)
        permco = sum(any(not change["permco_text_equal"] for change in json.loads(point["snapshot_comparisons_json"])) for point in points)
        complete = not (missing or ambiguous or variants)
        acceptance, reference = points[0], next(point for point in points if point["role"] == "reference")
        local_roles = {role: Counter() for role in ROLES}
        for point in points:
            points_writer.append(point)
            status_counts[point["match_status"]] += 1
            role_counts[point["role"]][point["match_status"]] += 1
            local_roles[point["role"]][point["match_status"]] += 1
        records = sorted({record for point in points for record in json.loads(point["source_records_json"])})
        summary_writer.append({"discovery_evidence_id": discovery["evidence_id"], "accession": discovery["accession"],
            "sec_manifest_csv_record": discovery["sec_manifest_csv_record"],
            "annual_names_source_csv_record": discovery["names_source_csv_record"],
            "original_snapshot_covers_acceptance": discovery["names_secinfo_covers_acceptance"],
            "acceptance_match_status": acceptance["match_status"], "reference_match_status": reference["match_status"],
            "requested_points": len(points), "unique_requested_dates": len({point["date"] for point in points}),
            "missing_points": missing, "ambiguous_points": ambiguous, "identifier_variant_points": variants,
            "descriptor_text_change_points": descriptor, "permco_text_change_points": permco,
            "full_window_status": "COMPLETE_UNAMBIGUOUS_DESCRIPTOR_COVERAGE" if complete else "INCOMPLETE_OR_AMBIGUOUS_DESCRIPTOR_COVERAGE",
            "matching_source_records_json": _json(records), "role_counts_json": _json(local_roles), **identity._unknown()})
        counts["discoveries"] += 1
        counts["original_snapshot_acceptance_gaps"] += int(not discovery["names_secinfo_covers_acceptance"])
        counts["original_snapshot_gaps_with_unique_full_history_acceptance"] += int(
            not discovery["names_secinfo_covers_acceptance"] and acceptance["match_status"] == "UNIQUE_RECORD"
            and acceptance["identifier_comparison"] == "EXACT_RAW_ONLY")
        for name, value in (("complete_unambiguous_coverage", complete), ("missing_points", missing),
                            ("ambiguous_points", ambiguous), ("identifier_variants", variants),
                            ("descriptor_text_changes", descriptor), ("permco_text_changes", permco)):
            counts["discoveries_with_" + name] += int(bool(value))
    manifest_seen, coverage_counts = set(), Counter()
    for row in foundation._rows(bundle, parts["filing_coverage"], foundation.COVERAGE_SCHEMA.names):
        ordinal = row["sec_manifest_csv_record"]
        _require(ordinal not in manifest_seen and ordinal in public["records"], "Original filing coverage is repeated or unknown")
        manifest_seen.add(ordinal)
        record = public["records"][ordinal]
        info = per_filing.get(ordinal, {"rows": 0, "names": set(), "ccm": set()})
        _require(row["accession"] == record["accession"]
                 and row["recorded_acceptance_date"] == record["acceptance_date"]
                 and row["sec_manifest_sha256"] == public["manifest_sha256"]
                 and row["sec_evidence_sha256"] == public["sha256"]
                 and row["primary_source_sha256"] == record["primary_source"]["sha256"]
                 and row["header_source_sha256"] == record["header_source"]["sha256"]
                 and row["source_report_bound"] is True
                 and row["discovery_pair_rows"] == info["rows"]
                 and row["distinct_raw_names_ids"] == len(info["names"])
                 and row["distinct_ccm_records"] == len(info["ccm"]), "Original filing coverage differs from source/discovery accounting")
        expected = "HEADER_CIK_DISCOVERY_ONLY" if info["rows"] else "NO_SAME_YEAR_HEADER_CIK_CANDIDATE_DISCOVERY"
        _require(row["coverage_status"] == expected, "Original unmatched filing status differs")
        coverage_counts[expected] += 1
        coverage.append(row)
    _require(manifest_seen == set(public["records"]), "Not every original SEC filing was retained")
    for row in db.execute("SELECT s.*,t.snapshot,t.requested FROM touched t JOIN source_rows s ON s.record=t.record ORDER BY s.record"):
        names_writer.append({**_raw_name(row), "source_csv_record": row["record"],
                             "source_sha256": source.sha256, "source_inventory_sha256": source.receipt_sha256,
                             "used_as_annual_snapshot": bool(row["snapshot"]), "used_at_requested_date": bool(row["requested"]),
                             **identity._unknown()})
    outputs = {"original_discoveries": original.finish(), "original_filing_coverage": coverage.finish(),
               "date_evidence": points_writer.finish(), "discovery_summary": summary_writer.finish(),
               "names_records": names_writer.finish()}
    counts.update(filings=len(manifest_seen), filings_with_discovery=len(per_filing),
                  filings_without_discovery=len(manifest_seen) - len(per_filing),
                  requested_points=outputs["date_evidence"]["rows"], distinct_original_names_records=outputs["names_records"]["rows"])
    _require(counts["requested_points"] == counts["discoveries"] * 82,
             "Every discovery requires acceptance, reference, sixty controls and twenty labels")
    return outputs, dict(counts), dict(status_counts), {role: dict(value) for role, value in role_counts.items()}, dict(coverage_counts)


def build_dated_names_evidence(foundation_directory, names_inventory, *, foundation_receipt_sha256,
                               names_receipt_sha256, sec_evidence_path, sec_manifest_path,
                               output, config, repo_root="."):
    repo = Path(repo_root).resolve()
    verify_lock(config, repo / "configs/protocol.lock.json")
    _require((config["initial_train_start"], config["development_end"], config["holdout_start"],
              config["reference_session_offset"], config["horizon_sessions"]) == (2010, 2021, 2022, 2, 20),
             "Dated Names evidence requires the frozen development design")
    out = _private_directory(output, repo)
    bundle, names_spec, snapshots = _load_foundation(foundation_directory, foundation_receipt_sha256, config)
    bound = bundle.receipt["inputs"]
    # SEC dates are rejected before any private Parquet or original Names is opened.
    public = foundation._sec_input(sec_evidence_path, bound["sec_evidence_sha256"], sec_manifest_path,
                                   bound["sec_manifest_sha256"], config)
    _require(snapshots["input_receipts/sec_evidence.json.gz"][1] == public["raw"], "Foundation SEC snapshot differs")
    _require(liquidity._sha(names_receipt_sha256) == names_spec["sha256"], "Original Names inventory pin differs from foundation lineage")
    _require(not out.is_relative_to(bundle.directory)
             and not out.is_relative_to(Path(names_inventory).resolve()), "Output must be separate from source bundles")
    parts = _foundation_tables(bundle)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dated-names-", dir=out.parent) as temporary:
        work, staged = Path(temporary), Path(temporary) / "bundle"
        staged.mkdir(mode=0o700)
        (staged / "input_receipts").mkdir(mode=0o700)
        source = listing._load_source(names_inventory, staged, config)
        _require(source.receipt_sha256 == names_receipt_sha256
                 and source.receipt_identity[2] == names_spec["bytes"], "Original Names receipt differs from its binding")
        receipt_snapshots = [liquidity._save_bytes(staged, "input_receipts/foundation.json", bundle.raw),
                             liquidity._save_bytes(staged, "input_receipts/sec_evidence.json.gz", public["raw"]),
                             {"file": "input_receipts/names.json", "sha256": source.receipt_sha256,
                              "bytes": source.receipt_identity[2]}]
        with closing(sqlite3.connect(work / "names.sqlite3")) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA cache_size=-16384")
            db.execute("PRAGMA temp_store=FILE")
            db.execute("CREATE TABLE source_rows(record INTEGER PRIMARY KEY,permno TEXT,info_start TEXT,"
                       "info_end TEXT,life_start TEXT,life_end TEXT,payload TEXT)")
            preflight = listing._date_preflight(source, db)
            _index_comparison_keys(db)
            outputs, counts, statuses, roles, coverage = _emit(bundle, parts, source, db, public, staged, config)
            counts["original_names_source_rows_checked"] = preflight["rows"]
        listing._guard(source, rehash=True)
        liquidity._guard([bundle], rehash=True)
        foundation.sec._guard(public["guards"])
        receipt = {"schema_version": 1, "status": STATUS, "created_at": datetime.now(timezone.utc).isoformat(),
                   "protocol_sha256": canonical_hash(config), "years": list(identity.YEARS),
                   "inputs": {"foundation_receipt_sha256": bundle.sha256,
                              "names_inventory_sha256": source.receipt_sha256, "names_source_sha256": source.sha256,
                              "names_source_bytes": source.identity[2], "sec_evidence_sha256": public["sha256"],
                              "sec_manifest_sha256": public["manifest_sha256"]},
                   "input_receipts": receipt_snapshots, "tables": outputs, "counts": counts,
                   "point_status_counts": statuses, "point_status_counts_by_role": roles,
                   "sec_manifest_coverage_counts": coverage, "names_preflight": preflight,
                   "normalization_code_sha256": _hash(Path(__file__)),
                   "policies": {"matching": "inclusive SecInfo dates over all original rows with the same valid PERMNO comparison key; raw variants remain unresolved",
                                "duplicates": "all original occurrences retained; duplicate records remain ambiguous",
                                "descriptor_text_fields": list(DESCRIPTOR_FIELDS),
                                "permco": "literal Names-versus-January-Names comparison only, not a CCM agreement claim",
                                "security_lifetime": "diagnostic only; never extends descriptor intervals",
                                "date_points": "82 role/date points per discovery; acceptance can repeat a control date and need not be an exchange session"},
                   "all_original_discoveries_retained": True, "all_original_sec_filings_retained": True,
                   "original_names_csv_reread": True, "complete_names_date_preflight_before_matching": True,
                   "original_sec_bytes_reread": False, "daily_market_files_opened": False,
                   "market_outcomes_read": False, "historical_cik_links_created": 0, "source_approvals": 0,
                   "human_reviews_created": 0, "known_at_inferred": False, "available_at_inferred": False,
                   "model_ready": False, "prior_arithmetic_review_modified": False, "final_period_opened": False}
        for spec in [*receipt_snapshots, *[part for table in outputs.values() for part in table["parts"]]]:
            path = staged / spec["file"]
            _require(path.stat().st_size == spec["bytes"] and _hash(path) == spec["sha256"], "Output evidence changed before publication")
        liquidity._save_bytes(staged, "receipt.json", (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
        liquidity._save_bytes(staged, "aggregate.json", (json.dumps(aggregate_summary(receipt), indent=2, sort_keys=True) + "\n").encode())
        _require(not out.exists(), "Output appeared during construction; original evidence preserved")
        staged.rename(out)
    return receipt


def aggregate_summary(receipt):
    """Only counts, hashes, fixed policy keys and scope declarations are public."""
    keys = ("status", "protocol_sha256", "years", "inputs", "counts", "point_status_counts",
            "point_status_counts_by_role", "sec_manifest_coverage_counts", "normalization_code_sha256",
            "all_original_discoveries_retained", "all_original_sec_filings_retained", "original_names_csv_reread",
            "complete_names_date_preflight_before_matching", "original_sec_bytes_reread", "daily_market_files_opened",
            "market_outcomes_read", "historical_cik_links_created", "source_approvals", "human_reviews_created",
            "known_at_inferred", "available_at_inferred", "model_ready", "prior_arithmetic_review_modified", "final_period_opened")
    return {key: receipt[key] for key in keys}
