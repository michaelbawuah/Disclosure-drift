"""Synthetic-only tests for source-bound, non-approving public checkpoint logic."""

import hashlib
import json

import pandas as pd
import pytest

from disclosure_research.protocol import canonical_hash, load_protocol
from disclosure_research.alternative_checkpoint import build_checkpoint


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def setup(tmp_path):
    config = load_protocol()
    root = tmp_path / "repo"
    pilot = root / "outputs" / "pilot"
    benchmark = root / "outputs" / "benchmark"
    pilot.mkdir(parents=True)
    benchmark.mkdir()
    rows, folds = [], []
    count_per_year = (19, 19, 19, 19, 20, 20)
    for i, year in enumerate(range(2016, 2022)):
        train_n = [19, 38, 57, 76, 95, 115][i]
        folds.append({
            "test_year": year, "train_rows": train_n, "test_rows": count_per_year[i],
            "earliest_test_reference_session": f"{year}-02-01",
            "training_label_end_max": f"{year - 1}-11-30",
            "training_filing_years": list(range(2015, year)),
        })
        for j in range(count_per_year[i]):
            identity = f"{1000000000+j:010d}-{year%100:02d}-{j:06d}"
            target = 0.05 - j / 1000
            for model, prediction in [("baseline", 0.025), ("text", 0.03)]:
                rows.append({
                    "observation_id": identity, "cik": f"{1000000000+j:010d}",
                    "filing_year": year, "reference_session": f"{year}-03-01",
                    "label_end": f"{year}-03-30",
                    "model": model, "fixed_alpha": 10.0,
                    "prediction": prediction,
                    "target": target,
                    "squared_error": (target - prediction)**2,
                    "train_rows": train_n,
                })
    frames = pd.DataFrame(rows)
    frames.to_csv(pilot / "candidate_predictions_private.csv", index=False, float_format="%.17g")
    totals = frames.groupby("model")["squared_error"].sum().to_dict()
    details = {
        "data_kind": "UNAPPROVED_REAL_CANDIDATE_EXPLORATORY_DEVELOPMENT_ONLY",
        "protocol_sha256": canonical_hash(config),
        "source_bindings_sha256": {
            "candidate_table": "a"*64, "candidate_receipt": "b"*64,
            "text_features": "c"*64, "text_receipt": "d"*64,
        },
        "actual_model_ready": False,
        "actual_2022_2025_final_period_opened": False,
        "folds": folds,
        "conditional_metrics": {
            "baseline_sse": totals["baseline"],
            "text_sse": totals["text"],
            "conditional_relative_sse_change": 1 - totals["text"]/totals["baseline"],
        },
    }
    (pilot / "conditional_metrics_private.json").write_text(json.dumps(details))
    public = {
        "data_kind": details["data_kind"],
        "protocol_sha256": canonical_hash(config),
        "development_test_rows": 116,
        "fixed_alpha": 10.0,
        "matched_sec_disclosure_pairs": 135,
        "candidate_issuers": 20,
        "model_ready": False, "final_period_opened": False,
        "performance_estimates_published": False,
        "source_approvals": 0, "historical_identity_approvals": 0,
        "study_milestones_completed": [],
    }
    (pilot / "public_summary.json").write_text(json.dumps(public))
    files = {
        p.name: {"sha256": _sha(p), "bytes": p.stat().st_size}
        for p in pilot.iterdir()
    }
    receipt = {
        "data_kind": details["data_kind"],
        "protocol_sha256": canonical_hash(config),
        "model_ready": False, "final_period_opened": False,
        "private_metrics_unreviewed": True,
        "source_hashes": details["source_bindings_sha256"],
        "files": files,
    }
    (pilot / "receipt.json").write_text(json.dumps(receipt))
    market = {
        "status": "PUBLIC_COMPARISON_NOT_PRIMARY_SOURCE_APPROVAL",
        "model_ready": False, "final_period_opened": False,
        "benchmark_selected": False,
        "development_return_cutoff": "2022-02-02",
        "stopped_before_later_public_factor_values": "2022-02-03",
        "overlap_sessions": 3103, "crsp_sessions": 3103,
        "crsp_sessions_missing_in_public": 0,
        "public_file_reported_upstream_crsp_yyyymm": "202608",
        "daily_exact_equality_days": 4,
        "public_zip_sha256": "1"*64,
        "private_crsp_source_sha256": "2"*64,
        "private_inventory_receipt_sha256": "3"*64,
    }
    (benchmark / "summary.json").write_text(json.dumps(market))
    benchmark_receipt = {
        "status": market["status"],
        "summary_sha256": _sha(benchmark / "summary.json"),
        "model_ready": False, "final_period_opened": False,
        "source_approvals": 0,
        "source_hashes_sha256": {
            "public_zip": "1"*64,
            "private_crsp_csv": "2"*64,
            "private_crsp_receipt": "3"*64,
        },
    }
    (benchmark / "receipt.json").write_text(json.dumps(benchmark_receipt))
    return pilot, benchmark, root / "reports" / "checkpoint.json", config


def _refresh(pilot):
    receipt = json.loads((pilot / "receipt.json").read_text())
    for p in pilot.iterdir():
        if p.name != "receipt.json":
            receipt["files"][p.name] = {"sha256": _sha(p), "bytes": p.stat().st_size}
    (pilot / "receipt.json").write_text(json.dumps(receipt))


def test_public_checkpoint_is_aggregate_only(setup):
    pilot, benchmark, output, config = setup
    info = build_checkpoint(pilot, benchmark, output, config)
    assert info["pilot"]["development_predictions_per_model"] == 116
    assert info["pilot"]["independent_prediction_arithmetic_passed"]
    assert info["pilot"]["development_timing_separation_verified"]
    assert info["public_market_source_comparison"]["matched_development_market_sessions"] == 3103
    assert not info["final_2022_2025_evaluation_opened"]
    assert not info["model_ready"]
    assert info["source_approvals_created"] == 0
    assert "baseline_sse" not in output.read_text()
    assert "conditional_relative_sse_change" not in output.read_text()
    with pytest.raises(ValueError, match="overwrite"):
        build_checkpoint(pilot, benchmark, output, config)


def test_independent_mse_verifier_finds_modified_prediction_even_if_rehashed(setup):
    pilot, benchmark, output, config = setup
    path = pilot / "candidate_predictions_private.csv"
    df = pd.read_csv(path)
    df.loc[0, "squared_error"] += 0.4
    df.to_csv(path, index=False)
    _refresh(pilot)
    with pytest.raises(ValueError, match="squared error arithmetic"):
        build_checkpoint(pilot, benchmark, output, config)


def test_future_year_diagnostic_rejected_even_if_rehashed(setup):
    pilot, benchmark, output, config = setup
    path = pilot / "candidate_predictions_private.csv"
    df = pd.read_csv(path)
    df.loc[0, "filing_year"] = 2025
    df.to_csv(path, index=False)
    _refresh(pilot)
    with pytest.raises(ValueError, match="Holdout predictions"):
        build_checkpoint(pilot, benchmark, output, config)


def test_private_receipt_tamper_rejected(setup):
    pilot, benchmark, output, config = setup
    (pilot / "candidate_predictions_private.csv").write_text("changed")
    with pytest.raises(ValueError, match="Corrupt"):
        build_checkpoint(pilot, benchmark, output, config)


def test_market_source_not_approved(setup):
    pilot, benchmark, output, config = setup
    path = benchmark / "receipt.json"
    data = json.loads(path.read_text())
    data["source_approvals"] = 1
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="falsely approved"):
        build_checkpoint(pilot, benchmark, output, config)


def test_historical_bound_not_inferred(setup):
    pilot, benchmark, output, config = setup
    path = benchmark / "summary.json"
    data = json.loads(path.read_text())
    data["stopped_before_later_public_factor_values"] = "2022-01-31"
    path.write_text(json.dumps(data))
    receipt = json.loads((benchmark / "receipt.json").read_text())
    receipt["summary_sha256"] = _sha(path)
    (benchmark / "receipt.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="boundary"):
        build_checkpoint(pilot, benchmark, output, config)


def test_invalid_training_label_end_detected(setup):
    pilot, benchmark, output, config = setup
    path = pilot / "conditional_metrics_private.json"
    details = json.loads(path.read_text())
    details["folds"][0]["training_label_end_max"] = "2016-03-01"
    path.write_text(json.dumps(details))
    _refresh(pilot)
    with pytest.raises(ValueError, match="Training labels"):
        build_checkpoint(pilot, benchmark, output, config)
