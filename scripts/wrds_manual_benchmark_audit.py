"""Diagnose a preserved WRDS benchmark discrepancy with private exact evidence."""

import argparse
import csv
import json
import sqlite3
from decimal import DecimalException
from pathlib import Path

import duckdb
import pyarrow as pa

from disclosure_research.manual_wrds_benchmark_audit import aggregate_summary, audit_benchmark
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/protocol.json")
    parser.add_argument("--stage", required=True)
    parser.add_argument("--output", required=True, help="New private directory under data/ or outputs/")
    args = parser.parse_args(argv)
    try:
        config = load_protocol(args.protocol)
        verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
        receipt = audit_benchmark(args.stage, output=args.output, config=config, repo_root=Path.cwd())
    except (ValueError, OSError, TypeError, KeyError, AttributeError, UnicodeError,
            csv.Error, DecimalException, sqlite3.Error, duckdb.Error, pa.ArrowException) as exc:
        # CSV/Arrow/OS/SQL exception messages can include raw licensed cells.
        print(json.dumps({"status": "BENCHMARK_DIAGNOSTIC_FAILED", "error_type": type(exc).__name__,
                          "model_ready": False, "source_approvals": 0, "final_period_opened": False}))
        return 1
    print(json.dumps(aggregate_summary(receipt), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
