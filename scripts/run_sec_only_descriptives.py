"""Build the separate exploratory SEC-only 2015–2021 Item 1A drift study."""

import argparse
import json
from pathlib import Path

from disclosure_research.protocol import load_protocol, verify_lock
from disclosure_research.sec_only_disclosure_descriptives import run_sec_only_descriptives


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", default="reports/pilot_expansion")
    parser.add_argument("--output", required=True)
    parser.add_argument("--protocol", default="configs/protocol.json")
    args = parser.parse_args(argv)
    cfg = load_protocol(args.protocol)
    verify_lock(cfg, Path(args.protocol).with_name("protocol.lock.json"))
    print(json.dumps(run_sec_only_descriptives(
        args.sources, args.output, config=cfg, repo_root=Path.cwd()
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
