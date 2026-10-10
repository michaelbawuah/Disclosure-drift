"""Synthetic/mock model checks; these tests never claim to execute MiniLM weights."""

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from disclosure_research import semantic
from disclosure_research.dataset import load_dataset
from disclosure_research.final_evaluation import run_synthetic_final_demo
from disclosure_research.freeze import (
    SYNTHETIC, FinalAccessBlocked, FreezeValidationError, artifact, file_sha256,
    write_json_exclusive,
)
from disclosure_research.protocol import load_protocol
from disclosure_research.semantic import compute_semantic_pairs
from disclosure_research.semantic_model import (
    ANALYSIS, _annual_predictions, _joined, _validate_feature_pairs, develop_semantic,
    evaluate_semantic_final, load_semantic_features,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "configs" / "semantic_retrospective.json"


class SyntheticEncoder:
    """Deterministic toy vectors, used only with explicitly synthetic inputs."""

    def __init__(self, spec, cache_dir=None):
        self.spec = spec

    def encode(self, text):
        tokens = len(text.split())
        vector = np.asarray([len(text), text.count("cybersecurity") + 1,
                             text.count("competition") + 5], dtype=float)
        vector /= np.linalg.norm(vector)
        return vector, {"chunks": math.ceil(tokens / 254), "content_tokens": tokens,
                        "document_sha256": hashlib.sha256(text.encode()).hexdigest()}


@pytest.fixture(scope="module")
def semantic_demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("retrospective-model") / "demo"
    patch = pytest.MonkeyPatch()
    patch.setattr(semantic, "PinnedSemanticEncoder", SyntheticEncoder)

    def freeze_secondary(development, output):
        output.mkdir()
        holdout, _ = load_dataset(root / "datasets" / "holdout", load_protocol(), "holdout", features_only=True)
        compute_semantic_pairs(development, SPEC, output / "development-features")
        compute_semantic_pairs(holdout, SPEC, output / "final-features")
        selection = develop_semantic(root / "datasets" / "development", output / "development-features",
                                     SPEC, output / "selection", load_protocol(), repo_root=ROOT)
        spec = json.loads((ROOT / "configs" / "secondary_analysis.json").read_text())
        spec["data_kind"] = SYNTHETIC
        spec["semantic"]["model_comparison"] = {
            "selected_alpha": selection["selected_alpha"],
            "selection": artifact(output / "selection" / "semantic_selection.json"),
            "development_predictions": artifact(output / "selection" / "semantic_development_predictions.parquet"),
            "development_features": artifact(output / "development-features" / "semantic_features.parquet"),
            "development_receipt": artifact(output / "development-features" / "semantic_receipt.json"),
            "final_features": artifact(output / "final-features" / "semantic_features.parquet"),
            "final_receipt": artifact(output / "final-features" / "semantic_receipt.json"),
            "spec": artifact(SPEC),
        }
        path = output / "secondary.json"
        write_json_exclusive(path, spec)
        return path

    try:
        summary = run_synthetic_final_demo(root, load_protocol(), repo_root=ROOT,
                                           secondary_builder=freeze_secondary)
        result = evaluate_semantic_final(root / "final", root / "freeze", root / "semantic-final",
                                         load_protocol(), repo_root=ROOT)
    finally:
        patch.undo()
    return root, summary, result


def test_separate_retrospective_grid_and_final_runner_are_reproducible(semantic_demo):
    root, primary, result = semantic_demo
    selection = json.loads((root / "secondary-development" / "selection" / "semantic_selection.json").read_text())
    assert selection["analysis"] == ANALYSIS
    assert selection["configurations"] == 4 and selection["annual_folds"] == 6
    assert selection["selected_alpha"] in load_protocol()["ridge_alphas"]
    assert selection["data_kind"] == SYNTHETIC and not selection["primary_model_input"]
    predictions = pd.read_parquet(root / "secondary-development" / "selection" / "semantic_development_predictions.parquet")
    assert set(predictions.year) == set(range(2016, 2022))
    assert predictions.groupby("alpha").size().nunique() == 1
    assert result["observations"] == 48 and result["annual_folds"] == 4
    assert result["chronology_scope"] == "retrospective_only"
    assert result["common_primary_observations"] and not result["fresh_tuning_performed"]
    assert not primary["empirical_ready"]
    frozen = json.loads((root / "freeze" / "freeze.json").read_text())
    assert frozen["semantic_development_verification"]["reproduced"]
    a = pd.read_parquet(root / "final" / "final_predictions.parquet")
    b = pd.read_parquet(root / "semantic-final" / "semantic_final_predictions.parquet")
    joined = a.merge(b, on="observation_id", suffixes=("_primary", "_semantic"))
    np.testing.assert_array_equal(joined.target_primary, joined.target_semantic)
    np.testing.assert_array_equal(joined.baseline_prediction_primary, joined.baseline_prediction_semantic)


def test_semantic_feature_receipts_bind_both_original_texts(semantic_demo):
    root, _, _ = semantic_demo
    pairs, _ = load_dataset(root / "datasets" / "development", load_protocol())
    directory = root / "secondary-development" / "development-features"
    features, receipt = load_semantic_features(pairs, directory / "semantic_features.parquet",
                                               directory / "semantic_receipt.json", SPEC, data_kind=SYNTHETIC)
    assert receipt["checkpoint_revision"] == json.loads(SPEC.read_text())["revision"]
    assert receipt["weights_sha256"] == json.loads(SPEC.read_text())["weights_sha256"]
    pairs.loc[0, "current_text"] += " Changed after feature extraction."
    with pytest.raises(FreezeValidationError, match="disclosure text"):
        _validate_feature_pairs(pairs, features)


@pytest.mark.parametrize("change", ["duplicate", "missing", "truncated", "wrong_chunks", "infinite", "outcome"])
def test_semantic_features_reject_invalid_identity_coverage_and_values(semantic_demo, change):
    root, _, _ = semantic_demo
    pairs, _ = load_dataset(root / "datasets" / "development", load_protocol())
    frame = pd.read_parquet(root / "secondary-development" / "development-features" / "semantic_features.parquet")
    if change == "duplicate":
        frame = pd.concat([frame, frame.iloc[:1]], ignore_index=True)
    elif change == "missing":
        frame = frame.iloc[1:]
    elif change == "truncated":
        frame.loc[0, "tokens_truncated"] = 1
    elif change == "wrong_chunks":
        frame.loc[0, "previous_chunks"] += 1
    elif change == "infinite":
        frame.loc[0, "semantic_distance"] = np.inf
    else:
        frame["target"] = 0
    with pytest.raises(FreezeValidationError):
        _validate_feature_pairs(pairs, frame)


def test_synthetic_feature_receipt_cannot_be_reclassified_as_empirical(semantic_demo):
    root, _, _ = semantic_demo
    pairs, _ = load_dataset(root / "datasets" / "development", load_protocol())
    directory = root / "secondary-development" / "development-features"
    with pytest.raises(FreezeValidationError, match="data kind"):
        load_semantic_features(pairs, directory / "semantic_features.parquet",
                               directory / "semantic_receipt.json", SPEC, data_kind="EMPIRICAL_RESEARCH_DATA")


def test_semantic_feature_byte_change_is_rejected(semantic_demo, tmp_path):
    root, _, _ = semantic_demo
    pairs, _ = load_dataset(root / "datasets" / "development", load_protocol())
    directory = root / "secondary-development" / "development-features"
    features = pd.read_parquet(directory / "semantic_features.parquet")
    features.loc[0, "semantic_distance"] = 0.5
    changed = tmp_path / "changed.parquet"
    features.to_parquet(changed, index=False)
    with pytest.raises(FreezeValidationError, match="feature bytes"):
        load_semantic_features(pairs, changed, directory / "semantic_receipt.json", SPEC, data_kind=SYNTHETIC)


def test_final_period_is_blocked_before_semantic_development_outcomes(tmp_path, monkeypatch):
    dataset = tmp_path / "not-development"
    dataset.mkdir()
    pd.DataFrame({"acceptance_date": ["2022-01-03"], "target": ["must not be opened"]}).to_parquet(
        dataset / "dataset.parquet", index=False,
    )
    original = pd.read_parquet

    def projected_only(path, *args, **kwargs):
        assert kwargs.get("columns") == ["acceptance_date"]
        return original(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", projected_only)
    with pytest.raises(ValueError, match="blocked"):
        develop_semantic(dataset, "never-opened", SPEC, tmp_path / "output", load_protocol(), repo_root=ROOT)


def test_future_semantic_values_and_targets_cannot_change_an_earlier_fit(semantic_demo):
    root, _, _ = semantic_demo
    development, _ = load_dataset(root / "datasets" / "development", load_protocol())
    final, _ = load_dataset(root / "datasets" / "holdout", load_protocol(), "holdout")
    semantic_development = pd.read_parquet(root / "secondary-development" / "development-features" / "semantic_features.parquet")
    semantic_final = pd.read_parquet(root / "secondary-development" / "final-features" / "semantic_features.parquet")
    data = pd.concat([_joined(development, semantic_development), _joined(final, semantic_final)], ignore_index=True)
    config = load_protocol()
    before, folds_before = _annual_predictions(data, range(2022, 2024), [1.0], config)
    later = pd.to_datetime(data.acceptance_date).dt.year >= 2023
    data.loc[later, "semantic_distance"] = 2
    data.loc[later, "momentum_20"] += 100
    data.loc[later, "target"] += 100
    after, folds_after = _annual_predictions(data, range(2022, 2024), [1.0], config)
    pd.testing.assert_frame_equal(before.loc[before.year == 2022], after.loc[after.year == 2022])
    assert folds_before[0] == folds_after[0]
    assert folds_before[1]["train_rows"] > folds_before[0]["train_rows"]


def test_missing_prebound_semantic_comparison_stays_blocked(tmp_path, monkeypatch):
    from disclosure_research import robustness_run

    spec = tmp_path / "secondary.json"
    write_json_exclusive(spec, {"semantic": {"status": "pending"}})
    receipt = {"artifacts": {"secondary_spec": artifact(spec)}}
    monkeypatch.setattr(robustness_run, "load_authorized_final", lambda *args, **kwargs: (pd.DataFrame(), receipt, {}))
    with pytest.raises(FinalAccessBlocked, match="not bound before"):
        evaluate_semantic_final("final", "freeze", tmp_path / "result", load_protocol())
    assert not (tmp_path / "result").exists()


def test_semantic_development_output_is_immutable(semantic_demo):
    root, _, _ = semantic_demo
    output = root / "secondary-development" / "selection"
    before = file_sha256(output / "semantic_selection.json")
    with pytest.raises(FreezeValidationError, match="output exists"):
        develop_semantic("never-read", "never-read", SPEC, output, load_protocol())
    assert before == file_sha256(output / "semantic_selection.json")
