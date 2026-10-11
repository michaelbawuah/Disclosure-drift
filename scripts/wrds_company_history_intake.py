"""Stage a manually obtained CRSP Company History CSV, without approving historical identities."""
import argparse
import json
from pathlib import Path

from disclosure_research.company_history_intake import build_company_history_intake
from disclosure_research.protocol import load_protocol, verify_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Existing manually authorized source CSV")
    parser.add_argument("--manifest", required=True, help="Source hash, product and explicit field semantics")
    parser.add_argument("--output", required=True, help="Fresh private path under data/ or outputs/")
    parser.add_argument("--protocol", default="configs/protocol.json")
    args = parser.parse_args(argv)
    config = load_protocol(args.protocol)
    verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))
    public = build_company_history_intake(args.source, args.manifest, args.output,
                                          config=config, repo_root=Path.cwd())
    print(json.dumps(public, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
