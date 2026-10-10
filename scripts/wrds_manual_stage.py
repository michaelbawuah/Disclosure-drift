"""Project preserved manual WRDS development inventories without contacting WRDS."""

import argparse
import csv
import json
from pathlib import Path

import pyarrow as pa

from disclosure_research.manual_wrds_stage import SourceStageError, aggregate_summary, stage_manual_development
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/protocol.json")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("stage")
    command.add_argument("--daily-inventory", required=True, action="append",
                         help="Preserved daily inventory directory; repeat for every batch")
    command.add_argument("--market-inventory", required=True,
                         help="Preserved independent dlycaldt/vwretd inventory directory")
    command.add_argument("--request-start", required=True)
    command.add_argument("--request-end", required=True)
    command.add_argument("--output", required=True, help="New private directory under data/ or outputs/")
    args = parser.parse_args(argv)
    try:
        config = load_protocol(args.protocol)
        verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
        receipt = stage_manual_development(args.daily_inventory, args.market_inventory,
                                           request_start=args.request_start, request_end=args.request_end,
                                           output=args.output, config=config, repo_root=Path.cwd())
    except (ValueError, OSError, csv.Error, pa.ArrowException) as exc:
        # Underlying CSV/OS exceptions can contain raw cells or local identifiers.
        # Return only the error category and our aggregate-only market evidence.
        print(json.dumps({"status": "SOURCE_STAGE_FAILED", "error_type": type(exc).__name__,
                          "evidence": exc.evidence if isinstance(exc, SourceStageError) else {},
                          "model_ready": False, "source_approvals": 0}, indent=2))
        return 1
    print(json.dumps(aggregate_summary(receipt), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
