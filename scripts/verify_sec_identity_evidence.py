"""Verify cached original SEC filer/clock and retain lexical cover evidence offline."""

import argparse
import csv
import json
from pathlib import Path

from lxml import etree

from disclosure_research.protocol import load_protocol, verify_lock
from disclosure_research.sec_identity_evidence import build_sec_identity_evidence, write_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manifest-sha256", required=True, help="Exact expected original manifest SHA-256")
    parser.add_argument("--cache", required=True, help="Existing original SEC .bin/.json cache; never fetched")
    parser.add_argument("--protocol", default="configs/protocol.json")
    parser.add_argument("--output", required=True, help="New deterministic public JSON report; never overwritten")
    args = parser.parse_args(argv)
    try:
        config = load_protocol(args.protocol)
        verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
        report = build_sec_identity_evidence(args.manifest, manifest_sha256=args.manifest_sha256,
                                            cache=args.cache, config=config, repo_root=Path.cwd())
        output = write_report(report, args.output)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, csv.Error, etree.LxmlError) as exc:
        print(json.dumps({"status": "SEC_IDENTITY_EVIDENCE_FAILED", "error_type": type(exc).__name__,
                          "model_ready": False, "source_approvals": 0}))
        return 1
    print(json.dumps({"status": report["status"], "manifest_sha256": report["manifest_sha256"],
                      "summary": report["summary"], "report": output, "original_sec_bytes_reread": True,
                      "model_ready": False, "source_approvals": 0, "prior_arithmetic_review_modified": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
