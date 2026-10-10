import json
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from disclosure_research import final_evaluation as final_module
from disclosure_research.features import FEATURE_NAMES
from disclosure_research.final_evaluation import (
    _fit_frozen_annual, _frozen_interval, evaluate_final, run_synthetic_final_demo,
)
from disclosure_research.freeze import (
    SYNTHETIC, FinalAccessBlocked, FreezeValidationError, _inspect_prerequisites,
    _review_complete, _selection_check, code_state, create_freeze,
    read_target_free_parquet, validate_features, validate_targets,
)
from disclosure_research.modeling import NUMERIC_CONTROLS
from disclosure_research.protocol import canonical_hash, load_protocol
from disclosure_research.timing import NY, event_window

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("frozen-final") / "demo"
    summary = run_synthetic_final_demo(root, load_protocol(), repo_root=ROOT)
    return root, summary


@pytest.fixture
def copied_demo(demo, tmp_path):
    original, _ = demo
    clone = tmp_path / "demo"
    shutil.copytree(original, clone)
    receipt_path = clone / "freeze" / "freeze.json"
    receipt = json.loads(receipt_path.read_text())
    for item in receipt["artifacts"].values():
        item["path"] = item["path"].replace(str(original), str(clone), 1)
    for item in receipt["evidence_files"]:
        item["path"] = item["path"].replace(str(original), str(clone), 1)
    # Each test binds the currently checked-out sources; paths are cloned so
    # destructive mutations cannot change the session's verified fixture.
    receipt["code"] = code_state(ROOT)
    rewrite_freeze(receipt_path, receipt)
    return clone, receipt


def rewrite_freeze(path, receipt):
    unsigned = {key: value for key, value in receipt.items() if key != "freeze_id"}
    receipt["freeze_id"] = canonical_hash(unsigned)
    path.write_text(json.dumps(receipt, indent=2) + "\n")


def frame_inputs(root):
    development = pd.read_parquet(root / "datasets" / "development" / "dataset.parquet")
    final = pd.read_parquet(root / "datasets" / "holdout" / "features.parquet").merge(
        pd.read_parquet(root / "datasets" / "holdout" / "targets.parquet"), on="observation_id",
        validate="one_to_one",
    )
    receipt = json.loads((root / "freeze" / "freeze.json").read_text())
    return development, final, receipt


def fail_if_targets_loaded(_):
    pytest.fail("A blocked evaluation opened final targets")


def evaluate_clone(root, tmp_path, **kwargs):
    return evaluate_final(root / "freeze", output=tmp_path / "new-final", config=load_protocol(),
                          repo_root=ROOT, ledger=tmp_path / "isolated-ledger", synthetic=True, **kwargs)


def test_complete_synthetic_reproduction_keeps_empirical_gates_closed(demo):
    root, summary = demo
    assert summary["data_kind"] == SYNTHETIC
    assert summary["universe_memberships"] == 192
    assert (summary["development_rows"], summary["final_rows"]) == (144, 48)
    assert (summary["development_configurations"], summary["development_annual_folds"],
            summary["final_annual_folds"]) == (8, 6, 4)
    assert not summary["empirical_ready"] and not summary["final_period_opened"]
    assert "synthetic_fixture_cannot_unlock_empirical_evaluation" in summary["empirical_blockers"]
    result = json.loads((root / "final" / "final_summary.json").read_text())
    assert result["metrics"]["primary"]["draws"] == 2000
    assert result["metrics"]["primary"]["block_months"] == 3
    assert result["metrics"]["six_month_sensitivity"]["block_months"] == 6
    assert result["common_observations"]
    predictions = pd.read_parquet(root / "final" / "final_predictions.parquet")
    assert set(predictions.year) == {2022, 2023, 2024, 2025}
    assert not predictions.observation_id.duplicated().any()


def test_synthetic_receipt_cannot_unlock_empirical_mode(copied_demo, tmp_path):
    root, _ = copied_demo
    with pytest.raises(FinalAccessBlocked, match="Synthetic"):
        evaluate_final(root / "freeze", output=tmp_path / "empirical", config=load_protocol(),
                       repo_root=ROOT, target_loader=fail_if_targets_loaded)


def test_incomplete_freeze_blocks_before_target_bytes(copied_demo, tmp_path, monkeypatch):
    root, receipt = copied_demo
    receipt["engineering_ready"] = False
    rewrite_freeze(root / "freeze" / "freeze.json", receipt)
    original = Path.read_bytes
    target = root / "datasets" / "holdout" / "targets.parquet"

    def no_target_bytes(path):
        assert path.resolve() != target.resolve(), "Blocked call read target bytes"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", no_target_bytes)
    with pytest.raises(FinalAccessBlocked, match="complete split"):
        evaluate_clone(root, tmp_path, target_loader=fail_if_targets_loaded)


def test_fingerprint_tampering_is_rejected_before_targets(copied_demo, tmp_path):
    root, receipt = copied_demo
    receipt["development"]["selected"]["baseline"]["alpha"] = 999.0
    (root / "freeze" / "freeze.json").write_text(json.dumps(receipt))
    with pytest.raises(FreezeValidationError, match="fingerprint"):
        evaluate_clone(root, tmp_path, target_loader=fail_if_targets_loaded)


def test_code_hash_mismatch_is_rejected_before_targets(copied_demo, tmp_path):
    root, receipt = copied_demo
    receipt["code"]["source_sha256"]["src/disclosure_research/modeling.py"] = "0" * 64
    rewrite_freeze(root / "freeze" / "freeze.json", receipt)
    with pytest.raises(FreezeValidationError, match="Code commit or source hashes"):
        evaluate_clone(root, tmp_path, target_loader=fail_if_targets_loaded)


def test_protocol_mismatch_is_rejected_before_targets(copied_demo, tmp_path):
    root, _ = copied_demo
    config = load_protocol()
    config["ridge_alphas"] = [999]
    with pytest.raises(FreezeValidationError, match="protocol hash"):
        evaluate_final(root / "freeze", output=tmp_path / "invalid-protocol", config=config,
                       repo_root=ROOT, synthetic=True, target_loader=fail_if_targets_loaded)


def test_mutated_feature_bytes_are_rejected_before_targets(copied_demo, tmp_path):
    root, _ = copied_demo
    feature_path = root / "datasets" / "holdout" / "features.parquet"
    frame = pd.read_parquet(feature_path)
    frame.loc[0, "momentum_20"] += 0.1
    frame.to_parquet(feature_path, index=False)
    with pytest.raises(FreezeValidationError, match="final_features"):
        evaluate_clone(root, tmp_path, target_loader=fail_if_targets_loaded)


@pytest.mark.parametrize("outcome", ["target", "stock_return", "market_return", "prediction"])
def test_target_free_schema_is_checked_before_deserialization(tmp_path, monkeypatch, outcome):
    path = tmp_path / "features.parquet"
    pd.DataFrame({"observation_id": ["one"], outcome: [999.0]}).to_parquet(path, index=False)
    monkeypatch.setattr(pd, "read_parquet", lambda *args, **kwargs: pytest.fail("Payload was read"))
    with pytest.raises(FreezeValidationError, match="outcome"):
        read_target_free_parquet(path)


def test_changed_target_hash_does_not_invoke_loader_and_keeps_access_record(copied_demo, tmp_path):
    root, _ = copied_demo
    target = root / "datasets" / "holdout" / "targets.parquet"
    frame = pd.read_parquet(target)
    frame.loc[0, "target"] += 0.01
    frame.to_parquet(target, index=False)
    with pytest.raises(FreezeValidationError, match="final_targets"):
        evaluate_clone(root, tmp_path, target_loader=fail_if_targets_loaded)
    assert len(list((tmp_path / "isolated-ledger").glob("*.access.json"))) == 1
    assert len(list((tmp_path / "isolated-ledger").glob("*.failed.json"))) == 1
    assert not (tmp_path / "new-final" / "final_summary.json").exists()


def test_loader_cannot_replace_frozen_target_values(copied_demo, tmp_path):
    root, _ = copied_demo

    def substitute(path):
        frame = pd.read_parquet(path)
        frame.loc[0, "target"] += 1
        return frame

    with pytest.raises(FreezeValidationError, match="different from the frozen file"):
        evaluate_clone(root, tmp_path, target_loader=substitute)


def test_target_join_requires_exact_common_observations(copied_demo, tmp_path):
    root, _ = copied_demo

    def omit_one(path):
        return pd.read_parquet(path).iloc[1:]

    with pytest.raises(FreezeValidationError, match="one-to-one"):
        evaluate_clone(root, tmp_path, target_loader=omit_one)


def test_persistent_ledger_refuses_changed_freeze_even_after_failed_run(copied_demo, tmp_path):
    root, receipt = copied_demo
    with pytest.raises(RuntimeError, match="adapter failed"):
        evaluate_clone(root, tmp_path, target_loader=lambda _: (_ for _ in ()).throw(RuntimeError("adapter failed")))
    receipt["created_at"] = "2026-10-10T00:00:00+00:00"
    rewrite_freeze(root / "freeze" / "freeze.json", receipt)
    with pytest.raises(FinalAccessBlocked, match="different freeze"):
        evaluate_final(root / "freeze", output=tmp_path / "changed-final", config=load_protocol(),
                       repo_root=ROOT, ledger=tmp_path / "isolated-ledger", synthetic=True,
                       target_loader=fail_if_targets_loaded)
    assert not (tmp_path / "changed-final").exists()


def test_same_freeze_can_be_reproduced_without_overwriting(copied_demo, tmp_path):
    root, _ = copied_demo
    first = evaluate_clone(root, tmp_path)
    second = evaluate_final(root / "freeze", output=tmp_path / "reproduction", config=load_protocol(),
                            repo_root=ROOT, ledger=tmp_path / "isolated-ledger", synthetic=True)
    assert not first["reproduction"] and second["reproduction"]
    a = pd.read_parquet(tmp_path / "new-final" / "final_predictions.parquet")
    b = pd.read_parquet(tmp_path / "reproduction" / "final_predictions.parquet")
    pd.testing.assert_frame_equal(a, b)
    assert first["metrics"] == second["metrics"]
    with pytest.raises(FreezeValidationError, match="new directory"):
        evaluate_clone(root, tmp_path, target_loader=fail_if_targets_loaded)


def test_existing_freeze_is_not_overwritten(copied_demo):
    root, _ = copied_demo
    before = (root / "freeze" / "freeze.json").read_bytes()
    with pytest.raises(FreezeValidationError, match="new directory"):
        create_freeze("not-opened", "not-opened", "not-opened", output=root / "freeze",
                      config=load_protocol(), manifest="not-opened", exclusions="not-opened",
                      audit_evidence="not-opened", secondary_spec="not-opened")
    assert before == (root / "freeze" / "freeze.json").read_bytes()


def test_final_prediction_rows_are_rejected_before_their_payload(copied_demo, monkeypatch):
    root, receipt = copied_demo
    artifacts = receipt["artifacts"]
    path = Path(artifacts["development_predictions"]["path"])
    predictions = pd.read_parquet(path)
    predictions.loc[0, "year"] = 2022
    predictions.to_parquet(path, index=False)
    original = pd.read_parquet

    def guard(source, *args, **kwargs):
        if isinstance(source, (str, Path)) and Path(source) == path:
            assert kwargs.get("columns") == ["year"], "Final prediction payload was read"
        return original(source, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", guard)
    with pytest.raises(FreezeValidationError, match="Final or out-of-window"):
        _inspect_prerequisites(
            artifacts["development_dataset"]["path"], path, artifacts["selection"]["path"],
            manifest=artifacts["dataset_manifest"]["path"], exclusions=artifacts["exclusions"]["path"],
            audit_evidence=artifacts["audit_evidence"]["path"], secondary_spec=artifacts["secondary_spec"]["path"],
            config=load_protocol(), repo_root=ROOT, synthetic=True, reproduce=False,
        )


def test_development_predictions_are_recomputed_not_merely_believed(demo):
    root, _ = demo
    frame, _, receipt = frame_inputs(root)
    predictions = pd.read_parquet(root / "development" / "development_predictions.parquet")
    selection = json.loads((root / "development" / "selection.json").read_text())
    selected = receipt["development"]["selected"]["baseline"]["alpha"]
    other_alpha = next(alpha for alpha in load_protocol()["ridge_alphas"] if alpha != selected)
    predictions.loc[(predictions.model == "baseline") & (predictions.alpha == other_alpha), "prediction"] += 100
    with pytest.raises(FreezeValidationError, match="do not reproduce"):
        _selection_check(frame, predictions, selection, load_protocol(), reproduce=True)


@pytest.mark.parametrize("values", [[True, False], ["0.1", "0.2"], [1.0, np.nan], [1.0, np.inf]])
def test_targets_require_finite_numeric_values_without_coercion(values):
    with pytest.raises(FreezeValidationError, match="finite numeric"):
        validate_targets(pd.DataFrame({"target": values}))


def test_future_controls_fail_target_free_validation(demo):
    root, _ = demo
    features = pd.read_parquet(root / "datasets" / "holdout" / "features.parquet")
    features.loc[0, "controls_asof"] = features.loc[0, "reference_session"]
    with pytest.raises(FreezeValidationError, match="timing"):
        validate_features(features, load_protocol(), partition="holdout")


def test_annual_refit_uses_mature_prior_final_labels_and_excludes_unmatured_tail(demo):
    root, _ = demo
    development, final, receipt = frame_inputs(root)
    late_index = development.index[pd.to_datetime(development.acceptance_date).dt.year == 2021][-1]
    late_id = development.loc[late_index, "observation_id"]
    early_index = final.index[pd.to_datetime(final.acceptance_date).dt.year == 2022][0]
    for frame, index, accepted in ((development, late_index, datetime(2021, 12, 31, 18, tzinfo=NY)),
                                  (final, early_index, datetime(2022, 1, 3, 18, tzinfo=NY))):
        window = event_window(accepted)
        frame.loc[index, ["acceptance_date", "reference_session", "label_end", "controls_asof"]] = [
            window.acceptance_date, window.reference_session, window.label_end, window.controls_through,
        ]
    _, folds = _fit_frozen_annual(development, final, receipt, load_protocol())
    assert late_id not in folds[0]["training_observation_ids"]
    assert late_id in folds[1]["training_observation_ids"]
    assert [fold["mature_prior_final_rows"] for fold in folds] == [0, 12, 24, 36]
    assert folds[0]["first_reference_session"] == "2022-01-05"
    assert all(fold["max_training_label_end"] < fold["first_reference_session"] for fold in folds)


def test_future_targets_features_and_categories_cannot_change_earlier_models(demo):
    root, _ = demo
    development, final, receipt = frame_inputs(root)
    before, before_folds = _fit_frozen_annual(development, final, receipt, load_protocol())
    changed = final.copy()
    mask = pd.to_datetime(changed.acceptance_date).dt.year >= 2023
    changed.loc[mask, "target"] += 100
    changed.loc[mask, "momentum_20"] += 1000
    changed.loc[mask, "industry"] = "never-seen-future-industry"
    changed.loc[mask, "current_text"] += " futuretokenonly "
    after, after_folds = _fit_frozen_annual(development, changed, receipt, load_protocol())
    columns = ["observation_id", "baseline_prediction", "text_prediction"]
    pd.testing.assert_frame_equal(before.loc[before.year == 2022, columns],
                                  after.loc[after.year == 2022, columns])
    assert before_folds[0] == after_folds[0]
    assert "never-seen-future-industry" not in after_folds[0]["models"]["baseline"]["training_industries"]


def test_all_three_text_features_and_training_only_scaler_are_recorded(demo):
    root, _ = demo
    development, final, receipt = frame_inputs(root)
    _, folds = _fit_frozen_annual(development, final, receipt, load_protocol())
    first = folds[0]
    assert first["models"]["text"]["numeric_features"] == NUMERIC_CONTROLS + FEATURE_NAMES
    np.testing.assert_allclose(first["models"]["baseline"]["training_scaler_mean"],
                               development[NUMERIC_CONTROLS].mean().to_numpy(), atol=1e-12)
    assert len(first["models"]["text"]["training_scaler_mean"]) == 7


def test_acceptance_2025_events_keep_their_2026_reference_and_label_tail(demo):
    root, _ = demo
    development, final, receipt = frame_inputs(root)
    index = final.index[pd.to_datetime(final.acceptance_date).dt.year == 2025][-1]
    observation = final.loc[index, "observation_id"]
    window = event_window(datetime(2025, 12, 31, 18, tzinfo=NY))
    final.loc[index, ["acceptance_date", "reference_session", "label_end", "controls_asof"]] = [
        window.acceptance_date, window.reference_session, window.label_end, window.controls_through,
    ]
    predictions, _ = _fit_frozen_annual(development, final, receipt, load_protocol())
    row = predictions.loc[predictions.observation_id == observation].iloc[0]
    assert row.year == 2025 and row.reference_session.startswith("2026-")
    assert window.label_end.startswith("2026-")


def test_zero_sse_interval_is_reported_unavailable_without_changing_settings():
    predictions = pd.DataFrame({"target": np.zeros(48), "baseline_prediction": np.zeros(48),
                                "text_prediction": np.zeros(48),
                                "reference_session": pd.date_range("2022-01-01", periods=48, freq="MS")})
    result = _frozen_interval(predictions, 6, load_protocol())
    assert result["status"] == "unavailable"
    assert result["incremental_r2"] is None
    assert result["draws"] == 2000 and result["block_months"] == 6
    assert "zero" in result["reason"]


@pytest.mark.parametrize("changed", [
    {"reviewer_type": "assistant"}, {"reviewed_at": "2026-01-01"},
    {"reviewed_at": "2099-01-01T00:00:00+00:00"}, {"reviewer": ""}, {"status": "pending"},
])
def test_pending_assistant_or_undated_reviews_do_not_grant_human_approval(changed):
    review = {"status": "pass", "reviewer_type": "human", "reviewer": "Named test reviewer",
              "reviewed_at": "2025-01-01T00:00:00+00:00", "notes": "Test record only"}
    review.update(changed)
    assert not _review_complete(review)


def test_target_reader_uses_verified_snapshot_even_if_file_changes_during_parse(copied_demo, tmp_path, monkeypatch):
    root, _ = copied_demo
    target_path = root / "datasets" / "holdout" / "targets.parquet"
    expected = pd.read_parquet(target_path)
    original = pd.read_parquet
    mutated = False

    def swap_after_snapshot(source, *args, **kwargs):
        nonlocal mutated
        # The full target table has exactly two columns, unlike every source
        # evidence, feature and historical table opened by metadata validation.
        value = original(source, *args, **kwargs)
        if (not mutated and isinstance(source, final_module.io.BytesIO)
                and set(value.columns) == {"observation_id", "target"}):
            mutated = True
            changed = expected.copy()
            changed["target"] += 999
            changed.to_parquet(target_path, index=False)
        return value

    monkeypatch.setattr(pd, "read_parquet", swap_after_snapshot)
    result = evaluate_clone(root, tmp_path)
    assert result["primary_comparison_completed"] and mutated
    actual = original(tmp_path / "new-final" / "final_predictions.parquet")
    comparison = actual.merge(expected, on="observation_id", suffixes=("_actual", "_frozen"))
    np.testing.assert_array_equal(comparison.target_actual, comparison.target_frozen)
