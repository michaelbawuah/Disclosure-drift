"""Build private, provisional annual listing candidates from a preserved Names inventory."""

import argparse
import csv
import json
import sqlite3
from pathlib import Path

import pyarrow as pa

from disclosure_research.manual_wrds_listing_candidates import aggregate_summary, build_listing_candidates
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/protocol.json")
    parser.add_argument("--names-inventory", required=True)
    parser.add_argument("--output", required=True, help="New private directory under data/ or outputs/")
    args = parser.parse_args(argv)
    try:
        config = load_protocol(args.protocol)
        verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
        receipt = build_listing_candidates(args.names_inventory, output=args.output,
                                            config=config, repo_root=Path.cwd())
    except (ValueError, OSError, csv.Error, sqlite3.Error, pa.ArrowException) as exc:
        print(json.dumps({"status": "LISTING_CANDIDATES_FAILED", "error_type": type(exc).__name__,
                          "model_ready": False, "source_approvals": 0}))
        return 1
    print(json.dumps(aggregate_summary(receipt), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
