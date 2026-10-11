"""Bind a small saved benchmark audit to observed, unapproved query evidence.

The full source comparison is not rerun. No original CSV or source-stage
Parquet is opened, and no SQL, screenshot, or vendor correspondence is executed.
"""

import hashlib
import json
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from itertools import zip_longest
from pathlib import Path

import pyarrow.parquet as pq

from . import manual_wrds_benchmark_audit as audit
from .manual_wrds_candidates import STAGE_STATUS, _inside
from .manual_wrds_intake import DAILY_FIELDS, _copy_source, _hash, _identity, _iso, _private_directory
from .manual_wrds_stage import _read_receipt
from .market_data import development_return_end
from .protocol import canonical_hash, verify_lock
from .universe import year_start_window

STATUS = "PRIVATE_BENCHMARK_SOURCE_EVIDENCE_PACKET_NOT_SOURCE_APPROVED"
_MAX_TABLE_BYTES = 64 * 1024 * 1024
_MAX_ROWS = 100_000
_MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
_MAX_DOCUMENT_TOTAL = 256 * 1024 * 1024
_MAX_SQL_BYTES = 1024 * 1024
_BATCH = 1024
_MAX_BATCH_BYTES = 8 * 1024 * 1024
_MISMATCH_COUNTS = (
    "numeric_mismatch_rows", "mismatch_dates", "mismatching_date_source_pairs",
    "mismatching_raw_text_groups", "positive_difference_dates", "negative_difference_dates",
    "positive_difference_daily_rows", "negative_difference_daily_rows",
)
_COUNT_KEYS = (*_MISMATCH_COUNTS, "compared_daily_rows", "exact_text_equal_rows", "numeric_equal_rows",
               "numeric_equal_text_different_rows", "daily_dates_with_distinct_raw_texts")
_RECON_KEYS = {"exact_observed_benchmark_values_equal", "requested_window_numerically_reconciled",
               "upstream_requested_window_numerically_reconciled", "source_discrepancy_explained",
               "tolerance_acceptance_used", "fallback_used", "source_replacement_used"}
_META = ["date", "daily_source_sha256", "daily_inventory_receipt_sha256", "market_source_sha256",
         "market_inventory_receipt_sha256", "market_source_csv_record", "daily_rows_affected"]


def _integer(value, minimum=0, maximum=2**63 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Evidence count is not a bounded integer")
    return value


def _sha(value):
    if not isinstance(value, str) or not audit._SHA.fullmatch(value):
        raise ValueError("Evidence binding requires a SHA-256 hash")
    return value


def _track(guards, root, name, identity, digest):
    path = _inside(root, name)
    binding = (root, name, identity, digest)
    if path in guards and guards[path] != binding:
        raise ValueError("An evidence input changed between reads")
    guards[path] = binding
    return path


def _json(root, name, guards, expected=None):
    if not isinstance(name, str) or Path(name).suffix.lower() != ".json":
        raise ValueError("Evidence receipts must be JSON documents, never original data files")
    path = _inside(root, name)
    value, raw, identity = _read_receipt(path)
    digest = hashlib.sha256(raw).hexdigest()
    if expected is not None and digest != _sha(expected):
        raise ValueError("Evidence receipt hash does not match its required binding")
    _track(guards, root, name, identity, digest)
    return value, path, digest


def _file(root, specification, guards, maximum):
    path = _inside(root, specification["file"])
    identity = _identity(path)
    size = _integer(specification["bytes"], maximum=maximum)
    digest = _sha(specification["sha256"])
    if size != identity[2] or _hash(path) != digest or _identity(path) != identity:
        raise ValueError("Evidence file size or hash disagrees with its declaration")
    return _track(guards, root, specification["file"], identity, digest)


def _guard(guards, *, rehash=False):
    for path, (root, name, identity, digest) in guards.items():
        if _inside(root, name) != path or _identity(path) != identity:
            raise ValueError("An evidence input changed during packet construction")
        if rehash and (_hash(path) != digest or _identity(path) != identity):
            raise ValueError("An evidence input hash changed during packet construction")


def _contract(receipt, status, protocol, *, final=True):
    if (type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1
            or receipt.get("status") != status or receipt.get("protocol_sha256") != protocol
            or receipt.get("model_ready") is not False
            or (final and (receipt.get("final_period_opened") is not False
                           or _integer(receipt.get("source_approvals")) != 0))):
        raise ValueError("Evidence receipt contradicts the frozen unapproved contract")
    for field in ("source_approvals", "human_approvals"):
        if field in receipt and _integer(receipt[field]) != 0:
            raise ValueError("Evidence must not supply or fabricate an approval")
    if receipt.get("prior_arithmetic_review_modified", False) is not False:
        raise ValueError("Evidence must preserve the prior arithmetic review")


def _inputs(directory, expected_hash, config, guards):
    protocol = canonical_hash(config)
    receipt, receipt_path, digest = _json(directory, "receipt.json", guards, expected_hash)
    _contract(receipt, audit.STATUS, protocol)
    for field in ("original_sources_modified", "approved_returns_created"):
        if receipt.get(field) is not False:
            raise ValueError("Audit cannot modify original sources or approve returns")
    if any(_integer(receipt[field]) != 0 for field in ("values_filled", "values_replaced")):
        raise ValueError("Audit contains an unsupported source alteration")
    stage, stage_path, _ = _json(directory, receipt["source_stage_receipt_snapshot"], guards,
                               receipt["source_stage_receipt_sha256"])
    _contract(stage, STAGE_STATUS, protocol)
    request = receipt["request"]
    start, end = _iso(request["start"], "Request start"), _iso(request["end"], "Request end")
    limit = development_return_end(config)
    if (request != stage["request"] or start > end or end > limit
            or start < year_start_window(2010, config)["liquidity_start"]
            or request["last_permitted_development_return_date"] != limit):
        raise ValueError("Audit request exceeds the frozen development envelope")
    bindings, staged = receipt["sources"], stage["sources"]
    if not isinstance(bindings, list) or not 2 <= len(bindings) <= 65 or len(staged) != len(bindings):
        raise ValueError("Audit source manifest must contain bounded daily and market sources")
    stage_by_hash = {_sha(row["source_sha256"]): row for row in staged}
    if len(stage_by_hash) != len(staged):
        raise ValueError("Source stage repeats an original source hash")
    copies = [(receipt_path, "audit/receipt.json"), (stage_path, "audit/source_stage_receipt.json")]
    sources, roles = {}, Counter()
    for binding in bindings:
        role, source_sha = binding["role"], _sha(binding["source_sha256"])
        inventory_sha = _sha(binding["inventory_receipt_sha256"])
        if role not in {"daily", "market"} or source_sha in sources or source_sha not in stage_by_hash:
            raise ValueError("Audit source role or source hash is unsupported or repeated")
        original = stage_by_hash[source_sha]
        if any(original[field] != binding[field] for field in
               ("role", "inventory_receipt_sha256", "source_bytes", "rows", "requested_rows")):
            raise ValueError("Audit source declaration differs from its stage binding")
        inventory, path, _ = _json(directory, binding["inventory_receipt_snapshot"], guards, inventory_sha)
        status = ("RAW_MANUAL_WRDS_INVENTORY_NOT_AUDIT_APPROVED" if role == "daily"
                  else "RAW_MANUAL_WRDS_MARKET_INVENTORY_NOT_SOURCE_APPROVED")
        _contract(inventory, status, protocol, final=False)
        source = inventory["source"]
        rows = _integer(binding["rows"], 1)
        requested = _integer(binding["requested_rows"], maximum=rows)
        if (source["sha256"] != source_sha or source["bytes"] != _integer(binding["source_bytes"], 1)
                or inventory["all_rows"]["rows"] != rows
                or source["observed_header"] != original["observed_header"]
                or source["preserved_file"] != original["preserved_file"]):
            raise ValueError("Source inventory differs from the audited original binding")
        header = source["observed_header"]
        if (not isinstance(header, list) or not 1 <= len(header) <= 256
                or any(not isinstance(name, str) or not audit._HEADER.fullmatch(name) for name in header)
                or len({name.lower() for name in header}) != len(header)):
            raise ValueError("Observed source header is invalid or ambiguous")
        fields = {name.lower() for name in header}
        if (role == "market" and fields != {"dlycaldt", "vwretd"}) or (
                role == "daily" and not set(DAILY_FIELDS).issubset(fields)):
            raise ValueError("Observed source fields do not support the audited comparison")
        first = _iso(inventory["request"]["start"], "Inventory start")
        last = _iso(inventory["request"]["end"], "Inventory end")
        if first > last or last > limit:
            raise ValueError("Bound inventory request exceeds the development boundary")
        relative = "audit/" + binding["inventory_receipt_snapshot"]
        copies.append((path, relative))
        roles[role] += 1
        sources[source_sha] = {
            "binding": binding, "stage": original, "inventory": inventory,
            "evidence": {"role": role, "source_sha256": source_sha, "inventory_receipt_sha256": inventory_sha,
                         "inventory_receipt_file": relative, "observed_rows": rows,
                         "observed_requested_rows": requested, "observed_header": header,
                         "observed_source_release_declaration": source.get("source_release"),
                         "vendor_release_or_vintage_evidence": None, "vendor_schema_version_evidence": None,
                         "vendor_return_semantics_certified": False, "query_to_csv_byte_binding_certified": False,
                         "source_completeness_verified": False, "sql_file": None,
                         "sql_observation_status": "NOT_RECORDED_IN_BOUND_INVENTORY", "query_observations": []},
        }
    if roles["market"] != 1 or not roles["daily"]:
        raise ValueError("Exactly one independent market source and at least one daily source are required")
    counts = receipt["counts"]
    if set(counts) != set(_COUNT_KEYS) or any(_integer(value) < 0 for value in counts.values()):
        raise ValueError("Audit comparison counts are unsupported")
    if (counts["compared_daily_rows"] != sum(s["binding"]["requested_rows"] for s in sources.values()
                                            if s["binding"]["role"] == "daily")
            or counts["compared_daily_rows"] != stage["projection"]["requested_rows"]
            or counts["compared_daily_rows"] != counts["numeric_equal_rows"] + counts["numeric_mismatch_rows"]
            or counts["numeric_equal_rows"] != counts["exact_text_equal_rows"] + counts["numeric_equal_text_different_rows"]):
        raise ValueError("Audit comparison accounting disagrees with the bound source counts")
    reconciliation = receipt["reconciliation"]
    if set(reconciliation) != _RECON_KEYS or any(type(value) is not bool for value in reconciliation.values()):
        raise ValueError("Audit reconciliation must contain only the supported Boolean declarations")
    for field in ("source_discrepancy_explained", "tolerance_acceptance_used", "fallback_used", "source_replacement_used"):
        if reconciliation.get(field) is not False:
            raise ValueError("Source evidence cannot accept a tolerance or select a replacement")
    equal = counts["numeric_mismatch_rows"] == 0
    complete = all(_integer(receipt["coverage"][role][field]) == 0
                   for role in ("daily_projection", "independent_market")
                   for field in ("missing_expected_sessions", "unexpected_requested_dates"))
    if (reconciliation["exact_observed_benchmark_values_equal"] is not equal
            or reconciliation["requested_window_numerically_reconciled"] is not (equal and complete)
            or reconciliation["upstream_requested_window_numerically_reconciled"]
            != stage["reconciliation"]["requested_window_numerically_reconciled"]):
        raise ValueError("Audit reconciliation state disagrees with its evidence")
    table = receipt["table"]
    if not isinstance(table.get("file"), str) or Path(table["file"]).suffix.lower() != ".parquet":
        raise ValueError("Mismatch evidence must be the saved Parquet table, never an original CSV")
    path = _file(directory, table, guards, _MAX_TABLE_BYTES)
    if (table.get("private_only") is not True or table.get("contains_security_identifiers") is not False
            or _integer(table["rows"], maximum=_MAX_ROWS) != counts["mismatching_raw_text_groups"]):
        raise ValueError("Mismatch table scope is unsupported or unbounded")
    parquet = pq.ParquetFile(path)
    if not parquet.schema_arrow.equals(audit.MISMATCH_SCHEMA, check_metadata=False) or parquet.metadata.num_rows != table["rows"]:
        raise ValueError("Mismatch table schema or row count disagrees with the audit")
    copies.append((path, "audit/mismatches.parquet"))
    return receipt, digest, sources, path, copies


def _sql_sources(sources, repo, guards, copies):
    for index, source in enumerate(sources.values(), 1):
        sql = source["inventory"].get("sql")
        if sql is None:
            continue
        if type(sql.get("provided")) is not bool:
            raise ValueError("SQL evidence declaration is invalid")
        if sql.get("preserved_file") is None:
            source["evidence"]["sql_observation_status"] = "NO_BOUND_SQL_SNAPSHOT"
            continue
        if (sql["provided"] is not True or sql.get("status") != "preserved_without_semantic_interpretation"
                or any(sql.get(field) is not False for field in
                       ("sql_interpreted", "sql_executed", "vendor_execution_verified", "vendor_vintage_verified"))):
            raise ValueError("SQL evidence must remain unexecuted and semantically unverified")
        if not isinstance(sql["preserved_file"], str) or Path(sql["preserved_file"]).suffix.lower() != ".sql":
            raise ValueError("SQL evidence requires a bounded SQL document, never an original data file")
        directory = Path(source["stage"]["inventory_directory"]).resolve(strict=True)
        if not any(directory.is_relative_to(repo / name) for name in ("data", "outputs")):
            raise ValueError("Bound SQL inventory must remain in the repository's private source tree")
        _json(directory, "receipt.json", guards, source["binding"]["inventory_receipt_sha256"])
        path = _file(directory, {"file": sql["preserved_file"], "bytes": sql["bytes"], "sha256": sql["sha256"]},
                     guards, _MAX_SQL_BYTES)
        relative = f"source_documents/source-{index:03d}/query.sql"
        copies.append((path, relative))
        source["evidence"].update(sql_file=relative, sql_sha256=sql["sha256"],
                                  sql_observation_status="PRESERVED_TEXT_ONLY_NOT_PARSED_OR_EXECUTED")


def _query_evidence(directories, sources, guards, copies):
    if len(directories) > 65:
        raise ValueError("Too many query-evidence bundles")
    seen, total = set(), 0
    for index, supplied in enumerate(directories, 1):
        root = Path(supplied).resolve(strict=True)
        observation, observed_path, observed_sha = _json(root, "observation.json", guards)
        reconciliation, reconciled_path, _ = _json(root, "inventory-reconciliation-v1.json", guards)
        if observed_sha in seen:
            raise ValueError("Query observation was supplied more than once")
        seen.add(observed_sha)
        for record in (observation, reconciliation):
            if (type(record.get("schema_version")) is not int or record["schema_version"] != 1
                    or record.get("model_ready") is not False or _integer(record.get("source_approvals")) != 0):
                raise ValueError("Observed query records must not claim readiness or approval")
        source_sha = _sha(reconciliation["preserved_source_sha256"])
        if source_sha not in sources:
            raise ValueError("Query evidence refers to an unaudited source")
        source, association = sources[source_sha], observation["local_inventory_comparison"]
        rows, displayed = source["binding"]["rows"], _integer(observation["displayed_result_rows"])
        if (reconciliation["query_observation_sha256"] != observed_sha
                or reconciliation["inventory_receipt_sha256"] != source["binding"]["inventory_receipt_sha256"]
                or reconciliation["source_inventory_status"] != source["inventory"]["status"]
                or str(_integer(observation["query_id"], 1)) != reconciliation["query_job_id"]
                or association["source_sha256"] != source_sha
                or _integer(association["inventory_rows"]) != rows
                or _integer(reconciliation["inventoried_source_rows"]) != rows
                or _integer(reconciliation["displayed_query_rows"]) != displayed
                or association["rows_match_displayed_result"] is not (rows == displayed)
                or reconciliation["row_counts_equal"] is not (rows == displayed)):
            raise ValueError("Observed query row-count association contradicts its saved source bindings")
        for field in ("method_code_semantics_verified", "source_completeness_verified",
                      "all_securities_selection_verified", "prior_arithmetic_review_modified"):
            if observation.get(field) is not False:
                raise ValueError("A query display cannot supply an unverified source judgment")
        if (observation.get("displayed_times_timezone") is not None
                or observation.get("displayed_times_not_converted_to_utc") is not True):
            raise ValueError("Observed query times must retain their unknown timezone")
        interval = observation["requested_date_range_visible"]
        if _iso(interval["start"], "Observed request start") > _iso(interval["end"], "Observed request end"):
            raise ValueError("Observed query date range is reversed")
        screenshots = observation["screenshots"]
        if not isinstance(screenshots, list) or len(screenshots) > 32:
            raise ValueError("Query screenshot manifest is unbounded")
        prefix = f"query_evidence/observation-{index:03d}/"
        copies.extend([(observed_path, prefix + "observation.json"),
                       (reconciled_path, prefix + "inventory-reconciliation-v1.json")])
        names = set()
        for specification in screenshots:
            name = specification["file"]
            if name in names or Path(name).suffix.lower() not in {".png", ".jpg", ".jpeg", ".pdf"}:
                raise ValueError("Query documents must be unique image/PDF files")
            names.add(name)
            path = _file(root, specification, guards, _MAX_DOCUMENT_BYTES)
            total += specification["bytes"]
            if total > _MAX_DOCUMENT_TOTAL:
                raise ValueError("Query evidence exceeds the bounded private document budget")
            copies.append((path, prefix + name))
        source["evidence"]["query_observations"].append({
            "observation_file": prefix + "observation.json", "observation_sha256": observed_sha,
            "reconciliation_file": prefix + "inventory-reconciliation-v1.json",
            "observed_parameters": observation["observed_parameters"],
            "recorded_association_scope": reconciliation["association_scope"],
            "association_basis": "operator-recorded displayed row-count comparison only",
            "row_counts_equal": rows == displayed, "query_to_csv_byte_binding_certified": False,
            "displayed_times_timezone": None, "screenshots_interpreted_by_packet_builder": False,
            "source_release_verified": False, "vendor_schema_version_verified": False,
        })


def _rows(path, columns=None):
    for batch in pq.ParquetFile(path).iter_batches(batch_size=_BATCH, columns=columns):
        if batch.nbytes > _MAX_BATCH_BYTES or any(column.null_count for column in batch.columns):
            raise ValueError("Mismatch evidence has a null field or exceeds the bounded batch size")
        yield from batch.to_pylist()


def _date_preflight(path, receipt, sources):
    market = next(s["binding"] for s in sources.values() if s["binding"]["role"] == "market")
    dates, ordinals, rows = {}, {}, 0
    for row in _rows(path, _META):
        day = _iso(row["date"], "Mismatch date")
        if not receipt["request"]["start"] <= day <= receipt["request"]["end"]:
            raise ValueError("Mismatch date lies outside the frozen development request")
        source = sources.get(row["daily_source_sha256"])
        if (source is None or source["binding"]["role"] != "daily"
                or row["daily_inventory_receipt_sha256"] != source["binding"]["inventory_receipt_sha256"]
                or row["market_source_sha256"] != market["source_sha256"]
                or row["market_inventory_receipt_sha256"] != market["inventory_receipt_sha256"]):
            raise ValueError("Mismatch source provenance is not bound to the saved audit")
        ordinal = _integer(row["market_source_csv_record"], 2, market["rows"] + 1)
        _integer(row["daily_rows_affected"], 1, source["binding"]["requested_rows"])
        if dates.get(day, ordinal) != ordinal or ordinals.get(ordinal, day) != day:
            raise ValueError("Independent market date and source ordinal are not one-to-one")
        dates[day], ordinals[ordinal] = ordinal, day
        rows += 1
    if rows != receipt["table"]["rows"]:
        raise ValueError("Mismatch row count changed during date preflight")
    return market


def _diagnostics(path, receipt, sources, market, work):
    with closing(sqlite3.connect(str(work / "mismatches.sqlite3"))) as db:
        db.execute("PRAGMA cache_size=-8192")
        db.execute("PRAGMA temp_store=FILE")
        db.execute("CREATE TABLE benchmark_groups(session_date TEXT,source_sha256 TEXT,"
                   "source_inventory_sha256 TEXT,raw_text TEXT,rows INTEGER,"
                   "PRIMARY KEY(session_date,source_sha256,source_inventory_sha256,raw_text)) WITHOUT ROWID")
        db.execute("CREATE TABLE market(day TEXT PRIMARY KEY,value TEXT,record INTEGER UNIQUE) WITHOUT ROWID")
        previous = None
        for row in _rows(path):
            for field in ("daily_raw_text", "market_raw_text"):
                if len(row[field]) > audit._MAX_TEXT:
                    raise ValueError("Mismatch numeric text exceeds the diagnostic bound")
            key = tuple(row[field] for field in ("date", "daily_source_sha256", "daily_inventory_receipt_sha256", "daily_raw_text"))
            if previous is not None and key <= previous:
                raise ValueError("Mismatch groups are duplicated or out of audited order")
            previous = key
            db.execute("INSERT INTO benchmark_groups VALUES (?,?,?,?,?)", (*key, row["daily_rows_affected"]))
            value = row["market_raw_text"], row["market_source_csv_record"]
            found = db.execute("SELECT value,record FROM market WHERE day=?", (row["date"],)).fetchone()
            if found is None:
                db.execute("INSERT INTO market VALUES (?,?,?)", (row["date"], *value))
            elif found != value:
                raise ValueError("Mismatch rows disagree on an independent market observation")
        db.commit()
        computed_path = work / "recomputed.parquet"
        result = audit._compare(db, db, {"binding": market}, computed_path,
                                [source["binding"] for source in sources.values()])
    for original, computed in zip_longest(_rows(path), _rows(computed_path)):
        if original != computed:
            raise ValueError("Saved mismatch detail contradicts exact Decimal recomputation")
    if any(result["counts"][key] != receipt["counts"][key] for key in _MISMATCH_COUNTS):
        raise ValueError("Saved audit mismatch counts disagree with the complete private detail")
    for field in ("mismatches_by_year", "mismatches_by_source_sha256", "exact_difference", "rounding_diagnostics"):
        if result[field] != receipt[field]:
            raise ValueError("Saved audit diagnostics disagree with exact recomputation")
    return result


def _destination(bundle, name):
    path = bundle
    for part in Path(name).parts[:-1]:
        path /= part
        path.mkdir(mode=0o700, exist_ok=True)
    return bundle / name


def _write(bundle, name, raw):
    audit._snapshot(_destination(bundle, name), raw)
    return {"file": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _vendor_question(summary):
    count = summary["audit_counts"]["mismatch_dates"]
    minimum, maximum = (summary["exact_difference"][key] for key in ("minimum_absolute", "maximum_absolute"))
    return (
        "# Unsent vendor question draft\n\n"
        "Status: DRAFT — NOT SENT. No recipient is selected and no attachments are transmitted.\n\n"
        "We are reconciling the vwretd field appended to a CIZ daily stock export with a separately "
        f"downloaded daily market-index export. The saved audit identifies {count} discrepant dates; "
        f"the absolute exact-decimal differences range from {minimum} to {maximum}. Original source "
        "bytes and the complete private discrepancy detail are preserved.\n\n"
        "1. For the specific saved query outputs, do vwretd in wrds_dsfv2_query and vwretd in "
        "wrds_dailyindexret_query use the same underlying benchmark definition, universe, dividend "
        "treatment, revision vintage and calculation/pass-through path? Please identify the "
        "libraries, source releases and effective schema versions.\n"
        "2. Could the documented output formats, numeric storage types, rounding rules or revisions "
        "produce these exact discrepancies? Please connect any explanation to the actual query "
        "outputs and supplied evidence, rather than to a generic precision rule.\n"
        "3. Which source and reproducible extraction procedure implements the intended value-weighted "
        "total-return benchmark for this study, and what source-bound evidence establishes that? "
        "If a corrected or higher-precision export is necessary, please specify it.\n\n"
        "WRDS's published CIZ beta and event-study macros use a separate daily index view. That "
        "documents its intended role, without certifying these exported files or their vintage. "
        "CRSP's SIZ/CIZ migration explanations do not establish the cause of this comparison.\n\n"
        "References: [WRDS CIZ beta macro](https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/wrds-macros-betas-ciz/), "
        "[WRDS CIZ event-study macro](https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/run-an-event-study-ciz-format-macro/), "
        "[CRSP migration usage](https://www.crsp.org/wp-content/uploads/appendix/FlagType_MU.html).\n\n"
        "The packet's query-display association is based on recorded row counts and source hashes; "
        "it is not vendor-certified query-to-CSV byte provenance. Missing source release, timezone "
        "and schema evidence remain explicit. No tolerance, fallback, source replacement, "
        "source approval or model-readiness decision has been made.\n\n"
        "Private source/query records and licensed per-date values should be shared only through "
        "an authorized channel if needed. This draft contains aggregate discrepancy information only.\n"
    ).encode()


def build_source_evidence(audit_directory, *, audit_receipt_sha256, output, config, repo_root=".", query_evidence=()):
    """Build a hash-pinned packet from small saved evidence; leave every source gate closed."""
    _sha(audit_receipt_sha256)
    repo = Path(repo_root).resolve()
    verify_lock(config, repo / "configs/protocol.lock.json")
    if (config["initial_train_start"], config["development_end"], config["holdout_start"],
            config["liquidity_lookback_sessions"]) != (2010, 2021, 2022, 60):
        raise ValueError("Source evidence requires the frozen development protocol")
    out, root = _private_directory(output, repo), Path(audit_directory).resolve(strict=True)
    guards = {}
    receipt, digest, sources, table, copies = _inputs(root, audit_receipt_sha256, config, guards)
    _sql_sources(sources, repo, guards, copies)
    _query_evidence(list(query_evidence), sources, guards, copies)
    if any(out.is_relative_to(binding[0]) for binding in guards.values()):
        raise ValueError("Evidence packet must be separate from every preserved input bundle")
    market = _date_preflight(table, receipt, sources)
    _guard(guards)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".wrds-benchmark-evidence-", dir=out.parent) as temporary:
        work = Path(temporary)
        result = _diagnostics(table, receipt, sources, market, work)
        bundle = work / "bundle"
        bundle.mkdir(mode=0o700)
        manifest, names = [], set()
        for path, name in copies:
            if name in names:
                raise ValueError("Private evidence destination is listed more than once")
            names.add(name)
            copied_sha, copied_bytes = _copy_source(path, _destination(bundle, name))
            if copied_sha != guards[path][3] or copied_bytes != guards[path][2][2]:
                raise ValueError("Private evidence changed while being copied")
            manifest.append({"file": name, "sha256": copied_sha, "bytes": copied_bytes})
        evidence = [source["evidence"] for source in sources.values()]
        summary = {
            "status": STATUS, "protocol_sha256": canonical_hash(config), "audit_receipt_sha256": digest,
            "audit_counts": receipt["counts"],
            **{key: result[key] for key in ("mismatches_by_year", "mismatches_by_source_sha256", "exact_difference", "rounding_diagnostics")},
            "source_evidence_counts": {
                "daily_sources": sum(row["role"] == "daily" for row in evidence),
                "independent_market_sources": 1, "sources_with_bound_sql": sum(row["sql_file"] is not None for row in evidence),
                "sources_with_query_displays": sum(bool(row["query_observations"]) for row in evidence),
                "sources_without_query_display_evidence": sum(not row["query_observations"] for row in evidence),
                "sources_without_verified_release_or_vintage": len(evidence),
                "sources_without_verified_schema_version": len(evidence),
                "sources_without_vendor_certified_query_to_csv_binding": len(evidence),
            },
            "mismatch_detail_recomputed_exactly": True, "full_daily_comparison_reexecuted": False,
            "raw_source_csv_files_opened": False, "source_stage_parquet_opened": False,
            "query_sql_executed": False, "query_sql_semantics_certified": False,
            "vendor_question_sent": False, "reconciliation": receipt["reconciliation"],
            "model_ready": False, "source_approvals": 0, "prior_arithmetic_review_modified": False,
            "final_period_opened": False,
        }
        manifest.append(_write(bundle, "source_evidence.json", _json_bytes(evidence)))
        manifest.append(_write(bundle, "public_summary.json", _json_bytes(summary)))
        manifest.append(_write(bundle, "vendor_question_draft.md", _vendor_question(summary)))
        _guard(guards, rehash=True)
        for item in manifest:
            path = bundle / item["file"]
            if path.stat().st_size != item["bytes"] or _hash(path) != item["sha256"]:
                raise ValueError("Completed private evidence or aggregate output changed")
        packet = {"schema_version": 1, **summary, "code_sha256": _hash(Path(__file__)),
                  "diagnostic_code_sha256": _hash(Path(audit.__file__)), "files": manifest,
                  "evidence_scope": {
                      "audit_receipt_pinned_by_caller": True, "complete_mismatch_parquet_bytes_preserved": True,
                      "every_audited_source_retained_even_without_mismatches": True,
                      "all_mismatch_dates_checked_before_decimal_interpretation": True,
                      "consumed_evidence_rehashed_before_completion": True,
                      "matching_row_counts_copied_from_bound_audit_not_recomputed": True,
                      "original_csv_and_stage_part_verification_relies_on_upstream_audit": True,
                      "screenshots_preserved_without_ocr_or_semantic_review": True,
                      "no_new_human_or_vendor_review_recorded": True},
                  "processing": {"mismatch_row_limit": _MAX_ROWS, "mismatch_file_byte_limit": _MAX_TABLE_BYTES,
                                 "arrow_batch_rows": _BATCH, "arrow_batch_byte_limit": _MAX_BATCH_BYTES,
                                 "sqlite_cache_kib": 8192, "query_document_total_byte_limit": _MAX_DOCUMENT_TOTAL}}
        _write(bundle, "receipt.json", _json_bytes(packet))
        if out.exists() or _private_directory(out, repo) != out:
            raise ValueError("Evidence output must remain new and private")
        bundle.rename(out)
    return packet


def aggregate_summary(receipt):
    """Return the generated whitelist, never private receipts or query parameters."""
    return {key: receipt[key] for key in (
        "status", "protocol_sha256", "audit_receipt_sha256", "audit_counts", "mismatches_by_year",
        "mismatches_by_source_sha256", "exact_difference", "rounding_diagnostics", "source_evidence_counts",
        "mismatch_detail_recomputed_exactly", "full_daily_comparison_reexecuted", "raw_source_csv_files_opened",
        "source_stage_parquet_opened", "query_sql_executed", "query_sql_semantics_certified", "vendor_question_sent",
        "reconciliation", "model_ready", "source_approvals", "prior_arithmetic_review_modified", "final_period_opened",
    )}
