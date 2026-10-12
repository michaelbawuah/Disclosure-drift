"""Conservative 10-K iXBRL stock-class lexical context triage for 41 pilot cases.

Analyses original-SEC-verified but nonvalidating lexical facts, NEVER establishes
a historical security link, SEC dissemination timestamp, or licensed source known_at.
Results containing raw SEC context/CRSP security IDs stay in private ignored outputs.
"""

import gzip
import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

from .protocol import canonical_hash

STATUS = "SEC_COVER_CLASS_LEXICAL_41_CASE_TRIAGE_NOT_APPROVED"
MATRIX_STATUS = "DEVELOPMENT_EVENT_IDENTITY_MATRIX_DESCRIPTORS_NOT_APPROVED"
SEC_STATUS = "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED"
SHA = re.compile(r"[0-9a-f]{64}")
SEC_NS = re.compile(r"^http://xbrl\.sec\.gov/dei/[0-9]{4}-[0-9]{2}-[0-9]{2}$")
US_GAAP_NS = re.compile(r"^http://fasb\.org/us-gaap/[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def _check(ok, why):
    if not ok:
        raise ValueError(why)


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _read(path, *, size):
    given = Path(path)
    _check(not given.is_symlink(), "Source is a symbolic link")
    path = given.resolve(strict=True)
    _check(path.is_file() and path.stat().st_size <= size,
           "Original source file missing or oversized")
    return path, path.read_bytes()


def _full_origin_url(src):
    uri = src.get("url") if isinstance(src, dict) else ""
    if not isinstance(uri, str):
        return ""
    parsed = urlsplit(uri)
    if (parsed.scheme != "https" or parsed.netloc != "www.sec.gov"
            or not parsed.path.startswith("/Archives/edgar/data/")
            or parsed.username or parsed.password or parsed.fragment):
        return ""
    return uri


def _source_contexts(source, name_symbol, filing_cik, acceptance_day):
    """Match symbols to source context by raw contextRef, not class by ticker.

    Standard CommonStockMember is a *lexical QName observation*. No full XBRL
    schema/instance validation or share-class interpretation occurs.
    """
    cover = source["cover_evidence"]
    contexts = defaultdict(list)
    for context in cover["contexts"]:
        contexts[context["context_id_raw"]].append(context)
    facts = cover["facts"]
    matches = []
    for fact in facts:
        if fact["concept_qname_raw"] != "dei:TradingSymbol" or fact["text_from_parsed_html"] not in name_symbol:
            continue
        source_contexts = contexts.get(fact.get("contextref_raw"), [])
        reasons = []
        if len(source_contexts) != 1:
            reasons.append("MISSING_OR_AMBIGUOUS_LEXICAL_CONTEXT")
        context = source_contexts[0] if len(source_contexts) == 1 else None
        member_symbols, context_id = [], fact.get("contextref_raw")
        context_end = []
        if context:
            if context["context_element_ordinal"] not in fact["context_element_ordinals"]:
                reasons.append("CONTEXT_ORDINAL_DISAGREEMENT")
            identifiers = context["entity_identifiers"]
            if (len(identifiers) != 1
                    or identifiers[0].get("scheme_raw") != "http://www.sec.gov/CIK"
                    or identifiers[0].get("text_from_parsed_html") != filing_cik):
                reasons.append("CONTEXT_ENTITY_IDENTIFIER_MISMATCH")
            for period in context["period_components"]:
                if period["kind"] in ("enddate", "instant"):
                    literal = period["text_from_parsed_html"]
                    context_end.append(literal)
                    valid_calendar = True
                    try:
                        date.fromisoformat(literal)
                    except (TypeError, ValueError):
                        valid_calendar = False
                    if not valid_calendar or literal > acceptance_day:
                        reasons.append("CONTEXT_PERIOD_END_UNSUPPORTED")
            if not context_end:
                reasons.append("CONTEXT_PERIOD_END_ABSENT")
            for dimension in context["dimensions"]:
                if dimension["dimension_qname_raw"] == "us-gaap:StatementClassOfStockAxis":
                    m = dimension["member_namespace"]
                    axis = dimension["dimension_namespace"]
                    if not (US_GAAP_NS.fullmatch(str(axis.get("namespace_uri", "")))
                            and axis.get("status") == "DECLARATION_FOUND_IN_PARSED_HTML"):
                        reasons.append("CLASS_AXIS_NAMESPACE_UNVERIFIED")
                    member_symbols.append({
                        "member_qname": m["qname_raw"],
                        "member_namespace": m.get("namespace_uri"),
                        "member_source_status": m["status"],
                        "standard_axis_namespace_verified": bool(
                            US_GAAP_NS.fullmatch(str(axis.get("namespace_uri", "")))
                            and axis.get("status") == "DECLARATION_FOUND_IN_PARSED_HTML"
                        ),
                    })
        common = any(
            x["member_qname"] == "us-gaap:CommonStockMember"
            and US_GAAP_NS.fullmatch(str(x["member_namespace"]))
            and x["member_source_status"] == "DECLARATION_FOUND_IN_PARSED_HTML"
            and x["standard_axis_namespace_verified"] is True
            for x in member_symbols
        )
        mode = ("STANDARD_GAAP_COMMON_STOCK_MEMBER" if common else
                "ISSUER_SPECIFIC_OR_OTHER_CLASS_MEMBER" if member_symbols else
                "NO_STATEMENT_CLASS_OF_STOCK_AXIS")
        if fact.get("lexical_issues"):
            reasons.append("SEC_TRADING_SYMBOL_LEXICAL_ISSUE")
        if fact.get("inside_hidden_element") or fact.get("hidden_by_inline_style_observed"):
            reasons.append("SEC_TRADING_SYMBOL_HIDDEN_LEXICAL_CONTEXT")
        if fact.get("nil_attributes_raw"):
            reasons.append("SEC_TRADING_SYMBOL_NIL_ATTRIBUTE")
        concept_ns = fact.get("concept_namespace", {})
        if (concept_ns.get("qname_raw") != "dei:TradingSymbol"
                or not SEC_NS.fullmatch(str(concept_ns.get("namespace_uri", "")))
                or concept_ns.get("status") != "DECLARATION_FOUND_IN_PARSED_HTML"):
            reasons.append("SEC_TRADING_SYMBOL_CONCEPT_NAMESPACE_UNVERIFIED")
        same_context_title = [
            v for v in facts if v["concept_qname_raw"] == "dei:Security12bTitle"
            and v.get("contextref_raw") == context_id
        ]
        same_context_exchange = [
            v for v in facts if v["concept_qname_raw"] == "dei:SecurityExchangeName"
            and v.get("contextref_raw") == context_id
        ]
        titles = sorted({x["text_from_parsed_html"] for x in same_context_title})
        exchanges = sorted({x["text_from_parsed_html"] for x in same_context_exchange})
        if len(same_context_title) == 0:
            reasons.append("SAME_CONTEXT_REGISTERED_SECURITY_TITLE_ABSENT")
        if len(same_context_exchange) == 0:
            reasons.append("SAME_CONTEXT_EXCHANGE_NAME_ABSENT")
        associated_fact_caveats = []
        for linked in same_context_title + same_context_exchange:
            for lexical_issue in linked.get("lexical_issues", []):
                if lexical_issue == "format_transformation_not_interpreted":
                    # SEC report retains a lexical fact but did not evaluate the
                    # XBRL title/exchange format transformation. Preserve this
                    # separately from an invalid symbol/context relationship.
                    associated_fact_caveats.append("ASSOCIATED_TITLE_EXCHANGE_FORMAT_NOT_INTERPRETED")
                else:
                    reasons.append("ASSOCIATED_TITLE_EXCHANGE_OTHER_LEXICAL_ISSUE")
        common_title_literal = any(re.search(r"\bcommon\s+stock\b", title, re.I) for title in titles)
        matches.append({
            "trading_symbol": fact["text_from_parsed_html"],
            "source_contextref": context_id,
            "matched_context_ordinal": (context["context_element_ordinal"] if context else None),
            "context_entity_matches_original_filer": bool(context) and "CONTEXT_ENTITY_IDENTIFIER_MISMATCH" not in reasons,
            "context_period_end_literals": context_end,
            "class_context_mode": mode,
            "class_members_raw": member_symbols,
            "same_context_registered_titles_raw": titles,
            "same_context_exchange_names_raw": exchanges,
            "same_context_title_common_stock_literal": bool(common_title_literal),
            "lexical_review_reasons": sorted(set(reasons)),
            "associated_fact_transformation_caveats": sorted(set(associated_fact_caveats)),
            "source_XBRL_values_semantically_validated": False,
            "historical_security_class_approved": False,
        })
    return matches


def _triage_group(facts):
    """Exclusive ordering for review, never a success/approval probability."""
    if any(f["class_context_mode"] == "STANDARD_GAAP_COMMON_STOCK_MEMBER" for f in facts):
        return "STANDARD_COMMON_LEXICAL_CONTEXT_PRESENT"
    if any(f["class_context_mode"] == "ISSUER_SPECIFIC_OR_OTHER_CLASS_MEMBER" for f in facts):
        return "ISSUER_SPECIFIC_CLASS_CONTEXT_REQUIRES_INTERPRETATION"
    return "NO_STANDARD_CLASS_AXIS_REQUIRES_INDEPENDENT_CLASS_EVIDENCE"


def _render_private(entries, sec_records):
    parts = []
    grouped = defaultdict(list)
    for item in entries:
        grouped[item["source_context_review_group"]].append(item)
    for group, items in sorted(grouped.items()):
        cards = []
        for item in items:
            facts = []
            for source_fact in item["matched_symbol_source_contexts"]:
                reasons = ", ".join(source_fact["lexical_review_reasons"]) or "No symbol/context structural issue observed"
                caveats = ", ".join(source_fact["associated_fact_transformation_caveats"]) or "None recorded"
                members = ", ".join(x["member_qname"] for x in source_fact["class_members_raw"]) or "No stock-class axis"
                facts.append(
                    '<div class="fact">'
                    f'<p><b>Exact source symbol:</b> {escape(source_fact["trading_symbol"])}'
                    f' · <b>Lexical class context:</b> {escape(source_fact["class_context_mode"])}</p>'
                    f'<p><b>Context Ref:</b> <code>{escape(str(source_fact["source_contextref"]))}</code></p>'
                    f'<p><b>Member QName:</b> <code>{escape(members)}</code></p>'
                    f'<p><b>Security title (same context):</b>'
                    f' {escape("; ".join(source_fact["same_context_registered_titles_raw"]) or "(not observed)")}</p>'
                    f'<p><b>Exchange fact (same context):</b>'
                    f' {escape("; ".join(source_fact["same_context_exchange_names_raw"]) or "(not observed)")}</p>'
                    f'<p><b>Symbol/context review:</b> {escape(reasons)}</p>'
                    f'<p><b>Associated title/exchange transformation caveats:</b> {escape(caveats)}</p>'
                    '</div>'
                )
            sec = sec_records[item["observation_id"]]
            urls = []
            for kind in ("primary_source", "header_source"):
                url = _full_origin_url(sec.get(kind))
                if url:
                    urls.append(f'<a href="{escape(url, quote=True)}" target="_blank" '
                                f'rel="noopener noreferrer">{escape(kind.replace("_", " "))}</a>')
            cards.append(
                f'<details><summary>{escape(item["observation_id"])}'
                f' · {escape(item["acceptance_date"])}'
                f' · {len(item["matched_symbol_source_contexts"])} matching symbol contexts</summary>'
                f'<p><b>Original issuer CIK:</b> {escape(item["original_issuer_CIK"])}'
                f' · <b>Provisional security PERMNO:</b> {escape(item["candidate_CRSP_PERMNO"])}</p>'
                f'<p><b>Original SEC sources:</b> {" · ".join(urls) if urls else "not available in report"}</p>'
                + "".join(facts)
                + '<p><b>Verdict:</b> Pending. Exact source and stock-class review required. '
                'No known_at/available_at established.</p></details>'
            )
        parts.append(f'<h2>{escape(group)} · {len(items)} filings</h2>' + "".join(cards))
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Disclosure Drift: Original SEC 10-K Stock-Class Lexical Review</title>'
        '<style>body{font:15px system-ui;background:#f6f7fa;color:#1c2936;'
        'max-width:1050px;margin:36px auto;padding:0 20px;line-height:1.5}'
        'details{border:1px solid #d7dce4;border-radius:9px;'
        'padding:13px;background:#fff;margin:12px 0;overflow-wrap:anywhere}'
        '.fact{background:#f7f9fa;border-left:3px solid #c6d4e2;'
        'margin:12px 0;padding:7px 12px}summary{cursor:pointer;font-weight:600}'
        'code{font-size:13px}a{color:#2052a0}</style>'
        '<h1>Original SEC 10-K lexical stock-class review: 41 cases</h1>'
        '<p><strong>Read-only, not research approval.</strong> Context and title'
        ' matches are from a previously verified original SEC report whose'
        ' XBRL values were NOT semantically validated. No continuous historical'
        ' CIK-to-PERMNO known-at, historical security-class adjudication or'
        ' public dissemination timestamp has been established.</p>'
        + "".join(parts) + '</html>'
    )


def run_cover_class_triage(matrix_dir, sec_gzip, sec_execution, destination, *,
                           config, repo_root):
    repo = Path(repo_root).resolve(strict=True)
    out = Path(destination).resolve()
    _check(not out.exists() and any(out.is_relative_to(repo / p) and out != repo / p
                                    for p in ("outputs", "data")),
           "Output must be unused private path within the repository")
    matrix_dir = Path(matrix_dir).resolve(strict=True)
    _check(not out.is_relative_to(matrix_dir), "Output cannot nest in the original matrix")
    _, receipt_bytes = _read(matrix_dir / "receipt.json", size=250000)
    _, summary_bytes = _read(matrix_dir / "public_summary.json", size=250000)
    _, queue_bytes = _read(matrix_dir / "review_queue_private.jsonl", size=2 * 1024 * 1024)
    receipt, matrix = json.loads(receipt_bytes), json.loads(summary_bytes)
    _check(receipt["status"] == matrix["status"] == MATRIX_STATUS
           and receipt["source_bindings"] == matrix["provenance"]
           and matrix["model_ready"] is False
           and matrix["final_period_opened"] is False
           and receipt["model_ready"] is False
           and receipt["final_period_opened"] is False
           and receipt["source_approvals"] == 0
           and receipt["historical_links_approved"] == 0,
           "Source matrix does not preserve original closed research gates")
    for name, blob in (("public_summary.json", summary_bytes),
                       ("review_queue_private.jsonl", queue_bytes)):
        _check(receipt["files"][name]["sha256"] == _sha(blob)
               and receipt["files"][name]["bytes"] == len(blob),
               "Matrix source receipts and original bytes are not identical")
    rows = [json.loads(x) for x in queue_bytes.decode().splitlines()]
    by_event = {x["observation_id"]: x for x in rows}
    _check(len(by_event) == len(rows) == matrix["counts"]["events"] == 135,
           "Original M5 event population missing or repeated")
    _check(all(
        x["historical_CIK_to_PERMNO_approved"] is False
        and x["historical_known_at"] is None
        and x["market_available_at"] is None
        and x["model_ready"] is False
        and x["source_release_verified"] is False
        for x in rows
    ), "Original development matrix event-level approval gates were changed")
    original_gzip, original_gzip_bytes = _read(sec_gzip, size=8 * 1024 * 1024)
    original_exec, original_exec_bytes = _read(sec_execution, size=2 * 1024 * 1024)
    pub = json.loads(original_exec_bytes)["publication"]
    _check(pub["sha256"] == _sha(original_gzip_bytes)
           and pub["bytes"] == len(original_gzip_bytes)
           and matrix["provenance"]["sec_identity_gzip"] == _sha(original_gzip_bytes)
           and matrix["provenance"]["sec_identity_execution"] == _sha(original_exec_bytes),
           "Pinned original SEC gzip/execution report disagrees")
    sec_bytes = gzip.decompress(original_gzip_bytes)
    _check(len(sec_bytes) <= 16 * 1024 * 1024
           and pub["uncompressed_sha256"] == _sha(sec_bytes)
           and pub["uncompressed_bytes"] == len(sec_bytes)
           and matrix["provenance"]["sec_identity_original_json"] == _sha(sec_bytes),
           "Original SEC report changed or exceeded safety limit")
    sec = json.loads(sec_bytes)
    _check(sec["status"] == SEC_STATUS and sec["protocol_sha256"] == canonical_hash(config)
           and sec["original_sec_bytes_reread"] is True
           and sec["xbrl_fact_values_interpreted"] is False
           and sec["source_approvals"] == 0 and sec["final_period_opened"] is False,
           "Original SEC report claims unverified XBRL or final release status")
    originals = {x["accession"]: x for x in sec["records"]}
    _check(len(originals) == len(sec["records"]) == 215,
           "Original SEC record count or accession uniqueness changed")
    selected = [x for x in rows if (
        x["2019q4_issuer_anchor_reported_before_10k"] and x["original_10k_symbol_fact_count"] > 0
    )]
    _check(len(selected) == matrix["counts"][
        "events_with_both_prior_Q4_filing_date_anchor_and_10K_cover_symbol"
    ], "Doubly corroborated review population differs from frozen source matrix")
    out_rows = []
    counts = Counter()
    by_year = defaultdict(Counter)
    for candidate in sorted(selected, key=lambda x: x["observation_id"]):
        orig = originals.get(candidate["observation_id"])
        _check(orig is not None and orig["manifest_cik_raw"] == candidate["original_SEC_CIK"]
               and orig["recorded_acceptance_timestamp"] == candidate["acceptance_timestamp"]
               and orig["header_identity"]["header_identity_consistent"] is True
               and orig["available_at"] is None and orig["known_at"] is None
               and orig["security_link_created"] is False,
               "Original 10-K issuer/clock/gates mismatch")
        accepts = datetime.fromisoformat(candidate["acceptance_timestamp"].replace("Z", "+00:00"))
        _check(accepts.utcoffset() is not None and accepts.year <= config["development_end"]
               and accepts.year < config["holdout_start"],
               "Outside-development SEC source data forbidden")
        facts = _source_contexts(
            orig, set(candidate["observed_names_trading_symbols_raw"]),
            candidate["original_SEC_CIK"], candidate["acceptance_timestamp"][:10]
        )
        _check(facts and len(facts) <= candidate["original_10k_symbol_fact_count"],
               "Original SEC expected matching symbol facts not found")
        kind = _triage_group(facts)
        year = candidate["year"]
        observed_modes = {f["class_context_mode"] for f in facts}
        all_symbols = [
            f for f in orig["cover_evidence"]["facts"]
            if f["concept_qname_raw"] == "dei:TradingSymbol"
        ]
        lexical_reasons = sorted({reason for f in facts for reason in f["lexical_review_reasons"]})
        format_caveats = sorted({
            reason for f in facts for reason in f["associated_fact_transformation_caveats"]
        })
        common = any(f["same_context_title_common_stock_literal"] for f in facts)
        both_title_exchange = any(
            f["same_context_registered_titles_raw"] and
            f["same_context_exchange_names_raw"] for f in facts
        )
        counts.update({
            "reviewed_doubly_corroborated_filings": 1,
            "matching_original_SEC_10K_trading_symbol_facts": len(facts),
            "filings_with_standard_gaap_CommonStockMember": int(
                "STANDARD_GAAP_COMMON_STOCK_MEMBER" in observed_modes
            ),
            "filings_with_issuer_specific_stock_axis_member": int(
                "ISSUER_SPECIFIC_OR_OTHER_CLASS_MEMBER" in observed_modes
            ),
            "filings_with_matched_symbol_without_stock_axis": int(
                "NO_STATEMENT_CLASS_OF_STOCK_AXIS" in observed_modes
            ),
            "filings_with_matching_same_context_Common_Stock_title_literal": int(common),
            "filings_with_matched_symbol_title_and_exchange_in_one_context": int(both_title_exchange),
            "filings_with_multiple_reported_10K_symbols": int(
                len({x["text_from_parsed_html"] for x in all_symbols}) > 1
            ),
            "filings_with_standard_common_member_and_multiple_reported_symbols": int(
                "STANDARD_GAAP_COMMON_STOCK_MEMBER" in observed_modes
                and len({x["text_from_parsed_html"] for x in all_symbols}) > 1
            ),
            "filings_with_any_structural_or_lexical_context_warning": int(bool(lexical_reasons)),
            "filings_with_uninterpreted_associated_title_exchange_format": int(bool(format_caveats)),
            "filings_standard_common_member_without_fact_lexical_warnings": int(
                any(f["class_context_mode"] == "STANDARD_GAAP_COMMON_STOCK_MEMBER"
                    and not f["lexical_review_reasons"] for f in facts)
            ),
        })
        counts["exclusive_group:" + kind] += 1
        by_year[year]["filings"] += 1
        by_year[year]["standard_common_member_present"] += int(
            "STANDARD_GAAP_COMMON_STOCK_MEMBER" in observed_modes
        )
        out_rows.append({
            "observation_id": candidate["observation_id"],
            "acceptance_date": candidate["acceptance_timestamp"][:10],
            "original_issuer_CIK": candidate["original_SEC_CIK"],
            "candidate_CRSP_PERMNO": candidate["candidate_CRSP_PERMNO"],
            "original_10k_reported_symbol_literals": sorted({
                f["text_from_parsed_html"] for f in all_symbols
            }),
            "dated_names_symbol_literals": candidate["observed_names_trading_symbols_raw"],
            "source_context_review_group": kind,
            "matched_symbol_source_contexts": facts,
            "source_warning_flags": lexical_reasons,
            "associated_fact_transformation_caveats": format_caveats,
            "original_SEC_bytes_reread_here": False,
            "source_XBRL_semantics_validated": False,
            "historical_security_class_approved": False,
            "historical_known_at": None,
            "source_publication_verified": False,
            "model_ready": False,
        })
    _check(counts["reviewed_doubly_corroborated_filings"] == len(selected)
           and len({x["observation_id"] for x in out_rows}) == len(selected),
           "Corroborated source row count differs from original sample")
    _check(_sha(original_gzip.read_bytes()) == _sha(original_gzip_bytes)
           and _sha(original_exec.read_bytes()) == _sha(original_exec_bytes),
           "Original SEC identity source changed after reading")
    summary = {
        "schema_version": 1, "status": STATUS,
        "research_scope": "2015-2021 purposive original pilot; 2019Q4 Q4 issuer anchor and cover-symbol intersection",
        "counts": dict(sorted(counts.items())),
        "year_counts": {str(k): dict(sorted(v.items())) for k, v in sorted(by_year.items())},
        "source_fingerprints": {
            "previous_private_matrix_receipt": _sha(receipt_bytes),
            "previous_matrix_event_rows": _sha(queue_bytes),
            "original_sec_gzip": _sha(original_gzip_bytes),
            "original_sec_execution": _sha(original_exec_bytes),
            "original_sec_source_json": _sha(sec_bytes),
            "protocol": canonical_hash(config),
        },
        "historical_security_class_approved": False,
        "lexical_source_contexts_not_validating_XBRL_processor": True,
        "historical_CIK_to_PERMNO_known_at_established": False,
        "historical_security_validity_intervals_established": False,
        "original_SEC_first_public_dissemination_known": False,
        "market_available_at_established": False,
        "source_approvals_created": 0, "human_reviews_created": 0,
        "model_ready": False, "final_period_opened": False,
        "interpretation": "Lexical explicit-member/SEC title context corroboration, not approved security class, effective interval or historical source publication.",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".cover-stock-class-", dir=out.parent) as scratch:
        stage = Path(scratch) / "result"
        stage.mkdir(mode=0o700)
        (stage / "private_context_review.jsonl").write_text(
            "".join(json.dumps(x, sort_keys=True) + "\n" for x in out_rows)
        )
        (stage / "private_context_review.html").write_text(_render_private(out_rows, originals))
        (stage / "public_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        receipt = {
            "schema_version": 1, "status": STATUS,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_fingerprints": summary["source_fingerprints"],
            "files": {filename: {"sha256": _sha((stage / filename).read_bytes()),
                                 "bytes": (stage / filename).stat().st_size}
                      for filename in (
                          "private_context_review.jsonl", "private_context_review.html",
                          "public_summary.json",
                      )},
            "approved_security_classes": 0, "source_approvals": 0,
            "model_ready": False, "final_period_opened": False,
        }
        (stage / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        for p in stage.iterdir():
            os.chmod(p, 0o400)
        stage.rename(out)
    return summary
