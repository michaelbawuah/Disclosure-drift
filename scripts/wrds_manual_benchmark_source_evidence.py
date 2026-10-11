"""Build a private source-evidence packet from a saved, hash-pinned benchmark audit."""

import argparse
import json
import sqlite3
from decimal import DecimalException
from pathlib import Path

import pyarrow as pa

from disclosure_research.manual_wrds_benchmark_source_evidence import aggregate_summary, build_source_evidence
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/protocol.json")
    parser.add_argument("--audit", required=True)
    parser.add_argument("--audit-receipt-sha256", required=True, help="Hash of the recorded successful audit receipt")
    parser.add_argument("--query-evidence", action="append", default=[], help="Saved observation/reconciliation document directory")
    parser.add_argument("--output", required=True, help="New private directory under data/ or outputs/")
    args = parser.parse_args(argv)
    try:
        config = load_protocol(args.protocol)
        verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
        receipt = build_source_evidence(args.audit, audit_receipt_sha256=args.audit_receipt_sha256,
                                        query_evidence=args.query_evidence, output=args.output,
                                        config=config, repo_root=Path.cwd())
    except (ValueError, OSError, TypeError, KeyError, AttributeError, UnicodeError,
            sqlite3.Error, pa.ArrowException, DecimalException) as exc:
        print(json.dumps({"status": "BENCHMARK_SOURCE_EVIDENCE_FAILED", "error_type": type(exc).__name__,
                          "model_ready": False, "source_approvals": 0, "vendor_question_sent": False}))
        return 1
    print(json.dumps(aggregate_summary(receipt), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
