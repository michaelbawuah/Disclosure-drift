"""Reconcile 30 current original SEC Item 1A text boundaries from two source caches.

This is an automated, source-bound, *read-only* reviewer aid, NOT a human
boundary sign-off. The two GE same-document registered ranges are original
source-rule text reproductions, not SHA-identical current original HTML.
No new WRDS data, model/return inputs, or final-period observations.
"""

import csv
import gzip
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

from .extraction import END, START, TOKEN, clean_html, extract_risk_factors
from .protocol import canonical_hash

STATUS = "THIRTY_CURRENT_SEC_ITEM1A_BOUNDARY_EVIDENCE_RECONCILED_HUMAN_REVIEW_PENDING"
ORIGINAL_DIAGNOSTIC = "TARGETED_ORIGINAL_SEC_ITEM1A_16_DOCUMENT_DIAGNOSTIC_NOT_HUMAN_APPROVED"
ORIGINAL_CLASS = "SEC_16_ORIGINAL_FILINGS_CURRENT_FETCH_BYTE_COMPARISON_NOT_APPROVED"
SOURCE_REPORT = "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED"
ALTERNATE = {"0000040545-20-000009", "0000040545-21-000011"}
PINNED_MANIFEST_SHA = "2658b7adfa03ea3c1800afd4107fa74c5348387533abde87cc30c0472b670fb1"
AUDIT_SETS = ("diagnostic", "class")


def _require(ok, why):
    if not ok:
        raise ValueError(why)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _file(path, cap):
    p = Path(path)
    _require(not p.is_symlink(), "Original source file cannot be a symlink")
    src = p.resolve(strict=True)
    _require(src.is_file() and src.stat().st_size <= cap,
             "Original SEC source file missing or over size bound")
    return src, src.read_bytes()


def _sec_url(url, accession, cik):
    if not isinstance(url, str) or not isinstance(cik, str):
        return False
    pieces = urlsplit(url)
    return bool(re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession)) and (
        pieces.scheme == "https" and pieces.netloc == "www.sec.gov"
        and pieces.path.startswith(
            f"/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
        )
        and not pieces.username and not pieces.password
        and not pieces.query and not pieces.fragment
    )


def _load_manifest(folder, config):
    manifest, blob = _file(Path(folder) / "filing_sources.csv", 2 * 1024 * 1024)
    checkpoint = json.loads(_file(Path(folder) / "pilot_checkpoint.json", 128000)[1])
    _require(
        checkpoint["data_kind"] == "REAL_SEC_TEXT_DESCRIPTIVE_PILOT"
        and _sha(blob) == PINNED_MANIFEST_SHA
        and checkpoint["files"]["text_features.csv"]
        and checkpoint["filings"] == 215 and checkpoint["pairs"] == 180
        and checkpoint["protocol_sha256"] == canonical_hash(config)
        and checkpoint["human_filing_reviews"] == 0
        and checkpoint["returns_read"] is False
        and checkpoint["milestone_06_complete"] is False,
        "Original 215 SEC filing manifest source receipt changed or source reviews falsely approved",
    )
    indexed = {}
    with manifest.open(encoding="utf-8-sig", newline="") as input_file:
        reader = csv.DictReader(input_file, strict=True, restkey="EXTRA")
        _require(reader.fieldnames and {
            "accessionNumber", "cik", "source_url", "acceptance_timestamp",
            "download_sha256", "risk_token_count", "resolution_method",
            "extraction_status", "extraction_version", "extraction_start",
            "extraction_end", "risk_source_url",
        }.issubset(reader.fieldnames), "Original SEC manifest missing source/boundary fields")
        for row in reader:
            acc = row["accessionNumber"]
            _require("EXTRA" not in row and None not in row.values()
                     and acc not in indexed
                     and _sec_url(row["source_url"], acc, row["cik"]),
                     "Original SEC manifest contains malformed or duplicate source filing identity")
            indexed[acc] = row
    _require(len(indexed) == 215, "Original SEC source manifest no longer has all 215 filings")
    return indexed, _sha(blob)


def _bound_input_cache_diagnostic(folder):
    folder = Path(folder).resolve(strict=True)
    receipt_raw = _file(folder / "receipt.json", 128000)[1]
    public_raw = _file(folder / "public_summary.json", 128000)[1]
    rows_raw = _file(folder / "private_original_source_rows.jsonl", 200000)[1]
    receipt, public = json.loads(receipt_raw), json.loads(public_raw)
    _require(
        receipt["status"] == public["status"] == ORIGINAL_DIAGNOSTIC
        and receipt["human_approvals"] == 0
        and receipt["model_ready"] is False
        and receipt["final_period_opened"] is False
        and public["manual_original_item1a_boundary_reviews_approved"] is False
        and public["first_publication_known_at_verified"] is False
        and public["model_ready"] is False and public["final_period_opened"] is False
        and receipt["files"]["public_summary.json"]["sha256"] == _sha(public_raw)
        and receipt["files"]["private_original_source_rows.jsonl"]["sha256"] == _sha(rows_raw)
        and public["counts"]["HTTP_200_original_documents"] == 16,
        "Original SEC diagnostic cache no longer has pending source-bound evidence",
    )
    rows = [json.loads(line) for line in rows_raw.decode().splitlines()]
    _require(len(rows) == 16 and len({x["accession"] for x in rows}) == 16,
             "Unexpected original SEC diagnostic cache size/duplicate")
    result = {}
    for item in rows:
        acc = item["accession"]
        _require(item["retrieval_status"] == "HTTP_200_VALID_SIZE"
                 and item["manual_Item1A_boundary_approved"] is False
                 and item["original_SEC_first_publication_at"] is None,
                 "Original 10-K diagnostic filing not fetched or falsely approved")
        original = folder / "original_html" / (acc + ".html")
        _, body = _file(original, 40 * 1024 * 1024)
        _require(_sha(body) == item["current_HTML_sha256"]
                 and len(body) == item["current_HTML_bytes"],
                 "Current SEC diagnostic HTML bytes disagree with their source receipt")
        result[acc] = {
            "cik": item["cik"], "year": item["year"],
            "source_url": item["original_SEC_url"],
            "old_sha": item["earlier_original_HTML_sha256"],
            "new_sha": item["current_HTML_sha256"],
            "source_bytes": len(body),
            "path": original,
            "extraction_status": item["extraction_status"],
            "original_token_count": item["original_source_expected_Item1A_tokens"],
        }
    return result, {
        "receipt_sha256": _sha(receipt_raw),
        "public_sha256": _sha(public_raw),
        "private_rows_sha256": _sha(rows_raw),
    }


def _bound_input_cache_class(folder):
    folder = Path(folder).resolve(strict=True)
    receipt_raw = _file(folder / "receipt.json", 128000)[1]
    public_raw = _file(folder / "public_summary.json", 128000)[1]
    rows_raw = _file(folder / "private_source_fetch_receipts.json", 200000)[1]
    receipt, public = json.loads(receipt_raw), json.loads(public_raw)
    _require(
        receipt["status"] == public["status"] == ORIGINAL_CLASS
        and receipt["model_ready"] is False
        and receipt["final_period_opened"] is False
        and receipt["new_approved_historical_links"] == 0
        and public["new_source_approvals"] == 0
        and public["model_ready"] is False
        and public["final_period_opened"] is False
        and receipt["files"]["public_summary.json"]["sha256"] == _sha(public_raw)
        and receipt["files"]["private_source_fetch_receipts.json"]["sha256"] == _sha(rows_raw)
        and public["retrieved_HTTP_200_source_objects"] == 32,
        "Original SEC paired stock-class cache has incomplete or approved source evidence",
    )
    rows = json.loads(rows_raw)
    _require(len(rows) == 16 and len({x["accession"] for x in rows}) == 16,
             "Original SEC class cache source size/duplication unexpected")
    result = {}
    for row in rows:
        acc = row["accession"]
        info = row["source_files"]["primary"]
        _require(info["status"] == "HTTP_200_VALID_SIZE"
                 and info["current_source_availability_as_of_filing"] is False
                 and info["source_publication_time_verified"] is False
                 and info["saved_relative_path"] == (
                     f"original_sec_bytes/{acc}.original.html"
                 ), "Original SEC class source was not a pending official primary HTML")
        original = folder / info["saved_relative_path"]
        _, body = _file(original, 40 * 1024 * 1024)
        _require(
            _sha(body) == info["current_sha256"]
            and len(body) == info["current_bytes"],
            "Current original SEC stock-class HTML changed since verified current fetch",
        )
        result[acc] = {
            "cik": row["issuer_CIK"], "year": row["acceptance_year"],
            "source_url": info["source_url"],
            "old_sha": info["earlier_verified_sha256"],
            "new_sha": info["current_sha256"],
            "source_bytes": len(body),
            "path": original,
        }
    return result, {
        "receipt_sha256": _sha(receipt_raw),
        "public_sha256": _sha(public_raw),
        "private_rows_sha256": _sha(rows_raw),
    }


def _prior_source_clock(original_report_gzip, original_execution, config):
    _, zipped = _file(original_report_gzip, 8 * 1024 * 1024)
    _, execution_raw = _file(original_execution, 2 * 1024 * 1024)
    pub = json.loads(execution_raw)["publication"]
    _require(pub["sha256"] == _sha(zipped) and pub["bytes"] == len(zipped),
             "Original SEC 215 source-verified report fingerprint changed")
    expanded = gzip.decompress(zipped)
    _require(len(expanded) < 16 * 1024 * 1024
             and pub["uncompressed_sha256"] == _sha(expanded),
             "Original SEC 215-filing decompressed source digest changed")
    source = json.loads(expanded)
    _require(source["status"] == SOURCE_REPORT
             and source["original_sec_bytes_reread"] is True
             and source["source_approvals"] == 0
             and source["final_period_opened"] is False
             and source["xbrl_fact_values_interpreted"] is False
             and source["protocol_sha256"] == canonical_hash(config)
             and len(source["records"]) == 215,
             "Prior original SEC source report no longer records original verified CIK/clock")
    records = {x["accession"]: x for x in source["records"]}
    _require(len(records) == 215, "Duplicated SEC prior accession")
    return records, {
        "original_sec_gzip_sha256": _sha(zipped),
        "original_sec_execution_sha256": _sha(execution_raw),
    }


def _reference_rules(path):
    _, raw = _file(path, 64 * 1024)
    source = json.loads(raw)
    _require(source["schema_version"] == 1
             and source["normalizer_version"] == "item1a-v1",
             "Registered reference resolver schema/normalizer changed")
    rules = {r["accession"]: r for r in source["rules"]}
    _require(len(rules) == len(source["rules"]) and ALTERNATE.issubset(rules),
             "Registered GE original risk source resolution missing or duplicated")
    for accession in ALTERNATE:
        rule = rules[accession]
        _require(
            rule["kind"] == "same_document_range"
            and rule["curation"].startswith("assistant-proposed")
            and "human" in rule["curation"]
            and rule["token_count"] >= 200
            and rule["source_url"] == rule["primary_url"],
            "Registered GE Item1A boundary has been silently treated as a human-approved source",
        )
    return rules, _sha(raw)


def _verify_boundary(body, row, rule=None):
    original_text = clean_html(body)
    raw_result = extract_risk_factors(body)
    start_candidates = list(START.finditer(original_text))
    end_candidates = list(END.finditer(original_text))
    _require(len(start_candidates) >= 1 and len(end_candidates) >= 1,
             "Original SEC current HTML has no Item1A and subsequent Item1B/2 heading")
    if rule is None:
        _require(raw_result.status == "ok"
                 and raw_result.token_count >= 200
                 and raw_result.start_offset is not None
                 and raw_result.end_offset is not None,
                 "Direct SEC Item1A body is not a uniquely selected substantive section")
        actual = raw_result.text
        method = "DIRECT_NUMBERED_ITEM1A_AUTOMATED"
        first = raw_result.start_offset
        last = raw_result.end_offset
        _require(any(x.end() == first for x in start_candidates)
                 and any(x.start() == last for x in end_candidates),
                 "Selected source Item1A range does not align with actual first/next section boundaries")
        _require(row["resolution_method"] == "numbered_item1a"
                 and row["extraction_version"] == raw_result.version,
                 "Direct source Item1A method/version differs from original source record")
    else:
        _require(raw_result.status == "review"
                 and raw_result.token_count < 200
                 and row["resolution_method"] == rule["kind"],
                 "GE referenced SEC Item1A source body was unexpectedly overwritten or claimed direct")
        _require(row["extraction_version"] == "reference-range-v1"
                 and row["source_url"] == rule["source_url"]
                 and row["download_sha256"] == rule["primary_sha256"],
                 "Previously registered GE original source binding modified")
        first, last = rule["start_offset"], rule["end_offset"]
        _require(0 <= first < last <= len(original_text),
                 "Registered alternate Item1A range is outside original HTML normalized text")
        actual = original_text[first:last].strip(" .:-\n")
        _require(_sha(actual.encode()) == rule["text_sha256"]
                 and len(TOKEN.findall(actual)) == rule["token_count"],
                 "Current SEC source no longer reproduces GE original registered risk-section text")
        method = "REGISTERED_GE_SAME_DOCUMENT_RANGE_REPRODUCED_NOT_ORIGINAL_BYTES_IDENTICAL"
    word_count = len(TOKEN.findall(actual))
    _require(word_count == int(row["risk_token_count"]) and word_count >= 200,
             "Source-bound Item1A token count disagrees with original SEC original filing manifest")
    if rule is None:
        _require(word_count == raw_result.token_count
                 and row["extraction_status"] == "ok",
                 "Direct SEC original Item1A extraction status/count changed")
    else:
        _require(row["extraction_status"] == "ok",
                 "Registered source resolution filing not accepted by old SEC source audit")
    return {
        "source_boundary_method": method,
        "risk_text_sha256": _sha(actual.encode()),
        "risk_token_count": word_count,
        "original_full_normalized_HTML_sha256": _sha(original_text.encode()),
        "original_normalized_section_start": first,
        "original_normalized_section_end": last,
        "source_original_risk_heading_count": len(start_candidates),
        "source_original_next_section_heading_count": len(end_candidates),
        "source_extractor_current_status": raw_result.status,
        "source_extractor_current_candidate_count": raw_result.candidate_count,
        "section_start_preview_private": actual[:220],
        "section_end_preview_private": actual[-220:],
        "surrounding_start_private": original_text[max(0, first-125):first],
        "surrounding_end_private": original_text[last:last+145],
        "manual_boundary_and_pair_review_approved": False,
        "original_html_source_semantically_equivalent_to_earlier_version": None,
    }


def _render_review(rows):
    chunks = []
    for item in rows:
        url = item["original_sec_url"]
        description = (
            "Registered GE range (source-text exact)" if item["source_boundary_method"].startswith("REGISTERED")
            else "Direct numbered Item 1A extraction"
        )
        chunks.append(
            f'<details><summary>{escape(item["accession"])} · {escape(str(item["acceptance_year"]))}'
            f' · {escape(description)} · {item["risk_token_count"]:,} risk words</summary>'
            f'<p><b>Original issuer CIK:</b> <code>{escape(item["issuer_CIK"])}</code>'
            f' · <a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">'
            'View original SEC filing</a></p>'
            '<p><b>Start context:</b> <code>'
            f'{escape(item["surrounding_start_private"])}</code></p>'
            '<p><b>First extracted words:</b> <code>'
            f'{escape(item["section_start_preview_private"])}</code></p>'
            '<p><b>Last extracted words:</b> <code>'
            f'{escape(item["section_end_preview_private"])}</code></p>'
            '<p><b>Next section:</b> <code>'
            f'{escape(item["surrounding_end_private"])}</code></p>'
            '<p><b>Source warning:</b> '
            'Current SEC HTML raw SHA differs from prior verified original; '
            'matching extracted risk text does not date source first publication.</p>'
            '<p><strong>Manual boundary and historical known-at: still pending.</strong></p>'
            '</details>'
        )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Original SEC Item 1A – thirty-source boundary review</title>'
        '<style>body{font:15px system-ui;max-width:1000px;margin:38px auto;'
        'padding:0 20px;background:#f6f8fa;color:#1b2d3f;line-height:1.55}'
        'details{background:white;border:1px solid #d3dde8;border-radius:9px;'
        'padding:14px;margin:12px 0;overflow-wrap:anywhere}summary{cursor:pointer;font-weight:600}'
        'code{font-size:13px}a{color:#18509f}</style>'
        '<h1>Thirty original SEC Risk Factors boundary cases</h1>'
        '<p><strong>Source comparison, read-only: no signed human review, '
        'historical source publication or model approval.</strong> '
        'These original 10-Ks were selected for other small pilot reviews, '
        'not a random issuer sample.</p>'
        + "".join(chunks) + '</html>'
    )


def build_original_sec_boundary_matrix(diagnostic, class_bundle, manifest_dir, rules_path,
                                       original_sec_gzip, original_execution, output, *,
                                       config, repo_root):
    repo = Path(repo_root).resolve(strict=True)
    dest = Path(output).resolve()
    _require(not dest.exists() and dest.is_relative_to(repo / "outputs")
             and dest != repo / "outputs", "Output must use a new private outputs path")
    manifest, manifest_sha = _load_manifest(manifest_dir, config)
    diagnostic_rows, diagnostic_hashes = _bound_input_cache_diagnostic(diagnostic)
    class_rows, class_hashes = _bound_input_cache_class(class_bundle)
    original_report, report_hashes = _prior_source_clock(
        original_sec_gzip, original_execution, config
    )
    rules, reference_sha = _reference_rules(rules_path)
    duplicates = set(diagnostic_rows).intersection(class_rows)
    _require(len(diagnostic_rows) == len(class_rows) == 16
             and len(duplicates) == 2
             and len(set(diagnostic_rows) | set(class_rows)) == 30,
             "Expected 30 unique original SEC filings from 32 current source cache records")
    for accession in duplicates:
        a, b = diagnostic_rows[accession], class_rows[accession]
        _require(a["new_sha"] == b["new_sha"]
                 and a["source_bytes"] == b["source_bytes"]
                 and a["path"].read_bytes() == b["path"].read_bytes()
                 and a["old_sha"] == b["old_sha"]
                 and a["source_url"] == b["source_url"],
                 "Duplicate SEC file across two independent caches was not byte-identical")
    output_rows = []
    counts = Counter()
    years = Counter()
    issuer_set = set()
    source_paths = []
    for accession in sorted(set(diagnostic_rows) | set(class_rows)):
        src = diagnostic_rows.get(accession, class_rows.get(accession))
        prior = original_report.get(accession)
        filing = manifest.get(accession)
        _require(prior is not None and filing is not None
                 and prior["manifest_cik_raw"] == filing["cik"] == src["cik"]
                 and prior["recorded_acceptance_timestamp"] == filing["acceptance_timestamp"]
                 and prior["acceptance_date"] == filing["acceptance_date"]
                 and prior["header_identity"]["header_identity_consistent"] is True
                 and prior["known_at"] is None
                 and prior["available_at"] is None
                 and prior["security_link_created"] is False,
                 "Prior verified original SEC issuer CIK/acceptance clock or gate differs")
        _require(
            src["old_sha"] == filing["download_sha256"]
            and prior["primary_source"]["sha256"] == filing["download_sha256"]
            and src["source_url"] == filing["source_url"]
            and _sec_url(src["source_url"], accession, src["cik"])
            and int(filing["acceptance_timestamp"][:4]) < config["holdout_start"],
            "SEC current review source does not bind to the original 215-filing manifest",
        )
        body = src["path"].read_bytes()
        _require(_sha(body) == src["new_sha"], "Current official SEC HTML changed since original review")
        alternate = rules.get(accession) if accession in ALTERNATE else None
        summary = _verify_boundary(body, filing, alternate)
        _require((alternate is not None) == (accession in ALTERNATE),
                 "Non-GE section may not inherit a special registered source range")
        output_rows.append({
            **summary,
            "accession": accession,
            "issuer_CIK": src["cik"],
            "acceptance_year": int(filing["acceptance_timestamp"][:4]),
            "original_SEC_clock": filing["acceptance_timestamp"],
            "original_sec_url": filing["source_url"],
            "origin_cache": ("both" if accession in duplicates
                             else "diagnostic" if accession in diagnostic_rows else "class"),
            "prior_original_html_sha256": src["old_sha"],
            "current_original_html_sha256": src["new_sha"],
            "current_original_html_byte_count": src["source_bytes"],
            "current_source_raw_sha_matches_prior": src["old_sha"] == src["new_sha"],
            "source_available_at_filing": None,
            "historical_security_link_known_at": None,
        })
        years[int(filing["acceptance_timestamp"][:4])] += 1
        issuer_set.add(src["cik"])
        counts["unique_original_SEC_filing_bodies"] += 1
        counts["direct_substantive_item1a_source_boundaries"] += int(alternate is None)
        counts["registered_alternate_source_boundaries"] += int(alternate is not None)
        counts["current_original_HTML_bytes_same_as_earlier_source"] += int(src["old_sha"] == src["new_sha"])
        counts["source_risk_text_token_count_matches_original_manifest"] += 1
        counts["prior_original_SEC_header_CIK_acceptance_clock_verified"] += 1
        counts["auto_document_boundary_review_human_signed"] += 0
        source_paths.append((src["path"], src["new_sha"]))
    _require(counts["unique_original_SEC_filing_bodies"] == 30
             and counts["direct_substantive_item1a_source_boundaries"] == 28
             and counts["registered_alternate_source_boundaries"] == 2,
             "Fixed original SEC selected document boundary cohort changed")
    for path, digest in source_paths:
        _require(_sha(path.read_bytes()) == digest, "One current SEC source HTML changed during review")
    public = {
        "schema_version": 1, "status": STATUS,
        "source_cache_record_count": len(diagnostic_rows) + len(class_rows),
        "identical_duplicate_current_SEC_source_files_in_both_caches": len(duplicates),
        "distinct_issuer_CIK_count": len(issuer_set),
        "source_year_counts": dict(sorted(years.items())),
        "counts": dict(sorted(counts.items())),
        "original_SEC_source_bindings": {
            "protocol_sha256": canonical_hash(config),
            "original_215_manifest_sha256": manifest_sha,
            "registered_resolution_rules_sha256": reference_sha,
            **{"earlier_SEC_"+k:v for k,v in report_hashes.items()},
            **{"diagnostic_"+k:v for k,v in diagnostic_hashes.items()},
            **{"class_"+k:v for k,v in class_hashes.items()},
        },
        "source_status": (
            "Assistant/source registered GE range reproduced by exact text digest; "
            "current full source bytes differ from earlier source fingerprints."
        ),
        "all_current_source_boundaries_human_approved": False,
        "full_universe_filing_review_completed": False,
        "historical_SEC_first_publication_available_at_established": False,
        "historical_CIK_PERMNO_security_link_established": False,
        "stock_returns_read": False,
        "new_source_or_human_approvals": 0,
        "model_ready": False, "final_period_opened": False,
        "interpretation": (
            "Retrospective automated 30-document Item1A extraction QA and "
            "two registered GE special-range text digest checks. "
            "No XBRL semantic assurance, signed human review, publication known-at "
            "or market forecast claims."
        ),
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sec-boundary30-", dir=dest.parent) as tmp:
        staged = Path(tmp) / "review"
        staged.mkdir(mode=0o700)
        (staged / "private_filing_boundaries.jsonl").write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in output_rows)
        )
        (staged / "private_review.html").write_text(_render_review(output_rows))
        (staged / "public_summary.json").write_text(json.dumps(public, sort_keys=True, indent=2) + "\n")
        receipt = {
            "schema_version": 1, "status": STATUS,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_bindings": public["original_SEC_source_bindings"],
            "files": {
                name: {"sha256": _sha((staged / name).read_bytes()),
                       "bytes": (staged / name).stat().st_size}
                for name in ("private_filing_boundaries.jsonl", "private_review.html",
                             "public_summary.json")
            },
            "human_review_approvals": 0,
            "historical_source_availability_approvals": 0,
            "model_ready": False, "final_period_opened": False,
        }
        (staged / "receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        for file in staged.iterdir():
            os.chmod(file, 0o400)
        staged.rename(dest)
    return public
