"""Independently reconstruct lexical 10-K cover-class context triage totals.

Verifies exact source context references, class QNames, original filer identity,
SEC title/exchange facts and every private case. Not XBRL schema validation.
"""

import gzip
import hashlib
import json
import re
from datetime import date
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from .protocol import canonical_hash

STATUS = "INDEPENDENT_SEC_COVER_CLASS_TRIAGE_RECONCILED_NOT_APPROVED"
FIRST_STATUS = "SEC_COVER_CLASS_LEXICAL_41_CASE_TRIAGE_NOT_APPROVED"


def _must(ok, text):
    if not ok:
        raise ValueError(text)


def _read(path, maximum):
    path = Path(path)
    _must(not path.is_symlink() and path.is_file()
          and path.stat().st_size <= maximum, "Original source file unavailable or too large")
    return path.read_bytes()


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def verify_original_cover_class(class_dir, sec_gzip, result, *, config, repo_root):
    root = Path(repo_root).resolve(strict=True)
    out = Path(result).resolve()
    _must(not out.exists() and out.is_relative_to(root / "reports"),
          "Provide a fresh aggregate verification path under reports/")
    class_dir = Path(class_dir).resolve(strict=True)
    receipt_blob = _read(class_dir / "receipt.json", 150000)
    public_blob = _read(class_dir / "public_summary.json", 150000)
    private_blob = _read(class_dir / "private_context_review.jsonl", 1024 * 1024)
    html_blob = _read(class_dir / "private_context_review.html", 1024 * 1024)
    receipt, public = json.loads(receipt_blob), json.loads(public_blob)
    _must(receipt["status"] == public["status"] == FIRST_STATUS
          and receipt["source_fingerprints"] == public["source_fingerprints"]
          and public["source_fingerprints"]["protocol"] == canonical_hash(config)
          and receipt["approved_security_classes"] == 0
          and receipt["source_approvals"] == 0
          and public["human_reviews_created"] == 0
          and public["source_approvals_created"] == 0
          and public["historical_security_class_approved"] is False
          and public["historical_CIK_to_PERMNO_known_at_established"] is False
          and public["historical_security_validity_intervals_established"] is False
          and public["original_SEC_first_public_dissemination_known"] is False
          and public["market_available_at_established"] is False
          and public["model_ready"] is False and public["final_period_opened"] is False
          and receipt["model_ready"] is False and receipt["final_period_opened"] is False,
          "Original context audit no longer preserves pending research state")
    for name, blob in (
        ("public_summary.json", public_blob),
        ("private_context_review.jsonl", private_blob),
        ("private_context_review.html", html_blob),
    ):
        entry = receipt["files"][name]
        _must(entry["sha256"] == _sha(blob) and entry["bytes"] == len(blob),
              "Private original class-review output fingerprint changed")
    _must(b"<script" not in html_blob.lower()
          and b"XBRL values were NOT semantically validated" in html_blob,
          "Review UI may be active or overstate original XBRL validation")
    rows = [json.loads(line) for line in private_blob.decode().splitlines()]
    ids = [x["observation_id"] for x in rows]
    _must(len(ids) == len(set(ids)) == public["counts"]["reviewed_doubly_corroborated_filings"],
          "Context audit contains duplicate or omitted events")
    source_blob = _read(sec_gzip, 8 * 1024 * 1024)
    _must(_sha(source_blob) == public["source_fingerprints"]["original_sec_gzip"],
          "Verified original SEC source fingerprint differs")
    original = gzip.decompress(source_blob)
    _must(len(original) < 16 * 1024 * 1024
          and _sha(original) == public["source_fingerprints"]["original_sec_source_json"],
          "Decompressed original SEC source hash differs")
    sec = json.loads(original)
    _must(sec["status"] == "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED"
          and sec["protocol_sha256"] == canonical_hash(config)
          and sec["xbrl_fact_values_interpreted"] is False
          and sec["original_sec_bytes_reread"] is True
          and sec["final_period_opened"] is False
          and sec["source_approvals"] == 0
          and len(sec["records"]) == 215,
          "Original SEC source semantics or scope changed")
    documents = {x["accession"]: x for x in sec["records"]}
    _must(len(documents) == 215, "Duplicate SEC source document accession")
    counts = Counter()
    years = defaultdict(Counter)
    for row in rows:
        doc = documents.get(row["observation_id"])
        _must(doc is not None
              and doc["manifest_cik_raw"] == row["original_issuer_CIK"]
              and doc["recorded_acceptance_timestamp"].startswith(row["acceptance_date"])
              and doc["header_identity"]["header_identity_consistent"] is True
              and doc["security_link_created"] is False
              and doc["known_at"] is None and doc["available_at"] is None,
              "Original issuer or known-at differs from source")
        src_cover = doc["cover_evidence"]
        context_by_id = defaultdict(list)
        for context in src_cover["contexts"]:
            context_by_id[context["context_id_raw"]].append(context)
        matches = [
            x for x in src_cover["facts"]
            if x["concept_qname_raw"] == "dei:TradingSymbol"
            and x["text_from_parsed_html"] in set(row["dated_names_symbol_literals"])
        ]
        stored = row["matched_symbol_source_contexts"]
        _must(len(matches) == len(stored) and len(matches) > 0,
              "Original matched SEC cover symbol facts differ from stored triage")
        modes = set()
        issue_present = False
        format_caveat = False
        common_title = False
        any_title_exchange = False
        standard_clean = False
        for fact, assertion in zip(matches, stored, strict=True):
            _must(fact["text_from_parsed_html"] == assertion["trading_symbol"]
                  and fact["contextref_raw"] == assertion["source_contextref"]
                  and assertion["historical_security_class_approved"] is False
                  and assertion["source_XBRL_values_semantically_validated"] is False,
                  "A stored trading-symbol fact is not from its original SEC source")
            ctxs = context_by_id.get(fact["contextref_raw"], [])
            reasons = set()
            if len(ctxs) != 1:
                reasons.add("MISSING_OR_AMBIGUOUS_LEXICAL_CONTEXT")
            context = ctxs[0] if len(ctxs) == 1 else None
            stock_axis = []
            if context:
                _must(assertion["matched_context_ordinal"] == context["context_element_ordinal"],
                      "Original source context ordinal changed")
                if context["context_element_ordinal"] not in fact["context_element_ordinals"]:
                    reasons.add("CONTEXT_ORDINAL_DISAGREEMENT")
                entities = context["entity_identifiers"]
                if (len(entities) != 1 or entities[0].get("scheme_raw") != "http://www.sec.gov/CIK"
                        or entities[0].get("text_from_parsed_html") != row["original_issuer_CIK"]):
                    reasons.add("CONTEXT_ENTITY_IDENTIFIER_MISMATCH")
                period = [
                    value["text_from_parsed_html"] for value in context["period_components"]
                    if value["kind"] in ("enddate", "instant")
                ]
                if not period:
                    reasons.add("CONTEXT_PERIOD_END_ABSENT")
                for period_end in period:
                    is_calendar = True
                    try:
                        date.fromisoformat(period_end)
                    except (TypeError, ValueError):
                        is_calendar = False
                    if not is_calendar or period_end > row["acceptance_date"]:
                        reasons.add("CONTEXT_PERIOD_END_UNSUPPORTED")
                _must(assertion["context_period_end_literals"] == period,
                      "Original SEC context reported period end differs")
                _must(assertion["context_entity_matches_original_filer"] is
                      ("CONTEXT_ENTITY_IDENTIFIER_MISMATCH" not in reasons),
                      "Original SEC context entity CIK outcome differs")
                for dimension in context["dimensions"]:
                    if dimension["dimension_qname_raw"] == "us-gaap:StatementClassOfStockAxis":
                        stock_axis.append(dimension)
                for dimension in stock_axis:
                    axis = dimension["dimension_namespace"]
                    if (not re.fullmatch(r"http://fasb\.org/us-gaap/[0-9]{4}-[0-9]{2}-[0-9]{2}",
                                         str(axis.get("namespace_uri", "")))
                            or axis.get("status") != "DECLARATION_FOUND_IN_PARSED_HTML"):
                        reasons.add("CLASS_AXIS_NAMESPACE_UNVERIFIED")
            else:
                _must(assertion["matched_context_ordinal"] is None,
                      "Missing original context cannot have a matched ordinal")
            standard = any(
                dim["member_namespace"]["qname_raw"] == "us-gaap:CommonStockMember"
                and re.fullmatch(r"http://fasb\.org/us-gaap/[0-9]{4}-[0-9]{2}-[0-9]{2}",
                                 str(dim["member_namespace"].get("namespace_uri", "")))
                and dim["member_namespace"]["status"] == "DECLARATION_FOUND_IN_PARSED_HTML"
                and re.fullmatch(r"http://fasb\.org/us-gaap/[0-9]{4}-[0-9]{2}-[0-9]{2}",
                                 str(dim["dimension_namespace"].get("namespace_uri", "")))
                and dim["dimension_namespace"]["status"] == "DECLARATION_FOUND_IN_PARSED_HTML"
                for dim in stock_axis
            )
            mode = ("STANDARD_GAAP_COMMON_STOCK_MEMBER" if standard else
                    "ISSUER_SPECIFIC_OR_OTHER_CLASS_MEMBER" if stock_axis else
                    "NO_STATEMENT_CLASS_OF_STOCK_AXIS")
            _must(mode == assertion["class_context_mode"],
                  "Original SEC stock-axis QName differs from published category")
            modes.add(mode)
            if fact.get("lexical_issues"):
                reasons.add("SEC_TRADING_SYMBOL_LEXICAL_ISSUE")
            if fact.get("inside_hidden_element") or fact.get("hidden_by_inline_style_observed"):
                reasons.add("SEC_TRADING_SYMBOL_HIDDEN_LEXICAL_CONTEXT")
            if fact.get("nil_attributes_raw"):
                reasons.add("SEC_TRADING_SYMBOL_NIL_ATTRIBUTE")
            concept = fact["concept_namespace"]
            if (concept.get("qname_raw") != "dei:TradingSymbol"
                    or not re.fullmatch(r"http://xbrl\.sec\.gov/dei/[0-9]{4}-[0-9]{2}-[0-9]{2}",
                                        str(concept.get("namespace_uri", "")))
                    or concept.get("status") != "DECLARATION_FOUND_IN_PARSED_HTML"):
                reasons.add("SEC_TRADING_SYMBOL_CONCEPT_NAMESPACE_UNVERIFIED")
            titles = [
                f for f in src_cover["facts"]
                if f["concept_qname_raw"] == "dei:Security12bTitle"
                and f["contextref_raw"] == fact["contextref_raw"]
            ]
            exchanges = [
                f for f in src_cover["facts"]
                if f["concept_qname_raw"] == "dei:SecurityExchangeName"
                and f["contextref_raw"] == fact["contextref_raw"]
            ]
            if not titles:
                reasons.add("SAME_CONTEXT_REGISTERED_SECURITY_TITLE_ABSENT")
            if not exchanges:
                reasons.add("SAME_CONTEXT_EXCHANGE_NAME_ABSENT")
            transformed = False
            for fact2 in titles + exchanges:
                for issue in fact2.get("lexical_issues", []):
                    if issue == "format_transformation_not_interpreted":
                        transformed = True
                    else:
                        reasons.add("ASSOCIATED_TITLE_EXCHANGE_OTHER_LEXICAL_ISSUE")
            parsed_titles = sorted({x["text_from_parsed_html"] for x in titles})
            parsed_exchanges = sorted({x["text_from_parsed_html"] for x in exchanges})
            _must(parsed_titles == assertion["same_context_registered_titles_raw"]
                  and parsed_exchanges == assertion["same_context_exchange_names_raw"],
                  "Original same-context SEC title/exchange facts differ")
            is_common_title = any(bool(re.search(r"\bcommon\s+stock\b", title, re.I))
                                  for title in parsed_titles)
            _must(is_common_title == assertion["same_context_title_common_stock_literal"],
                  "Registered title lexical common-stock claim differs")
            _must(set(assertion["lexical_review_reasons"]) == reasons,
                  "Original context structural review flags were altered")
            expected_transform = {"ASSOCIATED_TITLE_EXCHANGE_FORMAT_NOT_INTERPRETED"} if transformed else set()
            _must(set(assertion["associated_fact_transformation_caveats"]) == expected_transform,
                  "Uninterpreted associated format transformation was hidden or fabricated")
            issue_present |= bool(reasons)
            format_caveat |= transformed
            common_title |= is_common_title
            any_title_exchange |= bool(titles and exchanges)
            standard_clean |= standard and not reasons
            counts["matching_original_SEC_10K_trading_symbol_facts"] += 1
        priority = (
            "STANDARD_COMMON_LEXICAL_CONTEXT_PRESENT"
            if "STANDARD_GAAP_COMMON_STOCK_MEMBER" in modes else
            "ISSUER_SPECIFIC_CLASS_CONTEXT_REQUIRES_INTERPRETATION"
            if "ISSUER_SPECIFIC_OR_OTHER_CLASS_MEMBER" in modes else
            "NO_STANDARD_CLASS_AXIS_REQUIRES_INDEPENDENT_CLASS_EVIDENCE"
        )
        _must(priority == row["source_context_review_group"],
              "Exclusive SEC stock-class review priority changed")
        all_symbols = [
            f for f in src_cover["facts"] if f["concept_qname_raw"] == "dei:TradingSymbol"
        ]
        _must(sorted({f["text_from_parsed_html"] for f in all_symbols})
              == row["original_10k_reported_symbol_literals"],
              "Original SEC TradingSymbol full context evidence not preserved")
        n = len({f["text_from_parsed_html"] for f in all_symbols})
        counts.update({
            "reviewed_doubly_corroborated_filings": 1,
            "filings_with_standard_gaap_CommonStockMember": int(
                "STANDARD_GAAP_COMMON_STOCK_MEMBER" in modes
            ),
            "filings_with_issuer_specific_stock_axis_member": int(
                "ISSUER_SPECIFIC_OR_OTHER_CLASS_MEMBER" in modes
            ),
            "filings_with_matched_symbol_without_stock_axis": int(
                "NO_STATEMENT_CLASS_OF_STOCK_AXIS" in modes
            ),
            "filings_with_matching_same_context_Common_Stock_title_literal": int(common_title),
            "filings_with_matched_symbol_title_and_exchange_in_one_context": int(any_title_exchange),
            "filings_with_multiple_reported_10K_symbols": int(n > 1),
            "filings_with_standard_common_member_and_multiple_reported_symbols": int(
                "STANDARD_GAAP_COMMON_STOCK_MEMBER" in modes and n > 1
            ),
            "filings_with_any_structural_or_lexical_context_warning": int(issue_present),
            "filings_with_uninterpreted_associated_title_exchange_format": int(format_caveat),
            "filings_standard_common_member_without_fact_lexical_warnings": int(standard_clean),
        })
        counts["exclusive_group:" + priority] += 1
        year = int(row["acceptance_date"][:4])
        years[year].update({
            "filings": 1,
            "standard_common_member_present":
                int("STANDARD_GAAP_COMMON_STOCK_MEMBER" in modes),
        })
        _must(row["historical_known_at"] is None
              and row["historical_security_class_approved"] is False
              and row["source_publication_verified"] is False
              and row["source_XBRL_semantics_validated"] is False
              and row["model_ready"] is False,
              "Row-level historical security class falsely approved")
    _must(dict(counts) == public["counts"]
          and {str(k):dict(sorted(v.items())) for k,v in sorted(years.items())}
          == public["year_counts"],
          "Original source independent class/group counts fail reconciliation")
    _must(_sha(_read(sec_gzip, 8 * 1024 * 1024)) == _sha(source_blob),
          "Original SEC source changed during independent verification")
    summary = {
        "schema_version": 1,
        "status": STATUS,
        "independently_checked_doubly_corroborated_filings": len(rows),
        "original_SEC_matching_symbol_contexts_reconstructed": counts[
            "matching_original_SEC_10K_trading_symbol_facts"
        ],
        "full_original_source_facts_and_each_review_flag_verified": True,
        "exclusive_review_groups_and_overlap_counts_recomputed": True,
        "original_SEC_gzip_sha256": _sha(source_blob),
        "first_pass_private_receipt_sha256": _sha(receipt_blob),
        "standard_common_member_filings": counts["filings_with_standard_gaap_CommonStockMember"],
        "source_approvals_created": 0,
        "stock_class_or_CIK_PERMNO_approved": False,
        "historical_known_at_established": False,
        "SEC_first_dissemination_time_established": False,
        "human_reviews_created": 0, "model_ready": False,
        "final_period_opened": False,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".verify-sec-cover-", dir=out.parent) as scratch:
        new = Path(scratch) / "result.json"
        new.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        new.replace(out)
    return summary
