"""One frozen primary comparison, annual refits and a persistent access ledger.

Every non-target input and empirical gate is checked before final targets are
opened. Once opened, a repository-local ledger binds this protocol to that exact
freeze. Reproduction of the same freeze is allowed; changed freezes are refused.
"""

from __future__ import annotations

import json
import hashlib
import io
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from .evaluation import block_interval, incremental_r2
from .features import FEATURE_NAMES, TextChangeFeatures
from .freeze import (
    AUDIT_CHECKS, EMPIRICAL, FEATURE_COLUMNS, SYNTHETIC, FinalAccessBlocked,
    FreezeValidationError, _inspect_prerequisites, _manifest_blockers, _validate_exclusions,
    artifact, create_freeze, file_sha256, load_freeze, read_json, read_target_free_parquet,
    validate_features, validate_targets, verify_artifact, write_json_exclusive,
)
from .market_data import strings
from .modeling import NUMERIC_CONTROLS, development_comparison, pipeline
from .protocol import canonical_hash, eligible_training


def _validate_before_targets(receipt: dict, config: dict, repo_root: str | Path,
                             synthetic: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    kind = SYNTHETIC if synthetic else EMPIRICAL
    if receipt.get("data_kind") != kind:
        raise FinalAccessBlocked("Synthetic freeze cannot authorize empirical evaluation or vice versa")
    if not synthetic and (receipt.get("empirical_ready") is not True
                          or receipt.get("prerequisites_verified") is not True):
        raise FinalAccessBlocked("Final evaluation blocked: " + "; ".join(receipt.get("blockers", [])))
    if receipt.get("engineering_ready") is not True:
        raise FinalAccessBlocked("Final evaluation blocked: complete split final inputs were not frozen")
    artifacts = receipt.get("artifacts", {})
    required = {"development_dataset", "development_predictions", "selection", "dataset_manifest",
                "exclusions", "audit_evidence", "secondary_spec", "final_features", "final_targets",
                "final_manifest", "final_exclusions"}
    if not required.issubset(artifacts):
        raise FinalAccessBlocked("Final evaluation blocked: frozen artifact bundle is incomplete")
    # Target bytes themselves are checked only after every gate and ledger check.
    for name, item in artifacts.items():
        if name != "final_targets":
            verify_artifact(item, name)
    for item in receipt.get("evidence_files", []):
        if Path(item["path"]).resolve() == Path(artifacts["final_targets"]["path"]).resolve():
            raise FreezeValidationError("Final target file cannot be used as pre-access audit evidence")
        verify_artifact(item, "source audit evidence")
    args = {name: artifacts[name]["path"] for name in
            ("exclusions", "audit_evidence", "secondary_spec")}
    current, development = _inspect_prerequisites(
        artifacts["development_dataset"]["path"], artifacts["development_predictions"]["path"],
        artifacts["selection"]["path"], manifest=artifacts["dataset_manifest"]["path"],
        config=config, repo_root=repo_root, synthetic=synthetic, reproduce=False, **args,
    )
    if current["development"]["selected"] != receipt.get("development", {}).get("selected"):
        raise FreezeValidationError("Selected penalties differ from the frozen development comparison")
    if not synthetic and current["prerequisites_verified"] is not True:
        raise FinalAccessBlocked("Final evaluation blocked: " + "; ".join(current["blockers"]))
    if receipt.get("preprocessing") != current["preprocessing"]:
        raise FreezeValidationError("Frozen preprocessing specification has changed")
    features_path = Path(artifacts["final_features"]["path"])
    if features_path.resolve() == Path(artifacts["final_targets"]["path"]).resolve():
        raise FreezeValidationError("Final features and targets must be physically separate")
    features = read_target_free_parquet(features_path)
    validate_features(features, config, partition="holdout")
    _validate_exclusions(artifacts["final_exclusions"]["path"], features)
    blockers = _manifest_blockers(
        read_json(artifacts["final_manifest"]["path"]), config, "holdout", kind,
        {name: artifacts[name] for name in ("final_features", "final_targets", "final_exclusions")},
        len(features),
    )
    if not synthetic and blockers:
        raise FinalAccessBlocked("Final evaluation blocked: " + "; ".join(blockers))
    # Prepared empirical bundles also carry individual source- and scope-bound
    # reviews; a mutable aggregate 'approved' word is not sufficient authority.
    from .dataset import load_dataset
    for partition, path in (("development", artifacts["dataset_manifest"]["path"]),
                            ("holdout", artifacts["final_manifest"]["path"])):
        frame, checked = load_dataset(Path(path).parent, config, partition,
                                      require_approved=True, features_only=partition == "holdout")
        if checked["data_kind"] != kind:
            raise FinalAccessBlocked("Prepared dataset kind differs from the freeze")
        expected_frame = features if partition == "holdout" else development
        columns = FEATURE_COLUMNS if partition == "holdout" else FEATURE_COLUMNS + ["target"]
        left = frame[columns].sort_values("observation_id").reset_index(drop=True)
        right = expected_frame[columns].sort_values("observation_id").reset_index(drop=True)
        if not left.equals(right):
            raise FreezeValidationError("Reviewed dataset values differ from the freeze")
        if partition == "holdout":
            features = frame
        else:
            development = frame
    if set(development.observation_id) & set(features.observation_id):
        raise FreezeValidationError("Development and final observation identifiers overlap")
    ids_hash = canonical_hash({"development": sorted(development.observation_id),
                               "final": sorted(features.observation_id)})
    if ids_hash != receipt.get("observation_ids_sha256"):
        raise FreezeValidationError("Final observations differ from the frozen identity manifest")
    if len(features) != receipt.get("final_observations"):
        raise FreezeValidationError("Final row count differs from the freeze")
    return development, features


def _ledger_location(repo_root: str | Path, ledger: str | Path | None, synthetic: bool) -> Path:
    default = Path(repo_root).resolve() / "outputs" / "final-access-ledger"
    if ledger is None:
        return default
    requested = Path(ledger).resolve()
    if not synthetic and requested != default:
        raise FinalAccessBlocked("Empirical execution uses the repository's persistent final-access ledger")
    return requested


def _check_ledger(path: Path, receipt: dict) -> tuple[Path, dict | None]:
    namespace = "synthetic" if receipt["data_kind"] == SYNTHETIC else "empirical"
    study = path / f"{namespace}-{receipt['protocol_sha256']}.json"
    previous = read_json(study) if study.exists() else None
    if previous is not None and (previous.get("freeze_id") != receipt["freeze_id"]
                                 or previous.get("data_kind") != receipt["data_kind"]):
        raise FinalAccessBlocked("This protocol's targets were already opened under a different freeze")
    return study, previous


def _reserve_access(path: Path, receipt: dict, output: Path) -> tuple[Path, Path, dict]:
    path.mkdir(parents=True, exist_ok=True)
    study, previous = _check_ledger(path, receipt)
    lock = study.with_suffix(".running")
    try:
        with lock.open("x") as handle:
            handle.write(json.dumps({"pid": os.getpid(), "freeze_id": receipt["freeze_id"]}) + "\n")
    except FileExistsError as exc:
        raise FinalAccessBlocked("A final run is already active; inspect its persistent access receipt") from exc
    try:
        # Recheck after the exclusive reservation, avoiding check/write races.
        study, previous = _check_ledger(path, receipt)
        now = datetime.now(timezone.utc).isoformat()
        if previous is None:
            write_json_exclusive(study, {
                "schema_version": 1, "protocol_sha256": receipt["protocol_sha256"],
                "freeze_id": receipt["freeze_id"], "data_kind": receipt["data_kind"],
                "first_access_reserved_at": now,
                "target_sha256": receipt["artifacts"]["final_targets"]["sha256"],
                "immutable_rule": "same_freeze_reproduction_only",
            })
        run_id = uuid.uuid4().hex
        event = path / f"{run_id}.access.json"
        record = {"schema_version": 1, "run_id": run_id, "freeze_id": receipt["freeze_id"],
                  "data_kind": receipt["data_kind"], "reserved_at": now, "output": str(output.resolve()),
                  "reproduction": previous is not None, "state": "target_access_reserved"}
        write_json_exclusive(event, record)
        return lock, event, record
    except BaseException:
        lock.unlink(missing_ok=True)
        raise


def _fit_frozen_annual(development: pd.DataFrame, final: pd.DataFrame,
                       receipt: dict, config: dict) -> tuple[pd.DataFrame, list[dict]]:
    """The caller has already passed the gate and recorded target access."""
    history = pd.concat([development, final], ignore_index=True)
    final_years = pd.to_datetime(final.acceptance_date).dt.year
    selected = receipt["development"]["selected"]
    outputs, diagnostics = [], []
    for year in range(config["holdout_start"], config["holdout_end"] + 1):
        test = final.loc[final_years == year].sort_values(["reference_session", "observation_id"]).copy()
        cutoff = str(test.reference_session.min())
        train = eligible_training(history, year, cutoff)
        train = train.loc[pd.to_datetime(train.acceptance_date).dt.year >= config["initial_train_start"]]
        train = train.sort_values(["reference_session", "observation_id"]).copy()
        if len(train) < 10:
            raise FreezeValidationError(f"Insufficient mature prior observations for final year {year}")
        train_years = pd.to_datetime(train.acceptance_date).dt.year
        if (train_years >= year).any() or not (pd.to_datetime(train.label_end) < pd.Timestamp(cutoff)).all():
            raise FreezeValidationError("Future labels entered an annual training fold")
        if set(train.observation_id) & set(test.observation_id):
            raise FreezeValidationError("A final prediction observation also appears in its own training fold")
        features = TextChangeFeatures(config["tfidf_max_features"]).fit(train)
        train_text = features.transform(train)
        test_text = features.transform(test)
        x_train = pd.concat([train[NUMERIC_CONTROLS + ["industry"]], train_text], axis=1)
        x_test = pd.concat([test[NUMERIC_CONTROLS + ["industry"]], test_text], axis=1)
        fit_details, predictions = {}, {}
        for model_name, text in (("baseline", False), ("text", True)):
            alpha = selected[model_name]["alpha"]
            if alpha not in config["ridge_alphas"]:
                raise FreezeValidationError("Frozen alpha is outside the protocol grid")
            model = pipeline(alpha, text)
            model.fit(x_train, train.target)
            values = model.predict(x_test)
            if not np.isfinite(values).all():
                raise FreezeValidationError("Nonfinite final predictions")
            predictions[model_name] = values
            numeric = model.named_steps["preprocess"].named_transformers_["numeric"]
            encoder = model.named_steps["preprocess"].named_transformers_["industry"]
            fit_details[model_name] = {
                "alpha": alpha, "numeric_features": NUMERIC_CONTROLS + (FEATURE_NAMES if text else []),
                "training_imputer_statistics": numeric.named_steps["impute"].statistics_.tolist(),
                "training_scaler_mean": numeric.named_steps["scale"].mean_.tolist(),
                "training_scaler_scale": numeric.named_steps["scale"].scale_.tolist(),
                "training_industries": encoder.categories_[0].tolist(),
            }
        batch = test[["observation_id", "reference_session", "target"]].copy()
        batch["year"] = year
        batch["baseline_prediction"] = predictions["baseline"]
        batch["text_prediction"] = predictions["text"]
        batch["baseline_alpha"] = selected["baseline"]["alpha"]
        batch["text_alpha"] = selected["text"]["alpha"]
        batch["train_rows"] = len(train)
        outputs.append(batch)
        vocabulary = {word: int(index) for word, index in features.vectorizer.vocabulary_.items()}
        diagnostics.append({
            "year": year, "first_reference_session": cutoff, "train_rows": len(train),
            "test_rows": len(test), "max_training_label_end": str(train.label_end.max()),
            "training_acceptance_years": sorted(int(value) for value in train_years.unique()),
            "mature_prior_final_rows": int((train_years >= config["holdout_start"]).sum()),
            "training_observation_ids": train.observation_id.tolist(),
            "training_observation_ids_sha256": canonical_hash({"ids": train.observation_id.tolist()}),
            "vocabulary_terms": len(vocabulary), "vocabulary_sha256": canonical_hash(vocabulary),
            "idf_sha256": hashlib_array(features.vectorizer.idf_),
            "zero_training_vocabulary_pairs": int(train_text.attrs["zero_vocabulary_pairs"]),
            "zero_prediction_vocabulary_pairs": int(test_text.attrs["zero_vocabulary_pairs"]),
            "models": fit_details,
        })
    return pd.concat(outputs, ignore_index=True), diagnostics


def hashlib_array(values: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()


def _frozen_interval(predictions: pd.DataFrame, months: int, config: dict) -> dict:
    """A degenerate interval is a reported result, never a new tuning opportunity."""
    try:
        with np.errstate(over="ignore", invalid="ignore"):
            errors = np.square(predictions.target.to_numpy()[:, None]
                               - predictions[["baseline_prediction", "text_prediction"]].to_numpy())
        if not np.isfinite(errors).all() or not np.isfinite(errors.sum(axis=0)).all():
            raise ValueError("Squared prediction errors overflowed")
        return {"status": "defined", **block_interval(
            predictions, months=months, draws=config["bootstrap_draws"], seed=config["seed"],
        )}
    except ValueError as exc:
        try:
            point = incremental_r2(predictions.target, predictions.baseline_prediction,
                                   predictions.text_prediction)
            if not np.isfinite(point):
                point = None
        except ValueError:
            point = None
        return {"status": "unavailable", "incremental_r2": point, "lower_95": None, "upper_95": None,
                "reason": str(exc), "block_months": months, "draws": config["bootstrap_draws"],
                "seed": config["seed"], "method": "moving_month_blocks_percentile; frozen_settings"}


def evaluate_final(freeze: str | Path, *, output: str | Path, config: dict,
                   repo_root: str | Path = ".", ledger: str | Path | None = None,
                   synthetic: bool = False,
                   target_loader: Callable | None = None) -> dict:
    """Evaluate the exact freeze; a blocked call never invokes target_loader.

    ``target_loader`` exists for I/O adapters and failure-injection tests. Its
    return value is still required to equal the hash-bound on-disk target table.
    Empirical ledgers have one fixed repository location. Synthetic tests can
    use an isolated ledger and always retain explicit non-empirical markers.
    """
    out = Path(output)
    if out.exists():
        raise FreezeValidationError("Final output must be a new directory; existing results are immutable")
    receipt = load_freeze(freeze, config, repo_root)
    development, features = _validate_before_targets(receipt, config, repo_root, synthetic)
    ledger_root = _ledger_location(repo_root, ledger, synthetic)
    _check_ledger(ledger_root, receipt)
    targets_path = Path(receipt["artifacts"]["final_targets"]["path"])
    # All review decisions, code, observations, file hashes and run eligibility
    # now agree. Persist the access intent before opening the target vector.
    out.mkdir(parents=True, exist_ok=False)
    lock = event = None
    try:
        lock, event, access = _reserve_access(ledger_root, receipt, out)
        write_json_exclusive(out / "access_receipt.json", access)
        # Verify and deserialize the same byte snapshot, closing the gap between
        # hashing a path and subsequently reopening a potentially changed file.
        target_bytes = targets_path.read_bytes()
        if hashlib.sha256(target_bytes).hexdigest() != receipt["artifacts"]["final_targets"]["sha256"]:
            raise FreezeValidationError("Frozen artifact hash mismatch: final_targets")
        frozen_targets = pd.read_parquet(io.BytesIO(target_bytes))
        targets = target_loader(targets_path) if target_loader else frozen_targets
        if not isinstance(targets, pd.DataFrame) or set(targets.columns) != {"observation_id", "target"}:
            raise FreezeValidationError("Final targets must contain only observation_id and target")
        strings(targets.observation_id, "final target observation_id")
        validate_targets(targets)
        if (targets.observation_id.duplicated().any()
                or set(targets.observation_id) != set(features.observation_id)):
            raise FreezeValidationError("Final targets must join one-to-one to the identical frozen observations")
        if target_loader is not None:
            left = targets.sort_values("observation_id").reset_index(drop=True)
            right = frozen_targets.sort_values("observation_id").reset_index(drop=True)
            if not left.equals(right):
                raise FreezeValidationError("Target loader returned data different from the frozen file")
        final = features.merge(targets, on="observation_id", validate="one_to_one")
        predictions, folds = _fit_frozen_annual(development, final, receipt, config)
        predictions.to_parquet(out / "final_predictions.parquet", index=False)
        write_json_exclusive(out / "fold_diagnostics.json", folds)
        metrics = {
            "primary": _frozen_interval(predictions, config["bootstrap_months"], config),
            "six_month_sensitivity": _frozen_interval(predictions, config["bootstrap_sensitivity_months"], config),
        }
        by_year = []
        for year, rows in predictions.groupby("year"):
            denominator = float(np.square(rows.target - rows.baseline_prediction).sum())
            by_year.append({"year": int(year), "observations": len(rows),
                            "baseline_sse": denominator,
                            "text_sse": float(np.square(rows.target - rows.text_prediction).sum()),
                            "incremental_r2": incremental_r2(rows.target, rows.baseline_prediction,
                                                              rows.text_prediction) if denominator > 0 else None,
                            "status": "defined" if denominator > 0 else "undefined_zero_baseline_sse"})
        summary = {
            "schema_version": 1, "data_kind": receipt["data_kind"], "freeze_id": receipt["freeze_id"],
            "protocol_sha256": receipt["protocol_sha256"], "code_commit": receipt["code"]["commit"],
            "empirical_ready": not synthetic, "final_period_opened": not synthetic,
            "synthetic_targets_opened": synthetic, "primary_comparison_completed": True,
            "selected_penalties": receipt["development"]["selected"],
            "observations": len(predictions), "annual_folds": len(folds), "metrics": metrics,
            "years": by_year, "common_observations": True,
            "interpretation": ("SYNTHETIC ENGINEERING FIXTURE: invented outcomes; no empirical research finding"
                               if synthetic else "Primary frozen forecast comparison; not a trading-profit or causal claim"),
            "secondary_analyses_complete": False,
            "interval_scope": "Approximate time-block interval conditional on this fitted procedure; four acceptance years",
            "access_ledger": str(ledger_root.resolve()), "access_run_id": access["run_id"],
            "reproduction": access["reproduction"],
        }
        summary["files"] = {name: file_sha256(out / name) for name in
                            ("final_predictions.parquet", "fold_diagnostics.json", "access_receipt.json")}
        write_json_exclusive(out / "final_summary.json", summary)
        write_json_exclusive(event.with_suffix(".complete.json"), {
            "run_id": access["run_id"], "freeze_id": receipt["freeze_id"], "state": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "summary": artifact(out / "final_summary.json"),
        })
        return summary
    except BaseException as exc:
        if event is not None:
            write_json_exclusive(event.with_suffix(".failed.json"), {
                "freeze_id": receipt["freeze_id"], "state": "failed_after_access_reserved",
                "failed_at": datetime.now(timezone.utc).isoformat(), "error_type": type(exc).__name__,
                "note": "Access reservation remains; fixes require the same frozen algorithm and data",
            })
        raise
    finally:
        if lock is not None:
            lock.unlink(missing_ok=True)


def run_synthetic_final_demo(output: str | Path, config: dict, *, repo_root: str | Path = ".",
                             secondary_spec: str | Path | None = None,
                             secondary_builder: Callable | None = None) -> dict:
    """Run historical selection through the gated evaluator on invented inputs."""
    from .dataset import load_dataset, run_synthetic_dataset_demo

    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    dataset_summary = run_synthetic_dataset_demo(out / "datasets", config)
    development_dir, final_dir = out / "datasets" / "development", out / "datasets" / "holdout"
    frame, _ = load_dataset(development_dir, config)
    results, selection = development_comparison(frame, config)
    selection.update(data_kind=SYNTHETIC, empirical_ready=False)
    development_output = out / "development"
    development_output.mkdir()
    predictions_path = development_output / "development_predictions.parquet"
    selection_path = development_output / "selection.json"
    results.to_parquet(predictions_path, index=False)
    write_json_exclusive(selection_path, selection)
    if secondary_builder is not None:
        if secondary_spec is not None:
            raise FreezeValidationError("Provide secondary_spec or secondary_builder, not both")
        secondary_spec = secondary_builder(frame.copy(), out / "secondary-development")
    audit_path = out / "audit_evidence.json"
    bound_inputs = {
        "development_dataset": file_sha256(development_dir / "dataset.parquet"),
        "dataset_manifest": file_sha256(development_dir / "dataset_manifest.json"),
        "exclusions": file_sha256(development_dir / "exclusions.parquet"),
    }
    write_json_exclusive(audit_path, {
        "schema_version": 1, "protocol_sha256": canonical_hash(config), "data_kind": SYNTHETIC,
        "bound_inputs": bound_inputs,
        "checks": {name: {"status": "pending", "reviewer_type": "assistant", "reviewer": "fixture generator",
                          "notes": "Synthetic software verification cannot supply human empirical approval",
                          "evidence": []} for name in AUDIT_CHECKS},
    })
    if secondary_spec is None:
        secondary_spec = out / "secondary_fixture.json"
        write_json_exclusive(secondary_spec, {
            "schema_version": 1, "protocol_sha256": canonical_hash(config), "status": "frozen",
            "data_kind": SYNTHETIC,
            "reference_delays": {"primary": 2, "secondary": [1, 5], "status": "fixture_only"},
            "ablations": {"status": "fixture_only", "primary_features": FEATURE_NAMES},
            "paragraph_analysis": {"role": "descriptive_only"},
            "semantic": {"status": "pending", "manual_validation": "not an empirical review"},
            "rule_transition": {"role": "descriptive_coverage_audit"},
            "rank_correlation": {"grouping": "reference_month", "minimum_observations": 3},
            "bootstrap": {"draws": config["bootstrap_draws"], "seed": config["seed"],
                          "months": config["bootstrap_months"],
                          "sensitivity_months": config["bootstrap_sensitivity_months"]},
        })
    frozen = create_freeze(
        development_dir / "dataset.parquet", predictions_path, selection_path,
        output=out / "freeze", config=config, manifest=development_dir / "dataset_manifest.json",
        exclusions=development_dir / "exclusions.parquet", audit_evidence=audit_path,
        secondary_spec=secondary_spec, repo_root=repo_root, synthetic=True,
        final_features=final_dir / "features.parquet", final_targets=final_dir / "targets.parquet",
        final_manifest=final_dir / "dataset_manifest.json", final_exclusions=final_dir / "exclusions.parquet",
    )
    evaluated = evaluate_final(out / "freeze", output=out / "final", config=config,
                               repo_root=repo_root, ledger=out / "ledger", synthetic=True)
    summary = {
        "schema_version": 1, "data_kind": SYNTHETIC, "empirical_ready": False,
        "final_period_opened": False, "synthetic_targets_opened": True,
        "universe_memberships": dataset_summary["universe"]["memberships"],
        "development_rows": len(frame), "final_rows": evaluated["observations"],
        "development_configurations": 8, "development_annual_folds": 6,
        "final_annual_folds": evaluated["annual_folds"], "freeze_id": frozen["freeze_id"],
        "empirical_blockers": frozen["blockers"],
        "paths": {"development_dataset": str((development_dir / "dataset.parquet").resolve()),
                  "development_predictions": str(predictions_path.resolve()),
                  "selection": str(selection_path.resolve()),
                  "holdout_features": str((final_dir / "features.parquet").resolve()),
                  "holdout_targets": str((final_dir / "targets.parquet").resolve()),
                  "freeze": str((out / "freeze" / "freeze.json").resolve()),
                  "final_predictions": str((out / "final" / "final_predictions.parquet").resolve()),
                  "final_summary": str((out / "final" / "final_summary.json").resolve())},
        "interpretation": "Complete software path on invented inputs; empirical research gates remain unresolved",
    }
    write_json_exclusive(out / "synthetic_final_demo.json", summary)
    return summary
