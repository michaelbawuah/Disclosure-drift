"""Independent DOM-level raw SEC HTML check for the 16 paired stock source cases.

Uses a fresh lxml HTML tree walk, NOT prior cover_evidence fact/context
projections. Matching original SEC lexical source != validated iXBRL taxonomy,
historical link, publication time, or vendor data known-at/available-at.
"""

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

from lxml import etree, html

from .protocol import canonical_hash

STATUS = "INDEPENDENT_CURRENT_SEC_ORIGINAL_DOM_16_STOCK_CONTEXTS_RECONCILED_NOT_APPROVED"
URL_INTAKE = "SEC_16_ORIGINAL_FILINGS_CURRENT_FETCH_BYTE_COMPARISON_NOT_APPROVED"
PAIR_SOURCE = "ORIGINAL_10K_REGISTERED_STOCK_PAIRED_YEAR_REVIEW_NOT_APPROVED"
REPARSE_SOURCE = "SEC_16_CURRENT_ORIGINAL_HTML_REPARSED_AGAINST_PREVIOUS_SOURCE_REPORT_NOT_APPROVED"
_US_GAAP = re.compile(r"http://fasb\.org/us-gaap/[0-9]{4}-[0-9]{2}-[0-9]{2}")
_SEC_DEI = re.compile(r"http://xbrl\.sec\.gov/dei/[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _require(valid, what):
    if not valid:
        raise ValueError(what)


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _file(path, bound):
    raw = Path(path)
    _require(not raw.is_symlink(), "Original source cannot be a symlink")
    source = raw.resolve(strict=True)
    _require(source.is_file() and source.stat().st_size <= bound,
             "Source missing/oversized during independent current SEC DOM check")
    return source.read_bytes()


def _text(node):
    return "".join(node.itertext())


def _is_local(node, suffix):
    return isinstance(node.tag, str) and node.tag.lower().endswith(":" + suffix)


def _source_dom_check(raw_html, source_case, cik, acceptance_date):
    """Independently select matching inline SEC symbol, member, title and exchange."""
    parser = html.HTMLParser(no_network=True, recover=True, huge_tree=False, remove_comments=False)
    try:
        tree = html.fromstring(raw_html, parser=parser)
    except (etree.ParserError, etree.XMLSyntaxError) as error:
        raise ValueError("Original current SEC document could not be parsed as HTML") from error
    _require(tree.attrib.get("xmlns:dei") is not None
             and tree.attrib.get("xmlns:us-gaap") is not None,
             "Original SEC root iXBRL namespace declarations missing")
    _require(_SEC_DEI.fullmatch(str(tree.attrib["xmlns:dei"]))
             and _US_GAAP.fullmatch(str(tree.attrib["xmlns:us-gaap"])),
             "Original SEC lexical DEI/US-GAAP namespace declarations changed")
    requested_symbol = source_case["stock_symbol_raw"]
    context_ref = source_case["source_contextref"]
    matching_symbol_facts = [
        node for node in tree.iter() if _is_local(node, "nonnumeric")
        and node.get("name") == "dei:TradingSymbol"
        and node.get("contextref") == context_ref
        and _text(node) == requested_symbol
    ]
    _require(len(matching_symbol_facts) == 1,
             "SEC DOM does not contain one matching original stock-class symbol fact")
    matching_context = [
        node for node in tree.iter() if _is_local(node, "context")
        and node.get("id") == context_ref
    ]
    _require(len(matching_context) == 1,
             "SEC DOM stock-class context not uniquely identified")
    context = matching_context[0]
    identifiers = [
        node for node in context.iter() if _is_local(node, "identifier")
    ]
    _require(len(identifiers) == 1
             and identifiers[0].get("scheme") == "http://www.sec.gov/CIK"
             and _text(identifiers[0]) == cik,
             "SEC DOM original stock-class context issuer CIK differs")
    period = [
        _text(node) for node in context.iter()
        if _is_local(node, "enddate") or _is_local(node, "instant")
    ]
    _require(period and all(date.fromisoformat(value) <= date.fromisoformat(acceptance_date)
                            for value in period),
             "Original SEC DOM context has invalid/future filing period")
    members = [
        node for node in context.iter()
        if _is_local(node, "explicitmember")
        and node.get("dimension") == "us-gaap:StatementClassOfStockAxis"
    ]
    _require(len(members) == 1 and _text(members[0]).strip() == "us-gaap:CommonStockMember",
             "Original SEC DOM has no unambiguous common-stock member")
    matching_title = [
        node for node in tree.iter() if _is_local(node, "nonnumeric")
        and node.get("name") == "dei:Security12bTitle"
        and node.get("contextref") == context_ref
    ]
    matching_exchange = [
        node for node in tree.iter() if _is_local(node, "nonnumeric")
        and node.get("name") == "dei:SecurityExchangeName"
        and node.get("contextref") == context_ref
    ]
    _require(len(matching_title) == len(matching_exchange) == 1,
             "SEC DOM registered-security original title/exchange ambiguous or missing")
    title, exchange = _text(matching_title[0]), _text(matching_exchange[0])
    _require(title == source_case["registered_stock_title_raw"]
             and exchange == source_case["registered_exchange_raw"],
             "SEC DOM same-context title/exchange differs from original SEC review")
    _require(source_case["source_class_member_qname"] == "us-gaap:CommonStockMember"
             and source_case["historical_security_class_approved"] is False
             and source_case["historical_security_link_known_at"] is None
             and source_case["original_10k_HTML_bytes_reopened_here"] is False,
             "Private SEC original source class link was misrepresented")
    return {
        "source_member_present": True,
        "original_context_identifier_equal": True,
        "original_symbol_fact_equal": True,
        "original_registered_title_equal": True,
        "original_registered_exchange_equal": True,
        "original_source_facts_semantically_validated": False,
    }


def check_current_sec_dom16(intake_dir, first_pair_dir, reparse_dir, output, *,
                            config, repo_root):
    root = Path(repo_root).resolve(strict=True)
    target = Path(output).resolve()
    _require(not target.exists() and target.is_relative_to(root / "reports"),
             "Independent DOM review must be new aggregate report under reports/")
    intake = Path(intake_dir).resolve(strict=True)
    paired = Path(first_pair_dir).resolve(strict=True)
    reparse = Path(reparse_dir).resolve(strict=True)
    intake_public = json.loads(_file(intake / "public_summary.json", 256 * 1024))
    intake_receipt = json.loads(_file(intake / "receipt.json", 256 * 1024))
    intake_private = _file(intake / "private_source_fetch_receipts.json", 256 * 1024)
    _require(intake_public["status"] == intake_receipt["status"] == URL_INTAKE
             and intake_public["new_source_approvals"] == 0
             and intake_public["model_ready"] is False
             and intake_public["final_period_opened"] is False
             and intake_receipt["files"]["private_source_fetch_receipts.json"]["sha256"]
             == _hash(intake_private)
             and intake_public["source_fingerprints"]["frozen_protocol_sha256"] == canonical_hash(config),
             "Original SEC source intake is unpinned or incorrectly approved")
    original_downloads = json.loads(intake_private)
    _require(len(original_downloads) == 16
             and len({x["accession"] for x in original_downloads}) == 16,
             "Source intake doesn't contain the fixed sixteen original filings")
    fetch = {x["accession"]: x for x in original_downloads}
    paired_receipt = json.loads(_file(paired / "receipt.json", 256 * 1024))
    paired_public = json.loads(_file(paired / "public_summary.json", 256 * 1024))
    pair_blob = _file(paired / "private_issuer_pairs.jsonl", 2 * 1024 * 1024)
    _require(paired_public["status"] == paired_receipt["status"] == PAIR_SOURCE
             and paired_public["model_ready"] is False
             and paired_public["final_period_opened"] is False
             and paired_public["source_approvals_created"] == 0
             and paired_receipt["files"]["private_issuer_pairs.jsonl"]["sha256"] == _hash(pair_blob),
             "Original eight-issuer paired-filing evidence changed")
    pairs = [json.loads(line) for line in pair_blob.decode().splitlines()]
    _require(len(pairs) == 8 and sum(len(pair["filings"]) for pair in pairs) == 16,
             "Original SEC paired source cohort unexpectedly changed")
    reparse_public = json.loads(_file(reparse / "public_summary.json", 256 * 1024))
    reparse_receipt = json.loads(_file(reparse / "receipt.json", 256 * 1024))
    _require(reparse_public["status"] == reparse_receipt["status"] == REPARSE_SOURCE
             and reparse_public["all_current_source_lexical_evidence_matches_earlier_verified_packet"] is True
             and reparse_public["historical_link_or_common_stock_class_approved"] is False
             and reparse_public["source_approvals_created"] == 0
             and reparse_public["final_period_opened"] is False
             and reparse_public["source_fingerprints"]["current_source_download_receipt_sha256"]
             == _hash(_file(intake / "receipt.json", 256 * 1024)),
             "Source-verified reparse report is not bound to these current original SEC HTML files")
    counts = Counter()
    by_year = Counter()
    for issuer in pairs:
        _require(issuer["human_approved_historical_class"] is False
                 and issuer["historical_security_identity_known_at"] is None,
                 "Issuer stock-class review status must stay pending")
        for case in issuer["filings"]:
            accession = case["accession"]
            source = fetch.get(accession)
            _require(source is not None and issuer["issuer_CIK"] == source["issuer_CIK"],
                     "Paired original SEC filing isn't among the sixteen fetched originals")
            primary = source["source_files"]["primary"]
            _require(primary["status"] == "HTTP_200_VALID_SIZE"
                     and primary["current_source_availability_as_of_filing"] is False,
                     "Original primary SEC HTML is unavailable or claims historical known-at")
            relative = primary["saved_relative_path"]
            _require(isinstance(relative, str)
                     and relative == f"original_sec_bytes/{accession}.original.html",
                     "SEC original source bundle path is unsupported")
            f = intake / relative
            original = _file(f, 40 * 1024 * 1024)
            _require(primary["current_sha256"] == _hash(original)
                     and primary["current_bytes"] == len(original),
                     "Current SEC original HTML bytes were changed after preservation")
            outcome = _source_dom_check(
                original, case, issuer["issuer_CIK"], case["acceptance_date"]
            )
            _require(all(outcome[k] for k in (
                "source_member_present", "original_context_identifier_equal",
                "original_symbol_fact_equal", "original_registered_title_equal",
                "original_registered_exchange_equal",
            )) and outcome["original_source_facts_semantically_validated"] is False,
                     "Current original SEC DOM fact reinspection does not support source report")
            counts["direct_current_original_SEC_primary_HTML_stock_contexts_confirmed"] += 1
            counts["current_original_primary_SHA_differs_from_earlier_verified_SHA"] += int(
                primary["current_sha256"] != primary["earlier_verified_sha256"]
            )
            by_year[case["acceptance_date"][:4]] += 1
    _require(counts["direct_current_original_SEC_primary_HTML_stock_contexts_confirmed"] == 16
             and len(by_year) >= 1
             and all(2015 <= int(year) <= config["development_end"]
                     and int(year) < config["holdout_start"] for year in by_year),
             "Original SEC review size or years changed")
    final = {
        "schema_version": 1, "status": STATUS,
        "direct_current_original_SEC_html_source_contexts_checked":
            counts["direct_current_original_SEC_primary_HTML_stock_contexts_confirmed"],
        "current_original_primary_source_sha256_mismatch_count":
            counts["current_original_primary_SHA_differs_from_earlier_verified_SHA"],
        "direct_source_facts_and_registered_title_exchange_verified": True,
        "filing_year_counts": dict(sorted(by_year.items())),
        "provenance": {
            "source_intake_private_receipt_sha256": _hash(_file(intake / "receipt.json", 256 * 1024)),
            "previous_pair_source_receipt_sha256": _hash(_file(paired / "receipt.json", 256 * 1024)),
            "earlier_reparser_private_receipt_sha256": _hash(_file(reparse / "receipt.json", 256 * 1024)),
        },
        "original_filing_publication_time_verified": False,
        "historical_issuer_or_stock_class_approved": False,
        "historical_CIK_PERMNO_known_at": None,
        "historical_vendor_data_available_at": None,
        "current_original_html_iXBRL_schema_semantics_validated": False,
        "human_source_reviews_completed": 0, "source_approvals_created": 0,
        "model_ready": False, "final_period_opened": False,
        "interpretation": (
            "Independent direct DOM walk of current official original SEC HTML supports 16 "
            "source lexical symbol/stock-axis/registered-title matches. The earlier byte "
            "hash discrepancy is preserved and neither stock class nor historical "
            "public availability is certified."
        ),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".verify-sec-original-dom-", dir=target.parent) as tmp:
        staged = Path(tmp) / "independent.json"
        staged.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n")
        os.replace(staged, target)
    return final
