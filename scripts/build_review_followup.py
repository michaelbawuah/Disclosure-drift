"""Build the fixed-sample follow-up using the private M5 source archive."""

import argparse
import json
from pathlib import Path

from disclosure_research.review_followup import build_followup

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/reviews/m5-followup-v1"))
    parser.add_argument("--recheck-results", type=Path)
    parser.add_argument("--draft", type=Path)
    args = parser.parse_args()
    print(json.dumps(build_followup(Path("."), args.output, args.recheck_results, args.draft), indent=2))
