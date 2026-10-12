"""Independently recheck 30 saved current original SEC HTML Item 1A ranges."""

import argparse
import json
from pathlib import Path

from disclosure_research.protocol import load_protocol, verify_lock
from disclosure_research.sec_boundary_review_verifier import independent_boundary_source_recheck


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--diagnostic", required=True)
    cli.add_argument("--class-source", required=True)
    cli.add_argument("--original-features", default="reports/pilot_expansion")
    cli.add_argument("--resolution-rules", default="configs/section_resolutions.json")
    cli.add_argument("--original-sec-gzip", default="reports/sec_identity_evidence.json.gz")
    cli.add_argument("--matrix", required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--protocol", default="configs/protocol.json")
    args = cli.parse_args(argv)
    config = load_protocol(args.protocol)
    verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
    print(json.dumps(independent_boundary_source_recheck(
        args.diagnostic, args.class_source, args.original_features,
        args.resolution_rules, args.original_sec_gzip, args.matrix,
        args.output, config=config, repo_root=Path.cwd(),
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
