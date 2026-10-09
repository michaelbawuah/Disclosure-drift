import json

import pandas as pd
import pytest

from disclosure_research.export_plan import build_export_plan
from disclosure_research.market_data import sha256
from disclosure_research.protocol import load_protocol


@pytest.fixture
def events(tmp_path):
    path = tmp_path / "events.parquet"
    pd.DataFrame([{"event_id": "invented-accession-for-test", "cik": "0000000001",
                   "previous_accession": "invented-prior-accession-for-test",
                   "acceptance_timestamp": "2021-07-02T18:30:00-04:00",
                   "data_kind": "REAL_FILING_EVENTS", "current_evidence_id": "1" * 64,
                   "previous_evidence_id": "2" * 64, "filing_source_table_sha256": "3" * 64}]
                 ).to_parquet(path, index=False)
    return path


def test_request_uses_exact_pre_prediction_and_label_sessions(events, tmp_path):
    output = tmp_path / "request"
    summary = build_export_plan(events, output, load_protocol())
    row = pd.read_csv(output / "event_windows.csv").iloc[0]
    assert row.controls_asof == "2021-07-06"
    assert row.reference_session == "2021-07-07"
    assert row.label_start == "2021-07-08"
    assert row.label_end == "2021-08-04"
    assert row.control_history_start < row.momentum_20_start < row.controls_asof
    assert summary["events_sha256"] == sha256(events.read_bytes())
    assert not summary["market_returns_loaded"] and not summary["final_period_opened"]
    assert summary["human_reviews_completed_by_this_command"] == 0
    assert summary == json.loads((output / "export_plan.json").read_text())
    trace = pd.read_csv(output / "trace_reviews.template.csv")
    assert trace.label_review.tolist() == ["pending"]
    with pytest.raises(ValueError, match="already exists"):
        build_export_plan(events, output, load_protocol())


@pytest.mark.parametrize("column,value,pattern", [
    ("acceptance_timestamp", "2022-01-03T10:00:00-05:00", "holdout"),
    ("data_kind", "SYNTHETIC_ENGINEERING_FIXTURE", "real development"),
    ("current_evidence_id", "unbound", "provenance"),
    ("previous_accession", "", "previous accession"),
])
def test_no_request_published_for_holdout_or_unbound_events(events, tmp_path, column, value, pattern):
    frame = pd.read_parquet(events)
    frame[column] = value
    frame.to_parquet(events, index=False)
    output = tmp_path / "invalid-request"
    with pytest.raises(ValueError, match=pattern):
        build_export_plan(events, output, load_protocol())
    assert not output.exists()


def test_trace_selection_does_not_depend_on_input_order(events, tmp_path):
    frame = pd.read_parquet(events)
    rows = pd.concat([frame.assign(event_id=f"event-{i}") for i in range(25)], ignore_index=True)
    rows.to_parquet(events, index=False)
    build_export_plan(events, tmp_path / "first", load_protocol())
    rows.iloc[::-1].to_parquet(events, index=False)
    build_export_plan(events, tmp_path / "second", load_protocol())
    first = pd.read_csv(tmp_path / "first/trace_reviews.template.csv")
    second = pd.read_csv(tmp_path / "second/trace_reviews.template.csv")
    assert len(first) == 20
    pd.testing.assert_frame_equal(first, second)
