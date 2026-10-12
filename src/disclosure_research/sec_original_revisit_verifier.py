"""Reparse independently retrieved SEC originals and compare to pinned prior evidence.

This is an original-source byte and lexical context audit, NOT historical
SEC-publication timing, known_at, vendor source vintage or XBRL schema proof.
Original SEC bytes and per-issuer records are private ignored local artifacts.
"""

import gzip
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .protocol import canonical_hash
from .sec_identity_evidence import _clock, cover_evidence, header_identity

STATUS = "SEC_16_CURRENT_ORIGINAL_HTML_REPARSED_AGAINST_PREVIOUS_SOURCE_REPORT_NOT_APPROVED"
FETCH_KIND = "SEC_16_ORIGINAL_FILINGS_CURRENT_FETCH_BYTE_COMPARISON_NOT_APPROVED"
PRIOR_KIND = "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED"
SHA = re.compile(r"[0-9a-f]{64}")


def _must(good, why):
    if not good:
        raise ValueError(why)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _source(path, cap):
    original = Path(path)
    _must(not original.is_symlink(), "Source symlink not supported")
    path = original.resolve(strict=True)
    _must(path.is_file() and path.stat().st_size <= cap,
          "Source is missing or oversized")
    return path, path.read_bytes()


def _checked_saved_path(folder, relative):
    _must(isinstance(relative, str) and relative.startswith("original_sec_bytes/")
          and ".." not in Path(relative).parts and
          "/" not in Path(relative).name, "Unsafe SEC source bundle path")
    dest = folder / relative
    _must(dest.resolve().is_relative_to(folder)
          and not dest.is_symlink(), "SEC source bundle has escaped the source directory")
    return dest


def _original_report(original_gzip, original_execution, config):
    original_path, compressed = _source(original_gzip, 8 * 1024 * 1024)
    _, execution_raw = _source(original_execution, 2 * 1024 * 1024)
    record = json.loads(execution_raw)
    published = record["publication"]
    _must(_sha(compressed) == published["sha256"]
          and len(compressed) == published["bytes"], "Earlier SEC source evidence digest changed")
    plain = gzip.decompress(compressed)
    _must(len(plain) <= 16 * 1024 * 1024
          and _sha(plain) == published["uncompressed_sha256"]
          and len(plain) == published["uncompressed_bytes"],
          "Original 215-SEC source report decompression failed")
    report = json.loads(plain)
    _must(report["status"] == PRIOR_KIND
          and report["protocol_sha256"] == canonical_hash(config)
          and report["source_approvals"] == 0
          and report["historical_security_links_created"] == 0
          and report["final_period_opened"] is False
          and report["original_sec_bytes_reread"] is True
          and report["xbrl_fact_values_interpreted"] is False
          and len(report["records"]) == 215,
          "Original 215-filing SEC report no longer retains pending gates")
    by_acc = {r["accession"]: r for r in report["records"]}
    _must(len(by_acc) == 215, "Duplicate original SEC accession in prior source report")
    return by_acc, {
        "earlier_sec_source_gzip_sha256": _sha(compressed),
        "earlier_sec_source_original_json_sha256": _sha(plain),
        "earlier_sec_execution_sha256": _sha(execution_raw),
    }, (original_path, _sha(compressed))


def reparse_16_sec_originals(bundle, prior_gzip, prior_execution, output, *,
                             config, repo_root):
    root = Path(repo_root).resolve(strict=True)
    target = Path(output).resolve()
    _must(not target.exists() and target.is_relative_to(root / "outputs")
          and target != root / "outputs", "Output must be a fresh private project outputs directory")
    folder = Path(bundle).resolve(strict=True)
    _must(not target.is_relative_to(folder), "Output cannot be created inside original source")
    _, fetch_summary_raw = _source(folder / "public_summary.json", 256 * 1024)
    _, original_receipt_raw = _source(folder / "receipt.json", 256 * 1024)
    _, private_raw = _source(folder / "private_source_fetch_receipts.json", 256 * 1024)
    src_summary, original_receipt = json.loads(fetch_summary_raw), json.loads(original_receipt_raw)
    _must(src_summary["status"] == original_receipt["status"] == FETCH_KIND
          and original_receipt["model_ready"] is False
          and original_receipt["final_period_opened"] is False
          and original_receipt["new_approved_historical_links"] == 0
          and src_summary["new_source_approvals"] == 0
          and src_summary["historical_issuer_identity_approved"] is False
          and src_summary["source_publication_at_filing_established"] is False
          and src_summary["SEC_iXBRL_schema_semantics_validated"] is False
          and src_summary["model_ready"] is False
          and src_summary["final_period_opened"] is False
          and src_summary["source_fingerprints"] == original_receipt["source_fingerprints"]
          and src_summary["source_fingerprints"]["frozen_protocol_sha256"] == canonical_hash(config),
          "Unapproved SEC original fetch evidence source bindings changed")
    for filename, contents in (
        ("public_summary.json", fetch_summary_raw),
        ("private_source_fetch_receipts.json", private_raw),
    ):
        expected = original_receipt["files"][filename]
        _must(_sha(contents) == expected["sha256"] and len(contents) == expected["bytes"],
              "Original SEC retrieval evidence source hash mismatch")
    rows = json.loads(private_raw)
    _must(len(rows) == src_summary["original_filings_requested"] == 16
          and len({x["accession"] for x in rows}) == 16
          and src_summary["original_source_objects_requested"] == 32,
          "Expected exactly 16 distinct source original SEC filings")
    previous, prior_source_hashes, original_hash_check = _original_report(
        prior_gzip, prior_execution, config
    )
    _must(prior_source_hashes["earlier_sec_source_gzip_sha256"]
          == src_summary["source_fingerprints"]["original_earlier_SEC_verified_gzip_sha256"]
          and prior_source_hashes["earlier_sec_execution_sha256"]
          == src_summary["source_fingerprints"]["original_earlier_SEC_execution_sha256"],
          "Previous original SEC publication differs from SEC retrieval request")
    counters = Counter()
    private = []
    source_pins = []
    for row in rows:
        acc = row["accession"]
        original = previous.get(acc)
        _must(original is not None and original["manifest_cik_raw"] == row["issuer_CIK"]
              and original["known_at"] is None and original["available_at"] is None
              and original["security_link_created"] is False
              and original["header_identity"]["header_identity_consistent"] is True,
              "Previous 10-K filer identity or original source gates changed")
        entry = {
            "accession": acc, "issuer_CIK": row["issuer_CIK"],
            "acceptance_year": row["acceptance_year"], "sections": {},
            "original_source_publication_time_established": False,
            "current_document_XBRL_semantics_validated": False,
            "historical_security_class_approved": False,
        }
        contents = {}
        for kind, size in (("primary", 40 * 1024 * 1024),
                           ("header", 1024 * 1024)):
            record = row["source_files"][kind]
            expected = original["primary_source" if kind == "primary" else "header_source"]
            _must(record["earlier_verified_sha256"] == expected["sha256"]
                  and record["earlier_verified_bytes"] == expected["bytes"]
                  and record["source_url"] == expected["url"]
                  and record["source_publication_time_verified"] is False
                  and record["current_source_availability_as_of_filing"] is False,
                  "Current SEC object mismatches original 215-filing source accession")
            if record.get("status") != "HTTP_200_VALID_SIZE":
                counters[f"{kind}_unretrieved"] += 1
                entry["sections"][kind] = {"status": "NOT_RETRIEVED_OR_NOT_HTTP_200"}
                continue
            p = _checked_saved_path(folder, record["saved_relative_path"])
            _, raw = _source(p, size)
            source_pins.append((p, _sha(raw)))
            _must(_sha(raw) == record["current_sha256"]
                  and len(raw) == record["current_bytes"]
                  and (_sha(raw) == expected["sha256"]) is
                  record["original_sec_bytes_exact_match"],
                  "Downloaded original SEC bytes/source receipt inconsistent")
            contents[kind] = raw
            counters[f"{kind}_retrieved_HTTP_200"] += 1
            exact = _sha(raw) == expected["sha256"]
            counters[f"{kind}_exact_prior_sha256"] += int(exact)
            if not exact:
                counters[f"{kind}_changed_from_original_verified_byte_hash"] += 1
            delta = len(raw) - expected["bytes"]
            counters[f"{kind}_bytes_delta_{delta:+d}"] += 1
            entry["sections"][kind] = {
                "status": "RETRIEVED_DIRECT_ORIGINAL_SEC_ARCHIVE",
                "prior_verified_bytes_sha256": expected["sha256"],
                "current_download_bytes_sha256": _sha(raw),
                "prior_verified_bytes": expected["bytes"],
                "current_bytes": len(raw),
                "byte_length_difference": delta,
                "byte_identical_to_earlier_verified_archive": exact,
                "original_source_url": expected["url"],
                "source_publication_time_at_filing_established": False,
            }
        if "header" in contents:
            current_header = header_identity(
                contents["header"], expected_cik=row["issuer_CIK"], expected_accession=acc
            )
            same_identity = current_header == original["header_identity"]
            current_clock = _clock(
                contents["header"], original["recorded_acceptance_timestamp"],
                original["acceptance_date"],
            )
            same_clock = current_clock == original["acceptance_clock"]
            entry["sections"]["header"]["exact_source_header_identity_reproduced"] = same_identity
            entry["sections"]["header"]["exact_source_acceptance_clock_reproduced"] = same_clock
            counters["original_header_identity_exact_reproductions"] += int(same_identity)
            counters["original_header_clock_exact_reproductions"] += int(same_clock)
        if "primary" in contents:
            parsed = cover_evidence(contents["primary"])
            old = original["cover_evidence"]
            _must(parsed["full_xbrl_validity_claimed"] is False
                  and parsed["cross_context_security_assembly_performed"] is False,
                  "A lexical parser cannot assert semantic XBRL or historical stock class")
            facts_match = parsed["facts"] == old["facts"]
            contexts_match = parsed["contexts"] == old["contexts"]
            complete_match = parsed == old
            entry["sections"]["primary"].update({
                "selected_lexical_facts_equal_to_original_source_report": facts_match,
                "parsed_XBRL_contexts_equal_to_original_source_report": contexts_match,
                "all_original_source_lexical_report_fields_equal": complete_match,
                "matching_original_fact_count": len(parsed["facts"]),
                "matching_original_context_count": len(parsed["contexts"]),
                "reparsed_primary_document_is_lexical_evidence_only": True,
                "original_primary_html_retrieved_on_this_Mac": True,
            })
            counters["original_primary_selected_lexical_facts_exact_reproductions"] += int(facts_match)
            counters["original_primary_contexts_exact_reproductions"] += int(contexts_match)
            counters["original_primary_full_lexical_report_exact_reproductions"] += int(complete_match)
        private.append(entry)
    _must(counters["primary_retrieved_HTTP_200"] == src_summary["retrieved_HTTP_200_source_objects"]
          - counters["header_retrieved_HTTP_200"],
          "Original SEC primary+header fetch count changed")
    _must(sum(counters.get(f"{k}_exact_prior_sha256", 0) for k in ("primary", "header"))
          == src_summary["retrieved_exact_prior_verified_sha256"],
          "Downloaded exact-original SHA counts no longer agree with saved fetch bundle")
    _must(sum(counters.get(f"{k}_changed_from_original_verified_byte_hash", 0)
              for k in ("primary", "header"))
          == src_summary["retrieved_different_from_prior_verified_sha256"],
          "Original SEC byte drift count disagrees with fetch records")
    for p, old_hash in source_pins:
        _must(_sha(p.read_bytes()) == old_hash,
              "Downloaded original SEC file changed while verifying")
    _must(_sha(original_hash_check[0].read_bytes()) == original_hash_check[1],
          "Prior SEC original-source report was modified during current verification")
    summary = {
        "schema_version": 1, "status": STATUS,
        "original_10K_filings_revisited": len(rows),
        "source_object_counts": dict(sorted(counters.items())),
        "source_fingerprints": {
            **src_summary["source_fingerprints"],
            **prior_source_hashes,
            "current_source_download_receipt_sha256": _sha(original_receipt_raw),
            "current_source_private_details_sha256": _sha(private_raw),
        },
        "direct_current_original_SEC_primary_html_reparsed_on_Mac": (
            counters["primary_retrieved_HTTP_200"] > 0
        ),
        "all_current_source_lexical_evidence_matches_earlier_verified_packet": (
            counters["primary_retrieved_HTTP_200"] == 16
            and counters["original_primary_full_lexical_report_exact_reproductions"] == 16
            and counters["original_header_identity_exact_reproductions"] == 16
            and counters["original_header_clock_exact_reproductions"] == 16
        ),
        "source_sha256_mismatch_is_not_accepted_as_exact_historical_bytes": True,
        "previously_verified_original_HTML_bytes_are_not_available_for_diff_on_this_Mac": True,
        "current_SEC_response_first_published_time_verified": False,
        "original_SEC_iXBRL_schema_semantics_validated": False,
        "historical_link_or_common_stock_class_approved": False,
        "source_approvals_created": 0, "human_reviews_created": 0,
        "model_ready": False, "final_period_opened": False,
        "interpretation": (
            "Original SEC HTML/header bytes were fetched today and reparsed. "
            "Any prior hash mismatch remains a reported source-version difference; "
            "even identical lexical facts and contexts do not establish XBRL semantic "
            "class approval or original public-dissemination timing."
        ),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sec-reparse-", dir=target.parent) as scratch:
        stage = Path(scratch) / "bundle"
        stage.mkdir(mode=0o700)
        (stage / "private_reparse_per_filing.jsonl").write_text(
            "".join(json.dumps(x, sort_keys=True) + "\n" for x in private)
        )
        (stage / "public_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        receipt = {
            "schema_version": 1, "status": STATUS,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "files": {
                name: {"sha256": _sha((stage / name).read_bytes()),
                       "bytes": (stage / name).stat().st_size}
                for name in ("private_reparse_per_filing.jsonl", "public_summary.json")
            },
            "source_fingerprints": summary["source_fingerprints"],
            "historical_security_links_approved": 0, "model_ready": False,
            "final_period_opened": False,
        }
        (stage / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        for name in ("private_reparse_per_filing.jsonl", "public_summary.json", "receipt.json"):
            os.chmod(stage / name, 0o400)
        stage.rename(target)
    return summary
