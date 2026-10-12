"""Reconstruct original SEC stock facts and annual stability independently."""

import argparse
import json
from pathlib import Path

from disclosure_research.paired_stock_class_verifier import verify_paired_source
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--paired", required=True)
    cli.add_argument("--class-audit", required=True)
    cli.add_argument("--sec-gzip", required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--protocol", default="configs/protocol.json")
    args = cli.parse_args(argv)
    cfg = load_protocol(args.protocol)
    verify_lock(cfg, Path(args.protocol).with_name("protocol.lock.json"))
    print(json.dumps(verify_paired_source(
        args.paired, args.class_audit, args.sec_gzip, args.output,
        config=cfg, repo_root=Path.cwd(),
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
