"""Preserve and inventory manual Names/CCM metadata without normalizing it.

Only aggregates leave the private copy. Finite date intervals can be counted
against a requested window; B/E/blank/other bounds retain unresolved meaning.
Exact duplicates, historical-key variants, and interval overlap candidates are
separate observations, never an identity or information-availability approval.
"""

import csv
import gzip
import io
import json
import re
import sqlite3
import tempfile
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .manual_wrds_intake import _copy_source, _hash, _identity, _iso, _private_directory
from .market_data import development_return_end
from .protocol import canonical_hash, verify_lock

NAMES_FIELDS = tuple("""permno hdrprimaryexch nasdissuno hdrsiccd permco
    secinfostartdt secinfoenddt securitybegdt securityenddt cusip ticker issuernm
    shareclass usincflg issuertype securitytype securitysubtype sharetype
    securityactiveflg siccd primaryexch tradingsymbol naics tradingstatusflg""".split())
CCM_FIELDS = tuple("gvkey liid linkprim linktype lpermno lpermco linkdt linkenddt cik conm tic cusip".split())
SCHEMAS = {"names": NAMES_FIELDS, "ccm": CCM_FIELDS}
INTERVALS = {"names": (("secinfostartdt", "secinfoenddt"), ("securitybegdt", "securityenddt")),
             "ccm": (("linkdt", "linkenddt"),)}
HISTORICAL_KEYS = {"names": ("permno", "secinfostartdt", "secinfoenddt"),
                   "ccm": ("gvkey", "liid", "linkdt", "linkenddt", "lpermno")}
OVERLAP_GROUPS = {"names": ("permno",), "ccm": ("gvkey", "liid")}
BOUND_KINDS = ("finite_iso_date", "blank", "literal_B", "literal_E", "other_or_invalid")
INTERVAL_KINDS = ("finite_requested_overlap", "finite_before_request", "finite_after_request",
                  "reversed_finite_bounds", "unresolved_nonfinite_bounds")
_BATCH = 5000
_MAX_BATCH_BYTES = 8 * 1024 * 1024
_MAX_SQL_BYTES = 1024 * 1024
_IDENTIFIER = r"[A-Za-z_][A-Za-z_0-9]{0,127}"
_KNOWN_SQL_SOURCES = {
    "names": {"crsp_a_stock.wrds_names_query"},
    "ccm": {"crsp_a_ccm.ccmxpf_lnkhist", "crsp.ccmxpf_lnkhist"},
}


def _raw_tuple(values):
    return json.dumps(values, ensure_ascii=True, separators=(",", ":"))


@contextmanager
def _metadata_rows(path: Path, role: str):
    with path.open("rb") as raw:
        compressed = raw.read(2) == b"\x1f\x8b"
        raw.seek(0)
        binary = gzip.GzipFile(fileobj=raw) if compressed else raw
        with io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as text:
            reader = csv.reader(text, strict=True)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise ValueError("Metadata source is empty; a header is required") from exc
            canonical = [field.lower() for field in header]
            if len(set(canonical)) != len(canonical):
                raise ValueError("Metadata source has ambiguous duplicate headers")
            if (not 1 <= len(header) <= 256 or
                    not all(re.fullmatch(_IDENTIFIER, field) for field in header)):
                raise ValueError("Metadata headers must be at most 256 plain field names")
            if set(SCHEMAS[role]) - set(canonical):
                raise ValueError("Metadata source is missing required fields for its declared role")
            if role == "names" and len(canonical) != len(NAMES_FIELDS):
                raise ValueError("Names inventory requires its exact 24-field schema")

            def checked():
                for record_number, row in enumerate(reader, start=2):
                    if len(row) != len(header):
                        raise ValueError(f"Metadata CSV record {record_number} has the wrong field count")
                    yield row

            yield header, canonical, checked()


def _bound_kind(value: str) -> str:
    if not value.strip():
        return "blank"
    if value in ("B", "E"):
        return "literal_" + value
    try:
        _iso(value, "Metadata date bound")
    except ValueError:
        return "other_or_invalid"
    return "finite_iso_date"


def _interval_kind(left: str, right: str, start: str, end: str) -> str:
    if _bound_kind(left) != "finite_iso_date" or _bound_kind(right) != "finite_iso_date":
        return "unresolved_nonfinite_bounds"
    if left > right:
        return "reversed_finite_bounds"
    if right < start:
        return "finite_before_request"
    if left > end:
        return "finite_after_request"
    return "finite_requested_overlap"


def _unsupported_sql(reason: str) -> dict:
    return {"status": "unsupported", "reason": reason, "source_identifier_from_sql": None,
            "projection_matches_delivered_order": None, "syntactic_scope": None,
            "sql_executed": False, "vendor_execution_verified": False,
            "vendor_vintage_verified": False, "source_completeness_verified": False}


def analyze_metadata_sql(text: str, role: str, columns: list[str]) -> dict:
    """Recognize only a narrow SELECT shape; never execute supplied SQL.

    Supported: explicit fields from one known source, optional WHERE 1=1 and
    optional ordering by those fields. Joins, filters, aliases, expressions,
    comments, multiple statements, and unknown sources remain unsupported.
    A recognized query still does not establish that WRDS executed it.
    """
    if role not in SCHEMAS:
        return _unsupported_sql("unknown_role")
    text = text.strip()
    if text.endswith(";"):
        text = text[:-1].rstrip()
    if not text or len(text.encode("utf-8")) > _MAX_SQL_BYTES:
        return _unsupported_sql("empty_or_oversized_sql")
    match = re.fullmatch(
        rf"SELECT\s+(.+?)\s+FROM\s+({_IDENTIFIER}\.{_IDENTIFIER})(?:\s+(.*))?",
        text, flags=re.I | re.S)
    if not match:
        return _unsupported_sql("unrecognized_select_shape")
    projection, source, suffix = match.groups()
    source = source.lower()
    if source not in _KNOWN_SQL_SOURCES[role]:
        return _unsupported_sql("unrecognized_source_identifier")

    def selected_field(token):
        token = token.strip()
        if not re.fullmatch(rf"{_IDENTIFIER}(?:\.{_IDENTIFIER}){{0,2}}", token):
            return None
        parts = token.lower().split(".")
        if len(parts) > 1 and ".".join(parts[:-1]) not in (source, source.split(".")[1]):
            return None
        return parts[-1]

    fields = [selected_field(token) for token in projection.split(",")]
    if any(field is None for field in fields) or len(set(fields)) != len(fields):
        return _unsupported_sql("unrecognized_or_ambiguous_projection")
    if fields != [field.lower() for field in columns]:
        return _unsupported_sql("projection_does_not_match_delivered_column_order")
    suffix_match = re.fullmatch(
        r"(?:(?:WHERE\s+(?:1\s*=\s*1|\(\s*1\s*=\s*1\s*\)))\s*)?"
        r"(?:ORDER\s+BY\s+(.+))?", (suffix or "").strip(), flags=re.I | re.S)
    if not suffix_match:
        return _unsupported_sql("unrecognized_scope_or_trailing_statements")
    ordering = suffix_match.group(1)
    if ordering:
        for token in ordering.split(","):
            token = re.sub(r"\s+(?:ASC|DESC)$", "", token.strip(), flags=re.I)
            if selected_field(token) not in fields:
                return _unsupported_sql("unrecognized_ordering")
    return {"status": "recognized_restricted_select", "reason": None,
            "source_identifier_from_sql": source, "projection_matches_delivered_order": True,
            "syntactic_scope": "unrestricted_single_source_select",
            "sql_executed": False, "vendor_execution_verified": False,
            "vendor_vintage_verified": False, "source_completeness_verified": False}


def _preserve_sql(sql_source, out: Path, role: str, columns: list[str]):
    result = {"provided": sql_source is not None, "preserved_file": None, "sha256": None,
              "bytes": None, "analysis": _unsupported_sql("not_supplied")}
    if sql_source is None:
        result["analysis"]["status"] = "not_supplied"
        return result, None
    pending = out / "query.pending"
    try:
        original = Path(sql_source).resolve(strict=True)
        digest, byte_count = _copy_source(original, pending)
        snapshot = pending.rename(out / "query.sql")
        identity = _identity(snapshot)
        with snapshot.open("rb") as handle:
            raw = handle.read(_MAX_SQL_BYTES + 1)
        if len(raw) > _MAX_SQL_BYTES:
            analysis = _unsupported_sql("oversized_sql_preserved_without_analysis")
        else:
            try:
                analysis = analyze_metadata_sql(raw.decode("utf-8-sig"), role, columns)
            except UnicodeDecodeError:
                analysis = _unsupported_sql("sql_encoding_unsupported")
        if _identity(snapshot) != identity or _hash(snapshot) != digest:
            raise ValueError("SQL snapshot changed")
        result.update(preserved_file="query.sql", sha256=digest, bytes=byte_count, analysis=analysis)
        return result, (snapshot, identity, digest)
    except (OSError, ValueError):
        # The metadata's raw-byte preservation is independent of an unavailable
        # or unstable optional SQL attachment. Do not print attachment text/path.
        result["analysis"] = _unsupported_sql("sql_unavailable_or_copy_integrity_failed")
        return result, None


def _duplicate_counts(db, requested=False) -> dict:
    where = "WHERE interval_kind='finite_requested_overlap'" if requested else ""
    rows, projections = db.execute(
        f"SELECT COALESCE(SUM(n),0), COUNT(*) FROM projections {where}").fetchone()
    keys, duplicates, conflicts, conflict_rows = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(records>1),0), COALESCE(SUM(variants>1),0), "
        "COALESCE(SUM(CASE WHEN variants>1 THEN records ELSE 0 END),0) FROM "
        f"(SELECT SUM(n) records, COUNT(*) variants FROM projections {where} GROUP BY historical_key)"
    ).fetchone()
    return {"rows": rows, "distinct_full_rows": projections,
            "exact_full_duplicate_row_excess": rows - projections,
            "distinct_historical_keys": keys, "duplicate_historical_keys": duplicates,
            "duplicate_historical_key_row_excess": rows - keys,
            "historical_keys_with_conflicting_full_rows": conflicts,
            "rows_in_conflicting_historical_keys": conflict_rows}


def _overlap_counts(db) -> dict:
    total = candidates = candidate_groups = multi_projection_intervals = 0
    ambiguous_groups = same_interval_variant_groups = 0
    previous_group = maximum_end = None
    group_has_candidate = group_has_variants = group_is_ambiguous = False
    query = ("SELECT overlap_group, first_bound, last_bound, COUNT(*) FROM projections "
             "WHERE interval_kind IN ('finite_requested_overlap','finite_before_request',"
             "'finite_after_request') GROUP BY overlap_group, first_bound, last_bound "
             "ORDER BY overlap_group, first_bound, last_bound")
    for group, start, end, variants in db.execute(query):
        total += 1
        multi_projection_intervals += variants > 1
        if group != previous_group:
            maximum_end = None
            group_has_candidate = group_has_variants = group_is_ambiguous = False
        overlaps_previous = maximum_end is not None and start <= maximum_end
        if overlaps_previous:
            candidates += 1
            if not group_has_candidate:
                candidate_groups += 1
                group_has_candidate = True
        if variants > 1 and not group_has_variants:
            same_interval_variant_groups += 1
            group_has_variants = True
        if (overlaps_previous or variants > 1) and not group_is_ambiguous:
            ambiguous_groups += 1
            group_is_ambiguous = True
        maximum_end = end if maximum_end is None else max(maximum_end, end)
        previous_group = group
    unresolved_rows, unresolved_groups = db.execute(
        "SELECT COALESCE(SUM(n),0), COUNT(DISTINCT overlap_group) FROM projections "
        "WHERE interval_kind IN ('unresolved_nonfinite_bounds','reversed_finite_bounds')"
    ).fetchone()
    return {"distinct_finite_intervals": total,
            "finite_intervals_overlapping_an_earlier_distinct_interval": candidates,
            "groups_with_finite_overlap_candidates": candidate_groups,
            "finite_intervals_with_multiple_distinct_full_rows": multi_projection_intervals,
            "groups_with_multiple_full_rows_on_identical_finite_bounds": same_interval_variant_groups,
            "groups_with_any_finite_interval_ambiguity": ambiguous_groups,
            "rows_with_unresolved_or_reversed_bounds": unresolved_rows,
            "groups_with_unresolved_or_reversed_bounds": unresolved_groups,
            "overlap_comparison": "inclusive endpoints; distinct intervals in the declared group",
            "counts_are_pair_counts": False, "source_interval_semantics_verified": False,
            "overlap_candidates_resolved": False}


def inventory_metadata(source, *, role: str, request_start: str, request_end: str,
                       output, config: dict, repo_root=".", sql_source=None) -> dict:
    """Preserve complete historical metadata and inventory its development overlap."""
    if role not in SCHEMAS:
        raise ValueError("Metadata role must be names or ccm")
    verify_lock(config, Path(repo_root) / "configs" / "protocol.lock.json")
    start, end = _iso(request_start, "Request start"), _iso(request_end, "Request end")
    if start > end or end > development_return_end(config):
        raise ValueError("Requested overlap must be ordered and inside the development return window")
    out = _private_directory(output, repo_root)
    original = Path(source).resolve(strict=True)
    if not original.is_file():
        raise ValueError("Metadata source must be an existing regular file")
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    snapshot = out / "source.bin"
    digest, byte_count = _copy_source(original, snapshot)
    with snapshot.open("rb") as handle:
        compressed = handle.read(2) == b"\x1f\x8b"
    snapshot = snapshot.rename(out / ("source.csv.gz" if compressed else "source.csv"))
    identity = _identity(snapshot)

    def guard_snapshot():
        if _identity(snapshot) != identity or _hash(snapshot) != digest:
            raise ValueError("Metadata snapshot changed; no inventory receipt may be issued")

    guard_snapshot()
    with tempfile.TemporaryDirectory(prefix="metadata-inventory-", dir=out) as temporary:
        with closing(sqlite3.connect(str(Path(temporary) / "inventory.sqlite3"))) as db:
            db.execute("PRAGMA cache_size=-16384")
            db.execute("PRAGMA temp_store=FILE")
            db.execute("CREATE TABLE projections(historical_key TEXT, payload TEXT, overlap_group TEXT, "
                       "first_bound TEXT, last_bound TEXT, interval_kind TEXT, n INTEGER NOT NULL, "
                       "PRIMARY KEY(historical_key,payload)) WITHOUT ROWID")
            with _metadata_rows(snapshot, role) as (header, canonical, records):
                columns = {field: {"blank": 0, "nonblank": 0} for field in canonical}
                bound_fields = [field for pair in INTERVALS[role] for field in pair]
                bounds = {field: {**dict.fromkeys(BOUND_KINDS, 0), "first_finite_date": None,
                                  "last_finite_date": None} for field in bound_fields}
                intervals = {left + "/" + right: dict.fromkeys(INTERVAL_KINDS, 0)
                             for left, right in INTERVALS[role]}
                rows, batch, batch_bytes = 0, [], 0
                indices = {field: canonical.index(field) for field in SCHEMAS[role]}

                def flush():
                    nonlocal batch_bytes
                    db.executemany("INSERT INTO projections VALUES (?,?,?,?,?,?,1) "
                                   "ON CONFLICT(historical_key,payload) DO UPDATE SET n=n+1", batch)
                    db.commit()
                    batch.clear()
                    batch_bytes = 0

                for row in records:
                    for field, value in zip(canonical, row, strict=True):
                        columns[field]["blank" if not value.strip() else "nonblank"] += 1
                    for field in bound_fields:
                        value = row[indices[field]]
                        kind = _bound_kind(value)
                        bounds[field][kind] += 1
                        if kind == "finite_iso_date":
                            first, last = bounds[field]["first_finite_date"], bounds[field]["last_finite_date"]
                            bounds[field]["first_finite_date"] = value if first is None else min(first, value)
                            bounds[field]["last_finite_date"] = value if last is None else max(last, value)
                    primary_kind = None
                    for left, right in INTERVALS[role]:
                        kind = _interval_kind(row[indices[left]], row[indices[right]], start, end)
                        intervals[left + "/" + right][kind] += 1
                        if primary_kind is None:
                            primary_kind = kind
                    left, right = INTERVALS[role][0]
                    historical = [row[indices[field]] for field in HISTORICAL_KEYS[role]]
                    group = [row[indices[field]] for field in OVERLAP_GROUPS[role]]
                    entry = (_raw_tuple(historical), _raw_tuple(row), _raw_tuple(group), row[indices[left]],
                             row[indices[right]], primary_kind)
                    batch.append(entry)
                    batch_bytes += sum(len(value) for value in entry)
                    rows += 1
                    if len(batch) == _BATCH or batch_bytes >= _MAX_BATCH_BYTES:
                        flush()
                flush()
                if not rows:
                    raise ValueError("Metadata source contains no data records")
            guard_snapshot()
            all_rows = _duplicate_counts(db)
            requested = _duplicate_counts(db, requested=True)
            overlaps = _overlap_counts(db)

    sql, sql_guard = _preserve_sql(sql_source, out, role, canonical)
    guard_snapshot()
    if sql_guard is not None:
        sql_path, sql_identity, sql_digest = sql_guard
        if _identity(sql_path) != sql_identity or _hash(sql_path) != sql_digest:
            sql = {"provided": True, "preserved_file": None, "sha256": None, "bytes": None,
                   "analysis": _unsupported_sql("sql_snapshot_changed_after_analysis")}
    receipt = {
        "schema_version": 1, "role": role,
        "status": "RAW_MANUAL_WRDS_METADATA_INVENTORY_NOT_SOURCE_APPROVED",
        "created_at": datetime.now(timezone.utc).isoformat(), "protocol_sha256": canonical_hash(config),
        "source": {"preserved_file": snapshot.name, "sha256": digest, "bytes": byte_count,
                   "compression": "gzip" if compressed else "none", "observed_header": header,
                   "required_column_count": len(SCHEMAS[role]), "delivered_column_count": len(header),
                   "source_release": None, "release_evidence": None,
                   "vendor_query_submitted_at": None, "vendor_query_completed_at": None,
                   "vendor_downloaded_at": None, "vendor_execution_verified": False,
                   "all_securities_query_verified": False},
        "request": {"start": start, "end": end, "bounds_are_caller_declarations": True,
                    "complete_source_history_preserved": True,
                    "finite_metadata_bounds_after_development_are_permitted": True},
        "all_rows": all_rows, "definite_requested_overlap": requested,
        "columns": columns, "date_bounds": bounds, "interval_classifications": intervals,
        "historical_key_fields": list(HISTORICAL_KEYS[role]),
        "interval_overlap_group_fields": list(OVERLAP_GROUPS[role]),
        "interval_overlap_candidates": overlaps, "sql": sql,
        "full_row_equality": "exact parsed text in the preserved delivered column order, including extra fields",
        "historical_key_meaning": "raw grouping for inventory only; not an approved entity mapping",
        "bounds_policy": "B, E, blanks and other text retained literally; no infinite dates assigned",
        "requested_overlap_policy": "finite, nonreversed primary intervals only; unresolved bounds remain separate",
        "source_completeness_verified": False, "source_information_availability_verified": False,
        "rows_dropped": 0, "values_filled": 0, "values_normalized": 0,
        "model_ready": False, "source_approvals": 0,
        "prior_arithmetic_review_modified": False,
    }
    with (out / "receipt.json").open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, allow_nan=False)
        handle.write("\n")
    (out / "receipt.json").chmod(0o600)
    return receipt
