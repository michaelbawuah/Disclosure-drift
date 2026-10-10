"""Review helpers must catch wrong sources without changing a frozen selection."""

import io
from copy import deepcopy
from datetime import datetime

import pandas as pd
import pytest

from disclosure_research import review_followup as rf
from disclosure_research.audit import select_review_pairs
from disclosure_research.controls import control_sessions
from disclosure_research.pilot_audit import independent_trace
from disclosure_research.timing import NY, event_window


@pytest.fixture
def source_trace():
    window = event_window(datetime(2019, 3, 1, 12, tzinfo=NY))
    dates = [*control_sessions(window), window.reference_session, *window.return_sessions]
    daily = [{"source_record": i, "PERMNO": "123", "PERMCO": "456", "DlyCalDt": d,
              "DlyRet": "0.001", "vwretd": "0.002", "DlyCap": "250000", "DlyDelFlg": "N"}
             for i, d in enumerate(dates, 2)]
    names = [{"source_record": 2, "permno": "123", "permco": "456", "siccd": "1234",
              "secinfostartdt": dates[0], "secinfoenddt": dates[-1]}]
    trace = independent_trace(daily, {r["DlyCalDt"]: r for r in daily}, names, "123", window)
    return trace, "123", daily, names, window


def test_every_source_reference_checked_and_fourth_decimal_mutation_caught(source_trace):
    trace, *rest = source_trace
    assert sum(rf.check_trace_sources(trace, *rest).values()) == 102
    changed = deepcopy(trace)
    changed["controls"][0]["return"] = "0.0011"
    with pytest.raises(ValueError, match="Control source row differs"):
        rf.check_trace_sources(changed, *rest)


@pytest.mark.parametrize("field", ["stock", "benchmark", "snapshot"])
def test_incorrect_record_references_rejected(source_trace, field):
    trace, *rest = source_trace
    if field == "stock":
        trace["label_rows"][0]["source_record"] += 1
    elif field == "benchmark":
        trace["label_rows"][0]["benchmark_source_record"] += 1
    else:
        trace["snapshot"]["names_record"] = 99
    with pytest.raises(ValueError, match="source row differs|Invalid CSV record"):
        rf.check_trace_sources(trace, *rest)


def test_changed_frozen_pair_sample_rejected():
    pairs = pd.DataFrame([{"cik": "0000000001", "accession": f"0000000001-{year}-000001",
                           "previous_accession": f"0000000001-{year-1}-000001",
                           "acceptance_date": f"20{year}-03-01", "source_url": "https://www.sec.gov/current",
                           "previous_source_url": "https://www.sec.gov/previous"} for year in range(15, 19)])
    selected = select_review_pairs(pairs).to_csv(index=False).encode()
    assert len(rf.frozen_pairs(pairs, selected)) == 4
    changed = pd.read_csv(io.BytesIO(selected), dtype=str).iloc[1:].to_csv(index=False).encode()
    with pytest.raises(ValueError, match="Frozen filing-pair selection differs"):
        rf.frozen_pairs(pairs, changed)


def test_short_history_is_explicitly_synthetic_and_cannot_silently_pass(monkeypatch):
    case = rf.short_history_case()
    assert case["kind"] == "SYNTHETIC_FAULT_INJECTION"
    assert case["control_sessions_supplied"] == 59 and not case["real_small_cap_coverage"]
    monkeypatch.setattr(rf, "make_controls", lambda *args: {})
    with pytest.raises(ValueError, match="Incomplete control history was accepted"):
        rf.short_history_case()
