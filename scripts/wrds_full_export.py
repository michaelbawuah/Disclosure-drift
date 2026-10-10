"""Run locally: PyWRDS handles credential prompts; this script never records them."""

import argparse
import json
from pathlib import Path

from disclosure_research.protocol import canonical_hash, load_protocol, verify_lock
from disclosure_research.wrds_export import (
    DEFAULT_LIBRARIES,
    assemble_wrds_csv,
    discover_wrds_sources,
    export_wrds,
    plan_wrds_exports,
    verify_wrds_export,
)


def main(argv=None, *, connection_factory=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/protocol.json")
    sub = parser.add_subparsers(dest="command", required=True)
    catalog = sub.add_parser("catalog", help="Inspect source metadata only")
    catalog.add_argument("--libraries", nargs="+", default=DEFAULT_LIBRARIES)
    catalog.add_argument("--output", required=True)
    for name in ["plan", "export", "verify", "assemble"]:
        command = sub.add_parser(name)
        choices = ["population", "development", "holdout_population", "holdout"]
        command.add_argument("--partition", choices=choices + (["full_population"] if name == "plan" else []),
                             default="population", help="Default population covers development selection years only")
        if name in ["plan", "export"]:
            command.add_argument("--bindings", default="configs/wrds_sources.template.json")
        if name in ["verify", "assemble"]:
            command.add_argument("--bundle", required=True)
        if name != "verify":
            command.add_argument("--output", required=True)
        if name != "plan":
            command.add_argument("--prerequisites-request")
        if name == "export":
            command.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    config = load_protocol(args.protocol)
    verify_lock(config, Path(args.protocol).with_name("protocol.lock.json"))

    def authorize():
        from disclosure_research.freeze import validate_prerequisites
        if not args.prerequisites_request:
            raise ValueError("A freshly verified development prerequisite request is required for holdout access")
        request = json.loads(Path(args.prerequisites_request).read_text())
        if any(key in request for key in ["config", "repo_root", "synthetic"]):
            raise ValueError("Prerequisite request cannot override protocol, running code or data kind")
        return validate_prerequisites(**request, config=config, repo_root=Path.cwd())

    gate = None
    if args.command not in ["catalog", "plan"] and args.partition in {"holdout_population", "holdout"}:
        # The real prerequisite verifier runs before importing/connecting PyWRDS
        # and before reading any saved holdout source or checkpoint.
        verified = authorize()
        if (not isinstance(verified, dict) or verified.get("prerequisites_verified") is not True
                or verified.get("protocol_sha256") != canonical_hash(config)):
            raise ValueError("Holdout access remains blocked by empirical research prerequisites")
        def gate():
            return verified
    if args.command == "verify":
        result = verify_wrds_export(args.bundle, config, partition=args.partition, authorization=gate)
    elif args.command == "assemble":
        result = assemble_wrds_csv(args.bundle, args.output, config, partition=args.partition,
                                   authorization=gate)
    elif args.command == "plan":
        result = plan_wrds_exports(json.loads(Path(args.bindings).read_text()), config, args.partition)
        out = Path(args.output)
        if out.exists():
            raise ValueError("Plan output exists; preserve the earlier request")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n")
    else:
        if args.command == "catalog" and Path(args.output).exists():
            raise ValueError("Catalog output exists; use a new dated path")
        if connection_factory is None:
            try:
                import wrds
            except ImportError as exc:
                raise ValueError("Run with: uv run --locked --with wrds==3.5.0 python scripts/wrds_full_export.py ...") from exc
            connection_factory = wrds.Connection
        connection = connection_factory()
        try:
            if args.command == "catalog":
                result = discover_wrds_sources(connection, libraries=args.libraries)
                out = Path(args.output)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(result, indent=2) + "\n")
            else:
                result = export_wrds(connection, json.loads(Path(args.bindings).read_text()), args.output,
                                     config, partition=args.partition, resume=args.resume, authorization=gate)
        finally:
            connection.close()
    # Counts and hashes only; never print licensed source rows or authentication.
    print(json.dumps({key: value for key, value in result.items() if key not in
                      {"parts", "jobs", "annual_liquidity_windows", "observed_source_columns"}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
