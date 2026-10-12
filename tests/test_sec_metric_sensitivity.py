"""Synthetic SEC-only alternative-metric sensitivity and source tampering tests."""

import hashlib
import json

import pandas as pd
import pytest

from disclosure_research.sec_metric_sensitivity_verifier import independently_verify_metric_sensitivity
from disclosure_research.sec_only_disclosure_descriptives import run_sec_only_descriptives
from disclosure_research.sec_only_metric_sensitivity import build_sec_metric_sensitivity
from test_sec_only_descriptives import source as sec_source_fixture  # noqa: F401


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def sources(sec_source_fixture):  # noqa: F811
    x = sec_source_fixture
    x["baseline"] = x["root"] / "outputs" / "baseline"
    run_sec_only_descriptives(
        x["source"], x["baseline"], config=x["config"], repo_root=x["root"],
    )
    x["sensitivity"] = x["root"] / "outputs" / "sensitivity"
    x["verify_metric"] = x["root"] / "reports" / "independent-metrics.json"
    return x


def run(x):
    return build_sec_metric_sensitivity(
        x["source"], x["baseline"], x["sensitivity"],
        config=x["config"], repo_root=x["root"]
    )


def verify(x):
    return independently_verify_metric_sensitivity(
        x["source"], x["baseline"], x["sensitivity"], x["verify_metric"],
        config=x["config"], repo_root=x["root"]
    )


def rehash_private(x, filename, change):
    path = x["sensitivity"] / filename
    current = path.read_text()
    new = change(current)
    path.chmod(0o600)
    path.write_text(new)
    receipt_path = x["sensitivity"] / "receipt.json"
    receipt_path.chmod(0o600)
    receipt = json.loads(receipt_path.read_text())
    changed = path.read_bytes()
    receipt["files"][filename] = {"sha256": sha(changed), "bytes": len(changed)}
    receipt_path.write_text(json.dumps(receipt))


def test_alternative_metrics_source_bound_34_balanced_non_predictive(sources):
    result = run(sources)
    assert result["balanced_2019_2021_issuers"] == 34
    assert len(result["metrics_and_paired_year_results"]) == 9
    assert result["original_filing_sources_and_text_features_unchanged"]
    assert result["market_returns_or_historical_CIK_PERMNO_sources_read"] is False
    assert not result["forecast_improvement_claimed"]
    assert not result["confirmatory_hypothesis_or_causal_attribution_claimed"]
    assert not result["model_ready"]
    assert not result["final_period_opened"]
    delta = next(x for x in result["metrics_and_paired_year_results"]
                 if x["metric"] == "log_length_change"
                 and x["from_year"] == 2019 and x["to_year"] == 2021)
    assert delta["matched" if "matched" in delta else "balanced_issuer_count"] == 34
    assert delta["increased"] == 34
    assert delta["mean_paired_change"] > 0
    assert result["metric_interpretations"]["tfidf_cosine_distance"].find("NOT fixed-vocabulary effects") >= 0
    receipt = json.loads((sources["sensitivity"] / "receipt.json").read_text())
    assert receipt["source_approvals"] == 0
    assert sources["sensitivity"].stat().st_mode & 0o077 == 0
    for name, fact in receipt["files"].items():
        stored = sources["sensitivity"] / name
        assert sha(stored.read_bytes()) == fact["sha256"]
        assert stored.stat().st_mode & 0o222 == 0


def test_independent_rechecks_all_306_metric_issuer_contrasts(sources):
    run(sources)
    report = verify(sources)
    assert report["all_306_private_issuer_changes_verified"]
    assert report["balanced_2019_2021_issuer_count"] == 34
    assert report["issuer_bootstrap_and_Spearman_concordance_verified"]
    assert report["TFIDF_original_expanding_vocabulary_not_fixed_scale"]
    assert report["source_SEC_item1a_annual_pairs_rechecked"] == 180
    assert not report["historical_returns_or_CIK_security_mapping_read"]
    assert report["model_ready"] is False


def test_paired_original_sec_source_feature_mutation_cannot_run(sources):
    p = sources["source"] / "text_features.csv"
    p.write_text(p.read_text() + "\nX")
    with pytest.raises(ValueError, match="original source|source coverage"):
        run(sources)


def test_modified_previous_published_baseline_detected(sources):
    prior = sources["baseline"] / "public_summary.json"
    prior.chmod(0o600)
    prior.write_bytes(prior.read_bytes() + b'{"invalid":true}')
    with pytest.raises(ValueError, match="baseline descriptive source or review gates"):
        run(sources)


def test_forged_future_TFIDF_leakage_cannot_enter_alternative_result(sources):
    p = sources["source"] / "text_features.csv"
    frame = pd.read_csv(p, dtype={"cik":str})
    frame.loc[frame.year.eq(2015), "tfidf_cosine_distance"] = 0.99
    frame.to_csv(p,index=False,float_format="%.17g")
    rec = sources["source"] / "pilot_checkpoint.json"
    data = json.loads(rec.read_text())
    data["files"]["text_features.csv"] = sha(p.read_bytes())
    rec.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="null TF-IDF vocabulary policy"):
        run(sources)


def test_source_only_result_can_not_be_promoted_to_empirical_forecast(sources):
    run(sources)
    def forge(raw):
        d = json.loads(raw)
        d["forecast_improvement_claimed"] = True
        return json.dumps(d)
    rehash_private(sources, "public_summary.json", forge)
    with pytest.raises(ValueError, match="falsely claims empirical approval"):
        verify(sources)


def test_independent_rejects_per_issuer_TFIDF_delta_tamper(sources):
    run(sources)
    def forge(raw):
        rows = [json.loads(row) for row in raw.splitlines()]
        target = next(r for r in rows if r["metric"]=="tfidf_cosine_distance"
                      and r["from_year"]==2019 and r["to_year"]==2021)
        target["paired_metric_difference"] += .18
        return "".join(json.dumps(row)+"\n" for row in rows)
    rehash_private(sources, "private_issuer_metric_changes.jsonl", forge)
    with pytest.raises(ValueError, match="issuer metric change differs"):
        verify(sources)


def test_independent_rejects_forged_alternative_bootstrap(sources):
    run(sources)
    def forge(raw):
        d = json.loads(raw)
        d["metrics_and_paired_year_results"][-1]["conditional_issuer_bootstrap_95pct_interval"] = [-1, 1]
        return json.dumps(d)
    rehash_private(sources, "public_summary.json", forge)
    with pytest.raises(ValueError, match="issuer bootstrap"):
        verify(sources)


def test_independent_rejects_false_Spearman_relationship(sources):
    run(sources)
    def forge(raw):
        d = json.loads(raw)
        d["spearman_of_2019_to_2021_issuer_delta_against_Jaccard"]["tfidf_cosine_distance"] = -.98
        return json.dumps(d)
    rehash_private(sources, "public_summary.json", forge)
    with pytest.raises(ValueError, match="rank concordance"):
        verify(sources)


def test_no_source_or_output_overwrite(sources):
    run(sources)
    with pytest.raises(ValueError, match="fresh private"):
        run(sources)
    verify(sources)
    with pytest.raises(ValueError, match="fresh aggregate"):
        verify(sources)


def test_balanced_cohort_source_changed_year_detected(sources):
    p = sources["source"] / "text_features.csv"
    frame = pd.read_csv(p,dtype={"cik":str})
    frame.loc[frame.year.eq(2019),"year"]=2022
    frame.to_csv(p,index=False,float_format="%.17g")
    rec = sources["source"] / "pilot_checkpoint.json"
    summary = json.loads(rec.read_text())
    summary["files"]["text_features.csv"] = sha(p.read_bytes())
    rec.write_text(json.dumps(summary))
    with pytest.raises(ValueError,match="future or malformed filing years"):
        run(sources)
