"""Build provisional numerical candidates from a preserved WRDS source stage."""

import argparse
import json
from decimal import DecimalException
from pathlib import Path

import duckdb
import pyarrow as pa

from disclosure_research.manual_wrds_candidates import build_candidates
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/protocol.json")
    parser.add_argument("--stage", required=True)
    parser.add_argument("--output", required=True, help="New private directory under data/ or outputs/")
    args = parser.parse_args(argv)
    try:
        config = load_protocol(args.protocol)
        verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
        receipt = build_candidates(args.stage, output=args.output, config=config, repo_root=Path.cwd())
    except (ValueError, OSError, TypeError, KeyError, DecimalException, duckdb.Error, pa.ArrowException) as exc:
        print(json.dumps({"status": "CANDIDATE_STAGE_FAILED", "error_type": type(exc).__name__,
                          "model_ready": False, "source_approvals": 0}))
        return 1
    print(json.dumps({"status": receipt["status"], "coverage": receipt["coverage"],
                      "reconciliation": receipt["reconciliation"],
                      "candidate_rows": receipt["projection"]["candidate_rows"],
                      "equivalent_13_field_record_excess":
                          receipt["projection"]["equivalent_13_field_record_excess"],
                      "conflicting_security_date_keys":
                          receipt["projection"]["conflicting_security_date_keys"],
                      "counts": receipt["counts"], "model_ready": False,
                      "source_approvals": 0}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
