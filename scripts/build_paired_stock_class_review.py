"""Stage original SEC registered-security title pairs for source-only review."""

import argparse
import json
from pathlib import Path

from disclosure_research.paired_stock_class_review import build_paired_stock_class_review
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class-audit", required=True)
    parser.add_argument("--sec-gzip", required=True)
    parser.add_argument("--sec-execution", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--protocol", default="configs/protocol.json")
    args = parser.parse_args(argv)
    config = load_protocol(args.protocol)
    verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
    print(json.dumps(build_paired_stock_class_review(
        args.class_audit, args.sec_gzip, args.sec_execution, args.output,
        config=config, repo_root=Path.cwd()
    ), sort_keys=True, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
