"""Alternative SEC-only text-change metrics on the original fixed 34 issuer panel.

Metrics are precomputed original SEC features. They are exploratory descriptive
sensitivity, not a preregistered confirmatory comparison or market prediction.
TF-IDF uses expanding prior-year vocabularies and is NOT treated as fixed-scale
year-over-year semantic or causal change.
"""

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .protocol import canonical_hash
from .sec_only_disclosure_descriptives import _load_approved_as_descriptive_source

STATUS = "SEC_ONLY_ALTERNATIVE_TEXT_METRICS_EXPLORATORY_SENSITIVITY_NOT_PREDICTIVE"
FIRST = "EXPLORATORY_SEC_ONLY_DISCLOSURE_DRIFT_BALANCED_PANEL_NOT_RETURN_PREDICTION"
METRICS = ("log_length_change", "tfidf_cosine_distance", "jaccard_distance")
OBSERVED_YEARS = (2019, 2020, 2021)
DRAWS = 5000


def _require(ok, why):
    if not ok:
        raise ValueError(why)


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _read(path, max_bytes):
    p = Path(path)
    _require(not p.is_symlink(), "Source cannot be a symlink")
    p = p.resolve(strict=True)
    _require(p.is_file() and p.stat().st_size <= max_bytes,
             "Original SEC descriptive source missing/oversized")
    return p.read_bytes()


def _metric_contrast(group, metric, first, last, seed):
    start = group.loc[group.year == first].set_index("cik")[metric]
    end = group.loc[group.year == last].set_index("cik")[metric]
    _require(start.index.is_unique and end.index.is_unique
             and len(start) == len(end) == 34
             and set(start.index) == set(end.index),
             "Balanced issuer set changed between descriptive years")
    identities = sorted(start.index)
    delta = end.loc[identities].to_numpy(dtype=float) - start.loc[identities].to_numpy(dtype=float)
    _require(len(delta) == 34 and np.isfinite(delta).all(),
             "Original SEC alternative metric differences contain invalid values")
    bootstrap = np.random.default_rng(seed).integers(0, 34, size=(DRAWS, 34))
    bound = np.quantile(delta[bootstrap].mean(axis=1), [0.025, 0.975])
    omit_one = (delta.sum() - delta) / 33
    sorted_delta = np.sort(delta)
    return {
        "metric": metric, "from_year": first, "to_year": last,
        "balanced_issuer_count": 34,
        "year_mean_before": float(start.mean()),
        "year_mean_after": float(end.mean()),
        "mean_paired_change": float(delta.mean()),
        "median_paired_change": float(np.median(delta)),
        "increased": int((delta > 0).sum()),
        "decreased": int((delta < 0).sum()),
        "unchanged": int((delta == 0).sum()),
        "10percent_trimmed_mean_paired_change": float(sorted_delta[3:-3].mean()),
        "leave_one_issuer_out_mean_range": [float(omit_one.min()), float(omit_one.max())],
        "issuer_bootstrap_draws": DRAWS,
        "conditional_issuer_bootstrap_95pct_interval": [float(bound[0]), float(bound[1])],
    }, {identity: float(change) for identity, change in zip(identities, delta, strict=True)}


def _rank_correlation(values1, values2):
    # Spearman's rho is the ordinary Pearson correlation of average-tie ranks.
    if values1.shape != values2.shape or values1.ndim != 1:
        raise ValueError("Invalid correlation input")
    import pandas as pd

    # Quantize only for rank ordering: IEEE subtraction of algebraically
    # identical source values can differ in their last few binary bits,
    # generating false "different" ranks for tied issuer deltas.
    ranks1 = pd.Series(np.round(values1, decimals=12)).rank(method="average").to_numpy()
    ranks2 = pd.Series(np.round(values2, decimals=12)).rank(method="average").to_numpy()
    # With 34 identical change values the rank correlation is mathematically
    # undefined, not zero and definitely not a fabricated strong correlation.
    if np.ptp(ranks1) == 0 or np.ptp(ranks2) == 0:
        return None
    out = float(np.corrcoef(ranks1, ranks2)[0, 1])
    _require(np.isfinite(out) and -1 <= out <= 1,
             "Nonfinite SEC text metric directional concordance")
    return out


def build_sec_metric_sensitivity(source_dir, baseline_dir, output, *, config, repo_root):
    repo = Path(repo_root).resolve(strict=True)
    destination = Path(output).resolve()
    _require(not destination.exists() and destination.is_relative_to(repo / "outputs")
             and destination != repo / "outputs",
             "Alternative metric audit needs a fresh private outputs directory")
    features, source_hashes, inputs = _load_approved_as_descriptive_source(source_dir, config)
    base = Path(baseline_dir).resolve(strict=True)
    receipt_blob = _read(base / "receipt.json", 200000)
    public_blob = _read(base / "public_summary.json", 200000)
    private_blob = _read(base / "issuer_changes_private.jsonl", 256000)
    receipt = json.loads(receipt_blob)
    _require(
        receipt["files"]["public_summary.json"]["sha256"] == _sha(public_blob)
        and receipt["files"]["issuer_changes_private.jsonl"]["sha256"] == _sha(private_blob),
        "Previous SEC-only baseline descriptive source or review gates differ",
    )
    public = json.loads(public_blob)
    _require(
        receipt["status"] == public["status"] == FIRST
        and receipt["files"]["public_summary.json"]["sha256"] == _sha(public_blob)
        and receipt["files"]["issuer_changes_private.jsonl"]["sha256"] == _sha(private_blob)
        and receipt["source_fingerprints"] == public["source_fingerprints"] == source_hashes
        and public["balanced_issuer_count"] == 34
        and public["market_returns_or_CRSP_identity_data_read"] is False
        and public["predictive_performance_claimed"] is False
        and public["causal_or_population_inference_claimed"] is False
        and public["human_review_approvals_created"] == 0
        and public["model_ready"] is False
        and public["final_period_opened"] is False
        and receipt["model_ready"] is False
        and receipt["final_period_opened"] is False,
        "Previous SEC-only baseline descriptive source or review gates differ",
    )
    yrs = features.groupby("cik")["year"].apply(set)
    balanced_ids = sorted(cik for cik, observed in yrs.items()
                          if set(OBSERVED_YEARS).issubset(observed))
    _require(len(balanced_ids) == 34,
             "Expected the exact 34 original SEC issuer-year balanced cohort")
    frame = features.loc[
        features.cik.isin(balanced_ids) & features.year.isin(OBSERVED_YEARS)
    ].sort_values(["cik", "year"])
    _require(len(frame) == 102 and frame[["cik", "year"]].duplicated().sum() == 0,
             "The original SEC balanced panel has duplicate/missing issuer-years")
    summary = []
    private_changes = {}
    for metric in METRICS:
        for old, new in ((2019, 2020), (2020, 2021), (2019, 2021)):
            entry, issuer_deltas = _metric_contrast(frame, metric, old, new, config["seed"])
            summary.append(entry)
            private_changes[(metric, old, new)] = issuer_deltas
    for old, new in ((2019, 2020), (2020, 2021), (2019, 2021)):
        baseline = next(
            item for item in public["exploratory_balanced_jaccard_contrasts"]
            if (item["start_year"], item["end_year"]) == (old, new)
        )
        measured = next(
            item for item in summary if
            (item["metric"], item["from_year"], item["to_year"])
            == ("jaccard_distance", old, new)
        )
        for a, b in (
            (baseline["paired_mean_jaccard_distance_difference"], measured["mean_paired_change"]),
            (baseline["paired_median_jaccard_distance_difference"], measured["median_paired_change"]),
            (baseline["increased"], measured["increased"]),
            (baseline["decreased"], measured["decreased"]),
        ):
            _require(np.isclose(a, b, atol=1e-13, rtol=0),
                     "Previously published original SEC Jaccard statistic has changed")
    rho = {}
    reference = private_changes[("jaccard_distance", 2019, 2021)]
    for metric in ("log_length_change", "tfidf_cosine_distance"):
        comparison = private_changes[(metric, 2019, 2021)]
        _require(set(reference) == set(comparison), "Original SEC paired issuers not identical")
        v = np.array([reference[issuer] for issuer in balanced_ids])
        u = np.array([comparison[issuer] for issuer in balanced_ids])
        rho[metric] = _rank_correlation(v, u)
    for name, path in inputs.items():
        _require(_sha(path.read_bytes()) == source_hashes[name + "_sha256"],
                 "Original SEC feature/manifest source modified during audit")
    public_result = {
        "schema_version": 1, "status": STATUS,
        "source_scope": "original 215 SEC filings, 180 Item 1A pairs, purposive 35 issuer pilot",
        "balanced_2019_2021_issuers": len(balanced_ids),
        "metrics_and_paired_year_results": summary,
        "spearman_of_2019_to_2021_issuer_delta_against_Jaccard": rho,
        "metric_interpretations": {
            "log_length_change": (
                "Difference between log(1+current risk tokens) and log(1+previous "
                "risk tokens). Compares annual growth rates of extracted text length."
            ),
            "tfidf_cosine_distance": (
                "Original prior-year-only vocabulary TF-IDF cosine distance. "
                "Training vocabulary differs by year; contrasts across years "
                "are sensitivity observations, NOT fixed-vocabulary effects."
            ),
            "jaccard_distance": (
                "1-token-set similarity; reproduced as unchanged baseline, "
                "not an additional independent source metric."
            ),
        },
        "provenance": {
            **source_hashes,
            "first_SEC_descriptive_receipt_sha256": _sha(receipt_blob),
            "first_SEC_descriptive_public_sha256": _sha(public_blob),
            "first_SEC_descriptive_private_changes_sha256": _sha(private_blob),
            "frozen_protocol_sha256": canonical_hash(config),
        },
        "original_filing_sources_and_text_features_unchanged": True,
        "market_returns_or_historical_CIK_PERMNO_sources_read": False,
        "new_human_filing_reviews_claimed": 0,
        "confirmatory_hypothesis_or_causal_attribution_claimed": False,
        "representative_investable_universe_claimed": False,
        "forecast_improvement_claimed": False,
        "model_ready": False, "final_period_opened": False,
        "limitations": [
            "Purposive issuer selection and incomplete human boundary review",
            "Log text length differs from Jaccard token-set change",
            "TF-IDF expanding historical vocabularies prohibit interpreting contrast as constant-feature-space effect",
            "Bootstrap intervals are conditional on the same selected 34 issuers",
            "No causation, probability sample or historical point-in-time returns used",
        ],
    }
    private = [
        {"metric": metric, "from_year": old, "to_year": new,
         "cik": cik, "paired_metric_difference": value}
        for (metric, old, new), values in sorted(private_changes.items())
        for cik, value in sorted(values.items())
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sec-metric-sensitivity-", dir=destination.parent) as scratch:
        stage = Path(scratch) / "result"
        stage.mkdir(mode=0o700)
        (stage / "private_issuer_metric_changes.jsonl").write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in private)
        )
        (stage / "public_summary.json").write_text(json.dumps(public_result, indent=2, sort_keys=True) + "\n")
        receipt = {
            "schema_version": 1, "status": STATUS,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_fingerprints": public_result["provenance"],
            "files": {
                name: {"sha256": _sha((stage / name).read_bytes()),
                       "bytes": (stage / name).stat().st_size}
                for name in ("private_issuer_metric_changes.jsonl", "public_summary.json")
            },
            "source_approvals": 0, "model_ready": False, "final_period_opened": False,
        }
        (stage / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        for path in stage.iterdir():
            os.chmod(path, 0o400)
        stage.rename(destination)
    return public_result
