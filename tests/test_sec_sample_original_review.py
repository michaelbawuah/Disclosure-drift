"""Invented SEC source-only 16-document diagnostic mock; never network in tests."""

import csv
import hashlib
import json

import pandas as pd
import pytest

import disclosure_research.sec_sample_original_review as diagnostic
from disclosure_research.extraction import extract_risk_factors
from disclosure_research.sec_only_disclosure_descriptives import run_sec_only_descriptives
from disclosure_research.sec_sample_original_verifier import verify_original_diagnostic_sources
from test_sec_only_descriptives import source as sec_source_fixture  # noqa: F401


def _sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def source_case(sec_source_fixture, monkeypatch):  # noqa: F811
    x = sec_source_fixture
    features_file = x["source"] / "text_features.csv"
    features = pd.read_csv(features_file, dtype={"cik": str, "observation_id": str})
    balance = features.loc[features.year == 2019].set_index("cik")["jaccard_distance"].to_dict()
    for idx, cik in enumerate(sorted(balance)):
        features.loc[(features.cik == cik) & (features.year == 2021), "jaccard_distance"] = (
            balance[cik] + (-0.06 + 0.006 * idx)
        )
    features.to_csv(features_file, index=False, float_format="%.17g")
    receipt_path = x["source"] / "pilot_checkpoint.json"
    checkpoint = json.loads(receipt_path.read_text())
    checkpoint["files"]["text_features.csv"] = _sha(features_file.read_bytes())
    receipt_path.write_text(json.dumps(checkpoint))
    baseline = x["root"] / "outputs" / "baseline"
    x["baseline"] = baseline
    x["diagnostic"] = x["root"] / "outputs" / "diagnostic"
    x["diagnostic_verify"] = x["root"] / "reports" / "verified-originals.json"
    manifest_path = x["source"] / "filing_sources.csv"
    with manifest_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        old_rows = list(reader)
        old_head = reader.fieldnames
    head = old_head + [
        "risk_source_url", "risk_token_count", "resolution_method", "extraction_version",
    ]
    for row in old_rows:
        row.update({
            "risk_source_url": row["source_url"],
            "risk_token_count": "280",
            "resolution_method": "numbered_item1a",
            "extraction_version": "item1a-v1",
        })
    with manifest_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=head)
        writer.writeheader()
        writer.writerows(old_rows)
    run_sec_only_descriptives(x["source"], baseline, config=x["config"], repo_root=x["root"])
    mock_document = (
        "<html><body><h2>Item 1A. Risk Factors</h2>"
        + "<p>" + " ".join(("invented financial operating source risk factor "
                            "terms impact technology policy development ") for _ in range(40))
        + "</p><h2>Item 1B. Unresolved Staff Comments</h2>"
        + "</body></html>"
    ).encode()
    assert extract_risk_factors(mock_document).status == "ok"
    calls = []
    def get(url, path, agent, max_bytes):
        calls.append(url)
        path.write_bytes(mock_document)
        return {"status": "HTTP_200_VALID_SIZE", "http": "200",
                "bytes": len(mock_document)}, mock_document
    monkeypatch.setattr(diagnostic, "_curl", get)
    monkeypatch.setattr(diagnostic.time, "sleep", lambda _: None)
    x["calls"] = calls
    x["fake_html"] = mock_document
    return x


def _run(x, *, agent="DisclosureDriftResearch (academic@university.edu)"):
    return diagnostic.review_diagnostic_sec_originals(
        x["source"], x["baseline"], x["diagnostic"],
        user_agent=agent, config=x["config"], repo_root=x["root"], pace=1.3,
    )


def _verify(x):
    return verify_original_diagnostic_sources(
        x["diagnostic"], x["source"], x["diagnostic_verify"],
        config=x["config"], repo_root=x["root"],
    )


def test_deterministic_outcome_informed_four_distinct_original_issuer_cases(source_case):
    source = pd.read_csv(source_case["source"] / "text_features.csv", dtype={"cik": str})
    picked = diagnostic._pick_balanced_extremes(source)
    assert len(picked) == 4
    assert len({row["cik"] for row in picked}) == 4
    assert {row["case"] for row in picked} == {
        "largest_positive_change", "largest_negative_change",
        "closest_to_no_change", "closest_to_median_change",
    }


def test_mock_direct_sec_fetch_cannot_fake_source_feature_approval(source_case):
    report = _run(source_case)
    assert len(source_case["calls"]) == 16
    assert report["counts"]["original_SEC_documents_selected"] == 16
    assert report["counts"]["HTTP_200_original_documents"] == 16
    assert report["counts"]["original_risk_token_count_match"] == 0
    assert report["counts"]["annual_Jaccard_source_checks_reproduced"] == 0
    assert 0 <= report["counts"]["paired_issuer_delta_reproduced"] < 4
    assert report["counts"]["four_year_source_issuer_cases_complete"] == 4
    assert report["population_random_or_representative_sample"] is False
    assert report["manual_original_item1a_boundary_reviews_approved"] is False
    assert report["model_ready"] is False
    assert report["final_period_opened"] is False
    folder = source_case["diagnostic"]
    assert folder.stat().st_mode & 0o077 == 0
    receipt = json.loads((folder / "receipt.json").read_text())
    assert receipt["human_approvals"] == 0
    for name, meta in receipt["files"].items():
        f = folder / name
        assert meta["sha256"] == _sha(f.read_bytes())
        assert f.stat().st_mode & 0o222 == 0


def test_independent_recomputes_real_original_source_even_when_features_disagree(source_case):
    _run(source_case)
    verified = _verify(source_case)
    assert verified["original_sec_filing_html_files_reread"] == 16
    assert verified["independent_original_Item1A_extractions_reconfirmed"] == 0
    assert verified["independent_original_annual_Jaccard_measures_verified"] == 0
    assert 0 <= verified["original_source_diagnostic_issuer_deltas_verified"] < 4
    assert verified["stock_return_forecast_approved"] is False
    assert verified["model_ready"] is False and verified["final_period_opened"] is False


def test_manifest_must_have_matching_SEC_archive_url(source_case):
    p = source_case["source"] / "filing_sources.csv"
    txt = p.read_text()
    p.write_text(txt.replace("www.sec.gov", "malicious.example", 1))
    with pytest.raises(ValueError, match="original source|SEC source"):
        _run(source_case)
    assert not source_case["diagnostic"].exists()


def test_bad_fair_access_contact_user_agent_rejected(source_case):
    with pytest.raises(ValueError, match="contact-bearing"):
        _run(source_case, agent="Anonymous Scraper 1.0")
    assert not source_case["calls"]


def test_too_fast_sec_request_rate_rejected(source_case):
    with pytest.raises(ValueError, match="contact-bearing"):
        diagnostic.review_diagnostic_sec_originals(
            source_case["source"], source_case["baseline"], source_case["diagnostic"],
            user_agent="Academic Research (academic@university.edu)",
            config=source_case["config"], repo_root=source_case["root"],
            pace=0.3,
        )
    assert not source_case["diagnostic"].exists()


def test_failed_access_protects_further_sec_requests(source_case, monkeypatch):
    calls = source_case["calls"]
    def forbidden(url, path, agent, cap):
        calls.append(url)
        return {"status": "HTTP_STATUS", "http": "403"}, None
    monkeypatch.setattr(diagnostic, "_curl", forbidden)
    report = _run(source_case)
    assert len(calls) == 1
    assert report["stop_on_SEC_request_error"]
    assert report["counts"].get("HTTP_200_original_documents", 0) == 0
    assert report["model_ready"] is False


def test_original_sha_mismatch_not_overwritten(source_case):
    report = _run(source_case)
    assert report["counts"]["raw_sha256_equal_to_original_manifest"] == 0
    original = json.loads((source_case["diagnostic"] / "private_original_source_rows.jsonl")
                          .read_text().splitlines()[0])
    assert original["earlier_original_HTML_sha256"] == "a"*64
    assert original["current_HTML_sha256"] == _sha(source_case["fake_html"])
    assert not original["earlier_HTML_SHA256_exact_match"]


def test_modified_private_source_sha_cannot_pass_even_with_valid_receipt(source_case):
    _run(source_case)
    folder = source_case["diagnostic"] / "original_html"
    first = next(folder.iterdir())
    first.chmod(0o600)
    first.write_bytes(first.read_bytes() + b"malicious appendix")
    with pytest.raises(ValueError, match="current HTML changed"):
        _verify(source_case)


def test_unmodified_private_evidence_is_required(source_case):
    _run(source_case)
    path = source_case["diagnostic"] / "private_issuer_comparison_reviews.jsonl"
    path.chmod(0o600)
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="byte fingerprint changed"):
        _verify(source_case)


def test_cannot_overwrite_existing_private_or_independent_review(source_case):
    _run(source_case)
    with pytest.raises(ValueError, match="fresh private"):
        _run(source_case)
    _verify(source_case)
    with pytest.raises(ValueError, match="unused public aggregate"):
        _verify(source_case)


def test_source_token_sets_exact_calculation_and_positive_distance():
    first = "alpha beta gamma blue gamma"
    second = "alpha beta delta blue blue"
    assert diagnostic._distance(first, second) == pytest.approx(1 - 3/5)
    assert diagnostic._distance(first, first) == pytest.approx(0.0)
