import json
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from disclosure_research.cli import main, synthetic_dataset
from disclosure_research.evaluation import block_interval, incremental_r2
from disclosure_research.features import TextChangeFeatures
from disclosure_research.market import combine_legacy_return, make_label, resolve_security
from disclosure_research.modeling import development_comparison, validate_dataset
from disclosure_research.protocol import eligible_training, load_protocol, verify_lock, write_lock
from disclosure_research.timing import acceptance_from_header, event_window


def test_friday_evening_and_monday_holiday():
    window = event_window(datetime(2021, 7, 2, 18, 30, tzinfo=ZoneInfo("America/New_York")))
    assert window.reference_session == "2021-07-07"  # July 5 is an observed exchange holiday.
    assert window.controls_through == "2021-07-06"
    assert len(window.return_sessions) == 20
    assert window.return_sessions[0] == "2021-07-08"
    assert window.return_sessions[-1] == window.label_end


def test_utc_acceptance_uses_new_york_date():
    window = event_window(datetime.fromisoformat("2021-07-03T01:00:00+00:00"))
    assert window.acceptance_date == "2021-07-02"
    assert window.reference_session == "2021-07-07"


def test_early_close_does_not_shift_session_count():
    window = event_window(datetime(2021, 11, 24, 18, tzinfo=ZoneInfo("America/New_York")))
    assert window.reference_session == "2021-11-29"
    assert window.controls_through == "2021-11-26"


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        event_window(datetime(2021, 3, 1))


def test_header_timestamp_is_explicit_eastern():
    accepted = acceptance_from_header("<ACCEPTANCE-DATETIME>20210702183000\n")
    assert accepted.isoformat() == "2021-07-02T18:30:00-04:00"


def return_fixtures():
    window = event_window(datetime(2021, 3, 1, 18, tzinfo=ZoneInfo("America/New_York")))
    dates = [window.reference_session, *window.return_sessions]
    stock = pd.DataFrame({"session": dates, "total_return": [0.9] + [0.01] * 20,
                          "terminal_event": [False] * 21})
    market = pd.DataFrame({"session": dates, "total_return": [0.8] + [0.002] * 20})
    return window, stock, market


def test_label_excludes_reference_day_and_compounds_exactly_twenty_returns():
    window, stock, market = return_fixtures()
    result = make_label(stock, market, window)
    assert result["stock_return"] == pytest.approx(1.01 ** 20 - 1)
    assert result["market_return"] == pytest.approx(1.002 ** 20 - 1)
    assert result["target"] == pytest.approx(1.01 ** 20 - 1.002 ** 20)


def test_delisting_is_included_then_proceeds_stay_in_cash():
    window, stock, market = return_fixtures()
    stock = stock.iloc[:4].copy()
    stock.loc[3, ["total_return", "terminal_event"]] = [-0.5, True]
    result = make_label(stock, market, window)
    assert result["stock_return"] == pytest.approx(1.01 ** 2 * 0.5 - 1)


def test_missing_prices_are_not_zero_returns():
    window, stock, market = return_fixtures()
    with pytest.raises(ValueError, match="Missing stock"):
        make_label(stock.drop(index=3), market, window)


def test_post_delisting_records_are_rejected():
    window, stock, market = return_fixtures()
    stock.loc[3, "terminal_event"] = True
    with pytest.raises(ValueError, match="continue"):
        make_label(stock, market, window)


def test_legacy_return_combination_includes_cross_term():
    assert combine_legacy_return(0.1, -0.5) == pytest.approx(-0.45)
    with pytest.raises(ValueError):
        combine_legacy_return(0.1, float("nan"))


def test_link_mapping_respects_historical_validity_and_rejects_overlap():
    links = pd.DataFrame([
        {"cik": "123", "security_id": "old", "valid_from": "2010-01-01", "valid_to": "2018-12-31"},
        {"cik": "123", "security_id": "new", "valid_from": "2019-01-01", "valid_to": "2026-12-31"},
    ])
    assert resolve_security(links, "123", "2017-01-01") == "old"
    assert resolve_security(links, "123", "2021-01-01") == "new"
    links.loc[0, "valid_to"] = "2022-01-01"
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_security(links, "123", "2021-01-01")


def test_training_labels_must_mature_before_prediction():
    data = pd.DataFrame({"acceptance_date": ["2021-12-01", "2021-12-20", "2022-01-01"],
                         "label_end": ["2021-12-31", "2022-01-20", "2022-02-01"]})
    selected = eligible_training(data, 2022, "2022-01-05")
    assert selected.index.tolist() == [0]


def test_future_documents_cannot_change_earlier_features_or_training_vocabulary():
    train = pd.DataFrame({"previous_text": ["supply risk demand"],
                          "current_text": ["supply risk pricing"]})
    future = pd.DataFrame({"previous_text": ["quantum unicorn"],
                           "current_text": ["quantum unicorn dragons"]})
    model = TextChangeFeatures().fit(train)
    before = model.transform(train)
    model.transform(future)
    pd.testing.assert_frame_equal(before, model.transform(train))
    assert "quantum" not in model.vectorizer.vocabulary_


def test_unchanged_text_has_zero_distance():
    pairs = pd.DataFrame({"previous_text": ["risk supply competition"],
                          "current_text": ["risk supply competition"]})
    values = TextChangeFeatures().fit(pairs).transform(pairs)
    np.testing.assert_allclose(values.to_numpy(), 0, atol=1e-12)


def test_empty_disclosures_are_not_imputed_as_no_change():
    pairs = pd.DataFrame({"previous_text": [""], "current_text": ["risk supply"]})
    with pytest.raises(ValueError, match="Empty"):
        TextChangeFeatures().fit(pairs)


def test_unknown_vocabulary_has_undefined_cosine_instead_of_invented_distance():
    train = pd.DataFrame({"previous_text": ["supply risk"], "current_text": ["risk demand"]})
    unknown = pd.DataFrame({"previous_text": ["unicorn dragons"], "current_text": ["unicorn dragons"]})
    result = TextChangeFeatures().fit(train).transform(unknown)
    assert np.isnan(result.iloc[0].tfidf_cosine_distance)
    assert result.iloc[0].jaccard_distance == 0
    assert result.attrs["zero_vocabulary_pairs"] == 1


def test_protocol_tampering_is_detected(tmp_path):
    config = load_protocol()
    path = tmp_path / "lock.json"
    write_lock(config, path)
    verify_lock(config, path)
    config["ridge_alphas"] = [999]
    with pytest.raises(ValueError, match="changed"):
        verify_lock(config, path)


def test_final_years_are_rejected_by_development_runner():
    frame = synthetic_dataset()
    frame.loc[0, "acceptance_date"] = "2022-01-01"
    with pytest.raises(ValueError, match="blocked"):
        development_comparison(frame, load_protocol())


def test_future_controls_are_rejected():
    frame = synthetic_dataset()
    frame.loc[0, "controls_asof"] = frame.loc[0, "reference_session"]
    with pytest.raises(ValueError, match="future-dated"):
        validate_dataset(frame)


def test_incremental_score_uses_paired_observations():
    assert incremental_r2([1, 2], [0, 0], [1, 2]) == 1
    assert incremental_r2([1, 2], [0, 0], [0, 0]) == 0
    with pytest.raises(ValueError):
        incremental_r2([1], [0, 0], [1])


def test_month_blocks_are_deterministic_and_resample_both_models_together():
    sessions = pd.date_range("2018-01-01", periods=48, freq="MS")
    frame = pd.DataFrame({"reference_session": sessions, "target": np.arange(1, 49),
                          "baseline_prediction": 0, "text_prediction": 0})
    first = block_interval(frame, draws=200)
    assert first == block_interval(frame, draws=200)
    assert first["lower_95"] == first["upper_95"] == 0


def test_final_cli_remains_closed(capsys):
    assert main(["evaluate-final"]) == 2
    assert "blocked" in capsys.readouterr().out


def test_synthetic_end_to_end_runs_declared_development_grid(tmp_path):
    assert main(["demo", "--output", str(tmp_path)]) == 0
    summary = json.loads((tmp_path / "selection.json").read_text())
    assert summary["data_kind"] == "SYNTHETIC_ENGINEERING_FIXTURE"
    assert summary["configurations"] == 8
    predictions = pd.read_parquet(tmp_path / "development_predictions.parquet")
    assert set(predictions.year) == set(range(2016, 2022))
    assert predictions.groupby(["model", "alpha"]).size().nunique() == 1
