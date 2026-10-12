"""Source-bound, private paired-year review of SEC 10-K registered-stock literals.

This downstream study does not establish full iXBRL semantics, historical
security mapping, common-stock eligibility, SEC publication time or vendor
historical known-at. Source files remain in private outputs only.
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
from .sec_cover_class_triage import (
    STATUS as INPUT_KIND,
    _source_contexts,
)

STATUS = "ORIGINAL_10K_REGISTERED_STOCK_PAIRED_YEAR_REVIEW_NOT_APPROVED"
STANDARD = "STANDARD_GAAP_COMMON_STOCK_MEMBER"
EXACT_TITLE = re.compile(r"\bcommon\s+stock\b", flags=re.I)
CAPITAL_TITLE = re.compile(r"\bcapital\s+stock\b", flags=re.I)


def _require(test, message):
    if not test:
        raise ValueError(message)


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _original(path, size):
    p = Path(path)
    _require(not p.is_symlink(), "Input cannot be a symlink")
    p = p.resolve(strict=True)
    _require(p.is_file() and p.stat().st_size <= size, "Input absent or beyond size budget")
    return p, p.read_bytes()


def _title_kind(title):
    if not isinstance(title, str):
        return "NO_REGISTERED_TITLE"
    if EXACT_TITLE.search(title):
        return "EXPLICIT_COMMON_STOCK_TITLE"
    if CAPITAL_TITLE.search(title):
        return "CAPITAL_STOCK_TITLE_CLASS_REVIEW"
    if not title.strip():
        return "NO_REGISTERED_TITLE"
    return "OTHER_REGISTERED_TITLE_CLASS_REVIEW"


def _normalized_literal(text):
    """Whitespace/case-only comparison, never a source identifier resolution."""
    return " ".join(text.split()).casefold()


def _secure_sec_url(raw):
    if not isinstance(raw, dict):
        return ""
    value = raw.get("url")
    if not isinstance(value, str):
        return ""
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.netloc != "www.sec.gov"
            or not parsed.path.startswith("/Archives/edgar/data/")
            or parsed.username or parsed.password or parsed.fragment):
        return ""
    return value


def _registered_fact(original, case):
    """Re-match a saved candidate to the source literal CommonStockMember fact."""
    sym = case["trading_symbol"]
    source = _source_contexts(
        original, {sym}, original["manifest_cik_raw"],
        original["recorded_acceptance_timestamp"][:10],
    )
    matches = [
        f for f in source
        if f["trading_symbol"] == sym
        and f["source_contextref"] == case["source_contextref"]
        and f["class_context_mode"] == STANDARD
        and not f["lexical_review_reasons"]
        and f["context_entity_matches_original_filer"]
    ]
    _require(len(matches) == 1, "Previously clean stock-member context is not uniquely supported")
    actual = matches[0]
    for name in (
        "source_contextref", "class_context_mode", "same_context_registered_titles_raw",
        "same_context_exchange_names_raw", "class_members_raw",
        "associated_fact_transformation_caveats", "context_period_end_literals",
    ):
        _require(actual[name] == case[name], f"Prior lexical context differs: {name}")
    _require(actual["source_XBRL_values_semantically_validated"] is False
             and actual["historical_security_class_approved"] is False,
             "Original SEC class facts cannot be treated as approved")
    return actual


def _paired_lexical_stability(rows):
    """Compare two strictly consecutive original annual reports, not inferred links."""
    if len(rows) != 2 or rows[1]["year"] != rows[0]["year"] + 1:
        return {
            "symbol_same": False, "title_same": False, "exchange_same": False,
            "pair_state": "CONSECUTIVE_TWO_ANNUAL_FILINGS_NOT_ESTABLISHED",
            "consecutive": False,
        }
    sym = rows[0]["stock_symbol_raw"] == rows[1]["stock_symbol_raw"]
    title = (
        _normalized_literal(rows[0]["registered_stock_title_raw"])
        == _normalized_literal(rows[1]["registered_stock_title_raw"])
    )
    exch = (
        _normalized_literal(rows[0]["registered_exchange_raw"])
        == _normalized_literal(rows[1]["registered_exchange_raw"])
    )
    return {
        "symbol_same": sym, "title_same": title, "exchange_same": exch,
        "pair_state": (
            "TWO_CONSECUTIVE_ORIGINAL_10K_REPORTS_LEXICALLY_STABLE"
            if sym and title and exch else
            "TWO_CONSECUTIVE_REPORTS_LEXICAL_CHANGE_REVIEW"
        ),
        "consecutive": True,
    }


def _render_review(pairs):
    parts = []
    for pair in pairs:
        filing_cards = []
        for e in pair["filings"]:
            source_links = []
            for name, url in (("Original SEC 10-K", e["original_sec_primary_url"]),
                              ("Original SEC header", e["original_sec_header_url"])):
                if url:
                    source_links.append(
                        f'<a href="{escape(url, quote=True)}" target="_blank"'
                        f' rel="noopener noreferrer">{escape(name)}</a>'
                    )
            issues = "".join(f"<li>{escape(flag)}</li>" for flag in e["review_flags"])
            filing_cards.append(
                f'<details><summary>{escape(e["accession"])}'
                f' · {escape(e["acceptance_date"])}'
                f' · source title {escape(e["title_kind"])}</summary>'
                f'<p>Matched SEC symbol: <code>{escape(e["stock_symbol_raw"])}</code></p>'
                f'<p>Registered title (same context): '
                f'<code>{escape(e["registered_stock_title_raw"])}</code></p>'
                f'<p>Exchange fact (same context): '
                f'<code>{escape(e["registered_exchange_raw"])}</code></p>'
                f'<p>SEC stock class member: '
                f'<code>{escape(e["source_class_member_qname"])}</code></p>'
                f'<p>SEC context reference: '
                f'<code>{escape(e["source_contextref"])}</code></p>'
                f'<p>SEC original URLs: {" · ".join(source_links) if source_links else "not recorded"}</p>'
                f'<h4>Outstanding source caveats</h4><ul>{issues}</ul>'
                '<p><strong>Verdict:</strong> Unreviewed historical identity/class.'
                ' No source known_at, publication time or available_at approval.</p></details>'
            )
        headings = "".join(f"<li>{escape(item)}</li>" for item in pair["pair_review_flags"])
        parts.append(
            f'<section><h2>Issuer CIK <code>{escape(pair["issuer_CIK"])}</code>'
            f' · provisional security <code>{escape(pair["candidate_PERMNO"])}</code></h2>'
            f'<p>Pair result: {escape(pair["pair_source_stability"])}'
            f' · years: {escape(", ".join(str(v) for v in pair["filing_years"]))}</p>'
            f'<ul>{headings}</ul>'
            + "".join(filing_cards) + "</section>"
        )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Disclosure Drift — private annual stock-class review</title>'
        '<style>body{font:15px system-ui;max-width:1020px;'
        'margin:40px auto;padding:0 16px;background:#f5f7fa;color:#1c2d3e;line-height:1.55}'
        'section,details{background:white;border:1px solid #d7e0ea;'
        'border-radius:9px;padding:14px;margin:12px 0;overflow-wrap:anywhere}'
        'details{background:#fcfdff}summary{cursor:pointer;font-weight:600}'
        'code{font-size:13px}h2{font-size:18px}a{color:#1457a5}</style>'
        '<main><h1>Private SEC annual stock-class evidence — read-only</h1>'
        '<p><strong>These are original-source lexical review candidates, not'
        ' class approvals, SEC publication-time evidence, historical link'
        ' validity, or investment return predictions.</strong>'
        ' This page records no human verdicts.</p>'
        + "".join(parts) + "</main></html>"
    )


def _read_source(class_dir, sec_gzip, sec_execution, config):
    bundle = Path(class_dir).resolve(strict=True)
    _, receipt_raw = _original(bundle / "receipt.json", 128 * 1024)
    _, summary_raw = _original(bundle / "public_summary.json", 128 * 1024)
    _, private_raw = _original(bundle / "private_context_review.jsonl", 1024 * 1024)
    receipt, summary = json.loads(receipt_raw), json.loads(summary_raw)
    _require(receipt["status"] == summary["status"] == INPUT_KIND
             and summary["historical_security_class_approved"] is False
             and summary["historical_CIK_to_PERMNO_known_at_established"] is False
             and summary["historical_security_validity_intervals_established"] is False
             and summary["model_ready"] is False and summary["final_period_opened"] is False
             and receipt["approved_security_classes"] == receipt["source_approvals"] == 0
             and receipt["source_fingerprints"] == summary["source_fingerprints"]
             and summary["source_fingerprints"]["protocol"] == canonical_hash(config),
             "Upstream original SEC class review has changed its approval gates")
    for name, data in (("public_summary.json", summary_raw),
                       ("private_context_review.jsonl", private_raw)):
        ref = receipt["files"][name]
        _require(ref["sha256"] == _sha(data) and ref["bytes"] == len(data),
                 "Original SEC class review source hash mismatch")
    cases = [json.loads(line) for line in private_raw.decode().splitlines()]
    _require(len(cases) == summary["counts"]["reviewed_doubly_corroborated_filings"]
             and len(cases) >= 1
             and len({c["observation_id"] for c in cases}) == len(cases),
             "Unexpected source review cohort size/duplication")
    source_path, sec_compressed = _original(sec_gzip, 8 * 1024 * 1024)
    _, sec_execution_raw = _original(sec_execution, 2 * 1024 * 1024)
    publication = json.loads(sec_execution_raw)["publication"]
    _require(publication["sha256"] == _sha(sec_compressed)
             and publication["bytes"] == len(sec_compressed)
             and summary["source_fingerprints"]["original_sec_gzip"] == _sha(sec_compressed)
             and summary["source_fingerprints"]["original_sec_execution"] == _sha(sec_execution_raw),
             "Original 10-K source report no longer matches class review")
    original_raw = gzip.decompress(sec_compressed)
    _require(len(original_raw) < 16 * 1024 * 1024
             and _sha(original_raw) == publication["uncompressed_sha256"]
             and publication["uncompressed_bytes"] == len(original_raw)
             and summary["source_fingerprints"]["original_sec_source_json"] == _sha(original_raw),
             "Original SEC 10-K decompressed source report has changed")
    original = json.loads(original_raw)
    _require(original["status"] == "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED"
             and original["xbrl_fact_values_interpreted"] is False
             and original["source_approvals"] == 0
             and original["final_period_opened"] is False
             and original["original_sec_bytes_reread"] is True
             and original["protocol_sha256"] == canonical_hash(config)
             and len(original["records"]) == 215,
             "Original SEC report is not the frozen lexical-only evidence")
    by_accession = {r["accession"]: r for r in original["records"]}
    _require(len(by_accession) == 215, "Original SEC filing accession IDs are duplicated")
    return (cases, summary, by_accession, {
        "original_class_receipt": _sha(receipt_raw),
        "original_class_private_rows": _sha(private_raw),
        "original_sec_gzip": _sha(sec_compressed),
        "original_sec_execution": _sha(sec_execution_raw),
        "original_sec_json": _sha(original_raw),
        "locked_protocol": canonical_hash(config),
    }, source_path)


def build_paired_stock_class_review(class_dir, sec_gzip, sec_execution, output, *,
                                    config, repo_root):
    repo = Path(repo_root).resolve(strict=True)
    destination = Path(output).resolve()
    _require(not destination.exists() and any(
        destination.is_relative_to(repo / root) and destination != repo / root
        for root in ("data", "outputs")
    ), "Output must be an unused private directory in the research repository")
    _require(not destination.is_relative_to(Path(class_dir).resolve(strict=True)),
             "Output may not be within original source directory")
    cases, initial, originals, fingerprints, source_path = _read_source(
        class_dir, sec_gzip, sec_execution, config
    )
    group = defaultdict(list)
    totals = Counter()
    for row in cases:
        _require(
            row["historical_security_class_approved"] is False
            and row["source_XBRL_semantics_validated"] is False
            and row["historical_known_at"] is None
            and row["source_publication_verified"] is False
            and row["model_ready"] is False,
            "An upstream SEC stock-class candidate incorrectly claims historical approval",
        )
        selected = [
            f for f in row["matched_symbol_source_contexts"]
            if f["class_context_mode"] == STANDARD
            and not f["lexical_review_reasons"]
        ]
        if not selected:
            continue
        _require(len(selected) == 1, "Overlapping standard common-member symbols require review")
        case = selected[0]
        original = originals.get(row["observation_id"])
        _require(original is not None
                 and original["manifest_cik_raw"] == row["original_issuer_CIK"]
                 and original["recorded_acceptance_timestamp"][:10] == row["acceptance_date"]
                 and original["header_identity"]["header_identity_consistent"] is True
                 and original["security_link_created"] is False
                 and original["available_at"] is None
                 and original["known_at"] is None,
                 "Unmatched original 10-K filer/date or forbidden identity/source approval")
        facts = _registered_fact(original, case)
        _require(len(facts["same_context_registered_titles_raw"]) == 1
                 and len(facts["same_context_exchange_names_raw"]) == 1,
                 "Duplicated/absent same-context original security title or exchange")
        title = facts["same_context_registered_titles_raw"][0]
        exchange = facts["same_context_exchange_names_raw"][0]
        _require(title.strip() and exchange.strip(),
                 "Blank original SEC title or exchange on common member")
        acceptance = date.fromisoformat(row["acceptance_date"])
        _require(2015 <= acceptance.year <= config["development_end"]
                 and acceptance.year < config["holdout_start"], "Outside development filing years")
        flags = ["SEC_LEXICAL_CONTEXT_NOT_SEMANTIC_XBRL_CLASS_VALIDATION",
                 "NO_ORIGINAL_10K_HTML_REREAD_IN_THIS_WORKSPACE",
                 "NO_HISTORICAL_CIK_TO_SECURITY_KNOWN_AT",
                 "NO_HISTORICAL_VENDOR_VERSION_OR_AVAILABLE_AT",
                 "SEC_FIRST_DISSEMINATION_NOT_VERIFIED"]
        title_kind = _title_kind(title)
        if title_kind != "EXPLICIT_COMMON_STOCK_TITLE":
            flags.append(title_kind)
        if row["associated_fact_transformation_caveats"]:
            flags.append("ASSOCIATED_EXCHANGE_OR_TITLE_FORMAT_TRANSFORMATION_UNINTERPRETED")
        more_symbols = len(row["original_10k_reported_symbol_literals"]) > 1
        if more_symbols:
            flags.append("OTHER_REPORTED_10K_SECURITIES_REQUIRE_INDEPENDENT_CLASS_REVIEW")
        entry = {
            "accession": row["observation_id"],
            "acceptance_date": row["acceptance_date"],
            "year": acceptance.year,
            "stock_symbol_raw": case["trading_symbol"],
            "registered_stock_title_raw": title,
            "registered_exchange_raw": exchange,
            "title_kind": title_kind,
            "source_contextref": case["source_contextref"],
            "source_class_member_qname": "us-gaap:CommonStockMember",
            "registered_member_namespace_verified": True,
            "original_sec_primary_url": _secure_sec_url(original.get("primary_source")),
            "original_sec_header_url": _secure_sec_url(original.get("header_source")),
            "other_reported_symbols_present": more_symbols,
            "original_sec_class_context_lexically_consistent": True,
            "review_flags": flags,
            "original_10k_HTML_bytes_reopened_here": False,
            "historical_security_class_approved": False,
            "historical_security_link_known_at": None,
            "vendor_market_data_available_at": None,
            "original_sec_public_dissemination_verified": False,
        }
        group[(row["original_issuer_CIK"], row["candidate_CRSP_PERMNO"])].append(entry)
        totals["filings_with_standard_member_without_structural_warning"] += 1
        totals["registered_title_literal_explicit_Common_Stock"] += int(
            title_kind == "EXPLICIT_COMMON_STOCK_TITLE"
        )
        totals["registered_title_literal_Capital_stock_requires_review"] += int(
            title_kind == "CAPITAL_STOCK_TITLE_CLASS_REVIEW"
        )
        totals["registered_title_other_requires_review"] += int(
            title_kind not in ("EXPLICIT_COMMON_STOCK_TITLE", "CAPITAL_STOCK_TITLE_CLASS_REVIEW")
        )
        totals["same_context_exchange_present"] += 1
        totals["filings_with_multiple_other_SEC_reported_symbols"] += int(more_symbols)
        totals["filings_with_format_transformation_caveat"] += int(
            bool(row["associated_fact_transformation_caveats"])
        )
    _require(totals["filings_with_standard_member_without_structural_warning"] ==
             initial["counts"]["filings_standard_common_member_without_fact_lexical_warnings"],
             "Stricter stock member source filter disagrees with original class audit")
    pairs = []
    for (cik, permno), group_rows in sorted(group.items()):
        _require(len({x["accession"] for x in group_rows}) == len(group_rows),
                 "Duplicated original filing accession inside issuer pair")
        source_rows = sorted(group_rows, key=lambda x: (x["acceptance_date"], x["accession"]))
        years = [x["year"] for x in source_rows]
        stability = _paired_lexical_stability(source_rows)
        stable_symbol = stability["symbol_same"]
        stable_title = stability["title_same"]
        stable_exchange = stability["exchange_same"]
        pair_state = stability["pair_state"]
        if stability["consecutive"]:
            totals["consecutive_two_filing_issuer_pairs"] += 1
            totals["consecutive_pairs_with_identical_symbol"] += int(stable_symbol)
            totals["consecutive_pairs_with_normalized_title_match"] += int(stable_title)
            totals["consecutive_pairs_with_normalized_exchange_match"] += int(stable_exchange)
            totals["consecutive_pairs_with_all_three_stable"] += int(
                stable_symbol and stable_title and stable_exchange
            )
        else:
            totals["insufficient_or_nonconsecutive_filing_pairs"] += 1
        pair_flags = [
            "No continuous historical issuer-security validity was inferred",
            "Original SEC filing dissemination and WRDS revision/known-at remain unknown",
            "Cross-year lexical agreement does not create human stock-class approval",
        ]
        if any(x["title_kind"] != "EXPLICIT_COMMON_STOCK_TITLE" for x in source_rows):
            pair_flags.append("Original registered title not literally Common Stock in every filing")
        if any(x["other_reported_symbols_present"] for x in source_rows):
            pair_flags.append("Other security symbols present; preserve original stock-class context")
        if pair_state != "TWO_CONSECUTIVE_ORIGINAL_10K_REPORTS_LEXICALLY_STABLE":
            pair_flags.append("Consecutive original SEC registered-security evidence incomplete or changed")
        pairs.append({
            "issuer_CIK": cik, "candidate_PERMNO": permno,
            "filing_years": years,
            "original_10k_filing_count": len(source_rows),
            "filings": source_rows,
            "pair_source_stability": pair_state,
            "same_original_trading_symbol": stable_symbol,
            "same_normalized_registered_title": stable_title,
            "same_normalized_exchange_name": stable_exchange,
            "pair_review_flags": pair_flags,
            "human_approved_historical_class": False,
            "historical_security_identity_known_at": None,
            "source_release_verified": False,
        })
    _require(sum(len(pair["filings"]) for pair in pairs) ==
             totals["filings_with_standard_member_without_structural_warning"],
             "Not all class records were assigned to their original issuer")
    _require(len(pairs) >= 1, "No original 10-K issuer can be reviewed")
    _require(_sha(source_path.read_bytes()) == fingerprints["original_sec_gzip"],
             "Original SEC source report changed during paired review")
    public = {
        "schema_version": 1,
        "status": STATUS,
        "scope": "purposive 20-issuer development pilot, source-first 41-event class triage",
        "counts": dict(sorted(totals.items())),
        "issuer_pairs_in_first_review": len(pairs),
        "source_fingerprints": fingerprints,
        "source_10k_HTML_bytes_directly_reread_on_this_Mac": False,
        "iXBRL_semantics_validated": False,
        "historical_CIK_to_security_link_approved": False,
        "historical_known_at_established": False,
        "vendor_market_available_at_established": False,
        "original_SEC_public_dissemination_verified": False,
        "human_source_review_completed": False,
        "source_approvals_created": 0,
        "model_ready": False, "final_period_opened": False,
        "interpretation": (
            "Eight issuer-level annual pairs can carry stable original registration-title "
            "lexical observations. Neither matching reported stock symbols nor paired "
            "lexical titles establishes historical identity validity or data availability."
        ),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sec-registered-pair-", dir=destination.parent) as stage_dir:
        stage = Path(stage_dir) / "review"
        stage.mkdir(mode=0o700)
        (stage / "private_issuer_pairs.jsonl").write_text(
            "".join(json.dumps(x, sort_keys=True) + "\n" for x in pairs)
        )
        (stage / "private_review.html").write_text(_render_review(pairs))
        (stage / "public_summary.json").write_text(json.dumps(public, indent=2, sort_keys=True) + "\n")
        receipt = {
            "schema_version": 1, "status": STATUS,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_fingerprints": fingerprints,
            "files": {
                filename: {
                    "sha256": _sha((stage / filename).read_bytes()),
                    "bytes": (stage / filename).stat().st_size,
                }
                for filename in ("private_issuer_pairs.jsonl", "private_review.html",
                                 "public_summary.json")
            },
            "source_approvals": 0, "class_approvals": 0,
            "model_ready": False, "final_period_opened": False,
        }
        (stage / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        for file in stage.iterdir():
            os.chmod(file, 0o400)
        stage.rename(destination)
    return public
