"""Labels from an explicit normalized return contract, never from current tickers."""

import numpy as np
import pandas as pd

from .timing import EventWindow


def combine_legacy_return(ret: float, dlret: float | None) -> float:
    """For legacy separate fields ONLY. Modern combined returns must not use this."""
    if not np.isfinite(ret) or ret < -1:
        raise ValueError("Missing/invalid ordinary return")
    if dlret is None:
        return float(ret)
    if not np.isfinite(dlret) or dlret < -1:
        raise ValueError("Missing/invalid delisting return")
    return float((1 + ret) * (1 + dlret) - 1)


def _returns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["session"] = pd.to_datetime(frame["session"]).dt.strftime("%Y-%m-%d")
    if frame["session"].duplicated().any():
        raise ValueError("Duplicate return sessions")
    values = frame["total_return"].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < -1).any():
        raise ValueError("Returns must be finite and at least -1; missing is not zero")
    if "terminal_event" in frame and not frame["terminal_event"].isin([True, False, 0, 1]).all():
        raise ValueError("terminal_event must contain explicit boolean values")
    return frame.set_index("session").sort_index()


def make_label(stock: pd.DataFrame, benchmark: pd.DataFrame, window: EventWindow) -> dict:
    """Returns include corporate actions/delisting exactly once upstream."""
    stock, benchmark = _returns(stock), _returns(benchmark)
    if "terminal_event" not in stock:
        raise ValueError("Stock contract requires terminal_event, including explicit False")
    terminal_dates = stock.index[stock["terminal_event"].astype(bool)].tolist()
    if len(terminal_dates) > 1:
        raise ValueError("More than one terminal event for a security")
    terminal = terminal_dates[0] if terminal_dates else None
    if terminal and terminal <= window.reference_session:
        raise ValueError("Security terminated before an entry at the reference close")
    if window.reference_session not in stock.index:
        raise ValueError("Missing reference-session record; cannot establish entry")
    stock_values, market_values = [], []
    for session in window.return_sessions:
        if session not in benchmark.index:
            raise ValueError(f"Missing benchmark session {session}")
        market_values.append(float(benchmark.loc[session, "total_return"]))
        if terminal and session > terminal:
            if session in stock.index:
                raise ValueError("Security observations continue after a terminal event")
            stock_values.append(0.0)
        elif session not in stock.index:
            raise ValueError(f"Missing stock session {session} before terminal event")
        else:
            stock_values.append(float(stock.loc[session, "total_return"]))
    stock_return = float(np.prod(1 + np.array(stock_values)) - 1)
    market_return = float(np.prod(1 + np.array(market_values)) - 1)
    return {"reference_session": window.reference_session, "label_end": window.label_end,
            "stock_return": stock_return, "market_return": market_return,
            "target": stock_return - market_return, "horizon_sessions": len(stock_values)}


def resolve_security(links: pd.DataFrame, cik: str, session: str) -> str:
    cik = str(int(cik)).zfill(10)
    ids = links["cik"].map(lambda x: str(int(x)).zfill(10))
    at = pd.Timestamp(session)
    start = pd.to_datetime(links["valid_from"])
    end = pd.to_datetime(links["valid_to"])
    hits = links.loc[(ids == cik) & (start <= at) & (end >= at), "security_id"].unique()
    if len(hits) != 1:
        raise ValueError("Historical security identity is missing or ambiguous")
    return str(hits[0])
