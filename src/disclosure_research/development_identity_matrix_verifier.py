"""Independent raw-source recheck of the private development event evidence matrix.

Uses a separate bisect-based XNYS window derivation and fresh original CSV
reads, not the matrix builder's window/name helpers. Reconstructs aggregate
row evidence while keeping all vendor identifiers out of published JSON.
"""

import bisect
import csv
import gzip
import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .protocol import canonical_hash
from .timing import calendar

STATUS = "INDEPENDENT_DEVELOPMENT_IDENTITY_MATRIX_RECONCILED_NOT_APPROVED"
MATRIX_STATUS = "DEVELOPMENT_EVENT_IDENTITY_MATRIX_DESCRIPTORS_NOT_APPROVED"
ORIGINAL_REPORT_STATUS = "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED"
_CIK = re.compile(r"[0-9]{10}")


def _must(ok, reason):
    if not ok:
        raise ValueError(reason)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _input(path, *, cap):
    original = Path(path)
    _must(not original.is_symlink(), "Source symlink is not permitted")
    source = original.resolve(strict=True)
    _must(source.is_file() and source.stat().st_size <= cap, "Missing or oversized source")
    return source, source.read_bytes()


def independently_verify_event_matrix(matrix, market, names, ccm, sec_gzip,
                                      anchor, output, *, config, repo_root):
    root = Path(repo_root).resolve(strict=True)
    destination = Path(output).resolve()
    _must(not destination.exists() and destination.is_relative_to(root / "reports"),
          "Verification must write one new public report under reports/")
    matrix = Path(matrix).resolve(strict=True)
    receipt_path, receipt_raw = _input(matrix / "receipt.json", cap=200000)
    public_path, public_raw = _input(matrix / "public_summary.json", cap=200000)
    events_path, events_raw = _input(matrix / "review_queue_private.jsonl", cap=2 * 1024 * 1024)
    private_html_path, private_html = _input(matrix / "private_review.html", cap=1024 * 1024)
    receipt = json.loads(receipt_raw)
    public = json.loads(public_raw)
    _must(receipt["status"] == public["status"] == MATRIX_STATUS
          and receipt["source_approvals"] == 0
          and receipt["historical_links_approved"] == 0
          and receipt["model_ready"] is False and receipt["final_period_opened"] is False
          and public["model_ready"] is False and public["final_period_opened"] is False
          and public["historical_known_at_established"] is False
          and public["market_available_at_established"] is False
          and public["human_review_or_source_approvals_created"] == 0,
          "Original matrix or research gates differ from unapproved state")
    _must(receipt["source_bindings"] == public["provenance"]
          and public["provenance"]["protocol"] == canonical_hash(config),
          "Matrix input source fingerprints differ")
    for name, blob in (("public_summary.json", public_raw),
                       ("review_queue_private.jsonl", events_raw),
                       ("private_review.html", private_html)):
        declaration = receipt["files"][name]
        _must(_digest(blob) == declaration["sha256"]
              and len(blob) == declaration["bytes"],
              "Original matrix output bytes fail receipt hash")
    _must(b"Source evidence only" in private_html
          and b"read-only" in private_html
          and b"<script" not in private_html.lower(),
          "Private review HTML contains unsupported interactive or script content")
    saved = [json.loads(line) for line in events_raw.decode().splitlines()]
    by_id = {entry["observation_id"]: entry for entry in saved}
    _must(len(saved) == len(by_id) == public["counts"]["events"] == 135,
          "Matrix has duplicated or missing original filing identifiers")
    _must(all(x["historical_CIK_to_PERMNO_approved"] is False
              and x["historical_known_at"] is None
              and x["market_available_at"] is None and x["source_release_verified"] is False
              and x["model_ready"] is False for x in saved),
          "An original private event is falsely approved")
    original_market, market_bytes = _input(market, cap=32 * 1024 * 1024)
    _must(_digest(market_bytes) == public["provenance"]["candidate_table"],
          "Original M5 candidate table fingerprint differs")
    m5 = pd.read_parquet(original_market)
    _must(len(m5) == 135 and m5.event_id.is_unique
          and set(m5.event_id) == set(by_id),
          "Original M5 candidate event set differs")
    original_names, names_bytes = _input(names, cap=256 * 1024 * 1024)
    _must(_digest(names_bytes) == public["provenance"]["names_source"],
          "Original CRSP Names source fingerprint differs")
    original_sec, sec_bytes = _input(sec_gzip, cap=8 * 1024 * 1024)
    _must(_digest(sec_bytes) == public["provenance"]["sec_identity_gzip"],
          "SEC original-source gzip fingerprint differs")
    sec_json = gzip.decompress(sec_bytes)
    _must(len(sec_json) < 16 * 1024 * 1024
          and _digest(sec_json) == public["provenance"]["sec_identity_original_json"],
          "SEC original source report hash changed")
    sec_report = json.loads(sec_json)
    _must(sec_report["status"] == ORIGINAL_REPORT_STATUS
          and sec_report["source_approvals"] == 0
          and sec_report["final_period_opened"] is False,
          "Original SEC report has unsupported review state")
    original_accessions = {record["accession"]: record for record in sec_report["records"]}
    _must(len(original_accessions) == 215, "Original SEC report lacks complete filing set")
    anchors = Path(anchor).resolve(strict=True)
    anchor_path, anchor_bytes = _input(anchors / "private_issuer_rows.jsonl", cap=64 * 1024)
    _must(_digest(anchor_bytes) == public["provenance"]["anchor_private_rows"],
          "Original Q4 issuer anchor source changed")
    anchor_by_cik = {
        item["original_sec_filer_cik"]: item
        for item in (json.loads(line) for line in anchor_bytes.decode().splitlines())
    }
    _must(len(anchor_by_cik) == 20, "Missing or ambiguous issuer quarter anchors")
    security_ids = set(m5["candidate_permno"])
    names_by_security = defaultdict(list)
    names_count = 0
    with original_names.open(encoding="utf-8-sig", newline="") as file:
        rd = csv.DictReader(file, strict=True, restkey="EXTRA")
        _must(rd.fieldnames is not None
              and set(("permno", "permco", "secinfostartdt", "secinfoenddt",
                       "securitybegdt", "securityenddt", "cusip", "tradingsymbol",
                       "ticker")).issubset(rd.fieldnames),
              "Original CRSP Names has unsupported fields")
        for ordinal, row in enumerate(rd, start=2):
            names_count += 1
            _must("EXTRA" not in row and None not in row.values(),
                  "Malformed raw Names CSV row")
            if row["permno"] in security_ids:
                row["_source_record"] = ordinal
                names_by_security[row["permno"]].append(row)
    _must(len(names_by_security) == 20, "Expected every pilot PERMNO in original Names")
    selected_company_ids = {
        row["permco"] for rows in names_by_security.values() for row in rows
    }
    _must(len(selected_company_ids) == 20 and "" not in selected_company_ids,
          "Selected original Names company identifiers are missing or ambiguous")
    company_names = defaultdict(list)
    repeat_count = 0
    with original_names.open(encoding="utf-8-sig", newline="") as file:
        rd = csv.DictReader(file, strict=True, restkey="EXTRA")
        for ordinal, row in enumerate(rd, start=2):
            repeat_count += 1
            _must("EXTRA" not in row and None not in row.values(),
                  "Malformed complete source during independent PERMCO review")
            if row["permco"] in selected_company_ids:
                row["_source_record"] = ordinal
                company_names[row["permco"]].append(row)
    _must(repeat_count == names_count and len(company_names) == 20,
          "Independent complete same-company source history differs")
    ccm_rows = defaultdict(list)
    for filename in ccm:
        path, content = _input(filename, cap=64 * 1024 * 1024)
        _must(_digest(content) == public["provenance"][f"ccm_source:{path.name}"],
              "Original CCM row source fingerprint differs")
        with path.open(encoding="utf-8-sig", newline="") as file:
            rd = csv.DictReader(file, strict=True, restkey="EXTRA")
            _must(rd.fieldnames is not None
                  and {"LPERMNO", "LPERMCO", "LINKDT", "LINKENDDT", "cik",
                       "gvkey"}.issubset(rd.fieldnames),
                  "Original CCM lacks expected historical link fields")
            for ordinal, row in enumerate(rd, start=2):
                _must("EXTRA" not in row and None not in row.values(),
                      "Malformed original CCM file")
                if row["LPERMNO"] in security_ids:
                    row["_source_record"] = ordinal
                    row["_source_file"] = path.name
                    ccm_rows[row["LPERMNO"]].append(row)
    _must(len(ccm_rows) == 20, "Original CCM does not cover all pilot candidate securities")
    # Distinct independent session-index logic. The study's calendar package
    # is reused, but neither event_window nor control_sessions is invoked.
    sessions = calendar().sessions.strftime("%Y-%m-%d").tolist()
    eastern = ZoneInfo("America/New_York")
    totals = Counter()
    per_year = defaultdict(Counter)
    for row in m5.itertuples(index=False):
        item = by_id[row.event_id]
        _must(item["original_SEC_CIK"] == row.cik
              and item["candidate_CRSP_PERMNO"] == row.candidate_permno
              and item["acceptance_timestamp"] == row.acceptance_timestamp,
              "Saved event differs from original M5 CIK/security/time")
        recorded = original_accessions.get(row.event_id)
        _must(recorded is not None
              and recorded["manifest_cik_raw"] == row.cik
              and recorded["recorded_acceptance_timestamp"] == row.acceptance_timestamp
              and recorded["header_identity"]["header_identity_consistent"] is True,
              "Original SEC 10-K header CIK or acceptance changed")
        accepted = datetime.fromisoformat(row.acceptance_timestamp.replace("Z", "+00:00"))
        _must(accepted.utcoffset() is not None
              and 2015 <= accepted.year <= config["development_end"]
              and accepted.year < config["holdout_start"],
              "Outside-period or naive SEC acceptance timestamp")
        acceptance_day = accepted.astimezone(eastern).date().isoformat()
        reference_index = bisect.bisect_right(sessions, acceptance_day) + config["reference_session_offset"] - 1
        _must(reference_index >= 60
              and reference_index + config["horizon_sessions"] < len(sessions),
              "Original event has unsupported XNYS timing")
        history = sessions[reference_index - 60: reference_index]
        reference = sessions[reference_index]
        future = sessions[reference_index + 1:reference_index + 21]
        _must((reference, history[-1], history[0], future[-1])
              == (row.reference_session, row.controls_asof,
                  row.control_history_start, row.label_end)
              and item["reference_session"] == reference
              and item["control_session_count"] == len(history) == 60
              and item["return_session_count"] == len(future) == 20,
              "Original XNYS reference/control/label dates differ")
        required = [*history, reference, *future]
        live_ccm = [
            link for link in ccm_rows[row.candidate_permno]
            if link["LINKDT"] <= acceptance_day
            and (link["LINKENDDT"] == "E" or acceptance_day <= link["LINKENDDT"])
        ]
        _must(len(live_ccm) == 1,
              "Different number of original CCM link candidates at source filing")
        ccm_item = live_ccm[0]
        _must(item["original_CCM_source_file"] == ccm_item["_source_file"]
              and item["original_CCM_source_record"] == ccm_item["_source_record"]
              and item["original_CCM_GVKEY"] == ccm_item["gvkey"]
              and item["original_CCM_link_end_literal"] == ccm_item["LINKENDDT"]
              and item["original_CCM_company_header_CIK"] == ccm_item["cik"],
              "Event's original CCM source reference does not match complete source")
        records = []
        for day in required:
            valid = [name for name in names_by_security[row.candidate_permno]
                     if name["secinfostartdt"] <= day <= name["secinfoenddt"]]
            _must(len(valid) == 1, "Independent descriptor window has gap or overlap")
            name = valid[0]
            _must(name["securitybegdt"] <= day <= name["securityenddt"]
                  and name["permco"] == ccm_item["LPERMCO"],
                  "Independent Names lifetime or permanent company ID differs")
            records.append(name)
        source_ids = sorted({name["_source_record"] for name in records})
        cusips = sorted({name["cusip"] for name in records})
        ticker_symbols = sorted({name["tradingsymbol"] for name in records})
        _must(item["source_names_record_ordinals"] == source_ids
              and item["observed_names_CUSIP8_raw"] == cusips
              and item["observed_names_trading_symbols_raw"] == ticker_symbols,
              "Saved individual event's exact original Names history differs")
        anchor_row = anchor_by_cik.get(row.cik)
        _must(anchor_row is not None
              and anchor_row["pilot_candidate_permno"] == row.candidate_permno
              and anchor_row["pilot_cik_matched_earlier_issuer"] is True
              and anchor_row["known_at"] is None
              and anchor_row["available_at"] is None,
              "Different Q4 issuer CIK/permanent security anchor evidence")
        earlier = anchor_row["quarter_source_date_min"] < acceptance_day
        _must(item["2019q4_issuer_anchor_reported_before_10k"] is earlier,
              "Saved quarter anchor incorrectly ordered against 10-K")
        original_facts = [f for f in recorded["cover_evidence"]["facts"]
                          if f["concept_qname_raw"] == "dei:TradingSymbol"]
        _must(item["original_10k_symbol_fact_count"] == len(original_facts),
              "Original 10-K cover symbol source count changed")
        symbols = {f["text_from_parsed_html"] for f in original_facts}
        accept_descriptors = [
            name for name in names_by_security[row.candidate_permno]
            if name["secinfostartdt"] <= acceptance_day <= name["secinfoenddt"]
        ]
        _must(len(accept_descriptors) == 1, "Acceptance-day original Names descriptor ambiguous")
        selected_descriptor = accept_descriptors[0]
        alternate_company_securities = sorted({
            n["permno"] for n in company_names[selected_descriptor["permco"]]
            if n["secinfostartdt"] <= acceptance_day <= n["secinfoenddt"]
            and n["permno"] != row.candidate_permno
        })
        _must(
            item["alternative_active_same_PERMCO_security_ids_raw"] == alternate_company_securities
            and item["selected_original_names_sharetype_raw"] == selected_descriptor["sharetype"]
            and item["selected_original_names_shareclass_raw"] == selected_descriptor["shareclass"]
            and item["selected_original_names_issuertype_raw"] == selected_descriptor["issuertype"]
            and item["selected_original_names_securitytype_raw"] == selected_descriptor["securitytype"],
            "Original share-class context or other same-company PERMNO differs"
        )
        matched = bool(original_facts and any(
            s in (accept_descriptors[0]["ticker"], accept_descriptors[0]["tradingsymbol"])
            for s in symbols if s
        ))
        multi = len(symbols) > 1
        issue = any(bool(f["lexical_issues"]) for f in original_facts)
        hidden = any(bool(f["inside_hidden_element"])
                     or bool(f["hidden_by_inline_style_observed"]) for f in original_facts)
        clean = bool(original_facts) and matched and not multi and not issue and not hidden
        _must(item["strict_clean_single_cover_symbol_candidate"] is clean,
              "Clean lexical SEC 10-K stock class candidate differs")
        flags = set(item["review_flags"])
        expected_flags = {
            "CCM_OPEN_LINK_END_UNRESOLVED": ccm_item["LINKENDDT"] == "E",
            "CURRENT_COMPANY_HEADER_CIK_CONFLICT": ccm_item["cik"] != row.cik,
            "DATED_NAMES_DESCRIPTOR_TRANSITION_WITHIN_81_SESSIONS": len(source_ids) > 1,
            "CONTEMPORANEOUS_OTHER_CRSP_PERMNO_SAME_PERMCO_REVIEW": bool(alternate_company_securities),
            "BLANK_NAMES_SHARECLASS_LITERAL_NOT_ELIGIBILITY_APPROVAL": not bool(selected_descriptor["shareclass"]),
            "DATED_EIGHT_CHAR_CUSIP_CHANGE_WITHIN_WINDOW": len(cusips) > 1,
            "DATED_TRADING_SYMBOL_CHANGE_WITHIN_WINDOW": len(ticker_symbols) > 1,
            "NO_ORIGINAL_10K_LEXICAL_TRADING_SYMBOL_FACT": not bool(original_facts),
            "MULTIPLE_DISTINCT_10K_TRADING_SYMBOLS_CLASS_REVIEW": multi,
            "ORIGINAL_10K_SYMBOL_LEXICAL_ISSUE": issue,
            "ORIGINAL_10K_HIDDEN_SYMBOL_CONTEXT": hidden,
            "2019Q4_ISSUER_ANCHOR_NOT_EARLIER_THAN_THIS_10K": not earlier,
        }
        for flag, present in expected_flags.items():
            _must((flag in flags) is present,
                  "Private review flag disagrees with independently rebuilt original source")
        _must({
            "HISTORICAL_CIK_TO_SECURITY_KNOWN_AT_UNKNOWN",
            "MARKET_SOURCE_AVAILABLE_AT_UNKNOWN",
            "SOURCE_RELEASE_AND_VERSION_UNVERIFIED",
        }.issubset(flags), "Private review queue omits mandatory unresolved gates")
        year = accepted.year
        counts = {
            "events": 1,
            "required_session_checks": 81,
            "unique_names_descriptors_at_81_required_sessions": 1,
            "unique_ccm_link_candidate_at_acceptance": 1,
            "permanent_company_ID_consistent_for_all_81_sessions": 1,
            "original_filing_CIK_and_clock_validated_by_prior_SEC_source_report": 1,
            "dated_names_descriptor_transition_windows": int(len(source_ids) > 1),
            "eight_char_cusip_change_windows": int(len(cusips) > 1),
            "dated_trading_symbol_change_windows": int(len(ticker_symbols) > 1),
            "current_ccm_company_header_CIK_differences": int(ccm_item["cik"] != row.cik),
            "open_ended_CCM_links": int(ccm_item["LINKENDDT"] == "E"),
            "events_with_alternative_active_CRSP_PERMNO_same_company": int(bool(alternate_company_securities)),
            "events_with_blank_original_names_shareclass": int(not selected_descriptor["shareclass"]),
            "original_10k_trading_symbol_fact_events": int(bool(original_facts)),
            "original_10k_exact_date_symbol_candidate_matches": int(matched),
            "original_10k_single_clean_nonhidden_symbol_candidate_matches": int(clean),
            "original_10k_multiple_distinct_symbols": int(multi),
            "original_10k_lexical_symbol_issues": int(issue),
            "original_10k_hidden_symbol_facts": int(hidden),
            "original_2019q4_issuer_anchor_filing_date_before_this_event": int(earlier),
            "events_with_both_prior_Q4_filing_date_anchor_and_10K_cover_symbol":
                int(earlier and bool(original_facts)),
            "events_with_only_10K_cover_symbol_no_prior_Q4_anchor":
                int(not earlier and bool(original_facts)),
            "events_with_only_prior_Q4_filing_date_anchor_no_10K_cover_symbol":
                int(earlier and not original_facts),
            "events_with_neither_prior_Q4_anchor_nor_direct_10K_cover_symbol":
                int(not earlier and not original_facts),
        }
        totals.update(counts)
        per_year[year].update({
            "events": 1, "required_session_checks": 81,
            "descriptor_transition_windows": int(len(source_ids) > 1),
            "cusip_change_windows": int(len(cusips) > 1),
            "CCM_header_disagreement_events": int(ccm_item["cik"] != row.cik),
            "alternative_active_same_PERMCO_security_events": int(bool(alternate_company_securities)),
            "blank_original_names_shareclass_events": int(not selected_descriptor["shareclass"]),
            "original_10k_symbol_fact_events": int(bool(original_facts)),
            "clean_single_symbol_candidate_matches": int(clean),
            "prior_2019q4_issuer_anchor_date_events": int(earlier),
            "both_prior_Q4_anchor_and_cover_symbol_events":
                int(earlier and bool(original_facts)),
            "neither_prior_Q4_anchor_nor_cover_symbol_events":
                int(not earlier and not original_facts),
        })
    _must(dict(totals) == public["counts"]
          and {str(year): dict(sorted(ctr.items())) for year, ctr in sorted(per_year.items())}
          == public["year_counts"],
          "Independent full cohort metric totals/years differ")
    # Rehash source files at the end so this verification never reports success
    # after source mutation during processing.
    for path, digest in ((original_market, public["provenance"]["candidate_table"]),
                         (original_names, public["provenance"]["names_source"]),
                         (original_sec, public["provenance"]["sec_identity_gzip"]),
                         (anchor_path, public["provenance"]["anchor_private_rows"])):
        _must(_digest(path.read_bytes()) == digest,
              "A consumed original source changed during independent verification")
    result = {
        "schema_version": 1, "status": STATUS,
        "method": "Independent bisect-derived XNYS windows and raw CCM/CRSP Names/SEC original-source comparison",
        "independently_rebuilt_events": int(totals["events"]),
        "independently_rebuilt_session_checks": int(totals["required_session_checks"]),
        "independently_verified_issuers": len(anchor_by_cik),
        "independent_year_and_event_counts_match": True,
        "full_private_per_event_review_flag_comparison_passed": True,
        "original_names_rows_examined": names_count,
        "source_fingerprint": {
            "prior_private_matrix_receipt": _digest(receipt_raw),
            "original_M5_candidate_table": public["provenance"]["candidate_table"],
            "original_names_csv": public["provenance"]["names_source"],
            "original_SEC_10K_report": public["provenance"]["sec_identity_gzip"],
        },
        "source_approvals_created": 0,
        "continuous_CIK_PERMNO_link_approved": False,
        "historical_known_at_established": False,
        "point_in_time_market_available_at_established": False,
        "model_ready": False, "final_period_opened": False,
        "interpretation": "Independent reproducibility of retrospective descriptors; no empirical model input approvals or share-class adjudication",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".independent-identity-", dir=destination.parent) as temp:
        tmp = Path(temp) / "independent.json"
        tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, destination)
    return result
