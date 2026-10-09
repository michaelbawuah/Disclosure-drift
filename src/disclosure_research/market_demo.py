"""Invented input files for a reproducible import-to-label engineering check."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .labels import prepare_labels
from .market_data import SCHEMAS, SYNTHETIC, import_market, sha256
from .timing import event_window


def write_fixture(output: str | Path) -> tuple[Path, Path]:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    accepted = "2021-07-02T18:30:00-04:00"
    window = event_window(datetime.fromisoformat(accepted))
    sessions = [window.reference_session, *window.return_sessions]
    daily, links, events = [], [], []
    for number, case in enumerate(["continuing", "delisted", "missing_session"], start=1):
        security = f"SYNTHETIC-{case}"
        cik = str(number).zfill(10)
        for index, session in enumerate(sessions):
            if (case == "delisted" and index > 3) or (case == "missing_session" and index == 3):
                continue
            terminal = case == "delisted" and index == 3
            daily.append({"security_id": security, "session": session,
                          "total_return": -0.5 if terminal else (0.9 if index == 0 else 0.01),
                          "terminal_event": terminal})
        links.append({"cik": cik, "security_id": security, "valid_from": "2020-01-01",
                      "valid_to": "2021-12-31", "mapping_source": "invented fixture mapping",
                      "class_selection_rule": "one invented eligible class"})
        events.append({"event_id": f"SYNTHETIC-EVENT-{case}", "cik": cik,
                       "acceptance_timestamp": accepted, "data_kind": SYNTHETIC})
    tables = {"daily_returns": pd.DataFrame(daily), "security_links": pd.DataFrame(links),
              "market_returns": pd.DataFrame({"session": sessions,
                                               "total_return": [0.8] + [0.002] * 20})}
    manifest = {"schema_version": 1, "data_kind": SYNTHETIC,
                "provider": "invented arithmetic fixture", "dataset": "three synthetic securities",
                "release": "fixture-v1", "exported_at": "2026-10-09T00:00:00+00:00",
                "source_documentation": "src/disclosure_research/market_demo.py; no vendor data",
                "normalization_notes": "Invented decimal returns. Delisting payoff -0.5 appears once.",
                "normalization_code_sha256": sha256(Path(__file__).read_bytes()),
                "stock_return_convention": "dividends_and_delisting_exactly_once",
                "benchmark_convention": "value_weighted_total_return",
                "benchmark_description": "Invented benchmark arithmetic; not an actual market index",
                "raw_exports": [], "tables": {}}
    for name, frame in tables.items():
        path = output / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        digest = sha256(path.read_bytes())
        manifest["raw_exports"].append({"source_table": f"invented.{name}", "sha256": digest})
        manifest["tables"][name] = {"path": path.name, "sha256": digest,
                                    "field_mapping": {key: f"invented {key}" for key in SCHEMAS[name]}}
    manifest_path, events_path = output / "manifest.json", output / "events.parquet"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    pd.DataFrame(events).to_parquet(events_path, index=False)
    return manifest_path, events_path


def run_demo(output: str | Path, config: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="disclosure-market-demo-") as temp:
        root = Path(temp)
        manifest, events = write_fixture(root / "inputs")
        import_market(manifest, root / "bundle", config)
        summary = prepare_labels(events, root / "bundle", root / "labels", config)
        labels = pd.read_parquet(root / "labels/event_labels.parquet").set_index("event_id")
        expected = {"SYNTHETIC-EVENT-continuing": 1.01 ** 20 - 1.002 ** 20,
                    "SYNTHETIC-EVENT-delisted": 1.01 ** 2 * 0.5 - 1.002 ** 20}
        for event_id, target in expected.items():
            if not np.isclose(labels.loc[event_id, "target"], target, rtol=1e-12, atol=1e-12):
                raise ValueError("Synthetic label differs from independent compound-return arithmetic")
        if summary["events_excluded"] != 1 or not labels.loc[
                "SYNTHETIC-EVENT-missing_session", "exclusion_reason"].startswith("Missing stock session"):
            raise ValueError("Synthetic missing return was not excluded")
        summary["independent_arithmetic_check"] = "passed"
        summary["interpretation"] = "Invented engineering cases only; no empirical performance result"
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        labels.reset_index().to_csv(output / "synthetic_labels.csv", index=False)
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        return summary
