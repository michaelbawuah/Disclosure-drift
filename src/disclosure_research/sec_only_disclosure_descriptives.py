"""Exploratory descriptive risk-disclosure changes in a purposive SEC-only panel.

Uses only already source-audited original SEC Item 1A feature CSV, never
market returns, the CIK-PERMNO crosswalk or the 2022-2025 holdout.

This is not the frozen empirical forecast study or a representative sample.
"""

import csv
import hashlib
import io
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import pandas as pd

from .protocol import canonical_hash

STATUS = "EXPLORATORY_SEC_ONLY_DISCLOSURE_DRIFT_BALANCED_PANEL_NOT_RETURN_PREDICTION"
SOURCE_KIND = "REAL_SEC_TEXT_DESCRIPTIVE_PILOT"
SOURCE_STATUS = "source_verified_descriptive_pilot"
FIRST_YEAR = 2015
LAST_YEAR = 2021
BALANCED = (2019, 2020, 2021)
BOOTSTRAP_DRAWS = 5000
REQUIRED_FIELDS = (
    "observation_id", "cik", "year", "previous_tokens",
    "current_tokens", "log_length_change", "jaccard_distance",
    "tfidf_cosine_distance", "vocabulary_training_pairs",
    "source_url", "previous_source_url",
)


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _source(path, limit):
    p = Path(path)
    _require(not p.is_symlink(), "Linked source file is not permitted")
    p = p.resolve(strict=True)
    _require(p.is_file() and p.stat().st_size <= limit,
             "Source file absent or unexpectedly large")
    return p, p.read_bytes()


def _is_sec_original_url(url, cik):
    if not isinstance(url, str):
        return False
    parsed = urlsplit(url)
    prefix = f"/Archives/edgar/data/{int(cik)}/"
    return (
        parsed.scheme == "https"
        and parsed.netloc == "www.sec.gov"
        and parsed.path.startswith(prefix)
        and len(parsed.path) > len(prefix)
        and not parsed.query and not parsed.fragment
        and not parsed.username and not parsed.password
    )


def _load_approved_as_descriptive_source(sources, config):
    directory = Path(sources).resolve(strict=True)
    paths = {
        "features": directory / "text_features.csv",
        "manifest": directory / "filing_sources.csv",
        "checkpoint": directory / "pilot_checkpoint.json",
        "combination_receipt": directory / "combination_receipt.json",
    }
    loaded = {k: _source(v, 2 * 1024 * 1024) for k, v in paths.items()}
    blobs = {k: v[1] for k, v in loaded.items()}
    checkpoint = json.loads(blobs["checkpoint"])
    combined = json.loads(blobs["combination_receipt"])
    protocol = canonical_hash(config)
    _require(checkpoint["data_kind"] == combined["data_kind"] == SOURCE_KIND
             and combined["status"] == SOURCE_STATUS
             and combined["protocol_sha256"] == checkpoint["protocol_sha256"] == protocol,
             "Not the preserved SEC-only descriptive source/protocol")
    _require(
        checkpoint["files"]["text_features.csv"] == _sha(blobs["features"])
        and checkpoint["files"]["coverage_by_year.csv"] is not None
        and checkpoint["filings"] == combined["filings"] == 215
        and checkpoint["pairs"] == combined["pairs"] == 180
        and checkpoint["issuers"] == combined["issuers"] == 35
        and checkpoint["source_audit_passes"] == 215
        and checkpoint["human_filing_reviews"] == 0
        and checkpoint["reference_resolutions"] == 19
        and checkpoint["milestone_06_complete"] is False
        and checkpoint["returns_read"] is False
        and checkpoint["predictive_performance_claim"] is False
        and combined["returns_read"] is False
        and combined["historical_universe_claim"] is False
        and combined["predictive_performance_claim"] is False
        and combined["source_audit"]["human_reviews_complete"] == 0,
        "Original SEC descriptive source coverage/review-status receipt differs",
    )
    features = pd.read_csv(
        io.BytesIO(blobs["features"]),
        dtype={
            "cik": str, "observation_id": str,
            "source_url": str, "previous_source_url": str,
        },
    )
    _require(
        len(features) == 180
        and set(REQUIRED_FIELDS).issubset(features.columns)
        and features["observation_id"].is_unique,
        "Expected 180 uniquely identified original SEC annual disclosure changes",
    )
    _require(
        features["cik"].map(
            lambda value: isinstance(value, str) and len(value) == 10
            and value.isascii() and value.isdigit(),
        ).all(),
        "Original SEC CIKs have invalid/changed padding",
    )
    _require(
        features["year"].map(lambda x: isinstance(x, (int, np.integer))).all()
        and features["year"].between(FIRST_YEAR, LAST_YEAR).all(),
        "SEC-only descriptive source includes future or malformed filing years",
    )
    for col in ("previous_tokens", "current_tokens", "vocabulary_training_pairs"):
        _require(
            pd.api.types.is_integer_dtype(features[col])
            and features[col].notna().all(),
            f"Non-integer or missing original feature counts: {col}",
        )
    _require(features["previous_tokens"].ge(1).all()
             and features["current_tokens"].ge(1).all(),
             "Empty extracted risk-factor filing token counts are not comparable")
    for col in ("log_length_change", "jaccard_distance", "tfidf_cosine_distance"):
        _require(
            pd.api.types.is_numeric_dtype(features[col])
            and np.isfinite(features[col].dropna().to_numpy(dtype=float)).all(),
            f"Source SEC text features are invalid/nonfinite: {col}",
        )
    _require(features["jaccard_distance"].notna().all()
             and features["jaccard_distance"].between(0, 1).all(),
             "Unexpected original Jaccard vocabulary-change range")
    computed_length = np.log1p(features["current_tokens"]) - np.log1p(features["previous_tokens"])
    _require(
        np.allclose(computed_length, features["log_length_change"],
                    atol=1e-10, rtol=0),
        "Original length-change feature conflicts with source token counts",
    )
    _require(features.loc[features.year == FIRST_YEAR, "tfidf_cosine_distance"].isna().all()
             and features.loc[features.year > FIRST_YEAR, "tfidf_cosine_distance"].notna().all(),
             "Incorrect earliest-year null TF-IDF vocabulary policy")
    _require(features["tfidf_cosine_distance"].dropna().between(0, 1).all(),
             "TF-IDF feature is not a valid cosine distance")
    yearly = features.groupby("year", sort=True)
    annual_counts = yearly["observation_id"].count().to_dict()
    _require(annual_counts == {
        2015: 19, 2016: 19, 2017: 19, 2018: 19,
        2019: 34, 2020: 35, 2021: 35,
    }, "Original SEC sample year counts differ from checked source selection")
    _require(
        [
            {"year": int(year), "pairs": len(g), "issuers": int(g.cik.nunique())}
            for year, g in yearly
        ] == checkpoint["year_coverage"],
        "SEC sample year/issuer source audit coverage changed",
    )
    for year, g in yearly:
        _require(
            g["vocabulary_training_pairs"].eq(
                sum(n for y, n in annual_counts.items() if y < year)
            ).all(),
            "Future SEC filing tokens were leaked into earlier-year TF-IDF vocabulary",
        )
    rdr = csv.DictReader(io.StringIO(blobs["manifest"].decode("utf-8-sig"), newline=""),
                         restkey="extra")
    _require(rdr.fieldnames is not None and {
        "cik", "accessionNumber", "source_url", "acceptance_timestamp",
        "download_sha256", "header_sha256", "extraction_status",
    }.issubset(rdr.fieldnames), "Missing original SEC source manifest provenance")
    originals = {}
    source_urls = {}
    for line in rdr:
        _require("extra" not in line and None not in line.values(),
                 "Malformed original SEC source manifest record")
        accession = line["accessionNumber"]
        _require(accession not in originals
                 and line["source_url"] not in source_urls
                 and _is_sec_original_url(line["source_url"], line["cik"])
                 and line["extraction_status"] == "ok",
                 "Original SEC source URL/CIK/format record is duplicated or unsupported")
        originals[accession] = line
        source_urls[line["source_url"]] = line
    _require(len(originals) == checkpoint["filings"] == 215,
             "Original SEC source manifest no longer covers all 215 filings")
    for row in features.itertuples(index=False):
        current = originals.get(row.observation_id)
        source = source_urls.get(row.source_url)
        prior = source_urls.get(row.previous_source_url)
        _require(
            current is not None and source is current
            and prior is not None
            and current["cik"] == prior["cik"] == row.cik
            and current["source_url"] == row.source_url
            and prior["source_url"] == row.previous_source_url
            and int(current["acceptance_timestamp"][:4]) == row.year
            and int(prior["acceptance_timestamp"][:4]) == row.year - 1
            and _is_sec_original_url(row.previous_source_url, row.cik),
            "SEC original issuer/year/filing pair does not match immutable original manifest",
        )
    matched = set(features["cik"])
    _require(len(matched) == 35, "SEC descriptive issuer coverage changed")
    return features, {
        "protocol_sha256": protocol,
        **{name + "_sha256": _sha(blob) for name, blob in blobs.items()},
    }, paths


def _summarize(values):
    v = np.asarray(values, dtype=float)
    _require(len(v) > 0 and np.isfinite(v).all(), "Cannot summarize empty/nonfinite source values")
    return {
        "count": int(len(v)),
        "mean": float(v.mean()),
        "median": float(np.median(v)),
        "q25": float(np.quantile(v, 0.25)),
        "q75": float(np.quantile(v, 0.75)),
    }


def _paired_delta(frame, *, old_year, new_year, seed):
    old = frame.loc[frame.year == old_year].set_index("cik")["jaccard_distance"]
    new = frame.loc[frame.year == new_year].set_index("cik")["jaccard_distance"]
    _require(old.index.is_unique and new.index.is_unique
             and set(old.index) == set(new.index),
             "Balanced SEC issuer panel has an unpaired year or duplicate CIK")
    ordered = sorted(old.index)
    d = new.loc[ordered].to_numpy(dtype=float) - old.loc[ordered].to_numpy(dtype=float)
    n = len(d)
    _require(n == 34, "SEC source 2019–2021 balanced issuer comparison must retain 34 issuers")
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, n, size=(BOOTSTRAP_DRAWS, n))
    bootstrap_means = d[samples].mean(axis=1)
    loo = (d.sum() - d) / (n - 1)
    trim = int(math.floor(0.1 * n))
    trimmed = np.sort(d)[trim:n-trim]
    return {
        "start_year": old_year, "end_year": new_year,
        "matched_issuers": n,
        "paired_mean_jaccard_distance_difference": float(d.mean()),
        "paired_median_jaccard_distance_difference": float(np.median(d)),
        "increased": int(np.sum(d > 0)), "decreased": int(np.sum(d < 0)),
        "unchanged": int(np.sum(d == 0)),
        "mean_difference_10pct_trimmed": float(trimmed.mean()),
        "leave_one_issuer_out_mean_difference_range": [
            float(loo.min()), float(loo.max())
        ],
        "issuer_resampling_draws": BOOTSTRAP_DRAWS,
        "conditional_issuer_bootstrap_mean_95pct_interval": [
            float(np.quantile(bootstrap_means, 0.025)),
            float(np.quantile(bootstrap_means, 0.975)),
        ],
        "interpretation": (
            "Exploratory within-purposive-sample paired lexical-set turnover "
            "difference, not a population effect, causal event effect or return prediction."
        ),
    }, [{"cik": cik, "difference": float(v)} for cik, v in zip(ordered, d, strict=True)]


def run_sec_only_descriptives(source_dir, output, *, config, repo_root):
    root = Path(repo_root).resolve(strict=True)
    dest = Path(output).resolve()
    _require(not dest.exists() and dest.is_relative_to(root / "outputs")
             and dest != root / "outputs",
             "SEC descriptive result must use a new private output directory")
    features, provenance, source_paths = _load_approved_as_descriptive_source(source_dir, config)
    issuer_years = features.groupby("cik", sort=True)["year"].apply(set)
    eligible = [
        cik for cik, years in issuer_years.items()
        if set(BALANCED).issubset(years)
    ]
    _require(len(eligible) == 34,
             "Unexpected balanced original SEC 2019–2021 subcohort size")
    panel = features.loc[
        features.year.isin(BALANCED) & features.cik.isin(eligible),
    ].sort_values(["cik", "year"]).copy()
    _require(len(panel) == 34 * 3
             and panel.groupby("cik")["year"].nunique().eq(3).all(),
             "Balanced original SEC descriptive panel incomplete")
    annual_full = []
    for year, group in features.groupby("year", sort=True):
        annual_full.append({
            "year": int(year), "filing_pairs": len(group),
            "issuers": int(group.cik.nunique()),
            "jaccard_distance": _summarize(group["jaccard_distance"]),
            "log_length_change": _summarize(group["log_length_change"]),
            "tfidf_cosine_distance": (
                _summarize(group["tfidf_cosine_distance"].dropna())
                if year > FIRST_YEAR else None
            ),
        })
    annual_balanced = []
    for year, group in panel.groupby("year", sort=True):
        annual_balanced.append({
            "year": int(year), "issuers": int(group.cik.nunique()),
            "jaccard_distance": _summarize(group["jaccard_distance"]),
            "log_length_change": _summarize(group["log_length_change"]),
        })
    contrasts, private_issuer_changes = [], []
    for begin, end in ((2019, 2020), (2020, 2021), (2019, 2021)):
        result, deltas = _paired_delta(panel, old_year=begin, new_year=end,
                                       seed=config["seed"])
        contrasts.append(result)
        private_issuer_changes.extend({
            **item, "from_year": begin, "to_year": end
        } for item in deltas)
    _require(sum(r["filing_pairs"] for r in annual_full) == len(features) == 180
             and all(r["issuers"] == 34 for r in annual_balanced),
             "Source-audited SEC annual result counts do not reconcile")
    for field, path in source_paths.items():
        _require(_sha(path.read_bytes()) == provenance[field + "_sha256"],
                 "Original SEC source changed during descriptive analysis")
    summary = {
        "schema_version": 1, "status": STATUS,
        "data_kind": "REAL_SEC_ORIGINAL_RISK_TEXT_DESCRIPTIVE_SOURCE_ONLY",
        "source_filings": 215, "source_annual_comparisons": 180,
        "source_issuers": 35, "source_years": list(range(2015, 2022)),
        "balanced_issuer_count": len(eligible),
        "balanced_years": list(BALANCED),
        "original_acceptance_year_coverage": annual_full,
        "balanced_2019_2021_year_coverage": annual_balanced,
        "exploratory_balanced_jaccard_contrasts": contrasts,
        "jaccard_definition": (
            "1 minus token-set Jaccard similarity of consecutive original "
            "annual SEC Item 1A Risk Factors disclosures."
        ),
        "primary_descriptive_comparison": "2021-vs-2019 within the same 34 issuer CIKs",
        "source_fingerprints": provenance,
        "all_180_original_SEC_filing_pairs_match_source_manifest_and_prior_year": True,
        "earlier_year_only_TFIDF_vocabulary_check_passed": True,
        "market_returns_or_CRSP_identity_data_read": False,
        "full_iXBRL_or_filings_human_reviewed": False,
        "historical_investable_universe_selected": False,
        "causal_or_population_inference_claimed": False,
        "predictive_performance_claimed": False,
        "human_review_approvals_created": 0,
        "model_ready": False, "milestone_06_complete": False,
        "final_period_opened": False,
        "limitations": [
            "35 purposively selected SEC issuers, not a probability sample or historical investable universe",
            "34 balanced 2019–2021 issuers; historical selection and market data not used",
            "Prior automated SEC source checks passed, but full original filing/manual review is pending",
            "2015 TF-IDF unavailable by correctly earlier-year-only fitting; vocabulary changes across years",
            "Bootstrap interval quantifies variation conditional on the selected issuer observations only",
            "No causal COVID/regulatory attribution or claim that vocabulary drift predicts stock returns",
            "The frozen stock-return evaluation and 2022–2025 final period remain unopened",
        ],
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sec-only-descriptive-", dir=dest.parent) as scratch:
        stage = Path(scratch) / "result"
        stage.mkdir(mode=0o700)
        (stage / "issuer_changes_private.jsonl").write_text(
            "".join(json.dumps(v, sort_keys=True) + "\n"
                    for v in private_issuer_changes)
        )
        (stage / "public_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n"
        )
        receipt = {
            "schema_version": 1, "status": STATUS,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_fingerprints": provenance,
            "files": {
                name: {"sha256": _sha((stage / name).read_bytes()),
                       "bytes": (stage / name).stat().st_size}
                for name in ("issuer_changes_private.jsonl", "public_summary.json")
            },
            "market_data_used": False,
            "human_review_approvals": 0,
            "model_ready": False, "final_period_opened": False,
        }
        (stage / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        for item in stage.iterdir():
            os.chmod(item, 0o400)
        stage.rename(dest)
    return summary
