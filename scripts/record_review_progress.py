"""Preserve a prior user arithmetic verdict or reproduce assistant source checks."""

import argparse
import json

from disclosure_research.review_progress import (
    build_assistant_source_progress,
    record_user_arithmetic_review,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    arithmetic = commands.add_parser("user-arithmetic", help="Record an explicit prior user verdict")
    arithmetic.add_argument("--archive", required=True, help="Original M5 review-followup ZIP")
    arithmetic.add_argument("--packet", required=True, help="Unchanged original private arithmetic packet")
    arithmetic.add_argument("--statement", required=True, help="Prior user statement and provenance JSON")
    arithmetic.add_argument("--reproduced-results", help="Optional unchanged-script reproduction results")
    arithmetic.add_argument("--output", required=True, help="New immutable private record directory")
    source = commands.add_parser("assistant-sources", help="Revalidate recorded assistant source inspections")
    source.add_argument("--root", default=".")
    source.add_argument("--reviews", required=True, help="Explicit assistant boundary/timing decisions JSONL")
    source.add_argument("--output", required=True, help="New source-review directory")
    args = parser.parse_args()
    if args.command == "user-arithmetic":
        result = record_user_arithmetic_review(args.archive, args.packet, args.statement,
                                               args.output, args.reproduced_results)
    else:
        result = build_assistant_source_progress(args.root, args.reviews, args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
