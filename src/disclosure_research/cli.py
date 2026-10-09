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
from .ingest import ingest_smoke
from .modeling import development_comparison
from .protocol import load_protocol, verify_lock, write_lock
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
    demo = commands.add_parser("demo", help="Run the development pipeline on invented fixtures")
    demo.add_argument("--output", default="outputs/demo")
    develop = commands.add_parser("develop", help="Run annual development folds on a prepared Parquet dataset")
    develop.add_argument("--dataset", required=True)
    develop.add_argument("--output", default="outputs/development")
    commands.add_parser("status", help="Show research gates; contains no private account probes")
    commands.add_parser("evaluate-final", help="Show the requirements for final test access")
    args = parser.parse_args(argv)
    config = load_protocol(args.protocol)
    lock = Path(args.protocol).with_name("protocol.lock.json")
    if args.command == "lock-protocol":
        print(json.dumps(write_lock(config, lock), indent=2))
        return 0
    verify_lock(config, lock)
    if args.command == "ingest":
        companies = json.loads(Path(args.companies).read_text())
        if companies["filing_year_end"] > config["development_end"]:
            parser.error("This milestone's ingestion command is restricted to development years")
        client = SecClient(args.cache, os.environ.get("SEC_USER_AGENT", ""))
        summary = ingest_smoke(companies, client, args.output)
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
             "manual_filing_audit": "pending", "development_selection_on_real_returns": "pending",
             "embedding_checkpoint_and_protocol": "pending before final test access",
             "final_2022_2025_evaluation": "blocked; no empirical result exists"}
    print(json.dumps(gates, indent=2))
    return 2 if args.command == "evaluate-final" else 0


if __name__ == "__main__":
    raise SystemExit(main())
