"""Targeted, explicitly post-hoc source review of four SEC Item 1A change cases.

Two extremes, closest-to-zero and closest-to-median issuer differences in
2019 vs 2021 yearly lexical change. Four original annual 10-Ks per issuer.
Diagnoses extraction/source changes, never validates population/market model.
"""

import csv
import hashlib
import json
import math
import os
import re
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np

from .extraction import TOKEN, extract_risk_factors
from .protocol import canonical_hash
from .sec_only_disclosure_descriptives import _load_approved_as_descriptive_source
from .sec_original_revisit import _curl

STATUS = "TARGETED_ORIGINAL_SEC_ITEM1A_16_DOCUMENT_DIAGNOSTIC_NOT_HUMAN_APPROVED"


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _pick_balanced_extremes(features):
    matrix = features.loc[features.year.isin((2019, 2021))].pivot(
        index="cik", columns="year", values="jaccard_distance"
    ).dropna()
    _require(len(matrix) == 34, "Expected 34 original balanced SEC descriptive issuers")
    delta = matrix[2021] - matrix[2019]
    middle = float(np.median(delta.to_numpy(dtype=float)))
    picks = {
        "largest_positive_change": sorted(delta.items(), key=lambda x: (-x[1], x[0]))[0][0],
        "largest_negative_change": sorted(delta.items(), key=lambda x: (x[1], x[0]))[0][0],
        "closest_to_no_change": sorted(delta.items(), key=lambda x: (abs(x[1]), x[0]))[0][0],
        "closest_to_median_change": sorted(
            delta.items(), key=lambda x: (abs(x[1] - middle), x[0])
        )[0][0],
    }
    _require(len(set(picks.values())) == 4,
             "Extremal diagnostic selection overlaps; stop rather than invent a replacement")
    return [{"case": kind, "cik": cik, "observed_delta": float(delta[cik])}
            for kind, cik in sorted(picks.items())]


def _read_manifest(path):
    path = Path(path)
    raw = path.read_bytes()
    reader = csv.DictReader(raw.decode("utf-8-sig").splitlines(), restkey="extra")
    _require(reader.fieldnames is not None and {
        "cik", "accessionNumber", "source_url", "acceptance_timestamp",
        "download_sha256", "extraction_status", "risk_token_count",
        "resolution_method", "risk_source_url", "extraction_version",
    }.issubset(reader.fieldnames), "Original SEC filing source manifest fields changed")
    mapping = {}
    for entry in reader:
        _require("extra" not in entry and None not in entry.values(),
                 "Original SEC source manifest has malformed row")
        key = (entry["cik"], int(entry["acceptance_timestamp"][:4]))
        _require(key not in mapping, "Original SEC source manifest issuer/year repeated")
        mapping[key] = entry
    _require(len(mapping) == 215, "Original SEC filing source manifest no longer has 215 original rows")
    return mapping, _sha(raw)


def _safe_url(entry):
    url = entry["source_url"]
    cik = entry["cik"]
    acc = entry["accessionNumber"]
    parsed = urlsplit(url)
    expected = f"/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/"
    return (
        re.fullmatch(r"\d{10}-\d{2}-\d{6}", acc) is not None
        and parsed.scheme == "https" and parsed.netloc == "www.sec.gov"
        and parsed.path.startswith(expected) and parsed.path != expected
        and not parsed.username and not parsed.password and not parsed.query
        and not parsed.fragment
    )


def _distance(a, b):
    old, new = set(TOKEN.findall(a.lower())), set(TOKEN.findall(b.lower()))
    _require(old and new, "Source SEC Item 1A token set cannot be empty")
    return 1 - len(old & new) / len(old | new)


def _original_baseline(baseline, provenances):
    folder = Path(baseline).resolve(strict=True)
    receipt_raw = (folder / "receipt.json").read_bytes()
    public_raw = (folder / "public_summary.json").read_bytes()
    receipt = json.loads(receipt_raw)
    _require(receipt["files"]["public_summary.json"]["sha256"] == _sha(public_raw),
             "SEC-only published baseline summary hash changed")
    published = json.loads(public_raw)
    _require(published["source_fingerprints"] == provenances
             and published["balanced_issuer_count"] == 34
             and published["model_ready"] is False
             and published["final_period_opened"] is False
             and published["predictive_performance_claimed"] is False
             and published["market_returns_or_CRSP_identity_data_read"] is False,
             "SEC-only published descriptive baseline is no longer source-bound/unapproved")
    return {"original_baseline_receipt_sha256": _sha(receipt_raw),
            "original_baseline_public_sha256": _sha(public_raw)}


def review_diagnostic_sec_originals(source_dir, baseline, output, *,
                                    user_agent, config, repo_root, pace=1.3):
    root = Path(repo_root).resolve(strict=True)
    dest = Path(output).resolve()
    _require(not dest.exists() and dest.is_relative_to(root / "outputs")
             and dest != root / "outputs",
             "Original SEC diagnostic review needs a fresh private output folder")
    _require(isinstance(user_agent, str)
             and re.search(r"[\w.%+\-]+@[\w.\-]+\.[a-zA-Z]{2,}", user_agent)
             and 1 <= pace <= 10,
             "SEC fair access requires contact-bearing user agent and at least one second pacing")
    frame, provenance, inputs = _load_approved_as_descriptive_source(source_dir, config)
    base_proof = _original_baseline(baseline, provenance)
    selection = _pick_balanced_extremes(frame)
    original, manifest_hash = _read_manifest(inputs["manifest"])
    needed = []
    for candidate in selection:
        cik = candidate["cik"]
        for year in range(2018, 2022):
            row = original.get((cik, year))
            _require(row is not None and _safe_url(row)
                     and row["resolution_method"] == "numbered_item1a"
                     and row["risk_source_url"] == row["source_url"]
                     and row["extraction_status"] == "ok",
                     "Predeclared review source isn't direct original SEC Item 1A")
            needed.append({**candidate, "year": year, "source": row})
    _require(len(needed) == 16
             and len({item["source"]["accessionNumber"] for item in needed}) == 16,
             "Source review is not 16 distinct 10-K documents")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sec-diagnostic-", dir=dest.parent) as scratch:
        stage = Path(scratch) / "review"
        stage.mkdir(mode=0o700)
        original_bytes_dir = stage / "original_html"
        original_bytes_dir.mkdir(mode=0o700)
        records = []
        extracted_by_id = {}
        stopped = False
        for item in needed:
            source = item["source"]
            accession = source["accessionNumber"]
            path = original_bytes_dir / (accession + ".html")
            base = {
                "cik": item["cik"], "case": item["case"],
                "accession": accession, "year": item["year"],
                "earlier_original_HTML_sha256": source["download_sha256"],
                "original_SEC_url": source["source_url"],
                "manual_Item1A_boundary_approved": False,
                "original_SEC_first_publication_at": None,
            }
            if stopped:
                base["retrieval_status"] = "NOT_REQUESTED_AFTER_SEC_ERROR"
                records.append(base)
                continue
            transfer, raw = _curl(source["source_url"], path, user_agent, 40 * 1024 * 1024)
            base["retrieval_status"] = transfer["status"]
            base["http_status"] = transfer.get("http")
            if raw is None:
                if path.exists():
                    path.unlink()
                stopped = True
                records.append(base)
                continue
            extract = extract_risk_factors(raw)
            base.update({
                "current_HTML_sha256": _sha(raw),
                "earlier_HTML_SHA256_exact_match": _sha(raw) == source["download_sha256"],
                "current_HTML_bytes": len(raw),
                "original_source_expected_Item1A_tokens": int(source["risk_token_count"]),
                "current_source_Item1A_tokens": extract.token_count,
                "current_Item1A_tokens_match_prior": extract.token_count == int(source["risk_token_count"]),
                "original_extraction_version": source["extraction_version"],
                "current_extraction_version": extract.version,
                "extraction_status": extract.status,
                "current_Item1A_text_sha256": _sha(extract.text.encode()),
                "start_excerpt_private": extract.text[:140],
                "end_excerpt_private": extract.text[-140:],
            })
            extracted_by_id[(item["cik"], item["year"])] = extract.text
            os.chmod(path, 0o400)
            records.append(base)
            time.sleep(pace)
        counts = Counter()
        private_comparisons = []
        for record in records:
            counts["original_SEC_documents_selected"] += 1
            if record["retrieval_status"] == "HTTP_200_VALID_SIZE":
                counts["HTTP_200_original_documents"] += 1
                counts["raw_sha256_equal_to_original_manifest"] += int(
                    record["earlier_HTML_SHA256_exact_match"]
                )
                counts["original_risk_token_count_match"] += int(
                    record["current_Item1A_tokens_match_prior"]
                )
                counts["source_extraction_status_ok"] += int(record["extraction_status"] == "ok")
                counts["source_extraction_version_matches"] += int(
                    record["current_extraction_version"] == record["original_extraction_version"]
                )
        for item in selection:
            cik = item["cik"]
            panel_available = all((cik, year) in extracted_by_id for year in range(2018, 2022))
            result = {
                **item, "all_four_current_source_files_retrieved": panel_available,
                "human_source_review_approved": False,
            }
            if panel_available:
                compared = {}
                for year in (2019, 2020, 2021):
                    source = extracted_by_id[(cik, year)]
                    earlier = extracted_by_id[(cik, year - 1)]
                    rows = frame.loc[(frame.cik == cik) & (frame.year == year)]
                    _require(len(rows) == 1, "Original SEC descriptive source pair missing")
                    row = rows.iloc[0]
                    n_new, n_old = len(TOKEN.findall(source.lower())), len(TOKEN.findall(earlier.lower()))
                    d = _distance(earlier, source)
                    log_change = math.log1p(n_new) - math.log1p(n_old)
                    match = math.isclose(d, float(row.jaccard_distance), abs_tol=1e-12, rel_tol=0)
                    log_match = math.isclose(log_change, float(row.log_length_change), abs_tol=1e-12, rel_tol=0)
                    token_match = (n_new == int(row.current_tokens) and n_old == int(row.previous_tokens))
                    compared[str(year)] = {
                        "reparsed_Jaccard_distance": d,
                        "original_published_jaccard_distance": float(row.jaccard_distance),
                        "Jaccard_exact_source_computation_match": match,
                        "log_length_difference_exact": log_match,
                        "original_token_counts_match": token_match,
                    }
                    counts["annual_Jaccard_source_checks_reproduced"] += int(match)
                    counts["annual_length_source_checks_reproduced"] += int(log_match)
                    counts["annual_both_token_counts_verified"] += int(token_match)
                result["annual_comparisons"] = compared
                result["paired_2019_2021_delta_recomputed"] = (
                    compared["2021"]["reparsed_Jaccard_distance"]
                    - compared["2019"]["reparsed_Jaccard_distance"]
                )
                result["published_paired_delta_reproduced"] = math.isclose(
                    result["paired_2019_2021_delta_recomputed"], item["observed_delta"],
                    abs_tol=1e-12, rel_tol=0
                )
                counts["four_year_source_issuer_cases_complete"] += 1
                counts["paired_issuer_delta_reproduced"] += int(
                    result["published_paired_delta_reproduced"]
                )
            private_comparisons.append(result)
        summary = {
            "schema_version": 1, "status": STATUS,
            "posthoc_source_review_selection": (
                "largest signed increase, largest decrease, closest to zero, "
                "closest to median of 2019-2021 paired issuer Jaccard change"
            ),
            "original_original_SEC_feature_filings": 215,
            "original_source_annual_comparisons": 180,
            "diagnostic_selected_issuers": len(selection),
            "original_SEC_source_acceptance_years": [2018, 2019, 2020, 2021],
            "counts": dict(sorted(counts.items())),
            "stop_on_SEC_request_error": stopped,
            "source_provenance": {
                **provenance, **base_proof,
                "original_215_SEC_manifest_sha256": manifest_hash,
                "frozen_protocol_sha256": canonical_hash(config),
            },
            "original_html_hash_disagreements_are_explicit_source_version_warnings": True,
            "manual_original_item1a_boundary_reviews_approved": False,
            "first_publication_known_at_verified": False,
            "population_random_or_representative_sample": False,
            "historical_stock_or_CRSP_data_used": False,
            "causal_or_predictive_result_claimed": False,
            "model_ready": False, "final_period_opened": False,
        }
        (stage / "private_original_source_rows.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in records)
        )
        (stage / "private_issuer_comparison_reviews.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in private_comparisons)
        )
        (stage / "public_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        receipt = {
            "schema_version": 1, "status": STATUS,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_provenance": summary["source_provenance"],
            "files": {
                name: {"sha256": _sha((stage / name).read_bytes()),
                       "bytes": (stage / name).stat().st_size}
                for name in ("private_original_source_rows.jsonl",
                             "private_issuer_comparison_reviews.jsonl",
                             "public_summary.json")
            },
            "human_approvals": 0, "model_ready": False, "final_period_opened": False,
        }
        (stage / "receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        for file in stage.iterdir():
            if file.is_file():
                os.chmod(file, 0o400)
        stage.rename(dest)
    return summary
