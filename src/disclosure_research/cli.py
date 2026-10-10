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
from .crsp_staging import stage_crsp
from .export_plan import build_export_plan
from .ingest import ingest_smoke
from .identity_review import build_identity_review
from .labels import export_label_events, prepare_labels
from .market_data import import_market
from .market_demo import run_demo as market_demo
from .pilot_audit import audit_pilot_market
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
    develop_source = develop.add_mutually_exclusive_group(required=True)
    develop_source.add_argument("--dataset", help="dataset.parquet inside an audited dataset bundle")
    develop_source.add_argument("--bundle", help="Audited build-dataset output directory")
    develop.add_argument("--output", default="outputs/development")
    market_import = commands.add_parser("import-market", help="Validate a normalized development market bundle")
    market_import.add_argument("--manifest", required=True)
    market_import.add_argument("--output", required=True, help="New output directory; existing imports are preserved")
    crsp = commands.add_parser("stage-crsp", help="Stage CIZ CSV/Names exports with unresolved audit gates")
    crsp.add_argument("--daily", required=True)
    crsp.add_argument("--names", required=True)
    crsp.add_argument("--request-start", required=True)
    crsp.add_argument("--request-end", required=True)
    crsp.add_argument("--output", required=True, help="New private staging directory")
    identity = commands.add_parser("review-identities", help="Assemble private historical identity evidence without approving links")
    identity.add_argument("--events", required=True)
    identity.add_argument("--filings", required=True)
    identity.add_argument("--audit", required=True)
    identity.add_argument("--companies", default="configs/pilot_companies.json")
    identity.add_argument("--ccm", required=True, nargs="+")
    identity.add_argument("--names", required=True)
    identity.add_argument("--cache", default="data/raw/sec_cache")
    identity.add_argument("--output", required=True, help="New private review directory")
    pilot_audit = commands.add_parser("audit-pilot-market", help="Reconcile candidate labels/controls with raw-source arithmetic")
    for field in ["events", "filings", "audit", "identity", "staging", "daily", "names", "plan", "output"]:
        pilot_audit.add_argument("--" + field, required=True)
    pilot_audit.add_argument("--reviews", help="Optional evidence-bound human or assistant trace reviews")
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
    universe = commands.add_parser("build-universe", help="Select each historical year-start issuer universe")
    universe.add_argument("--manifest", required=True)
    universe.add_argument("--output", required=True)
    full_plan = commands.add_parser("plan-full-export", help="Create an outcome-free request for the full historical study")
    full_plan.add_argument("--output", required=True)
    historical = commands.add_parser("ingest-universe", help="Collect SEC filings for source-bound historical universe members")
    historical.add_argument("--universe", required=True)
    historical.add_argument("--partition", choices=["development", "holdout"], default="development")
    historical.add_argument("--prerequisites-request", help="JSON paths for freshly verified development prerequisites")
    historical.add_argument("--cache", default="data/raw/sec_cache")
    historical.add_argument("--resolutions", default="configs/section_resolutions.json")
    historical.add_argument("--output", required=True)
    dataset = commands.add_parser("build-dataset", help="Join reviewed pairs, labels, controls and historical membership")
    dataset.add_argument("--manifest", required=True)
    dataset.add_argument("--output", required=True)
    dataset.add_argument("--partition", choices=["development", "holdout"], default="development")
    dataset.add_argument("--prerequisites-request", help="JSON paths for freshly verified development prerequisites")
    checkpoint = commands.add_parser("pilot-checkpoint", help="Build SEC-only coverage and descriptive text distributions")
    checkpoint.add_argument("--pairs", default="data/processed/pilot-resolved/filing_pairs.parquet")
    checkpoint.add_argument("--filings", default="data/processed/pilot-resolved/filings.parquet")
    checkpoint.add_argument("--audit", default="outputs/audit-pilot-resolved")
    checkpoint.add_argument("--output", required=True)
    pilot_smoke = commands.add_parser("pilot-baseline", help="Run fixed-alpha controls-only smoke on an audited pilot")
    pilot_smoke.add_argument("--bundle", required=True)
    pilot_smoke.add_argument("--output", required=True)
    freeze = commands.add_parser("freeze-development", help="Freeze audited development choices and final input fingerprints")
    freeze.add_argument("--request", required=True, help="JSON object of create_freeze input paths")
    freeze.add_argument("--output", required=True)
    freeze.add_argument("--synthetic", action="store_true", help="Only for labeled invented engineering fixtures")
    final = commands.add_parser("evaluate-final", help="Evaluate a verified freeze or show remaining access requirements")
    final.add_argument("--freeze")
    final.add_argument("--output")
    final.add_argument("--ledger", help="Synthetic ledger override; empirical ledger is fixed inside this repository")
    final.add_argument("--synthetic", action="store_true", help="Only accepts synthetic freezes and targets")
    robustness = commands.add_parser("robustness", help="Run declared diagnostics on a verified completed final run")
    robustness.add_argument("--final-run", required=True)
    robustness.add_argument("--freeze", required=True)
    robustness.add_argument("--output", required=True)
    full_demo = commands.add_parser("full-demo", help="Exercise the full study with invented data; never empirical evidence")
    full_demo.add_argument("--output", default="outputs/full-demo")
    semantic = commands.add_parser("semantic-features", help="Compute a separate retrospective semantic development comparator")
    semantic.add_argument("--dataset", required=True)
    semantic.add_argument("--partition", choices=["development", "holdout"], default="development")
    semantic.add_argument("--prerequisites-request", help="Verified development prerequisites required for holdout features")
    semantic.add_argument("--spec", default="configs/semantic_retrospective.json")
    semantic.add_argument("--output", required=True)
    semantic_dev = commands.add_parser("semantic-develop", help="Select a separate retrospective semantic model on development data")
    semantic_dev.add_argument("--bundle", required=True)
    semantic_dev.add_argument("--features", required=True)
    semantic_dev.add_argument("--spec", default="configs/semantic_retrospective.json")
    semantic_dev.add_argument("--output", required=True)
    semantic_final = commands.add_parser("semantic-evaluate-final", help="Run only the prebound retrospective semantic secondary model")
    semantic_final.add_argument("--final-run", required=True)
    semantic_final.add_argument("--freeze", required=True)
    semantic_final.add_argument("--output", required=True)
    report = commands.add_parser("research-report", help="Build progress PDFs and SEC-only figures")
    report.add_argument("--checkpoint", default="reports/pilot_checkpoint")
    report.add_argument("--verification", default="reports/build_verification.json")
    report.add_argument("--output", required=True)
    commands.add_parser("status", help="Show research gates; contains no private account probes")
    args = parser.parse_args(argv)
    config = load_protocol(args.protocol)
    lock = Path(args.protocol).with_name("protocol.lock.json")
    if args.command == "lock-protocol":
        print(json.dumps(write_lock(config, lock), indent=2))
        return 0
    verify_lock(config, lock)
    def prerequisites():
        from .freeze import validate_prerequisites
        if not args.prerequisites_request:
            raise ValueError("A verified development prerequisite request is required")
        request = json.loads(Path(args.prerequisites_request).read_text())
        if any(key in request for key in ["config", "repo_root", "synthetic"]):
            raise ValueError("Prerequisite request cannot override protocol, running code or data kind")
        return validate_prerequisites(**request, config=config, repo_root=Path.cwd())

    if args.command == "build-universe":
        from .universe import build_universe
        print(json.dumps(build_universe(args.manifest, args.output, config), indent=2))
        return 0
    if args.command == "plan-full-export":
        from .study import build_full_export_plan
        print(json.dumps(build_full_export_plan(args.output, config), indent=2))
        return 0
    if args.command == "ingest-universe":
        from .study import ingest_historical_universe
        client = SecClient(args.cache, os.environ.get("SEC_USER_AGENT", ""))
        result = ingest_historical_universe(args.universe, client, args.output, config,
                    partition=args.partition, rules=load_reference_rules(args.resolutions),
                    authorization=prerequisites if args.partition == "holdout" else None)
        print(json.dumps(result, indent=2))
        return 1 if result["failures"] else 0
    if args.command == "build-dataset":
        from .dataset import build_dataset
        result = build_dataset(args.manifest, args.output, config, partition=args.partition,
                               authorization=prerequisites if args.partition == "holdout" else None)
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "pilot-checkpoint":
        from .pilot_checkpoint import build_pilot_checkpoint
        print(json.dumps(build_pilot_checkpoint(args.pairs, args.filings, args.audit, args.output, config), indent=2))
        return 0
    if args.command == "pilot-baseline":
        from .dataset import load_dataset
        from .pilot_checkpoint import pilot_baseline
        frame, evidence = load_dataset(args.bundle, config, partition="development")
        years = pd.to_datetime(frame.acceptance_date).dt.year
        results, receipt = pilot_baseline(frame.loc[years.between(2019, 2021)], config, evidence=evidence)
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=False)
        results.to_parquet(out / "pilot_baseline_predictions.parquet", index=False)
        (out / "pilot_baseline_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, indent=2))
        return 0
    if args.command == "freeze-development":
        from .freeze import create_freeze
        request = json.loads(Path(args.request).read_text())
        if any(key in request for key in ["config", "repo_root", "synthetic", "output"]):
            raise ValueError("Freeze request cannot override command protocol, code, output or data kind")
        result = create_freeze(**request, config=config, repo_root=Path.cwd(), output=args.output,
                               synthetic=args.synthetic)
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "evaluate-final" and args.freeze:
        from .final_evaluation import evaluate_final
        if not args.output:
            parser.error("--output is required with --freeze")
        result = evaluate_final(args.freeze, output=args.output, ledger=args.ledger, config=config,
                                repo_root=Path.cwd(), synthetic=args.synthetic)
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "full-demo":
        from .full_demo import run_full_demo
        print(json.dumps(run_full_demo(args.output, config), indent=2))
        return 0
    if args.command == "robustness":
        from .robustness_run import run_robustness
        print(json.dumps(run_robustness(args.final_run, args.freeze, args.output, config,
                                        repo_root=Path.cwd()), indent=2))
        return 0
    if args.command == "semantic-features":
        from .dataset import load_dataset
        from .semantic import compute_semantic_pairs
        if args.partition == "holdout":
            authorization = prerequisites()
            if authorization.get("prerequisites_verified") is not True:
                raise ValueError("Holdout semantic features require completed empirical development prerequisites")
        source = Path(args.dataset)
        bundle = source.parent if source.is_file() else source
        frame, receipt = load_dataset(bundle, config, partition=args.partition,
                                       features_only=args.partition == "holdout")
        frame.attrs["data_kind"] = receipt["data_kind"]
        print(json.dumps(compute_semantic_pairs(frame, args.spec, args.output), indent=2))
        return 0
    if args.command == "semantic-develop":
        from .semantic_model import develop_semantic
        print(json.dumps(develop_semantic(args.bundle, args.features, args.spec, args.output,
                                          config, repo_root=Path.cwd()), indent=2))
        return 0
    if args.command == "semantic-evaluate-final":
        from .semantic_model import evaluate_semantic_final
        print(json.dumps(evaluate_semantic_final(args.final_run, args.freeze, args.output,
                                                 config, repo_root=Path.cwd()), indent=2))
        return 0
    if args.command == "research-report":
        from .reporting import build_progress_report
        print(json.dumps(build_progress_report(args.checkpoint, args.output, verification=args.verification), indent=2))
        return 0
    if args.command == "audit-pilot-market":
        summary = audit_pilot_market(args.events, args.filings, args.audit, args.identity,
                                    args.staging, args.daily, args.names, args.plan, args.output,
                                    config, args.reviews)
        print(json.dumps(summary, indent=2))
        return 1 if summary["qa_cases_blocked"] else 0
    if args.command == "review-identities":
        print(json.dumps(build_identity_review(args.events, args.filings, args.audit,
                         args.companies, args.ccm, args.names, args.cache, args.output, config), indent=2))
        return 0
    if args.command == "stage-crsp":
        print(json.dumps(stage_crsp(args.daily, args.names, args.output, config,
                                    args.request_start, args.request_end), indent=2))
        return 0
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
        if args.command == "demo":
            frame = synthetic_dataset()
            data_kind = "SYNTHETIC_ENGINEERING_FIXTURE"
        else:
            from .dataset import load_dataset
            folder = Path(args.bundle) if args.bundle else Path(args.dataset).parent
            if args.dataset and Path(args.dataset).resolve() != (folder / "dataset.parquet").resolve():
                parser.error("Use dataset.parquet from build-dataset or pass its --bundle directory")
            frame, evidence = load_dataset(folder, config, partition="development")
            data_kind = evidence["data_kind"]
        results, selection = development_comparison(frame, config)
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        results.to_parquet(out / "development_predictions.parquet", index=False)
        selection["data_kind"] = data_kind
        selection["rows"] = len(frame)
        (out / "selection.json").write_text(json.dumps(selection, indent=2) + "\n")
        print(json.dumps(selection, indent=2))
        return 0
    gates = {"protocol": "locked", "market_data_access": "export evidence in reports/market_access_samples.json",
             "market_import_and_label_staging": "implemented; real import still needs source and identity audits",
             "crsp_source_staging": "stage-crsp implemented; staging does not certify research readiness",
             "historical_identity_review": "review-identities assembles evidence; historical link approval is pending",
             "pre_event_controls": "calculator and CRSP snapshot staging implemented; source availability audit required",
             "pilot_arithmetic_audit": "audit-pilot-market reconciles provisional candidate labels/controls; no identity or human approval inferred",
             "manual_filing_audit": "pending", "development_selection_on_real_returns": "pending",
             "embedding_checkpoint_and_protocol": "pending before final test access",
             "historical_universe_and_dataset": "implemented; requires full historical source exports and reviews",
             "development_freeze_and_final_evaluator": "implemented with evidence, code, dataset fingerprints and run ledger",
             "robustness": "year/month, block intervals, ablations, delay rebuilds, subgroups and failure cases implemented",
             "semantic_comparator": "pinned retrospective checkpoint; complete token coverage; manual validation pending",
             "final_2022_2025_evaluation": "blocked; no empirical result exists"}
    print(json.dumps(gates, indent=2))
    return 2 if args.command == "evaluate-final" else 0


if __name__ == "__main__":
    raise SystemExit(main())
