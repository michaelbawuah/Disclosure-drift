"""Bounded, consented SEC-original-10K bytes intake for the private eight-issuer pilot.

Retrieves only the 16 URLs already present in the locked 215-filing manifest,
with a legitimate SEC research contact User-Agent. Original content is never
rewritten or represented as byte-equivalent if its SHA-256 differs.
No new vendor data, year >= 2022 source or frozen returns are requested.
"""

import csv
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .protocol import canonical_hash

STATUS = "SEC_16_ORIGINAL_FILINGS_CURRENT_FETCH_BYTE_COMPARISON_NOT_APPROVED"
MANIFEST_HASH = "2658b7adfa03ea3c1800afd4107fa74c5348387533abde87cc30c0472b670fb1"
CLASS_SOURCE_STATUS = "ORIGINAL_10K_REGISTERED_STOCK_PAIRED_YEAR_REVIEW_NOT_APPROVED"
SEC_PRIOR_STATUS = "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED"
SHA = re.compile(r"[0-9a-f]{64}")
ACC = re.compile(r"\d{10}-\d{2}-\d{6}")
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _require(good, message):
    if not good:
        raise ValueError(message)


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _source(path, limit):
    p = Path(path)
    _require(not p.is_symlink(), "Input symbolic links are not permitted")
    p = p.resolve(strict=True)
    _require(p.is_file() and p.stat().st_size <= limit, "Missing/oversized original source input")
    return p, p.read_bytes()


def _allowed_sec_url(url, accession, cik):
    if not isinstance(url, str):
        return False
    split = urlsplit(url)
    _require(bool(ACC.fullmatch(accession)) and cik.isascii() and cik.isdigit(),
             "Invalid SEC filing accession or issuer CIK")
    expected = f"/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
    return (split.scheme == "https" and split.netloc == "www.sec.gov"
            and split.path.startswith(expected) and split.path != expected
            and not split.username and not split.password
            and not split.query and not split.fragment)


def _curl(url, dst, user_agent, cap, *, timeout=100):
    """Single GET, no redirect, no bypass of status 403, no UA in logs."""
    cmd = [
        "curl", "-sS", "--compressed", "--proto", "=https",
        "--max-redirs", "0", "--connect-timeout", "15", "--max-time", str(timeout),
        "-A", user_agent, "-o", str(dst), "-w", "%{http_code}", url,
    ]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "http": None, "curl_returncode": None}, None
    code = done.stdout.strip()
    if done.returncode or not re.fullmatch(r"\d{3}", code):
        return {"status": "CURL_ERROR", "http": code if len(code) == 3 else None,
                "curl_returncode": done.returncode}, None
    if code != "200":
        return {"status": "HTTP_STATUS", "http": code, "curl_returncode": 0}, None
    if not dst.is_file():
        return {"status": "NO_CONTENT_FILE", "http": code, "curl_returncode": 0}, None
    size = dst.stat().st_size
    if not 100 <= size <= cap:
        return {"status": "CONTENT_SIZE_INVALID", "http": code, "bytes": size}, None
    data = dst.read_bytes()
    if (data[:100].lstrip().startswith(b"<html") and
            (b"Access Denied" in data[:5000] or b"Request Rate Threshold" in data[:5000])):
        return {"status": "SEC_DENIAL_IN_CONTENT", "http": code}, None
    return {"status": "HTTP_200_VALID_SIZE", "http": code, "bytes": len(data),
            "curl_returncode": 0}, data


def _selected_sources(pairs_path, manifest, original_sec_report, original_sec_execution, config):
    pair_folder = Path(pairs_path).resolve(strict=True)
    _, receipt_bytes = _source(pair_folder / "receipt.json", 120000)
    _, public_bytes = _source(pair_folder / "public_summary.json", 120000)
    _, rows_bytes = _source(pair_folder / "private_issuer_pairs.jsonl", 2 * 1024 * 1024)
    receipt, public = json.loads(receipt_bytes), json.loads(public_bytes)
    _require(receipt["status"] == public["status"] == CLASS_SOURCE_STATUS
             and public["source_approvals_created"] == 0
             and public["model_ready"] is False
             and public["final_period_opened"] is False
             and receipt["source_approvals"] == 0
             and receipt["class_approvals"] == 0
             and receipt["files"]["private_issuer_pairs.jsonl"]["sha256"] == _sha(rows_bytes)
             and receipt["files"]["public_summary.json"]["sha256"] == _sha(public_bytes)
             and public["source_fingerprints"]["locked_protocol"] == canonical_hash(config),
             "Private pair selection changed or approved")
    pairs = [json.loads(s) for s in rows_bytes.decode().splitlines()]
    _require(len(pairs) == public["issuer_pairs_in_first_review"] == 8
             and sum(len(p["filings"]) for p in pairs) ==
             public["counts"]["filings_with_standard_member_without_structural_warning"] == 16,
             "Selected SEC filing count unexpectedly changed")
    file_ids = {}
    for pair in pairs:
        _require(pair["human_approved_historical_class"] is False
                 and pair["historical_security_identity_known_at"] is None,
                 "Historical security class was silently approved")
        for filing in pair["filings"]:
            acc = filing["accession"]
            _require(acc not in file_ids
                     and filing["historical_security_class_approved"] is False
                     and filing["historical_security_link_known_at"] is None,
                     "Repeated or approved selected filing")
            file_ids[acc] = pair["issuer_CIK"]
    manifest_path, raw = _source(manifest, 1024 * 1024)
    _require(_sha(raw) == MANIFEST_HASH, "Original 215-filing URL/byte inventory SHA changed")
    with manifest_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, strict=True, restkey="extra")
        _require(reader.fieldnames and {
            "accessionNumber", "cik", "source_url", "header_url",
            "download_sha256", "header_sha256",
        }.issubset(reader.fieldnames), "Missing original SEC source URL/digest inventory")
        allrows = {}
        for row in reader:
            _require("extra" not in row and None not in row.values(),
                     "Malformed original SEC source manifest record")
            key = row["accessionNumber"]
            _require(key not in allrows, "Duplicate SEC manifest accession")
            allrows[key] = row
    _require(len(allrows) == 215 and set(file_ids).issubset(allrows),
             "Selected 10-Ks absent from full original SEC manifest")
    _, earlier_bytes = _source(original_sec_report, 8 * 1024 * 1024)
    _, execution_bytes = _source(original_sec_execution, 2 * 1024 * 1024)
    compressed_meta = json.loads(execution_bytes)["publication"]
    _require(_sha(earlier_bytes) == compressed_meta["sha256"]
             and len(earlier_bytes) == compressed_meta["bytes"]
             and _sha(earlier_bytes) == public["source_fingerprints"]["original_sec_gzip"],
             "Original SEC previously verified publication is not pinned")
    import gzip
    plain = gzip.decompress(earlier_bytes)
    _require(_sha(plain) == compressed_meta["uncompressed_sha256"]
             and len(plain) == compressed_meta["uncompressed_bytes"],
             "Original SEC source gzip roundtrip changed")
    source = json.loads(plain)
    _require(source["status"] == SEC_PRIOR_STATUS
             and source["source_approvals"] == 0 and source["final_period_opened"] is False
             and source["original_sec_bytes_reread"] is True
             and source["protocol_sha256"] == canonical_hash(config),
             "Previously original-SEC verified evidence report changed")
    prior = {x["accession"]: x for x in source["records"]}
    _require(len(prior) == 215, "Original source records count/uniqueness changed")
    selected = []
    for accession, issuer in sorted(file_ids.items()):
        x = allrows[accession]
        event = prior[accession]
        _require(x["cik"] == event["manifest_cik_raw"] == issuer
                 and event["header_identity"]["header_identity_consistent"] is True
                 and event["primary_source"]["sha256"] == x["download_sha256"]
                 and event["header_source"]["sha256"] == x["header_sha256"],
                 "Original SEC prior verified byte receipt/manifest mismatch")
        for kind in ("source_url", "header_url"):
            _require(_allowed_sec_url(x[kind], accession, issuer),
                     "Unapproved external or malformed SEC Archive URL")
        selected.append({
            "accession": accession,
            "issuer_CIK": issuer,
            "acceptance_year": int(event["recorded_acceptance_timestamp"][:4]),
            "urls": {"primary": x["source_url"], "header": x["header_url"]},
            "expected_sha256": {"primary": x["download_sha256"],
                                "header": x["header_sha256"]},
            "expected_bytes": {
                "primary": event["primary_source"]["bytes"],
                "header": event["header_source"]["bytes"],
            },
        })
    _require(all(2015 <= x["acceptance_year"] <= config["development_end"]
                 and x["acceptance_year"] < config["holdout_start"] for x in selected),
             "Original SEC source selection crossed final evaluation period")
    proof = {
        "original_215_filing_manifest_sha256": _sha(raw),
        "original_earlier_SEC_verified_gzip_sha256": _sha(earlier_bytes),
        "original_earlier_SEC_execution_sha256": _sha(execution_bytes),
        "pair_selection_receipt_sha256": _sha(receipt_bytes),
        "pair_selection_private_file_sha256": _sha(rows_bytes),
        "frozen_protocol_sha256": canonical_hash(config),
    }
    return selected, proof


def fetch_original_sec_16(pairs, manifest, sec_gzip, sec_execution, output, *,
                          user_agent, config, repo_root, delay=1.3):
    """Fetch exact official SEC URLs, keeping changed bytes as separate observations."""
    repo = Path(repo_root).resolve(strict=True)
    destination = Path(output).resolve()
    _require(not destination.exists()
             and destination.is_relative_to(repo / "outputs")
             and destination != repo / "outputs", "Output requires a fresh private output path")
    _require(isinstance(user_agent, str) and 8 <= len(user_agent) <= 200
             and EMAIL.search(user_agent) is not None
             and "(" in user_agent and ")" in user_agent,
             "A legitimate SEC academic research User-Agent with a contact email is required")
    _require(isinstance(delay, (float, int)) and 1.0 <= delay <= 10.0,
             "SEC fair access intake cannot request more than one file per second")
    selected, proof = _selected_sources(pairs, manifest, sec_gzip, sec_execution, config)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sec-official-revisit-", dir=destination.parent) as scratch:
        stage = Path(scratch) / "bundle"
        stage.mkdir(mode=0o700)
        originals = stage / "original_sec_bytes"
        originals.mkdir(mode=0o700)
        report = []
        halted = False
        for filing in selected:
            new_row = {
                "accession": filing["accession"],
                "issuer_CIK": filing["issuer_CIK"],
                "acceptance_year": filing["acceptance_year"],
                "source_files": {},
            }
            for kind in ("primary", "header"):
                if halted:
                    new_row["source_files"][kind] = {"status": "NOT_FETCHED_AFTER_SEC_ACCESS_ERROR"}
                    continue
                url = filing["urls"][kind]
                expected = filing["expected_sha256"][kind]
                suffix = "original.html" if kind == "primary" else "original.hdr.sgml"
                target = originals / f'{filing["accession"]}.{suffix}'
                transfer, data = _curl(
                    url, target, user_agent, 40 * 1024 * 1024 if kind == "primary" else 1024 * 1024
                )
                details = {
                    **transfer,
                    "source_url": url,
                    "saved_relative_path": (
                        f"original_sec_bytes/{target.name}" if data is not None else None
                    ),
                    "earlier_verified_sha256": expected,
                    "earlier_verified_bytes": filing["expected_bytes"][kind],
                    "current_sha256": _sha(data) if data is not None else None,
                    "current_bytes": len(data) if data is not None else None,
                    "original_sec_bytes_exact_match": (_sha(data) == expected) if data is not None else False,
                    "source_publication_time_verified": False,
                    "current_source_availability_as_of_filing": False,
                }
                new_row["source_files"][kind] = details
                if data is not None:
                    os.chmod(target, 0o400)
                elif target.exists():
                    target.unlink()
                if transfer["status"] in {"HTTP_STATUS", "SEC_DENIAL_IN_CONTENT", "CURL_ERROR", "TIMEOUT"}:
                    halted = True
                time.sleep(delay)
            report.append(new_row)
        completed = sum(
            detail.get("status") == "HTTP_200_VALID_SIZE"
            for r in report for detail in r["source_files"].values()
        )
        exact = sum(
            detail.get("original_sec_bytes_exact_match") is True
            for r in report for detail in r["source_files"].values()
        )
        changed = [
            f"{r['accession']}:{kind}"
            for r in report for kind, detail in r["source_files"].items()
            if detail.get("status") == "HTTP_200_VALID_SIZE"
            and detail["original_sec_bytes_exact_match"] is False
        ]
        aggregate = {
            "schema_version": 1, "status": STATUS,
            "original_filings_requested": len(selected),
            "original_source_objects_requested": 2 * len(selected),
            "retrieved_HTTP_200_source_objects": completed,
            "retrieved_exact_prior_verified_sha256": exact,
            "retrieved_different_from_prior_verified_sha256": len(changed),
            "retrieved_missing_or_error": 2 * len(selected) - completed,
            "SEC_access_error_stop_triggered": halted,
            "source_fingerprints": proof,
            "original_source_bytes_directly_downloaded_on_this_Mac": completed > 0,
            "original_source_bytes_all_exactly_match_prior_verified_16_filing_cache": exact == 32,
            "source_verification_pending_if_any_bytes_differ": bool(changed),
            "historical_issuer_identity_approved": False,
            "source_publication_at_filing_established": False,
            "SEC_iXBRL_schema_semantics_validated": False,
            "new_source_approvals": 0, "model_ready": False,
            "final_period_opened": False,
            "interpretation": (
                "Original SEC source bytes reread from official URLs on current date. "
                "Hashes are compared with pinned earlier original SEC evidence; changed "
                "bytes are not accepted as identical or historical publication evidence."
            ),
        }
        (stage / "private_source_fetch_receipts.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        (stage / "public_summary.json").write_text(
            json.dumps(aggregate, indent=2, sort_keys=True) + "\n"
        )
        receipt = {
            "schema_version": 1, "status": STATUS,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_fingerprints": proof,
            "files": {
                name: {"sha256": _sha((stage / name).read_bytes()),
                       "bytes": (stage / name).stat().st_size}
                for name in ("private_source_fetch_receipts.json", "public_summary.json")
            },
            "new_approved_historical_links": 0, "model_ready": False,
            "final_period_opened": False,
        }
        (stage / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        for name in ("private_source_fetch_receipts.json", "public_summary.json", "receipt.json"):
            os.chmod(stage / name, 0o400)
        stage.rename(destination)
    return aggregate
