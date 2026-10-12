"""Verify source-based SEC alternative-metric changes with independent Decimal parsing."""

import argparse
import json
from pathlib import Path

from disclosure_research.protocol import load_protocol, verify_lock
from disclosure_research.sec_metric_sensitivity_verifier import independently_verify_metric_sensitivity


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--sources", default="reports/pilot_expansion")
    cli.add_argument("--baseline", required=True)
    cli.add_argument("--sensitivity", required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--protocol", default="configs/protocol.json")
    args = cli.parse_args(argv)
    cfg = load_protocol(args.protocol)
    verify_lock(cfg, Path(args.protocol).with_name("protocol.lock.json"))
    print(json.dumps(independently_verify_metric_sensitivity(
        args.sources, args.baseline, args.sensitivity, args.output,
        config=cfg, repo_root=Path.cwd()
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
