"""Evidence-bound development freeze, without parsing final-period outcomes.

These fingerprints make changes detectable; they are an audit trail, not a
security boundary. Synthetic fixtures never grant empirical holdout access.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from .features import FEATURE_NAMES, TextChangeFeatures
from .market_data import iso_dates, strings
from .modeling import NUMERIC_CONTROLS, development_comparison
from .protocol import canonical_hash, eligible_training, guard_development, verify_lock
from .timing import NY, event_window

SYNTHETIC = "SYNTHETIC_ENGINEERING_FIXTURE"
EMPIRICAL = "EMPIRICAL_RESEARCH_DATA"
AUDIT_CHECKS = (
    "source_provenance", "historical_universe", "security_links",
    "filing_extraction", "availability_timing", "labels_and_controls",
)
SECONDARY_KEYS = (
    "reference_delays", "ablations", "paragraph_analysis", "semantic",
    "rule_transition", "rank_correlation", "bootstrap",
)
FEATURE_COLUMNS = [
    "observation_id", "acceptance_date", "reference_session", "label_end", "controls_asof",
    "previous_text", "current_text", "industry", *NUMERIC_CONTROLS,
]
OUTCOME_COLUMNS = {
    "target", "stock_return", "market_return", "baseline_prediction", "text_prediction",
    "prediction", "squared_error", "forward_return", "excess_return",
}


class FreezeValidationError(ValueError):
    """A frozen input or research specification is inconsistent."""


class FinalAccessBlocked(FreezeValidationError):
    """A necessary empirical gate has not been satisfied."""


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: str | Path) -> dict:
    def invalid_constant(value):
        raise FreezeValidationError(f"Nonfinite JSON constant: {value}")

    value = json.loads(Path(path).read_text(), parse_constant=invalid_constant)
    if not isinstance(value, dict):
        raise FreezeValidationError(f"Expected a JSON object: {path}")
    return value


def write_json_exclusive(path: str | Path, value: dict | list) -> None:
    with Path(path).open("x") as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def artifact(path: str | Path) -> dict:
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise FreezeValidationError(f"Expected a regular file: {path}")
    return {"path": str(path), "sha256": file_sha256(path), "bytes": path.stat().st_size}


def verify_artifact(item: dict, name: str) -> Path:
    if not isinstance(item, dict) or not isinstance(item.get("path"), str):
        raise FreezeValidationError(f"Missing artifact path: {name}")
    expected = item.get("sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise FreezeValidationError(f"Invalid SHA-256 for {name}")
    path = Path(item["path"])
    if not path.is_file() or file_sha256(path) != expected:
        raise FreezeValidationError(f"Frozen artifact hash mismatch: {name}")
    return path


def code_state(repo_root: str | Path) -> dict:
    root = Path(repo_root).resolve()
    sources = sorted((root / "src" / "disclosure_research").glob("*.py"))
    sources += [root / name for name in (
        "pyproject.toml", "uv.lock", "configs/protocol.json", "configs/protocol.lock.json",
    )]
    if len(sources) < 5 or any(not path.is_file() for path in sources):
        raise FreezeValidationError("Code snapshot requires package sources, lockfiles and protocol")
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all", "--",
             *[str(path.relative_to(root)) for path in sources]],
            check=True, capture_output=True, text=True,
        ).stdout.splitlines()
    except subprocess.CalledProcessError as exc:
        raise FreezeValidationError("A committed Git repository is required for the code freeze") from exc
    return {"commit": commit, "source_sha256": {
        str(path.relative_to(root)): file_sha256(path) for path in sources
    }, "dirty_source_files": status}


def verify_code(snapshot: dict, repo_root: str | Path) -> None:
    current = code_state(repo_root)
    if snapshot != current:
        raise FreezeValidationError("Code commit or source hashes differ from the development freeze")
    # A different checkout may be used only when its code agrees with the code
    # actually imported by this process; a label on an unrelated checkout is not enough.
    package = Path(__file__).resolve().parent
    for name, expected in snapshot["source_sha256"].items():
        if name.startswith("src/disclosure_research/"):
            active = package / Path(name).name
            if not active.is_file() or file_sha256(active) != expected:
                raise FreezeValidationError(f"Running source differs from the frozen checkout: {name}")


def validate_features(frame: pd.DataFrame, config: dict, *, partition: str) -> None:
    """Strict metadata/feature validation, requiring no target values."""
    missing = set(FEATURE_COLUMNS) - set(frame.columns)
    if missing or frame.empty:
        raise FreezeValidationError(f"Empty or incomplete {partition} features: {sorted(missing)}")
    if partition == "holdout" and OUTCOME_COLUMNS.intersection(frame.columns):
        raise FreezeValidationError("Final feature file contains outcome or prediction columns")
    for column in ["observation_id", "industry", "previous_text", "current_text"]:
        strings(frame[column], column)
    if frame.observation_id.duplicated().any():
        raise FreezeValidationError("Duplicate observation identifiers")
    for column in ["acceptance_date", "reference_session", "label_end", "controls_asof"]:
        iso_dates(frame[column], column, sessions=column != "acceptance_date")
    years = pd.to_datetime(frame.acceptance_date).dt.year
    if partition == "development":
        guard_development(frame, config)
        expected = set(range(config["initial_train_start"], config["development_end"] + 1))
    elif partition == "holdout":
        expected = set(range(config["holdout_start"], config["holdout_end"] + 1))
    else:
        raise FreezeValidationError("Unknown dataset partition")
    if set(years) != expected:
        raise FreezeValidationError(f"{partition} acceptance years must be exactly {sorted(expected)}")
    for column in NUMERIC_CONTROLS:
        series = frame[column]
        if (not is_numeric_dtype(series) or is_bool_dtype(series)
                or not np.isfinite(series.to_numpy(dtype=float)).all()):
            raise FreezeValidationError(f"{column} must be finite numeric data, without coercion")
    if (frame.volatility_20 < 0).any():
        raise FreezeValidationError("Volatility cannot be negative")
    TextChangeFeatures._validate(frame)
    # The date-only acceptance is explicitly the already-normalized New York date.
    # Recheck the exact primary session convention, including the 2026 tail.
    windows = {}
    for row in frame.itertuples(index=False):
        if row.acceptance_date not in windows:
            accepted = datetime.fromisoformat(row.acceptance_date).replace(tzinfo=NY)
            windows[row.acceptance_date] = event_window(
                accepted, config["reference_session_offset"], config["horizon_sessions"],
            )
        window = windows[row.acceptance_date]
        if (row.reference_session != window.reference_session
                or row.controls_asof != window.controls_through
                or row.label_end != window.label_end):
            raise FreezeValidationError("Dataset timing differs from the frozen primary event window")


def validate_targets(frame: pd.DataFrame) -> None:
    if "target" not in frame:
        raise FreezeValidationError("Target column is missing")
    values = frame.target
    if (not is_numeric_dtype(values) or is_bool_dtype(values)
            or not np.isfinite(values.to_numpy(dtype=float)).all()):
        raise FreezeValidationError("Targets must be finite numeric data, without coercion")


def read_target_free_parquet(path: str | Path) -> pd.DataFrame:
    """Inspect column names before reading any potentially misplaced final values."""
    names = set(pq.read_schema(path).names)
    if OUTCOME_COLUMNS & names:
        raise FreezeValidationError("Target-free file contains outcome or prediction columns")
    return pd.read_parquet(path)


def _selection_check(frame: pd.DataFrame, predictions: pd.DataFrame, selection: dict,
                     config: dict, *, reproduce: bool) -> dict:
    needed = {"observation_id", "year", "target", "reference_session", "model", "alpha",
              "prediction", "train_rows"}
    if needed - set(predictions.columns) or predictions.empty:
        raise FreezeValidationError("Development predictions are incomplete")
    strings(predictions.observation_id, "development observation_id")
    for column in ("year", "alpha", "prediction", "train_rows", "target"):
        if (not is_numeric_dtype(predictions[column]) or is_bool_dtype(predictions[column])
                or not np.isfinite(predictions[column].to_numpy(dtype=float)).all()):
            raise FreezeValidationError(f"Development {column} must be finite numeric data")
    if not predictions.year.isin(range(config["development_start"],
                                      config["development_end"] + 1)).all():
        raise FreezeValidationError("Final or out-of-window predictions cannot enter the freeze")
    if set(predictions.model) != {"baseline", "text"}:
        raise FreezeValidationError("Development predictions must contain both primary models")
    if set(predictions.alpha) != set(config["ridge_alphas"]):
        raise FreezeValidationError("Development alpha grid differs from the locked protocol")
    if predictions.duplicated(["observation_id", "model", "alpha"]).any():
        raise FreezeValidationError("Duplicate development observation/model/alpha rows")
    years = pd.to_datetime(frame.acceptance_date).dt.year
    development = frame.loc[years >= config["development_start"]].set_index("observation_id")
    expected_ids = set(development.index)
    for _, group in predictions.groupby(["model", "alpha"]):
        if set(group.observation_id) != expected_ids:
            raise FreezeValidationError("Development models do not use identical complete observations")
    matched = development.loc[predictions.observation_id]
    if not np.array_equal(matched.target.to_numpy(), predictions.target.to_numpy()):
        raise FreezeValidationError("Development prediction targets differ from the frozen dataset")
    if (matched.reference_session.to_numpy() != predictions.reference_session.to_numpy()).any():
        raise FreezeValidationError("Development prediction sessions differ from the dataset")
    expected_years = pd.to_datetime(matched.acceptance_date).dt.year.to_numpy()
    if not np.array_equal(expected_years, predictions.year.to_numpy()):
        raise FreezeValidationError("Development prediction years must be acceptance years")
    for year in range(config["development_start"], config["development_end"] + 1):
        test = frame.loc[years == year]
        train = eligible_training(frame, year, str(test.reference_session.min()))
        train = train.loc[pd.to_datetime(train.acceptance_date).dt.year >= config["initial_train_start"]]
        if len(train) < 10 or not (predictions.loc[predictions.year == year, "train_rows"] == len(train)).all():
            raise FreezeValidationError("Development training counts violate mature-label chronology")
    measured = predictions.assign(squared_error=(predictions.target - predictions.prediction) ** 2)
    scores = measured.groupby(["model", "alpha"], as_index=False).squared_error.mean()
    choices = {}
    for name in ("baseline", "text"):
        row = scores.loc[scores.model == name].sort_values(["squared_error", "alpha"]).iloc[0]
        recorded = selection.get("selected", {}).get(name, {})
        if (not isinstance(recorded.get("alpha"), (float, int))
                or isinstance(recorded.get("alpha"), bool)
                or recorded["alpha"] != float(row.alpha)
                or not isinstance(recorded.get("development_mse"), (int, float))
                or not math.isclose(recorded["development_mse"], float(row.squared_error),
                                    rel_tol=1e-10, abs_tol=1e-12)):
            raise FreezeValidationError("Selected penalties/MSE do not reproduce pooled development selection")
        choices[name] = {"alpha": float(row.alpha), "development_mse": float(row.squared_error)}
    if reproduce:
        rerun, _ = development_comparison(frame, config)
        keys = ["observation_id", "model", "alpha"]
        actual = predictions.sort_values(keys).reset_index(drop=True)
        rebuilt = rerun.sort_values(keys).reset_index(drop=True)
        if not np.allclose(actual.prediction, rebuilt.prediction, rtol=1e-10, atol=1e-12):
            raise FreezeValidationError("Development predictions do not reproduce from the dataset and code")
    return {"selected": choices, "configurations": len(scores),
            "development_years": list(range(config["development_start"], config["development_end"] + 1)),
            "grid_mse": scores.rename(columns={"squared_error": "mse"}).to_dict("records"),
            "prediction_rows": len(predictions), "common_observations": len(expected_ids),
            "reproduced_from_dataset": reproduce, "tie_break": "smaller_alpha"}


def _manifest_blockers(manifest: dict, config: dict, partition: str,
                       data_kind: str, files: dict[str, dict], rows: int) -> list[str]:
    if manifest.get("protocol_sha256") != canonical_hash(config):
        raise FreezeValidationError(f"{partition} dataset manifest protocol mismatch")
    if manifest.get("partition") != partition or manifest.get("data_kind") != data_kind:
        raise FreezeValidationError(f"{partition} dataset manifest partition/data kind mismatch")
    expected_files = manifest.get("files", {})
    if not isinstance(expected_files, dict):
        raise FreezeValidationError("Dataset manifest files must be a hash mapping")
    for name, item in files.items():
        if expected_files.get(Path(item["path"]).name) != item["sha256"]:
            raise FreezeValidationError(f"Dataset manifest does not bind {name}")
    declared_rows = manifest.get("observations", manifest.get("rows"))
    if isinstance(declared_rows, dict):
        declared_rows = declared_rows.get("retained", declared_rows.get("included"))
    if declared_rows is not None and declared_rows != rows:
        raise FreezeValidationError("Dataset manifest observation count differs from its data")
    blockers = []
    if manifest.get("model_ready") is not True or manifest.get("approval_status") != "approved":
        blockers.append(f"{partition}_dataset_human_approval_pending")
    return blockers


def _validate_exclusions(path: str | Path, retained: pd.DataFrame) -> None:
    excluded = read_target_free_parquet(path)
    if "observation_id" not in excluded:
        raise FreezeValidationError("Exclusions need explicit observation identifiers")
    if not excluded.empty:
        strings(excluded.observation_id, "excluded observation_id")
        if excluded.observation_id.duplicated().any():
            raise FreezeValidationError("Exclusion identifiers must be unique")
        reason = next((name for name in ("reason", "reason_codes", "reasons") if name in excluded), None)
        if reason is None or excluded[reason].isna().any():
            raise FreezeValidationError("Every exclusion requires an explicit reason")
        if set(excluded.observation_id) & set(retained.observation_id):
            raise FreezeValidationError("Included and excluded observation identifiers overlap")


def _evidence_refs(value: Any) -> list[dict]:
    """Collect explicit path/hash pairs; free-form URLs alone are not evidence receipts."""
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            return [value]
        return [item for child in value.values() for item in _evidence_refs(child)]
    if isinstance(value, list):
        return [item for child in value for item in _evidence_refs(child)]
    return []


def _review_complete(review: dict) -> bool:
    if not isinstance(review, dict) or review.get("status") != "pass":
        return False
    if review.get("reviewer_type") != "human":
        return False
    if any(not isinstance(review.get(key), str) or not review[key].strip()
           for key in ("reviewer", "reviewed_at", "notes")):
        return False
    try:
        when = datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
    except ValueError:
        return False
    return when.tzinfo is not None and when <= datetime.now(timezone.utc)


def _audit_blockers(audit: dict, artifacts: dict, config: dict, data_kind: str) -> list[str]:
    if audit.get("protocol_sha256") != canonical_hash(config) or audit.get("data_kind") != data_kind:
        raise FreezeValidationError("Audit evidence protocol or data kind mismatch")
    bound = audit.get("bound_inputs", {})
    if not isinstance(bound, dict):
        raise FreezeValidationError("Audit bound_inputs must be a hash mapping")
    for name in ("development_dataset", "dataset_manifest", "exclusions"):
        if bound.get(name) != artifacts[name]["sha256"]:
            raise FreezeValidationError(f"Audit evidence is not hash-bound to {name}")
    checks = audit.get("checks", {})
    if not isinstance(checks, dict):
        raise FreezeValidationError("Audit checks must be a named mapping")
    blockers = []
    for name in AUDIT_CHECKS:
        review = checks.get(name, {})
        if not _review_complete(review):
            blockers.append(f"human_{name}_review_pending")
        elif not _evidence_refs(review.get("evidence", [])):
            blockers.append(f"{name}_source_evidence_missing")
    return blockers


def _secondary_blockers(spec: dict, config: dict) -> list[str]:
    if spec.get("protocol_sha256") != canonical_hash(config):
        raise FreezeValidationError("Secondary specification protocol mismatch")
    blockers = [f"secondary_{name}_missing" for name in SECONDARY_KEYS if name not in spec]
    if spec.get("status") != "frozen":
        blockers.append("secondary_specification_not_frozen")
    from .robustness import ABLATION_FEATURES
    delays = spec.get("reference_delays", {})
    if (not isinstance(delays, dict) or delays.get("primary") != config["reference_session_offset"]
            or delays.get("secondary") != [1, 5] or delays.get("penalties") != "frozen_primary"
            or delays.get("independent_labels_and_controls") is not True):
        blockers.append("secondary_reference_delays_not_fully_specified")
    ablations = spec.get("ablations", {})
    if not isinstance(ablations, dict):
        ablations = {}
    selected = ablations.get("selected_alphas", {})
    if (ablations.get("features") != ABLATION_FEATURES
            or ablations.get("alphas") != config["ridge_alphas"]
            or ablations.get("selection_metric") != config["tuning_metric"]
            or not isinstance(selected, dict) or set(selected) != set(ABLATION_FEATURES)
            or any(isinstance(value, bool) or value not in config["ridge_alphas"] for value in selected.values())
            or not _evidence_refs(ablations.get("development_selection_evidence"))):
        blockers.append("secondary_ablation_development_selection_not_frozen")
    bootstrap = spec.get("bootstrap", {})
    expected_bootstrap = {"draws": config["bootstrap_draws"], "seed": config["seed"],
                          "months": config["bootstrap_months"],
                          "sensitivity_months": config["bootstrap_sensitivity_months"]}
    if (not isinstance(bootstrap, dict)
            or any(bootstrap.get(key) != value for key, value in expected_bootstrap.items())):
        blockers.append("secondary_bootstrap_settings_differ_from_protocol")
    rank = spec.get("rank_correlation", {})
    if (not isinstance(rank, dict) or rank.get("grouping") != "reference_month"
            or rank.get("minimum_observations") != 3 or rank.get("ties") != "average"
            or rank.get("constant_groups") != "unavailable"):
        blockers.append("secondary_rank_correlation_not_fully_specified")
    paragraphs = spec.get("paragraph_analysis", {})
    if (not isinstance(paragraphs, dict) or paragraphs.get("role") != "descriptive_only"
            or paragraphs.get("predictor") is not False
            or paragraphs.get("similarity_threshold") != 0.5):
        blockers.append("secondary_paragraph_descriptive_rule_not_frozen")
    transition = spec.get("rule_transition", {})
    if not isinstance(transition, dict) or transition.get("role") != "descriptive_coverage_audit":
        blockers.append("secondary_rule_transition_decision_not_frozen")
    semantic = spec.get("semantic", {})
    if not isinstance(semantic, dict):
        raise FreezeValidationError("Semantic specification must be a JSON object")
    required = ("checkpoint", "checkpoint_sha256", "release_date", "training_cutoff",
                "fine_tuning_cutoff", "chunking", "aggregation", "development_tuning",
                "comparison", "chronology_evidence", "manual_validation")
    chronology = semantic.get("chronology_interpretation")
    if semantic.get("chronology_scope") == "retrospective_only":
        chronology = "retrospective"
        if semantic.get("checkpoint_historical_availability_claim") is not False:
            blockers.append("retrospective_semantics_must_disclaim_historical_availability")
    if semantic.get("status") != "frozen" or any(not semantic.get(key) for key in required):
        blockers.append("semantic_checkpoint_and_method_not_frozen")
    elif (not re.fullmatch(r"[0-9a-f]{64}", str(semantic["checkpoint_sha256"]))
          or chronology not in {"point_in_time", "retrospective"}
          or not _evidence_refs(semantic["chronology_evidence"])
          or not _evidence_refs(semantic["manual_validation"])):
        blockers.append("semantic_chronology_or_manual_evidence_incomplete")
    manual = semantic.get("manual_validation", {})
    if (not _review_complete(manual)
            or not isinstance(manual.get("cases"), list)
            or not all(isinstance(value, str) for value in manual["cases"])
            or set(manual["cases"]) != {"unchanged", "rewording", "new_risk"}):
        blockers.append("semantic_manual_examples_human_review_pending")
    if semantic.get("primary_model_input") is not False:
        blockers.append("semantic_must_be_separate_from_primary_features")
    if chronology == "point_in_time" and (
            semantic.get("training_data_cutoff_verified") is not True
            or semantic.get("fine_tuning_cutoff_verified") is not True):
        blockers.append("semantic_point_in_time_cutoff_evidence_not_verified")
    comparison = semantic.get("model_comparison", {})
    development_bindings = ("selection", "development_features", "development_receipt",
                            "development_predictions", "spec")
    if (not isinstance(comparison, dict)
            or isinstance(comparison.get("selected_alpha"), bool)
            or comparison.get("selected_alpha") not in config["ridge_alphas"]
            or any(not _evidence_refs(comparison.get(name)) for name in development_bindings)):
        blockers.append("semantic_development_model_selection_not_frozen")
    return blockers


def _resolve_evidence_refs(document: dict, document_path: Path) -> list[dict]:
    verified = []
    for item in _evidence_refs(document):
        path = Path(item["path"])
        if not path.is_absolute():
            path = document_path.parent / path
        record = {**item, "path": str(path.resolve())}
        verify_artifact(record, "audit/secondary evidence")
        verified.append({"path": record["path"], "sha256": record["sha256"]})
    return verified


def _inspect_prerequisites(development_dataset: str | Path,
                           development_predictions: str | Path, selection: str | Path, *,
                           manifest: str | Path, exclusions: str | Path,
                           audit_evidence: str | Path, secondary_spec: str | Path,
                           config: dict, repo_root: str | Path = ".",
                           synthetic: bool = False, reproduce: bool = True) -> tuple[dict, pd.DataFrame]:
    verify_lock(config, Path(repo_root) / "configs" / "protocol.lock.json")
    paths = {"development_dataset": development_dataset,
             "development_predictions": development_predictions, "selection": selection,
             "dataset_manifest": manifest, "exclusions": exclusions,
             "audit_evidence": audit_evidence, "secondary_spec": secondary_spec}
    artifacts = {name: artifact(path) for name, path in paths.items()}
    dataset_manifest = read_json(manifest)
    kind = SYNTHETIC if synthetic else EMPIRICAL
    if dataset_manifest.get("data_kind") != kind:
        raise FinalAccessBlocked("Synthetic and empirical data require separate explicit execution modes")
    # Check metadata before the development target vector is interpreted.
    metadata = pd.read_parquet(development_dataset, columns=FEATURE_COLUMNS)
    validate_features(metadata, config, partition="development")
    from .dataset import load_dataset
    frame, verified_manifest = load_dataset(Path(manifest).parent, config, "development",
                                            require_approved=True)
    if (verified_manifest != dataset_manifest
            or Path(development_dataset).resolve() != (Path(manifest).parent / "dataset.parquet").resolve()
            or Path(exclusions).resolve() != (Path(manifest).parent / "exclusions.parquet").resolve()):
        raise FreezeValidationError("Development paths differ from the reviewed prepared dataset bundle")
    validate_targets(frame)
    _validate_exclusions(exclusions, frame)
    prediction_years = pd.read_parquet(development_predictions, columns=["year"])
    if (not is_numeric_dtype(prediction_years.year) or is_bool_dtype(prediction_years.year)
            or not prediction_years.year.isin(range(config["development_start"],
                                                    config["development_end"] + 1)).all()):
        raise FreezeValidationError("Final or out-of-window predictions cannot enter the freeze")
    choices = _selection_check(frame, pd.read_parquet(development_predictions),
                               read_json(selection), config, reproduce=reproduce)
    blockers = _manifest_blockers(dataset_manifest, config, "development", kind,
                                  {name: artifacts[name] for name in
                                   ("development_dataset", "exclusions")}, len(frame))
    audit, secondary = read_json(audit_evidence), read_json(secondary_spec)
    blockers.extend(_audit_blockers(audit, artifacts, config, kind))
    blockers.extend(_secondary_blockers(secondary, config))
    code = code_state(repo_root)
    semantic_validation = None
    semantic_binding = secondary.get("semantic", {}).get("model_comparison", {})
    semantic_parts = ("selection", "development_features", "development_receipt", "development_predictions", "spec")
    if (isinstance(semantic_binding, dict)
            and all(_evidence_refs(semantic_binding.get(name)) for name in semantic_parts)):
        from .semantic_model import verify_development_binding
        semantic_validation = verify_development_binding(
            frame, semantic_binding, secondary_spec, config, data_kind=kind, code=code,
            dataset_sha256=artifacts["development_dataset"]["sha256"],
            manifest_sha256=artifacts["dataset_manifest"]["sha256"],
        )
    if code["dirty_source_files"]:
        blockers.append("research_source_changes_not_committed")
    if synthetic:
        blockers.append("synthetic_fixture_cannot_unlock_empirical_evaluation")
    evidence = _resolve_evidence_refs(audit, Path(audit_evidence))
    evidence += _resolve_evidence_refs(secondary, Path(secondary_spec))
    receipt = {
        "schema_version": 1, "protocol_sha256": canonical_hash(config), "data_kind": kind,
        "prerequisites_verified": not blockers, "empirical_ready": not blockers,
        "blockers": sorted(set(blockers)), "artifacts": artifacts, "evidence_files": evidence,
        "code": code, "development": choices, "development_observations": len(frame),
        "semantic_development_verification": semantic_validation,
        "preprocessing": {
            "training_only": ["tfidf_vocabulary", "idf", "imputation", "scaling", "industry_encoding"],
            "primary_text_features": FEATURE_NAMES, "controls": NUMERIC_CONTROLS + ["industry"],
            "tfidf_max_features": config["tfidf_max_features"], "tfidf_min_df": config["tfidf_min_df"],
            "tfidf_ngram_range": config["tfidf_ngram_range"],
            "tokenization": {"lowercase": True, "alphabetic_minimum_characters": 2,
                             "stop_words": None, "unit": "unigram"},
            "annual_refit": "prior_acceptance_years_and_label_end_strictly_before_first_reference_session",
            "include_prior_final_year_labels_when_mature": True,
        },
    }
    return receipt, frame


def validate_prerequisites(development_dataset: str | Path,
                           development_predictions: str | Path, selection: str | Path, **kwargs) -> dict:
    """Audit M8 prerequisites; false receipts cannot authorize empirical label staging.

    Required keyword paths are manifest, exclusions, audit_evidence and
    secondary_spec; config is the verified protocol. Missing sign-offs stay
    explicit in ``blockers`` and are never manufactured by this function.
    """
    receipt, _ = _inspect_prerequisites(development_dataset, development_predictions, selection,
                                      **kwargs)
    return receipt


def create_freeze(development_dataset: str | Path, development_predictions: str | Path,
                  selection: str | Path, *, output: str | Path, config: dict,
                  manifest: str | Path, exclusions: str | Path, audit_evidence: str | Path,
                  secondary_spec: str | Path, repo_root: str | Path = ".",
                  synthetic: bool = False, final_features: str | Path | None = None,
                  final_targets: str | Path | None = None, final_manifest: str | Path | None = None,
                  final_exclusions: str | Path | None = None) -> dict:
    """Write a new immutable freeze, including pending gates when reviews are absent.

    Final target bytes can be fingerprinted here; their Parquet values are never
    loaded. Final features and targets must be separate files. Callers can first
    use validate_prerequisites as the gate for approved holdout data staging.
    """
    out = Path(output)
    if out.exists():
        raise FreezeValidationError("Freeze output must be a new directory; existing evidence is preserved")
    receipt, development = _inspect_prerequisites(
        development_dataset, development_predictions, selection, manifest=manifest,
        exclusions=exclusions, audit_evidence=audit_evidence, secondary_spec=secondary_spec,
        config=config, repo_root=repo_root, synthetic=synthetic,
    )
    paths = {"final_features": final_features, "final_targets": final_targets,
             "final_manifest": final_manifest, "final_exclusions": final_exclusions}
    if any(path is not None for path in paths.values()) and not all(path is not None for path in paths.values()):
        raise FreezeValidationError("Bind final features, targets, manifest and exclusions together")
    final_ids = []
    if all(path is not None for path in paths.values()):
        if Path(final_features).resolve() == Path(final_targets).resolve():
            raise FreezeValidationError("Final features and targets must be physically separate files")
        features = read_target_free_parquet(final_features)
        validate_features(features, config, partition="holdout")
        if set(development.observation_id) & set(features.observation_id):
            raise FreezeValidationError("Development and final observation identifiers overlap")
        _validate_exclusions(final_exclusions, features)
        receipt["artifacts"].update({name: artifact(path) for name, path in paths.items()})
        receipt["blockers"].extend(_manifest_blockers(
            read_json(final_manifest), config, "holdout", receipt["data_kind"],
            {name: receipt["artifacts"][name] for name in
             ("final_features", "final_targets", "final_exclusions")}, len(features),
        ))
        semantic_binding = read_json(secondary_spec).get("semantic", {}).get("model_comparison", {})
        if (not isinstance(semantic_binding, dict)
                or any(not _evidence_refs(semantic_binding.get(name)) for name in
                       ("final_features", "final_receipt"))):
            receipt["blockers"].append("semantic_final_feature_artifacts_not_bound")
        final_ids = features.observation_id.tolist()
    else:
        receipt["blockers"].append("final_feature_target_manifest_bundle_not_bound")
    receipt["blockers"] = sorted(set(receipt["blockers"]))
    receipt.update({
        "created_at": datetime.now(timezone.utc).isoformat(),
        "empirical_ready": not receipt["blockers"],
        "prerequisites_verified": not receipt["blockers"],
        "engineering_ready": bool(final_ids), "final_period_opened": False,
        "final_observations": len(final_ids),
        "observation_ids_sha256": canonical_hash({"development": sorted(development.observation_id),
                                                   "final": sorted(final_ids)}),
        "interpretation": ("SYNTHETIC engineering verification only; no empirical inference or approval"
                           if synthetic else "Frozen development choices; inspect explicit access gates"),
    })
    receipt["freeze_id"] = canonical_hash(receipt)
    out.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(out / "freeze.json", receipt)
    write_json_exclusive(out / "observations.json", {
        "development": sorted(development.observation_id), "final": sorted(final_ids),
        "observation_ids_sha256": receipt["observation_ids_sha256"],
    })
    return receipt


def load_freeze(path: str | Path, config: dict, repo_root: str | Path = ".") -> dict:
    path = Path(path)
    if path.is_dir():
        path = path / "freeze.json"
    receipt = read_json(path)
    unsigned = {key: value for key, value in receipt.items() if key != "freeze_id"}
    if (receipt.get("schema_version") != 1
            or receipt.get("freeze_id") != canonical_hash(unsigned)):
        raise FreezeValidationError("Freeze fingerprint is missing or has changed")
    if receipt.get("protocol_sha256") != canonical_hash(config):
        raise FreezeValidationError("Freeze protocol hash differs from the locked protocol")
    verify_lock(config, Path(repo_root) / "configs" / "protocol.lock.json")
    verify_code(receipt.get("code", {}), repo_root)
    observations = read_json(path.parent / "observations.json")
    actual = canonical_hash({name: observations.get(name) for name in ("development", "final")})
    if actual != receipt.get("observation_ids_sha256"):
        raise FreezeValidationError("Frozen observation identity manifest has changed")
    return receipt
