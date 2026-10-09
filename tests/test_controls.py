from datetime import datetime
from math import log, sqrt

import numpy as np
import pandas as pd
import pytest

from disclosure_research.controls import control_sessions, make_controls
from disclosure_research.timing import NY, event_window


@pytest.fixture
def inputs():
    window = event_window(datetime(2021, 7, 2, 18, 30, tzinfo=NY))
    sessions = control_sessions(window)
    stock = pd.DataFrame({"security_id": "INVENTED-1", "session": sessions,
                          "total_return": [.02] * 40 + [.01, -.01] * 10,
                          "terminal_event": False})
    snapshots = pd.DataFrame([{"security_id": "INVENTED-1", "session": "2021-07-06",
                               "market_cap_usd": 1e9, "industry": "invented-sector",
                               "industry_scheme": "invented-scheme"}])
    return stock, snapshots, window


def test_independent_arithmetic_and_holiday_window(inputs):
    stock, snapshots, window = inputs
    result = make_controls(stock, snapshots, window)
    assert window.reference_session == "2021-07-07"
    assert result["controls_asof"] == "2021-07-06"
    assert result["control_history_sessions"] == 60
    assert "2021-07-05" not in control_sessions(window)
    assert result["momentum_20"] == pytest.approx(.9999 ** 10 - 1)
    assert result["momentum_60"] == pytest.approx(1.02 ** 40 * .9999 ** 10 - 1)
    assert result["volatility_20"] == pytest.approx(sqrt(.002 / 19))
    assert result["log_market_cap"] == pytest.approx(log(1e9))


def test_future_returns_delisting_and_industry_cannot_change_controls(inputs):
    stock, snapshots, window = inputs
    expected = make_controls(stock, snapshots, window)
    future = stock.iloc[[-1]].assign(session="2021-07-07", total_return=np.nan, terminal_event=True)
    future_snapshot = snapshots.assign(session="2021-07-07", market_cap_usd=-99,
                                       industry="future-industry")
    assert make_controls(pd.concat([stock, future]), pd.concat([snapshots, future_snapshot]),
                         window) == expected


@pytest.mark.parametrize("case,pattern", [
    ("missing", "Missing control return"), ("duplicate", "Duplicate"),
    ("nan", "finite"), ("invalid_return", "at least -1"), ("terminal", "terminated"),
    ("two_securities", "one permanent security"), ("overflow", "overflowed"),
])
def test_control_history_cannot_be_filled_or_spliced(inputs, case, pattern):
    stock, snapshots, window = inputs
    if case == "missing":
        stock = stock.drop(2)
    elif case == "duplicate":
        stock = pd.concat([stock, stock.iloc[[0]]])
    elif case == "nan":
        stock.loc[2, "total_return"] = np.nan
    elif case == "invalid_return":
        stock.loc[2, "total_return"] = -1.1
    elif case == "terminal":
        stock.loc[2, "terminal_event"] = True
    elif case == "two_securities":
        stock.loc[2, "security_id"] = "PREDECESSOR"
    elif case == "overflow":
        stock["total_return"] = 1e100
    with pytest.raises(ValueError, match=pattern):
        make_controls(stock, snapshots, window)


@pytest.mark.parametrize("case,pattern", [
    ("stale", "exact-date"), ("future", "exact-date"), ("other_id", "exact-date"),
    ("duplicate", "exact-date"), ("zero_cap", "positive"), ("missing_cap", "finite"),
    ("boolean_cap", "numeric"), ("missing_industry", "industry"),
    ("missing_scheme", "scheme"),
])
def test_snapshot_must_be_historical_exact_and_usable(inputs, case, pattern):
    stock, snapshots, window = inputs
    if case == "duplicate":
        snapshots = pd.concat([snapshots, snapshots])
    elif case == "boolean_cap":
        snapshots["market_cap_usd"] = True
    else:
        column, value = {
            "stale": ("session", "2021-07-02"), "future": ("session", "2021-07-07"),
            "other_id": ("security_id", "DIFFERENT"), "zero_cap": ("market_cap_usd", 0),
            "missing_cap": ("market_cap_usd", np.nan), "missing_industry": ("industry", ""),
            "missing_scheme": ("industry_scheme", ""),
        }[case]
        snapshots.loc[0, column] = value
    with pytest.raises(ValueError, match=pattern):
        make_controls(stock, snapshots, window)
