"""Invented SEC filing and Item 1A feature fixtures, never licensed market data."""

import csv
import hashlib
import json
import math

import pandas as pd
import pytest

from disclosure_research.protocol import canonical_hash, load_protocol
from disclosure_research.sec_only_descriptive_figure import render_sec_only_mean_drift_svg
from disclosure_research.sec_only_disclosure_descriptives import (
    STATUS, _paired_delta, run_sec_only_descriptives,
)
from disclosure_research.sec_only_descriptives_verifier import (
    independently_verify_sec_only_descriptives,
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "repo"
    folder = root / "reports" / "original_sec"
    folder.mkdir(parents=True)
    config = load_protocol()
    year_counts = {2015: 19, 2016: 19, 2017: 19, 2018: 19,
                   2019: 34, 2020: 35, 2021: 35}
    prefix = {year: sum(v for y, v in year_counts.items() if y < year)
              for year in year_counts}
    originals, features = {}, []
    for i in range(35):
        cik = f"{1000000000+i:010d}"
        years = range(2015, 2022) if i < 19 else (
            range(2019, 2022) if i < 34 else range(2020, 2022)
        )
        years = list(years)
        prior_yr = years[0] - 1
        relevant = [prior_yr] + years
        urls = {}
        for year in relevant:
            acc = f'{cik}-{year%100:02d}-{i+1:06d}'
            url = (
                f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/'
                + acc.replace("-", "") + "/invented10k.htm"
            )
            assert acc not in originals
            urls[year] = (acc, url)
            originals[acc] = {
                "cik": cik, "name": f"SYNTHETIC ORIGINAL COMPANY {i}",
                "accessionNumber": acc,
                "acceptance_timestamp": f"{year}-02-18T14:01:00-05:00",
                "source_url": url,
                "extraction_status": "ok",
                "download_sha256": "a" * 64,
                "header_sha256": "b" * 64,
            }
        for year in years:
            acc, url = urls[year]
            old_url = urls[year-1][1]
            previous_tokens = 5000 + i * 45 + year
            current_tokens = previous_tokens + 20 + (year - 2014) * (i % 4 + 1)
            features.append({
                "observation_id": acc, "cik": cik, "year": year,
                "previous_tokens": previous_tokens, "current_tokens": current_tokens,
                "log_length_change": math.log1p(current_tokens) - math.log1p(previous_tokens),
                "jaccard_distance": 0.04 + i * 0.003 + (year-2015) * 0.01,
                "tfidf_cosine_distance": (
                    "" if year == 2015 else 0.001 + i * 0.0003 + year * 0.00001
                ),
                "vocabulary_training_pairs": prefix[year],
                "source_url": url, "previous_source_url": old_url,
            })
    assert len(originals) == 215 and len(features) == 180
    file = folder / "text_features.csv"
    with file.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(features[0]))
        writer.writeheader()
        writer.writerows(features)
    manifest = folder / "filing_sources.csv"
    with manifest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(next(iter(originals.values()))))
        writer.writeheader()
        writer.writerows(originals.values())
    checkpoint = {
        "data_kind": "REAL_SEC_TEXT_DESCRIPTIVE_PILOT",
        "protocol_sha256": canonical_hash(config),
        "filings": 215, "pairs": 180, "issuers": 35,
        "source_audit_passes": 215, "human_filing_reviews": 0,
        "reference_resolutions": 19,
        "milestone_06_complete": False,
        "returns_read": False, "predictive_performance_claim": False,
        "files": {
            "text_features.csv": _sha(file.read_bytes()),
            "coverage_by_year.csv": "source-marker",
        },
        "year_coverage": [
            {"year": year, "pairs": count, "issuers": count}
            for year, count in year_counts.items()
        ],
    }
    (folder / "pilot_checkpoint.json").write_text(json.dumps(checkpoint))
    receipt = {
        "data_kind": "REAL_SEC_TEXT_DESCRIPTIVE_PILOT",
        "protocol_sha256": canonical_hash(config),
        "status": "source_verified_descriptive_pilot",
        "filings": 215, "pairs": 180, "issuers": 35,
        "source_audit": {"human_reviews_complete": 0},
        "returns_read": False, "historical_universe_claim": False,
        "predictive_performance_claim": False,
    }
    (folder / "combination_receipt.json").write_text(json.dumps(receipt))
    return {
        "root": root, "source": folder, "config": config,
        "output": root / "outputs" / "descriptive",
        "independent": root / "reports" / "independent.json",
    }


def refresh_feature_hash(example):
    checkpoint = example["source"] / "pilot_checkpoint.json"
    info = json.loads(checkpoint.read_text())
    info["files"]["text_features.csv"] = _sha(
        (example["source"] / "text_features.csv").read_bytes()
    )
    checkpoint.write_text(json.dumps(info))


def edit_features(example, editor):
    p = example["source"] / "text_features.csv"
    frame = pd.read_csv(p, dtype={"cik": str, "observation_id": str})
    editor(frame)
    frame.to_csv(p, index=False, float_format="%.17g")
    refresh_feature_hash(example)


def run(example):
    return run_sec_only_descriptives(
        example["source"], example["output"],
        config=example["config"], repo_root=example["root"],
    )


def verify(example):
    return independently_verify_sec_only_descriptives(
        example["source"], example["output"], example["independent"],
        config=example["config"], repo_root=example["root"],
    )


def _rehashed_result(example, file, editor):
    location = example["output"] / file
    original = location.read_text()
    changed = editor(original)
    location.chmod(0o600)
    location.write_text(changed)
    receipt_path = example["output"] / "receipt.json"
    receipt_path.chmod(0o600)
    receipt = json.loads(receipt_path.read_text())
    raw = location.read_bytes()
    receipt["files"][file] = {
        "sha256": _sha(raw), "bytes": len(raw),
    }
    receipt_path.write_text(json.dumps(receipt))


def test_180_original_SEC_descriptive_pairs_and_balanced_comparison(source):
    result = run(source)
    assert result["status"] == STATUS
    assert result["source_filings"] == 215
    assert result["source_annual_comparisons"] == 180
    assert result["source_issuers"] == 35
    assert result["balanced_issuer_count"] == 34
    assert len(result["exploratory_balanced_jaccard_contrasts"]) == 3
    assert [x["year"] for x in result["original_acceptance_year_coverage"]] == list(range(2015, 2022))
    assert result["original_acceptance_year_coverage"][0]["tfidf_cosine_distance"] is None
    c = result["exploratory_balanced_jaccard_contrasts"][-1]
    assert c["start_year"] == 2019 and c["end_year"] == 2021
    assert c["matched_issuers"] == 34
    assert c["paired_mean_jaccard_distance_difference"] == pytest.approx(0.02)
    assert c["increased"] == 34 and c["decreased"] == 0
    assert c["conditional_issuer_bootstrap_mean_95pct_interval"] == pytest.approx([0.02, 0.02])
    assert c["leave_one_issuer_out_mean_difference_range"] == pytest.approx([0.02, 0.02])
    assert result["market_returns_or_CRSP_identity_data_read"] is False
    assert not result["historical_investable_universe_selected"]
    assert not result["predictive_performance_claimed"]
    assert not result["final_period_opened"]
    assert not result["model_ready"]
    folder = source["output"]
    assert folder.stat().st_mode & 0o077 == 0
    receipt = json.loads((folder / "receipt.json").read_text())
    for name, meta in receipt["files"].items():
        path = folder / name
        assert _sha(path.read_bytes()) == meta["sha256"]
        assert path.stat().st_mode & 0o222 == 0
    assert "0000000000-20-000001" not in (folder / "public_summary.json").read_text()


def test_independent_decimal_reconciles_every_source_issuer_delta(source):
    run(source)
    result = verify(source)
    assert result["original_SEC_disclosure_pairs_checked"] == 180
    assert result["matched_balanced_2019_2021_issuers"] == 34
    assert result["all_private_issuer_year_differences_verified"]
    assert result["bootstrap_and_leave_one_issuer_out_diagnostics_verified"]
    assert result["independent_decimal_source_year_means_medians_verified"]
    assert result["causal_claim_or_population_inference_validated"] is False
    assert result["historical_market_or_identity_data_used"] is False
    assert not result["final_period_opened"]


def test_feature_sha_mismatch_refused_before_reading_data(source):
    p = source["source"] / "text_features.csv"
    p.write_text(p.read_text() + "\nCHANGED SOURCE")
    with pytest.raises(ValueError, match="descriptive source coverage"):
        run(source)


def test_future_2025_source_filing_year_refused_with_rehashed_inputs(source):
    def alter(frame):
        frame.loc[0, "year"] = 2025
    edit_features(source, alter)
    with pytest.raises(ValueError, match="future or malformed filing years"):
        run(source)


def test_forged_jaccard_value_source_refused(source):
    def alter(frame):
        frame.loc[0, "jaccard_distance"] = 1.7
    edit_features(source, alter)
    with pytest.raises(ValueError, match="Jaccard vocabulary-change range"):
        run(source)


def test_source_risk_text_log_length_feature_fails_independent_token_check(source):
    def alter(frame):
        frame.loc[0, "log_length_change"] = 5.0
    edit_features(source, alter)
    with pytest.raises(ValueError, match="length-change feature"):
        run(source)


def test_earliest_TFIDF_imputation_is_forbidden(source):
    def alter(frame):
        frame.loc[frame.year.eq(2015), "tfidf_cosine_distance"] = 0.2
    edit_features(source, alter)
    with pytest.raises(ValueError, match="null TF-IDF vocabulary policy"):
        run(source)


def test_future_vocabulary_counts_rejected(source):
    def alter(frame):
        frame.loc[frame.year.eq(2019), "vocabulary_training_pairs"] = 180
    edit_features(source, alter)
    with pytest.raises(ValueError, match="Future SEC filing tokens"):
        run(source)


def test_unknown_previous_filing_url_is_rejected(source):
    def alter(frame):
        frame.loc[0, "previous_source_url"] = "https://www.sec.gov/Archives/edgar/data/1/missing.htm"
    edit_features(source, alter)
    with pytest.raises(ValueError, match="pair does not match immutable original manifest"):
        run(source)


def test_forged_external_source_domain_rejected(source):
    p = source["source"] / "filing_sources.csv"
    p.write_text(p.read_text().replace("www.sec.gov", "evil.example", 1))
    with pytest.raises(ValueError, match="URL/CIK/format"):
        run(source)


def test_missing_balanced_year_cannot_be_silently_replaced(source):
    def alter(frame):
        frame.loc[frame.year.eq(2019), "year"] = 2020
    edit_features(source, alter)
    with pytest.raises(ValueError, match="year counts differ"):
        run(source)


def test_forecast_claim_flag_is_never_allowed_in_source_receipt(source):
    path = source["source"] / "combination_receipt.json"
    receipt = json.loads(path.read_text())
    receipt["predictive_performance_claim"] = True
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="descriptive source coverage"):
        run(source)


def test_existing_result_output_will_not_be_overwritten(source):
    run(source)
    with pytest.raises(ValueError, match="new private"):
        run(source)


def test_forged_private_per_issuer_outcome_detected_after_rehash(source):
    run(source)
    def change(content):
        rows = [json.loads(line) for line in content.splitlines()]
        rows[0]["difference"] = -0.99
        return "".join(json.dumps(row) + "\n" for row in rows)
    _rehashed_result(source, "issuer_changes_private.jsonl", change)
    with pytest.raises(ValueError, match="issuer-level Jaccard change differs"):
        verify(source)


def test_forged_mean_result_detected_even_when_receipt_rehashed(source):
    run(source)
    def change(content):
        result = json.loads(content)
        result["exploratory_balanced_jaccard_contrasts"][-1][
            "paired_mean_jaccard_distance_difference"
        ] = 0.95
        return json.dumps(result)
    _rehashed_result(source, "public_summary.json", change)
    with pytest.raises(ValueError, match="counts or mean/median drift"):
        verify(source)


def test_forged_bootstrap_interval_detected_even_with_updated_digest(source):
    run(source)
    def change(content):
        result = json.loads(content)
        result["exploratory_balanced_jaccard_contrasts"][-1][
            "conditional_issuer_bootstrap_mean_95pct_interval"
        ] = [-1.0, 1.0]
        return json.dumps(result)
    _rehashed_result(source, "public_summary.json", change)
    with pytest.raises(ValueError, match="resampling uncertainty"):
        verify(source)


def test_independent_rejects_silently_added_model_approval(source):
    run(source)
    def change(content):
        data = json.loads(content)
        data["model_ready"] = True
        return json.dumps(data)
    _rehashed_result(source, "public_summary.json", change)
    with pytest.raises(ValueError, match="fabricated historical/model/review approvals"):
        verify(source)


def test_independent_must_not_overwrite_prior_verification(source):
    run(source)
    verify(source)
    with pytest.raises(ValueError, match="new public report"):
        verify(source)


def test_signed_differences_and_outlier_sensitivity_are_preserved(source):
    base = [(i, d) for i, d in enumerate((0.1, -0.05, 0.04, -0.02))]
    data = []
    for k in range(34):
        cik = f"{1000000000+k:010d}"
        delta = base[k % len(base)][1]
        for year, v in (
            (2019, 0.15), (2020, 0.15 + delta / 2),
            (2021, 0.15 + delta),
        ):
            data.append({"cik": cik, "year": year, "jaccard_distance": v})
    frame = pd.DataFrame(data)
    result, private = _paired_delta(frame, old_year=2019, new_year=2021, seed=42)
    assert result["matched_issuers"] == 34
    assert result["decreased"] > 0 and result["increased"] > 0
    assert len(private) == 34
    assert result["leave_one_issuer_out_mean_difference_range"][0] <= (
        result["paired_mean_jaccard_distance_difference"]
    ) <= result["leave_one_issuer_out_mean_difference_range"][1]



def test_published_descriptive_figure_uses_balanced_public_means_only(source):
    public = run(source)
    svg = render_sec_only_mean_drift_svg(public)
    assert svg.startswith("<svg")
    assert "Mean Jaccard distance" in svg
    assert '2019</text>' in svg
    assert '2020</text>' in svg
    assert '2021</text>' in svg
    assert "<script" not in svg.lower()
    assert "candidate_permno" not in svg
    assert "source_url" not in svg
    assert "purposive" in svg


def test_figure_cannot_turn_synthetic_validation_into_model_claim(source):
    public = run(source)
    public["model_ready"] = True
    with pytest.raises(ValueError, match="allegedly approved empirical SEC results"):
        render_sec_only_mean_drift_svg(public)


def test_figure_requires_same_balanced_cohort_and_safe_axis_range(source):
    public = run(source)
    public["balanced_issuer_count"] = 10
    with pytest.raises(ValueError, match="allegedly approved empirical SEC results"):
        render_sec_only_mean_drift_svg(public)
    public["balanced_issuer_count"] = 34
    public["balanced_2019_2021_year_coverage"][0]["jaccard_distance"]["mean"] = 1.0
    with pytest.raises(ValueError, match="plotting domain"):
        render_sec_only_mean_drift_svg(public)
