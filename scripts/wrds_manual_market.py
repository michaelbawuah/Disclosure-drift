"""Inventory a manual WRDS dlycaldt/vwretd market CSV without contacting WRDS."""

import argparse
import json
from pathlib import Path

from disclosure_research.manual_wrds_market import inventory_market
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/protocol.json")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("inventory")
    command.add_argument("--source", required=True)
    command.add_argument("--request-start", required=True)
    command.add_argument("--request-end", required=True)
    command.add_argument("--output", required=True, help="New private directory under data/ or outputs/")
    command.add_argument("--sql", help="Optional SQL attachment; copied and never executed")
    args = parser.parse_args(argv)
    config = load_protocol(args.protocol)
    verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
    result = inventory_market(args.source, request_start=args.request_start,
                              request_end=args.request_end, output=args.output, config=config,
                              repo_root=Path.cwd(), sql_source=args.sql)
    print(json.dumps({"status": result["status"], "source_sha256": result["source"]["sha256"],
                      "actual_coverage": result["actual_coverage"],
                      "requested_coverage": result["requested_coverage"],
                      "all_rows": result["all_rows"], "requested_slice": result["requested_slice"],
                      "return_classifications": result["return_classifications"],
                      "sql_status": result["sql"]["status"],
                      "model_ready": False, "source_approvals": 0}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
