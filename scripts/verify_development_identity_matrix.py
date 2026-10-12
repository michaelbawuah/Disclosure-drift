"""Independently verify private 2015-2021 source descriptor matrices."""

import argparse
import json
from pathlib import Path

from disclosure_research.development_identity_matrix_verifier import independently_verify_event_matrix
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--matrix", required=True)
    cli.add_argument("--market", required=True)
    cli.add_argument("--names", required=True)
    cli.add_argument("--ccm", nargs=2, required=True)
    cli.add_argument("--sec-gzip", required=True)
    cli.add_argument("--anchor", required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--protocol", default="configs/protocol.json")
    args = cli.parse_args(argv)
    config = load_protocol(args.protocol)
    verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
    result = independently_verify_event_matrix(
        args.matrix, args.market, args.names, args.ccm,
        args.sec_gzip, args.anchor, args.output,
        config=config, repo_root=Path.cwd(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
