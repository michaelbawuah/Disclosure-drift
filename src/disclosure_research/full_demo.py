"""One-command historical selection through final diagnostics on invented inputs."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .final_evaluation import run_synthetic_final_demo
from .freeze import file_sha256
from .market_demo import run_demo as run_market_demo
from .protocol import canonical_hash
from .robustness import (
    ABLATION_FEATURES, describe_paragraph_changes, development_ablations,
    rebuild_delay_dataset, validate_delay_dataset,
)
from .robustness_run import run_robustness
from .timing import calendar


def _write(path, value):
    with Path(path).open("x") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def run_full_demo(output, config) -> dict:
    out = Path(output)
    if out.exists():
        raise ValueError("Full-demo output exists; use a new run directory")
    out.mkdir(parents=True)
    captured = {}

    def secondary_builder(development, primary_output):
        predictions, selection = development_ablations(development, config)
        secondary = Path(primary_output) / "secondary"
        secondary.mkdir(parents=True)
        predictions.to_parquet(secondary / "development_ablation_predictions.parquet", index=False)
        _write(secondary / "ablation_selection.json", selection)
        spec = json.loads(Path("configs/secondary_analysis.json").read_text())
        spec["data_kind"] = "SYNTHETIC_ENGINEERING_FIXTURE"
        spec["subgroups"]["industry_scheme"] = "SYNTHETIC_ENGINEERING_SECTORS"
        spec["ablations"]["selected_alphas"] = {name: item["alpha"] for name, item in selection["selected"].items()}
        spec["ablations"]["evidence"] = [{"path": str((secondary / "ablation_selection.json").resolve()),
                         "sha256": file_sha256(secondary / "ablation_selection.json")}]
        spec["ablations"]["selection_artifact"] = spec["ablations"]["evidence"][0]
        spec["ablations"]["development_selection_evidence"] = spec["ablations"]["evidence"]
        _write(secondary / "secondary_specification.json", spec)
        captured["selection"] = selection
        captured["development_configurations"] = selection["configurations"]
        return secondary / "secondary_specification.json"

    market = run_market_demo(out / "market-labels", config)
    primary = run_synthetic_final_demo(out / "primary", config, secondary_builder=secondary_builder)
    paths = primary["paths"]
    dev = pd.read_parquet(paths["development_dataset"])
    features = pd.read_parquet(paths["holdout_features"])
    all_data = pd.concat([dev, features], ignore_index=True)
    if not all_data.observation_id.str.startswith("SYNTHETIC").all():
        raise ValueError("Full demonstration accepts invented identifiers only")
    robustness = run_robustness(Path(paths["final_summary"]).parent, paths["freeze"],
                                out / "robustness", config)
    if set(robustness["components"].values()) != {"completed"}:
        raise ValueError(f"Synthetic robustness components failed: {robustness['components']}")
    if robustness["final_target_table_deserialized"] or robustness["new_penalties_selected"]:
        raise ValueError("Secondary diagnostics reopened targets or retuned the frozen procedure")
    ablations = pd.read_parquet(out / "robustness" / "ablation_predictions.parquet")
    paragraph = describe_paragraph_changes(
        "Supplier concentration can disrupt production.\n\nExtreme weather can close facilities.",
        "Cyberattacks may interrupt business.\n\nSupplier concentration can disrupt production.")
    _write(out / "paragraph_example.json", paragraph)

    # Directed synthetic source arithmetic for all three delays, independent of
    # the full fixture's invented labels. Never reuse a primary target or clock.
    sessions = calendar().sessions_in_range("2020-10-01", "2021-05-01").strftime("%Y-%m-%d")
    stock = pd.DataFrame({"security_id": "SYNTHETIC-DELAY", "session": sessions,
                         "total_return": np.linspace(-.002, .003, len(sessions)), "terminal_event": False})
    benchmark = pd.DataFrame({"session": sessions, "total_return": .0001})
    snapshots = pd.DataFrame({"security_id": "SYNTHETIC-DELAY", "session": sessions,
                             "market_cap_usd": 1e10, "industry": "synthetic_industry_A",
                             "industry_scheme": "synthetic_industry"})
    event = pd.DataFrame([{"observation_id": "SYNTHETIC-DELAY-EVENT", "security_id": "SYNTHETIC-DELAY",
                          "acceptance_timestamp": "2021-03-01T18:00:00-05:00",
                          "current_text": "Supplier and cyber disruption.", "previous_text": "Supplier disruption."}])
    availability = pd.DataFrame([{"observation_id": "SYNTHETIC-DELAY-EVENT", "delay": delay,
                       "availability_status": "verified", "public_available_at": "2021-03-01T19:00:00-05:00",
                       "availability_evidence_id": f"SYNTHETIC-AVAILABILITY-{delay}"} for delay in [1, 2, 5]])
    delay_receipts = {}
    for delay in [1, 2, 5]:
        frame, exclusions, receipt = rebuild_delay_dataset(event, stock, benchmark, snapshots, delay, config,
                                                            availability=availability)
        if len(frame) != 1 or len(exclusions):
            raise ValueError("Synthetic source-delay demonstration did not retain its event")
        validate_delay_dataset(frame, delay, receipt, config)
        frame.to_parquet(out / f"delay_{delay}_source_rebuild.parquet", index=False)
        delay_receipts[str(delay)] = receipt
    _write(out / "delay_rebuild_receipts.json", delay_receipts)
    summary = {"schema_version": 1, "data_kind": "SYNTHETIC_ENGINEERING_FIXTURE",
               "protocol_sha256": canonical_hash(config), "empirical_ready": False,
               "final_period_opened": False, "synthetic_final_evaluation_completed": True,
               "development_observations": len(dev), "final_observations": len(features),
               "primary_configurations": 8, "development_folds": 6, "final_folds": 4,
               "ablation_subsets": len(ABLATION_FEATURES),
               "ablation_development_configurations": captured["development_configurations"],
               "ablation_final_predictions": len(ablations), "delay_source_rebuilds": [1, 2, 5],
               "bootstrap_draws_per_interval": config["bootstrap_draws"],
               "robustness_components": robustness["components"],
               "robustness_reused_authorized_predictions": True,
               "market_label_demo": market, "primary_paths": paths,
               "semantic_model_execution": "not_run_optional_dependencies_and_manual_validation_pending",
               "interpretation": "Invented outcomes validate software behavior; no empirical finding or milestone sign-off"}
    _write(out / "full_demo_summary.json", summary)
    return summary
