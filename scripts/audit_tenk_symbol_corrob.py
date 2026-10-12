"""Audit original 10-K cover TradingSymbol lexical facts against dated CRSP Names."""

import argparse
import json
from pathlib import Path

from disclosure_research.protocol import load_protocol, verify_lock
from disclosure_research.tenk_symbol_corrob import run_tenk_symbol_corrob


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--market-candidates", required=True)
    cli.add_argument("--sec-report-gzip", required=True)
    cli.add_argument("--sec-execution", required=True)
    cli.add_argument("--names-csv", required=True)
    cli.add_argument("--names-sha256", required=True)
    cli.add_argument("--names-inventory", required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--protocol", default="configs/protocol.json")
    args = cli.parse_args(argv)
    config = load_protocol(args.protocol)
    verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
    summary = run_tenk_symbol_corrob(
        args.market_candidates, args.sec_report_gzip, args.sec_execution,
        args.names_csv, args.names_sha256, args.names_inventory, args.output,
        config=config, repo_root=Path.cwd(),
    )
    print(json.dumps(summary, sort_keys=True, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
