"""Report public SEC context for a pinned private identity discovery ledger.

Only the ledger's public manifest keys and coverage status are read. No CCM,
Names, security identifiers, relationships, or market-return rows are exported.
This is source context, not a historical identity or availability approval.
"""

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

from disclosure_research.manual_wrds_candidates import _inside
from disclosure_research.manual_wrds_identity_candidates import STATUS
from disclosure_research.protocol import canonical_hash, load_protocol, verify_lock

COLUMNS = ["sec_manifest_sha256", "sec_manifest_csv_record", "accession",
           "sec_filer_cik_raw", "recorded_acceptance_date", "coverage_status"]
PUBLIC_FIELDS = ["cik", "name", "accessionNumber", "acceptance_date",
                 "source_url", "header_url", "download_sha256", "header_sha256"]
UNMATCHED = "NO_SAME_YEAR_HEADER_CIK_CANDIDATE_DISCOVERY"
MATCHED = "HEADER_CIK_DISCOVERY_ONLY"


def inspect(directory, expected_receipt_sha256, output):
    directory, output = Path(directory), Path(output)
    if directory.is_symlink():
        raise ValueError("The identity bundle must not be a symbolic link")
    directory = directory.resolve()
    if output.exists() or output.is_symlink():
        raise ValueError("Preserve prior discovery evidence; use a new output path")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_receipt_sha256 or ""):
        raise ValueError("An explicit identity receipt SHA-256 is required")
    guards = {}

    def bound(name, digest, size=None):
        path = _inside(directory, name)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest or (size is not None and len(raw) != size):
            raise ValueError("Discovery input differs from its pinned hash or size")
        guards[path] = digest
        return raw

    receipt = json.loads(bound("receipt.json", expected_receipt_sha256))
    config = load_protocol()
    verify_lock(config, "configs/protocol.lock.json")
    if (receipt.get("status") != STATUS or receipt.get("model_ready") is not False
            or type(receipt.get("source_approvals")) is not int or receipt["source_approvals"] != 0
            or receipt.get("protocol_sha256") != canonical_hash(config)
            or receipt.get("original_sec_bytes_reread") is not False
            or receipt.get("prior_arithmetic_review_modified") is not False
            or receipt.get("final_period_opened") is not False):
        raise ValueError("Identity receipt does not describe the unapproved development evidence")
    manifest = receipt["sec_manifest"]
    snapshot = manifest["snapshot"]
    if not manifest["provided"] or snapshot["sha256"] != manifest["sha256"]:
        raise ValueError("A bound original SEC manifest is required")
    raw = bound(snapshot["file"], snapshot["sha256"], snapshot["bytes"])
    public_rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    if len(public_rows) != manifest["rows"]:
        raise ValueError("SEC manifest record count differs")
    for source in public_rows:
        day = date.fromisoformat(source["acceptance_date"])
        if (day.isoformat() != source["acceptance_date"]
                or not config["initial_train_start"] <= day.year <= config["development_end"]):
            raise ValueError("SEC discovery context accepts exact ISO development dates only")
    table = receipt["tables"]["sec_manifest_coverage"]
    coverage = []
    for part in table["parts"]:
        raw = bound(part["file"], part["sha256"], part["bytes"])
        selected = pq.read_table(io.BytesIO(raw), columns=COLUMNS)
        if selected.num_rows != part["rows"]:
            raise ValueError("Discovery part record count differs")
        coverage.extend(selected.to_pylist())
    coverage.sort(key=lambda row: row["sec_manifest_csv_record"])
    if (len(coverage) != len(public_rows) or table["rows"] != len(coverage)
            or [row["sec_manifest_csv_record"] for row in coverage] != list(range(2, len(public_rows) + 2))):
        raise ValueError("Discovery coverage must account for each manifest ordinal exactly once")
    counts, unmatched = Counter(), []
    for source, row in zip(public_rows, coverage, strict=True):
        if (row["sec_manifest_sha256"] != manifest["sha256"]
                or row["accession"] != source["accessionNumber"]
                or row["sec_filer_cik_raw"] != source["cik"]
                or row["recorded_acceptance_date"] != source["acceptance_date"]
                or row["coverage_status"] not in {MATCHED, UNMATCHED}):
            raise ValueError("Discovery row differs from its exact public filing metadata")
        counts[row["coverage_status"]] += 1
        if row["coverage_status"] == UNMATCHED:
            unmatched.append({key: source[key] for key in PUBLIC_FIELDS})
    if dict(counts) != receipt["sec_manifest_coverage_counts"]:
        raise ValueError("Discovery coverage counts differ from the receipt")
    for path, digest in guards.items():
        current = _inside(directory, path.relative_to(directory).as_posix())
        if hashlib.sha256(current.read_bytes()).hexdigest() != digest:
            raise ValueError("Discovery input changed during inspection")
    result = {
        "schema_version": 1,
        "status": "PUBLIC_SEC_DISCOVERY_CONTEXT_NOT_HISTORICAL_IDENTITY_APPROVAL",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "identity_receipt_sha256": expected_receipt_sha256,
        "sec_manifest_sha256": manifest["sha256"],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "protocol_sha256": receipt["protocol_sha256"],
        "verified_manifest_records": len(coverage),
        "coverage_counts": dict(sorted(counts.items())),
        "unmatched_original_filer_counts": dict(sorted(Counter(row["cik"] for row in unmatched).items())),
        "public_unmatched_filings": unmatched,
        "source_files_rehashed": len(guards),
        "ledger_columns_read": COLUMNS,
        "original_sec_bytes_reread": False,
        "vendor_identifiers_exported": False,
        "market_returns_read": False,
        "historical_cik_link_approved": False,
        "historical_availability_supplied": False,
        "model_ready": False,
        "source_approvals": 0,
        "human_reviews_added": 0,
        "prior_arithmetic_review_modified": False,
        "final_period_opened": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--identity-receipt-sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = inspect(args.identity, args.identity_receipt_sha256, args.output)
    print(json.dumps({key: value for key, value in result.items() if key != "public_unmatched_filings"}, indent=2))
