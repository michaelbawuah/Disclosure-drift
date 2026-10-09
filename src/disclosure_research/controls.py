"""Pre-event controls from normalized, historically dated inputs.

Arithmetic and timing checks do not certify a vendor's point-in-time history.
The snapshot adapter and its source dictionary still require independent review.
"""

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from .market_data import iso_dates, required_text, strings
from .timing import EventWindow, calendar


def control_sessions(window: EventWindow) -> tuple[str, ...]:
    """The exact 60 sessions ending at the close before prediction/entry day."""
    sessions = calendar().sessions.strftime("%Y-%m-%d").tolist()
    if window.reference_session not in sessions:
        raise ValueError("Reference date is not a configured exchange session")
    index = sessions.index(window.reference_session)
    if index < 60 or sessions[index - 1] != window.controls_through:
        raise ValueError("Controls must end at the immediately preceding session")
    return tuple(sessions[index - 60:index])


def make_controls(stock: pd.DataFrame, snapshots: pd.DataFrame, window: EventWindow) -> dict:
    """Calculate controls for one permanent security; never splice predecessors.

    ``snapshots`` requires security_id, session, market_cap_usd, industry and
    industry_scheme. The exact controls-day snapshot must exist. Neither current
    classifications nor forward-filled snapshots may replace missing history.
    """
    required = {"security_id", "session", "total_return", "terminal_event"}
    if stock.empty or required - set(stock.columns):
        raise ValueError("Controls require normalized daily security returns")
    strings(stock.security_id, "controls.security_id")
    if stock.security_id.nunique() != 1:
        raise ValueError("Controls require exactly one permanent security")
    security_id = stock.security_id.iloc[0]
    iso_dates(stock.session, "controls.session", sessions=True)
    expected = control_sessions(window)
    # Cut off rows BEFORE inspecting returns or terminal flags. Future outcomes
    # cannot change a control, including through a delisting-based exclusion.
    history = stock.loc[stock.session <= window.controls_through].copy()
    if history.session.duplicated().any():
        raise ValueError("Duplicate historical return sessions")
    if (history.terminal_event.isna().any() or
            not is_bool_dtype(history.terminal_event)):
        raise ValueError("Historical terminal_event requires explicit booleans")
    if history.terminal_event.any():
        raise ValueError("Security terminated before the controls snapshot")
    history = history.set_index("session")
    missing = set(expected) - set(history.index)
    if missing:
        raise ValueError(f"Missing control return sessions: {sorted(missing)}")
    values = history.loc[list(expected), "total_return"]
    if (not is_numeric_dtype(values) or is_bool_dtype(values) or
            not np.isfinite(values.to_numpy(dtype=float)).all() or (values < -1).any()):
        raise ValueError("Control returns must be numeric, finite and at least -1")

    required = {"security_id", "session", "market_cap_usd", "industry", "industry_scheme"}
    if snapshots.empty or required - set(snapshots.columns):
        raise ValueError("Controls require a dated market-cap and industry snapshot")
    strings(snapshots.security_id, "snapshots.security_id")
    iso_dates(snapshots.session, "snapshots.session", sessions=True)
    snapshot = snapshots.loc[(snapshots.security_id == security_id) &
                             (snapshots.session == window.controls_through)]
    if len(snapshot) != 1:
        raise ValueError("Missing or ambiguous exact-date security snapshot")
    cap = snapshot.market_cap_usd
    if (not is_numeric_dtype(cap) or is_bool_dtype(cap) or
            not np.isfinite(cap.to_numpy(dtype=float)).all() or (cap <= 0).any()):
        raise ValueError("Historical market_cap_usd must be numeric, finite and positive")
    row = snapshot.iloc[0]
    required_text(row.industry, "Historical industry")
    required_text(row.industry_scheme, "Historical industry scheme")
    returns = values.to_numpy(dtype=float)
    with np.errstate(over="ignore", invalid="ignore"):
        numeric = {
            "momentum_20": float(np.prod(1 + returns[-20:]) - 1),
            "momentum_60": float(np.prod(1 + returns) - 1),
            "volatility_20": float(np.std(returns[-20:], ddof=1)),
            "log_market_cap": float(np.log(cap.iloc[0])),
        }
    if not np.isfinite(list(numeric.values())).all():
        raise ValueError("Control calculation overflowed; verify source units")
    return {**numeric, "industry": row.industry, "industry_scheme": row.industry_scheme,
            "security_id": security_id, "controls_asof": window.controls_through,
            "control_history_start": expected[0], "control_history_sessions": 60}
