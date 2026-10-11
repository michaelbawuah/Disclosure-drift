"""Dated ownership-form observations for the complete saved 2020 candidate cohort.

Metadata only: literal issuer/symbol observations never become historical links,
availability timestamps, class decisions, or approved universe membership.
"""

import csv
import hashlib
import io
import json
import re
import sqlite3
import tempfile
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

import pyarrow as pa

from . import dated_names_evidence as dated
from . import historical_foundation as foundation
from . import manual_wrds_identity_candidates as identity
from . import manual_wrds_liquidity_candidates as liquidity
from . import manual_wrds_listing_candidates as listing
from .manual_wrds_intake import _hash, _private_directory
from .manual_wrds_metadata import NAMES_FIELDS
from .protocol import canonical_hash, verify_lock
from .universe import aware_timestamp, year_start_window

STATUS = "SEC_OWNERSHIP_ISSUER_OBSERVATIONS_NOT_APPROVED_LINKS"
YEAR, QUARTER_START, QUARTER_END = 2020, "2019-10-01", "2019-12-31"
SEC_FIELDS = tuple("""ACCESSION_NUMBER FILING_DATE PERIOD_OF_REPORT DATE_OF_ORIG_SUB
    NO_SECURITIES_OWNED NOT_SUBJECT_SEC16 FORM3_HOLDINGS_REPORTED FORM4_TRANS_REPORTED
    DOCUMENT_TYPE ISSUERCIK ISSUERNAME ISSUERTRADINGSYMBOL REMARKS""".split())
_MONTHS = dict(zip("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), range(1, 13), strict=True))
_PLACEHOLDERS = ("n/a", "na", "none", "not applicable", "not available", "no symbol", "no ticker", "null")
_MAX_PUBLIC_BYTES, _MAX_PUBLIC_ROWS, _MAX_MATCHES = 64 * 1024 * 1024, 500_000, 100_000
_f, _require, _json = foundation._f, foundation._require, foundation._json
_UNKNOWN = identity._UNKNOWN
SEC_SCHEMA = pa.schema([
    *[_f(field) for field in SEC_FIELDS], _f("source_tsv_record", pa.int64()), _f("source_sha256"),
    _f("filing_date"), _f("cutoff_date_relation"), _f("symbol_status"),
    _f("issuer_cik_comparison_key", nullable=True), _f("issuer_cik_grammar"),
    _f("accession_occurrences", pa.int64()), *_UNKNOWN,
])
NAMES_SCHEMA = pa.schema([
    *[_f(field) for field in NAMES_FIELDS], _f("source_csv_record", pa.int64()),
    _f("source_sha256"), _f("source_inventory_sha256"), _f("retention_roles_json"), *_UNKNOWN,
])
RELATIONSHIP_SCHEMA = pa.schema([*identity.PAIR_SCHEMA, _f("relationship_evidence_id")])
OBSERVATION_SCHEMA = pa.schema([
    _f("observation_id"), _f("security_id"), _f("source_tsv_record", pa.int64()), _f("accession"),
    _f("filing_date"), _f("cutoff_date_relation"), _f("sec_issuer_cik_raw"),
    _f("sec_issuer_cik_comparison_key", nullable=True), _f("sec_symbol_raw"),
    _f("names_source_csv_record", pa.int64()), _f("matched_fields_json"),
    _f("cohort_identifier_comparison"), _f("global_symbol_source_records_json"),
    _f("security_date_source_records_json"), _f("global_symbol_record_count", pa.int64()),
    _f("security_date_record_count", pa.int64()), _f("unambiguous_exact_literal_observation", pa.bool_()),
    _f("names_record_covers_selection", pa.bool_()), _f("securitylife_covers_filing_date", pa.bool_()),
    _f("sec_source_sha256"), _f("names_source_sha256"), *_UNKNOWN,
])
COMPARISON_SCHEMA = pa.schema([
    _f("observation_id"), _f("security_id"), _f("relationship_evidence_id", nullable=True),
    _f("ccm_source_csv_record", pa.int64(), nullable=True), _f("candidate_search", pa.bool_(), nullable=True),
    _f("ccm_header_cik_raw", nullable=True), _f("cik_comparison"),
    _f("ccm_relation_at_filing_date", nullable=True), _f("dated_names_ccm_permco_comparison", nullable=True),
    *_UNKNOWN,
])
SUMMARY_SCHEMA = pa.schema([
    _f("security_id"), _f("identity_evidence_status"), _f("observation_status"),
    *[_f(name, pa.int64()) for name in (
        "names_quarter_records", "names_selection_records", "original_relationship_rows",
        "original_candidate_relationship_rows", "observation_rows", "sec_occurrences",
        "earlier_date_sec_occurrences", "cutoff_day_sec_occurrences",
        "unambiguous_earlier_date_sec_occurrences")],
    _f("earlier_issuer_cik_literals_json"), _f("earlier_issuer_cik_comparison_keys_json"),
    _f("unambiguous_earlier_candidate_header_comparisons_json"),
    _f("earlier_candidate_header_agreement", pa.bool_()),
    _f("earlier_candidate_header_disagreement", pa.bool_()), *_UNKNOWN,
])
FOLLOWUP_SCHEMA = pa.schema([
    _f("security_id"), _f("source_tsv_record", pa.int64(), nullable=True), _f("accession", nullable=True),
    _f("filing_date", nullable=True), _f("document_type", nullable=True), _f("priority", pa.int16()),
    _f("reasons_json"), _f("names_source_records_json"), _f("relationship_evidence_ids_json"),
    _f("action"), *_UNKNOWN,
])


def _read_public(path, digest, guards):
    path = Path(path).absolute()
    before = foundation.sec._regular(path, _MAX_PUBLIC_BYTES)
    raw = foundation.sec._BoundedFile(path, before, _MAX_PUBLIC_BYTES).read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == liquidity._sha(digest), "Public input pin differs")
    guards[path] = before, digest
    return raw


def _filing_date(raw):
    match = re.fullmatch(r"([0-9]{2})-([A-Z]{3})-([0-9]{4})", raw)
    _require(match is not None and match[2] in _MONTHS, "SEC filing date has unsupported grammar")
    return date(int(match[3]), _MONTHS[match[2]], int(match[1])).isoformat()


def _cutoff_relation(day, cutoff_day):
    return ("BEFORE_CUTOFF_DATE" if day < cutoff_day else
            "CUTOFF_DAY_TIME_UNRESOLVED" if day == cutoff_day else "AFTER_CUTOFF_DATE")


def _symbol_status(raw):
    if not raw or raw.isspace():
        return "EMPTY_LITERAL"
    if raw.strip().casefold() in _PLACEHOLDERS:
        return "PLACEHOLDER_OR_AMBIGUOUS_LITERAL"
    if any(char.isspace() or char in ",;|" for char in raw):
        return "COMBINED_OR_SPACED_LITERAL_UNRESOLVED"
    return "SINGLE_LITERAL_CANDIDATE"


def _load_public(submission_path, ledger_path, ledger_sha256, collection_path, window):
    """Read every original SEC column/date before any private input is opened."""
    guards = {}
    ledger_raw = _read_public(ledger_path, ledger_sha256, guards)
    ledger = json.loads(ledger_raw)
    _require(ledger.get("schema_version") == 1
             and ledger.get("status") == "PUBLIC_HISTORICAL_IDENTITY_CORROBORATION_NOT_APPROVED_LINKS",
             "SEC source ledger contract differs")
    collection_sha = ledger["collection_receipt"]["sha256"]
    collection_raw = _read_public(collection_path, collection_sha, guards)
    collection = json.loads(collection_raw)
    _require(collection.get("schema_version") == 1
             and collection.get("archive_members_read") == ["SUBMISSION.tsv"]
             and all(collection.get(key) is False for key in (
                 "final_period_sources_read", "reportingowner_member_read", "transaction_or_holdings_members_read")),
             "SEC collection scope differs")
    specification = collection["submission"]
    demo = ledger["insider_2019q4_metadata_demo"]
    _require(demo["submission"] == specification
             and collection["source_receipts"]["insider_2019q4"] == ledger["source_receipts"]["insider_2019q4"]
             and collection["source_receipts"]["insider_2019q4"]["url"]
             == "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/2019q4_form345.zip",
             "SEC source ledger and collection lineage differ")
    raw = _read_public(submission_path, specification["sha256"], guards)
    _require(len(raw) == specification["bytes"] and specification["delivered_field_order"] == list(SEC_FIELDS),
             "SEC source byte count or delivered schema differs")
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), delimiter="\t", strict=True)
    _require(next(reader, None) == list(SEC_FIELDS), "SEC source must retain the exact 13-column delivered schema")
    rows, accessions, forms, dates = [], Counter(), Counter(), Counter()
    cutoff_day = aware_timestamp(window["information_cutoff"], "Selection cutoff").tz_convert("America/New_York").date().isoformat()
    for ordinal, values in enumerate(reader, 2):
        _require(len(values) == len(SEC_FIELDS) and len(rows) < _MAX_PUBLIC_ROWS,
                 "SEC source has an invalid record width or exceeds its row bound")
        row = dict(zip(SEC_FIELDS, values, strict=True))
        day = _filing_date(row["FILING_DATE"])
        _require(QUARTER_START <= day <= QUARTER_END, "SEC filing date is outside the fixed development quarter")
        _require(identity._ACCESSION.fullmatch(row["ACCESSION_NUMBER"]) is not None
                 and row["DOCUMENT_TYPE"] in {"3", "3/A", "4", "4/A", "5", "5/A"},
                 "SEC accession or ownership form is unsupported")
        key, grammar = identity._integer_key(row["ISSUERCIK"], cik=True)
        rows.append({**row, "source_tsv_record": ordinal, "source_sha256": specification["sha256"],
                     "filing_date": day, "cutoff_date_relation": _cutoff_relation(day, cutoff_day),
                     "symbol_status": _symbol_status(row["ISSUERTRADINGSYMBOL"]),
                     "issuer_cik_comparison_key": key, "issuer_cik_grammar": grammar, **identity._unknown()})
        accessions[row["ACCESSION_NUMBER"]] += 1
        forms[row["DOCUMENT_TYPE"]] += 1
        dates[day] += 1
    _require(len(rows) == specification["rows"] and len(rows) > 0
             and len(rows) - len(accessions) == specification["accession_duplicates_excess"]
             and dict(forms) == specification["document_type_counts"]
             and min(dates) == specification["filing_dates"]["min"]
             and max(dates) == specification["filing_dates"]["max"],
             "SEC complete-source counts differ from the collection")
    for row in rows:
        row["accession_occurrences"] = accessions[row["ACCESSION_NUMBER"]]
    foundation.sec._guard(guards)
    return {"rows": rows, "raw": raw, "ledger_raw": ledger_raw, "collection_raw": collection_raw,
            "sha256": specification["sha256"], "ledger_sha256": ledger_sha256,
            "collection_sha256": collection_sha, "guards": guards,
            "archive_sha256": collection["source_receipts"]["insider_2019q4"]["sha256"],
            "cutoff_counts": dict(Counter(row["cutoff_date_relation"] for row in rows)),
            "symbol_status_counts": dict(Counter(row["symbol_status"] for row in rows))}


def _load_private(foundation_directory, foundation_digest, identity_directory, identity_digest, config):
    bundle, names_spec, preserved = dated._load_foundation(foundation_directory, foundation_digest, config)
    ident = foundation._bundle(identity_directory, identity_digest, identity.STATUS, config)
    _require(ident.raw == preserved["input_receipts/identity.json"][1],
             "Original identity receipt differs from the pinned foundation snapshot")
    _require(ident.receipt.get("historical_cik_supplied") is False
             and ident.receipt.get("historical_availability_supplied") is False
             and ident.receipt.get("approved_security_links_created") == 0,
             "Original identity evidence scope differs")
    snapshots = {spec["file"]: foundation._snapshot(ident, spec) for spec in ident.receipt["input_receipts"]}
    _require(len(snapshots) == len(ident.receipt["input_receipts"]), "Repeated identity snapshot")
    listing_receipt, listing_raw = snapshots["input_receipts/listing_candidates.json"]
    inventory, inventory_raw = snapshots["input_receipts/names_inventory.json"]
    ccm_receipt, ccm_raw = snapshots["input_receipts/ccm_inventory.json"]
    listing_sha = hashlib.sha256(listing_raw).hexdigest()
    _require(hashlib.sha256(inventory_raw).hexdigest() == names_spec["sha256"]
             and listing_sha == bundle.receipt["inputs"]["listing_receipt_sha256"]
             == ident.receipt["inputs"]["listing_candidates_sha256"]
             and listing_receipt["source"]["inventory_receipt_sha256"] == names_spec["sha256"]
             and listing_receipt["source"]["source_sha256"] == inventory["source"]["sha256"]
             and hashlib.sha256(ccm_raw).hexdigest() == ident.receipt["inputs"]["ccm_inventory_sha256"]
             and ccm_receipt["source"]["sha256"] == ident.receipt["inputs"]["ccm_source_sha256"],
             "Original Names/CCM receipt lineage differs")
    liquidity._contract(listing_receipt, liquidity.LISTING_STATUS, config)
    _require(listing_receipt["candidate_policy"] == listing.POLICY
             and listing_receipt["candidate_policy_sha256"] == canonical_hash(listing.POLICY),
             "Original listing candidate policy differs")
    schemas = {"ccm_records": identity.CCM_SCHEMA, "relationships": identity.PAIR_SCHEMA,
               "annual_evidence": identity.ANNUAL_SCHEMA, "sec_discovery": identity.SEC_MATCH_SCHEMA,
               "sec_manifest_coverage": identity.SEC_COVERAGE_SCHEMA, "names_evidence": listing.CANDIDATE_SCHEMA}
    _require(set(ident.receipt["tables"]) == set(schemas), "Original identity table set differs")
    tables = {name: foundation._parts(ident, ident.receipt["tables"][name], schema) for name, schema in schemas.items()}
    original = listing_receipt["projection"]["parts"]
    _require([(spec["sha256"], spec["bytes"], spec["rows"]) for _, spec in tables["names_evidence"]]
             == [(spec["sha256"], spec["bytes"], spec["rows"]) for spec in original],
             "Preserved annual Names parts differ from their listing source")
    names = foundation._Bundle(ident.directory, listing_receipt, listing_raw, listing_sha,
                               ident.guards, tables["names_evidence"])
    return bundle, ident, names_spec, tables, names, ccm_receipt


def _cohort(bundle, parts, ident, tables, windows):
    originals = {}
    for row in foundation._rows(ident, tables["annual_evidence"], identity.ANNUAL_SCHEMA.names):
        key = row["candidate_year"], row["names_permno_raw"]
        _require(key not in originals, "Original annual identity key is repeated")
        originals[key] = row
    rows, seen, by_year, total_eligible = [], set(), Counter(), 0
    for row in foundation._rows(bundle, parts["annual_foundation"], foundation.ANNUAL_SCHEMA.names):
        year, security = row["candidate_year"], row["security_id"]
        _require(year in windows and (year, security) not in seen, "Foundation annual key is repeated or out of development")
        seen.add((year, security))
        by_year[year] += 1
        _require(all(row[key] == windows[year][key] for key in ("selection_asof", "information_cutoff")),
                 "Foundation annual selection clock differs")
        original = originals.get((year, security))
        _require(row["identity_present"] == (original is not None)
                 and row["identity_evidence_json"] == (_json(original) if original is not None else None)
                 and row["identity_receipt_sha256"] == ident.sha256
                 and row["liquidity_receipt_sha256"] == bundle.receipt["inputs"]["liquidity_receipt_sha256"],
                 "Foundation annual identity content or provenance differs")
        numerical = json.loads(row["liquidity_metadata_json"]) if row["liquidity_metadata_json"] else None
        _require(row["liquidity_present"] == (numerical is not None)
                 and row["rank_eligible_by_candidate_policy"] == bool(numerical and numerical["rank_eligible_by_candidate_policy"]),
                 "Foundation saved rank-eligibility declaration differs")
        if numerical:
            _require(set(numerical) == set(foundation.LIQUIDITY_COLUMNS)
                     and numerical["candidate_year"] == year and numerical["security_id"] == security
                     and numerical["known_at"] is None and numerical["available_at"] is None,
                     "Foundation liquidity metadata projection differs")
        total_eligible += row["rank_eligible_by_candidate_policy"]
        if year == YEAR and row["rank_eligible_by_candidate_policy"]:
            _require(original is not None and row["identity_evidence_status"] == original["evidence_status"],
                     "Eligible cohort lacks its original annual identity evidence")
            rows.append(row)
    _require(dict(by_year) == {int(key): value for key, value in bundle.receipt["annual_union_by_year"].items()}
             and len(seen) == bundle.receipt["counts"]["annual_union_rows"]
             and total_eligible == bundle.receipt["counts"]["rank_eligible_rows"]
             and set(originals).issubset(seen), "Complete foundation annual accounting differs")
    return rows, by_year[YEAR]


def _index_full_names(db, cohort):
    db.execute("CREATE TABLE name_keys(record INTEGER PRIMARY KEY,comparison_key TEXT)")
    db.execute("CREATE TABLE symbols(symbol TEXT,record INTEGER,fields TEXT,PRIMARY KEY(symbol,record)) WITHOUT ROWID")
    db.execute("CREATE TABLE retained_names(record INTEGER,role TEXT,PRIMARY KEY(record,role)) WITHOUT ROWID")
    keys, symbols = [], []
    for row in db.execute("SELECT record,payload FROM source_rows ORDER BY record"):
        raw = dated._raw_name(row)
        keys.append((row["record"], identity._integer_key(raw["permno"])[0]))
        literals = defaultdict(list)
        for field in ("ticker", "tradingsymbol"):
            literals[raw[field]].append(field)
        symbols.extend((literal, row["record"], _json(fields)) for literal, fields in literals.items())
        if len(keys) >= 5000:
            db.executemany("INSERT INTO name_keys VALUES (?,?)", keys)
            db.executemany("INSERT INTO symbols VALUES (?,?,?)", symbols)
            keys.clear()
            symbols.clear()
    db.executemany("INSERT INTO name_keys VALUES (?,?)", keys)
    db.executemany("INSERT INTO symbols VALUES (?,?,?)", symbols)
    db.execute("CREATE INDEX name_key_lookup ON name_keys(comparison_key)")
    by_key = defaultdict(list)
    context = {}
    for row in cohort:
        security = row["security_id"]
        key = identity._integer_key(security)[0]
        _require(key is not None, "Eligible cohort contains an unsupported security identifier")
        by_key[key].append(security)
        records = db.execute("SELECT s.* FROM source_rows s JOIN name_keys k USING(record) WHERE k.comparison_key=? "
                             "AND ((s.info_start<=? AND s.info_end>=?) OR (s.info_start<=? AND s.info_end>=?)) ORDER BY record",
                             (key, QUARTER_END, QUARTER_START, f"{YEAR}-01-01", f"{YEAR}-01-01")).fetchall()
        quarter = [r["record"] for r in records if r["info_start"] <= QUARTER_END and r["info_end"] >= QUARTER_START]
        selection = [r["record"] for r in records if r["info_start"] <= f"{YEAR}-01-01" <= r["info_end"]]
        context[security] = {"quarter": quarter, "selection": selection}
        for record in records:
            _retain(db, record["record"], "COHORT_QUARTER_OR_SELECTION_DESCRIPTOR")
    return by_key, context


def _retain(db, record, role):
    db.execute("INSERT OR IGNORE INTO retained_names VALUES (?,?)", (record, role))


def _observe(db, sec, by_key, cache, source_sha):
    if sec["symbol_status"] != "SINGLE_LITERAL_CANDIDATE":
        return []
    day = sec["filing_date"]
    matches = db.execute("SELECT s.*,k.comparison_key,t.fields FROM symbols t JOIN source_rows s USING(record) "
                         "JOIN name_keys k USING(record) WHERE t.symbol=? AND s.info_start<=? AND s.info_end>=? ORDER BY s.record",
                         (sec["ISSUERTRADINGSYMBOL"], day, day)).fetchall()
    _require(len(matches) <= _MAX_MATCHES, "Global symbol overlap exceeds its bounded evidence limit")
    result = []
    for record in matches:
        if record["comparison_key"] not in by_key:
            continue
        key = record["comparison_key"], day
        if key not in cache:
            cache[key] = db.execute("SELECT s.record,s.permno FROM source_rows s JOIN name_keys k USING(record) "
                                    "WHERE k.comparison_key=? AND s.info_start<=? AND s.info_end>=? ORDER BY s.record",
                                    (key[0], day, day)).fetchall()
        local = cache[key]
        _require(len(local) <= _MAX_MATCHES, "Security descriptor overlap exceeds its bounded evidence limit")
        for match in matches:
            _retain(db, match["record"], "GLOBAL_SYMBOL_COLLISION_CONTEXT")
        for item in local:
            _retain(db, item["record"], "FULL_SECURITY_DATE_DESCRIPTOR_CONTEXT")
        raw = dated._raw_name(record)
        for security in by_key[record["comparison_key"]]:
            comparison = identity._id_comparison(security, raw["permno"], record["comparison_key"], record["comparison_key"])
            observation = {"security_id": security, "source_tsv_record": sec["source_tsv_record"],
                "accession": sec["ACCESSION_NUMBER"], "filing_date": day, "cutoff_date_relation": sec["cutoff_date_relation"],
                "sec_issuer_cik_raw": sec["ISSUERCIK"], "sec_issuer_cik_comparison_key": sec["issuer_cik_comparison_key"],
                "sec_symbol_raw": sec["ISSUERTRADINGSYMBOL"], "names_source_csv_record": record["record"],
                "matched_fields_json": record["fields"], "cohort_identifier_comparison": comparison,
                "global_symbol_source_records_json": _json([r["record"] for r in matches]),
                "security_date_source_records_json": _json([r["record"] for r in local]),
                "global_symbol_record_count": len(matches), "security_date_record_count": len(local),
                "unambiguous_exact_literal_observation": (len(matches) == len(local) == 1
                    and comparison == "EXACT_RAW_TEXT" and sec["issuer_cik_comparison_key"] is not None),
                "names_record_covers_selection": record["info_start"] <= f"{YEAR}-01-01" <= record["info_end"],
                "securitylife_covers_filing_date": record["life_start"] <= day <= record["life_end"],
                "sec_source_sha256": sec["source_sha256"], "names_source_sha256": source_sha, **identity._unknown()}
            observation["observation_id"] = canonical_hash(observation)
            result.append((observation, raw))
    return result


def _compare(observation, name, relation):
    result = {"observation_id": observation["observation_id"], "security_id": observation["security_id"],
              "relationship_evidence_id": None, "ccm_source_csv_record": None, "candidate_search": None,
              "ccm_header_cik_raw": None, "cik_comparison": "NO_RELATED_CCM_RECORD",
              "ccm_relation_at_filing_date": None, "dated_names_ccm_permco_comparison": None, **identity._unknown()}
    if relation is not None:
        result.update(relationship_evidence_id=relation["relationship_evidence_id"],
                      ccm_source_csv_record=relation["ccm_source_csv_record"], candidate_search=relation["candidate_search"],
                      ccm_header_cik_raw=relation["ccm_header_cik_raw"],
                      cik_comparison=identity._id_comparison(
                          observation["sec_issuer_cik_raw"], relation["ccm_header_cik_raw"],
                          observation["sec_issuer_cik_comparison_key"], relation["header_cik_comparison_key"]),
                      ccm_relation_at_filing_date=identity._relation(
                          relation["ccm_linkdt_raw"], relation["ccm_linkenddt_raw"], observation["filing_date"])[0],
                      dated_names_ccm_permco_comparison=identity._id_comparison(
                          name["permco"], relation["ccm_lpermco_raw"], identity._integer_key(name["permco"])[0],
                          identity._integer_key(relation["ccm_lpermco_raw"])[0]))
    return result


def _emit(db, cohort, context, by_key, ident, tables, public, source, out):
    schemas = {"cohort": foundation.ANNUAL_SCHEMA, "sec_occurrences": SEC_SCHEMA, "names_records": NAMES_SCHEMA,
               "original_relationships": RELATIONSHIP_SCHEMA, "ccm_records": identity.CCM_SCHEMA,
               "observations": OBSERVATION_SCHEMA, "header_comparisons": COMPARISON_SCHEMA,
               "cohort_summary": SUMMARY_SCHEMA, "original_source_followup": FOLLOWUP_SCHEMA}
    writers = {name: identity._Writer(out, name, schema) for name, schema in schemas.items()}
    originals = {row["security_id"]: row for row in cohort}
    relations, ccm_records = defaultdict(list), set()
    for row in cohort:
        writers["cohort"].append(row)
    for row in foundation._rows(ident, tables["relationships"], identity.PAIR_SCHEMA.names):
        if row["candidate_year"] == YEAR and row["names_permno_raw"] in originals:
            relation = {**row, "relationship_evidence_id": canonical_hash(row)}
            relations[row["names_permno_raw"]].append(relation)
            ccm_records.add(row["ccm_source_csv_record"])
            writers["original_relationships"].append(relation)
    for row in foundation._rows(ident, tables["ccm_records"], identity.CCM_SCHEMA.names):
        if row["ccm_source_csv_record"] in ccm_records:
            writers["ccm_records"].append(row)
    stats = {security: {"rows": 0, "sec": set(), "early": set(), "cutoff": set(), "unique_early": set(),
                        "ciks": set(), "keys": set(), "comparisons": Counter()} for security in originals}
    cache, followups = {}, {}
    for sec in public["rows"]:
        writers["sec_occurrences"].append(sec)
        for observation, name in _observe(db, sec, by_key, cache, source.sha256):
            security, ordinal = observation["security_id"], sec["source_tsv_record"]
            writers["observations"].append(observation)
            current = stats[security]
            current["rows"] += 1
            current["sec"].add(ordinal)
            earlier = observation["cutoff_date_relation"] == "BEFORE_CUTOFF_DATE"
            current["early" if earlier else "cutoff"].add(ordinal)
            if earlier:
                current["ciks"].add(sec["ISSUERCIK"])
                if sec["issuer_cik_comparison_key"] is not None:
                    current["keys"].add(sec["issuer_cik_comparison_key"])
                if observation["unambiguous_exact_literal_observation"]:
                    current["unique_early"].add(ordinal)
            followup = followups.setdefault((security, ordinal), {
                "security_id": security, "source_tsv_record": ordinal, "accession": sec["ACCESSION_NUMBER"],
                "filing_date": sec["filing_date"], "document_type": sec["DOCUMENT_TYPE"], "priority": 3,
                "reasons": {"ORIGINAL_ISSUER_ROLE_AND_SOURCE_VERSION_UNVERIFIED"}, "names": set(), "relations": set()})
            followup["names"].add(observation["names_source_csv_record"])
            if originals[security]["identity_evidence_status"] != "SINGLE_CANDIDATE_REQUIRES_HISTORICAL_IDENTITY_EVIDENCE":
                followup["priority"] = 0
                followup["reasons"].add("CURRENT_HEADER_IDENTITY_UNSUPPORTED_OR_AMBIGUOUS")
            if not earlier:
                followup["priority"] = min(followup["priority"], 2)
                followup["reasons"].add("CUTOFF_DAY_CLOCK_UNKNOWN")
            if not observation["unambiguous_exact_literal_observation"]:
                followup["priority"] = min(followup["priority"], 1)
                followup["reasons"].add("DATED_NAMES_OR_ISSUER_LITERAL_AMBIGUOUS")
            for relation in relations[security] or [None]:
                comparison = _compare(observation, name, relation)
                writers["header_comparisons"].append(comparison)
                if relation is not None:
                    followup["relations"].add(relation["relationship_evidence_id"])
                if earlier and observation["unambiguous_exact_literal_observation"] and comparison["candidate_search"] is True:
                    current["comparisons"][comparison["cik_comparison"]] += 1
                if comparison["candidate_search"] is True and comparison["cik_comparison"] == "DIFFERENT_VALID_COMPARISON_KEYS":
                    followup["priority"] = 0
                    followup["reasons"].add("CURRENT_HEADER_CIK_DIFFERS")
    crosses, statuses, counts = Counter(), Counter(), Counter()
    for security, original in originals.items():
        current = stats[security]
        status = ("NO_DATED_NAMES_DESCRIPTOR_IN_QUARTER" if not context[security]["quarter"] else
                  "NO_EXACT_SINGLE_LITERAL_SEC_OBSERVATION" if not current["sec"] else
                  "CUTOFF_DAY_OBSERVATIONS_ONLY" if not current["early"] else
                  "EARLIER_DATE_OBSERVATIONS_WITHOUT_UNAMBIGUOUS_MATCH" if not current["unique_early"] else
                  "MULTIPLE_EARLIER_ISSUER_KEYS_OBSERVED" if len(current["keys"]) > 1 else
                  "EARLIER_DATE_UNAMBIGUOUS_LITERAL_OBSERVATIONS")
        comparisons = current["comparisons"]
        agreement = bool(comparisons["EXACT_RAW_TEXT"] + comparisons["LEADING_ZERO_COMPARISON_ONLY"])
        disagreement = bool(comparisons["DIFFERENT_VALID_COMPARISON_KEYS"])
        summary = {"security_id": security, "identity_evidence_status": original["identity_evidence_status"],
                   "observation_status": status, "names_quarter_records": len(context[security]["quarter"]),
                   "names_selection_records": len(context[security]["selection"]),
                   "original_relationship_rows": len(relations[security]),
                   "original_candidate_relationship_rows": sum(row["candidate_search"] for row in relations[security]),
                   "observation_rows": current["rows"], "sec_occurrences": len(current["sec"]),
                   "earlier_date_sec_occurrences": len(current["early"]), "cutoff_day_sec_occurrences": len(current["cutoff"]),
                   "unambiguous_earlier_date_sec_occurrences": len(current["unique_early"]),
                   "earlier_issuer_cik_literals_json": _json(sorted(current["ciks"])),
                   "earlier_issuer_cik_comparison_keys_json": _json(sorted(current["keys"])),
                   "unambiguous_earlier_candidate_header_comparisons_json": _json(comparisons),
                   "earlier_candidate_header_agreement": agreement,
                   "earlier_candidate_header_disagreement": disagreement, **identity._unknown()}
        writers["cohort_summary"].append(summary)
        statuses[status] += 1
        crosses[(original["identity_evidence_status"], status, agreement, disagreement)] += 1
        counts["cohort_rows_with_any_sec_observation"] += bool(current["sec"])
        counts["cohort_rows_without_sec_observation"] += not current["sec"]
        counts["cohort_rows_with_unambiguous_earlier_date_observation"] += bool(current["unique_early"])
        counts["cohort_rows_with_earlier_candidate_header_agreement"] += agreement
        counts["cohort_rows_with_earlier_candidate_header_disagreement"] += disagreement
        counts["cohort_rows_with_multiple_earlier_issuer_keys"] += len(current["keys"]) > 1
        if not current["sec"]:
            followups[(security, 0)] = {"security_id": security, "source_tsv_record": None, "accession": None,
                "filing_date": None, "document_type": None, "priority": 0,
                "reasons": {status}, "names": set(context[security]["quarter"]), "relations": set()}
    for _, row in sorted(followups.items()):
        writers["original_source_followup"].append({
            **{key: row[key] for key in ("security_id", "source_tsv_record", "accession", "filing_date", "document_type", "priority")},
            "reasons_json": _json(sorted(row["reasons"])), "names_source_records_json": _json(sorted(row["names"])),
            "relationship_evidence_ids_json": _json(sorted(row["relations"])),
            "action": ("RETRIEVE_ORIGINAL_OWNERSHIP_XML_AND_HEADER" if row["accession"] else
                       "SEARCH_EARLIER_ORIGINAL_ISSUER_EVIDENCE_WITHOUT_EXCLUDING_SECURITY"), **identity._unknown()})
    for row in db.execute("SELECT s.* FROM source_rows s WHERE EXISTS "
                          "(SELECT 1 FROM retained_names r WHERE r.record=s.record) ORDER BY s.record"):
        roles = [r[0] for r in db.execute("SELECT role FROM retained_names WHERE record=? ORDER BY role", (row["record"],))]
        writers["names_records"].append({**dated._raw_name(row), "source_csv_record": row["record"],
            "source_sha256": source.sha256, "source_inventory_sha256": source.receipt_sha256,
            "retention_roles_json": _json(roles), **identity._unknown()})
    outputs = {name: writer.finish() for name, writer in writers.items()}
    _require(outputs["cohort"]["rows"] == outputs["cohort_summary"]["rows"] == len(cohort)
             and outputs["sec_occurrences"]["rows"] == len(public["rows"]),
             "Output lost a cohort or original SEC occurrence")
    counts.update(cohort_rows=len(cohort), original_sec_occurrences=len(public["rows"]),
                  observation_rows=outputs["observations"]["rows"],
                  header_comparison_rows=outputs["header_comparisons"]["rows"],
                  retained_names_source_records=outputs["names_records"]["rows"],
                  retained_ccm_source_records=outputs["ccm_records"]["rows"],
                  original_relationship_rows=outputs["original_relationships"]["rows"],
                  original_source_followup_rows=outputs["original_source_followup"]["rows"])
    cross_rows = [{"identity_evidence_status": key[0], "observation_status": key[1],
                   "earlier_candidate_header_agreement": key[2], "earlier_candidate_header_disagreement": key[3],
                   "rows": value} for key, value in sorted(crosses.items())]
    return outputs, dict(counts), dict(statuses), cross_rows


def build_sec_ownership_corrob(foundation_directory, identity_directory, names_inventory, *,
                              foundation_receipt_sha256, identity_receipt_sha256, names_receipt_sha256,
                              sec_submission_path, sec_ledger_path, sec_ledger_sha256, sec_collection_receipt_path,
                              output, config, repo_root="."):
    repo = Path(repo_root).resolve()
    verify_lock(config, repo / "configs/protocol.lock.json")
    _require((config["initial_train_start"], config["development_end"], config["holdout_start"]) == (2010, 2021, 2022),
             "Ownership corroboration requires the frozen development design")
    windows = {year: year_start_window(year, config) for year in identity.YEARS}
    window = windows[YEAR]
    public = _load_public(sec_submission_path, sec_ledger_path, sec_ledger_sha256, sec_collection_receipt_path, window)
    out = _private_directory(output, repo)
    bundle, ident, names_spec, tables, annual_names, ccm = _load_private(
        foundation_directory, foundation_receipt_sha256, identity_directory, identity_receipt_sha256, config)
    _require(liquidity._sha(names_receipt_sha256) == names_spec["sha256"],
             "Original Names receipt pin differs from foundation lineage")
    _require(not any(out.is_relative_to(directory) for directory in
                     (bundle.directory, ident.directory, Path(names_inventory).resolve())),
             "Output must be separate from preserved private inputs")
    parts = dated._foundation_tables(bundle)
    cohort, annual_total = _cohort(bundle, parts, ident, tables, windows)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sec-ownership-", dir=out.parent) as temporary:
        work, staged = Path(temporary), Path(temporary) / "bundle"
        staged.mkdir(mode=0o700)
        (staged / "input_receipts").mkdir(mode=0o700)
        source = listing._load_source(names_inventory, staged, config)
        _require(source.receipt_sha256 == names_receipt_sha256
                 and source.receipt_identity[2] == names_spec["bytes"], "Original Names inventory binding differs")
        snapshots = [liquidity._save_bytes(staged, "input_receipts/foundation.json", bundle.raw),
                     liquidity._save_bytes(staged, "input_receipts/identity.json", ident.raw),
                     liquidity._save_bytes(staged, "input_receipts/sec_ledger.json", public["ledger_raw"]),
                     liquidity._save_bytes(staged, "input_receipts/sec_collection.json", public["collection_raw"]),
                     liquidity._save_bytes(staged, "original_SUBMISSION.tsv", public["raw"]),
                     {"file": "input_receipts/names.json", "sha256": source.receipt_sha256, "bytes": source.receipt_identity[2]}]
        with closing(sqlite3.connect(work / "evidence.sqlite3")) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA cache_size=-16384")
            db.execute("PRAGMA temp_store=FILE")
            db.execute("CREATE TABLE source_rows(record INTEGER PRIMARY KEY,permno TEXT,info_start TEXT,"
                       "info_end TEXT,life_start TEXT,life_end TEXT,payload TEXT)")
            preflight = listing._date_preflight(source, db)
            foundation._index_sources(db, ident, tables, annual_names, ccm, windows)
            # The copied annual descriptors must reproduce the actual original CSV values.
            for row in foundation._rows(ident, tables["names_evidence"], listing.CANDIDATE_SCHEMA.names):
                original = db.execute("SELECT payload FROM source_rows WHERE record=?", (row["source_csv_record"],)).fetchone()
                _require(original is not None and dated._raw_name(original) == {field: row[field] for field in NAMES_FIELDS},
                         "Annual descriptor differs from the complete original Names source")
            by_key, context = _index_full_names(db, cohort)
            outputs, counts, statuses, crosses = _emit(
                db, cohort, context, by_key, ident, tables, public, source, staged)
        listing._guard(source, rehash=True)
        liquidity._guard([bundle, ident], rehash=True)
        foundation.sec._guard(public["guards"])
        counts.update(original_names_source_rows_checked=preflight["rows"], all_2020_foundation_rows=annual_total)
        receipt = {"schema_version": 1, "status": STATUS, "created_at": datetime.now(timezone.utc).isoformat(),
            "protocol_sha256": canonical_hash(config), "cohort_year": YEAR, "source_quarter": "2019Q4",
            "selection_asof": window["selection_asof"], "information_cutoff": window["information_cutoff"],
            "inputs": {"foundation_receipt_sha256": bundle.sha256, "identity_receipt_sha256": ident.sha256,
                       "names_inventory_sha256": source.receipt_sha256, "names_source_sha256": source.sha256,
                       "sec_submission_sha256": public["sha256"], "sec_ledger_sha256": public["ledger_sha256"],
                       "sec_collection_receipt_sha256": public["collection_sha256"],
                       "sec_archive_declared_sha256": public["archive_sha256"]},
            "input_receipts": snapshots, "tables": outputs, "counts": counts, "names_preflight": preflight,
            "sec_cutoff_date_counts": public["cutoff_counts"], "sec_symbol_status_counts": public["symbol_status_counts"],
            "cohort_status_counts": statuses, "identity_status_cross_tabulation": crosses,
            "normalization_code_sha256": _hash(Path(__file__)),
            "policies": {"cohort": "all exact raw security/year rows already rank-eligible in the pinned 2020 foundation; no issuer grouping or top-500 selection",
                "literal_matching": "exact SEC symbol equality to ticker and tradingsymbol at inclusive SecInfo dates; both field hits retained once per SEC/Names occurrence",
                "global_collisions": "all original Names records, including noncohort securities and all same-security descriptors at each filing date",
                "placeholder_casefold_for_flags_only": list(_PLACEHOLDERS),
                "raw_identifiers": "comparison-key aliases remain explicit and cannot qualify as unambiguous exact literal observations",
                "duplicates": "all original SEC and Names occurrences retained; repeated evidence is never a vote",
                "clock": "FILING_DATE strictly before cutoff calendar day is an earlier reported filing-date observation only; cutoff-day clocks remain unknown",
                "report_period": "PERIOD_OF_REPORT and DATE_OF_ORIG_SUB retained literally, never used as filing or availability dates",
                "security_lifetime": "diagnostic only; does not extend SecInfo descriptor bounds",
                "header_comparison": "all original CCM relationships retained; header CIK agreement is a text comparison, not an approved historical mapping",
                "absence": "no observation in one quarter never excludes a cohort security"},
            "all_cohort_rows_retained": True, "all_original_sec_occurrences_retained": True,
            "original_names_csv_reread": True, "original_ownership_xml_or_headers_read": False,
            "sec_archive_body_reread": False, "daily_market_files_opened": False, "market_outcomes_read": False,
            "liquidity_mean_or_rank_values_read": False, "existing_rank_eligibility_boolean_read": True,
            "historical_cik_links_created": 0, "source_approvals": 0, "human_reviews_created": 0,
            "known_at_inferred": False, "available_at_inferred": False, "historical_effective_intervals_inferred": False,
            "model_ready": False, "prior_arithmetic_review_modified": False, "final_period_opened": False}
        for spec in [*snapshots, *[part for table in outputs.values() for part in table["parts"]]]:
            path = staged / spec["file"]
            _require(path.stat().st_size == spec["bytes"] and _hash(path) == spec["sha256"],
                     "Output evidence changed before publication")
        liquidity._save_bytes(staged, "receipt.json", (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
        liquidity._save_bytes(staged, "aggregate.json", (json.dumps(aggregate_summary(receipt), indent=2, sort_keys=True) + "\n").encode())
        _require(not out.exists(), "Output appeared during construction; preserved evidence cannot be overwritten")
        staged.rename(out)
    return receipt


def aggregate_summary(receipt):
    keys = ("schema_version", "status", "protocol_sha256", "cohort_year", "source_quarter", "selection_asof",
            "information_cutoff", "inputs", "counts", "sec_cutoff_date_counts", "sec_symbol_status_counts",
            "cohort_status_counts", "identity_status_cross_tabulation", "policies",
            "all_cohort_rows_retained", "all_original_sec_occurrences_retained", "original_names_csv_reread",
            "original_ownership_xml_or_headers_read", "sec_archive_body_reread", "daily_market_files_opened",
            "market_outcomes_read", "liquidity_mean_or_rank_values_read", "existing_rank_eligibility_boolean_read",
            "historical_cik_links_created", "source_approvals", "human_reviews_created", "known_at_inferred",
            "available_at_inferred", "historical_effective_intervals_inferred", "model_ready",
            "prior_arithmetic_review_modified", "final_period_opened")
    return {key: receipt[key] for key in keys}
