"""Independent original-byte/Jaccard arithmetic check of selected SEC Item 1A.

Uses the *same versioned conservative Item 1A boundary parser*, but a separate
CSV+stdlib-regex reconstruction of the vocabulary-set and token arithmetic.
Source-bound diagnostic selection is post-hoc, not independent sampling,
manual source review, first publication, or a forecast result.
"""

import csv
import hashlib
import json
import math
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from .extraction import extract_risk_factors
from .protocol import canonical_hash

STATUS = "INDEPENDENT_ORIGINAL_SEC_ITEM1A_DIAGNOSTIC_SOURCES_RECOMPUTED_NOT_HUMAN_APPROVED"
SOURCE_STATUS = "TARGETED_ORIGINAL_SEC_ITEM1A_16_DOCUMENT_DIAGNOSTIC_NOT_HUMAN_APPROVED"


def _must(ok, why):
    if not ok:
        raise ValueError(why)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _data(path, cap):
    p = Path(path)
    _must(not p.is_symlink(), "Original SEC source cannot be a symlink")
    p = p.resolve(strict=True)
    _must(p.is_file() and p.stat().st_size <= cap, "Missing or oversized original SEC source")
    return p.read_bytes()


def _tokens(text):
    return re.findall(r"\b[a-zA-Z]{2,}\b", text.lower())


def _dist(before, after):
    a, b = set(_tokens(before)), set(_tokens(after))
    _must(a and b, "Unusable original SEC Risk Factors token sets")
    return 1 - len(a.intersection(b)) / len(a.union(b))


def verify_original_diagnostic_sources(intake, original_source, output, *,
                                       config, repo_root):
    repo = Path(repo_root).resolve(strict=True)
    dest = Path(output).resolve()
    _must(not dest.exists() and dest.is_relative_to(repo / "reports"),
          "Use an unused public aggregate report path for independent SEC diagnostic verification")
    folder = Path(intake).resolve(strict=True)
    receipt_blob = _data(folder / "receipt.json", 128000)
    public_blob = _data(folder / "public_summary.json", 128000)
    source_rows_blob = _data(folder / "private_original_source_rows.jsonl", 128000)
    comparison_blob = _data(folder / "private_issuer_comparison_reviews.jsonl", 128000)
    receipt, summary = json.loads(receipt_blob), json.loads(public_blob)
    _must(
        receipt["status"] == summary["status"] == SOURCE_STATUS
        and receipt["source_provenance"] == summary["source_provenance"]
        and summary["source_provenance"]["frozen_protocol_sha256"] == canonical_hash(config)
        and summary["model_ready"] is False
        and summary["final_period_opened"] is False
        and receipt["human_approvals"] == 0
        and receipt["model_ready"] is False
        and receipt["final_period_opened"] is False
        and summary["manual_original_item1a_boundary_reviews_approved"] is False
        and summary["causal_or_predictive_result_claimed"] is False
        and summary["population_random_or_representative_sample"] is False
        and summary["historical_stock_or_CRSP_data_used"] is False
        and summary["first_publication_known_at_verified"] is False,
        "Selected SEC original source reports improperly claim approved review or forecast",
    )
    for name, blob in (
        ("public_summary.json", public_blob),
        ("private_original_source_rows.jsonl", source_rows_blob),
        ("private_issuer_comparison_reviews.jsonl", comparison_blob),
    ):
        declaration = receipt["files"][name]
        _must(declaration["sha256"] == _sha(blob) and declaration["bytes"] == len(blob),
              "Source-bound original SEC diagnostic evidence byte fingerprint changed")
    source = Path(original_source).resolve(strict=True)
    original_features = _data(source / "text_features.csv", 2 * 1024 * 1024)
    original_manifest = _data(source / "filing_sources.csv", 2 * 1024 * 1024)
    _must(_sha(original_features) == summary["source_provenance"]["features_sha256"]
          and _sha(original_manifest) == summary["source_provenance"]["original_215_SEC_manifest_sha256"],
          "SEC original feature/filing manifest fingerprint differs")
    features = {}
    issuer_deltas = defaultdict(dict)
    for row in csv.DictReader(original_features.decode("utf-8-sig").splitlines()):
        k = (row["cik"], int(row["year"]))
        _must(k not in features, "Duplicate original SEC source feature issuer/year")
        features[k] = row
        if int(row["year"]) in (2019, 2021):
            issuer_deltas[row["cik"]][int(row["year"])] = float(row["jaccard_distance"])
    _must(len(features) == 180, "Wrong original SEC source-feature panel")
    matched = [(cik, v[2021] - v[2019]) for cik, v in issuer_deltas.items()
               if 2019 in v and 2021 in v]
    _must(len(matched) == 34, "Original SEC balanced pair population changed")
    middle = sorted(v for _, v in matched)
    median = (middle[16] + middle[17]) / 2
    choices = {
        "largest_positive_change": sorted(matched, key=lambda x: (-x[1], x[0]))[0][0],
        "largest_negative_change": sorted(matched, key=lambda x: (x[1], x[0]))[0][0],
        "closest_to_no_change": sorted(matched, key=lambda x: (abs(x[1]), x[0]))[0][0],
        "closest_to_median_change": sorted(matched, key=lambda x: (abs(x[1]-median), x[0]))[0][0],
    }
    _must(len(set(choices.values())) == 4,
          "Independent diagnostic source selection unexpectedly overlaps")
    rows = [json.loads(row) for row in source_rows_blob.decode().splitlines()]
    cases = [json.loads(row) for row in comparison_blob.decode().splitlines()]
    _must(len(rows) == summary["counts"]["original_SEC_documents_selected"] == 16
          and len(cases) == summary["diagnostic_selected_issuers"] == 4
          and len({row["accession"] for row in rows}) == 16,
          "Original source review case count or accession uniqueness changed")
    source_manifest = {
        row["accessionNumber"]: row for row in
        csv.DictReader(original_manifest.decode("utf-8-sig").splitlines())
    }
    matched_original_rows = defaultdict(dict)
    metrics = Counter()
    for row in rows:
        acc = row["accession"]
        from_manifest = source_manifest.get(acc)
        _must(from_manifest is not None,
              "Missing original SEC source archive accession")
        _must(row["cik"] == from_manifest["cik"]
              and row["original_SEC_url"] == from_manifest["source_url"]
              and row["earlier_original_HTML_sha256"] == from_manifest["download_sha256"]
              and row["year"] == int(from_manifest["acceptance_timestamp"][:4])
              and row["manual_Item1A_boundary_approved"] is False
              and row["original_SEC_first_publication_at"] is None,
              "SEC original source review rows do not match original manifest")
        _must(row["case"] in choices and choices[row["case"]] == row["cik"],
              "Original post-hoc diagnostic review labels were substituted")
        _must(row["retrieval_status"] == "HTTP_200_VALID_SIZE",
              "This completed independent diagnostic requires all current original source documents")
        source_path = folder / "original_html" / (acc + ".html")
        raw = _data(source_path, 40 * 1024 * 1024)
        _must(row["current_HTML_sha256"] == _sha(raw)
              and row["current_HTML_bytes"] == len(raw)
              and row["earlier_HTML_SHA256_exact_match"] is (
                  _sha(raw) == from_manifest["download_sha256"]
              ), "Saved original SEC current HTML changed after review")
        extraction = extract_risk_factors(raw)
        _must(extraction.status == row["extraction_status"] == "ok"
              and extraction.version == row["current_extraction_version"]
              and row["original_extraction_version"] == from_manifest["extraction_version"]
              and extraction.token_count == row["current_source_Item1A_tokens"]
              and row["original_source_expected_Item1A_tokens"] == int(from_manifest["risk_token_count"])
              and row["current_Item1A_tokens_match_prior"] is (
                  extraction.token_count == int(from_manifest["risk_token_count"])
              )
              and row["current_Item1A_text_sha256"] == _sha(extraction.text.encode()),
              "Original SEC Item 1A saved extracted text no longer matches current raw source")
        _must(row["start_excerpt_private"] == extraction.text[:140]
              and row["end_excerpt_private"] == extraction.text[-140:],
              "Original SEC diagnostic item1a boundary excerpts changed")
        matched_original_rows[row["cik"]][row["year"]] = extraction.text
        metrics["HTTP_200_original_documents"] += 1
        metrics["raw_sha256_equal_to_original_manifest"] += int(
            row["earlier_HTML_SHA256_exact_match"]
        )
        metrics["original_risk_token_count_match"] += int(
            row["current_Item1A_tokens_match_prior"]
        )
        metrics["source_extraction_version_matches"] += int(
            extraction.version == from_manifest["extraction_version"]
        )
        metrics["source_extraction_status_ok"] += 1
    for case in cases:
        cik, reason = case["cik"], case["case"]
        _must(reason in choices and choices[reason] == cik
              and len(matched_original_rows[cik]) == 4
              and case["all_four_current_source_files_retrieved"] is True
              and case["human_source_review_approved"] is False,
              "Original SEC diagnostic issuer review group is incomplete or falsely approved")
        _must(math.isclose(case["observed_delta"],
                            issuer_deltas[cik][2021] - issuer_deltas[cik][2019],
                            rel_tol=0, abs_tol=1e-12),
              "Published source diagnostic selected-issuer Jaccard delta differs")
        for year in (2019, 2020, 2021):
            text_new = matched_original_rows[cik][year]
            text_old = matched_original_rows[cik][year-1]
            calculated = _dist(text_old, text_new)
            source_pair = features[(cik, year)]
            stored = case["annual_comparisons"][str(year)]
            tokens_new, tokens_old = len(_tokens(text_new)), len(_tokens(text_old))
            calculated_log = math.log1p(tokens_new) - math.log1p(tokens_old)
            matches = math.isclose(calculated, float(source_pair["jaccard_distance"]),
                                   abs_tol=1e-12, rel_tol=0)
            log_matches = math.isclose(calculated_log, float(source_pair["log_length_change"]),
                                       abs_tol=1e-12, rel_tol=0)
            token_matches = (tokens_new == int(source_pair["current_tokens"])
                             and tokens_old == int(source_pair["previous_tokens"]))
            _must(
                math.isclose(stored["reparsed_Jaccard_distance"], calculated,
                             rel_tol=0, abs_tol=1e-12)
                and stored["Jaccard_exact_source_computation_match"] is matches
                and stored["log_length_difference_exact"] is log_matches
                and stored["original_token_counts_match"] is token_matches,
                "Independent source-token set Jaccard/log-length review evidence differs",
            )
            metrics["annual_Jaccard_source_checks_reproduced"] += int(matches)
            metrics["annual_length_source_checks_reproduced"] += int(log_matches)
            metrics["annual_both_token_counts_verified"] += int(token_matches)
        independent_delta = (_dist(matched_original_rows[cik][2020], matched_original_rows[cik][2021])
                             - _dist(matched_original_rows[cik][2018], matched_original_rows[cik][2019]))
        expected_delta = issuer_deltas[cik][2021] - issuer_deltas[cik][2019]
        independently_reproduced = math.isclose(
            independent_delta, expected_delta, rel_tol=0, abs_tol=1e-12
        )
        _must(math.isclose(independent_delta, case["paired_2019_2021_delta_recomputed"],
                           rel_tol=0, abs_tol=1e-12)
              and case["published_paired_delta_reproduced"] is independently_reproduced,
              "Original SEC 4-year issuer delta consistency flag is false or fabricated")
        metrics["four_year_source_issuer_cases_complete"] += 1
        metrics["paired_issuer_delta_reproduced"] += int(independently_reproduced)
    metrics["original_SEC_documents_selected"] = len(rows)
    _must(dict(metrics) == summary["counts"],
          "Independent source downloaded files and all aggregate counts disagree")
    result = {
        "schema_version": 1, "status": STATUS,
        "original_sec_filing_html_files_reread": len(rows),
        "independent_original_Item1A_extractions_reconfirmed": metrics["original_risk_token_count_match"],
        "independent_original_annual_Jaccard_measures_verified": metrics["annual_Jaccard_source_checks_reproduced"],
        "independent_original_length_measures_verified": metrics["annual_length_source_checks_reproduced"],
        "original_source_diagnostic_issuer_deltas_verified": metrics["paired_issuer_delta_reproduced"],
        "source_fingerprints": {
            "first_reviewer_receipt_sha256": _sha(receipt_blob),
            "original_SEC_features_sha256": _sha(original_features),
            "original_SEC_manifest_sha256": _sha(original_manifest),
            "frozen_protocol_sha256": canonical_hash(config),
        },
        "direct_SEC_html_first_publication_known_at_verified": False,
        "SEC_iXBRL_boundary_human_review_completed": False,
        "posthoc_selection_not_representative_or_causal": True,
        "stock_return_forecast_approved": False,
        "model_ready": False, "final_period_opened": False,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sec-source-diagnostic-verify-", dir=dest.parent) as work:
        staged = Path(work) / "summary.json"
        staged.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        staged.replace(dest)
    return result
