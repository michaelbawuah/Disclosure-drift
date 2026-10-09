"""Paired forecast comparison with contiguous month-block resampling."""

import numpy as np
import pandas as pd


def incremental_r2(y, baseline, augmented) -> float:
    y, baseline, augmented = [np.asarray(x, dtype=float) for x in (y, baseline, augmented)]
    if y.ndim != 1 or not (y.shape == baseline.shape == augmented.shape) or len(y) == 0:
        raise ValueError("Prediction arrays must be aligned, nonempty one-dimensional arrays")
    if not all(np.isfinite(x).all() for x in (y, baseline, augmented)):
        raise ValueError("Nonfinite outcomes/predictions")
    denominator = np.sum((y - baseline) ** 2)
    if denominator <= 0:
        raise ValueError("Baseline SSE is zero; incremental R-squared is undefined")
    return float(1 - np.sum((y - augmented) ** 2) / denominator)


def block_interval(predictions: pd.DataFrame, months: int = 3, draws: int = 2000,
                   seed: int = 20261009) -> dict:
    if months < 1 or draws < 100:
        raise ValueError("Use positive block length and at least 100 draws")
    required = ["target", "baseline_prediction", "text_prediction", "reference_session"]
    if any(c not in predictions for c in required):
        raise ValueError("Prediction table is incomplete")
    frame = predictions.copy()
    frame["month"] = pd.to_datetime(frame["reference_session"]).dt.to_period("M")
    all_months = pd.period_range(frame.month.min(), frame.month.max(), freq="M")
    if len(all_months) < 2 * months:
        raise ValueError("Too few calendar months for the requested block length")
    # Both models share exactly the same sampled observations. Empty months stay in time.
    baseline_sse = ((frame.target - frame.baseline_prediction) ** 2).groupby(frame.month).sum()
    text_sse = ((frame.target - frame.text_prediction) ** 2).groupby(frame.month).sum()
    baseline_sse = baseline_sse.reindex(all_months, fill_value=0).to_numpy()
    text_sse = text_sse.reindex(all_months, fill_value=0).to_numpy()
    point = incremental_r2(frame.target, frame.baseline_prediction, frame.text_prediction)
    rng = np.random.default_rng(seed)
    sampled = []
    for _ in range(draws):
        starts = rng.integers(0, len(all_months) - months + 1,
                              size=int(np.ceil(len(all_months) / months)))
        indices = np.concatenate([np.arange(start, start + months) for start in starts])[:len(all_months)]
        denominator = baseline_sse[indices].sum()
        if denominator > 0:
            sampled.append(1 - text_sse[indices].sum() / denominator)
    if len(sampled) < 0.95 * draws:
        raise ValueError("Too many undefined bootstrap draws; interval is unreliable")
    lower, upper = np.quantile(sampled, [0.025, 0.975])
    return {"incremental_r2": point, "lower_95": float(lower), "upper_95": float(upper),
            "block_months": months, "calendar_months": len(all_months),
            "draws": draws, "valid_draws": len(sampled), "seed": seed,
            "method": "moving_month_blocks_percentile; conditional_on_frozen_predictions"}
