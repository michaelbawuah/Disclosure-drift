"""Run strictly non-authoritative, development-only modeling on existing pilot evidence."""

import argparse
import json
from pathlib import Path

from disclosure_research.exploratory_sec_pilot import run_exploratory_sec_pilot
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-candidates", required=True)
    parser.add_argument("--text-features", required=True)
    parser.add_argument("--output", required=True, help="Unused private path under data/ or outputs/")
    parser.add_argument("--protocol", default="configs/protocol.json")
    args = parser.parse_args(argv)
    config = load_protocol(args.protocol)
    verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
    result = run_exploratory_sec_pilot(args.market_candidates, args.text_features,
                                       args.output, config, Path.cwd())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
