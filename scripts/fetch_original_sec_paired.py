"""Retrieve the 16 immutable-mapped original SEC 10-K primaries and headers.

Set SEC_USER_AGENT in the shell to a legitimate identity/contact email; do
not put credentials or contact details inside saved public evidence files.
"""

import argparse
import json
import os
from pathlib import Path

from disclosure_research.protocol import load_protocol, verify_lock
from disclosure_research.sec_original_revisit import fetch_original_sec_16


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--paired", required=True)
    cli.add_argument("--manifest", required=True)
    cli.add_argument("--sec-gzip", required=True)
    cli.add_argument("--sec-execution", required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--delay", type=float, default=1.3)
    cli.add_argument("--protocol", default="configs/protocol.json")
    args = cli.parse_args(argv)
    cfg = load_protocol(args.protocol)
    verify_lock(cfg, Path(args.protocol).with_name("protocol.lock.json"))
    report = fetch_original_sec_16(
        args.paired, args.manifest, args.sec_gzip,
        args.sec_execution, args.output,
        user_agent=os.environ.get("SEC_USER_AGENT", ""),
        config=cfg, repo_root=Path.cwd(), delay=args.delay,
    )
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
