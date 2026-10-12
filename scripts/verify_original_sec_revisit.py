"""Reparse downloaded original SEC 10-K HTML and original SGML headers offline."""

import argparse
import json
from pathlib import Path

from disclosure_research.protocol import load_protocol, verify_lock
from disclosure_research.sec_original_revisit_verifier import reparse_16_sec_originals


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source-intake", required=True)
    cli.add_argument("--prior-gzip", required=True)
    cli.add_argument("--prior-execution", required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--protocol", default="configs/protocol.json")
    args = cli.parse_args(argv)
    cfg = load_protocol(args.protocol)
    verify_lock(cfg, Path(args.protocol).with_name("protocol.lock.json"))
    print(json.dumps(reparse_16_sec_originals(
        args.source_intake, args.prior_gzip, args.prior_execution,
        args.output, config=cfg, repo_root=Path.cwd(),
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
