"""Independently verify every stored original SEC cover-class lexical case and context."""

import argparse
import json
from pathlib import Path

from disclosure_research.protocol import load_protocol, verify_lock
from disclosure_research.sec_cover_class_verifier import verify_original_cover_class


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--class-audit", required=True)
    cli.add_argument("--sec-gzip", required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--protocol", default="configs/protocol.json")
    args = cli.parse_args(argv)
    config = load_protocol(args.protocol)
    verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
    print(json.dumps(
        verify_original_cover_class(args.class_audit, args.sec_gzip, args.output,
                                    config=config, repo_root=Path.cwd()),
        indent=2, sort_keys=True,
    ))


if __name__ == "__main__":
    raise SystemExit(main())
