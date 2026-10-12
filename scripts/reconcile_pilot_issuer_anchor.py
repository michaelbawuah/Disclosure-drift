"""Independently cross-check 2019Q4 original SEC issuer anchor against pilot candidates."""

import argparse
import json
from pathlib import Path

from disclosure_research.pilot_issuer_anchor import run_pilot_anchor
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-candidates", required=True)
    parser.add_argument("--ownership", required=True)
    parser.add_argument("--names-csv", required=True)
    parser.add_argument("--sec-identity-gzip", required=True)
    parser.add_argument("--sec-identity-execution", required=True)
    parser.add_argument("--ownership-receipt-sha256", required=True)
    parser.add_argument("--candidate-receipt-sha256", required=True)
    parser.add_argument("--output", required=True, help="Fresh private directory under data/ or outputs/")
    parser.add_argument("--protocol", default="configs/protocol.json")
    args = parser.parse_args(argv)
    config = load_protocol(args.protocol)
    verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
    public = run_pilot_anchor(
        args.market_candidates, args.ownership, args.names_csv,
        args.sec_identity_gzip, args.sec_identity_execution, args.output,
        config=config, repo_root=Path.cwd(),
        ownership_receipt_sha256=args.ownership_receipt_sha256,
        candidate_receipt_sha256=args.candidate_receipt_sha256,
    )
    print(json.dumps(public, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
