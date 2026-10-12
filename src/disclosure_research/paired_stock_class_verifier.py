"""Separate source and per-issuer recheck for the private 10-K paired-year dossier.

Reconstructs each fact/context/title/exchange from original-source-verified
lexical SEC evidence, without granting historic mapping or SEC publication time.
"""

import gzip
import hashlib
import json
import re
import tempfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from .protocol import canonical_hash

STATUS = "INDEPENDENT_10K_REGISTERED_STOCK_ANNUAL_PAIR_AUDIT_NOT_APPROVED"
EXPECTED = "ORIGINAL_10K_REGISTERED_STOCK_PAIRED_YEAR_REVIEW_NOT_APPROVED"
COMMON = re.compile(r"\bcommon\s+stock\b", re.I)
CAPITAL = re.compile(r"\bcapital\s+stock\b", re.I)
GAAP = re.compile(r"http://fasb\.org/us-gaap/[0-9]{4}-[0-9]{2}-[0-9]{2}")
SEC = re.compile(r"http://xbrl\.sec\.gov/dei/[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _require(good, what):
    if not good:
        raise ValueError(what)


def _sha(content):
    return hashlib.sha256(content).hexdigest()


def _data(path, *, size):
    raw = Path(path)
    _require(not raw.is_symlink(), "Symlinked research source forbidden")
    path = raw.resolve(strict=True)
    _require(path.is_file() and path.stat().st_size <= size,
             "Missing or oversized original research source")
    return path, path.read_bytes()


def _words(s):
    return " ".join(s.split()).casefold()


def _class_title(s):
    if COMMON.search(s):
        return "EXPLICIT_COMMON_STOCK_TITLE"
    if CAPITAL.search(s):
        return "CAPITAL_STOCK_TITLE_CLASS_REVIEW"
    return "OTHER_REGISTERED_TITLE_CLASS_REVIEW"


def verify_paired_source(paired_dir, first_class_dir, original_sec_gzip, destination, *,
                         config, repo_root):
    root = Path(repo_root).resolve(strict=True)
    out = Path(destination).resolve()
    _require(not out.exists() and out.is_relative_to(root / "reports"),
             "Independent source report must be a new path in reports")
    paired = Path(paired_dir).resolve(strict=True)
    class_dir = Path(first_class_dir).resolve(strict=True)
    _, receipt_raw = _data(paired / "receipt.json", size=120000)
    receipt = json.loads(receipt_raw)
    _, public_raw = _data(paired / "public_summary.json", size=120000)
    public = json.loads(public_raw)
    _, private_raw = _data(paired / "private_issuer_pairs.jsonl", size=2 * 1024 * 1024)
    _, html_raw = _data(paired / "private_review.html", size=2 * 1024 * 1024)
    _require(receipt["status"] == public["status"] == EXPECTED
             and receipt["source_fingerprints"] == public["source_fingerprints"]
             and receipt["source_approvals"] == receipt["class_approvals"] == 0
             and public["source_approvals_created"] == 0
             and public["human_source_review_completed"] is False
             and public["historical_CIK_to_security_link_approved"] is False
             and public["historical_known_at_established"] is False
             and public["vendor_market_available_at_established"] is False
             and public["iXBRL_semantics_validated"] is False
             and public["original_SEC_public_dissemination_verified"] is False
             and public["model_ready"] is False and public["final_period_opened"] is False
             and receipt["model_ready"] is False and receipt["final_period_opened"] is False
             and public["source_fingerprints"]["locked_protocol"] == canonical_hash(config),
             "Original paired review no longer declares source/identity restrictions")
    for key, blob in (
        ("public_summary.json", public_raw),
        ("private_issuer_pairs.jsonl", private_raw),
        ("private_review.html", html_raw),
    ):
        declaration = receipt["files"][key]
        _require(declaration["sha256"] == _sha(blob)
                 and declaration["bytes"] == len(blob),
                 "Original private annual review output does not match receipt hashes")
    _require(b"<script" not in html_raw.lower()
             and b"read-only" in html_raw
             and b"not class approvals" in html_raw.lower(),
             "Private review HTML is unsafe or fails to state review status")
    pairs = [json.loads(line) for line in private_raw.decode().splitlines()]
    _require(len(pairs) == public["issuer_pairs_in_first_review"]
             and len({(p["issuer_CIK"], p["candidate_PERMNO"]) for p in pairs}) == len(pairs),
             "Annual source-review pairs are duplicated or missing")
    _, first_receipt_raw = _data(class_dir / "receipt.json", size=150000)
    _, first_public_raw = _data(class_dir / "public_summary.json", size=150000)
    _, first_private_raw = _data(class_dir / "private_context_review.jsonl", size=2 * 1024 * 1024)
    ref = public["source_fingerprints"]
    _require(_sha(first_receipt_raw) == ref["original_class_receipt"]
             and _sha(first_private_raw) == ref["original_class_private_rows"],
             "Earlier 41-case source bundle fingerprint differs")
    first_receipt = json.loads(first_receipt_raw)
    _require(
        first_receipt["files"]["public_summary.json"]["sha256"] == _sha(first_public_raw)
        and first_receipt["files"]["private_context_review.jsonl"]["sha256"] == _sha(first_private_raw),
        "Earlier 41-case packet no longer matches its original receipt",
    )
    prior = json.loads(first_public_raw)
    _require(prior["status"] == "SEC_COVER_CLASS_LEXICAL_41_CASE_TRIAGE_NOT_APPROVED"
             and prior["source_approvals_created"] == 0
             and prior["model_ready"] is False
             and prior["final_period_opened"] is False,
             "Earlier common-stock candidate review lost its closed gates")
    eligible_cases = {}
    for case in (json.loads(line) for line in first_private_raw.decode().splitlines()):
        eligible = [
            fact for fact in case["matched_symbol_source_contexts"]
            if fact["class_context_mode"] == "STANDARD_GAAP_COMMON_STOCK_MEMBER"
            and not fact["lexical_review_reasons"]
        ]
        if eligible:
            _require(len(eligible) == 1,
                     "Multiple source symbols in same common member need manual review")
            eligible_cases[case["observation_id"]] = {
                "original_issuer_CIK": case["original_issuer_CIK"],
                "candidate_CRSP_PERMNO": case["candidate_CRSP_PERMNO"],
                "source": eligible[0],
            }
    _require(len(eligible_cases) ==
             prior["counts"]["filings_standard_common_member_without_fact_lexical_warnings"],
             "Eligible source-based candidate set no longer agrees with original review")
    original_sec_path, compressed = _data(original_sec_gzip, size=8 * 1024 * 1024)
    _require(_sha(compressed) == ref["original_sec_gzip"],
             "Original SEC source report fingerprint changed")
    original = gzip.decompress(compressed)
    _require(len(original) <= 16 * 1024 * 1024
             and _sha(original) == ref["original_sec_json"],
             "Original SEC decompressed source publication fingerprint changed")
    src = json.loads(original)
    _require(src["status"] == "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED"
             and src["source_approvals"] == 0 and src["final_period_opened"] is False
             and src["xbrl_fact_values_interpreted"] is False
             and src["original_sec_bytes_reread"] is True
             and len(src["records"]) == 215
             and src["protocol_sha256"] == canonical_hash(config),
             "Original SEC records falsely assert semantic or access verification")
    original_records = {x["accession"]: x for x in src["records"]}
    _require(len(original_records) == 215, "Duplicate original SEC filing accession")
    counts = Counter()
    by_original = defaultdict(list)
    for pair in pairs:
        cik, permno = pair["issuer_CIK"], pair["candidate_PERMNO"]
        _require(pair["human_approved_historical_class"] is False
                 and pair["historical_security_identity_known_at"] is None
                 and pair["source_release_verified"] is False,
                 "A paired-source reviewer decision was inferred")
        for row in pair["filings"]:
            accession = row["accession"]
            _require(accession in eligible_cases
                     and eligible_cases[accession]["original_issuer_CIK"] == cik
                     and eligible_cases[accession]["candidate_CRSP_PERMNO"] == permno
                     and row["historical_security_class_approved"] is False
                     and row["historical_security_link_known_at"] is None
                     and row["vendor_market_data_available_at"] is None
                     and row["original_sec_public_dissemination_verified"] is False
                     and row["original_10k_HTML_bytes_reopened_here"] is False,
                     "Unapproved original 10-K source case is inconsistent or has fabricated approval")
            original_item = original_records.get(accession)
            _require(original_item is not None
                     and original_item["manifest_cik_raw"] == cik
                     and original_item["recorded_acceptance_timestamp"][:10] == row["acceptance_date"]
                     and original_item["header_identity"]["header_identity_consistent"] is True
                     and original_item["known_at"] is None
                     and original_item["available_at"] is None
                     and original_item["security_link_created"] is False,
                     "Original SEC filer/acceptance/source security gates disagree")
            cover = original_item["cover_evidence"]
            facts = cover["facts"]
            context = [
                ctx for ctx in cover["contexts"]
                if ctx["context_id_raw"] == row["source_contextref"]
            ]
            _require(len(context) == 1, "Original source symbol context is ambiguous or missing")
            ctx = context[0]
            _require(len(ctx["entity_identifiers"]) == 1
                     and ctx["entity_identifiers"][0].get("scheme_raw") == "http://www.sec.gov/CIK"
                     and ctx["entity_identifiers"][0].get("text_from_parsed_html") == cik,
                     "Original SEC source context CIK is not original filer")
            ends = [
                period["text_from_parsed_html"]
                for period in ctx["period_components"]
                if period["kind"] in ("enddate", "instant")
            ]
            _require(ends and all(
                isinstance(d, str) and date.fromisoformat(d) <= date.fromisoformat(row["acceptance_date"])
                for d in ends
            ), "Original stock-class SEC context period is after filing")
            commons = [
                dim for dim in ctx["dimensions"]
                if dim["dimension_qname_raw"] == "us-gaap:StatementClassOfStockAxis"
                and dim["member_namespace"]["qname_raw"] == "us-gaap:CommonStockMember"
                and dim["member_namespace"]["status"] == "DECLARATION_FOUND_IN_PARSED_HTML"
                and dim["dimension_namespace"]["status"] == "DECLARATION_FOUND_IN_PARSED_HTML"
                and GAAP.fullmatch(str(dim["member_namespace"].get("namespace_uri", "")))
                and GAAP.fullmatch(str(dim["dimension_namespace"].get("namespace_uri", "")))
            ]
            _require(len(commons) == 1
                     and row["source_class_member_qname"] == "us-gaap:CommonStockMember"
                     and row["registered_member_namespace_verified"] is True,
                     "Original common-stock member QName/namespace not supported")
            matching_fact = [
                f for f in facts if f["concept_qname_raw"] == "dei:TradingSymbol"
                and f["text_from_parsed_html"] == row["stock_symbol_raw"]
                and f["contextref_raw"] == row["source_contextref"]
                and f["context_element_ordinals"] == [ctx["context_element_ordinal"]]
                and not f["lexical_issues"]
                and not f["inside_hidden_element"]
                and not f["hidden_by_inline_style_observed"]
                and not f["nil_attributes_raw"]
                and f["concept_namespace"]["status"] == "DECLARATION_FOUND_IN_PARSED_HTML"
                and SEC.fullmatch(str(f["concept_namespace"].get("namespace_uri", "")))
            ]
            _require(len(matching_fact) == 1, "Original 10-K symbol is not a clean exact fact")
            titles = sorted({
                f["text_from_parsed_html"] for f in facts
                if f["concept_qname_raw"] == "dei:Security12bTitle"
                and f["contextref_raw"] == row["source_contextref"]
            })
            exchanges = sorted({
                f["text_from_parsed_html"] for f in facts
                if f["concept_qname_raw"] == "dei:SecurityExchangeName"
                and f["contextref_raw"] == row["source_contextref"]
            })
            _require(titles == [row["registered_stock_title_raw"]]
                     and exchanges == [row["registered_exchange_raw"]],
                     "Original same-context registered title/exchange changed")
            prior_fact = eligible_cases[accession]["source"]
            _require(prior_fact["trading_symbol"] == row["stock_symbol_raw"]
                     and prior_fact["same_context_registered_titles_raw"] == titles
                     and prior_fact["same_context_exchange_names_raw"] == exchanges,
                     "Pair fact no longer agrees with first original lexical review")
            original_associated_format_issue = any(
                "format_transformation_not_interpreted" in fact.get("lexical_issues", [])
                for fact in facts
                if fact["contextref_raw"] == row["source_contextref"]
                and fact["concept_qname_raw"] in (
                    "dei:Security12bTitle", "dei:SecurityExchangeName",
                )
            )
            _require(
                original_associated_format_issue
                == bool(prior_fact["associated_fact_transformation_caveats"]),
                "Uninterpreted associated title/exchange XBRL format source report differs",
            )
            title = row["registered_stock_title_raw"]
            title_kind = (
                "EXPLICIT_COMMON_STOCK_TITLE" if re.search(r"\bcommon\s+stock\b", title, re.I)
                else "CAPITAL_STOCK_TITLE_CLASS_REVIEW"
                if re.search(r"\bcapital\s+stock\b", title, re.I)
                else "OTHER_REGISTERED_TITLE_CLASS_REVIEW"
            )
            _require(row["title_kind"] == title_kind,
                     "Registered SEC stock-title classification was altered")
            report_symbols = {
                f["text_from_parsed_html"] for f in facts
                if f["concept_qname_raw"] == "dei:TradingSymbol"
            }
            _require(row["other_reported_symbols_present"] is (len(report_symbols) > 1),
                     "Original other-SEC-security presence flag differs")
            _require({
                "NO_HISTORICAL_CIK_TO_SECURITY_KNOWN_AT",
                "NO_HISTORICAL_VENDOR_VERSION_OR_AVAILABLE_AT",
                "SEC_FIRST_DISSEMINATION_NOT_VERIFIED",
            }.issubset(set(row["review_flags"])),
                     "A required source/research blocker was removed")
            if title_kind != "EXPLICIT_COMMON_STOCK_TITLE":
                _require(title_kind in row["review_flags"],
                         "Non-common original SEC stock title unflagged")
            associated = original_associated_format_issue
            _require(
                ("ASSOCIATED_EXCHANGE_OR_TITLE_FORMAT_TRANSFORMATION_UNINTERPRETED"
                 in row["review_flags"]) is bool(associated),
                "Uninterpreted SEC exchange/title formatting claim was altered",
            )
            if len(report_symbols) > 1:
                _require("OTHER_REPORTED_10K_SECURITIES_REQUIRE_INDEPENDENT_CLASS_REVIEW"
                         in row["review_flags"],
                         "A 10-K containing multiple securities omitted class-review flag")
            counts.update({
                "filings_with_standard_member_without_structural_warning": 1,
                "registered_title_literal_explicit_Common_Stock":
                    int(title_kind == "EXPLICIT_COMMON_STOCK_TITLE"),
                "registered_title_literal_Capital_stock_requires_review":
                    int(title_kind == "CAPITAL_STOCK_TITLE_CLASS_REVIEW"),
                "registered_title_other_requires_review":
                    int(title_kind == "OTHER_REGISTERED_TITLE_CLASS_REVIEW"),
                "same_context_exchange_present": 1,
                "filings_with_multiple_other_SEC_reported_symbols": int(len(report_symbols) > 1),
                "filings_with_format_transformation_caveat": int(bool(associated)),
            })
            by_original[(cik, permno)].append(row)
    _require(sum(map(len, by_original.values())) == len(eligible_cases)
             and len(by_original) == len(pairs),
             "Original eligible common-member filings missing from paired output")
    for group in pairs:
        raw = by_original[(group["issuer_CIK"], group["candidate_PERMNO"])]
        raw.sort(key=lambda r: (r["acceptance_date"], r["accession"]))
        _require(raw == group["filings"],
                 "Paired rows are not chronologically ordered as claimed")
        years = [int(r["acceptance_date"][:4]) for r in raw]
        _require(years == group["filing_years"]
                 and len(raw) == group["original_10k_filing_count"],
                 "Original SEC filing-year pair membership changed")
        if len(raw) == 2 and years[1] == years[0] + 1:
            sym_eq = raw[0]["stock_symbol_raw"] == raw[1]["stock_symbol_raw"]
            title_eq = _words(raw[0]["registered_stock_title_raw"]) == _words(raw[1]["registered_stock_title_raw"])
            exchange_eq = _words(raw[0]["registered_exchange_raw"]) == _words(raw[1]["registered_exchange_raw"])
            expected_state = (
                "TWO_CONSECUTIVE_ORIGINAL_10K_REPORTS_LEXICALLY_STABLE"
                if (sym_eq and title_eq and exchange_eq)
                else "TWO_CONSECUTIVE_REPORTS_LEXICAL_CHANGE_REVIEW"
            )
            counts.update({
                "consecutive_two_filing_issuer_pairs": 1,
                "consecutive_pairs_with_identical_symbol": int(sym_eq),
                "consecutive_pairs_with_normalized_title_match": int(title_eq),
                "consecutive_pairs_with_normalized_exchange_match": int(exchange_eq),
                "consecutive_pairs_with_all_three_stable": int(sym_eq and title_eq and exchange_eq),
            })
        else:
            expected_state = "CONSECUTIVE_TWO_ANNUAL_FILINGS_NOT_ESTABLISHED"
            sym_eq = title_eq = exchange_eq = False
            counts["insufficient_or_nonconsecutive_filing_pairs"] += 1
        _require(expected_state == group["pair_source_stability"]
                 and group["same_original_trading_symbol"] is sym_eq
                 and group["same_normalized_registered_title"] is title_eq
                 and group["same_normalized_exchange_name"] is exchange_eq,
                 "Independent SEC registered-security paired-year evidence differs")
    _require(dict(counts) == public["counts"],
             "Independent original source paired-year totals fail reconciliation")
    _require(_sha(original_sec_path.read_bytes()) == ref["original_sec_gzip"],
             "Original SEC compressed source changed during independent verification")
    result = {
        "schema_version": 1,
        "status": STATUS,
        "independent_source_facts_checked": counts[
            "filings_with_standard_member_without_structural_warning"
        ],
        "independently_rebuilt_issuer_pairs": len(by_original),
        "original_SEC_source_fact_class_and_registered_title_recomputed": True,
        "paired_year_symbol_title_exchange_stability_recomputed": True,
        "source_fingerprints": {
            "previous_private_annual_receipt": _sha(receipt_raw),
            "earlier_class_review_receipt": ref["original_class_receipt"],
            "original_SEC_source_gzip": ref["original_sec_gzip"],
        },
        "direct_original_10K_HTML_reinspection_completed": False,
        "historical_security_class_approved": False,
        "historical_CIK_PERMNO_known_at_established": False,
        "human_review_completed": False, "source_approvals_created": 0,
        "model_ready": False, "final_period_opened": False,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sec-pair-independent-", dir=out.parent) as work:
        staged = Path(work) / "report.json"
        staged.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        staged.replace(out)
    return result
