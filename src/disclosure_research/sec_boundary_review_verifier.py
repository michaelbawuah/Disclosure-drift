"""Independent raw-source reproduction of the private 30-original Item 1A dossier.

Rereads current original SEC HTMLs from both preserved caches, compares
selected source boundaries to original 215-filing manifest, original SEC
header/CIK report, and the previously registered GE *text* digests.
Independence is in source relations and range arithmetic, not an alternate
human or semantic SEC section parser. No approvals are created.
"""

import csv
import gzip
import hashlib
import json
import tempfile
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from .extraction import END, START, TOKEN, clean_html, extract_risk_factors
from .protocol import canonical_hash

STATUS = "INDEPENDENT_THIRTY_CURRENT_ORIGINAL_SEC_ITEM1A_BOUNDARIES_REPRODUCED_PENDING_REVIEW"
UPSTREAM = "THIRTY_CURRENT_SEC_ITEM1A_BOUNDARY_EVIDENCE_RECONCILED_HUMAN_REVIEW_PENDING"
GE_CASES = ("0000040545-20-000009", "0000040545-21-000011")


def _check(ok, reason):
    if not ok:
        raise ValueError(reason)


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _read(path, cap):
    p = Path(path)
    _check(not p.is_symlink(), "Linked original SEC source forbidden")
    p = p.resolve(strict=True)
    _check(p.is_file() and p.stat().st_size <= cap,
           "Original SEC primary file missing or oversized")
    return p.read_bytes()


def _official_url(url, cik, accession):
    p = urlsplit(url)
    return (
        p.scheme == "https" and p.netloc == "www.sec.gov"
        and p.path.startswith(
            f"/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
        )
        and not p.username and not p.password and not p.query and not p.fragment
    )


def independent_boundary_source_recheck(diagnostic, class_bundle, source_dir,
                                        reference_json, prior_sec_gzip, original_dir,
                                        output, *, config, repo_root):
    repo = Path(repo_root).resolve(strict=True)
    report_path = Path(output).resolve()
    _check(not report_path.exists() and report_path.is_relative_to(repo / "reports"),
           "Independent boundary recheck must use fresh public reports path")
    root = Path(original_dir).resolve(strict=True)
    receipt_raw = _read(root / "receipt.json", 128000)
    public_raw = _read(root / "public_summary.json", 128000)
    private_raw = _read(root / "private_filing_boundaries.jsonl", 256000)
    html_raw = _read(root / "private_review.html", 256000)
    receipt, summary = json.loads(receipt_raw), json.loads(public_raw)
    _check(
        receipt["status"] == summary["status"] == UPSTREAM
        and receipt["source_bindings"] == summary["original_SEC_source_bindings"]
        and summary["original_SEC_source_bindings"]["protocol_sha256"] == canonical_hash(config)
        and receipt["model_ready"] is False and receipt["final_period_opened"] is False
        and receipt["human_review_approvals"] == 0
        and receipt["historical_source_availability_approvals"] == 0
        and summary["all_current_source_boundaries_human_approved"] is False
        and summary["historical_SEC_first_publication_available_at_established"] is False
        and summary["historical_CIK_PERMNO_security_link_established"] is False
        and summary["new_source_or_human_approvals"] == 0
        and summary["stock_returns_read"] is False
        and summary["model_ready"] is False and summary["final_period_opened"] is False,
        "Filing-level boundary packet falsely signals approval or is not the original source bundle",
    )
    for name, data in (
        ("public_summary.json", public_raw),
        ("private_filing_boundaries.jsonl", private_raw),
        ("private_review.html", html_raw),
    ):
        pin = receipt["files"][name]
        _check(pin["sha256"] == _sha(data) and pin["bytes"] == len(data),
               "SEC original source-bound private output fingerprint changed")
    _check(b"<script" not in html_raw.lower() and b"read-only" in html_raw.lower(),
           "Private SEC boundary reading page is interactive or missing pending label")
    source_pins = summary["original_SEC_source_bindings"]
    manifest_raw = _read(Path(source_dir) / "filing_sources.csv", 2 * 1024 * 1024)
    _check(_sha(manifest_raw) == source_pins["original_215_manifest_sha256"],
           "Original SEC 215 filing manifest changed")
    source_manifest = {}
    for entry in csv.DictReader(manifest_raw.decode("utf-8-sig").splitlines()):
        key = entry["accessionNumber"]
        _check(key not in source_manifest, "SEC historical manifest duplicate accession")
        source_manifest[key] = entry
    _check(len(source_manifest) == 215,
           "Original SEC 215 source rows no longer complete")
    rule_raw = _read(reference_json, 64 * 1024)
    _check(_sha(rule_raw) == source_pins["registered_resolution_rules_sha256"],
           "Original GE registered boundary instructions changed")
    rules = json.loads(rule_raw)
    by_acc = {record["accession"]: record for record in rules["rules"]}
    _check(len(by_acc) == len(rules["rules"]) and set(GE_CASES).issubset(by_acc),
           "Original GE source resolution missing")
    prior_blob = _read(prior_sec_gzip, 8 * 1024 * 1024)
    _check(_sha(prior_blob) == source_pins["earlier_SEC_original_sec_gzip_sha256"],
           "Previously source-audited SEC report has changed")
    prior_unpacked = gzip.decompress(prior_blob)
    _check(len(prior_unpacked) < 16 * 1024 * 1024,
           "SEC prior original source report unexpectedly expanded")
    original_docs = json.loads(prior_unpacked)
    _check(
        original_docs["status"] == "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED"
        and original_docs["source_approvals"] == 0
        and original_docs["final_period_opened"] is False
        and original_docs["original_sec_bytes_reread"] is True
        and original_docs["protocol_sha256"] == canonical_hash(config)
        and len(original_docs["records"]) == 215,
        "Original SEC 215-filing source proof doesn't retain its audit restrictions",
    )
    prior = {x["accession"]: x for x in original_docs["records"]}
    _check(len(prior) == 215, "Original SEC source report duplicate accession")
    rows = [json.loads(line) for line in private_raw.decode().splitlines()]
    _check(len(rows) == summary["counts"]["unique_original_SEC_filing_bodies"] == 30
           and len({x["accession"] for x in rows}) == 30,
           "Original SEC reviewed-document identity/quantity changed")
    source_dir_by_kind = {
        "diagnostic": Path(diagnostic).resolve(strict=True),
        "class": Path(class_bundle).resolve(strict=True),
    }
    details = {
        "diagnostic": (
            _read(source_dir_by_kind["diagnostic"] / "private_original_source_rows.jsonl", 200000),
            _read(source_dir_by_kind["diagnostic"] / "receipt.json", 128000),
        ),
        "class": (
            _read(source_dir_by_kind["class"] / "private_source_fetch_receipts.json", 200000),
            _read(source_dir_by_kind["class"] / "receipt.json", 128000),
        ),
    }
    for kind, (source_rows, source_receipt) in details.items():
        _check(
            _sha(source_rows) == source_pins[kind + "_private_rows_sha256"]
            and _sha(source_receipt) == source_pins[kind + "_receipt_sha256"],
            "Original 16-filing SEC source-cache inputs differ from source-bound review",
        )
    lookup = {
        "diagnostic": {
            x["accession"]: x for x in (
                json.loads(line) for line in details["diagnostic"][0].decode().splitlines()
            )
        },
        "class": {
            x["accession"]: x for x in json.loads(details["class"][0])
        },
    }
    _check(len(lookup["diagnostic"]) == len(lookup["class"]) == 16,
           "Original dual-source evidence coverages changed")
    counters = Counter()
    year_counts = Counter()
    issuers = set()
    for entry in rows:
        acc = entry["accession"]
        saved = source_manifest[acc]
        original = prior[acc]
        _check(
            entry["issuer_CIK"] == saved["cik"] == original["manifest_cik_raw"]
            and entry["original_sec_url"] == saved["source_url"]
            and _official_url(saved["source_url"], saved["cik"], acc)
            and entry["original_SEC_clock"] == saved["acceptance_timestamp"]
            == original["recorded_acceptance_timestamp"]
            and original["known_at"] is None
            and original["available_at"] is None
            and original["security_link_created"] is False
            and original["header_identity"]["header_identity_consistent"] is True
            and entry["manual_boundary_and_pair_review_approved"] is False
            and entry["source_available_at_filing"] is None
            and entry["historical_security_link_known_at"] is None,
            "Source-bound original SEC identity/clock or unapproved research gates changed",
        )
        kinds = ("diagnostic", "class") if entry["origin_cache"] == "both" else (entry["origin_cache"],)
        source_blobs = []
        for kind in kinds:
            hit = lookup[kind][acc]
            if kind == "diagnostic":
                _check(hit["retrieval_status"] == "HTTP_200_VALID_SIZE"
                       and hit["manual_Item1A_boundary_approved"] is False
                       and hit["original_SEC_first_publication_at"] is None,
                       "Original SEC diagnostic source falsely passed review")
                source = source_dir_by_kind["diagnostic"] / "original_html" / (acc + ".html")
                expected_new = hit["current_HTML_sha256"]
                expected_old = hit["earlier_original_HTML_sha256"]
            else:
                r = hit["source_files"]["primary"]
                _check(r["status"] == "HTTP_200_VALID_SIZE"
                       and r["source_publication_time_verified"] is False,
                       "Original SEC class source not an unapproved 200 source")
                source = source_dir_by_kind["class"] / "original_sec_bytes" / (acc + ".original.html")
                expected_new = r["current_sha256"]
                expected_old = r["earlier_verified_sha256"]
            data = _read(source, 40 * 1024 * 1024)
            _check(_sha(data) == expected_new
                   and expected_old == saved["download_sha256"],
                   "Earlier/current SEC original source hashes disagree with saved evidence")
            source_blobs.append(data)
        _check(all(blob == source_blobs[0] for blob in source_blobs),
               "Duplicate current SEC original HTML files are not byte-identical")
        raw = source_blobs[0]
        _check(_sha(raw) == entry["current_original_html_sha256"]
               and len(raw) == entry["current_original_html_byte_count"]
               and entry["prior_original_html_sha256"] == saved["download_sha256"]
               and entry["current_source_raw_sha_matches_prior"] is (
                   _sha(raw) == saved["download_sha256"]
               ), "Current source exact-byte comparison was misreported")
        normalized = clean_html(raw)
        sstart = list(START.finditer(normalized))
        send = list(END.finditer(normalized))
        _check(len(sstart) == entry["source_original_risk_heading_count"]
               and len(send) == entry["source_original_next_section_heading_count"],
               "Original Item1A/next-section heading counts changed")
        original_range = extract_risk_factors(raw)
        begin, finish = entry["original_normalized_section_start"], entry["original_normalized_section_end"]
        _check(0 <= begin < finish <= len(normalized)
               and original_range.status == entry["source_extractor_current_status"]
               and original_range.candidate_count == entry["source_extractor_current_candidate_count"]
               and _sha(normalized.encode()) == entry["original_full_normalized_HTML_sha256"],
               "SEC original normalized boundary offsets and parser candidate count differ")
        if acc in GE_CASES:
            rule = by_acc[acc]
            _check(
                entry["source_boundary_method"] ==
                "REGISTERED_GE_SAME_DOCUMENT_RANGE_REPRODUCED_NOT_ORIGINAL_BYTES_IDENTICAL"
                and saved["resolution_method"] == rule["kind"] == "same_document_range"
                and original_range.status == "review"
                and begin == rule["start_offset"] and finish == rule["end_offset"],
                "Original referenced GE Item1A range has been changed",
            )
            text = normalized[begin:finish].strip(" .:-\n")
            _check(_sha(text.encode()) == rule["text_sha256"]
                   and rule["primary_sha256"] == saved["download_sha256"]
                   and len(TOKEN.findall(text)) == rule["token_count"],
                   "Previously registered GE Item1A text digest was not reproduced")
            counters["registered_alternate_source_boundaries"] += 1
        else:
            _check(
                entry["source_boundary_method"] == "DIRECT_NUMBERED_ITEM1A_AUTOMATED"
                and original_range.status == "ok"
                and original_range.start_offset == begin
                and original_range.end_offset == finish
                and any(x.end() == begin for x in sstart)
                and any(x.start() == finish for x in send)
                and saved["resolution_method"] == "numbered_item1a",
                "Original SEC direct numbered Item1A range changed or not bracketed by headings",
            )
            text = original_range.text
            counters["direct_substantive_item1a_source_boundaries"] += 1
        _check(
            len(TOKEN.findall(text)) == entry["risk_token_count"]
            == int(saved["risk_token_count"])
            and _sha(text.encode()) == entry["risk_text_sha256"]
            and entry["section_start_preview_private"] == text[:220]
            and entry["section_end_preview_private"] == text[-220:]
            and entry["surrounding_start_private"] == normalized[max(0, begin-125):begin]
            and entry["surrounding_end_private"] == normalized[finish:finish+145]
            and entry["original_html_source_semantically_equivalent_to_earlier_version"] is None,
            "Original filing risk text boundary preview, count or SHA disagrees with direct source",
        )
        counters["unique_original_SEC_filing_bodies"] += 1
        counters["source_risk_text_token_count_matches_original_manifest"] += 1
        counters["prior_original_SEC_header_CIK_acceptance_clock_verified"] += 1
        counters["current_original_HTML_bytes_same_as_earlier_source"] += int(
            _sha(raw) == saved["download_sha256"]
        )
        year_counts[int(saved["acceptance_timestamp"][:4])] += 1
        issuers.add(saved["cik"])
    counters["auto_document_boundary_review_human_signed"] = 0
    _check(dict(counters) == summary["counts"]
           and dict(sorted(year_counts.items())) == {
               int(k):v for k,v in summary["source_year_counts"].items()
           }
           and len(issuers) == summary["distinct_issuer_CIK_count"]
           and len(set(lookup["diagnostic"]) & set(lookup["class"])) ==
           summary["identical_duplicate_current_SEC_source_files_in_both_caches"] == 2,
           "Independent original SEC 30-source overlap or annual boundary totals differ")
    result = {
        "schema_version": 1, "status": STATUS,
        "independent_current_original_SEC_body_files_checked": 30,
        "distinct_issuer_CIKs": len(issuers),
        "independent_direct_bounded_Item1A_texts_reproduced": counters["direct_substantive_item1a_source_boundaries"],
        "independent_registered_GE_Item1A_text_digests_reproduced": counters["registered_alternate_source_boundaries"],
        "source_original_CIK_clock_and_SHA_boundaries_all_reproduced": True,
        "all_source_risk_text_counts_and_surrounding_boundaries_reproduced": True,
        "duplicate_current_source_bytes_verified_across_both_caches": 2,
        "provenance": {
            "first_boundary_matrix_receipt_sha256": _sha(receipt_raw),
            "first_boundary_matrix_private_sha256": _sha(private_raw),
            "original_SEC_manifest_sha256": _sha(manifest_raw),
            "original_SEC_report_sha256": _sha(prior_blob),
            "frozen_protocol_sha256": canonical_hash(config),
        },
        "GE_source_text_digest_reproduced_even_though_original_current_HTML_hash_mismatch": True,
        "source_first_public_dissemination_time_certified": False,
        "manual_section_boundary_reviews_completed_here": 0,
        "historical_stock_class_or_issuer_security_identity_approved": False,
        "CRSP_return_data_or_model_inputs_used": False,
        "model_ready": False, "final_period_opened": False,
        "interpretation": (
            "Automated original-HTML boundary and recorded original-source text "
            "reproducibility across 30 selected filings. No independent "
            "human or semantic Item1A boundary decision or historical availability."
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sec-boundary-verify-", dir=report_path.parent) as temp:
        staged = Path(temp) / "independent.json"
        staged.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        staged.replace(report_path)
    return result
