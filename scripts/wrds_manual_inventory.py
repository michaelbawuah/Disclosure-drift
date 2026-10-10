"""Inventory a manually downloaded WRDS daily CSV without connecting to WRDS."""

import argparse
import json
from pathlib import Path

from disclosure_research.manual_wrds_intake import inventory_daily
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/protocol.json")
    products = parser.add_subparsers(dest="product", required=True)
    daily = products.add_parser("manualdaily")
    actions = daily.add_subparsers(dest="action", required=True)
    command = actions.add_parser("inventory")
    command.add_argument("--source", required=True)
    command.add_argument("--request-start", required=True)
    command.add_argument("--request-end", required=True)
    command.add_argument("--output", required=True, help="New private directory under data/ or outputs/")
    command.add_argument("--allow-extra-columns", action="store_true",
                         help="Preserve extra delivered columns; inventory and duplicates use only the 13 required fields")
    args = parser.parse_args(argv)
    config = load_protocol(args.protocol)
    verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
    receipt = inventory_daily(args.source, request_start=args.request_start,
                              request_end=args.request_end, output=args.output,
                              config=config, repo_root=Path.cwd(),
                              allow_extra_columns=args.allow_extra_columns)
    print(json.dumps({"status": receipt["status"], "source_sha256": receipt["source"]["sha256"],
                      "actual_coverage": receipt["actual_coverage"],
                      "requested_coverage": receipt["requested_coverage"],
                      "all_rows": receipt["all_rows"], "requested_slice": receipt["requested_slice"],
                      "projection": receipt["projection"],
                      "delivered_column_count": receipt["source"]["delivered_column_count"],
                      "full_delivered_row_duplicates_checked": receipt["full_delivered_row_duplicates_checked"],
                      "model_ready": False, "human_approvals": 0}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
