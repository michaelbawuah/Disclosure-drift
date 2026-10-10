import io
import json
from pathlib import Path

import pandas as pd
import pytest

from disclosure_research.dataset import load_dataset, run_synthetic_dataset_demo
from disclosure_research.final_evaluation import evaluate_final, run_synthetic_final_demo
from disclosure_research.freeze import (
    AUDIT_CHECKS, SYNTHETIC, FinalAccessBlocked, FreezeValidationError,
    create_freeze, file_sha256,
)
from disclosure_research.modeling import development_comparison
from disclosure_research.protocol import canonical_hash, load_protocol
from disclosure_research.robustness import ABLATION_FEATURES, development_ablations
from disclosure_research.robustness_run import _frozen_ablation_selection, load_authorized_final, run_robustness

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


@pytest.fixture(scope="module")
def prepared_demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("authorized-robustness")
    config = load_protocol()
    run_synthetic_dataset_demo(root / "datasets", config)
    development = root / "datasets" / "development"
    holdout = root / "datasets" / "holdout"
    frame, _ = load_dataset(development, config)
    primary_predictions, primary_selection = development_comparison(frame, config)
    primary_predictions.to_parquet(root / "development_predictions.parquet", index=False)
    write_json(root / "selection.json", primary_selection)
    _, ablation_selection = development_ablations(frame, config)
    write_json(root / "ablation_selection.json", ablation_selection)
    selected_artifact = {"path": "ablation_selection.json", "sha256": file_sha256(root / "ablation_selection.json")}
    secondary = json.loads((ROOT / "configs" / "secondary_analysis.json").read_text())
    secondary["data_kind"] = SYNTHETIC
    secondary["subgroups"].update(industry_scheme="SYNTHETIC_ENGINEERING_SECTORS")
    secondary["ablations"].update({
        "selected_alphas": {name: choice["alpha"] for name, choice in ablation_selection["selected"].items()},
        "selection_artifact": selected_artifact,
        "development_selection_evidence": [selected_artifact],
    })
    write_json(root / "secondary.json", secondary)
    audit = {
        "schema_version": 1, "protocol_sha256": canonical_hash(config), "data_kind": SYNTHETIC,
        "bound_inputs": {
            "development_dataset": file_sha256(development / "dataset.parquet"),
            "dataset_manifest": file_sha256(development / "dataset_manifest.json"),
            "exclusions": file_sha256(development / "exclusions.parquet"),
        },
        "checks": {name: {"status": "pending", "reviewer_type": "assistant", "reviewer": "synthetic fixture",
                          "notes": "No empirical human approval is asserted", "evidence": []} for name in AUDIT_CHECKS},
    }
    write_json(root / "audit.json", audit)
    create_freeze(development / "dataset.parquet", root / "development_predictions.parquet", root / "selection.json",
                  output=root / "freeze", config=config, manifest=development / "dataset_manifest.json",
                  exclusions=development / "exclusions.parquet", audit_evidence=root / "audit.json",
                  secondary_spec=root / "secondary.json", repo_root=ROOT, synthetic=True,
                  final_features=holdout / "features.parquet", final_targets=holdout / "targets.parquet",
                  final_manifest=holdout / "dataset_manifest.json", final_exclusions=holdout / "exclusions.parquet")
    evaluate_final(root / "freeze", output=root / "final", config=config, repo_root=ROOT,
                   ledger=root / "ledger", synthetic=True)
    return root


@pytest.fixture
def sealed_demo(prepared_demo):
    # Reuse the expensive chronological fit, but restore every source/ledger
    # byte after fault injection so tests remain independent.
    files = {path: path.read_bytes() for path in prepared_demo.rglob("*") if path.is_file()}
    yield prepared_demo
    for path in prepared_demo.rglob("*"):
        if path.is_file() and path not in files:
            path.unlink()
    for path, body in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)


def test_completed_run_drives_all_bound_robustness_components_without_new_selection(sealed_demo, tmp_path):
    result = run_robustness(sealed_demo / "final", sealed_demo / "freeze", tmp_path / "results",
                            load_protocol(), ROOT)
    assert result["data_kind"] == SYNTHETIC and not result["empirical_results"]
    assert result["observations"] == 48
    assert result["components"] == {"diagnostics": "completed", "subgroups": "completed",
                                     "failure_cases": "completed", "ablations": "completed"}
    assert result["new_penalties_selected"] is False
    assert result["final_target_table_deserialized"] is False
    assert result["delay_comparisons"]["status"] == "not_run"
    assert "independent" in result["delay_comparisons"]["reason"]
    assert result["secondary_analyses_complete"] is False
    predictions = pd.read_parquet(tmp_path / "results" / "ablation_predictions.parquet")
    assert len(predictions) == 48 * 6 and set(predictions.ablation) == set(ABLATION_FEATURES)
    assert set(predictions.year) == {2022, 2023, 2024, 2025}
    for name, expected in result["files"].items():
        assert file_sha256(tmp_path / "results" / name) == expected


def test_robustness_never_deserializes_final_targets_or_runs_development_tuning(sealed_demo, tmp_path, monkeypatch):
    target_bytes = (sealed_demo / "datasets" / "holdout" / "targets.parquet").read_bytes()
    original_read = pd.read_parquet

    def forbid_final_targets(source, *args, **kwargs):
        if isinstance(source, (str, Path)):
            assert Path(source).resolve() != (sealed_demo / "datasets" / "holdout" / "targets.parquet").resolve()
        if isinstance(source, io.BytesIO):
            assert source.getvalue() != target_bytes, "Final target payload was decoded"
        return original_read(source, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", forbid_final_targets)
    monkeypatch.setattr("disclosure_research.robustness.development_ablations",
                        lambda *args, **kwargs: pytest.fail("A new ablation search was run after final access"))
    monkeypatch.setattr("disclosure_research.freeze.development_comparison",
                        lambda *args, **kwargs: pytest.fail("New primary choices were selected"))
    result = run_robustness(sealed_demo / "final", sealed_demo / "freeze", tmp_path / "results", load_protocol(), ROOT)
    assert result["components"]["ablations"] == "completed"


@pytest.mark.parametrize("corruption", ["predictions", "summary", "access", "completion", "study", "code", "source", "selection", "promotion"])
def test_untrusted_run_is_rejected_before_saved_outcomes_are_decoded(sealed_demo, tmp_path, monkeypatch, corruption):
    summary = json.loads((sealed_demo / "final" / "final_summary.json").read_text())
    run_id = summary["access_run_id"]
    if corruption == "predictions":
        path = sealed_demo / "final" / "final_predictions.parquet"
        path.write_bytes(path.read_bytes() + b"changed")
    elif corruption == "summary":
        summary["observations"] += 1
        write_json(sealed_demo / "final" / "final_summary.json", summary)
    elif corruption == "access":
        path = sealed_demo / "ledger" / f"{run_id}.access.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif corruption == "completion":
        (sealed_demo / "ledger" / f"{run_id}.access.complete.json").unlink()
    elif corruption == "study":
        path = sealed_demo / "ledger" / f"synthetic-{canonical_hash(load_protocol())}.json"
        value = json.loads(path.read_text())
        value["freeze_id"] = "0" * 64
        write_json(path, value)
    elif corruption == "code":
        path = sealed_demo / "freeze" / "freeze.json"
        value = json.loads(path.read_text())
        value["code"]["source_sha256"]["src/disclosure_research/modeling.py"] = "0" * 64
        value["freeze_id"] = canonical_hash({key: item for key, item in value.items() if key != "freeze_id"})
        write_json(path, value)
    elif corruption == "source":
        path = sealed_demo / "datasets" / "holdout" / "features.parquet"
        path.write_bytes(path.read_bytes() + b"changed")
    elif corruption == "selection":
        path = sealed_demo / "ablation_selection.json"
        path.write_bytes(path.read_bytes() + b" ")
    else:
        summary.update(data_kind="EMPIRICAL_RESEARCH_DATA", empirical_ready=True,
                       final_period_opened=True, synthetic_targets_opened=False)
        write_json(sealed_demo / "final" / "final_summary.json", summary)
    monkeypatch.setattr(pd, "read_parquet", lambda *args, **kwargs: pytest.fail("Outcome payload decoded on rejecting path"))
    with pytest.raises((ValueError, FileNotFoundError)):
        run_robustness(sealed_demo / "final", sealed_demo / "freeze", tmp_path / "rejected", load_protocol(), ROOT)
    assert not (tmp_path / "rejected").exists()


def test_an_active_or_failed_access_reservation_cannot_authorize_secondary_results(sealed_demo, tmp_path):
    summary = json.loads((sealed_demo / "final" / "final_summary.json").read_text())
    run_id = summary["access_run_id"]
    write_json(sealed_demo / "ledger" / f"{run_id}.access.failed.json", {"state": "failed"})
    with pytest.raises(FinalAccessBlocked, match="incomplete|failure"):
        run_robustness(sealed_demo / "final", sealed_demo / "freeze", tmp_path / "rejected", load_protocol(), ROOT)


def test_missing_frozen_secondary_artifacts_are_reported_without_retuning(tmp_path):
    # A separate, explicitly synthetic final fixture has pending secondary
    # choices. Production empirical freezes do not acquire such an exception.
    demo = tmp_path / "incomplete-methods"
    run_synthetic_final_demo(demo, load_protocol(), repo_root=ROOT)
    result = run_robustness(demo / "final", demo / "freeze", tmp_path / "results", load_protocol(), ROOT)
    assert result["components"]["ablations"] == "unavailable"
    assert result["components"]["subgroups"] == "unavailable"
    report = json.loads((tmp_path / "results" / "ablations.json").read_text())
    assert "selection_artifact" in report["reason"]
    assert not (tmp_path / "results" / "ablation_predictions.parquet").exists()


def test_shared_authorized_loader_returns_saved_labels_and_checks_existing_output(sealed_demo, tmp_path):
    predictions, receipt, summary = load_authorized_final(sealed_demo / "final", sealed_demo / "freeze", load_protocol(), ROOT)
    assert len(predictions) == 48
    assert receipt["freeze_id"] == summary["freeze_id"]
    output = tmp_path / "exists"
    output.mkdir()
    (output / "preserve.txt").write_text("earlier results")
    with pytest.raises(FreezeValidationError, match="new directory"):
        run_robustness(sealed_demo / "final", sealed_demo / "freeze", output, load_protocol(), ROOT)
    assert (output / "preserve.txt").read_text() == "earlier results"


@pytest.mark.parametrize("payload", ["[]", "not a selection document"])
def test_bound_but_unusable_ablation_artifact_stays_unavailable(tmp_path, payload):
    path = tmp_path / "selection.json"
    path.write_text(payload)
    item = {"path": str(path), "sha256": file_sha256(path)}
    selection, reason = _frozen_ablation_selection({"ablations": {"selection_artifact": item}},
                                                   tmp_path / "secondary.json", {"evidence_files": [item]},
                                                   pd.DataFrame(), load_protocol())
    assert selection is None and "JSON" in reason
