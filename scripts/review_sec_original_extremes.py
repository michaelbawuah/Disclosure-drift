"""Reinspect SEC original Item 1A for four posthoc selected diagnostic issuers."""

import argparse
import json
import os
from pathlib import Path

from disclosure_research.protocol import load_protocol, verify_lock
from disclosure_research.sec_sample_original_review import review_diagnostic_sec_originals


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--sources", default="reports/pilot_expansion")
    cli.add_argument("--baseline", required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--pace", type=float, default=1.3)
    cli.add_argument("--protocol", default="configs/protocol.json")
    args = cli.parse_args(argv)
    cfg = load_protocol(args.protocol)
    verify_lock(cfg, Path(args.protocol).with_name("protocol.lock.json"))
    print(json.dumps(review_diagnostic_sec_originals(
        args.sources, args.baseline, args.output,
        user_agent=os.environ.get("SEC_USER_AGENT", ""),
        config=cfg, repo_root=Path.cwd(), pace=args.pace
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
