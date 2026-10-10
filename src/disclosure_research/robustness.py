"""Prespecified secondary diagnostics without changing the primary comparison.

These are in-memory research components. The final-run orchestrator must validate
its frozen manifest before supplying final-period data. No function in this module
loads a dataset, unlocks a holdout, or turns a source declaration into verified fact.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .controls import make_controls
from .evaluation import block_interval
from .features import FEATURE_NAMES, TextChangeFeatures
from .market import make_label
from .modeling import NUMERIC_CONTROLS, validate_dataset
from .protocol import canonical_hash, eligible_training, guard_development
from .timing import calendar, event_window


# Every nonempty proper subset is declared in advance. The primary all-three
# model remains in modeling.py; these six comparisons never choose that model.
ABLATION_FEATURES = {
    "length_only": ["log_length_change"],
    "jaccard_only": ["jaccard_distance"],
    "tfidf_only": ["tfidf_cosine_distance"],
    "length_jaccard": ["log_length_change", "jaccard_distance"],
    "length_tfidf": ["log_length_change", "tfidf_cosine_distance"],
    "jaccard_tfidf": ["jaccard_distance", "tfidf_cosine_distance"],
}


def _paired(predictions: pd.DataFrame) -> pd.DataFrame:
    required = {"observation_id", "year", "reference_session", "target",
                "baseline_prediction", "text_prediction"}
    if predictions.empty or required - set(predictions.columns):
        raise ValueError("Nonempty paired predictions with acceptance year are required")
    frame = predictions.copy()
    if frame[list(required)].isna().any().any() or frame.observation_id.duplicated().any():
        raise ValueError("Prediction identities and required values must be complete and unique")
    for name in ("year", "target", "baseline_prediction", "text_prediction"):
        if not is_numeric_dtype(frame[name]) or is_bool_dtype(frame[name]):
            raise ValueError("Paired years, outcomes and predictions must be numeric without coercion")
    values = frame[["target", "baseline_prediction", "text_prediction"]].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Paired outcomes and predictions must be finite")
    with np.errstate(over="ignore", invalid="ignore"):
        errors = np.square(values[:, :1] - values[:, 1:])
    if not np.isfinite(errors).all() or not np.isfinite(errors.sum(axis=0)).all():
        raise ValueError("Squared prediction errors overflow; verify source units and model output")
    years = pd.to_numeric(frame.year, errors="raise")
    if not np.isfinite(years).all() or not np.equal(years, np.floor(years)).all():
        raise ValueError("Prediction year must be the integer acceptance year")
    frame["year"] = years.astype(int)
    sessions = pd.to_datetime(frame.reference_session, errors="raise")
    if sessions.isna().any():
        raise ValueError("Reference sessions cannot be missing")
    frame["reference_session"] = sessions.dt.strftime("%Y-%m-%d")
    frame["month"] = sessions.dt.to_period("M").astype(str)
    return frame


def _score(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"observations": 0, "baseline_sse": None, "text_sse": None,
                "baseline_mse": None, "text_mse": None, "incremental_r2": None,
                "status": "no_observations"}
    baseline = float(np.square(frame.target - frame.baseline_prediction).sum())
    text = float(np.square(frame.target - frame.text_prediction).sum())
    return {"observations": len(frame), "baseline_sse": baseline, "text_sse": text,
            "baseline_mse": baseline / len(frame), "text_mse": text / len(frame),
            "incremental_r2": float(1 - text / baseline) if baseline > 0 else None,
            "status": "ok" if baseline > 0 else "undefined_zero_baseline_sse"}


def _rank_correlation(group: pd.DataFrame, column: str, minimum: int) -> tuple[float | None, str]:
    if len(group) < minimum:
        return None, "insufficient_observations"
    if group.target.nunique() < 2:
        return None, "constant_target"
    if group[column].nunique() < 2:
        return None, "constant_prediction"
    correlation = group.target.rank(method="average").corr(group[column].rank(method="average"))
    return float(correlation), "ok"


def prediction_diagnostics(predictions: pd.DataFrame, config: dict, *,
                           minimum_month_observations: int = 3) -> dict:
    """Annual, monthly, year-omission and paired block-bootstrap diagnostics.

``year`` is the acceptance year, including when a late-December event's reference
session is in January. Rank groups and bootstrap blocks use reference months.
Year omission reuses frozen predictions; it is not nonchronological retraining.
"""
    if (isinstance(minimum_month_observations, bool) or not isinstance(minimum_month_observations, int)
            or minimum_month_observations < 3):
        raise ValueError("Prespecified monthly rank groups require at least three observations")
    frame = _paired(predictions)
    years = sorted(frame.year.unique().tolist())
    annual = [{"year": int(year), **_score(frame.loc[frame.year == year])} for year in years]
    omitted = [{"omitted_year": int(year), **_score(frame.loc[frame.year != year])}
               for year in years]
    monthly = []
    for month, group in frame.groupby("month", sort=True):
        baseline, baseline_status = _rank_correlation(group, "baseline_prediction", minimum_month_observations)
        text, text_status = _rank_correlation(group, "text_prediction", minimum_month_observations)
        monthly.append({"reference_month": month, "observations": len(group),
                        "baseline_spearman": baseline, "text_spearman": text,
                        "baseline_status": baseline_status, "text_status": text_status,
                        "delta_spearman": text - baseline
                        if baseline is not None and text is not None else None})
    intervals = []
    for months in (config["bootstrap_months"], config["bootstrap_sensitivity_months"]):
        try:
            interval = block_interval(frame, months=months, draws=config["bootstrap_draws"],
                                      seed=config["seed"])
            interval["status"] = "ok"
        except ValueError as exc:
            # Small/degenerate subgroup samples are reportable failures, never
            # reasons to silently shorten the prespecified block length.
            interval = {"status": "unavailable", "reason": str(exc), "block_months": months,
                        "draws": config["bootstrap_draws"], "seed": config["seed"]}
        intervals.append(interval)
    return {"pooled": _score(frame), "annual_scores": annual,
            "monthly_rank_correlation": monthly,
            "minimum_month_observations": minimum_month_observations,
            "leave_one_year_out": omitted, "bootstrap": intervals,
            "year_omission_method": "omit_acceptance_year_from_frozen_predictions_without_refitting",
            "interpretation": "secondary diagnostics; no model selection from final outcomes; "
                              "intervals are approximate and conditional on frozen predictions"}


def subgroup_diagnostics(predictions: pd.DataFrame, covariates: pd.DataFrame, *,
                         size_cutpoints_usd: list[float], industry_scheme: str) -> dict:
    """Describe size and dated-industry groups using cutpoints frozen in development.

The caller freezes the cutpoints and their rationale in the secondary manifest.
They are absolute USD thresholds, not ranks recomputed from a final year's firms.
Covariates must cover exactly the scored observations and use the prior close.
"""
    frame = _paired(predictions)
    required = {"observation_id", "controls_asof", "log_market_cap", "industry", "industry_scheme"}
    if required - set(covariates.columns) or covariates.observation_id.duplicated().any():
        raise ValueError("Unique, dated size and industry covariates are required")
    if set(covariates.observation_id) != set(frame.observation_id):
        raise ValueError("Subgroup covariates must match every scored observation exactly")
    if not isinstance(industry_scheme, str) or not industry_scheme.strip():
        raise ValueError("A frozen historical industry scheme is required")
    if covariates[list(required)].isna().any().any():
        raise ValueError("Subgroup covariates cannot be missing")
    if not covariates.industry_scheme.eq(industry_scheme).all():
        raise ValueError("Historical industry schemes do not match the frozen declaration")
    cuts = np.asarray(size_cutpoints_usd, dtype=float)
    if (cuts.ndim != 1 or len(cuts) == 0 or not np.isfinite(cuts).all() or
            (cuts <= 0).any() or (np.diff(cuts) <= 0).any()):
        raise ValueError("Size cutpoints must be finite, positive, strictly increasing USD values")
    frame = frame.drop(columns=list((required - {"observation_id"}) & set(frame.columns)))
    frame = frame.merge(covariates[list(required)], on="observation_id", validate="one_to_one")
    log_cap = frame.log_market_cap.to_numpy(dtype=float)
    if not np.isfinite(log_cap).all():
        raise ValueError("Historical logged capitalization must be finite")
    if frame.industry.astype(str).str.strip().eq("").any():
        raise ValueError("Historical industry must be explicit")
    reference = pd.to_datetime(frame.reference_session)
    controls = pd.to_datetime(frame.controls_asof)
    previous_sessions = [calendar().previous_session(session).strftime("%Y-%m-%d") for session in reference]
    if controls.dt.strftime("%Y-%m-%d").tolist() != previous_sessions:
        raise ValueError("Subgroup covariates must use the exact prior exchange close")
    frame["size_bin"] = np.searchsorted(np.log(cuts), log_cap, side="right")
    sizes = []
    for index in range(len(cuts) + 1):
        sizes.append({"size_bin": index,
                      "lower_usd_inclusive": float(cuts[index - 1]) if index else 0.0,
                      "upper_usd_exclusive": float(cuts[index]) if index < len(cuts) else None,
                      **_score(frame.loc[frame.size_bin == index])})
    industries = [{"industry": str(industry), **_score(group)}
                  for industry, group in frame.groupby("industry", sort=True)]
    return {"size_cutpoints_usd": cuts.tolist(), "industry_scheme": industry_scheme,
            "size_scores": sizes, "industry_scores": industries,
            "interpretation": "descriptive frozen subgroups; no inference from tiny groups; "
                              "size cutpoints must be fixed before final outcomes are opened"}


def failure_cases(predictions: pd.DataFrame, filings: pd.DataFrame, *, limit: int = 10) -> list[dict]:
    """Source-linked examples where text adds the most squared error.

This is outcome-selected interpretation after a frozen run, never a new exclusion
rule or a claim of representative extraction error. The caller controls whether
licensed outcome-derived values may be published.
"""
    frame = _paired(predictions)
    if limit < 1:
        raise ValueError("Failure example limit must be positive")
    # The prepared dataset uses source_url; explicitly accept that canonical
    # current-filing name while keeping paired output labels unambiguous.
    if "current_source_url" not in filings and "source_url" in filings:
        filings = filings.rename(columns={"source_url": "current_source_url"})
    columns = ["observation_id", "current_source_url", "previous_source_url"]
    if set(columns) - set(filings.columns) or filings.observation_id.duplicated().any():
        raise ValueError("Unique current and previous filing source links are required")
    if set(frame.observation_id) - set(filings.observation_id):
        raise ValueError("Every scored observation requires filing source references")
    frame = frame.merge(filings[columns], on="observation_id", validate="one_to_one")
    if frame[columns].isna().any().any() or any(
        not isinstance(value, str) or not value.strip()
        for column in columns[1:] for value in frame[column]
    ):
        raise ValueError("Filing source references cannot be empty")
    frame["baseline_squared_error"] = np.square(frame.target - frame.baseline_prediction)
    frame["text_squared_error"] = np.square(frame.target - frame.text_prediction)
    frame["added_squared_error"] = frame.text_squared_error - frame.baseline_squared_error
    frame = frame.sort_values(["added_squared_error", "observation_id"], ascending=[False, True]).head(limit)
    selected = columns + ["year", "reference_session", "baseline_squared_error",
                          "text_squared_error", "added_squared_error"]
    records = frame[selected].to_dict(orient="records")
    for row in records:
        row["selection"] = "largest_text_minus_baseline_squared_error; outcome_selected_descriptive"
    return records


def _ablation_pipeline(alpha: float, features: list[str]) -> Pipeline:
    numeric = NUMERIC_CONTROLS + features
    numeric_steps = Pipeline([
        ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scale", StandardScaler()),
    ])
    transform = ColumnTransformer([
        ("numeric", numeric_steps, numeric),
        ("industry", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["industry"]),
    ])
    return Pipeline([("preprocess", transform), ("ridge", Ridge(alpha=alpha))])


def _fold(frame: pd.DataFrame, year: int, config: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    years = pd.to_datetime(frame.acceptance_date).dt.year
    test = frame.loc[years == year].copy()
    if test.empty:
        raise ValueError(f"Missing evaluation year {year}")
    train = eligible_training(frame, year, str(test.reference_session.min()))
    train = train.loc[pd.to_datetime(train.acceptance_date).dt.year >= config["initial_train_start"]]
    if len(train) < 10:
        raise ValueError(f"Insufficient matured training observations for {year}")
    features = TextChangeFeatures(config["tfidf_max_features"]).fit(train)
    x_train = pd.concat([train[NUMERIC_CONTROLS + ["industry"]], features.transform(train)], axis=1)
    x_test = pd.concat([test[NUMERIC_CONTROLS + ["industry"]], features.transform(test)], axis=1)
    return train, test, x_train, x_test


def development_ablations(frame: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, dict]:
    """Tune six declared text subsets on six development folds, never final data."""
    guard_development(frame, config)
    validate_dataset(frame)
    rows = []
    for year in range(config["development_start"], config["development_end"] + 1):
        train, test, x_train, x_test = _fold(frame, year, config)
        for name, features in ABLATION_FEATURES.items():
            for alpha in config["ridge_alphas"]:
                model = _ablation_pipeline(float(alpha), features)
                model.fit(x_train, train.target)
                prediction = model.predict(x_test)
                for obs, target, session, value in zip(test.observation_id, test.target,
                                                      test.reference_session, prediction, strict=True):
                    rows.append({"observation_id": obs, "year": year, "reference_session": session,
                                 "target": float(target), "ablation": name, "alpha": float(alpha),
                                 "prediction": float(value), "train_rows": len(train)})
    predictions = pd.DataFrame(rows)
    predictions["squared_error"] = np.square(predictions.target - predictions.prediction)
    scores = predictions.groupby(["ablation", "alpha"], as_index=False).squared_error.mean()
    selected = {}
    for name in ABLATION_FEATURES:
        row = scores.loc[scores.ablation == name].sort_values(["squared_error", "alpha"]).iloc[0]
        selected[name] = {"alpha": float(row.alpha), "development_mse": float(row.squared_error)}
    selection = {"schema_version": 1, "protocol_sha256": canonical_hash(config),
                 "features": {name: list(features) for name, features in ABLATION_FEATURES.items()},
                 "selected": selected,
                 "selection_years": list(range(config["development_start"], config["development_end"] + 1)),
                 "ridge_alphas": config["ridge_alphas"], "configurations": len(scores),
                 "selection_metric": "pooled_development_mse", "tie_break": "smaller_alpha",
                 "development_dataset_sha256": _frame_hash(frame),
                 "development_predictions_sha256": _frame_hash(predictions),
                 "interpretation": "secondary development choices; freeze before final access"}
    selection["selection_sha256"] = canonical_hash(selection)
    return predictions, selection


def _validate_ablation_selection(selection: dict, config: dict) -> None:
    unsigned = {key: value for key, value in selection.items() if key != "selection_sha256"}
    if selection.get("selection_sha256") != canonical_hash(unsigned):
        raise ValueError("Ablation selection has changed since its development freeze")
    if (selection.get("protocol_sha256") != canonical_hash(config) or
            selection.get("features") != ABLATION_FEATURES or
            selection.get("selection_years") != list(range(config["development_start"], config["development_end"] + 1)) or
            selection.get("ridge_alphas") != config["ridge_alphas"] or
            set(selection.get("selected", {})) != set(ABLATION_FEATURES)):
        raise ValueError("Ablations must use the declared development specification")
    for choice in selection["selected"].values():
        if choice.get("alpha") not in config["ridge_alphas"]:
            raise ValueError("Frozen ablation penalty is outside the declared grid")


def evaluate_ablations(frame: pd.DataFrame, selection: dict, config: dict, *,
                       years: list[int] | None = None) -> pd.DataFrame:
    """Produce secondary predictions from an already validated final-run context.

This low-level component does not grant final access. It verifies the unchanged
development selection, then performs chronological yearly fits without retuning.
Pair its outputs with the primary baseline on observation_id and year.
"""
    _validate_ablation_selection(selection, config)
    validate_dataset(frame)
    evaluation_years = years if years is not None else list(range(config["holdout_start"], config["holdout_end"] + 1))
    if (not evaluation_years or len(set(evaluation_years)) != len(evaluation_years) or
            any(year < config["holdout_start"] or year > config["holdout_end"] for year in evaluation_years)):
        raise ValueError("Ablation final predictions require declared final evaluation years")
    event_years = pd.to_datetime(frame.acceptance_date).dt.year
    if (event_years > config["holdout_end"]).any():
        raise ValueError("Events beyond the frozen final period are forbidden")
    rows = []
    for year in sorted(evaluation_years):
        train, test, x_train, x_test = _fold(frame, year, config)
        for name, features in ABLATION_FEATURES.items():
            alpha = float(selection["selected"][name]["alpha"])
            model = _ablation_pipeline(alpha, features)
            model.fit(x_train, train.target)
            prediction = model.predict(x_test)
            for obs, target, session, value in zip(test.observation_id, test.target,
                                                  test.reference_session, prediction, strict=True):
                rows.append({"observation_id": obs, "year": year, "reference_session": session,
                             "target": float(target), "ablation": name, "alpha": alpha,
                             "prediction": float(value), "train_rows": len(train)})
    return pd.DataFrame(rows)


def compare_ablation_predictions(primary_predictions: pd.DataFrame, ablation_predictions: pd.DataFrame,
                                  selection: dict, config: dict) -> dict:
    """Score all six frozen ablations on exactly the primary baseline's events."""
    _validate_ablation_selection(selection, config)
    primary = _paired(primary_predictions)
    required = {"observation_id", "year", "reference_session", "target", "ablation", "alpha", "prediction"}
    if (ablation_predictions.empty or required - set(ablation_predictions.columns) or
            set(ablation_predictions.ablation) != set(ABLATION_FEATURES)):
        raise ValueError("All six declared ablation prediction tables are required")
    results = {}
    for name in ABLATION_FEATURES:
        subset = ablation_predictions.loc[ablation_predictions.ablation == name].copy()
        if (subset.observation_id.duplicated().any() or
                set(subset.observation_id) != set(primary.observation_id)):
            raise ValueError("Ablation and primary baseline observations must match exactly")
        subset = subset.set_index("observation_id").loc[primary.observation_id]
        if (subset.alpha.nunique(dropna=False) != 1 or
                subset.alpha.iloc[0] != selection["selected"][name]["alpha"] or
                not np.array_equal(subset.target.to_numpy(dtype=float), primary.target.to_numpy(dtype=float)) or
                subset.reference_session.tolist() != primary.reference_session.tolist() or
                subset.year.tolist() != primary.year.tolist()):
            raise ValueError("Ablation outcomes, event clocks or frozen penalties differ from the paired comparison")
        paired = primary.copy()
        paired["text_prediction"] = subset.prediction.to_numpy(dtype=float)
        results[name] = {"features": ABLATION_FEATURES[name],
                          "alpha": selection["selected"][name]["alpha"],
                          "diagnostics": prediction_diagnostics(paired, config)}
    return {"ablations": results, "selection_sha256": selection["selection_sha256"],
            "primary_baseline_events": len(primary),
            "interpretation": "all prespecified subsets reported on identical baseline events; "
                              "no selection of a new primary model from these secondary results"}


def _frame_hash(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    digest.update(str([(name, str(dtype)) for name, dtype in frame.dtypes.items()]).encode())
    digest.update(pd.util.hash_pandas_object(frame, index=True, categorize=False).to_numpy().tobytes())
    return digest.hexdigest()


def _aware(value: Any, name: str) -> datetime:
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an explicit timestamp") from exc
    if pd.isna(parsed) or parsed.tzinfo is None:
        raise ValueError(f"{name} must include an explicit timezone")
    return parsed.to_pydatetime()


def rebuild_delay_dataset(events: pd.DataFrame, daily_returns: pd.DataFrame,
                          market_returns: pd.DataFrame, snapshots: pd.DataFrame,
                          delay: int, config: dict, *, availability: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Independently rebuild labels AND controls for a declared 1/2/5-session delay.

``events`` supplies approved, outcome-independently selected securities and audited
texts. It may be a primary prepared table, but its labels and controls are never
reused. ``availability`` contains observation_id, delay, availability_status
(``verified`` or ``documented_assumption``), public_available_at and
availability_evidence_id. Each bound must precede that delay's prediction open.
An unbounded two-session proxy is insufficient evidence for a one-session test.
The receipt separates actual verification from documented assumptions.

Historical-universe, identity, source and final-access gates are inherited from
the calling preparation/final-run workflow, not established by this calculator.
"""
    if delay not in (1, 2, 5) or isinstance(delay, bool):
        raise ValueError("Only the prespecified one-, two- and five-session delays are supported")
    required = {"observation_id", "security_id", "acceptance_timestamp", "current_text", "previous_text"}
    if events.empty or required - set(events.columns) or events.observation_id.duplicated().any():
        raise ValueError("Unique approved event identities, securities, acceptance and texts are required")
    if events[list(required)].isna().any().any():
        raise ValueError("Delay source events cannot have missing required values")
    needed_availability = {"observation_id", "delay", "availability_status", "public_available_at",
                           "availability_evidence_id"}
    if needed_availability - set(availability.columns):
        raise ValueError("Explicit delay-specific public-availability evidence is required")
    if availability.duplicated(["observation_id", "delay"]).any():
        raise ValueError("Delay-specific availability evidence is ambiguous")
    if set(availability.observation_id) - set(events.observation_id):
        raise ValueError("Availability evidence refers to unknown events")
    if {"security_id", "session", "total_return", "terminal_event"} - set(daily_returns.columns):
        raise ValueError("Delay rebuild requires normalized security returns")
    if {"session", "total_return"} - set(market_returns.columns):
        raise ValueError("Delay rebuild requires normalized benchmark returns")
    availability_for_delay = availability.loc[availability.delay == delay].set_index("observation_id")
    security_frames = {str(security): group for security, group in daily_returns.groupby("security_id", sort=False)}
    rows, exclusions = [], []
    for row in events.to_dict(orient="records"):
        identity = row["observation_id"]
        stage = "availability"
        try:
            accepted = _aware(row["acceptance_timestamp"], "acceptance_timestamp")
            window = event_window(accepted, delay=delay, horizon=config["horizon_sessions"])
            if not config["initial_train_start"] <= int(window.acceptance_date[:4]) <= config["holdout_end"]:
                raise ValueError("Event is outside the frozen research period")
            if identity not in availability_for_delay.index:
                raise ValueError("Missing availability evidence for this delay")
            evidence = availability_for_delay.loc[identity]
            if evidence.availability_status not in ("verified", "documented_assumption"):
                raise ValueError("Public availability is neither verified nor a documented assumption")
            if not isinstance(evidence.availability_evidence_id, str) or not evidence.availability_evidence_id.strip():
                raise ValueError("Public availability requires a source-bound evidence reference")
            available = _aware(evidence.public_available_at, "public_available_at")
            if available < accepted:
                raise ValueError("Availability bound precedes the original filing acceptance")
            if available >= _aware(window.prediction_time_utc, "prediction_time_utc"):
                raise ValueError("Public-availability bound is not before this delay's prediction")
            stage = "controls_and_label"
            stock = security_frames.get(str(row["security_id"]))
            if stock is None:
                raise ValueError("Missing approved security returns")
            controls = make_controls(stock, snapshots, window)
            label = make_label(stock, market_returns, window)
            # Copy only identity, text and evidence fields. None of the original
            # target/control numbers or source-session claims are inherited.
            result = {key: row[key] for key in (
                "observation_id", "security_id", "cik", "acceptance_timestamp", "current_text",
                "previous_text", "previous_accession", "source_url", "current_source_url", "previous_source_url"
            ) if key in row}
            result.update({**controls, **label, "acceptance_date": window.acceptance_date,
                           "prediction_time_utc": window.prediction_time_utc, "reference_delay": delay,
                           "availability_status": evidence.availability_status,
                           "public_available_at": available.isoformat(),
                           "availability_evidence_id": evidence.availability_evidence_id,
                           "delay_data_kind": "INDEPENDENTLY_REBUILT_SECONDARY_DATASET"})
            rows.append(result)
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            exclusions.append({"observation_id": identity, "delay": delay, "stage": stage,
                               "reason": str(exc)})
    prepared = pd.DataFrame(rows)
    excluded = pd.DataFrame(exclusions, columns=["observation_id", "delay", "stage", "reason"])
    if not prepared.empty:
        validate_dataset(prepared)
    receipt = {"schema_version": 1, "protocol_sha256": canonical_hash(config), "delay": delay,
               "horizon_sessions": config["horizon_sessions"], "source_events": len(events),
               "included_events": len(prepared), "excluded_events": len(excluded),
               "labels_rebuilt": True, "controls_rebuilt": True,
               "input_hash_method": "sha256_of_columns_dtypes_and_pandas_row_hashes; locked_environment",
               "inputs": {"events": _frame_hash(events), "daily_returns": _frame_hash(daily_returns),
                          "market_returns": _frame_hash(market_returns), "snapshots": _frame_hash(snapshots),
                          "availability": _frame_hash(availability)},
               "dataset_sha256": _frame_hash(prepared), "exclusions_sha256": _frame_hash(excluded),
               "availability_counts": prepared.availability_status.value_counts().to_dict()
               if not prepared.empty else {},
               "interpretation": "conditional on inherited source/universe/identity audits; "
                                 "documented availability assumptions are not verified dissemination"}
    receipt["receipt_sha256"] = canonical_hash(receipt)
    return prepared, excluded, receipt


def validate_delay_dataset(frame: pd.DataFrame, delay: int, evidence: dict, config: dict) -> None:
    """Reject shifted/corrupted tables, stale rebuild receipts and wrong clocks."""
    unsigned = {key: value for key, value in evidence.items() if key != "receipt_sha256"}
    if evidence.get("receipt_sha256") != canonical_hash(unsigned):
        raise ValueError("Delay rebuild receipt has changed")
    if (delay not in (1, 2, 5) or evidence.get("delay") != delay or
            evidence.get("protocol_sha256") != canonical_hash(config) or
            evidence.get("labels_rebuilt") is not True or evidence.get("controls_rebuilt") is not True or
            evidence.get("dataset_sha256") != _frame_hash(frame)):
        raise ValueError("Delay dataset must match its independent label/control rebuild evidence")
    validate_dataset(frame)
    for row in frame.to_dict(orient="records"):
        window = event_window(_aware(row["acceptance_timestamp"], "acceptance_timestamp"), delay=delay,
                              horizon=config["horizon_sessions"])
        if (row.get("reference_delay") != delay or row["reference_session"] != window.reference_session or
                row["controls_asof"] != window.controls_through or row["label_end"] != window.label_end or
                row.get("prediction_time_utc") != window.prediction_time_utc):
            raise ValueError("Delay dataset does not follow the independently rebuilt event clock")
        if (row.get("availability_status") not in ("verified", "documented_assumption") or
                not row.get("availability_evidence_id") or
                _aware(row["public_available_at"], "public_available_at") >=
                _aware(window.prediction_time_utc, "prediction_time_utc")):
            raise ValueError("Delay dataset violates its public-availability condition")


def evaluate_delay_predictions(frame: pd.DataFrame, delay: int, evidence: dict, config: dict, *,
                                baseline_alpha: float, text_alpha: float,
                                years: list[int] | None = None) -> pd.DataFrame:
    """Fit a rebuilt delay variant using the primary development-selected penalties.

The authorized orchestration layer supplies the frozen penalties and final data;
this low-level function grants no access. It performs no alpha search, retains the
same annual training-label maturity rule and fits all preprocessing in training.
"""
    validate_delay_dataset(frame, delay, evidence, config)
    if any(isinstance(alpha, bool) or alpha not in config["ridge_alphas"]
           for alpha in (baseline_alpha, text_alpha)):
        raise ValueError("Delay penalties must be the primary frozen development-grid values")
    evaluation_years = years if years is not None else list(range(config["holdout_start"], config["holdout_end"] + 1))
    if (not evaluation_years or len(evaluation_years) != len(set(evaluation_years)) or
            any(isinstance(year, bool) or not isinstance(year, int) or
                not config["development_start"] <= year <= config["holdout_end"] for year in evaluation_years)):
        raise ValueError("Delay evaluation years must belong to the frozen development/final periods")
    rows = []
    for year in sorted(evaluation_years):
        train, test, x_train, x_test = _fold(frame, year, config)
        baseline = _ablation_pipeline(float(baseline_alpha), [])
        augmented = _ablation_pipeline(float(text_alpha), FEATURE_NAMES)
        baseline.fit(x_train, train.target)
        augmented.fit(x_train, train.target)
        baseline_prediction, text_prediction = baseline.predict(x_test), augmented.predict(x_test)
        for obs, target, session, base, text in zip(test.observation_id, test.target, test.reference_session,
                                                   baseline_prediction, text_prediction, strict=True):
            rows.append({"observation_id": obs, "year": year, "reference_session": session,
                         "target": float(target), "baseline_prediction": float(base),
                         "text_prediction": float(text), "baseline_alpha": float(baseline_alpha),
                         "text_alpha": float(text_alpha), "train_rows": len(train), "reference_delay": delay})
    return pd.DataFrame(rows)


def compare_delay_predictions(predictions_by_delay: dict[int, pd.DataFrame],
                              datasets_by_delay: dict[int, pd.DataFrame],
                              evidence_by_delay: dict[int, dict], config: dict) -> dict:
    """Compare rebuilt delay variants on their own samples and a common event set.

Supply predictions made with the primary development-selected penalties. The
frozen final workflow must bind those penalties; this routine checks that all
three runs actually use the same baseline/text penalties and rebuilt targets.
"""
    expected = {1, 2, 5}
    if any(set(bundle) != expected for bundle in (predictions_by_delay, datasets_by_delay, evidence_by_delay)):
        raise ValueError("Delay comparison requires explicit one-, two- and five-session variants")
    checked, penalties = {}, None
    for delay in sorted(expected):
        data = datasets_by_delay[delay]
        validate_delay_dataset(data, delay, evidence_by_delay[delay], config)
        predictions = _paired(predictions_by_delay[delay])
        if {"baseline_alpha", "text_alpha"} - set(predictions.columns):
            raise ValueError("Delay predictions must record frozen primary penalties")
        current_penalties = []
        for column in ("baseline_alpha", "text_alpha"):
            if predictions[column].nunique(dropna=False) != 1 or predictions[column].isna().any():
                raise ValueError("A delay variant changed its frozen primary penalty")
            value = float(predictions[column].iloc[0])
            if value not in config["ridge_alphas"]:
                raise ValueError("Delay penalty is outside the primary development grid")
            current_penalties.append(value)
        if penalties is not None and current_penalties != penalties:
            raise ValueError("Delay variants must share the primary frozen penalties")
        penalties = current_penalties
        expected_events = data.loc[pd.to_datetime(data.acceptance_date).dt.year.isin(predictions.year)]
        if set(predictions.observation_id) != set(expected_events.observation_id):
            raise ValueError("Delay predictions must cover every rebuilt event in their evaluation years")
        truth = data.set_index("observation_id").loc[predictions.observation_id]
        if (not np.array_equal(predictions.target.to_numpy(dtype=float), truth.target.to_numpy(dtype=float)) or
                predictions.reference_session.tolist() != truth.reference_session.tolist() or
                predictions.year.tolist() != pd.to_datetime(truth.acceptance_date).dt.year.tolist()):
            raise ValueError("Delay predictions do not match the independently rebuilt labels and clock")
        checked[delay] = predictions
    if len({tuple(sorted(frame.year.unique())) for frame in checked.values()}) != 1:
        raise ValueError("Delay comparisons must cover the same evaluation years")
    common = set.intersection(*(set(frame.observation_id) for frame in checked.values()))
    own, paired = {}, {}
    for delay, frame in checked.items():
        own[str(delay)] = {"diagnostics": prediction_diagnostics(frame, config),
                           "excluded_during_rebuild": evidence_by_delay[delay]["excluded_events"],
                           "availability_counts": evidence_by_delay[delay]["availability_counts"]}
        subset = frame.loc[frame.observation_id.isin(common)]
        paired[str(delay)] = _score(subset)
    return {"per_delay": own, "common_event_scores": paired, "common_events": len(common),
            "baseline_alpha": penalties[0], "text_alpha": penalties[1],
            "interpretation": "prespecified sensitivity; horizons and prior-close controls rebuilt "
                              "for each delay; own-sample and common-event results both retained"}


def describe_paragraph_changes(previous: str, current: str, *,
                               rewording_jaccard_threshold: float = 0.5) -> dict:
    """Conservative candidate paragraph matches for manual descriptive review.

Blank lines delimit paragraphs. Exact normalized matches are matched first with
multiplicity preserved. A deterministic longest increasing match sequence marks
relative-order preservation: an insertion alone does not imply relocation.
Unmatched paragraphs are called rewording candidates only for unique mutual-best
token-set matches above the fixed threshold. All unmatched portions remain visible;
human review distinguishes actual new/deleted risk from formatting and relocation.
This deliberately creates no numerical forecasting feature.
"""
    if not isinstance(previous, str) or not isinstance(current, str):
        raise ValueError("Paragraph comparison requires text strings")
    if not 0 < rewording_jaccard_threshold <= 1:
        raise ValueError("Descriptive matching threshold must be in (0, 1]")
    def split(text):
        return [part.strip() for part in re.split(r"\n\s*\n", text.replace("\r\n", "\n")) if part.strip()]
    old, new = split(previous), split(current)
    if not old or not new:
        raise ValueError("Both disclosures require nonempty paragraphs")
    def normalize(text):
        # Preserve numbers and punctuation: a changed dollar amount is not an
        # unchanged disclosure even though the primary text model drops digits.
        return " ".join(text.lower().split())
    old_norm, new_norm = [normalize(text) for text in old], [normalize(text) for text in new]
    if any(not re.search(r"[a-zA-Z]", text) for text in old_norm + new_norm):
        raise ValueError("Paragraphs without alphabetic tokens need manual boundary review")
    by_text = defaultdict(deque)
    for index, text in enumerate(old_norm):
        by_text[text].append(index)
    exact = []
    for index, text in enumerate(new_norm):
        if by_text[text]:
            exact.append((by_text[text].popleft(), index))
    # Dynamic programming is clear and deterministic for a few hundred risk
    # paragraphs; ties retain the earliest subsequence encountered.
    best_paths = []
    for index, (old_index, _) in enumerate(exact):
        candidates = [best_paths[j] for j in range(index) if exact[j][0] < old_index]
        prior = max(candidates, key=len) if candidates else []
        best_paths.append([*prior, index])
    ordered = set(max(best_paths, key=len) if best_paths else [])
    records = [{"previous_index": old_index, "current_index": new_index,
                "category": "unchanged" if index in ordered else "relocated_candidate",
                "similarity": 1.0, "previous_text": old[old_index], "current_text": new[new_index]}
               for index, (old_index, new_index) in enumerate(exact)]
    remaining_old = sorted(set(range(len(old))) - {x for x, _ in exact})
    remaining_new = sorted(set(range(len(new))) - {y for _, y in exact})
    similarities = {}
    for left in remaining_old:
        a = set(re.findall(r"\b[a-zA-Z0-9]+\b", old_norm[left]))
        for right in remaining_new:
            b = set(re.findall(r"\b[a-zA-Z0-9]+\b", new_norm[right]))
            similarities[left, right] = len(a & b) / len(a | b)
    best_old, best_new = {}, {}
    for left in remaining_old:
        options = [(right, similarities[left, right]) for right in remaining_new]
        if options:
            maximum = max(score for _, score in options)
            winners = [right for right, score in options if score == maximum]
            if len(winners) == 1 and maximum >= rewording_jaccard_threshold:
                best_old[left] = winners[0]
    for right in remaining_new:
        options = [(left, similarities[left, right]) for left in remaining_old]
        if options:
            maximum = max(score for _, score in options)
            winners = [left for left, score in options if score == maximum]
            if len(winners) == 1 and maximum >= rewording_jaccard_threshold:
                best_new[right] = winners[0]
    changed = [(left, right) for left, right in best_old.items() if best_new.get(right) == left]
    for left, right in changed:
        records.append({"previous_index": left, "current_index": right,
                        "category": "rewording_candidate", "similarity": similarities[left, right],
                        "previous_text": old[left], "current_text": new[right]})
    for left in sorted(set(remaining_old) - {left for left, _ in changed}):
        records.append({"previous_index": left, "current_index": None, "category": "removed_candidate",
                        "similarity": None, "previous_text": old[left], "current_text": None})
    for right in sorted(set(remaining_new) - {right for _, right in changed}):
        records.append({"previous_index": None, "current_index": right, "category": "added_candidate",
                        "similarity": None, "previous_text": None, "current_text": new[right]})
    counts = {category: sum(row["category"] == category for row in records) for category in
              ("unchanged", "relocated_candidate", "rewording_candidate", "removed_candidate", "added_candidate")}
    return {"previous_paragraphs": len(old), "current_paragraphs": len(new), "counts": counts,
            "matches": records, "rewording_jaccard_threshold": rewording_jaccard_threshold,
            "forecast_features_created": False, "manual_review_status": "pending",
            "interpretation": "descriptive candidates only; manual review must distinguish risk "
                              "additions, removals, rewording and relocation"}
