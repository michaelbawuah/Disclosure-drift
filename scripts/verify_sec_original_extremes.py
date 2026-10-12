"""Recalculate sampled current original SEC Item 1A source metrics independently."""

import argparse
import json
from pathlib import Path

from disclosure_research.protocol import load_protocol, verify_lock
from disclosure_research.sec_sample_original_verifier import verify_original_diagnostic_sources


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake", required=True)
    parser.add_argument("--sources", default="reports/pilot_expansion")
    parser.add_argument("--output", required=True)
    parser.add_argument("--protocol", default="configs/protocol.json")
    args = parser.parse_args(argv)
    cfg = load_protocol(args.protocol)
    verify_lock(cfg, Path(args.protocol).with_name("protocol.lock.json"))
    print(json.dumps(verify_original_diagnostic_sources(
        args.intake, args.sources, args.output,
        config=cfg, repo_root=Path.cwd(),
    ), sort_keys=True, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
