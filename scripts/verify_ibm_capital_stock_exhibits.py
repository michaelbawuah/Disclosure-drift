"""Independently reparse the two original IBM Exhibit 4.1 equity sections offline."""

import argparse
import json
from pathlib import Path

from disclosure_research.ibm_capital_stock_exhibits_verifier import independently_verify_ibm_exhibits
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-files", required=True)
    parser.add_argument("--source-pin", required=True)
    parser.add_argument("--audit", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--protocol", default="configs/protocol.json")
    args = parser.parse_args(argv)
    cfg = load_protocol(args.protocol)
    verify_lock(cfg, Path(args.protocol).with_name("protocol.lock.json"))
    print(json.dumps(
        independently_verify_ibm_exhibits(
            args.source_files, args.audit, args.output,
            source_pin_path=args.source_pin,
            config=cfg, repo_root=Path.cwd()
        ),
        indent=2, sort_keys=True,
    ))


if __name__ == "__main__":
    raise SystemExit(main())
