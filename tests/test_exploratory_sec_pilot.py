"""Only synthetic sources: check the quarantine of provisional empirical exploration."""

import hashlib
import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from disclosure_research.exploratory_sec_pilot import (
    FIXED_ALPHA,
    KIND,
    _conditional_metrics,
    run_exploratory_sec_pilot,
)
from disclosure_research.protocol import canonical_hash, load_protocol


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def staged(tmp_path):
    repo = tmp_path / "repo"
    source = repo / "data" / "market"
    text = repo / "reports" / "sec"
    source.mkdir(parents=True)
    text.mkdir(parents=True)
    config = load_protocol()
    proto = canonical_hash(config)
    history, features = [], []
    previous_years = 0
    for year in range(2015, 2022):
        records = 19 if year <= 2019 else 20
        for i in range(records):
            cik = f"{1000000000 + i:010d}"
            accession = f"{1000000000 + i:010d}-{year % 100:02d}-{i + 1:06d}"
            acceptance = f"{year}-01-10T09:15:00-05:00"
            ref = date(year, 1, 25)
            end = date(year, 2, 28)
            controls = date(year, 1, 24)
            momentum = (i - 10) / 250
            market = 0.012 + i / 10000
            target = (i - 9) / 200 + (year - 2015) / 1000
            history.append({
                "event_id": accession,
                "cik": cik,
                "acceptance_timestamp": acceptance,
                "data_kind": "PROVISIONAL_CANDIDATE_ARITHMETIC_QA",
                "previous_accession": f"{1000000000+i:010d}-{(year-1)%100:02d}-{i+1:06d}",
                "human_pair_review_complete": False,
                "reference_session": ref.isoformat(),
                "controls_asof": controls.isoformat(),
                "label_end": end.isoformat(),
                "control_history_start": (controls - timedelta(days=90)).isoformat(),
                "candidate_permno": str(5000 + i),
                "identity_approved": False, "model_ready": False,
                "qa_status": "calculated_pending_review",
                "header_cik_differs": i % 7 == 0, "open_end_unresolved": True,
                "stock_return": market + target,
                "market_return": market, "target": target,
                "horizon_sessions": 20,
                "momentum_20": momentum, "momentum_60": 1.7 * momentum,
                "volatility_20": 0.02 + i / 10000,
                "log_market_cap": 22 + i / 1000,
                "industry": str(3000 + i % 4),
                "control_history_sessions": 60, "independent_max_abs_error": 0.0,
            })
            old, new = 400 + i, 420 + i + year % 5
            features.append({
                "observation_id": accession, "cik": cik, "year": year,
                "previous_tokens": old, "current_tokens": new,
                "log_length_change": np.log1p(new) - np.log1p(old),
                "jaccard_distance": 0.1 + i / 100,
                "tfidf_cosine_distance": np.nan if year == 2015 else 0.03 + i / 1000,
                "vocabulary_training_pairs": previous_years,
                "source_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/original.htm",
                "previous_source_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/previous.htm",
            })
        previous_years += records
    history = pd.DataFrame(history)
    features = pd.DataFrame(features)
    src_path = source / "candidate_calculations.parquet"
    history.to_parquet(src_path, index=False)
    txt_path = text / "text_features.csv"
    with np.errstate(invalid="ignore"):
        features.to_csv(txt_path, index=False)
    pilot = {
        "data_kind": "PROVISIONAL_CANDIDATE_ARITHMETIC_QA",
        "qa_cases_calculated": 135,
        "model_ready": False, "milestone_05_complete": False,
        "historical_cik_mapping_approved": False, "final_period_opened": False,
        "source_hashes": {"protocol": proto},
        "files": {"candidate_calculations.parquet": _sha(src_path)},
    }
    descriptor = {
        "data_kind": "REAL_SEC_TEXT_DESCRIPTIVE_PILOT",
        "protocol_sha256": proto, "pairs": 135, "returns_read": False,
        "milestone_06_complete": False,
        "files": {"text_features.csv": _sha(txt_path)},
    }
    (source / "audit_summary.json").write_text(json.dumps(pilot))
    (text / "pilot_checkpoint.json").write_text(json.dumps(descriptor))
    return {
        "repo": repo, "source": source, "text": text, "history": history,
        "features": features, "config": config,
    }


def run(staged, suffix="first"):
    return run_exploratory_sec_pilot(
        staged["source"], staged["text"], staged["repo"] / "outputs" / suffix,
        staged["config"], staged["repo"],
    )


def republish_table(staged):
    path = staged["source"] / "candidate_calculations.parquet"
    staged["history"].to_parquet(path, index=False)
    p = staged["source"] / "audit_summary.json"
    receipt = json.loads(p.read_text())
    receipt["files"]["candidate_calculations.parquet"] = _sha(path)
    p.write_text(json.dumps(receipt))


def republish_text(staged):
    path = staged["text"] / "text_features.csv"
    with np.errstate(invalid="ignore"):
        staged["features"].to_csv(path, index=False)
    p = staged["text"] / "pilot_checkpoint.json"
    receipt = json.loads(p.read_text())
    receipt["files"]["text_features.csv"] = _sha(path)
    p.write_text(json.dumps(receipt))


def test_development_only_fixed_spec_and_private_receipt(staged):
    public = run(staged)
    assert public["data_kind"] == KIND
    assert public["matched_sec_disclosure_pairs"] == 135
    assert public["development_test_rows"] == 116
    assert public["development_test_years"] == [2016, 2017, 2018, 2019, 2020, 2021]
    assert [x["train_rows"] for x in public["yearly_train_and_test_counts"]] == [19, 38, 57, 76, 95, 115]
    assert [x["test_rows"] for x in public["yearly_train_and_test_counts"]] == [19, 19, 19, 19, 20, 20]
    assert public["performance_estimates_published"] is False
    assert public["final_period_opened"] is False
    assert public["source_approvals"] == 0
    dest = staged["repo"] / "outputs" / "first"
    assert dest.stat().st_mode & 0o077 == 0
    receipt = json.loads((dest / "receipt.json").read_text())
    assert receipt["model_ready"] is False
    assert receipt["final_period_opened"] is False
    assert receipt["private_metrics_unreviewed"] is True
    for filename, binding in receipt["files"].items():
        file = dest / filename
        assert _sha(file) == binding["sha256"]
        assert file.stat().st_mode & 0o222 == 0
    data = pd.read_csv(dest / "candidate_predictions_private.csv")
    assert len(data) == 232
    assert set(data.model) == {"baseline", "text"}
    assert set(data.filing_year) == set(range(2016, 2022))
    assert data.fixed_alpha.eq(FIXED_ALPHA).all()
    assert not data.observation_id.duplicated().all()
    assert data.groupby(["filing_year", "model"]).size().to_dict() == {
        (year, model): 19 if year <= 2019 else 20
        for year in range(2016, 2022) for model in ("baseline", "text")
    }
    assert data["squared_error"].ge(0).all()
    details = json.loads((dest / "conditional_metrics_private.json").read_text())
    totals = data.groupby("model")["squared_error"].sum().to_dict()
    assert details["conditional_metrics"]["baseline_sse"] == pytest.approx(totals["baseline"])
    assert details["conditional_metrics"]["text_sse"] == pytest.approx(totals["text"])
    assert details["candidate_identity_approved"] is False
    assert details["actual_2022_2025_final_period_opened"] is False


def test_overwrite_is_refused_and_original_source_unchanged(staged):
    before = _sha(staged["source"] / "candidate_calculations.parquet")
    run(staged)
    with pytest.raises(ValueError, match="overwrite"):
        run(staged)
    assert _sha(staged["source"] / "candidate_calculations.parquet") == before


def test_modifying_source_without_matching_receipt_fails(staged):
    staged["history"].loc[0, "target"] += 0.01
    staged["history"].to_parquet(staged["source"] / "candidate_calculations.parquet", index=False)
    with pytest.raises(ValueError, match="fingerprint"):
        run(staged)
    assert not (staged["repo"] / "outputs" / "first").exists()


def test_rehashed_sec_cik_mismatch_does_not_join(staged):
    staged["features"].loc[0, "cik"] = "0000000029"
    republish_text(staged)
    with pytest.raises(ValueError, match="CIK"):
        run(staged)


def test_temporal_leakage_control_date_detected(staged):
    staged["history"].loc[0, "controls_asof"] = "2015-03-01"
    republish_table(staged)
    with pytest.raises(ValueError, match="temporal"):
        run(staged)


def test_future_acceptance_is_rejected(staged):
    staged["history"].loc[0, "acceptance_timestamp"] = "2023-01-10T09:15:00-05:00"
    republish_table(staged)
    with pytest.raises(ValueError, match="filing-year"):
        run(staged)


def test_future_text_year_rejected_even_if_rehashed(staged):
    staged["features"].loc[0, "year"] = 2025
    republish_text(staged)
    with pytest.raises(ValueError, match="holdout boundary"):
        run(staged)


def test_future_vocabulary_leak_rejected(staged):
    ix = staged["features"].index[staged["features"].year.eq(2016)][0]
    staged["features"].loc[ix, "vocabulary_training_pairs"] = 130
    republish_text(staged)
    with pytest.raises(ValueError, match="future-filing leakage"):
        run(staged)


def test_wrong_text_metric_rejected(staged):
    staged["features"].loc[0, "log_length_change"] = -100
    republish_text(staged)
    with pytest.raises(ValueError, match="text-length"):
        run(staged)


def test_unreviewed_mappings_cannot_be_silently_promoted(staged):
    staged["history"].loc[0, "identity_approved"] = True
    republish_table(staged)
    with pytest.raises(ValueError, match="identity_approved"):
        run(staged)


def test_rehashed_target_mutation_is_not_accepted(staged):
    staged["history"].loc[0, "target"] += 0.1
    republish_table(staged)
    with pytest.raises(ValueError, match="target identity"):
        run(staged)


def test_duplicate_event_ids_are_rejected(staged):
    staged["history"].loc[1, "event_id"] = staged["history"].loc[0, "event_id"]
    republish_table(staged)
    with pytest.raises(ValueError, match="Duplicate"):
        run(staged)


def test_unapproved_feature_model_is_not_claimed_to_be_primary(staged):
    status = run(staged)
    assert status["comparison_status"] == "EXECUTED_PRIVATELY_NOT_VALIDATED"
    assert status["study_milestones_completed"] == []
    assert "conditional" in json.loads(
        (staged["repo"] / "outputs" / "first" / "conditional_metrics_private.json").read_text()
    )["conditional_metrics"]["note"].lower()


def test_cluster_bootstrap_sanity_and_seed():
    table = pd.DataFrame([
        {"observation_id": f"{i}", "cik": f"{i:010d}", "model": model,
         "squared_error": (i + 1) * (1 if model == "baseline" else 0.75)}
        for i in range(20) for model in ("baseline", "text")
    ])
    m1 = _conditional_metrics(table, seed=100, draws=200)
    m2 = _conditional_metrics(table, seed=100, draws=200)
    assert m1 == m2
    assert m1["conditional_relative_sse_change"] == pytest.approx(0.25)
    assert m1["cluster_percentile_interval_95"] == pytest.approx([0.25, 0.25])


@pytest.mark.parametrize("suffix", [
    "../outside", "../../../elsewhere",
])
def test_output_escape_is_refused(staged, suffix):
    with pytest.raises(ValueError, match="Private output"):
        run(staged, suffix)
