"""Reconstruct prior issuer-anchor match directly from original 2019Q4 SEC and Names files."""

import argparse
import json
from pathlib import Path

from disclosure_research.pilot_issuer_anchor_verifier import independently_verify_anchor


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--anchor", required=True)
    cli.add_argument("--ownership-receipt", required=True)
    cli.add_argument("--sec-submission", required=True)
    cli.add_argument("--names-csv", required=True)
    cli.add_argument("--output", required=True, help="New public aggregate under reports/")
    args = cli.parse_args(argv)
    result = independently_verify_anchor(
        args.anchor, args.ownership_receipt, args.sec_submission,
        args.names_csv, args.output, repo_root=Path.cwd(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
