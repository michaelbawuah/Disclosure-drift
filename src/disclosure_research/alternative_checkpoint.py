"""Independent private-outcome verifier for the SEC-backed conditional pilot.

All full provisional predictions remain private; this module reports only
aggregate QA and cannot approve empirical results.
"""

import hashlib
import json
import math
from datetime import date
from pathlib import Path

import pandas as pd

from .exploratory_sec_pilot import KIND
from .protocol import canonical_hash
from .public_benchmark_check import STATUS as FF_STATUS


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_pilot(folder, config):
    folder = Path(folder).resolve(strict=True)
    receipt = json.loads((folder / "receipt.json").read_bytes())
    public = json.loads((folder / "public_summary.json").read_bytes())
    details = json.loads((folder / "conditional_metrics_private.json").read_bytes())
    _require(receipt["data_kind"] == public["data_kind"] == details["data_kind"] == KIND,
             "Mismatched private pilot kind")
    _require(receipt["protocol_sha256"] == public["protocol_sha256"] ==
             details["protocol_sha256"] == canonical_hash(config), "Pilot protocol mismatch")
    _require(not receipt["model_ready"] and not receipt["final_period_opened"] and
             not public["model_ready"] and not public["final_period_opened"] and
             not details["actual_model_ready"] and not details["actual_2022_2025_final_period_opened"],
             "Pilot must remain unapproved")
    _require(receipt["private_metrics_unreviewed"] is True
             and public["performance_estimates_published"] is False, "Source approvals not preserved")
    _require(receipt["source_hashes"] == details["source_bindings_sha256"],
             "Private source bindings differ")
    for filename, binding in receipt["files"].items():
        _require(Path(filename).name == filename, "Unsafe private file path")
        path = folder / filename
        _require(path.is_file() and _sha(path) == binding["sha256"]
                 and path.stat().st_size == binding["bytes"], f"Corrupt private output: {filename}")
    predictions = pd.read_csv(folder / "candidate_predictions_private.csv")
    _require(len(predictions) == 2 * public["development_test_rows"]
             and len(predictions) == 232, "Unexpected provisional test count")
    _require(predictions["model"].isin(["baseline", "text"]).all()
             and predictions["fixed_alpha"].eq(public["fixed_alpha"]).all(),
             "Unexpected candidate models")
    _require(predictions["observation_id"].astype(str).notna().all()
             and len(predictions.groupby(["observation_id", "model"])) == len(predictions),
             "Duplicated predictions")
    _require(not predictions["filing_year"].ge(config["holdout_start"]).any(),
             "Holdout predictions in private development output")
    _require(predictions["filing_year"].between(2016, 2021).all(), "Unexpected prediction years")
    expected = [(str(id_), str(model)) for id_, model in
                zip(predictions["observation_id"], predictions["model"], strict=True)]
    _require(len(expected) == len(set(expected)), "Duplicated model/filing predictions")
    # Independent scalar aggregation directly from exported predictions, rather
    # than trusting the model implementation's private conditional totals.
    totals = {"baseline": 0.0, "text": 0.0}
    counts = {"baseline": 0, "text": 0}
    for row in predictions.itertuples(index=False):
        predicted = float(row.prediction)
        target = float(row.target)
        saved_sq = float(row.squared_error)
        _require(all(math.isfinite(v) for v in (predicted, target, saved_sq))
                 and saved_sq >= 0, "Nonfinite squared error")
        _require(math.isclose((target - predicted) ** 2, saved_sq, rel_tol=0, abs_tol=1e-12),
                 "Exported squared error arithmetic mismatch")
        totals[row.model] += saved_sq
        counts[row.model] += 1
        _require(row.label_end > row.reference_session,
                 "A development label ends before the reference session")
    _require(counts == {"baseline": 116, "text": 116}, "Unbalanced model comparison")
    metrics = details["conditional_metrics"]
    _require(math.isclose(totals["baseline"], metrics["baseline_sse"], rel_tol=0, abs_tol=1e-12)
             and math.isclose(totals["text"], metrics["text_sse"], rel_tol=0, abs_tol=1e-12),
             "Original model comparison totals did not independently reconcile")
    _require(math.isclose(1 - totals["text"] / totals["baseline"],
                          metrics["conditional_relative_sse_change"], rel_tol=0, abs_tol=1e-12),
             "Original conditional improvement calculation did not reconcile")
    _require(len(details["folds"]) == 6
             and [fold["test_year"] for fold in details["folds"]] == list(range(2016, 2022)),
             "Unexpected development fold years")
    for fold in details["folds"]:
        year = fold["test_year"]
        _require(all(training_year < year for training_year in fold["training_filing_years"])
                 and date.fromisoformat(fold["training_label_end_max"])
                 < date.fromisoformat(fold["earliest_test_reference_session"]),
                 "Training labels cross test cutoff")
        _require((predictions.filing_year == year).sum() == 2 * fold["test_rows"],
                 "Predictions do not match fold membership counts")
        subset = predictions.loc[predictions.filing_year == year]
        _require(subset["train_rows"].eq(fold["train_rows"]).all(),
                 "Training row counts disagree with actual predictions")
    _require(public["source_approvals"] == 0 and public["historical_identity_approvals"] == 0
             and not public["study_milestones_completed"], "Unexpected source or milestone approvals")
    return {
        "candidate_pairs": int(public["matched_sec_disclosure_pairs"]),
        "development_predictions_per_model": counts["baseline"],
        "models": sorted(counts),
        "years": list(range(2016, 2022)),
        "issuers": public["candidate_issuers"],
        "source_fingerprints_verified": len(receipt["source_hashes"]),
        "private_receipt_sha256": _sha(folder / "receipt.json"),
        "numerical_results": "PRIVATE_UNAPPROVED_NOT_PUBLISHED",
        "independent_prediction_arithmetic_passed": True,
        "development_timing_separation_verified": True,
    }


def validate_market(folder, config):
    folder = Path(folder).resolve(strict=True)
    receipt = json.loads((folder / "receipt.json").read_bytes())
    data = json.loads((folder / "summary.json").read_bytes())
    _require(receipt["status"] == data["status"] == FF_STATUS
             and receipt["summary_sha256"] == _sha(folder / "summary.json"),
             "Source alternative hash/status mismatch")
    _require(not receipt["model_ready"] and not receipt["final_period_opened"]
             and not data["model_ready"] and not data["final_period_opened"]
             and receipt["source_approvals"] == 0
             and data["benchmark_selected"] is False, "Alternate benchmark was falsely approved")
    _require(data["development_return_cutoff"] == "2022-02-02"
             and date.fromisoformat(data["stopped_before_later_public_factor_values"])
             > date.fromisoformat(data["development_return_cutoff"]),
             "Unexpected final-period boundary")
    _require(data["overlap_sessions"] == data["crsp_sessions"] == 3103
             and data["crsp_sessions_missing_in_public"] == 0,
             "Public market source lacks saved development coverage")
    for key, expected in {
        "public_zip": data["public_zip_sha256"],
        "private_crsp_csv": data["private_crsp_source_sha256"],
        "private_crsp_receipt": data["private_inventory_receipt_sha256"],
    }.items():
        _require(receipt["source_hashes_sha256"][key] == expected, "Alternative source receipt mismatch")
    return {
        "matched_development_market_sessions": int(data["overlap_sessions"]),
        "crsp_sessions_missing_from_public_series": data["crsp_sessions_missing_in_public"],
        "public_file_reported_crsp_yyyymm": data["public_file_reported_upstream_crsp_yyyymm"],
        "exact_daily_return_matches": int(data["daily_exact_equality_days"]),
        "comparability_note": "Different factor universe/source versions; no equivalence asserted",
        "private_receipt_sha256": _sha(folder / "receipt.json"),
        "benchmark_approved": False,
    }


def build_checkpoint(pilot, benchmark, output, config):
    out = Path(output)
    _require(not out.exists(), "Do not overwrite a prior public checkpoint")
    p = validate_pilot(pilot, config)
    b = validate_market(benchmark, config)
    final = {
        "schema_version": 1,
        "status": "SEC_BACKED_ALTERNATIVE_EXECUTED_CONDITIONALLY_NOT_APPROVED",
        "protocol_sha256": canonical_hash(config),
        "pilot": p,
        "public_market_source_comparison": b,
        "claim": "Reproducible development-only diagnostic, NOT a validated empirical forecast or completed frozen study",
        "source_approvals_created": 0, "human_reviews_inferred": 0,
        "historical_cik_links_approved": False, "model_ready": False,
        "final_2022_2025_evaluation_opened": False,
        "milestones_5_through_11_complete": False,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n")
    return final


