"""Rebuild the expanded, SEC-only pilot from preserved baseline and new sources."""

import argparse
import json
from pathlib import Path

from disclosure_research.pilot_expansion import combine_pilot_sources
from disclosure_research.protocol import load_protocol, verify_lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", nargs="+", default=["data/processed/pilot-resolved",
                                                       "data/processed/pilot-expansion-2019-2021-resolved"])
    parser.add_argument("--output", required=True)
    parser.add_argument("--cache", default="data/raw/sec_cache")
    parser.add_argument("--resolutions", default="configs/pilot_expansion_resolutions.json")
    parser.add_argument("--protocol", default="configs/protocol.json")
    args = parser.parse_args()
    config = load_protocol(args.protocol)
    verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
    result = combine_pilot_sources(args.sources, args.output, args.cache, args.resolutions, config)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
