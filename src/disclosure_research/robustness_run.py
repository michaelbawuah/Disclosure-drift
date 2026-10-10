"""Secondary reports from an already completed, authorized frozen final run.

This orchestration never reads the final target table into memory, selects a
penalty, grants holdout access, or replaces an existing result. Outcome values
come exclusively from the completed run's hash-bound saved predictions.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from .final_evaluation import _ledger_location, _validate_before_targets
from .freeze import (
    EMPIRICAL, SYNTHETIC, FinalAccessBlocked, FreezeValidationError,
    file_sha256, load_freeze, read_json, verify_artifact, write_json_exclusive,
)
from .protocol import canonical_hash, eligible_training
from .robustness import (
    ABLATION_FEATURES, _frame_hash, _paired, _validate_ablation_selection,
    compare_ablation_predictions, evaluate_ablations, failure_cases,
    prediction_diagnostics, subgroup_diagnostics,
)


def _snapshot(path: Path, expected: str, label: str) -> bytes:
    """Hash the same bytes subsequently decoded, avoiding a hash/read race."""
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise FreezeValidationError(f"Missing valid SHA-256 for {label}")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected:
        raise FreezeValidationError(f"Frozen artifact hash mismatch: {label}")
    return payload


def _timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise FreezeValidationError(f"{label} must be a timezone-aware timestamp") from exc
    if parsed.tzinfo is None or parsed > datetime.now(timezone.utc):
        raise FreezeValidationError(f"{label} must be a past timezone-aware timestamp")
    return parsed


def _authorized_run(final_run: Path, receipt: dict, config: dict, repo_root: Path) -> tuple[dict, dict[str, bytes]]:
    """Verify completed access and output fingerprints before decoding outcomes."""
    summary_path = final_run / "final_summary.json"
    summary = read_json(summary_path)
    synthetic = receipt["data_kind"] == SYNTHETIC
    if (receipt["data_kind"] not in {SYNTHETIC, EMPIRICAL} or summary.get("schema_version") != 1 or
            summary.get("freeze_id") != receipt["freeze_id"] or
            summary.get("data_kind") != receipt["data_kind"] or
            summary.get("protocol_sha256") != canonical_hash(config) or
            summary.get("code_commit") != receipt["code"]["commit"] or
            summary.get("primary_comparison_completed") is not True or
            summary.get("common_observations") is not True or
            summary.get("empirical_ready") is not (not synthetic) or
            summary.get("final_period_opened") is not (not synthetic) or
            summary.get("synthetic_targets_opened") is not synthetic):
        raise FinalAccessBlocked("Robustness requires the completed final run for this exact freeze and data kind")
    if not synthetic and (receipt.get("empirical_ready") is not True or
                          receipt.get("prerequisites_verified") is not True):
        raise FinalAccessBlocked("Empirical robustness cannot bypass unresolved final-access gates")
    if summary.get("selected_penalties") != receipt["development"]["selected"]:
        raise FreezeValidationError("Saved final penalties differ from the frozen development choices")
    run_id = summary.get("access_run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise FreezeValidationError("Final run has no valid access-ledger run identifier")
    ledger_value = summary.get("access_ledger")
    if not isinstance(ledger_value, str) or not ledger_value.strip():
        raise FinalAccessBlocked("Final run has no persistent access-ledger location")
    ledger = _ledger_location(repo_root, ledger_value, synthetic)
    namespace = "synthetic" if synthetic else "empirical"
    study = read_json(ledger / f"{namespace}-{receipt['protocol_sha256']}.json")
    if (study.get("schema_version") != 1 or study.get("protocol_sha256") != receipt["protocol_sha256"] or
            study.get("freeze_id") != receipt["freeze_id"] or study.get("data_kind") != receipt["data_kind"] or
            study.get("target_sha256") != receipt["artifacts"]["final_targets"]["sha256"] or
            study.get("immutable_rule") != "same_freeze_reproduction_only"):
        raise FinalAccessBlocked("Persistent target-access study record does not authorize this freeze")
    complete = read_json(ledger / f"{run_id}.access.complete.json")
    if (complete.get("run_id") != run_id or complete.get("freeze_id") != receipt["freeze_id"] or
            complete.get("state") != "completed" or
            (ledger / f"{run_id}.access.failed.json").exists()):
        raise FinalAccessBlocked("Final access run is incomplete or has conflicting failure evidence")
    completed_at = _timestamp(complete.get("completed_at"), "completed_at")
    complete_summary = complete.get("summary", {})
    if not isinstance(complete_summary.get("path"), str) or Path(complete_summary["path"]).resolve() != summary_path.resolve():
        raise FreezeValidationError("Access completion receipt names a different final summary")
    summary_bytes = _snapshot(summary_path, complete_summary.get("sha256"), "completed final summary")
    if json.loads(summary_bytes) != summary:
        raise FreezeValidationError("Final summary changed while its completion receipt was checked")
    expected_files = {"final_predictions.parquet", "fold_diagnostics.json", "access_receipt.json"}
    if not isinstance(summary.get("files"), dict) or set(summary["files"]) != expected_files:
        raise FreezeValidationError("Final summary must bind the complete prediction/fold/access output set")
    # All bytes are checked before the first prediction/target value is decoded.
    bodies = {name: _snapshot(final_run / name, summary["files"][name], name) for name in sorted(expected_files)}
    access_bytes = _snapshot(ledger / f"{run_id}.access.json", summary["files"]["access_receipt.json"],
                             "persistent access receipt")
    if access_bytes != bodies["access_receipt.json"]:
        raise FreezeValidationError("Saved and persistent final access receipts differ")
    access = json.loads(access_bytes)
    if (access.get("schema_version") != 1 or access.get("run_id") != run_id or
            access.get("freeze_id") != receipt["freeze_id"] or
            access.get("data_kind") != receipt["data_kind"] or
            access.get("state") != "target_access_reserved" or
            access.get("reproduction") != summary.get("reproduction") or
            not isinstance(access.get("output"), str) or Path(access["output"]).resolve() != final_run.resolve()):
        raise FinalAccessBlocked("Final prediction output is not bound to its original access reservation")
    if _timestamp(access.get("reserved_at"), "reserved_at") > completed_at:
        raise FreezeValidationError("Final access completion precedes its reservation")
    summary["verified_summary_sha256"] = complete_summary["sha256"]
    return summary, bodies


def _check_predictions(predictions: pd.DataFrame, features: pd.DataFrame,
                       development: pd.DataFrame, summary: dict, receipt: dict, config: dict) -> pd.DataFrame:
    frame = _paired(predictions)
    if set(frame.observation_id) != set(features.observation_id):
        raise FreezeValidationError("Saved final predictions omit or add frozen observations")
    if (len(frame) != summary.get("observations") or len(frame) != receipt.get("final_observations") or
            summary.get("annual_folds") != config["holdout_end"] - config["holdout_start"] + 1):
        raise FreezeValidationError("Saved final observation/fold counts differ from the freeze")
    frozen = features.set_index("observation_id").loc[frame.observation_id]
    expected_years = pd.to_datetime(frozen.acceptance_date).dt.year
    if (frame.reference_session.tolist() != frozen.reference_session.tolist() or
            frame.year.tolist() != expected_years.tolist() or
            set(frame.year) != set(range(config["holdout_start"], config["holdout_end"] + 1))):
        raise FreezeValidationError("Saved final predictions differ from their frozen event clocks")
    for column, model in (("baseline_alpha", "baseline"), ("text_alpha", "text")):
        if (column not in frame or not is_numeric_dtype(frame[column]) or is_bool_dtype(frame[column]) or
                not frame[column].eq(receipt["development"]["selected"][model]["alpha"]).all()):
            raise FreezeValidationError("Saved final predictions changed the frozen primary penalties")
    if ("train_rows" not in frame or not is_numeric_dtype(frame.train_rows) or is_bool_dtype(frame.train_rows)
            or not np.isfinite(frame.train_rows.to_numpy(dtype=float)).all()):
        raise FreezeValidationError("Saved final predictions need numeric mature training counts")
    chronology = pd.concat([development, features], ignore_index=True)
    for year, group in frame.groupby("year"):
        mature = eligible_training(chronology, int(year), str(group.reference_session.min()))
        mature = mature.loc[pd.to_datetime(mature.acceptance_date).dt.year >= config["initial_train_start"]]
        if not group.train_rows.eq(len(mature)).all():
            raise FreezeValidationError("Saved final training counts violate the frozen maturity rule")
    return frame


def _unavailable(reason: str) -> dict:
    return {"status": "unavailable", "reason": reason}


def _load_authorized_context(final_run: str | Path, freeze: str | Path, config: dict,
                              repo_root: str | Path) -> tuple[pd.DataFrame, dict, dict, pd.DataFrame, pd.DataFrame]:
    final_run, repo_root = Path(final_run), Path(repo_root)
    receipt = load_freeze(freeze, config, repo_root)
    summary, bodies = _authorized_run(final_run, receipt, config, repo_root)
    synthetic = receipt["data_kind"] == SYNTHETIC
    development, features = _validate_before_targets(receipt, config, repo_root, synthetic)
    verify_artifact(receipt["artifacts"]["final_targets"], "frozen final target bytes")
    predictions = _check_predictions(pd.read_parquet(io.BytesIO(bodies["final_predictions.parquet"])),
                                     features, development, summary, receipt, config)
    return predictions, receipt, summary, development, features


def load_authorized_final(final_run: str | Path, freeze: str | Path, config: dict,
                           repo_root: str | Path = ".") -> tuple[pd.DataFrame, dict, dict]:
    """Return saved predictions, freeze and summary after completed-access checks.

This shared secondary-entry gate never deserializes the final target table and
does not reserve new target access. Consumers must additionally enforce their
own pre-access frozen method/artifact specifications.
"""
    predictions, receipt, summary, _, _ = _load_authorized_context(final_run, freeze, config, repo_root)
    return predictions, receipt, summary


def _frozen_ablation_selection(spec: dict, spec_path: Path, receipt: dict,
                               development: pd.DataFrame, config: dict) -> tuple[dict | None, str | None]:
    ablations = spec.get("ablations", {})
    if not isinstance(ablations, dict) or not isinstance(ablations.get("selection_artifact"), dict):
        return None, "No explicit ablations.selection_artifact was bound in the pre-access secondary specification"
    item = ablations["selection_artifact"]
    if not isinstance(item.get("path"), str):
        return None, "Frozen ablation selection artifact has no path"
    path = Path(item["path"])
    path = path if path.is_absolute() else spec_path.parent / path
    path = path.resolve()
    bound = {(str(Path(entry["path"]).resolve()), entry["sha256"]) for entry in receipt.get("evidence_files", [])}
    if (str(path), item.get("sha256")) not in bound:
        return None, "Ablation selection artifact is not bound in the freeze's evidence manifest"
    # Integrity failure raises; unavailable method choices never lead to a new
    # development search after final access.
    payload = _snapshot(path, item.get("sha256"), "frozen ablation selection")
    try:
        selection = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "Frozen ablation selection artifact is not a valid JSON selection"
    if not isinstance(selection, dict):
        return None, "Frozen ablation selection artifact must contain a JSON object"
    try:
        _validate_ablation_selection(selection, config)
    except ValueError as exc:
        return None, str(exc)
    selected = {name: selection["selected"][name]["alpha"] for name in ABLATION_FEATURES}
    if (ablations.get("features") != ABLATION_FEATURES or ablations.get("alphas") != config["ridge_alphas"] or
            ablations.get("selection_metric") != config["tuning_metric"] or
            ablations.get("selected_alphas") != selected):
        return None, "Ablation artifact choices differ from the pre-access secondary specification"
    if selection.get("development_dataset_sha256") != _frame_hash(development):
        return None, "Ablation development selection was produced from a different prepared dataset"
    return selection, None


def run_robustness(final_run: str | Path, freeze: str | Path, output: str | Path,
                   config: dict, repo_root: str | Path = ".") -> dict:
    """Write immutable secondary results from an authorized completed primary run.

Arguments are the directory containing final_summary.json, the matching freeze
directory/file, and a new output directory. Synthetic provenance is inferred only
from the verified freeze and is preserved in every summary. The final target table
is fingerprinted for integrity but never deserialized; saved predictions supply
all final labels. Missing secondary inputs retain explicit unavailable reasons.
"""
    final_run, out, repo_root = Path(final_run), Path(output), Path(repo_root)
    if out.exists():
        raise FreezeValidationError("Robustness output must be a new directory; earlier results are preserved")
    # Revalidate original source-bound reviews and frozen input files before
    # decoding the already opened final prediction outcomes.
    predictions, receipt, summary, development, features = _load_authorized_context(final_run, freeze, config, repo_root)
    synthetic = receipt["data_kind"] == SYNTHETIC
    spec_record = receipt["artifacts"]["secondary_spec"]
    spec_path = Path(spec_record["path"])
    spec = json.loads(_snapshot(spec_path, spec_record["sha256"], "frozen secondary specification"))
    rank_spec = spec.get("rank_correlation", {})
    minimum = rank_spec.get("minimum_observations", 3) if isinstance(rank_spec, dict) else 3
    if (not isinstance(rank_spec, dict) or rank_spec.get("grouping") != "reference_month" or
            minimum != 3):
        raise FreezeValidationError("Reference-month diagnostics must use the frozen minimum-three grouping")
    diagnostics = prediction_diagnostics(predictions, config, minimum_month_observations=minimum)
    subgroups = spec.get("subgroups", {})
    if (not isinstance(subgroups, dict) or "size_cutpoints_usd" not in subgroups or
            not isinstance(subgroups.get("industry_scheme"), str) or
            subgroups.get("selection") != "fixed_before_final_access"):
        subgroup_report = _unavailable("Frozen size cutpoints, industry scheme and pre-access selection declaration are required")
    else:
        try:
            subgroup_report = {"status": "completed", **subgroup_diagnostics(
                predictions, features, size_cutpoints_usd=subgroups["size_cutpoints_usd"],
                industry_scheme=subgroups["industry_scheme"],
            )}
        except (ValueError, KeyError, TypeError) as exc:
            subgroup_report = _unavailable(str(exc))
    try:
        examples = {"status": "completed", "cases": failure_cases(predictions, features),
                    "interpretation": "Outcome-selected descriptive filing examples; never a new exclusion rule"}
    except (ValueError, KeyError, TypeError) as exc:
        examples = _unavailable(str(exc))
    selection, missing = _frozen_ablation_selection(spec, spec_path, receipt, development, config)
    ablation_predictions = None
    if selection is None:
        ablation_report = _unavailable(missing)
    else:
        # Final labels are copied exclusively from the saved, completed primary
        # predictions. No target-file parsing or penalty selection occurs here.
        final = features.merge(predictions[["observation_id", "target"]], on="observation_id", validate="one_to_one")
        full_history = pd.concat([development, final], ignore_index=True)
        ablation_predictions = evaluate_ablations(full_history, selection, config)
        ablation_report = {"status": "completed", **compare_ablation_predictions(
            predictions, ablation_predictions, selection, config)}
    reports = {"diagnostics.json": diagnostics, "subgroups.json": subgroup_report,
               "failure_cases.json": examples, "ablations.json": ablation_report}
    result = {
        "schema_version": 1, "data_kind": receipt["data_kind"], "freeze_id": receipt["freeze_id"],
        "protocol_sha256": receipt["protocol_sha256"], "code_commit": receipt["code"]["commit"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "final_access_run_id": summary["access_run_id"],
        "final_summary_sha256": summary["verified_summary_sha256"],
        "saved_predictions_sha256": summary["files"]["final_predictions.parquet"],
        "observations": len(predictions), "empirical_results": not synthetic,
        "uses_existing_authorized_final_predictions": True,
        "final_target_table_deserialized": False, "new_penalties_selected": False,
        "components": {"diagnostics": "completed", "subgroups": subgroup_report["status"],
                       "failure_cases": examples["status"], "ablations": ablation_report["status"]},
        "delay_comparisons": {"status": "not_run", "delays": [1, 5],
                              "reason": "Requires independent per-delay source label/control rebuilds, availability evidence and receipts"},
        "paragraph_analysis": {"status": "manual_descriptive_review_pending"},
        "semantic_analysis": {"status": "not_run_by_this_orchestrator"},
        "secondary_analyses_complete": False,
        "interpretation": ("SYNTHETIC ENGINEERING FIXTURE: all results use invented outcomes; no empirical finding"
                           if synthetic else "Secondary analyses of the completed frozen primary run; no retuning or new primary selection"),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".robustness-", dir=out.parent) as temporary:
        stage = Path(temporary) / "results"
        stage.mkdir()
        for name, report in reports.items():
            write_json_exclusive(stage / name, report)
        if ablation_predictions is not None:
            ablation_predictions.to_parquet(stage / "ablation_predictions.parquet", index=False)
        result["files"] = {path.name: file_sha256(path) for path in sorted(stage.iterdir())}
        result["summary_id"] = canonical_hash(result)
        write_json_exclusive(stage / "robustness_summary.json", result)
        stage.rename(out)
    return result
