"""Development-only conditional experiment on unapproved SEC/market pilot candidates.

This is not the frozen empirical study, an approved security crosswalk, or a
validated forecast-performance result. 2022-2025 source targets are never read.
"""

import hashlib
import io
import json
import math
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import pandas as pd

from .features import FEATURE_NAMES
from .modeling import NUMERIC_CONTROLS, pipeline
from .protocol import canonical_hash

KIND = "UNAPPROVED_REAL_CANDIDATE_EXPLORATORY_DEVELOPMENT_ONLY"
FIXED_ALPHA = 10.0
FIRST_YEAR = 2015
LAST_YEAR = 2021
MIN_TRAIN = 15
REQUIRED_YEARS = range(2016, 2022)
RECEIPT_KIND = "PROVISIONAL_CANDIDATE_ARITHMETIC_QA"
SOURCE_FEATURE_KIND = "REAL_SEC_TEXT_DESCRIPTIVE_PILOT"
CANDIDATE_FIELDS = (
    "event_id", "cik", "acceptance_timestamp", "previous_accession",
    "human_pair_review_complete", "reference_session", "controls_asof", "label_end",
    "control_history_start", "candidate_permno", "identity_approved", "model_ready",
    "qa_status", "header_cik_differs", "open_end_unresolved",
    "stock_return", "market_return", "target", "horizon_sessions",
    "momentum_20", "momentum_60", "volatility_20", "log_market_cap",
    "industry", "control_history_sessions", "independent_max_abs_error",
)
FEATURE_FIELDS = (
    "observation_id", "cik", "year", "previous_tokens", "current_tokens",
    *FEATURE_NAMES, "vocabulary_training_pairs", "source_url", "previous_source_url",
)
_PREDICTION_FIELDS = [
    "observation_id", "cik", "filing_year", "reference_session", "label_end",
    "model", "fixed_alpha", "prediction", "target", "squared_error", "train_rows",
]
_SOURCE_FILES = {
    "candidate_table": "candidate_calculations.parquet",
    "candidate_receipt": "audit_summary.json",
    "text_features": "text_features.csv",
    "text_receipt": "pilot_checkpoint.json",
}


def _require(ok, why):
    if not ok:
        raise ValueError(why)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _source_bytes(paths):
    data = {}
    for key, path in paths.items():
        _require(path.is_file() and not path.is_symlink(), f"Missing or linked source: {key}")
        size = path.stat().st_size
        _require(size <= (30 * 1024 * 1024 if key == "candidate_table" else 2 * 1024 * 1024),
                 f"Source exceeds bounded size: {key}")
        data[key] = path.read_bytes()
    return data


def _date(raw, name):
    _require(isinstance(raw, str) and len(raw) == 10 and raw[4] == "-" and raw[7] == "-",
             f"Malformed {name}")
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid {name}") from exc
    _require(parsed.isoformat() == raw, f"Noncanonical {name}")
    return parsed


def _timestamp(raw):
    _require(isinstance(raw, str), "Missing acceptance timestamp")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid acceptance timestamp") from exc
    _require(value.utcoffset() is not None, "Acceptance timestamp lacks timezone")
    return value


def _read_inputs(blobs, config):
    pilot = json.loads(blobs["candidate_receipt"])
    report = json.loads(blobs["text_receipt"])
    expected_protocol = canonical_hash(config)
    _require(pilot.get("data_kind") == RECEIPT_KIND, "Source is not provisional arithmetic QA")
    _require(report.get("data_kind") == SOURCE_FEATURE_KIND, "Source is not SEC text pilot")
    _require(pilot["source_hashes"]["protocol"] == expected_protocol
             and report["protocol_sha256"] == expected_protocol, "Frozen protocol mismatch")
    _require(_sha(blobs["candidate_table"]) == pilot["files"][_SOURCE_FILES["candidate_table"]],
             "Candidate table fingerprint mismatch")
    _require(_sha(blobs["text_features"]) == report["files"][_SOURCE_FILES["text_features"]],
             "SEC text feature fingerprint mismatch")
    _require(pilot.get("model_ready") is False and pilot.get("milestone_05_complete") is False
             and pilot.get("historical_cik_mapping_approved") is False
             and pilot.get("final_period_opened") is False, "Unexpected candidate source state")
    _require(report.get("returns_read") is False and report.get("milestone_06_complete") is False,
             "Text source receipt is not the original SEC descriptive pilot")
    _require(set(config["primary_features"]) == set(FEATURE_NAMES),
             "Unexpected primary text-feature definition")
    _require(FIXED_ALPHA in config["ridge_alphas"], "Exploratory ridge penalty not in frozen grid")
    observed = pd.read_parquet(io.BytesIO(blobs["candidate_table"]))
    features = pd.read_csv(io.BytesIO(blobs["text_features"]), dtype={"observation_id": str, "cik": str})
    _require(not set(CANDIDATE_FIELDS).difference(observed.columns), "Candidate table missing fields")
    _require(not set(FEATURE_FIELDS).difference(features.columns), "Text features missing fields")
    _require(len(observed) == pilot["qa_cases_calculated"] == report["pairs"] == len(features) == 135,
             "Unexpected purposive 20-issuer pilot coverage")
    _require(observed["event_id"].is_unique and features["observation_id"].is_unique,
             "Duplicate original filing ID in candidate or text source")
    _require(observed["data_kind"].eq(RECEIPT_KIND).all(), "Mixed candidate data kinds")
    _require(observed["qa_status"].eq("calculated_pending_review").all(),
             "Only preliminary calculated-but-pending candidates are supported")
    for name in ["identity_approved", "model_ready", "human_pair_review_complete"]:
        _require(observed[name].eq(False).all(), f"Input {name} falsely implies approval")
    _require(observed["open_end_unresolved"].eq(True).all(),
             "This code is only for original unresolved-open-end review cohort")
    _require(observed["horizon_sessions"].eq(config["horizon_sessions"]).all(),
             "Incorrect label horizon")
    _require(observed["control_history_sessions"].eq(60).all(), "Incorrect control lookback")
    _require(observed["event_id"].map(lambda s: isinstance(s, str) and len(s) == 20).all(),
             "Malformed original accession")
    _require(observed["cik"].map(lambda s: isinstance(s, str) and len(s) == 10
             and s.isascii() and s.isdigit()).all(), "Malformed issuer CIK")
    observed["year"] = observed["acceptance_timestamp"].map(lambda x: _timestamp(x).year)
    _require(observed["year"].between(FIRST_YEAR, LAST_YEAR).all()
             and set(observed["year"]) == set(range(FIRST_YEAR, LAST_YEAR + 1)),
             "Unexpected filing-year coverage; never read holdout")
    for row in observed.itertuples():
        filing = _timestamp(row.acceptance_timestamp).date()
        start = _date(row.control_history_start, "control history start")
        control = _date(row.controls_asof, "controls as-of")
        ref = _date(row.reference_session, "reference session")
        label = _date(row.label_end, "label end")
        _require(start <= control < ref < label and filing < ref, "Invalid temporal window")
    for name in ["target", "stock_return", "market_return", *NUMERIC_CONTROLS]:
        _require(pd.api.types.is_numeric_dtype(observed[name]), f"Non-numeric {name}")
        _require(np.isfinite(observed[name].to_numpy(dtype=float)).all(), f"Nonfinite {name}")
    _require(np.allclose(
        observed["target"].to_numpy(dtype=float),
        observed["stock_return"].to_numpy(dtype=float)
        - observed["market_return"].to_numpy(dtype=float), rtol=0, atol=1e-12,
    ), "Original calculated labels do not satisfy target identity")
    _require(np.isfinite(observed["independent_max_abs_error"].to_numpy(dtype=float)).all()
             and observed["independent_max_abs_error"].le(1e-12).all(),
             "Unverified independent pilot arithmetic")
    _require(observed["industry"].notna().all(), "Missing historical industry candidate")
    _require(observed["candidate_permno"].notna().all(), "Missing permanent security candidate")
    _require(features["year"].between(FIRST_YEAR, LAST_YEAR).all(),
             "Text features cross frozen holdout boundary")
    for name in ("previous_tokens", "current_tokens"):
        _require(features[name].notna().all() and features[name].ge(1).all(),
                 "Empty text tokens")
    computed_log = np.log1p(features["current_tokens"]) - np.log1p(features["previous_tokens"])
    _require(np.allclose(computed_log, features["log_length_change"], atol=1e-10, rtol=0),
             "Source text-length change disagrees with token counts")
    _require(features["jaccard_distance"].notna().all()
             and features["jaccard_distance"].between(0, 1).all(), "Invalid Jaccard features")
    _require(features["tfidf_cosine_distance"].dropna().between(0, 1).all(),
             "Invalid TF-IDF cosine distance")
    _require(features.loc[features.year == FIRST_YEAR, "tfidf_cosine_distance"].isna().all()
             and features.loc[features.year > FIRST_YEAR, "tfidf_cosine_distance"].notna().all(),
             "Unexpected missing TF-IDF pattern: earlier-year-only vocabulary required")
    years = features.groupby("year").size().to_dict()
    for year, group in features.groupby("year"):
        expected = sum(n for yy, n in years.items() if yy < year)
        _require(group["vocabulary_training_pairs"].eq(expected).all(),
                 "Possible future-filing leakage in saved TF-IDF feature metadata")
    for field in ("source_url", "previous_source_url"):
        _require(features[field].map(
            lambda u: isinstance(u, str) and urlsplit(u).scheme == "https"
            and urlsplit(u).netloc.lower() == "www.sec.gov"
            and urlsplit(u).path.startswith("/Archives/edgar/data/")
        ).all(), f"Unexpected source URL: {field}")
    joined = observed.merge(features, left_on="event_id", right_on="observation_id", how="inner",
                            validate="one_to_one", suffixes=("_market", "_sec"), sort=True)
    _require(len(joined) == len(observed) == len(features), "SEC-market source join not one-to-one")
    _require(joined["cik_market"].eq(joined["cik_sec"]).all(), "SEC filer CIK disagrees with market candidate")
    _require(joined["year_market"].eq(joined["year_sec"]).all(), "SEC filing year disagrees with market candidate")
    return joined, pilot, report


def _validation_years(frame):
    folds = []
    for year in REQUIRED_YEARS:
        test = frame.loc[frame["year_market"] == year].copy().sort_values("event_id")
        if test.empty:
            raise ValueError(f"Missing exploratory test year {year}")
        cutoff = min(test["reference_session"])
        train = frame.loc[
            (frame["year_market"] < year) & (frame["label_end"] < cutoff)
        ].copy().sort_values("event_id")
        _require(len(train) >= MIN_TRAIN, f"Insufficient chronologically prior labels for {year}")
        _require(train["label_end"].max() < cutoff, "Train label end overlaps new test year")
        _require(train["year_market"].max() < year, "Later filing leaked into training")
        folds.append((year, cutoff, train, test))
    return folds


def _predict(frame):
    predictions = []
    folds_report = []
    for year, cutoff, train, test in _validation_years(frame):
        cols = list(NUMERIC_CONTROLS) + ["industry"] + list(FEATURE_NAMES)
        x_train = train[cols].copy()
        x_test = test[cols].copy()
        for mode in ("baseline", "text"):
            model = pipeline(alpha=FIXED_ALPHA, text=(mode == "text"))
            model.fit(x_train, train["target"].to_numpy(dtype=float))
            values = model.predict(x_test)
            _require(np.isfinite(values).all(), f"Nonfinite {mode} predictions")
            for row, pred in zip(test.itertuples(), values, strict=True):
                predictions.append({
                    "observation_id": row.event_id, "cik": row.cik_market,
                    "filing_year": year, "reference_session": row.reference_session,
                    "label_end": row.label_end, "model": mode,
                    "fixed_alpha": FIXED_ALPHA, "prediction": float(pred),
                    "target": float(row.target), "squared_error": float((row.target - pred) ** 2),
                    "train_rows": len(train),
                })
        folds_report.append({
            "test_year": year, "train_rows": len(train), "test_rows": len(test),
            "training_label_end_max": max(train["label_end"]),
            "earliest_test_reference_session": cutoff,
            "training_filing_years": sorted(set(int(y) for y in train["year_market"])),
        })
    return pd.DataFrame(predictions), folds_report


def _conditional_metrics(predictions, *, seed, draws=2000):
    paired = predictions.pivot(index="observation_id", columns="model", values="squared_error")
    _require(not paired.isna().any().any() and len(paired) * 2 == len(predictions),
             "Unpaired exploratory predictions")
    baseline = float(paired["baseline"].sum())
    augmented = float(paired["text"].sum())
    _require(baseline > 0 and math.isfinite(baseline) and math.isfinite(augmented),
             "Unsupported baseline residual sum of squares")
    issuer = (predictions.loc[predictions.model == "baseline", ["observation_id", "cik"]]
              .set_index("observation_id", verify_integrity=True))
    paired = paired.join(issuer)
    _require(paired.cik.notna().all(), "Missing test issuer for clustered resampling")
    by_issuer = paired.groupby("cik", sort=True)[["baseline", "text"]].sum().to_numpy()
    _require(len(by_issuer) >= 10, "Too few issuers for pilot uncertainty diagnostic")
    rng = np.random.default_rng(seed)
    selections = rng.integers(0, len(by_issuer), size=(draws, len(by_issuer)))
    totals = by_issuer[selections].sum(axis=1)
    _require((totals[:, 0] > 0).all(), "Zero denominator in pilot cluster resampling")
    draws_relative = 1 - totals[:, 1] / totals[:, 0]
    _require(np.isfinite(draws_relative).all(), "Nonfinite exploratory cluster interval")
    return {
        "model_names": ["baseline", "text"], "fixed_alpha": FIXED_ALPHA,
        "baseline_sse": baseline, "text_sse": augmented,
        "baseline_mse": baseline / len(paired), "text_mse": augmented / len(paired),
        "conditional_relative_sse_change": float(1 - augmented / baseline),
        "issuer_cluster_bootstrap_draws": draws, "issuer_clusters": len(by_issuer),
        "cluster_percentile_interval_95": [
            float(np.quantile(draws_relative, 0.025)),
            float(np.quantile(draws_relative, 0.975)),
        ],
        "note": "Descriptive uncertainty conditional on unreviewed candidate identities; not a valid population inference or primary result",
    }


def run_exploratory_sec_pilot(candidate_dir, feature_dir, output, config, repo_root) -> dict:
    """Run a fixed, non-tuned exploratory check without touching production evaluation."""
    root = Path(repo_root).resolve(strict=True)
    destination = Path(output).resolve()
    _require(any(destination.is_relative_to(root / d) and destination != root / d
                 for d in ("data", "outputs")), "Private output must be below repo data/ or outputs/")
    _require(not destination.exists(), "Cannot overwrite any exploratory result")
    candidate_dir = Path(candidate_dir).resolve(strict=True)
    feature_dir = Path(feature_dir).resolve(strict=True)
    _require(not destination.is_relative_to(candidate_dir)
             and not destination.is_relative_to(feature_dir),
             "Output cannot be nested inside consumed inputs")
    sources = {
        "candidate_table": candidate_dir / _SOURCE_FILES["candidate_table"],
        "candidate_receipt": candidate_dir / _SOURCE_FILES["candidate_receipt"],
        "text_features": feature_dir / _SOURCE_FILES["text_features"],
        "text_receipt": feature_dir / _SOURCE_FILES["text_receipt"],
    }
    blobs = _source_bytes(sources)
    frame, pilot, text_report = _read_inputs(blobs, config)
    predictions, folds = _predict(frame)
    results = _conditional_metrics(predictions, seed=config["seed"])
    _require(len(predictions) == sum(f["test_rows"] for f in folds) * 2,
             "Predictions do not cover the expected development folds")
    _require(not predictions["filing_year"].ge(config["holdout_start"]).any(),
             "Holdout predictions are forbidden")
    # Check all read-once sources again before persisting any result.
    for name, path in sources.items():
        _require(_sha(path.read_bytes()) == _sha(blobs[name]), f"Source changed during run: {name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sec-exploration-", dir=destination.parent) as scratch:
        stage = Path(scratch) / "result"
        stage.mkdir(mode=0o700)
        predictions[_PREDICTION_FIELDS].to_csv(stage / "candidate_predictions_private.csv",
                                               index=False, float_format="%.17g")
        results_data = {
            "schema_version": 1, "data_kind": KIND,
            "source_bindings_sha256": {k: _sha(v) for k, v in blobs.items()},
            "protocol_sha256": canonical_hash(config),
            "candidate_count": len(frame), "candidate_issuers": int(frame.cik_market.nunique()),
            "test_count": len(predictions) // 2, "test_years": list(REQUIRED_YEARS),
            "features": list(FEATURE_NAMES),
            "train_observation_reuse": "expanding, only completed earlier-year labels",
            "folds": folds, "conditional_metrics": results,
            "candidate_identity_approved": False,
            "source_release_verified": False,
            "historical_availability_verified": False,
            "human_filing_and_market_reviews_complete": False,
            "actual_model_ready": False, "primary_protocol_executed": False,
            "study_milestones_5_through_11_complete": False,
            "actual_2022_2025_final_period_opened": False,
            "interpretation": "Exploratory non-authoritative model diagnostic on unapproved real development candidates. Never cite as validated forecast performance.",
        }
        (stage / "conditional_metrics_private.json").write_text(json.dumps(
            results_data, indent=2, sort_keys=True) + "\n")
        public = {
            "schema_version": 1, "data_kind": KIND,
            "protocol_sha256": canonical_hash(config),
            "candidate_market_rows": len(frame),
            "matched_sec_disclosure_pairs": len(frame),
            "candidate_issuers": int(frame.cik_market.nunique()),
            "development_test_rows": len(predictions) // 2,
            "development_test_years": list(REQUIRED_YEARS),
            "yearly_train_and_test_counts": [
                {"year": f["test_year"], "train_rows": f["train_rows"], "test_rows": f["test_rows"]}
                for f in folds
            ],
            "conditional_prediction_models": ["ridge_controls_only", "ridge_controls_plus_text"],
            "fixed_alpha": FIXED_ALPHA,
            "comparison_status": "EXECUTED_PRIVATELY_NOT_VALIDATED",
            "performance_estimates_published": False,
            "source_approvals": 0, "historical_identity_approvals": 0,
            "human_reviews_inferred": 0, "model_ready": False,
            "final_period_opened": False,
            "exclusions_finalized": False, "study_milestones_completed": [],
            "limitations": [
                "Twenty purposively selected SEC issuers, not the frozen historical large-cap universe",
                "All historical CIK/security links pending approval; open-ended interval semantics unresolved",
                "No validated point-in-time source vintage or historical data availability",
                "Filing/source and benchmark normalization reviews pending",
                "Predictive metrics privately quarantined; not a validated forecast performance claim",
                "Exploratory fixed-alpha and 2015 warmup differ from frozen primary development protocol",
                "Issuer-cluster uncertainty only describes this conditional candidate sample",
            ],
        }
        (stage / "public_summary.json").write_text(json.dumps(public, indent=2, sort_keys=True) + "\n")
        hashes = {}
        for filename in ["candidate_predictions_private.csv", "conditional_metrics_private.json",
                         "public_summary.json"]:
            path = stage / filename
            hashes[filename] = {"sha256": _sha(path.read_bytes()), "bytes": path.stat().st_size}
            os.chmod(path, 0o400)
        receipt = {
            "schema_version": 1, "data_kind": KIND,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "files": hashes, "protocol_sha256": canonical_hash(config),
            "model_ready": False, "final_period_opened": False,
            "research_approval": "none", "source_approvals": 0, "human_reviews_inferred": 0,
            "source_hashes": {k: _sha(v) for k, v in blobs.items()},
            "private_metrics_unreviewed": True,
        }
        (stage / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        os.chmod(stage / "receipt.json", 0o400)
        stage.rename(destination)
    return public
