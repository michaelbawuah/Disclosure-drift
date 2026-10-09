"""Small ridge baselines with preprocessing fitted independently in each time fold."""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .features import FEATURE_NAMES, TextChangeFeatures
from .protocol import eligible_training, guard_development

NUMERIC_CONTROLS = ["momentum_20", "momentum_60", "volatility_20", "log_market_cap"]


def pipeline(alpha: float, text: bool) -> Pipeline:
    numeric = NUMERIC_CONTROLS + (FEATURE_NAMES if text else [])
    numeric_steps = Pipeline([("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                              ("scale", StandardScaler())])
    transformer = ColumnTransformer([
        ("numeric", numeric_steps, numeric),
        ("industry", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["industry"]),
    ])
    return Pipeline([("preprocess", transformer), ("ridge", Ridge(alpha=alpha))])


def validate_dataset(frame: pd.DataFrame) -> None:
    required = ["observation_id", "acceptance_date", "reference_session", "label_end", "target",
                "current_text", "previous_text", "industry", "controls_asof"] + NUMERIC_CONTROLS
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing dataset columns: {missing}")
    if frame.observation_id.duplicated().any():
        raise ValueError("Duplicate observation identifiers")
    if frame[required].isna().any().any():
        raise ValueError("Required dataset values are missing; resolve exclusions before modeling")
    if not np.isfinite(frame[["target"] + NUMERIC_CONTROLS].to_numpy(dtype=float)).all():
        raise ValueError("Controls and labels must be finite")
    acceptance = pd.to_datetime(frame.acceptance_date)
    reference = pd.to_datetime(frame.reference_session)
    ends = pd.to_datetime(frame.label_end)
    asof = pd.to_datetime(frame.controls_asof)
    if ((acceptance >= reference) | (asof >= reference) | (ends <= reference)).any():
        raise ValueError("Invalid temporal ordering or future-dated controls")


def development_comparison(frame: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, dict]:
    guard_development(frame, config)
    validate_dataset(frame)
    years = pd.to_datetime(frame.acceptance_date).dt.year
    outputs = []
    for year in range(config["development_start"], config["development_end"] + 1):
        test = frame.loc[years == year].copy()
        if test.empty:
            raise ValueError(f"Missing development year {year}")
        train = eligible_training(frame, year, str(test.reference_session.min()))
        train = train.loc[pd.to_datetime(train.acceptance_date).dt.year >= config["initial_train_start"]]
        if len(train) < 10:
            raise ValueError(f"Insufficient eligible training observations for {year}")
        features = TextChangeFeatures(config["tfidf_max_features"]).fit(train)
        x_train = pd.concat([train[NUMERIC_CONTROLS + ["industry"]], features.transform(train)], axis=1)
        x_test = pd.concat([test[NUMERIC_CONTROLS + ["industry"]], features.transform(test)], axis=1)
        for text in (False, True):
            for alpha in config["ridge_alphas"]:
                model = pipeline(alpha, text)
                model.fit(x_train, train.target)
                prediction = model.predict(x_test)
                for obs, target, session, value in zip(test.observation_id, test.target,
                                                      test.reference_session, prediction, strict=True):
                    outputs.append({"observation_id": obs, "year": year, "target": float(target),
                                    "reference_session": session, "model": "text" if text else "baseline",
                                    "alpha": alpha, "prediction": float(value), "train_rows": len(train)})
    results = pd.DataFrame(outputs)
    results["squared_error"] = (results.target - results.prediction) ** 2
    scores = results.groupby(["model", "alpha"], as_index=False).squared_error.mean()
    choices = {}
    for name in ("baseline", "text"):
        # Stable tie break toward the smaller declared alpha.
        row = scores.loc[scores.model == name].sort_values(["squared_error", "alpha"]).iloc[0]
        choices[name] = {"alpha": float(row.alpha), "development_mse": float(row.squared_error)}
    return results, {"selected": choices, "selection_period": "2016-2021",
                     "interpretation": "development selection only; not an independent performance claim",
                     "configurations": len(scores)}
