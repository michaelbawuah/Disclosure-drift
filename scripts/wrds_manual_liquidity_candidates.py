"""Build private 2010–2021 annual liquidity candidates from preserved candidate bundles."""

import argparse
import json
import sqlite3
from pathlib import Path

import duckdb
import pyarrow as pa

from disclosure_research.manual_wrds_liquidity_candidates import aggregate_summary, build_liquidity_candidates
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/protocol.json")
    parser.add_argument("--numerical-candidates", required=True)
    parser.add_argument("--listing-candidates", required=True)
    parser.add_argument("--output", required=True, help="New private directory under data/ or outputs/")
    args = parser.parse_args(argv)
    try:
        config = load_protocol(args.protocol)
        verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
        receipt = build_liquidity_candidates(args.numerical_candidates, args.listing_candidates,
                                             output=args.output, config=config, repo_root=Path.cwd())
    except (ValueError, OSError, TypeError, KeyError, AttributeError, UnicodeError,
            sqlite3.Error, duckdb.Error, pa.ArrowException) as exc:
        print(json.dumps({"status": "LIQUIDITY_CANDIDATES_FAILED", "error_type": type(exc).__name__,
                          "model_ready": False, "source_approvals": 0}))
        return 1
    print(json.dumps(aggregate_summary(receipt), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
