"""Publish aggregate-only QA checkpoint after independently checking private outcomes."""

import argparse
import json
from pathlib import Path

from disclosure_research.alternative_checkpoint import build_checkpoint
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--protocol", default="configs/protocol.json")
    args = parser.parse_args(argv)
    config = load_protocol(args.protocol)
    verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
    final = build_checkpoint(args.pilot, args.benchmark, args.output, config)
    print(json.dumps(final, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
