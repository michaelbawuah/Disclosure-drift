"""Explicit SEC timestamps and an exchange-session calendar, including holidays."""

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

NY = ZoneInfo("America/New_York")


@lru_cache(maxsize=8)
def calendar(start: str = "2008-01-01", end: str = "2028-12-31"):
    return xcals.get_calendar("XNYS", start=start, end=end)


def acceptance_from_header(raw: str) -> datetime:
    """EDGAR SGML acceptance values are exchange-local wall time."""
    import re
    match = re.search(r"<ACCEPTANCE-DATETIME>\s*(\d{14})", raw, re.I)
    if not match:
        raise ValueError("No SEC acceptance datetime in header")
    return datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=NY)


@dataclass(frozen=True)
class EventWindow:
    acceptance_date: str
    reference_session: str
    prediction_time_utc: str
    controls_through: str
    label_end: str
    return_sessions: tuple[str, ...]


def event_window(accepted: datetime, delay: int = 2, horizon: int = 20) -> EventWindow:
    if accepted.tzinfo is None:
        raise ValueError("Acceptance datetime must include an explicit timezone")
    if delay < 1 or horizon < 1:
        raise ValueError("Delay and horizon must be positive")
    local_date = pd.Timestamp(accepted.astimezone(NY).date())
    cal = calendar()
    sessions = cal.sessions
    # Session labels in exchange_calendars are timezone-naive calendar dates.
    if sessions.tz is not None:
        sessions = sessions.tz_localize(None)
    idx = sessions.searchsorted(local_date, side="right") + delay - 1
    if idx < 1 or idx + horizon >= len(sessions):
        raise ValueError("Event window is outside the configured calendar")
    def fmt(value):
        return value.date().isoformat()
    reference = sessions[idx]
    return EventWindow(
        local_date.date().isoformat(), fmt(reference),
        cal.session_open(reference).isoformat(), fmt(sessions[idx - 1]),
        fmt(sessions[idx + horizon]),
        tuple(fmt(x) for x in sessions[idx + 1:idx + horizon + 1]),
    )
