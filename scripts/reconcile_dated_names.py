"""Reconcile existing filing discoveries with complete, preserved Names history."""

import argparse
import csv
import gzip
import json
import sqlite3
from pathlib import Path

import pyarrow as pa

from disclosure_research.dated_names_evidence import aggregate_summary, build_dated_names_evidence
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/protocol.json")
    parser.add_argument("--foundation", required=True)
    parser.add_argument("--foundation-receipt-sha256", required=True)
    parser.add_argument("--names-inventory", required=True)
    parser.add_argument("--names-receipt-sha256", required=True)
    parser.add_argument("--sec-evidence", required=True)
    parser.add_argument("--sec-manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        config = load_protocol(args.protocol)
        verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
        receipt = build_dated_names_evidence(
            args.foundation, args.names_inventory,
            foundation_receipt_sha256=args.foundation_receipt_sha256,
            names_receipt_sha256=args.names_receipt_sha256,
            sec_evidence_path=args.sec_evidence, sec_manifest_path=args.sec_manifest,
            output=args.output, config=config, repo_root=Path.cwd())
    except (ValueError, OSError, TypeError, KeyError, AttributeError, UnicodeError,
            csv.Error, sqlite3.Error, pa.ArrowException, gzip.BadGzipFile, EOFError) as exc:
        print(json.dumps({"status": "DATED_NAMES_EVIDENCE_FAILED", "error_type": type(exc).__name__,
                          "model_ready": False, "source_approvals": 0}))
        return 1
    print(json.dumps(aggregate_summary(receipt), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
