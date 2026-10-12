"""Cross-check original SEC 10-K filers against 2019Q4 SEC/dated-Names issuer anchors.

Offline and retrospective. A 2019Q4 ownership filing matches one issuer at a
dated security descriptor; it does not make the 2015-2021 security link known
at all filing dates, and does not establish historical source availability.
The exact licensed joins and SEC symbols stay in private, immutable outputs.
"""

import csv
import gzip
import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .protocol import canonical_hash

STATUS = "SEC_2019Q4_PILOT_ISSUER_ANCHORS_NOT_HISTORICAL_LINK_APPROVAL"
MARKET_STATUS = "PROVISIONAL_CANDIDATE_ARITHMETIC_QA"
OWNERSHIP_STATUS = "SEC_OWNERSHIP_ISSUER_OBSERVATIONS_NOT_APPROVED_LINKS"
SEC_STATUS = "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED"
EARLIER = "BEFORE_CUTOFF_DATE"
CUTOFF_UNRESOLVED = "CUTOFF_DAY_TIME_UNRESOLVED"
SHA = re.compile(r"[0-9a-f]{64}")
CIK = re.compile(r"[0-9]{10}")
CANDIDATE_COLUMNS = ("event_id", "cik", "candidate_permno", "acceptance_timestamp",
                     "model_ready", "identity_approved", "open_end_unresolved",
                     "human_pair_review_complete", "qa_status", "data_kind")
RELEVANT_TABLES = (
    "cohort", "cohort_summary", "observations", "names_records",
    "sec_occurrences", "header_comparisons",
)


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _checked_file(path, *, max_bytes):
    raw_path = Path(path)
    _require(not raw_path.is_symlink(), "Symbolic links are not permitted as source files")
    path = raw_path.resolve(strict=True)
    _require(path.is_file() and path.stat().st_size <= max_bytes,
             f"Missing, linked or oversized source: {path.name}")
    return path


def _read_table(root, receipt, name):
    spec = receipt["tables"][name]
    _require(spec.get("parts") and type(spec.get("rows")) is int,
             f"Missing preserved table manifest: {name}")
    parts, paths = [], []
    for index, part in enumerate(spec["parts"], 1):
        relative = part["file"]
        _require(relative == f"{name}/part-{index:06d}.parquet",
                 "Missing/incorrect source Parquet part sequence")
        path = _checked_file(root / relative, max_bytes=64 * 1024 * 1024)
        _require(path.is_relative_to(root.resolve()) and SHA.fullmatch(part["sha256"])
                 and part["sha256"] == _file_hash(path)
                 and part["bytes"] == path.stat().st_size,
                 f"Original source Parquet changed: {name}")
        parquet = pq.ParquetFile(path)
        _require(parquet.metadata.num_rows == part["rows"]
                 and parquet.schema_arrow.names == spec["fields"],
                 f"Source Parquet declared schema/rows changed: {name}")
        parts.append(parquet.read())
        paths.append((path, part["sha256"]))
    table = pa.concat_tables(parts)
    _require(table.num_rows == spec["rows"], f"Source row count changed: {name}")
    return table.to_pandas(), paths


def _integer_key(raw, *, cik=False):
    if not isinstance(raw, str) or not re.fullmatch(r"[0-9]{1,10}" if cik else r"[0-9]{1,20}", raw):
        return None
    n = int(raw)
    if n == 0:
        return None
    return str(n).zfill(10) if cik else str(n)


def _sec_source_rows(path, ordinals, source_digest, expected_rows):
    _require(_file_hash(path) == source_digest, "Original SEC ownership TSV SHA mismatch")
    columns = ["ACCESSION_NUMBER", "FILING_DATE", "PERIOD_OF_REPORT", "DATE_OF_ORIG_SUB",
               "NO_SECURITIES_OWNED", "NOT_SUBJECT_SEC16", "FORM3_HOLDINGS_REPORTED",
               "FORM4_TRANS_REPORTED", "DOCUMENT_TYPE", "ISSUERCIK", "ISSUERNAME",
               "ISSUERTRADINGSYMBOL", "REMARKS"]
    result = {}
    index = 1
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t", restkey="__extra__", strict=True)
        _require(reader.fieldnames == columns, "Original SEC TSV fields unexpectedly changed")
        for index, row in enumerate(reader, start=2):
            _require("__extra__" not in row and None not in row.values(),
                     "Original SEC TSV contains malformed records")
            if index in ordinals:
                result[index] = row
    _require(index == expected_rows + 1, "Original SEC TSV number of source records changed")
    _require(len(result) == len(ordinals), "An original SEC record ordinal was not found")
    return result


def _names_source_rows(path, ordinals, source_digest, expected_rows):
    _require(_file_hash(path) == source_digest, "Original CRSP Names CSV SHA mismatch")
    result = {}
    index = 1
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, restkey="__extra__", strict=True)
        header = reader.fieldnames
        _require(header and len(header) == 24 and len(set(header)) == len(header),
                 "Original CRSP Names schema changed")
        for index, row in enumerate(reader, start=2):
            _require("__extra__" not in row and None not in row.values(),
                     "Original CRSP Names has malformed row")
            if index in ordinals:
                result[index] = row
    _require(index == expected_rows + 1, "Original CRSP Names record count changed")
    _require(len(result) == len(ordinals), "Missing original CRSP Names source record")
    return result, header


def _sec_identity(gzip_path, execution_path, config):
    execution_raw = execution_path.read_bytes()
    _require(len(execution_raw) < 1024 * 1024, "Original SEC source execution record too large")
    execution = json.loads(execution_raw)
    publication = execution["publication"]
    compressed = gzip_path.read_bytes()
    _require(len(compressed) < 8 * 1024 * 1024
             and publication["sha256"] == _sha(compressed)
             and publication["bytes"] == len(compressed), "Original SEC publication checksum changed")
    original = gzip.decompress(compressed)
    _require(len(original) <= 16 * 1024 * 1024
             and publication["uncompressed_sha256"] == _sha(original)
             and publication["uncompressed_bytes"] == len(original),
             "Original SEC source report gzip roundtrip differs from published original")
    report = json.loads(original)
    _require(report["status"] == SEC_STATUS and report["original_sec_bytes_reread"] is True
             and report["protocol_sha256"] == canonical_hash(config)
             and report["source_approvals"] == 0 and report["final_period_opened"] is False
             and report["historical_security_links_created"] == 0
             and execution["source_approvals"] == 0 and execution["final_period_opened"] is False,
             "Original SEC lexical source is not the original, unapproved evidence")
    _require(len(report["records"]) == 215 and
             len({r["accession"] for r in report["records"]}) == 215,
             "SEC original identity evidence record uniqueness changed")
    return {x["accession"]: x for x in report["records"]}, {
        "compressed_sha256": _sha(compressed), "original_sha256": _sha(original),
        "published_execution_sha256": _sha(execution_raw),
        "original_headers_rechecked_here": False,
    }


def run_pilot_anchor(market_candidates, ownership, names_csv, sec_gzip, sec_execution,
                     output, *, config, repo_root, ownership_receipt_sha256,
                     candidate_receipt_sha256):
    """Record exact evidence by identifier, keeping all unapproved statements explicit."""
    root = Path(repo_root).resolve(strict=True)
    out = Path(output).resolve()
    _require(any(out.is_relative_to(root / folder) and out != root / folder
                 for folder in ("data", "outputs")), "Output must be a fresh private directory")
    _require(not out.exists(), "Never overwrite an issuer anchor evidence output")
    market = Path(market_candidates).resolve(strict=True)
    ownership = Path(ownership).resolve(strict=True)
    names_csv = _checked_file(names_csv, max_bytes=256 * 1024 * 1024)
    sec_gzip = _checked_file(sec_gzip, max_bytes=8 * 1024 * 1024)
    sec_execution = _checked_file(sec_execution, max_bytes=1024 * 1024)
    _require(not out.is_relative_to(market) and not out.is_relative_to(ownership)
             and not out.is_relative_to(names_csv.parent)
             and not out.is_relative_to(sec_gzip.parent),
             "Output must not nest inside consumed input locations")
    _require(SHA.fullmatch(ownership_receipt_sha256)
             and SHA.fullmatch(candidate_receipt_sha256),
             "Caller must pin expected existing receipt SHA-256 values")
    candidate_receipt_path = _checked_file(market / "audit_summary.json", max_bytes=200000)
    ownership_receipt_path = _checked_file(ownership / "receipt.json", max_bytes=1000000)
    candidate_receipt_raw = candidate_receipt_path.read_bytes()
    ownership_receipt_raw = ownership_receipt_path.read_bytes()
    _require(_sha(candidate_receipt_raw) == candidate_receipt_sha256
             and _sha(ownership_receipt_raw) == ownership_receipt_sha256,
             "Original source receipts do not match caller's pinned values")
    pilot = json.loads(candidate_receipt_raw)
    owner = json.loads(ownership_receipt_raw)
    protocol_sha = canonical_hash(config)
    _require(pilot.get("data_kind") == MARKET_STATUS and
             pilot["source_hashes"]["protocol"] == protocol_sha
             and pilot["model_ready"] is False and pilot["final_period_opened"] is False
             and pilot["historical_cik_mapping_approved"] is False,
             "Pilot arithmetic source cannot be promoted to approved identities")
    _require(owner["status"] == OWNERSHIP_STATUS
             and owner["source_quarter"] == "2019Q4" and owner["cohort_year"] == 2020
             and owner["selection_asof"] == "2020-01-01"
             and owner["protocol_sha256"] == protocol_sha
             and owner["model_ready"] is False and owner["final_period_opened"] is False
             and owner["source_approvals"] == 0
             and owner["historical_cik_links_created"] == 0
             and owner["known_at_inferred"] is False
             and owner["available_at_inferred"] is False,
             "Original 2020 ownership cohort is not the preserved, unapproved source")
    market_path = _checked_file(market / "candidate_calculations.parquet", max_bytes=32*1024*1024)
    _require(pilot["files"]["candidate_calculations.parquet"] == _file_hash(market_path),
             "Pilot candidate calculations changed since original M5 audit")
    candidate = pd.read_parquet(market_path)
    _require(set(CANDIDATE_COLUMNS).issubset(candidate.columns)
             and len(candidate) == pilot["qa_cases_calculated"] == 135
             and candidate.event_id.is_unique
             and candidate["data_kind"].eq(MARKET_STATUS).all()
             and candidate["model_ready"].eq(False).all()
             and candidate["identity_approved"].eq(False).all()
             and candidate["human_pair_review_complete"].eq(False).all()
             and candidate["qa_status"].eq("calculated_pending_review").all(),
             "Unexpected or allegedly approved pilot event identities")
    candidate["cik_key"] = candidate["cik"].map(lambda s: _integer_key(s, cik=True))
    candidate["security_key"] = candidate["candidate_permno"].map(_integer_key)
    _require(candidate["cik_key"].notna().all() and candidate["security_key"].notna().all()
             and candidate["cik"].eq(candidate["cik_key"]).all(),
             "Malformed pilot CIK or permanent security identifier")
    _require(candidate["acceptance_timestamp"].map(
        lambda s: int(datetime.fromisoformat(s.replace("Z", "+00:00")).year)
        if isinstance(s, str) else 9999).between(2015, 2021).all(),
        "Pilot contains forbidden later-period filings")
    issuer_keys = candidate[["cik_key", "security_key"]].drop_duplicates()
    _require(len(issuer_keys) == 20
             and not issuer_keys.cik_key.duplicated().any()
             and not issuer_keys.security_key.duplicated().any(),
             "Issuer pilot lacks one distinct candidate security per CIK")
    original_sec, sec_provenance = _sec_identity(sec_gzip, sec_execution, config)
    original_rows = 0
    for event in candidate.itertuples():
        original = original_sec.get(event.event_id)
        _require(original is not None, "Pilot event lacks an original SEC filing evidence record")
        source_header = original["header_identity"]
        _require(source_header["header_identity_consistent"] is True
                 and source_header["matching_filer_count"] == 1
                 and original["manifest_cik_raw"] == event.cik_key
                 and original["recorded_acceptance_timestamp"] == event.acceptance_timestamp
                 and any(f["matches_manifest_cik"] and f["cik_comparison_key"] == event.cik_key
                         for f in source_header["filers"]),
                 "Pilot CIK/acceptance disagrees with original SEC filing header")
        _require(original["security_link_created"] is False
                 and original["known_at"] is None and original["available_at"] is None,
                 "Original SEC report silently claims historical security availability")
        original_rows += 1
    tables, source_parts = {}, {}
    for name in RELEVANT_TABLES:
        tables[name], source_parts[name] = _read_table(ownership, owner, name)
    cohort, summary, observations, names = (
        tables["cohort"], tables["cohort_summary"],
        tables["observations"], tables["names_records"]
    )
    sec_occurrences = tables["sec_occurrences"]
    ccm_comparisons = tables["header_comparisons"]
    _require(len(cohort) == len(summary) == owner["counts"]["cohort_rows"]
             and owner["counts"]["cohort_rows"] >= len(issuer_keys)
             and len(sec_occurrences) == owner["counts"]["original_sec_occurrences"]
             and len(sec_occurrences) >= len(issuer_keys),
             "Whole cohort or original SEC occurrence coverage differs from preserved original")
    _require(cohort.security_id.is_unique and summary.security_id.is_unique,
             "Ambiguous selection-year source-security rows")
    _require(cohort["identity_approved"].eq(False).all()
             and summary["identity_approved"].eq(False).all()
             and cohort["known_at"].isna().all() and summary["known_at"].isna().all(),
             "2020 original cohort must remain historical-unapproved")
    selected = issuer_keys.merge(cohort[["security_id", "selection_asof",
                                        "information_cutoff", "rank_eligible_by_candidate_policy"]],
                                 left_on="security_key", right_on="security_id", how="left",
                                 validate="one_to_one", indicator=True)
    _require(selected["_merge"].eq("both").all()
             and selected["rank_eligible_by_candidate_policy"].eq(True).all()
             and selected["selection_asof"].eq("2020-01-01").all()
             and selected["information_cutoff"].eq(owner["information_cutoff"]).all(),
             "Pilot issuer candidate absent or not rank-eligible in saved 2020 cohort")
    selected = selected.merge(summary, on="security_id", how="left", validate="one_to_one")
    _require(selected["observation_status"].notna().all(),
             "Pilot issuer candidate lacks source cohort summary")
    selected_keys = set(selected["security_key"])
    matched_obs = observations.loc[observations["security_id"].isin(selected_keys)].copy()
    _require(len(matched_obs) == int(selected["observation_rows"].sum()),
             "Observed pilot SEC/Names occurrences disagree with saved cohort summary")
    _require(matched_obs["observation_id"].is_unique
             and matched_obs["source_tsv_record"].is_unique,
             "Pilot has duplicated original SEC issuer observations")
    _require(matched_obs["known_at"].isna().all()
             and matched_obs["identity_approved"].eq(False).all(),
             "Issuer observations cannot assert known-at or approval")
    named = names.set_index("source_csv_record", verify_integrity=True)
    present = set(matched_obs["names_source_csv_record"])
    _require(present.issubset(set(named.index)), "Missing dated Names source records")
    _require(named.loc[list(present), "identity_approved"].eq(False).all(),
             "Dated Names source was promoted without evidence")
    sec_original = _checked_file(ownership / "original_SUBMISSION.tsv", max_bytes=24*1024*1024)
    sec_rows = _sec_source_rows(
        sec_original, set(matched_obs["source_tsv_record"]),
        owner["inputs"]["sec_submission_sha256"], len(sec_occurrences),
    )
    name_rows, original_names_header = _names_source_rows(
        names_csv, present, owner["inputs"]["names_source_sha256"],
        owner["counts"]["original_names_source_rows_checked"],
    )
    _require(set(original_names_header) == set(named.columns) - {
        "source_csv_record", "source_sha256", "source_inventory_sha256",
        "retention_roles_json", "known_at", "available_at", "identity_approved",
    }, "Retained Names representation must match all original delivered columns")
    observed_by_security = defaultdict(list)
    for item in matched_obs.itertuples(index=False):
        key = _integer_key(item.security_id)
        original = sec_rows[item.source_tsv_record]
        names_original = name_rows[item.names_source_csv_record]
        names_retained = named.loc[item.names_source_csv_record]
        _require(original["ACCESSION_NUMBER"] == item.accession
                 and original["ISSUERCIK"] == item.sec_issuer_cik_raw
                 and original["ISSUERTRADINGSYMBOL"] == item.sec_symbol_raw
                 and _integer_key(original["ISSUERCIK"], cik=True)
                 == item.sec_issuer_cik_comparison_key
                 and datetime.strptime(original["FILING_DATE"], "%d-%b-%Y").date().isoformat() == item.filing_date,
                 "Original SEC quarterly source ordinal disagrees with derived issuer occurrence")
        _require(item.sec_source_sha256 == owner["inputs"]["sec_submission_sha256"]
                 and item.names_source_sha256 == owner["inputs"]["names_source_sha256"],
                 "Original ownership evidence source SHA reference differs")
        _require(all(str(names_retained[c]) == names_original[c] for c in original_names_header),
                 "Original CRSP Names row differs from retained dated descriptor")
        _require(_integer_key(names_original["permno"]) == key
                 and item.sec_symbol_raw in (names_original["ticker"],
                                              names_original["tradingsymbol"]),
                 "Dated security ID or exact source trading symbol differs")
        day, selection = item.filing_date, "2020-01-01"
        _require(names_original["secinfostartdt"] <= day <= names_original["secinfoenddt"]
                 and names_original["secinfostartdt"] <= selection <= names_original["secinfoenddt"]
                 and names_original["securitybegdt"] <= day <= names_original["securityenddt"]
                 and bool(item.names_record_covers_selection)
                 and bool(item.securitylife_covers_filing_date),
                 "Dated Names and security lifetime do not cover observed SEC/selection dates")
        _require(item.global_symbol_record_count == item.security_date_record_count == 1
                 and bool(item.unambiguous_exact_literal_observation),
                 "SEC/Names literal observation was not a globally unambiguous descriptor match")
        _require(item.filing_date <= "2019-12-31",
                 "Issuer anchor record is after the preserved pre-2020 cutoff date")
        expected_relation = EARLIER if item.filing_date < "2019-12-31" else CUTOFF_UNRESOLVED
        _require(item.cutoff_date_relation == expected_relation,
                 "Cutoff-day or earlier original SEC filing date was misclassified")
        observed_by_security[key].append(item)
    _require(all(len(observed_by_security[key]) > 0 for key in selected_keys),
             "Missing quarter observations for a pilot issuer")
    private = []
    earlier_total = cutoff_total = matching_anchors = 0
    for item in sorted(selected.itertuples(), key=lambda r: r.cik_key):
        key = item.security_key
        group = observed_by_security[key]
        earlier = [o for o in group if o.cutoff_date_relation == EARLIER]
        cutoff = [o for o in group if o.cutoff_date_relation == CUTOFF_UNRESOLVED]
        keys = {_integer_key(o.sec_issuer_cik_comparison_key, cik=True) for o in earlier}
        source_keys = set(json.loads(item.earlier_issuer_cik_comparison_keys_json))
        _require(len(earlier) == item.unambiguous_earlier_date_sec_occurrences
                 and keys == source_keys,
                 "Independent dated issuer facts disagree with original cohort summary")
        _require(len(earlier) + len(cutoff) == item.observation_rows,
                 "Earlier and cutoff observations do not fully account for a pilot issuer")
        _require(keys and None not in keys and all(CIK.fullmatch(k) for k in keys),
                 "Unusable original SEC earlier issuer CIK")
        agrees = keys == {item.cik_key}
        matching_anchors += int(agrees)
        earlier_total += len(earlier)
        cutoff_total += len(cutoff)
        _require(item.known_at is None and item.available_at is None
                 and item.identity_approved is False,
                 "Cohort summary cannot assert historical availability")
        private.append({
            "original_sec_filer_cik": item.cik_key,
            "pilot_candidate_permno": key,
            "cohort_2020_selection_date": item.selection_asof,
            "strictly_earlier_2019q4_source_observations": len(earlier),
            "unresolved_clock_2019q4_source_observations": len(cutoff),
            "strictly_earlier_cik_keys": sorted(keys),
            "pilot_cik_matched_earlier_issuer": agrees,
            "quarter_source_date_min": min(o.filing_date for o in group),
            "quarter_source_date_max": max(o.filing_date for o in group),
            "candidate_header_agreement": bool(item.earlier_candidate_header_agreement),
            "candidate_header_disagreement": bool(item.earlier_candidate_header_disagreement),
            "conditional_development_event_count": int((candidate["security_key"] == key).sum()),
            "source_identity_approval": False, "known_at": None, "available_at": None,
            "historical_link_validity_established": False,
        })
    _require(sum(p["conditional_development_event_count"] for p in private) == 135,
             "Not every pilot filing maps to the recorded source-security candidate")
    _require(matching_anchors <= len(private), "Impossible issuer anchor status")
    original_counts = Counter()
    for row in ccm_comparisons.loc[ccm_comparisons.security_id.isin(selected_keys)].itertuples():
        original_counts[row.cik_comparison] += 1
    _require(_file_hash(names_csv) == owner["inputs"]["names_source_sha256"]
             and _file_hash(sec_original) == owner["inputs"]["sec_submission_sha256"]
             and _file_hash(market_path) == pilot["files"]["candidate_calculations.parquet"]
             and _file_hash(candidate_receipt_path) == candidate_receipt_sha256
             and _file_hash(ownership_receipt_path) == ownership_receipt_sha256,
             "Consumed source changed after source-bound examination")
    for paths in source_parts.values():
        for part, digest in paths:
            _require(_file_hash(part) == digest, "Preserved cohort source part mutated during audit")
    public = {
        "schema_version": 1, "status": STATUS,
        "cohort_year": 2020, "source_quarter": "2019Q4",
        "pilot_development_event_count": len(candidate),
        "pilot_issuers": len(private),
        "pilot_issuers_found_in_2020_cohort": len(selected),
        "original_10k_event_headers_matching_original_cik_and_acceptance": original_rows,
        "securities_with_strictly_earlier_unambiguous_matching_issuer_cik": matching_anchors,
        "strictly_earlier_dated_SEC_ownership_name_observations": earlier_total,
        "cutoff_day_observations_retained_but_not_used_as_earlier": cutoff_total,
        "original_SEC_quarterly_rows_reread": len(sec_rows),
        "original_CRSP_Names_rows_reread": len(name_rows),
        "candidate_header_agreement_issuers": sum(v["candidate_header_agreement"] for v in private),
        "candidate_header_disagreement_issuers": sum(v["candidate_header_disagreement"] for v in private),
        "original_2020_header_comparison_counts": dict(sorted(original_counts.items())),
        "original_quarterly_SEC_occurrences_preserved": owner["counts"]["original_sec_occurrences"],
        "full_original_2020_candidate_cohort_preserved": owner["counts"]["cohort_rows"],
        "original_SEC_headers_reread_this_run": False,
        "original_quarterly_SEC_TSV_reread_this_run": True,
        "original_CRSP_Names_CSV_reread_this_run": True,
        "provenance": {
            "market_candidate_receipt_sha256": candidate_receipt_sha256,
            "ownership_cohort_receipt_sha256": ownership_receipt_sha256,
            "sec_original_evidence_gzip_sha256": sec_provenance["compressed_sha256"],
            "sec_original_evidence_execution_sha256": sec_provenance["published_execution_sha256"],
            "original_SEC_quarterly_TSV_sha256": owner["inputs"]["sec_submission_sha256"],
            "original_CRSP_Names_CSV_sha256": owner["inputs"]["names_source_sha256"],
            "frozen_protocol_sha256": protocol_sha,
        },
        "historical_CIK_to_PERMNO_effective_intervals_established": False,
        "security_links_approved": 0, "historical_known_at_established": False,
        "point_in_time_available_at_established": False,
        "selected_universe_approved": False, "source_approvals": 0, "human_reviews_created": 0,
        "model_ready": False, "final_period_opened": False,
        "empirical_milestones_completed": [],
        "interpretation": (
            "A strictly earlier 2019Q4 filing-date issuer CIK/symbol/dated-Names corroboration "
            "exists for each purposive pilot security at the 2020 selection anchor. These "
            "observations are not continuous security-link validity or point-in-time known_at."
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pilot-issuer-anchor-", dir=out.parent) as scratch:
        stage = Path(scratch) / "evidence"
        stage.mkdir(mode=0o700)
        (stage / "private_issuer_rows.jsonl").write_text(
            "".join(json.dumps(x, sort_keys=True) + "\n" for x in private)
        )
        (stage / "public_summary.json").write_text(json.dumps(public, indent=2, sort_keys=True) + "\n")
        receipt = {
            "schema_version": 1, "status": STATUS,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "files": {name: {
                "sha256": _file_hash(stage / name),
                "bytes": (stage / name).stat().st_size,
            } for name in ("private_issuer_rows.jsonl", "public_summary.json")},
            "provenance": public["provenance"],
            "source_approvals": 0, "security_links_approved": 0,
            "historical_known_at_established": False, "model_ready": False,
            "final_period_opened": False,
        }
        (stage / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        for f in stage.iterdir():
            os.chmod(f, 0o400)
        stage.rename(out)
    return public
