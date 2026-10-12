"""Produce a private evidence-by-event review matrix from already saved original sources."""

import argparse
import json
from pathlib import Path

from disclosure_research.development_identity_matrix import run_development_identity_matrix
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--market-candidates", required=True)
    cli.add_argument("--names-csv", required=True)
    cli.add_argument("--names-inventory", required=True)
    cli.add_argument("--ccm", required=True, nargs=2)
    cli.add_argument("--identity-summary", required=True)
    cli.add_argument("--sec-report-gzip", required=True)
    cli.add_argument("--sec-execution", required=True)
    cli.add_argument("--tenk-audit", required=True)
    cli.add_argument("--issuer-anchor", required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--protocol", default="configs/protocol.json")
    args = cli.parse_args(argv)
    config = load_protocol(args.protocol)
    verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
    result = run_development_identity_matrix(
        args.market_candidates, args.names_csv, args.names_inventory,
        args.ccm, args.identity_summary, args.sec_report_gzip,
        args.sec_execution, args.tenk_audit, args.issuer_anchor, args.output,
        config=config, repo_root=Path.cwd(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
