from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from disclosure_research.cli import synthetic_dataset
from disclosure_research.controls import control_sessions
from disclosure_research.protocol import load_protocol
from disclosure_research.robustness import (
    ABLATION_FEATURES,
    compare_ablation_predictions,
    compare_delay_predictions,
    describe_paragraph_changes,
    development_ablations,
    evaluate_ablations,
    evaluate_delay_predictions,
    failure_cases,
    prediction_diagnostics,
    rebuild_delay_dataset,
    subgroup_diagnostics,
    validate_delay_dataset,
)
from disclosure_research.timing import calendar, event_window


def paired_predictions(months=48, firms=3):
    rows = []
    for month in pd.date_range("2018-01-01", periods=months, freq="MS"):
        reference = calendar().date_to_session(month, direction="next").strftime("%Y-%m-%d")
        for firm in range(firms):
            target = (firm + 1) * 0.02
            rows.append({"observation_id": f"SYNTHETIC-{month:%Y-%m}-{firm}", "year": month.year,
                         "reference_session": reference, "target": target,
                         "baseline_prediction": 0.0, "text_prediction": target / 2,
                         "baseline_alpha": 1.0, "text_alpha": 10.0})
    return pd.DataFrame(rows)


def test_secondary_scores_omit_year_without_refitting_and_keep_reference_month_blocks():
    predictions = paired_predictions()
    report = prediction_diagnostics(predictions, load_protocol())
    assert report["pooled"]["incremental_r2"] == pytest.approx(0.75)
    assert [row["observations"] for row in report["annual_scores"]] == [36] * 4
    assert [row["observations"] for row in report["leave_one_year_out"]] == [108] * 4
    assert all(row["incremental_r2"] == pytest.approx(0.75) for row in report["leave_one_year_out"])
    assert [row["block_months"] for row in report["bootstrap"]] == [3, 6]
    assert all(row["draws"] == 2000 and row["seed"] == 20261009 for row in report["bootstrap"])
    assert all(row["lower_95"] == pytest.approx(0.75) for row in report["bootstrap"])
    assert all(row["text_spearman"] == pytest.approx(1) for row in report["monthly_rank_correlation"])
    assert all(row["baseline_status"] == "constant_prediction" for row in report["monthly_rank_correlation"])


def test_year_diagnostics_use_acceptance_year_even_when_reference_is_next_year():
    predictions = paired_predictions(months=1)
    predictions["year"] = 2017
    report = prediction_diagnostics(predictions, load_protocol())
    assert report["annual_scores"][0]["year"] == 2017
    assert report["monthly_rank_correlation"][0]["reference_month"] == "2018-01"
    assert report["leave_one_year_out"][0]["status"] == "no_observations"
    assert all(row["status"] == "unavailable" for row in report["bootstrap"])


def test_rank_groups_keep_small_constant_and_tied_groups_explicit():
    predictions = paired_predictions(months=3)
    predictions = predictions.drop(index=0).copy()
    predictions.loc[predictions.reference_session == "2018-02-01", "target"] = 0.1
    predictions.loc[predictions.reference_session == "2018-03-01", "baseline_prediction"] = [1, 1, 2]
    report = prediction_diagnostics(predictions, load_protocol())
    monthly = report["monthly_rank_correlation"]
    assert monthly[0]["text_status"] == "insufficient_observations"
    assert monthly[0]["text_spearman"] is None
    assert monthly[1]["text_status"] == "constant_target"
    assert monthly[2]["baseline_spearman"] == pytest.approx(np.sqrt(3) / 2)


def test_zero_baseline_error_is_reported_without_fabricating_an_improvement():
    predictions = paired_predictions(months=12)
    predictions["baseline_prediction"] = predictions.target
    report = prediction_diagnostics(predictions, load_protocol())
    assert report["pooled"]["incremental_r2"] is None
    assert report["pooled"]["status"] == "undefined_zero_baseline_sse"
    assert all(row["status"] == "unavailable" for row in report["bootstrap"])


@pytest.mark.parametrize("mutation", ["duplicate", "nonfinite", "overflow", "missing_year"])
def test_diagnostics_reject_unusable_or_unpaired_predictions(mutation):
    predictions = paired_predictions(months=1)
    if mutation == "duplicate":
        predictions.loc[1, "observation_id"] = predictions.loc[0, "observation_id"]
    elif mutation == "nonfinite":
        predictions.loc[0, "text_prediction"] = np.nan
    elif mutation == "overflow":
        predictions.loc[0, "text_prediction"] = 1e300
    else:
        predictions = predictions.drop(columns="year")
    with pytest.raises(ValueError):
        prediction_diagnostics(predictions, load_protocol())


def covariates(predictions):
    return pd.DataFrame({
        "observation_id": predictions.observation_id,
        "controls_asof": [calendar().previous_session(day).strftime("%Y-%m-%d")
                          for day in predictions.reference_session],
        "log_market_cap": np.log([1e9, 20e9, 200e9] * (len(predictions) // 3)),
        "industry": ["10", "20", "20"] * (len(predictions) // 3),
        "industry_scheme": "historical_sic",
    })


def test_size_industry_diagnostics_use_fixed_usd_cutpoints_and_prior_date():
    predictions = paired_predictions(months=1)
    groups = covariates(predictions)
    report = subgroup_diagnostics(predictions, groups, size_cutpoints_usd=[10e9, 100e9],
                                  industry_scheme="historical_sic")
    assert [row["observations"] for row in report["size_scores"]] == [1, 1, 1]
    assert [row["observations"] for row in report["industry_scores"]] == [1, 2]
    assert all(row["incremental_r2"] == pytest.approx(0.75) for row in report["size_scores"])


@pytest.mark.parametrize("mutation", ["missing", "future", "stale", "scheme", "duplicate"])
def test_subgroups_do_not_silently_drop_rows_or_use_current_classifications(mutation):
    predictions = paired_predictions(months=1)
    groups = covariates(predictions)
    if mutation == "missing":
        groups = groups.iloc[:-1]
    elif mutation == "future":
        groups.loc[0, "controls_asof"] = predictions.reference_session.iloc[0]
    elif mutation == "stale":
        groups.loc[0, "controls_asof"] = "2017-12-28"
    elif mutation == "scheme":
        groups.loc[0, "industry_scheme"] = "current_header_sic"
    else:
        groups = pd.concat([groups, groups.iloc[:1]])
    with pytest.raises(ValueError):
        subgroup_diagnostics(predictions, groups, size_cutpoints_usd=[10e9], industry_scheme="historical_sic")


def test_failure_examples_are_source_linked_and_explicitly_outcome_selected():
    predictions = paired_predictions(months=1)
    predictions["text_prediction"] = 2.0
    filings = pd.DataFrame({"observation_id": predictions.observation_id,
                            "current_source_url": "https://example.invalid/current",
                            "previous_source_url": "https://example.invalid/previous"})
    examples = failure_cases(predictions, filings, limit=2)
    assert len(examples) == 2
    assert examples[0]["added_squared_error"] >= examples[1]["added_squared_error"]
    assert all("outcome_selected_descriptive" in row["selection"] for row in examples)
    with pytest.raises(ValueError, match="source references"):
        failure_cases(predictions, filings.iloc[:-1])


@pytest.fixture(scope="module")
def ablation_development():
    return development_ablations(synthetic_dataset(), load_protocol())


def test_all_declared_ablations_use_pooled_development_mse_and_the_same_observations(ablation_development):
    predictions, selection = ablation_development
    assert selection["configurations"] == 24
    assert set(selection["selected"]) == set(ABLATION_FEATURES)
    assert selection["features"]["length_only"] == ["log_length_change"]
    assert set(predictions.year) == set(range(2016, 2022))
    assert predictions.groupby(["ablation", "alpha"]).size().nunique() == 1
    for name, choice in selection["selected"].items():
        scores = predictions.loc[predictions.ablation == name].groupby("alpha").squared_error.mean()
        expected = sorted(scores.items(), key=lambda pair: (pair[1], pair[0]))[0]
        assert choice["alpha"] == expected[0]
        assert choice["development_mse"] == pytest.approx(expected[1])


def test_ablations_refuse_final_events_during_development():
    frame = synthetic_dataset()
    frame.loc[0, "acceptance_date"] = "2022-01-01"
    with pytest.raises(ValueError, match="blocked"):
        development_ablations(frame, load_protocol())


def extended_dataset():
    development = synthetic_dataset()
    rows = development.to_dict(orient="records")
    for year in range(2022, 2026):
        for issuer in range(12):
            source = development.loc[development.acceptance_date.str.startswith("2021")].iloc[issuer].to_dict()
            window = event_window(datetime(year, 2 + issuer % 6, 15, 18, tzinfo=ZoneInfo("America/New_York")))
            source.update({"observation_id": f"SYNTHETIC-{year}-{issuer}", "acceptance_date": window.acceptance_date,
                           "reference_session": window.reference_session, "label_end": window.label_end,
                           "controls_asof": window.controls_through})
            rows.append(source)
    return pd.DataFrame(rows)


def test_final_ablations_do_not_retune_or_use_the_evaluation_years_outcomes(ablation_development):
    _, selection = ablation_development
    frame = extended_dataset()
    original = evaluate_ablations(frame, selection, load_protocol(), years=[2022])
    frame.loc[frame.acceptance_date.str.startswith("2022"), "target"] = 0.987
    frame.loc[frame.acceptance_date.str.startswith("2025"), "current_text"] = "unseen future unicorn risk"
    changed = evaluate_ablations(frame, selection, load_protocol(), years=[2022])
    np.testing.assert_array_equal(original.prediction, changed.prediction)
    assert len(original) == 12 * 6
    for name, choice in selection["selected"].items():
        assert set(original.loc[original.ablation == name, "alpha"]) == {choice["alpha"]}


def test_final_ablation_training_requires_label_maturity(ablation_development):
    _, selection = ablation_development
    frame = extended_dataset()
    index = frame.index[frame.observation_id.eq("SYNTHETIC-2021-0")][0]
    previous = event_window(datetime(2021, 12, 30, 18, tzinfo=ZoneInfo("America/New_York")))
    first = event_window(datetime(2022, 1, 3, 18, tzinfo=ZoneInfo("America/New_York")))
    frame.loc[index, ["acceptance_date", "reference_session", "label_end", "controls_asof"]] = [
        previous.acceptance_date, previous.reference_session, previous.label_end, previous.controls_through]
    index = frame.index[frame.observation_id.eq("SYNTHETIC-2022-0")][0]
    frame.loc[index, ["acceptance_date", "reference_session", "label_end", "controls_asof"]] = [
        first.acceptance_date, first.reference_session, first.label_end, first.controls_through]
    predictions = evaluate_ablations(frame, selection, load_protocol(), years=[2022])
    assert set(predictions.train_rows) == {143}


def test_ablation_selection_changes_require_a_new_freeze(ablation_development):
    _, selection = ablation_development
    changed = deepcopy(selection)
    changed["selected"]["length_only"]["alpha"] = 999
    with pytest.raises(ValueError, match="changed"):
        evaluate_ablations(extended_dataset(), changed, load_protocol(), years=[2022])
    with pytest.raises(ValueError, match="final evaluation years"):
        evaluate_ablations(extended_dataset(), selection, load_protocol(), years=[2021])


def test_ablation_reports_keep_all_primary_observations_and_selected_penalties(ablation_development):
    _, selection = ablation_development
    frame = extended_dataset()
    results = evaluate_ablations(frame, selection, load_protocol(), years=[2022])
    primary = results.loc[results.ablation == "length_only", [
        "observation_id", "year", "reference_session", "target"]].copy()
    primary["baseline_prediction"] = 0.0
    primary["text_prediction"] = 0.0
    report = compare_ablation_predictions(primary, results, selection, load_protocol())
    assert set(report["ablations"]) == set(ABLATION_FEATURES)
    assert report["primary_baseline_events"] == 12
    with pytest.raises(ValueError, match="match exactly"):
        compare_ablation_predictions(primary, results.iloc[1:], selection, load_protocol())
    changed = results.copy()
    changed.loc[0, "target"] += 0.1
    with pytest.raises(ValueError, match="outcomes"):
        compare_ablation_predictions(primary, changed, selection, load_protocol())


def delay_inputs():
    accepted = datetime(2021, 3, 1, 18, tzinfo=ZoneInfo("America/New_York"))
    first, last = event_window(accepted, delay=1), event_window(accepted, delay=5)
    sessions = calendar().sessions_in_range(control_sessions(first)[0], last.label_end).strftime("%Y-%m-%d").tolist()
    events = pd.DataFrame([{"observation_id": "SYNTHETIC-delay", "security_id": "SYNTHETIC-security",
                            "cik": "0000000001", "acceptance_timestamp": accepted.isoformat(),
                            "previous_text": "supply market risk", "current_text": "supply market risk demand",
                            # Poisonous existing values must never be reused.
                            "target": 999.0, "momentum_20": 999.0, "controls_asof": "2099-01-01"}])
    stock = pd.DataFrame({"security_id": "SYNTHETIC-security", "session": sessions,
                          "total_return": np.arange(len(sessions)) / 10000,
                          "terminal_event": False})
    market = pd.DataFrame({"session": sessions, "total_return": np.arange(len(sessions)) / 50000})
    snapshots = pd.DataFrame({"security_id": "SYNTHETIC-security", "session": sessions,
                              "market_cap_usd": 1e9 + np.arange(len(sessions)) * 10000,
                              "industry": "SYNTHETIC-sector", "industry_scheme": "SYNTHETIC-scheme"})
    availability = pd.DataFrame([
        {"observation_id": "SYNTHETIC-delay", "delay": delay,
         "availability_status": "verified", "public_available_at": "2021-03-01T19:00:00-05:00",
         "availability_evidence_id": f"SYNTHETIC-public-evidence-delay-{delay}"} for delay in (1, 2, 5)])
    return events, stock, market, snapshots, availability


def test_delays_rebuild_labels_and_controls_independently_from_source_returns():
    events, stock, market, snapshots, availability = delay_inputs()
    targets, controls = [], []
    for delay in (1, 2, 5):
        frame, exclusions, receipt = rebuild_delay_dataset(events, stock, market, snapshots,
                                                            delay, load_protocol(), availability=availability)
        assert exclusions.empty
        validate_delay_dataset(frame, delay, receipt, load_protocol())
        window = event_window(datetime.fromisoformat(events.acceptance_timestamp.iloc[0]), delay=delay)
        s = stock.set_index("session").loc[list(window.return_sessions), "total_return"]
        b = market.set_index("session").loc[list(window.return_sessions), "total_return"]
        expected = np.prod(1 + s) - np.prod(1 + b)
        history = stock.set_index("session").loc[list(control_sessions(window)), "total_return"]
        assert frame.target.iloc[0] == pytest.approx(expected)
        assert frame.momentum_20.iloc[0] == pytest.approx(np.prod(1 + history.iloc[-20:]) - 1)
        assert frame.controls_asof.iloc[0] == window.controls_through
        assert receipt["labels_rebuilt"] is receipt["controls_rebuilt"] is True
        targets.append(frame.target.iloc[0])
        controls.append(frame.momentum_20.iloc[0])
    assert len(set(targets)) == len(set(controls)) == 3


def test_one_session_delay_cannot_borrow_a_two_session_availability_proxy():
    events, stock, market, snapshots, availability = delay_inputs()
    availability.loc[availability.delay == 1, "public_available_at"] = "2021-03-02T12:00:00-05:00"
    frame, excluded, receipt = rebuild_delay_dataset(events, stock, market, snapshots, 1,
                                                     load_protocol(), availability=availability)
    assert frame.empty
    assert len(excluded) == 1
    assert "not before" in excluded.reason.iloc[0]
    assert receipt["included_events"] == 0
    later, excluded, receipt = rebuild_delay_dataset(events, stock, market, snapshots, 2,
                                                     load_protocol(), availability=availability)
    assert len(later) == 1 and excluded.empty


def test_delay_missing_returns_produce_visible_exclusions_and_no_filling():
    events, stock, market, snapshots, availability = delay_inputs()
    window = event_window(datetime.fromisoformat(events.acceptance_timestamp.iloc[0]), delay=5)
    stock = stock.loc[stock.session != window.return_sessions[-1]]
    frame, excluded, _ = rebuild_delay_dataset(events, stock, market, snapshots, 5,
                                               load_protocol(), availability=availability)
    assert frame.empty
    assert "Missing stock session" in excluded.reason.iloc[0]


def test_delay_availability_assumptions_are_counted_separately_from_verification():
    events, stock, market, snapshots, availability = delay_inputs()
    availability["availability_status"] = "documented_assumption"
    _, excluded, receipt = rebuild_delay_dataset(events, stock, market, snapshots, 1,
                                                 load_protocol(), availability=availability)
    assert excluded.empty
    assert receipt["availability_counts"] == {"documented_assumption": 1}


@pytest.mark.parametrize("mutation", ["target", "controls", "receipt"])
def test_delay_validation_rejects_shifted_or_stale_data(mutation):
    events, stock, market, snapshots, availability = delay_inputs()
    frame, _, receipt = rebuild_delay_dataset(events, stock, market, snapshots, 2,
                                               load_protocol(), availability=availability)
    if mutation == "target":
        frame.loc[0, "target"] += 0.01
    elif mutation == "controls":
        frame.loc[0, "controls_asof"] = frame.reference_session.iloc[0]
    else:
        receipt["controls_rebuilt"] = False
    with pytest.raises(ValueError, match="receipt|rebuild"):
        validate_delay_dataset(frame, 2, receipt, load_protocol())


def delay_comparison_inputs():
    events, stock, market, snapshots, availability = delay_inputs()
    datasets, receipts, predictions = {}, {}, {}
    for delay in (1, 2, 5):
        frame, _, receipt = rebuild_delay_dataset(events, stock, market, snapshots, delay,
                                                   load_protocol(), availability=availability)
        prediction = frame[["observation_id", "target", "reference_session"]].copy()
        prediction["year"] = 2021
        prediction["baseline_prediction"] = 0.0
        prediction["text_prediction"] = prediction.target / 2
        prediction["baseline_alpha"], prediction["text_alpha"] = 1.0, 10.0
        datasets[delay], receipts[delay], predictions[delay] = frame, receipt, prediction
    return predictions, datasets, receipts


def test_delay_comparison_retains_common_event_and_own_samples():
    predictions, datasets, receipts = delay_comparison_inputs()
    report = compare_delay_predictions(predictions, datasets, receipts, load_protocol())
    assert report["common_events"] == 1
    assert set(report["per_delay"]) == {"1", "2", "5"}
    assert all(row["incremental_r2"] == pytest.approx(0.75) for row in report["common_event_scores"].values())


def test_delay_comparison_refuses_different_penalties_or_shifted_predictions():
    predictions, datasets, receipts = delay_comparison_inputs()
    changed = {key: value.copy() for key, value in predictions.items()}
    changed[5]["text_alpha"] = 100.0
    with pytest.raises(ValueError, match="same|share"):
        compare_delay_predictions(changed, datasets, receipts, load_protocol())
    predictions[1]["target"] = predictions[2].target
    with pytest.raises(ValueError, match="rebuilt labels"):
        compare_delay_predictions(predictions, datasets, receipts, load_protocol())


def test_delay_comparison_cannot_silently_omit_a_rebuilt_same_year_event():
    predictions, datasets, receipts = delay_comparison_inputs()
    events, stock, market, snapshots, availability = delay_inputs()
    extra = events.copy()
    extra["observation_id"] = "SYNTHETIC-other-delay"
    events = pd.concat([events, extra], ignore_index=True)
    extra_availability = availability.copy()
    extra_availability["observation_id"] = "SYNTHETIC-other-delay"
    availability = pd.concat([availability, extra_availability], ignore_index=True)
    datasets[1], _, receipts[1] = rebuild_delay_dataset(events, stock, market, snapshots, 1,
                                                        load_protocol(), availability=availability)
    with pytest.raises(ValueError, match="every rebuilt event"):
        compare_delay_predictions(predictions, datasets, receipts, load_protocol())


def test_rebuilt_delay_models_fit_only_prior_mature_years_with_fixed_primary_penalties():
    sessions = calendar().sessions_in_range("2009-01-02", "2025-06-30").strftime("%Y-%m-%d").tolist()
    stock = pd.DataFrame({"security_id": "SYNTHETIC-security", "session": sessions,
                          "total_return": np.sin(np.arange(len(sessions)) / 10) / 100,
                          "terminal_event": False})
    market = pd.DataFrame({"session": sessions, "total_return": 0.0001})
    snapshots = pd.DataFrame({"security_id": "SYNTHETIC-security", "session": sessions,
                              "market_cap_usd": 1e9 + np.arange(len(sessions)) * 10000,
                              "industry": "SYNTHETIC-sector", "industry_scheme": "SYNTHETIC-scheme"})
    events, availability = [], []
    for year in range(2010, 2026):
        identity = f"SYNTHETIC-delay-fit-{year}"
        events.append({"observation_id": identity, "security_id": "SYNTHETIC-security",
                       "acceptance_timestamp": f"{year}-03-01T18:00:00-05:00",
                       "previous_text": "supply costs may increase", "current_text": "supply costs may increase demand"})
        availability.append({"observation_id": identity, "delay": 1, "availability_status": "verified",
                             "public_available_at": f"{year}-03-01T19:00:00-05:00",
                             "availability_evidence_id": f"SYNTHETIC-evidence-{year}"})
    frame, exclusions, receipt = rebuild_delay_dataset(pd.DataFrame(events), stock, market, snapshots,
                                                        1, load_protocol(), availability=pd.DataFrame(availability))
    assert exclusions.empty
    predictions = evaluate_delay_predictions(frame, 1, receipt, load_protocol(),
                                               baseline_alpha=1.0, text_alpha=10.0)
    assert predictions.year.tolist() == [2022, 2023, 2024, 2025]
    assert predictions.train_rows.tolist() == [12, 13, 14, 15]
    assert predictions.baseline_alpha.eq(1.0).all() and predictions.text_alpha.eq(10.0).all()
    with pytest.raises(ValueError, match="frozen development-grid"):
        evaluate_delay_predictions(frame, 1, receipt, load_protocol(), baseline_alpha=999.0, text_alpha=10.0)


def test_paragraph_insertion_does_not_mark_shifted_unchanged_paragraphs_as_moves():
    old = "Supply risks affect deliveries.\n\nCyber attacks threaten operations."
    new = "Regulatory changes create uncertainty.\n\n" + old
    result = describe_paragraph_changes(old, new)
    assert result["counts"] == {"unchanged": 2, "relocated_candidate": 0,
                                "rewording_candidate": 0, "removed_candidate": 0, "added_candidate": 1}
    assert result["forecast_features_created"] is False
    assert result["manual_review_status"] == "pending"


def test_paragraph_moves_rewordings_deletions_and_numeric_changes_remain_visible():
    old = "Supplier costs have risen 20 percent.\n\nCyber attacks threaten operations.\n\nFlood damage disrupts facilities."
    new = "Cyber attacks threaten operations.\n\nSupplier costs have risen 90 percent.\n\nGovernment permits may expire."
    result = describe_paragraph_changes(old, new)
    assert result["counts"]["unchanged"] == 1
    assert result["counts"]["rewording_candidate"] == 1
    assert result["counts"]["removed_candidate"] == 1
    assert result["counts"]["added_candidate"] == 1
    swapped = describe_paragraph_changes("Supply risk.\n\nCyber risk.", "Cyber risk.\n\nSupply risk.")
    assert swapped["counts"]["relocated_candidate"] == 1


def test_paragraph_duplicate_multiplicity_and_ambiguous_matches_are_preserved():
    repeated = describe_paragraph_changes("Supply risk.\n\nSupply risk.", "Supply risk.")
    assert repeated["counts"]["unchanged"] == 1
    assert repeated["counts"]["removed_candidate"] == 1
    ambiguous = describe_paragraph_changes("Supply costs rise.\n\nSupply costs fall.", "Supply costs change.")
    assert ambiguous["counts"]["rewording_candidate"] == 0
    assert ambiguous["counts"]["removed_candidate"] == 2
    assert ambiguous["counts"]["added_candidate"] == 1
