"""Separate, explicitly retrospective controls-plus-semantic ridge comparison.

The encoder is pinned and never fitted to outcomes. Imputation, scaling and
industry encoding are fitted to each eligible training fold. Final execution
requires a previously completed primary run and pre-access artifact bindings;
there is no final-period model-selection path.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .dataset import load_dataset
from .final_evaluation import _frozen_interval
from .freeze import (
    EMPIRICAL, SYNTHETIC, FinalAccessBlocked, FreezeValidationError,
    artifact, code_state, file_sha256, read_json, validate_features, validate_targets,
    verify_artifact, write_json_exclusive,
)
from .market_data import strings
from .modeling import NUMERIC_CONTROLS
from .protocol import canonical_hash, eligible_training, guard_development, verify_lock
from .semantic import validate_spec

SEMANTIC_FEATURE = "semantic_distance"
ANALYSIS = "RETROSPECTIVE_SEMANTIC_SECONDARY"
SEMANTIC_COLUMNS = {
    "observation_id", "semantic_distance", "previous_text_sha256", "current_text_sha256",
    "previous_chunks", "current_chunks", "previous_tokens", "current_tokens", "tokens_truncated",
}


def _pipeline(alpha: float) -> Pipeline:
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scale", StandardScaler()),
    ])
    transform = ColumnTransformer([
        ("numeric", numeric, NUMERIC_CONTROLS + [SEMANTIC_FEATURE]),
        ("industry", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["industry"]),
    ])
    return Pipeline([("preprocess", transform), ("ridge", Ridge(alpha=alpha))])


def _validate_feature_pairs(pairs: pd.DataFrame, features: pd.DataFrame) -> None:
    if set(features.columns) != SEMANTIC_COLUMNS or features.empty:
        raise FreezeValidationError("Semantic feature schema is incomplete or includes undeclared columns")
    strings(features.observation_id, "semantic observation_id")
    if (features.observation_id.duplicated().any()
            or set(features.observation_id) != set(pairs.observation_id)):
        raise FreezeValidationError("Semantic features require the exact same unique observations")
    for name in ("semantic_distance", "previous_chunks", "current_chunks", "previous_tokens",
                 "current_tokens", "tokens_truncated"):
        values = features[name]
        if (not is_numeric_dtype(values) or is_bool_dtype(values)
                or not np.isfinite(values.to_numpy(dtype=float)).all()):
            raise FreezeValidationError(f"Semantic {name} must be finite numeric data")
    if not features.semantic_distance.between(0, 2).all():
        raise FreezeValidationError("Semantic cosine distances must lie between zero and two")
    if not (features.tokens_truncated == 0).all():
        raise FreezeValidationError("Truncated semantic sections are not eligible")
    for side in ("previous", "current"):
        tokens, chunks = features[f"{side}_tokens"], features[f"{side}_chunks"]
        if ((tokens < 1).any() or (tokens != np.floor(tokens)).any()
                or not np.array_equal(chunks.to_numpy(), np.ceil(tokens / 254).to_numpy())):
            raise FreezeValidationError("Semantic token/chunk coverage differs from the frozen encoder")
        strings(features[f"{side}_text_sha256"], f"{side}_text_sha256")
        expected = pairs.set_index("observation_id")[f"{side}_text"].map(
            lambda text: hashlib.sha256(text.encode()).hexdigest(),
        )
        actual = features.set_index("observation_id")[f"{side}_text_sha256"]
        if not np.array_equal(expected.loc[actual.index].to_numpy(), actual.to_numpy()):
            raise FreezeValidationError("Semantic feature receipt does not match the disclosure text")


def load_semantic_features(pairs: pd.DataFrame, feature_path: str | Path,
                           receipt_path: str | Path, spec_path: str | Path, *,
                           data_kind: str) -> tuple[pd.DataFrame, dict]:
    """Read one verified feature snapshot and bind each pair's original text hashes."""
    if data_kind not in {SYNTHETIC, EMPIRICAL}:
        raise FreezeValidationError("Semantic modeling requires a classified, reviewed dataset")
    spec_bytes = Path(spec_path).read_bytes()
    spec = read_json(spec_path)
    validate_spec(spec)
    receipt = read_json(receipt_path)
    if (receipt.get("schema_version") != 1 or receipt.get("analysis") != ANALYSIS
            or receipt.get("primary_model_input") is not False
            or receipt.get("chronology_scope") != "retrospective_only"
            or receipt.get("data_kind") != data_kind):
        raise FreezeValidationError("Semantic receipt must match the retrospective data kind and scope")
    if (receipt.get("spec_sha256") != hashlib.sha256(spec_bytes).hexdigest()
            or receipt.get("checkpoint_revision") != spec["revision"]
            or receipt.get("weights_sha256") != spec["weights_sha256"]):
        raise FreezeValidationError("Semantic model, tokenizer specification or checkpoint differs")
    raw = Path(feature_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != receipt.get("features_sha256"):
        raise FreezeValidationError("Semantic feature bytes differ from their receipt")
    features = pd.read_parquet(io.BytesIO(raw))
    _validate_feature_pairs(pairs, features)
    if receipt.get("rows") != len(features) or receipt.get("tokens_truncated") != 0:
        raise FreezeValidationError("Semantic receipt row count or full-token coverage differs")
    return features, receipt


def _joined(frame: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    _validate_feature_pairs(frame, features)
    if SEMANTIC_FEATURE in frame.columns:
        raise FreezeValidationError("Do not smuggle an unverified semantic feature into the model table")
    return frame.merge(features[["observation_id", SEMANTIC_FEATURE]], on="observation_id",
                       validate="one_to_one")


def _annual_predictions(frame: pd.DataFrame, years: range, alphas: list[float],
                         config: dict) -> tuple[pd.DataFrame, list[dict]]:
    acceptance_years = pd.to_datetime(frame.acceptance_date).dt.year
    outputs, folds = [], []
    if (not alphas or any(isinstance(alpha, bool) or alpha not in config["ridge_alphas"]
                         for alpha in alphas) or len(set(alphas)) != len(alphas)):
        raise FreezeValidationError("Semantic ridge penalties must use the declared grid")
    for year in years:
        test = frame.loc[acceptance_years == year].sort_values(["reference_session", "observation_id"])
        if test.empty:
            raise FreezeValidationError(f"Missing semantic evaluation year {year}")
        cutoff = str(test.reference_session.min())
        train = eligible_training(frame, year, cutoff)
        train = train.loc[pd.to_datetime(train.acceptance_date).dt.year >= config["initial_train_start"]]
        train = train.sort_values(["reference_session", "observation_id"])
        if len(train) < 10 or not (pd.to_datetime(train.label_end) < pd.Timestamp(cutoff)).all():
            raise FreezeValidationError("Semantic training labels are immature or too few")
        if (pd.to_datetime(train.acceptance_date).dt.year >= year).any():
            raise FreezeValidationError("Future acceptance years entered semantic training")
        for alpha in alphas:
            model = _pipeline(alpha)
            model.fit(train[NUMERIC_CONTROLS + ["industry", SEMANTIC_FEATURE]], train.target)
            prediction = model.predict(test[NUMERIC_CONTROLS + ["industry", SEMANTIC_FEATURE]])
            if not np.isfinite(prediction).all():
                raise FreezeValidationError("Nonfinite semantic predictions")
            result = test[["observation_id", "reference_session", "target"]].copy()
            result["year"], result["alpha"], result["prediction"] = year, alpha, prediction
            result["train_rows"] = len(train)
            outputs.append(result)
            scaler = model.named_steps["preprocess"].named_transformers_["numeric"].named_steps["scale"]
            folds.append({"year": year, "alpha": alpha, "first_reference_session": cutoff,
                          "train_rows": len(train), "prediction_rows": len(test),
                          "max_training_label_end": str(train.label_end.max()),
                          "training_observation_ids": train.observation_id.tolist(),
                          "training_scaler_mean": scaler.mean_.tolist(),
                          "numeric_features": NUMERIC_CONTROLS + [SEMANTIC_FEATURE],
                          "chronology_scope": "retrospective_only"})
    return pd.concat(outputs, ignore_index=True), folds


def _verify_development_selection(frame: pd.DataFrame, predictions: pd.DataFrame,
                                   selection: dict, config: dict) -> None:
    guard_development(frame, config)
    required = {"observation_id", "year", "reference_session", "target", "prediction", "alpha", "train_rows"}
    if required - set(predictions.columns):
        raise FreezeValidationError("Semantic development prediction evidence is incomplete")
    for name in ("year", "target", "prediction", "alpha", "train_rows"):
        if (not is_numeric_dtype(predictions[name]) or is_bool_dtype(predictions[name])
                or not np.isfinite(predictions[name].to_numpy(dtype=float)).all()):
            raise FreezeValidationError("Semantic development prediction values must be finite numeric data")
    years = range(config["development_start"], config["development_end"] + 1)
    if not predictions.year.isin(years).all() or set(predictions.alpha) != set(config["ridge_alphas"]):
        raise FreezeValidationError("Semantic development predictions violate the frozen years/grid")
    if predictions.duplicated(["observation_id", "alpha"]).any():
        raise FreezeValidationError("Duplicate semantic development predictions")
    expected = frame.loc[pd.to_datetime(frame.acceptance_date).dt.year.isin(years)].set_index("observation_id")
    for _, rows in predictions.groupby("alpha"):
        if set(rows.observation_id) != set(expected.index):
            raise FreezeValidationError("Semantic development alpha grid must share complete observations")
        matched = expected.loc[rows.observation_id]
        if (not np.array_equal(rows.target.to_numpy(), matched.target.to_numpy())
                or not np.array_equal(rows.reference_session.to_numpy(), matched.reference_session.to_numpy())
                or not np.array_equal(rows.year.to_numpy(), pd.to_datetime(matched.acceptance_date).dt.year.to_numpy())):
            raise FreezeValidationError("Semantic development prediction targets/clocks differ from source data")
    scores = predictions.assign(error=(predictions.target - predictions.prediction) ** 2).groupby(
        "alpha", as_index=False,
    ).error.mean().sort_values(["error", "alpha"])
    winner = scores.iloc[0]
    if (selection.get("selected_alpha") != float(winner.alpha)
            or not np.isclose(selection.get("development_mse", np.nan), float(winner.error), rtol=1e-10, atol=1e-12)):
        raise FreezeValidationError("Semantic selected alpha does not reproduce pooled development MSE")
    # Verification reruns the already-fixed development procedure and cannot
    # replace its choice after access. No final-period target enters this replay.
    rebuilt, _ = _annual_predictions(frame, years, config["ridge_alphas"], config)
    keys = ["observation_id", "alpha"]
    stored = predictions.sort_values(keys).reset_index(drop=True)
    rebuilt = rebuilt.sort_values(keys).reset_index(drop=True)
    if (not np.allclose(stored.prediction, rebuilt.prediction, rtol=1e-10, atol=1e-12)
            or not np.array_equal(stored.train_rows, rebuilt.train_rows)):
        raise FreezeValidationError("Semantic development predictions do not reproduce from frozen inputs")


def develop_semantic(dataset_bundle: str | Path, semantic_bundle: str | Path,
                      spec_path: str | Path, output: str | Path, config: dict, *,
                      repo_root: str | Path = ".") -> dict:
    """Tune exactly four semantic ridge penalties on the six development folds."""
    out = Path(output)
    if out.exists():
        raise FreezeValidationError("Semantic development output exists; choose a new directory")
    verify_lock(config, Path(repo_root) / "configs" / "protocol.lock.json")
    dataset_dir, semantic_dir = Path(dataset_bundle), Path(semantic_bundle)
    metadata = pd.read_parquet(dataset_dir / "dataset.parquet", columns=["acceptance_date"])
    guard_development(metadata, config)
    frame, manifest = load_dataset(dataset_dir, config, "development")
    validate_features(frame, config, partition="development")
    validate_targets(frame)
    features, semantic_receipt = load_semantic_features(
        frame, semantic_dir / "semantic_features.parquet", semantic_dir / "semantic_receipt.json",
        spec_path, data_kind=manifest["data_kind"],
    )
    predictions, folds = _annual_predictions(
        _joined(frame, features), range(config["development_start"], config["development_end"] + 1),
        config["ridge_alphas"], config,
    )
    scores = predictions.assign(error=(predictions.target - predictions.prediction) ** 2).groupby(
        "alpha", as_index=False,
    ).error.mean().sort_values(["error", "alpha"])
    selected = scores.iloc[0]
    out.mkdir(parents=True, exist_ok=False)
    predictions.to_parquet(out / "semantic_development_predictions.parquet", index=False)
    write_json_exclusive(out / "semantic_development_folds.json", folds)
    selection = {
        "schema_version": 1, "analysis": ANALYSIS, "chronology_scope": "retrospective_only",
        "data_kind": manifest["data_kind"], "primary_model_input": False,
        "protocol_sha256": canonical_hash(config), "selected_alpha": float(selected.alpha),
        "development_mse": float(selected.error), "tuning_metric": config["tuning_metric"],
        "alphas": config["ridge_alphas"], "configurations": 4, "annual_folds": 6,
        "selection_years": list(range(config["development_start"], config["development_end"] + 1)),
        "grid_mse": scores.rename(columns={"error": "mse"}).to_dict("records"),
        "development_dataset_sha256": file_sha256(dataset_dir / "dataset.parquet"),
        "development_manifest_sha256": file_sha256(dataset_dir / "dataset_manifest.json"),
        "semantic_features_sha256": semantic_receipt["features_sha256"],
        "semantic_spec_sha256": semantic_receipt["spec_sha256"],
        "predictions_sha256": file_sha256(out / "semantic_development_predictions.parquet"),
        "code": code_state(repo_root),
        "interpretation": "Development selection for a retrospective secondary; no historical point-in-time claim",
    }
    write_json_exclusive(out / "semantic_selection.json", selection)
    return selection


def verify_development_binding(frame: pd.DataFrame, binding: dict, document_path: str | Path,
                                config: dict, *, data_kind: str, code: dict,
                                dataset_sha256: str, manifest_sha256: str) -> dict:
    """Reproduce a semantic development choice before the primary access gate."""
    paths = {}
    for name in ("selection", "development_features", "development_receipt", "development_predictions", "spec"):
        item = binding.get(name)
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise FreezeValidationError("Semantic development binding is incomplete")
        item = dict(item)
        if not Path(item["path"]).is_absolute():
            item["path"] = str(Path(document_path).parent / item["path"])
        paths[name] = verify_artifact(item, f"semantic development {name}")
    selection = read_json(paths["selection"])
    if (selection.get("analysis") != ANALYSIS or selection.get("data_kind") != data_kind
            or selection.get("chronology_scope") != "retrospective_only"
            or selection.get("primary_model_input") is not False
            or selection.get("protocol_sha256") != canonical_hash(config)
            or selection.get("selected_alpha") != binding.get("selected_alpha")
            or selection.get("development_dataset_sha256") != dataset_sha256
            or selection.get("development_manifest_sha256") != manifest_sha256
            or selection.get("semantic_spec_sha256") != binding["spec"].get("sha256")
            or selection.get("semantic_features_sha256") != binding["development_features"].get("sha256")
            or selection.get("predictions_sha256") != binding["development_predictions"].get("sha256")
            or selection.get("code") != code):
        raise FreezeValidationError("Semantic development selection is bound to different code/data/specification")
    features, _ = load_semantic_features(frame, paths["development_features"], paths["development_receipt"],
                                         paths["spec"], data_kind=data_kind)
    metadata = pd.read_parquet(paths["development_predictions"], columns=["year"])
    if not metadata.year.isin(range(config["development_start"], config["development_end"] + 1)).all():
        raise FreezeValidationError("Semantic development evidence contains final-period predictions")
    _verify_development_selection(_joined(frame, features), pd.read_parquet(paths["development_predictions"]),
                                  selection, config)
    return {"selected_alpha": selection["selected_alpha"], "development_mse": selection["development_mse"],
            "reproduced": True, "chronology_scope": "retrospective_only"}


def evaluate_semantic_final(final_run: str | Path, freeze: str | Path, output: str | Path,
                            config: dict, *, repo_root: str | Path = ".") -> dict:
    """Use only semantic artifacts and alpha already bound by the original freeze."""
    from .robustness_run import load_authorized_final

    out = Path(output)
    if out.exists():
        raise FreezeValidationError("Semantic final output exists; choose a new directory")
    primary, frozen, final_summary = load_authorized_final(final_run, freeze, config, repo_root=repo_root)
    secondary_path = verify_artifact(frozen["artifacts"]["secondary_spec"], "secondary specification")
    secondary = read_json(secondary_path)
    binding = secondary.get("semantic", {}).get("model_comparison", {})
    required = {"selection", "development_features", "development_receipt", "development_predictions", "final_features",
                "final_receipt", "spec", "selected_alpha"}
    if not isinstance(binding, dict) or not required.issubset(binding):
        raise FinalAccessBlocked("Semantic final comparison was not bound before primary target access")
    bound_paths = {}
    for name in required - {"selected_alpha"}:
        item = dict(binding[name])
        path = Path(item["path"])
        if not path.is_absolute():
            item["path"] = str(secondary_path.parent / path)
        bound_paths[name] = verify_artifact(item, f"frozen semantic {name}")
    selection = read_json(bound_paths["selection"])
    if (selection.get("analysis") != ANALYSIS or selection.get("chronology_scope") != "retrospective_only"
            or selection.get("primary_model_input") is not False
            or selection.get("protocol_sha256") != canonical_hash(config)
            or selection.get("data_kind") != frozen["data_kind"]
            or selection.get("selected_alpha") != binding["selected_alpha"]
            or selection.get("selected_alpha") not in config["ridge_alphas"]
            or isinstance(selection.get("selected_alpha"), bool)
            or selection.get("code") != frozen["code"]):
        raise FreezeValidationError("Frozen semantic selection differs from the approved study code/specification")
    inputs = frozen["artifacts"]
    if (selection.get("development_dataset_sha256") != inputs["development_dataset"]["sha256"]
            or selection.get("development_manifest_sha256") != inputs["dataset_manifest"]["sha256"]
            or selection.get("semantic_spec_sha256") != binding["spec"]["sha256"]
            or selection.get("semantic_features_sha256") != binding["development_features"]["sha256"]
            or selection.get("predictions_sha256") != binding["development_predictions"]["sha256"]):
        raise FreezeValidationError("Semantic development selection is bound to different data")
    development, _ = load_dataset(Path(inputs["dataset_manifest"]["path"]).parent, config, "development")
    holdout, _ = load_dataset(Path(inputs["final_manifest"]["path"]).parent, config, "holdout",
                              features_only=True)
    if set(primary.observation_id) != set(holdout.observation_id):
        raise FreezeValidationError("Semantic final comparison must retain the exact primary observations")
    # Reuse the already authorized, saved final outcomes; never open another target file.
    holdout = holdout.merge(primary[["observation_id", "target"]], on="observation_id", validate="one_to_one")
    semantic_development, _ = load_semantic_features(
        development, bound_paths["development_features"], bound_paths["development_receipt"],
        bound_paths["spec"], data_kind=frozen["data_kind"],
    )
    semantic_final, _ = load_semantic_features(
        holdout, bound_paths["final_features"], bound_paths["final_receipt"], bound_paths["spec"],
        data_kind=frozen["data_kind"],
    )
    prediction_years = pd.read_parquet(bound_paths["development_predictions"], columns=["year"])
    if not prediction_years.year.isin(range(config["development_start"], config["development_end"] + 1)).all():
        raise FreezeValidationError("Final-period predictions cannot masquerade as semantic development evidence")
    _verify_development_selection(
        _joined(development, semantic_development), pd.read_parquet(bound_paths["development_predictions"]),
        selection, config,
    )
    frame = pd.concat([_joined(development, semantic_development), _joined(holdout, semantic_final)],
                       ignore_index=True)
    predictions, folds = _annual_predictions(
        frame, range(config["holdout_start"], config["holdout_end"] + 1),
        [selection["selected_alpha"]], config,
    )
    compare = primary[["observation_id", "year", "reference_session", "target", "baseline_prediction"]].merge(
        predictions[["observation_id", "year", "reference_session", "target", "prediction"]],
        on=["observation_id", "year", "reference_session", "target"], validate="one_to_one", how="inner",
    )
    if len(compare) != len(primary):
        raise FreezeValidationError("Semantic predictions differ from primary observation clocks or targets")
    compare = compare.rename(columns={"prediction": "semantic_prediction"})
    metrics_input = compare.rename(columns={"semantic_prediction": "text_prediction"})
    summary = {
        "schema_version": 1, "analysis": ANALYSIS, "data_kind": frozen["data_kind"],
        "chronology_scope": "retrospective_only", "primary_model_input": False,
        "freeze_id": frozen["freeze_id"], "protocol_sha256": canonical_hash(config),
        "primary_access_run_id": final_summary["access_run_id"], "observations": len(compare),
        "selected_alpha": selection["selected_alpha"], "annual_folds": len(folds),
        "common_primary_observations": True, "fresh_tuning_performed": False,
        "metrics": {"three_month": _frozen_interval(metrics_input, config["bootstrap_months"], config),
                    "six_month": _frozen_interval(metrics_input, config["bootstrap_sensitivity_months"], config)},
        "interpretation": "Retrospective semantic secondary only; checkpoint chronology cannot support historical deployment claims",
    }
    out.mkdir(parents=True, exist_ok=False)
    compare.to_parquet(out / "semantic_final_predictions.parquet", index=False)
    write_json_exclusive(out / "semantic_final_folds.json", folds)
    summary["files"] = {name: artifact(out / name) for name in
                        ("semantic_final_predictions.parquet", "semantic_final_folds.json")}
    write_json_exclusive(out / "semantic_final_summary.json", summary)
    return summary
