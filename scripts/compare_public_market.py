"""Compare current public Fama-French daily market factors with preserved CRSP development data."""

import argparse
import json
from pathlib import Path

from disclosure_research.protocol import load_protocol, verify_lock
from disclosure_research.public_benchmark_check import compare_public_benchmark


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-zip", required=True, help="Manually saved original Fama-French ZIP")
    parser.add_argument("--market-csv", required=True, help="Unchanged original CRSP development CSV")
    parser.add_argument("--market-receipt", required=True, help="Original signed-by-hash inventory receipt")
    parser.add_argument("--output", required=True, help="New private path under data/ or outputs/")
    parser.add_argument("--protocol", default="configs/protocol.json")
    args = parser.parse_args(argv)
    config = load_protocol(args.protocol)
    verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
    summary = compare_public_benchmark(args.public_zip, args.market_csv, args.market_receipt,
                                       args.output, config=config, repo_root=Path.cwd())
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
