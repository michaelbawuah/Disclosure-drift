"""Original 10-K cover-page TradingSymbol lexical evidence vs. dated CRSP Names.

Read-only development-only corroboration. Matching original SEC trading symbols
does not prove which security class a context represents, contemporaneous
historical availability, or a continuous approved issuer/security mapping.
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

from .protocol import canonical_hash

KIND = "ORIGINAL_SEC_10K_LEXICAL_TRADING_SYMBOL_NAMES_CORROBORATION_UNAPPROVED"
SHA_RE = re.compile(r"[0-9a-f]{64}")
TRADING_CONCEPT = "dei:TradingSymbol"
SOURCE_KIND = "PROVISIONAL_CANDIDATE_ARITHMETIC_QA"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_file(path, size_limit):
    initial = Path(path)
    require(not initial.is_symlink(), "Linked sources not allowed")
    p = initial.resolve(strict=True)
    require(p.is_file() and p.stat().st_size <= size_limit, "Missing or oversized original source")
    return p


def read_sources(candidates, report_gzip, report_execution, names_csv, names_sha,
                 names_inventory, config):
    candidates = Path(candidates)
    original = source_file(candidates / "candidate_calculations.parquet", 32 * 1024 * 1024)
    receipt = source_file(candidates / "audit_summary.json", 250000)
    market_receipt = json.loads(receipt.read_bytes())
    require(market_receipt["data_kind"] == SOURCE_KIND
            and market_receipt["source_hashes"]["protocol"] == canonical_hash(config)
            and market_receipt["historical_cik_mapping_approved"] is False
            and market_receipt["model_ready"] is False
            and market_receipt["final_period_opened"] is False
            and market_receipt["files"]["candidate_calculations.parquet"] == sha(original.read_bytes()),
            "Candidate market source is not original locked unapproved source")
    frame = pd.read_parquet(original)
    require(len(frame) == market_receipt["qa_cases_calculated"] == 135
            and frame.event_id.is_unique and frame.cik.nunique() == 20,
            "Expected 135 original pilot events from 20 issuers")
    require(frame["identity_approved"].eq(False).all()
            and frame["model_ready"].eq(False).all()
            and frame["human_pair_review_complete"].eq(False).all(),
            "Original market candidates cannot already be source-approved")
    require(frame["acceptance_timestamp"].map(
        lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")).year
        if isinstance(value, str) else 3000).between(2015, 2021).all(),
        "Later-year SEC events are not permitted")
    for row in frame.itertuples():
        require(isinstance(row.cik, str) and re.fullmatch(r"[0-9]{10}", row.cik)
                and isinstance(row.candidate_permno, str)
                and re.fullmatch(r"[0-9]{1,20}", row.candidate_permno)
                and datetime.fromisoformat(row.acceptance_timestamp.replace("Z", "+00:00")).tzinfo,
                "Invalid original SEC identification or timezone")
    gzip_path = source_file(report_gzip, 8 * 1024 * 1024)
    execution_path = source_file(report_execution, 1 * 1024 * 1024)
    compressed = gzip_path.read_bytes()
    exec_blob = execution_path.read_bytes()
    execution = json.loads(exec_blob)
    publication = execution["publication"]
    require(sha(compressed) == publication["sha256"] and len(compressed) == publication["bytes"],
            "Original SEC cover-page publication hash changed")
    original_json = gzip.decompress(compressed)
    require(len(original_json) <= 16 * 1024 * 1024
            and sha(original_json) == publication["uncompressed_sha256"],
            "Original SEC cover report decompressed SHA changed")
    data = json.loads(original_json)
    require(data["protocol_sha256"] == canonical_hash(config)
            and data["original_sec_bytes_reread"] is True
            and data["status"] == "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED"
            and data["final_period_opened"] is False and data["source_approvals"] == 0
            and data["xbrl_fact_values_interpreted"] is False
            and len(data["records"]) == 215,
            "Original SEC lexical evidence status not verified")
    accession = {r["accession"]: r for r in data["records"]}
    require(len(accession) == 215, "Duplicate original SEC source accessions")
    saved_names = source_file(names_csv, 256 * 1024 * 1024)
    inventory_path = source_file(names_inventory, 1024 * 1024)
    inventory_raw = inventory_path.read_bytes()
    inventory = json.loads(inventory_raw)
    require(inventory["status"] == "RAW_MANUAL_WRDS_METADATA_INVENTORY_NOT_SOURCE_APPROVED"
            and inventory["protocol_sha256"] == canonical_hash(config)
            and inventory["model_ready"] is False
            and inventory["source_approvals"] == 0,
            "Wrong original unapproved Names inventory receipt")
    source_sha = sha(saved_names.read_bytes())
    require(isinstance(names_sha, str) and SHA_RE.fullmatch(names_sha)
            and source_sha == names_sha
            and inventory["source"]["sha256"] == source_sha
            and inventory["source"]["bytes"] == saved_names.stat().st_size
            and inventory["source"]["observed_header"] == [
                "permno", "hdrprimaryexch", "nasdissuno", "hdrsiccd", "permco",
                "secinfostartdt", "secinfoenddt", "securitybegdt", "securityenddt",
                "cusip", "ticker", "issuernm", "shareclass", "usincflg", "issuertype",
                "securitytype", "securitysubtype", "sharetype", "securityactiveflg",
                "siccd", "primaryexch", "tradingsymbol", "naics", "tradingstatusflg",
            ], "Original Names CSV SHA or inventory header mismatch")
    expected_names_rows = inventory["all_rows"]["rows"]
    require(type(expected_names_rows) is int and 1 <= expected_names_rows <= 2_000_000,
            "Unbounded original Names inventory rows")
    return frame, accession, saved_names, expected_names_rows, {
        "candidate_table_sha256": sha(original.read_bytes()),
        "candidate_receipt_sha256": sha(receipt.read_bytes()),
        "original_SEC_report_gzip_sha256": sha(compressed),
        "original_SEC_report_execution_sha256": sha(exec_blob),
        "original_CRSP_Names_csv_sha256": names_sha,
        "original_CRSP_Names_inventory_receipt_sha256": sha(inventory_raw),
        "protocol_sha256": canonical_hash(config),
    }


def run_tenk_symbol_corrob(candidate_dir, sec_gzip, sec_execution, names_csv, names_sha,
                           names_inventory, output,
                           *, config, repo_root):
    root = Path(repo_root).resolve(strict=True)
    out = Path(output).resolve()
    require(not out.exists() and any(out.is_relative_to(root / name) and out != root / name
                                      for name in ("data", "outputs")),
            "Result must be a new private directory under the repository")
    frame, originals, names_path, expected_names_rows, hashes = read_sources(
        candidate_dir, sec_gzip, sec_execution, names_csv, names_sha, names_inventory, config
    )
    symbols, original_by_event = set(), {}
    for event in frame.itertuples():
        original = originals.get(event.event_id)
        require(original is not None and original["manifest_cik_raw"] == event.cik
                and original["recorded_acceptance_timestamp"] == event.acceptance_timestamp
                and original["header_identity"]["header_identity_consistent"] is True
                and original["header_identity"]["matching_filer_count"] == 1,
                "Original SEC 10-K CIK or acceptance does not match provisional event")
        facts = [f for f in original["cover_evidence"]["facts"]
                 if f["concept_qname_raw"] == TRADING_CONCEPT]
        require(original["security_link_created"] is False
                and original["known_at"] is None
                and original["available_at"] is None, "SEC source cannot claim approved links")
        for fact in facts:
            require(fact["security_link_created"] is False
                    and fact["interpreted_xbrl_value"] is None,
                    "SEC lexical fact cannot claim validated semantics")
            require(isinstance(fact["text_from_parsed_html"], str),
                    "SEC parsed symbol must be original string")
            if fact["text_from_parsed_html"]:
                symbols.add(fact["text_from_parsed_html"])
        original_by_event[event.event_id] = facts
    # All 191,048 original Names rows checked; symbols from other securities
    # must be checked for same-date collisions, not just pilot PERMNO records.
    required_security_ids = set(frame.candidate_permno)
    by_symbol, by_security = defaultdict(list), defaultdict(list)
    row_count = 0
    with names_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, strict=True, restkey="extra")
        hdr = reader.fieldnames
        required = {"permno", "ticker", "tradingsymbol", "secinfostartdt",
                    "secinfoenddt", "securitybegdt", "securityenddt"}
        require(hdr is not None and len(hdr) == 24 and len(set(hdr)) == 24
                and required.issubset(hdr), "Original CRSP Names fields changed")
        for idx, record in enumerate(reader, start=2):
            require("extra" not in record and None not in record.values(),
                    "Malformed original Names CSV record")
            row_count += 1
            row = {
                "ordinal": idx, "permno": record["permno"],
                "start": record["secinfostartdt"], "end": record["secinfoenddt"],
                "born": record["securitybegdt"], "last": record["securityenddt"],
                "ticker": record["ticker"], "tradingsymbol": record["tradingsymbol"],
            }
            if row["permno"] in required_security_ids:
                by_security[row["permno"]].append(row)
            for symbol in {row["ticker"], row["tradingsymbol"]} & symbols:
                by_symbol[symbol].append(row)
    require(row_count == expected_names_rows, "Original complete Names history row count changed")
    counts = Counter()
    by_year = Counter()
    private = []
    for event in sorted(frame.itertuples(), key=lambda x: x.event_id):
        facts = original_by_event[event.event_id]
        if not facts:
            counts["no_supported_trading_symbol_fact"] += 1
            continue
        values = sorted({f["text_from_parsed_html"] for f in facts})
        issues = any(bool(f["lexical_issues"]) for f in facts)
        hidden = any(bool(f["inside_hidden_element"]) or
                     bool(f["hidden_by_inline_style_observed"]) for f in facts)
        day = event.acceptance_timestamp[:10]
        year = int(day[:4])
        matches = []
        for symbol in values:
            global_today = [r for r in by_symbol.get(symbol, ())
                            if r["start"] <= day <= r["end"]]
            same_today = [r for r in by_security[event.candidate_permno]
                          if r["start"] <= day <= r["end"]]
            if (len(global_today) == len(same_today) == 1
                    and global_today[0]["permno"] == event.candidate_permno
                    and global_today[0]["born"] <= day <= global_today[0]["last"]):
                matches.append((symbol, global_today[0]["ordinal"]))
        counts["events_with_original_trading_symbol_facts"] += 1
        by_year[year] += 1
        counts["events_with_at_least_one_unique_dated_names_candidate"] += bool(matches)
        counts["events_with_multiple_distinct_symbols"] += len(values) > 1
        counts["events_with_lexical_issues"] += issues
        counts["events_with_hidden_lexical_facts"] += hidden
        counts["events_with_single_clean_unhidden_symbol_and_unique_names_candidate"] += (
            len(values) == 1 and not issues and not hidden and len(matches) == 1
        )
        private.append({
            "accession": event.event_id, "original_issuer_cik": event.cik,
            "candidate_permno": event.candidate_permno,
            "original_10k_acceptance_day": day,
            "all_sec_symbol_fact_contexts": [
                {"symbol_raw": f["text_from_parsed_html"], "contextref_raw": f["contextref_raw"],
                 "lexical_issues": f["lexical_issues"],
                 "hidden_fact": bool(f["inside_hidden_element"])}
                for f in facts
            ],
            "dated_names_matching_symbol_and_source_record": matches,
            "multiple_symbols_require_class_review": len(values) > 1,
            "lexical_issues_require_review": issues,
            "hidden_facts_require_review": hidden,
            "SEC_XBRL_semantics_validated": False,
            "candidate_security_identity_approved": False,
            "known_at": None, "available_at": None,
        })
    require(sum(by_year.values()) == counts["events_with_original_trading_symbol_facts"]
            and counts["no_supported_trading_symbol_fact"] +
            counts["events_with_original_trading_symbol_facts"] == len(frame),
            "SEC report filing count coverage mismatch")
    require(sha(names_path.read_bytes()) == names_sha
            and sha((Path(candidate_dir) / "candidate_calculations.parquet").read_bytes())
            == hashes["candidate_table_sha256"]
            and sha((Path(candidate_dir) / "audit_summary.json").read_bytes())
            == hashes["candidate_receipt_sha256"]
            and sha(Path(sec_gzip).read_bytes()) == hashes["original_SEC_report_gzip_sha256"]
            and sha(Path(sec_execution).read_bytes()) ==
            hashes["original_SEC_report_execution_sha256"]
            and sha(Path(names_inventory).read_bytes()) ==
            hashes["original_CRSP_Names_inventory_receipt_sha256"],
            "A pinned source changed during the symbol corroboration audit")
    summary = {
        "schema_version": 1, "status": KIND,
        "original_source_filing_pairs": len(frame), "original_names_rows_reread": row_count,
        "filings_with_original_10k_TradingSymbol_lexical_facts":
            counts["events_with_original_trading_symbol_facts"],
        "filings_with_at_least_one_dated_names_candidate_match":
            counts["events_with_at_least_one_unique_dated_names_candidate"],
        "filings_with_multiple_distinct_reported_trading_symbols":
            counts["events_with_multiple_distinct_symbols"],
        "filings_with_symbol_lexical_issues": counts["events_with_lexical_issues"],
        "filings_with_hidden_symbol_facts": counts["events_with_hidden_lexical_facts"],
        "filings_with_clean_single_unhidden_symbol_and_unique_names_candidate":
            counts["events_with_single_clean_unhidden_symbol_and_unique_names_candidate"],
        "filings_without_supported_TradingSymbol_facts":
            counts["no_supported_trading_symbol_fact"],
        "lexical_fact_filing_year_counts": {str(k): v for k, v in sorted(by_year.items())},
        "provenance": hashes,
        "unambiguous_share_class_established": False,
        "XBRL_fact_semantics_validated": False, "original_SEC_bytes_reread_this_run": False,
        "historical_identity_effective_intervals_established": False,
        "historical_known_at_established": False, "market_available_at_established": False,
        "source_approvals": 0, "approved_security_links": 0, "human_reviews_created": 0,
        "model_ready": False, "actual_final_2022_2025_opened": False,
        "interpretation": "Lexical original-10K symbol-to-dated-Names candidate observations only. Multiple symbols/context dimensions, lexical problems and historical availability remain unapproved.",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".tenk-symbol-", dir=out.parent) as scratch:
        stage = Path(scratch) / "audit"
        stage.mkdir(mode=0o700)
        (stage / "private_filing_symbol_contexts.jsonl").write_text(
            "".join(json.dumps(x, sort_keys=True) + "\n" for x in private)
        )
        (stage / "public_summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
        receipt = {
            "schema_version": 1, "status": KIND,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "files": {name: {"sha256": sha((stage / name).read_bytes()),
                             "bytes": (stage / name).stat().st_size}
                      for name in ("private_filing_symbol_contexts.jsonl", "public_summary.json")},
            "provenance": hashes, "source_approvals": 0, "model_ready": False,
            "actual_final_2022_2025_opened": False, "security_links_approved": 0,
        }
        (stage / "receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        for f in stage.iterdir():
            os.chmod(f, 0o400)
        stage.rename(out)
    return summary
