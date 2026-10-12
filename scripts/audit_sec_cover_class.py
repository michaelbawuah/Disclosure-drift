"""Inspect original SEC cover symbol/title/stock-axis lexical contexts for the 41 pilot cases."""

import argparse
import json
from pathlib import Path

from disclosure_research.protocol import load_protocol, verify_lock
from disclosure_research.sec_cover_class_triage import run_cover_class_triage


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--sec-gzip", required=True)
    parser.add_argument("--sec-execution", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--protocol", default="configs/protocol.json")
    args = parser.parse_args(argv)
    config = load_protocol(args.protocol)
    verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
    result = run_cover_class_triage(
        args.matrix, args.sec_gzip, args.sec_execution, args.output,
        config=config, repo_root=Path.cwd(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
