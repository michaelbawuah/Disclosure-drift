"""Build private, non-approving annual Names/CCM identity evidence entirely offline."""

import argparse
import csv
import json
import sqlite3
from pathlib import Path

import pyarrow as pa

from disclosure_research.manual_wrds_identity_candidates import aggregate_summary, build_identity_candidates
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/protocol.json")
    parser.add_argument("--ccm-inventory", required=True)
    parser.add_argument("--listing-candidates", required=True)
    parser.add_argument("--sec-manifest", help="Optional saved public SEC filing_sources.csv; no sources are fetched")
    parser.add_argument("--output", required=True, help="New private directory under data/ or outputs/")
    args = parser.parse_args(argv)
    try:
        config = load_protocol(args.protocol)
        verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
        receipt = build_identity_candidates(args.ccm_inventory, args.listing_candidates, output=args.output,
                                            sec_manifest=args.sec_manifest, config=config, repo_root=Path.cwd())
    except (ValueError, OSError, TypeError, KeyError, AttributeError, UnicodeError,
            csv.Error, sqlite3.Error, pa.ArrowException) as exc:
        print(json.dumps({"status": "IDENTITY_EVIDENCE_FAILED", "error_type": type(exc).__name__,
                          "model_ready": False, "source_approvals": 0}))
        return 1
    print(json.dumps(aggregate_summary(receipt), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
