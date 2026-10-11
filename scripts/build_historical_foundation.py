"""Reconcile completed private annual evidence with a pinned original-SEC report."""

import argparse
import csv
import gzip
import json
import sqlite3
from pathlib import Path

import pyarrow as pa

from disclosure_research.historical_foundation import aggregate_summary, build_historical_foundation_review
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/protocol.json")
    parser.add_argument("--identity", required=True)
    parser.add_argument("--identity-receipt-sha256", required=True)
    parser.add_argument("--liquidity", required=True)
    parser.add_argument("--liquidity-receipt-sha256", required=True)
    parser.add_argument("--sec-evidence", required=True, help="Preserved gzip original-source report")
    parser.add_argument("--sec-evidence-sha256", required=True, help="SHA-256 of the compressed input bytes")
    parser.add_argument("--sec-manifest", required=True)
    parser.add_argument("--sec-manifest-sha256", required=True)
    parser.add_argument("--output", required=True, help="New private directory beneath data/ or outputs/")
    args = parser.parse_args(argv)
    try:
        config = load_protocol(args.protocol)
        verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
        receipt = build_historical_foundation_review(
            args.identity, args.liquidity, identity_receipt_sha256=args.identity_receipt_sha256,
            liquidity_receipt_sha256=args.liquidity_receipt_sha256, sec_evidence_path=args.sec_evidence,
            sec_evidence_sha256=args.sec_evidence_sha256, sec_manifest_path=args.sec_manifest,
            sec_manifest_sha256=args.sec_manifest_sha256, output=args.output, config=config, repo_root=Path.cwd())
    except (ValueError, OSError, TypeError, KeyError, AttributeError, UnicodeError,
            csv.Error, sqlite3.Error, pa.ArrowException, gzip.BadGzipFile, EOFError) as exc:
        print(json.dumps({"status": "HISTORICAL_FOUNDATION_FAILED", "error_type": type(exc).__name__,
                          "model_ready": False, "source_approvals": 0}))
        return 1
    print(json.dumps(aggregate_summary(receipt), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
