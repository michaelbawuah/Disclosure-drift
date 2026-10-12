"""Independent Decimal-backed recheck of exploratory SEC-only filing drift.

Separate from the first Pandas group/join logic. Reads only the archived
original SEC feature CSV and the private source-bound descriptive output.
No market returns, company/security identity link or holdout is used.
"""

import csv
import hashlib
import json
import math
import statistics
import tempfile
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

import numpy as np

from .protocol import canonical_hash

STATUS = "INDEPENDENT_SEC_ORIGINAL_DESCRIPTIVE_ISSUER_PAIR_CHECK_NOT_PREDICTION"
SOURCE_KIND = "EXPLORATORY_SEC_ONLY_DISCLOSURE_DRIFT_BALANCED_PANEL_NOT_RETURN_PREDICTION"


def _check(ok, reason):
    if not ok:
        raise ValueError(reason)


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _source(path, cap):
    file = Path(path)
    _check(not file.is_symlink(), "Original SEC source symlinks are forbidden")
    file = file.resolve(strict=True)
    _check(file.is_file() and file.stat().st_size <= cap,
           "Original SEC source is missing or oversized")
    return file.read_bytes()


def _close(a, b, tolerance=1e-12):
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=tolerance)


def _rows_decimal_csv(raw):
    reader = csv.DictReader(raw.decode("utf-8-sig").splitlines(), restkey="EXTRA")
    _check(reader.fieldnames is not None and {
        "observation_id", "cik", "year", "jaccard_distance",
        "previous_tokens", "current_tokens",
    }.issubset(reader.fieldnames), "Original SEC feature dictionary missing fields")
    by_cik_year = {}
    year_counts = Counter()
    for row in reader:
        _check("EXTRA" not in row and None not in row.values(),
               "Original SEC text feature row malformed")
        try:
            year = int(row["year"])
            distance = Decimal(row["jaccard_distance"])
        except (ValueError, InvalidOperation) as e:
            raise ValueError("SEC Jaccard values cannot be reconstituted") from e
        _check(distance.is_finite() and 0 <= distance <= 1
               and 2015 <= year <= 2021
               and len(row["cik"]) == 10 and row["cik"].isdigit(),
               "Invalid original SEC year/CIK/Jaccard source value")
        key = (row["cik"], year)
        _check(key not in by_cik_year, "Duplicate original SEC issuer-year feature row")
        by_cik_year[key] = distance
        year_counts[year] += 1
    _check(len(by_cik_year) == 180
           and dict(sorted(year_counts.items())) == {
               2015: 19, 2016: 19, 2017: 19, 2018: 19,
               2019: 34, 2020: 35, 2021: 35,
           }, "Original SEC descriptive source cohort/years differ")
    return by_cik_year, year_counts


def independently_verify_sec_only_descriptives(original_source, descriptive_dir, out, *,
                                                config, repo_root):
    root = Path(repo_root).resolve(strict=True)
    output = Path(out).resolve()
    _check(not output.exists() and output.is_relative_to(root / "reports"),
           "Independent SEC descriptive review must use a new public report path")
    destination = Path(descriptive_dir).resolve(strict=True)
    receipt_raw = _source(destination / "receipt.json", 128 * 1024)
    public_raw = _source(destination / "public_summary.json", 128 * 1024)
    private_raw = _source(destination / "issuer_changes_private.jsonl", 128 * 1024)
    receipt, public = json.loads(receipt_raw), json.loads(public_raw)
    _check(receipt["status"] == public["status"] == SOURCE_KIND
           and receipt["source_fingerprints"] == public["source_fingerprints"]
           and public["source_fingerprints"]["protocol_sha256"] == canonical_hash(config)
           and receipt["files"]["public_summary.json"]["sha256"] == _sha(public_raw)
           and receipt["files"]["issuer_changes_private.jsonl"]["sha256"] == _sha(private_raw)
           and receipt["human_review_approvals"] == 0
           and public["human_review_approvals_created"] == 0
           and public["market_returns_or_CRSP_identity_data_read"] is False
           and public["full_iXBRL_or_filings_human_reviewed"] is False
           and public["predictive_performance_claimed"] is False
           and public["historical_investable_universe_selected"] is False
           and public["causal_or_population_inference_claimed"] is False
           and public["model_ready"] is False and public["final_period_opened"] is False
           and receipt["model_ready"] is False and receipt["final_period_opened"] is False,
           "Source-bound SEC descriptive result has fabricated historical/model/review approvals")
    source_dir = Path(original_source).resolve(strict=True)
    source_blob = _source(source_dir / "text_features.csv", 2 * 1024 * 1024)
    _check(_sha(source_blob) == public["source_fingerprints"]["features_sha256"],
           "Original SEC text features changed since descriptive first pass")
    checkpoint = json.loads(_source(source_dir / "pilot_checkpoint.json", 128 * 1024))
    _check(checkpoint["data_kind"] == "REAL_SEC_TEXT_DESCRIPTIVE_PILOT"
           and checkpoint["files"]["text_features.csv"] == _sha(source_blob)
           and checkpoint["source_audit_passes"] == 215
           and checkpoint["human_filing_reviews"] == 0
           and checkpoint["returns_read"] is False
           and checkpoint["milestone_06_complete"] is False,
           "SEC historical source report lost its original source-only scope")
    by_key, year_counts = _rows_decimal_csv(source_blob)
    yrs = (2019, 2020, 2021)
    issuers = sorted({
        cik for cik, _ in by_key
        if all((cik, year) in by_key for year in yrs)
    })
    _check(len(issuers) == public["balanced_issuer_count"] == 34,
           "Previously balanced 34 original SEC issuer trajectories differ")
    raw_private = [json.loads(line) for line in private_raw.decode().splitlines()]
    private = {}
    for item in raw_private:
        key = (item["cik"], item["from_year"], item["to_year"])
        _check(key not in private, "Duplicate private source descriptive change observation")
        private[key] = item["difference"]
    _check(len(private) == 34 * 3, "Wrong number of private paired issuer changes")
    recomputed = []
    for previous_year, current_year in ((2019, 2020), (2020, 2021), (2019, 2021)):
        diffs = []
        for issuer in issuers:
            diff = by_key[(issuer, current_year)] - by_key[(issuer, previous_year)]
            _check(_close(diff, private[(issuer, previous_year, current_year)]),
                   "Independent original SEC issuer-level Jaccard change differs from saved private evidence")
            diffs.append(diff)
        mean = sum(diffs, Decimal(0)) / Decimal(len(diffs))
        median = statistics.median(diffs)
        positive = sum(x > 0 for x in diffs)
        negative = sum(x < 0 for x in diffs)
        equal = sum(x == 0 for x in diffs)
        saved = next(x for x in public["exploratory_balanced_jaccard_contrasts"]
                     if x["start_year"] == previous_year and x["end_year"] == current_year)
        _check(
            len(diffs) == saved["matched_issuers"] == 34
            and positive == saved["increased"]
            and negative == saved["decreased"]
            and equal == saved["unchanged"]
            and _close(mean, saved["paired_mean_jaccard_distance_difference"])
            and _close(median, saved["paired_median_jaccard_distance_difference"]),
            "SEC-only balanced paired issuer counts or mean/median drift cannot be independently reconciled",
        )
        ordered = [float(n) for n in diffs]
        rng = np.random.default_rng(config["seed"])
        picks = rng.integers(0, len(ordered), size=(5000, len(ordered)))
        ci = np.quantile(np.asarray(ordered)[picks].mean(axis=1), (0.025, 0.975))
        _check(
            len(saved["conditional_issuer_bootstrap_mean_95pct_interval"]) == 2
            and all(_close(a, b) for a, b in zip(
                ci, saved["conditional_issuer_bootstrap_mean_95pct_interval"], strict=True
            )),
            "Issuer-resampling uncertainty does not independently match fixed-source bootstrap",
        )
        loo = [
            (sum(diffs, Decimal(0)) - d) / Decimal(len(diffs) - 1)
            for d in diffs
        ]
        _check(all(_close(a, b) for a, b in zip(
            [min(loo), max(loo)], saved["leave_one_issuer_out_mean_difference_range"],
            strict=True,
        )), "SEC-only leave-one-issuer-out source sensitivity differs")
        recomputed.append({
            "begin_year": previous_year, "end_year": current_year,
            "issuer_count": len(diffs), "mean": float(mean),
            "median": float(median), "increase_count": positive,
        })
    balanced = public["balanced_2019_2021_year_coverage"]
    _check([x["year"] for x in balanced] == list(yrs),
           "Balanced SEC year source report differs")
    for observed in balanced:
        values = [by_key[(issuer, observed["year"])] for issuer in issuers]
        _check(
            len(values) == observed["issuers"] == 34
            and _close(sum(values, Decimal(0)) / Decimal(len(values)),
                       observed["jaccard_distance"]["mean"])
            and _close(statistics.median(values), observed["jaccard_distance"]["median"]),
            "Original source year-level descriptive means/medians differ",
        )
    for row in public["original_acceptance_year_coverage"]:
        vals = [value for (issuer, year), value in by_key.items() if year == row["year"]]
        _check(
            len(vals) == row["filing_pairs"] == year_counts[row["year"]]
            and _close(sum(vals, Decimal(0)) / Decimal(len(vals)),
                       row["jaccard_distance"]["mean"])
            and _close(statistics.median(vals), row["jaccard_distance"]["median"]),
            "Original unbalanced SEC year-level source Jaccard statistics differ",
        )
    _check(_sha(_source(source_dir / "text_features.csv", 2 * 1024 * 1024))
           == public["source_fingerprints"]["features_sha256"],
           "Original SEC source changed during independent calculation")
    summary = {
        "schema_version": 1, "status": STATUS,
        "original_SEC_disclosure_pairs_checked": len(by_key),
        "distinct_original_SEC_issuers_in_source": len({issuer for issuer, _ in by_key}),
        "matched_balanced_2019_2021_issuers": len(issuers),
        "independent_decimal_source_year_means_medians_verified": True,
        "all_private_issuer_year_differences_verified": True,
        "all_three_paired_year_delta_and_sign_counts_verified": True,
        "bootstrap_and_leave_one_issuer_out_diagnostics_verified": True,
        "independent_descriptive_contrasts": recomputed,
        "source_fingerprints": {
            "original_features_sha256": _sha(source_blob),
            "first_descriptive_receipt_sha256": _sha(receipt_raw),
            "first_descriptive_public_sha256": _sha(public_raw),
            "frozen_protocol_sha256": canonical_hash(config),
        },
        "historical_market_or_identity_data_used": False,
        "human_filing_reviews_inferred": 0,
        "causal_claim_or_population_inference_validated": False,
        "empirical_stock_return_forecast_approved": False,
        "model_ready": False, "final_period_opened": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".independent-sec-descriptive-", dir=output.parent) as scratch:
        destination = Path(scratch) / "summary.json"
        destination.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        destination.replace(output)
    return summary
