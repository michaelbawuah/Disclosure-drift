"""Commands default to development data; final empirical evaluation stays gated."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .edgar import SecClient
from .audit import build_audit
from .export_plan import build_export_plan
from .ingest import ingest_smoke
from .labels import export_label_events, prepare_labels
from .market_data import import_market
from .market_demo import run_demo as market_demo
from .modeling import development_comparison
from .protocol import load_protocol, verify_lock, write_lock
from .references import load_reference_rules
from .timing import event_window


def synthetic_dataset() -> pd.DataFrame:
    """Purely invented engineering fixture. Never present its metrics as market research."""
    rng = np.random.default_rng(20261009)
    rows = []
    for year in range(2010, 2022):
        for issuer in range(12):
            window = event_window(datetime(year, 2 + issuer % 6, 15, 18, tzinfo=ZoneInfo("America/New_York")))
            additions = int(rng.integers(1, 20))
            old = "supply demand competition pricing " * 20
            new = old + "cybersecurity disruption regulatory uncertainty " * additions
            rows.append({"observation_id": f"SYNTHETIC-{year}-{issuer}",
                         "acceptance_date": window.acceptance_date,
                         "reference_session": window.reference_session, "label_end": window.label_end,
                         "controls_asof": window.controls_through, "previous_text": old, "current_text": new,
                         "momentum_20": rng.normal(0, 0.04), "momentum_60": rng.normal(0, 0.08),
                         "volatility_20": rng.uniform(0.01, 0.04), "log_market_cap": rng.normal(24, 1),
                         "industry": f"synthetic-sector-{issuer % 3}",
                         "target": -0.04 * np.log1p(additions / 20) + rng.normal(0, 0.005)})
    return pd.DataFrame(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/protocol.json")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("lock-protocol", help="Write or verify the primary protocol fingerprint")
    ingest = commands.add_parser("ingest", help="Download development-year SEC smoke filings")
    ingest.add_argument("--companies", default="configs/smoke_companies.json")
    ingest.add_argument("--output", default="data/processed/smoke")
    ingest.add_argument("--cache", default="data/raw/sec_cache")
    ingest_rules = ingest.add_mutually_exclusive_group()
    ingest_rules.add_argument("--resolutions", default="configs/section_resolutions.json")
    ingest_rules.add_argument("--no-resolutions", action="store_true", help="Reproduce the numbered-section baseline")
    audit = commands.add_parser("audit", help="Build offline source evidence and a review packet")
    audit.add_argument("--filings", default="data/processed/smoke/filings.parquet")
    audit.add_argument("--cache", default="data/raw/sec_cache")
    audit.add_argument("--output", default="outputs/audit-smoke")
    audit.add_argument("--reviews", help="Completed review JSONL; generated templates are never sign-off")
    audit.add_argument("--pairs", help="Optional paired table; defaults to the filings table's sibling")
    audit_rules = audit.add_mutually_exclusive_group()
    audit_rules.add_argument("--resolutions", default="configs/section_resolutions.json")
    audit_rules.add_argument("--no-resolutions", action="store_true", help="Audit the numbered-section baseline")
    demo = commands.add_parser("demo", help="Run the development pipeline on invented fixtures")
    demo.add_argument("--output", default="outputs/demo")
    develop = commands.add_parser("develop", help="Run annual development folds on a prepared Parquet dataset")
    develop.add_argument("--dataset", required=True)
    develop.add_argument("--output", default="outputs/development")
    market_import = commands.add_parser("import-market", help="Validate a normalized development market bundle")
    market_import.add_argument("--manifest", required=True)
    market_import.add_argument("--output", required=True, help="New output directory; existing imports are preserved")
    event_export = commands.add_parser("export-label-events", help="Export an event queue from a fresh source audit")
    event_export.add_argument("--filings", required=True)
    event_export.add_argument("--pairs", required=True)
    event_export.add_argument("--audit", required=True, help="Directory containing the matching offline audit")
    event_export.add_argument("--output", required=True, help="New Parquet event-queue path")
    export_plan = commands.add_parser("plan-market-export", help="Request pilot data without loading outcomes")
    export_plan.add_argument("--events", required=True, help="Audit-bound development event queue")
    export_plan.add_argument("--output", required=True, help="New export-plan directory")
    labels = commands.add_parser("prepare-labels", help="Stage development labels for data QA, not model selection")
    labels.add_argument("--events", required=True)
    labels.add_argument("--market", required=True, help="Validated import directory")
    labels.add_argument("--output", required=True, help="New output directory")
    market_demo_command = commands.add_parser("market-demo", help="Verify invented imports and delisting labels")
    market_demo_command.add_argument("--output", default="outputs/market-demo")
    commands.add_parser("status", help="Show research gates; contains no private account probes")
    commands.add_parser("evaluate-final", help="Show the requirements for final test access")
    args = parser.parse_args(argv)
    config = load_protocol(args.protocol)
    lock = Path(args.protocol).with_name("protocol.lock.json")
    if args.command == "lock-protocol":
        print(json.dumps(write_lock(config, lock), indent=2))
        return 0
    verify_lock(config, lock)
    if args.command == "import-market":
        print(json.dumps(import_market(args.manifest, args.output, config), indent=2))
        return 0
    if args.command == "export-label-events":
        summary = export_label_events(args.filings, args.pairs, args.audit, args.output, config)
        print(json.dumps(summary, indent=2))
        return 0
    if args.command == "prepare-labels":
        summary = prepare_labels(args.events, args.market, args.output, config)
        print(json.dumps(summary, indent=2))
        return 1 if summary["events_excluded"] else 0
    if args.command == "plan-market-export":
        print(json.dumps(build_export_plan(args.events, args.output, config), indent=2))
        return 0
    if args.command == "market-demo":
        print(json.dumps(market_demo(args.output, config), indent=2))
        return 0
    if args.command == "audit":
        resolutions = None if args.no_resolutions else args.resolutions
        summary = build_audit(args.filings, args.cache, args.output,
                              config["development_end"], args.reviews, args.pairs, resolutions)
        print(json.dumps(summary, indent=2))
        return 1 if summary["filings_with_blocking_issues"] else 0
    if args.command == "ingest":
        companies = json.loads(Path(args.companies).read_text())
        if companies["filing_year_end"] > config["development_end"]:
            parser.error("This milestone's ingestion command is restricted to development years")
        client = SecClient(args.cache, os.environ.get("SEC_USER_AGENT", ""))
        resolutions = None if args.no_resolutions else args.resolutions
        summary = ingest_smoke(companies, client, args.output, load_reference_rules(resolutions))
        print(json.dumps(summary, indent=2))
        return 1 if summary["failures"] else 0
    if args.command in {"demo", "develop"}:
        frame = synthetic_dataset() if args.command == "demo" else pd.read_parquet(args.dataset)
        results, selection = development_comparison(frame, config)
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        results.to_parquet(out / "development_predictions.parquet", index=False)
        selection["data_kind"] = "SYNTHETIC_ENGINEERING_FIXTURE" if args.command == "demo" else "user_prepared_development_data"
        selection["rows"] = len(frame)
        (out / "selection.json").write_text(json.dumps(selection, indent=2) + "\n")
        print(json.dumps(selection, indent=2))
        return 0
    gates = {"protocol": "locked", "market_data_access": "requires Cornell WRDS verification and normalized exports",
             "market_import_and_label_staging": "implemented; verified only with invented market data",
             "pre_event_controls": "standalone calculator tested; vendor snapshot adapter pending",
             "manual_filing_audit": "pending", "development_selection_on_real_returns": "pending",
             "embedding_checkpoint_and_protocol": "pending before final test access",
             "final_2022_2025_evaluation": "blocked; no empirical result exists"}
    print(json.dumps(gates, indent=2))
    return 2 if args.command == "evaluate-final" else 0


if __name__ == "__main__":
    raise SystemExit(main())
