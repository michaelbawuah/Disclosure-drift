"""Build a portable pending filing-review desk or validate a review export."""

import argparse
import json
from pathlib import Path

from disclosure_research.filing_review import build_filing_review, validate_filing_reviews
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--filings", required=True)
    build.add_argument("--pairs", required=True)
    build.add_argument("--audit", required=True)
    build.add_argument("--audit-summary-sha256", required=True)
    build.add_argument("--selected-pairs", required=True)
    build.add_argument("--selected-pairs-sha256", required=True)
    build.add_argument("--reference-template")
    build.add_argument("--reference-template-sha256")
    build.add_argument("--protocol", default="configs/protocol.json")
    build.add_argument("--output", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--packet", required=True)
    validate.add_argument("--packet-sha256", required=True)
    validate.add_argument("--reviews", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            config = load_protocol(args.protocol)
            verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
            result = build_filing_review(
                filings_path=args.filings, pairs_path=args.pairs, audit_dir=args.audit,
                audit_summary_sha256=args.audit_summary_sha256,
                selected_pairs_path=args.selected_pairs,
                selected_pairs_sha256=args.selected_pairs_sha256,
                reference_template_path=args.reference_template,
                reference_template_sha256=args.reference_template_sha256,
                output_dir=args.output, config=config)
        else:
            from disclosure_research.filing_review import _check_hash, _json, _read_bytes

            raw = _read_bytes(args.packet)
            _check_hash(raw, args.packet_sha256, "Review packet")
            result = validate_filing_reviews(_json(raw), args.reviews)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        print(json.dumps({"status": "FILING_REVIEW_FAILED", "error": str(exc),
                          "model_ready": False, "final_period_opened": False}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
