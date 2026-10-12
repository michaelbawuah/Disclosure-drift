"""Independent original SEC 34-issuer alternative-metric source audit.

Reparses original CSV via csv/Decimal, not the first Pandas feature loader.
No CRSP records, stock returns, future SEC observations or sealed holdout.
"""

import csv
import hashlib
import json
import math
import statistics
import tempfile
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

import numpy as np

from .protocol import canonical_hash

STATUS = "INDEPENDENT_ORIGINAL_SEC_ALTERNATIVE_METRIC_SENSITIVITY_VERIFIED_NOT_PREDICTIVE"
UPSTREAM = "SEC_ONLY_ALTERNATIVE_TEXT_METRICS_EXPLORATORY_SENSITIVITY_NOT_PREDICTIVE"
FIRST_SOURCE = "EXPLORATORY_SEC_ONLY_DISCLOSURE_DRIFT_BALANCED_PANEL_NOT_RETURN_PREDICTION"


def _check(ok, message):
    if not ok:
        raise ValueError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(path, limit):
    file = Path(path)
    _check(not file.is_symlink(), "Linked source file forbidden")
    file = file.resolve(strict=True)
    _check(file.is_file() and file.stat().st_size <= limit,
           "Original SEC source unreadable or oversized")
    return file.read_bytes()


def _match(a, b, abs_tol=1e-12):
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=abs_tol)


def _average_tie_ranks(values):
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i + 1
        while j < len(indexed) and indexed[i][1] == indexed[j][1]:
            j += 1
        mean_rank = (i + 1 + j) / 2
        for k in range(i, j):
            ranks[indexed[k][0]] = mean_rank
        i = j
    return ranks


def _rho(xs, ys):
    x = _average_tie_ranks([round(v, 12) for v in xs])
    y = _average_tie_ranks([round(v, 12) for v in ys])
    mx, my = statistics.mean(x), statistics.mean(y)
    cross = sum((u - mx) * (v - my) for u, v in zip(x, y, strict=True))
    d1 = sum((u - mx)**2 for u in x)
    d2 = sum((v - my)**2 for v in y)
    if d1 == 0 or d2 == 0:
        return None  # Constant-valued source differences have no defined Spearman rho.
    return cross / math.sqrt(d1 * d2)


def independently_verify_metric_sensitivity(source_dir, baseline_dir, audit_dir,
                                            output, *, config, repo_root):
    repo = Path(repo_root).resolve(strict=True)
    dest = Path(output).resolve()
    _check(not dest.exists() and dest.is_relative_to(repo / "reports"),
           "Use a fresh aggregate verification path under reports")
    directory = Path(audit_dir).resolve(strict=True)
    public_raw = _read(directory / "public_summary.json", 256000)
    private_raw = _read(directory / "private_issuer_metric_changes.jsonl", 256000)
    receipt_raw = _read(directory / "receipt.json", 128000)
    public, receipt = json.loads(public_raw), json.loads(receipt_raw)
    _check(
        public["status"] == receipt["status"] == UPSTREAM
        and public["provenance"] == receipt["source_fingerprints"]
        and public["provenance"]["frozen_protocol_sha256"] == canonical_hash(config)
        and receipt["source_approvals"] == 0
        and receipt["files"]["public_summary.json"]["sha256"] == _sha(public_raw)
        and receipt["files"]["private_issuer_metric_changes.jsonl"]["sha256"] == _sha(private_raw)
        and public["market_returns_or_historical_CIK_PERMNO_sources_read"] is False
        and public["new_human_filing_reviews_claimed"] == 0
        and public["forecast_improvement_claimed"] is False
        and public["representative_investable_universe_claimed"] is False
        and public["confirmatory_hypothesis_or_causal_attribution_claimed"] is False
        and public["model_ready"] is False and public["final_period_opened"] is False,
        "Original alternative-metric descriptive source falsely claims empirical approval",
    )
    base = Path(baseline_dir).resolve(strict=True)
    baseline_public_raw = _read(base / "public_summary.json", 256000)
    baseline_receipt_raw = _read(base / "receipt.json", 128000)
    _check(public["provenance"]["first_SEC_descriptive_receipt_sha256"]
           == _sha(baseline_receipt_raw)
           and public["provenance"]["first_SEC_descriptive_public_sha256"]
           == _sha(baseline_public_raw)
           and json.loads(baseline_public_raw)["status"] == FIRST_SOURCE,
           "Original SEC-only baseline features/balanced panel changed")
    sec_root = Path(source_dir).resolve(strict=True)
    csv_blob = _read(sec_root / "text_features.csv", 2 * 1024 * 1024)
    _check(_sha(csv_blob) == public["provenance"]["features_sha256"],
           "Original SEC text source hash no longer matches alternative audit")
    original = defaultdict(dict)
    reader = csv.DictReader(csv_blob.decode("utf-8-sig").splitlines(), restkey="EXTRA")
    _check(reader.fieldnames is not None and {
        "cik", "year", "log_length_change", "tfidf_cosine_distance",
        "jaccard_distance", "previous_tokens", "current_tokens",
    }.issubset(reader.fieldnames),
           "Missing original SEC feature metrics required for independence")
    seen = set()
    for row in reader:
        _check("EXTRA" not in row and None not in row.values(),
               "Malformed original SEC feature CSV line")
        cik, year = row["cik"], int(row["year"])
        _check(len(cik) == 10 and cik.isdigit()
               and 2015 <= year <= 2021 and (cik, year) not in seen,
               "Invalid source SEC issuer/year or repeated observation")
        seen.add((cik, year))
        prior = int(row["previous_tokens"])
        current = int(row["current_tokens"])
        _check(prior > 0 and current > 0, "Invalid SEC risk text token counts")
        expected_log = math.log1p(current) - math.log1p(prior)
        observed_log = float(row["log_length_change"])
        _check(_match(expected_log, observed_log, 1e-11),
               "SEC annual text length metric is not supported by source token counts")
        try:
            jaccard = Decimal(row["jaccard_distance"])
            tfidf = Decimal(row["tfidf_cosine_distance"]) if row["tfidf_cosine_distance"] else None
        except InvalidOperation as exc:
            raise ValueError("Original SEC cosine/Jaccard metrics are malformed") from exc
        _check(jaccard.is_finite() and 0 <= jaccard <= 1
               and (tfidf is None if year == 2015
                    else tfidf is not None and tfidf.is_finite() and 0 <= tfidf <= 1),
               "Original Jaccard or growing-vocabulary TF-IDF metric invalid")
        original[cik][year] = {
            "jaccard_distance": jaccard,
            "tfidf_cosine_distance": tfidf,
            "log_length_change": Decimal(row["log_length_change"]),
        }
    _check(len(seen) == 180 and len(original) == 35,
           "Original SEC 180-feature / 35-issuer source scope changed")
    balanced = sorted(cik for cik, values in original.items()
                      if {2019, 2020, 2021}.issubset(values))
    _check(len(balanced) == public["balanced_2019_2021_issuers"] == 34,
           "Balanced SEC source issuer subset has changed")
    saved_changes = {}
    for raw in private_raw.decode().splitlines():
        item = json.loads(raw)
        key = (item["metric"], item["from_year"], item["to_year"], item["cik"])
        _check(key not in saved_changes,
               "Duplicate private issuer-metric source comparison")
        saved_changes[key] = item["paired_metric_difference"]
    _check(len(saved_changes) == 34 * 3 * 3,
           "Missing 34 issuer observations for three metrics and three paired comparisons")
    expected_metrics = ("log_length_change", "tfidf_cosine_distance", "jaccard_distance")
    contrasts = []
    rho_data = {}
    for metric in expected_metrics:
        for start, end in ((2019, 2020), (2020, 2021), (2019, 2021)):
            d = []
            for cik in balanced:
                difference = original[cik][end][metric] - original[cik][start][metric]
                _check(_match(difference, saved_changes[(metric, start, end, cik)]),
                       "Original SEC issuer metric change differs from locked private evidence")
                d.append(difference)
            mean = sum(d) / Decimal(34)
            median = statistics.median(d)
            plus = sum(x > 0 for x in d)
            minus = sum(x < 0 for x in d)
            unchanged = sum(x == 0 for x in d)
            found = next(
                x for x in public["metrics_and_paired_year_results"]
                if (x["metric"], x["from_year"], x["to_year"]) == (metric, start, end)
            )
            _check(
                found["balanced_issuer_count"] == 34
                and found["increased"] == plus
                and found["decreased"] == minus
                and found["unchanged"] == unchanged
                and _match(mean, found["mean_paired_change"])
                and _match(median, found["median_paired_change"]),
                "Independently recomputed SEC alternative metric mean/median/sign counts differ",
            )
            leave = [
                (sum(d) - x) / Decimal(33) for x in d
            ]
            _check(all(_match(a, b) for a, b in zip(
                (min(leave), max(leave)),
                found["leave_one_issuer_out_mean_range"], strict=True,
            )), "Original SEC alternative-metric leave-one-out source arithmetic mismatch")
            values = sorted(d)
            trimmed = sum(values[3:-3]) / Decimal(28)
            _check(_match(trimmed, found["10percent_trimmed_mean_paired_change"]),
                   "Original SEC alternative-metric trimmed mean source arithmetic mismatch")
            rng = np.random.default_rng(config["seed"])
            draws = rng.integers(0, 34, size=(5000, 34))
            ar = np.asarray([float(v) for v in d])
            interval = np.quantile(ar[draws].mean(axis=1), (0.025, 0.975))
            _check(
                found["issuer_bootstrap_draws"] == 5000
                and all(_match(a, b) for a, b in zip(
                    interval, found["conditional_issuer_bootstrap_95pct_interval"], strict=True
                )),
                "Original SEC issuer bootstrap is inconsistent with source differences",
            )
            year_before = sum(original[cik][start][metric] for cik in balanced) / Decimal(34)
            year_after = sum(original[cik][end][metric] for cik in balanced) / Decimal(34)
            _check(
                _match(year_before, found["year_mean_before"])
                and _match(year_after, found["year_mean_after"]),
                "Source year feature means don't support paired SEC sensitivity",
            )
            if start == 2019 and end == 2021:
                rho_data[metric] = [float(v) for v in d]
            contrasts.append({
                "metric": metric, "from_year": start, "to_year": end,
                "issuers": 34, "mean_paired_change": float(mean),
                "increased": plus, "decreased": minus,
            })
    for metric in ("log_length_change", "tfidf_cosine_distance"):
        calculated = _rho(rho_data["jaccard_distance"], rho_data[metric])
        observed = public["spearman_of_2019_to_2021_issuer_delta_against_Jaccard"][metric]
        _check(
            (calculated is None and observed is None)
            or (calculated is not None and observed is not None and _match(calculated, observed)),
            "Original source Jaccard/alternative metric rank concordance not independently supported",
        )
    _check(_sha(_read(sec_root / "text_features.csv", 2 * 1024 * 1024))
           == public["provenance"]["features_sha256"],
           "SEC source feature bytes changed during independent calculations")
    result = {
        "schema_version": 1, "status": STATUS,
        "source_SEC_item1a_annual_pairs_rechecked": len(seen),
        "original_source_issuer_count": len(original),
        "balanced_2019_2021_issuer_count": len(balanced),
        "alternative_metric_source_token_lengths_recomputed": True,
        "all_306_private_issuer_changes_verified": True,
        "paired_means_medians_signs_trim_and_leave_one_out_verified": True,
        "issuer_bootstrap_and_Spearman_concordance_verified": True,
        "reconstructed_metric_contrasts": contrasts,
        "source_fingerprints": {
            "SEC_original_text_feature_sha256": _sha(csv_blob),
            "primary_sensitivity_receipt_sha256": _sha(receipt_raw),
            "original_SEC_descriptive_receipt_sha256": _sha(baseline_receipt_raw),
            "frozen_protocol_sha256": canonical_hash(config),
        },
        "TFIDF_original_expanding_vocabulary_not_fixed_scale": True,
        "population_causal_or_stock_return_forecast_claim": False,
        "historical_returns_or_CIK_security_mapping_read": False,
        "human_reviews_inferred": 0,
        "model_ready": False, "final_period_opened": False,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".independent-sec-altmetrics-", dir=dest.parent) as work:
        file = Path(work) / "independent.json"
        file.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        file.replace(dest)
    return result
