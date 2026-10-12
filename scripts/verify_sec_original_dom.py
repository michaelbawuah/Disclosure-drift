"""Walk current original SEC HTML DOM independently of saved lexical fact projections."""

import argparse
import json
from pathlib import Path

from disclosure_research.protocol import load_protocol, verify_lock
from disclosure_research.sec_original_dom_crosscheck import check_current_sec_dom16


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--intake", required=True)
    cli.add_argument("--paired", required=True)
    cli.add_argument("--reparse", required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--protocol", default="configs/protocol.json")
    args = cli.parse_args(argv)
    cfg = load_protocol(args.protocol)
    verify_lock(cfg, Path(args.protocol).with_name("protocol.lock.json"))
    print(json.dumps(check_current_sec_dom16(
        args.intake, args.paired, args.reparse, args.output,
        config=cfg, repo_root=Path.cwd(),
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
