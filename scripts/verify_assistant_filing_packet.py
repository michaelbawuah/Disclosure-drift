"""Verify a pinned assistant filing-review bundle; never create reviewer judgments."""

import argparse
from datetime import date, datetime
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
from zoneinfo import ZoneInfo

import pyarrow.parquet as pq

from disclosure_research.audit import build_audit
from disclosure_research.filing_review import validate_filing_reviews
from disclosure_research.protocol import canonical_hash, load_protocol, verify_lock


BUNDLE = "reports/filing_review/assistant"
PACKET = "reports/filing_review/packet.json"
FILINGS = "data/processed/pilot-resolved/filings.parquet"
PAIRS = "data/processed/pilot-resolved/filing_pairs.parquet"
OLD_EVIDENCE = "outputs/audit-pilot-resolved/filing_evidence.parquet"
OLD_AUDIT = "outputs/audit-pilot-resolved/audit_summary.json"
PRIOR = "reports/review_progress/assistant_filing_decisions.jsonl"
PRIOR_SHA256 = "88e6113d0508e9aaa49ba9e66b5c25c7cb735f451201bfe5530c036a31e59e32"
SELECTION = "reports/expanded_review_pairs.csv"
TEMPLATE = "reports/reference_reviews.template.jsonl"
RULES = "configs/section_resolutions.json"
FIELDS = {"accession", "evidence_id", "reviewer", "reviewer_type", "reviewed_at",
          "boundary_verdict", "timing_verdict", "notes"}
REQUIRED_SOURCES = {PACKET, FILINGS, PAIRS, OLD_EVIDENCE, OLD_AUDIT, PRIOR,
                    SELECTION, TEMPLATE, RULES, "configs/protocol.json", "configs/protocol.lock.json"}
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(items):
    result = {}
    for key, value in items:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError(f"Nonfinite JSON constant: {value}")


def parse(raw):
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def local_path(base, relative, missing=False):
    require(isinstance(relative, str) and relative and "\\" not in relative,
            "Paths must be nonempty local relative POSIX paths")
    parsed = PurePosixPath(relative)
    require(not parsed.is_absolute() and parsed.as_posix() == relative
            and all(part not in {".", ".."} for part in parsed.parts), "Unsafe relative path")
    target = base
    for part in parsed.parts:
        target = target / part
        require(not target.is_symlink(), "Symlink input or output path is not allowed")
    require(target.resolve(strict=not missing).is_relative_to(base.resolve(strict=True)),
            "Path leaves its allowed directory")
    return target


def read(path, expected=None):
    require(path.is_file() and not path.is_symlink(), f"Missing regular input: {path.name}")
    with path.open("rb") as handle:
        raw = handle.read(MAX_FILE_BYTES + 1)
    require(len(raw) <= MAX_FILE_BYTES, f"Oversized input: {path.name}")
    if expected is not None:
        require(isinstance(expected, dict) and set(expected) == {"sha256", "bytes"}
                and type(expected["bytes"]) is int and expected["bytes"] == len(raw)
                and expected["sha256"] == digest(raw), f"Input binding differs: {path.name}")
    return raw


def date_preflight(sources):
    """Decode only dates across all three pinned SEC tables before broader reads."""
    for relative, columns in ((FILINGS, ["acceptance_date", "acceptance_timestamp"]),
                              (PAIRS, ["acceptance_date", "previous_acceptance_date"]),
                              (OLD_EVIDENCE, ["acceptance_timestamp"])):
        parquet = pq.ParquetFile(io.BytesIO(sources[relative]))
        require(0 < parquet.metadata.num_rows <= 1000, "Unexpected source table row count")
        for row in parquet.read(columns=columns).to_pylist():
            for key, value in row.items():
                if "timestamp" in key:
                    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    require(stamp.tzinfo is not None and stamp.utcoffset() is not None, "Naive source timestamp")
                    day = stamp.astimezone(ZoneInfo("America/New_York")).date()
                else:
                    day = date.fromisoformat(value)
                require(2010 <= day.year <= 2021, "Source table leaves the development envelope")


def evidence_ids(raw):
    rows = pq.read_table(io.BytesIO(raw), columns=["accession", "evidence_id"]).to_pylist()
    result = {row["accession"]: row["evidence_id"] for row in rows}
    require(len(rows) == len(result) == 155, "Expected 155 unique original evidence IDs")
    return result


def verify(root, receipt_sha256, requested_audit):
    require(re.fullmatch(r"[0-9a-f]{64}", receipt_sha256) is not None, "Invalid expected receipt SHA-256")
    bundle = local_path(root, BUNDLE)
    receipt_path = local_path(bundle, "receipt.json")
    receipt_raw = read(receipt_path)
    require(digest(receipt_raw) == receipt_sha256, "Receipt does not match the required external pin")
    receipt = parse(receipt_raw)
    require(receipt["schema_version"] == 1 and receipt["review_count"] == 73
            and receipt["preserved_prior_review_count"] == 63 and receipt["new_review_count"] == 10,
            "Receipt counts or schema differ")
    require(receipt["prior_reviews_path"] == PRIOR and receipt["prior_reviews_sha256"] == PRIOR_SHA256,
            "Original assistant review identity differs")
    require(receipt["reviews_file"] == "reviews.jsonl" and receipt["audit_selection_source"] == SELECTION,
            "Unexpected review file or frozen selection")
    local_path(root, receipt["audit_output"], missing=True)
    require(PurePosixPath(receipt["audit_output"]).parts[0] == "outputs", "Audit output must be under outputs")
    files, source_bindings = receipt["files"], receipt["source_bindings"]
    require(isinstance(files, dict) and 0 < len(files) <= 200 and "reviews.jsonl" in files
            and "receipt.json" not in files, "Invalid bundle file manifest")
    require(isinstance(source_bindings, dict) and REQUIRED_SOURCES <= set(source_bindings)
            and len(source_bindings) <= 200, "Required source bindings are missing")
    actual_files = set()
    for path in bundle.rglob("*"):
        require(not path.is_symlink(), "Bundle contains a symlink")
        if path.is_file() and path != receipt_path:
            actual_files.add(path.relative_to(bundle).as_posix())
    require(actual_files == set(files), "Bundle contains missing or unmanifested files")
    frozen = {receipt_path: receipt_raw}
    bundle_raw, sources = {}, {}
    for base, manifest, values in ((bundle, files, bundle_raw), (root, source_bindings, sources)):
        for relative, expected in manifest.items():
            path = local_path(base, relative)
            raw = read(path, expected)
            require(sum(map(len, frozen.values())) + len(raw) <= MAX_TOTAL_BYTES, "Bundle exceeds verification byte bound")
            frozen[path] = raw
            values[relative] = raw
    require(digest(sources[PACKET]) == receipt["packet_sha256"]
            and digest(sources[PRIOR]) == PRIOR_SHA256
            and digest(bundle_raw["reviews.jsonl"]) == receipt["reviews_sha256"], "Top-level byte pins differ")
    date_preflight(sources)
    packet, old_audit = parse(sources[PACKET]), parse(sources[OLD_AUDIT])
    require(packet["packet_id"] == receipt["packet_id"] and packet["market_returns_read"] is False,
            "Packet identity or source scope differs")
    require(old_audit["market_returns_used"] is False and old_audit["filings"] == 155,
            "Unexpected original source audit")
    for relative, field in ((FILINGS, "source_table_sha256"), (PAIRS, "pair_table_sha256"),
                            (OLD_EVIDENCE, "evidence_table_sha256")):
        require(digest(sources[relative]) == old_audit[field], "Original audit source binding differs")
    packet_sources = {"filings": FILINGS, "pairs": PAIRS, "evidence": OLD_EVIDENCE,
                      "audit_summary": OLD_AUDIT, "selected_pairs": SELECTION, "reference_template": TEMPLATE}
    for role, relative in packet_sources.items():
        require(packet["source_bindings"][role]["sha256"] == digest(sources[relative])
                and packet["source_bindings"][role]["bytes"] == len(sources[relative]),
                "Review desk source binding differs")
    config = load_protocol(local_path(root, "configs/protocol.json"))
    verify_lock(config, local_path(root, "configs/protocol.lock.json"))
    require(canonical_hash(config) == packet["protocol_sha256"] and config["development_end"] == 2021,
            "Frozen development protocol differs")
    reviews = [parse(line) for line in bundle_raw["reviews.jsonl"].splitlines() if line.strip()]
    prior = [parse(line) for line in sources[PRIOR].splitlines() if line.strip()]
    review_map = {row["accession"]: row for row in reviews}
    prior_map = {row["accession"]: row for row in prior}
    require(len(review_map) == len(reviews) == 73 and len(prior_map) == len(prior) == 63,
            "Duplicate or unexpected review counts")
    require(len(packet["filings"]) == 73 and set(review_map) == {row["accession"] for row in packet["filings"]},
            "Reviews do not cover the exact 73-filing packet")
    require(all(set(row) == FIELDS and row["reviewer_type"] == "assistant"
                and row["boundary_verdict"] == row["timing_verdict"] == "pass" for row in reviews),
            "Expected exactly 73 completed assistant reviews and no human records")
    require(set(prior_map) <= set(review_map), "Prior decisions were removed")
    for accession, old in prior_map.items():
        require({key: old[key] for key in FIELDS} == review_map[accession],
                "A preserved prior author, timestamp, verdict, note, or evidence ID changed")
    new_ids = sorted(set(review_map) - set(prior_map))
    require(len(new_ids) == 10, "Expected exactly ten additional assistant decisions")
    audit_result = None
    with tempfile.TemporaryDirectory(prefix="assistant-filing-verify-") as temporary:
        temp = Path(temporary)
        immutable_reviews = temp / "reviews.jsonl"
        immutable_reviews.write_bytes(bundle_raw["reviews.jsonl"])
        validation = validate_filing_reviews(packet, immutable_reviews)
        require(validation["records"] == validation["assistant_reviews_declared_complete"] == 73
                and validation["human_reviews_declared_complete"] == validation["partial_reviews"]
                == validation["failed_reviews"] == 0, "Legacy-compatible review validation differs")
        if requested_audit is not None:
            output = local_path(root, requested_audit, missing=True)
            require(PurePosixPath(requested_audit).parts[0] == "outputs" and not output.exists(),
                    "Choose a new, nonexistent audit directory under outputs")
            cache = local_path(root, "data/raw/sec_cache")
            source_columns = ["source_url", "header_url", "risk_source_url", "resolution_index_url"]
            for row in pq.read_table(io.BytesIO(sources[FILINGS]), columns=source_columns).to_pylist():
                for url in row.values():
                    if url:
                        key = digest(url.encode())
                        local_path(cache, key + ".bin")
                        local_path(cache, key + ".json")
            for relative, name in ((FILINGS, "filings.parquet"), (PAIRS, "filing_pairs.parquet"),
                                    (RULES, "section_resolutions.json")):
                (temp / name).write_bytes(sources[relative])
            output.mkdir(parents=True, exist_ok=False)
            audit_result = build_audit(temp / "filings.parquet", cache, output, development_end=2021,
                                       reviews=immutable_reviews, pairs=temp / "filing_pairs.parquet",
                                       resolutions=temp / "section_resolutions.json")
            require(audit_result["filings"] == audit_result["automated_evidence_ok"] == 155
                    and audit_result["filings_with_blocking_issues"] == audit_result["human_reviews_complete"] == 0
                    and audit_result["assistant_reviews_complete"] == 73 and audit_result["manual_audit"] == "pending"
                    and audit_result["market_returns_used"] is False, "Source re-audit did not preserve required gates")
            require(evidence_ids(read(output / "filing_evidence.parquet")) == evidence_ids(sources[OLD_EVIDENCE]),
                    "Re-audit changed one or more original evidence IDs")
            require(read(output / "review_pairs.csv") == sources[SELECTION], "Re-audit changed the fixed 30-pair selection")
    for path, raw in frozen.items():
        require(read(local_path(root, path.relative_to(root).as_posix())) == raw, "An input changed during verification")
    return {"status": "ASSISTANT_FILING_PACKET_VERIFIED" if audit_result is None else "ASSISTANT_FILING_PACKET_SOURCE_REAUDITED",
            "receipt_sha256": receipt_sha256, "packet_id": packet["packet_id"],
            "reviews_sha256": receipt["reviews_sha256"], "assistant_reviews": 73,
            "preserved_prior_reviews": 63, "new_assistant_reviews": 10,
            "new_accessions": new_ids, "source_binding_files": len(source_bindings),
            "bundle_files": len(files), "original_sec_bytes_reread": audit_result is not None,
            "source_audit_output": requested_audit, "source_audit_summary": audit_result,
            "human_reviews_created": 0, "source_approvals": 0, "historical_security_links_created": 0,
            "prior_arithmetic_review_modified": False, "model_ready": False, "final_period_opened": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-sha256", required=True, help="Externally recorded SHA-256 of bundle receipt.json")
    parser.add_argument("--audit-output", help="Optional new repo-relative directory under outputs for a source re-audit")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        result = verify(root, args.receipt_sha256, args.audit_output)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, StopIteration) as error:
        print(json.dumps({"status": "ASSISTANT_FILING_PACKET_VERIFICATION_FAILED", "error": str(error)[:500],
                          "model_ready": False, "final_period_opened": False}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
