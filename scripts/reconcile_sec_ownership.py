"""Reconcile saved 2019 Q4 ownership metadata for the complete 2020 candidate cohort."""

import argparse
import csv
import json
import sqlite3
from pathlib import Path

import pyarrow as pa

from disclosure_research.protocol import load_protocol, verify_lock
from disclosure_research.sec_ownership_corrob import aggregate_summary, build_sec_ownership_corrob


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/protocol.json")
    for name in ("foundation", "foundation-receipt-sha256", "identity", "identity-receipt-sha256",
                 "names-inventory", "names-receipt-sha256", "sec-submission", "sec-ledger",
                 "sec-ledger-sha256", "sec-collection-receipt", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        config = load_protocol(args.protocol)
        verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
        receipt = build_sec_ownership_corrob(
            args.foundation, args.identity, args.names_inventory,
            foundation_receipt_sha256=args.foundation_receipt_sha256,
            identity_receipt_sha256=args.identity_receipt_sha256,
            names_receipt_sha256=args.names_receipt_sha256,
            sec_submission_path=args.sec_submission, sec_ledger_path=args.sec_ledger,
            sec_ledger_sha256=args.sec_ledger_sha256, sec_collection_receipt_path=args.sec_collection_receipt,
            output=args.output, config=config, repo_root=Path.cwd())
    except (ValueError, OSError, TypeError, KeyError, AttributeError, UnicodeError,
            csv.Error, sqlite3.Error, pa.ArrowException, EOFError) as exc:
        print(json.dumps({"status": "SEC_OWNERSHIP_CORROBORATION_FAILED",
                          "error_type": type(exc).__name__, "model_ready": False, "source_approvals": 0}))
        return 1
    print(json.dumps(aggregate_summary(receipt), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
