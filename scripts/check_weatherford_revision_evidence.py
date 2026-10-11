"""Compare a public historical correction with saved development Names snapshots.

This is a literal-field diagnostic for one published case. It does not identify
the saved source vintage, read daily market values, or approve a mapping.
"""

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from disclosure_research import manual_wrds_liquidity_candidates as liquidity
from disclosure_research import manual_wrds_listing_candidates as listing
from disclosure_research.manual_wrds_intake import _private_directory
from disclosure_research.protocol import canonical_hash, load_protocol, verify_lock

PUBLIC_CASE = {
    "source_url": "https://indexes.morningstar.com/api/docs/6abeb4ad280ccc81416648b9",
    "source_title": "CRSP US Stock Databases Release Notes: August 2026 Monthly Update",
    "locator": "PDF page 3, Individual Edits, PERMNO 32791",
    "permno": "32791",
    "company_name": "WEATHERFORD INTERNATIONAL PLC",
    "effective_start": "2015-05-13",
    "effective_end": "2019-05-12",
    "published_changes": {
        "exchange_code": {"from": "0", "to": "1"},
        "primary_exchange": {"from": "X", "to": "N"},
        "trading_status": {"from": "X", "to": "A"},
        "security_status": {"from": "X", "to": "R"},
    },
    "saved_field_literal_comparisons": {"primaryexch": "N", "tradingstatusflg": "A"},
    "release_label_discrepancy": (
        "August title; July data narrative; calendar extends through August; "
        "landing metadata observed as September 30. No saved vintage inferred."
    ),
}


def check_saved_case(listing_directory, *, receipt_sha256, output, config, repo_root="."):
    """Write immutable private occurrences and return an aggregate public summary."""
    verify_lock(config, Path(repo_root) / "configs" / "protocol.lock.json")
    liquidity._sha(receipt_sha256)
    out = _private_directory(output, repo_root)
    bundle = liquidity._load(listing_directory, "listing", config)
    if bundle.sha256 != receipt_sha256:
        raise ValueError("Saved Names receipt differs from the explicit source pin")
    rows_seen, selected, overlap, outside = 0, [], [], []
    seen = set()
    for batch in liquidity._batches(bundle, listing.CANDIDATE_SCHEMA.names):
        for row in batch.to_pylist():
            rows_seen += 1
            if row["candidate_year"] not in liquidity.YEARS or row["known_at"] is not None:
                raise ValueError("Names row exceeds development years or fills unknown availability")
            if (row["source_sha256"] != bundle.receipt["source"]["source_sha256"]
                    or row["source_inventory_sha256"] != bundle.receipt["source"]["inventory_receipt_sha256"]):
                raise ValueError("Names row provenance differs from its bound inventory")
            if row["permno"] != PUBLIC_CASE["permno"]:
                continue
            key = (row["candidate_year"], row["source_csv_record"])
            if key in seen:
                raise ValueError("The same saved source occurrence was repeated")
            seen.add(key)
            selection = f"{row['candidate_year']}-01-01"
            if (row["selection_asof"] != selection
                    or not row["secinfostartdt"] <= selection <= row["secinfoenddt"]):
                raise ValueError("Selected Names occurrence does not cover its saved selection date")
            in_interval = PUBLIC_CASE["effective_start"] <= selection <= PUBLIC_CASE["effective_end"]
            observation = {
                "names_record": row,
                "selection_within_public_correction_interval": in_interval,
                "literal_comparisons": {
                    field: row[field] == expected
                    for field, expected in PUBLIC_CASE["saved_field_literal_comparisons"].items()
                },
                "source_vintage_identified": False,
                "known_at": None,
                "available_at": None,
                "source_approved": False,
            }
            selected.append(observation)
            (overlap if in_interval else outside).append(observation)
    if rows_seen != bundle.receipt["projection"]["rows"]:
        raise ValueError("Names scan did not account for all receipt-bound rows")
    overlap.sort(key=lambda x: (x["names_record"]["candidate_year"], x["names_record"]["source_csv_record"]))
    selected.sort(key=lambda x: (x["names_record"]["candidate_year"], x["names_record"]["source_csv_record"]))
    expected_years = [year for year in liquidity.YEARS
                      if PUBLIC_CASE["effective_start"] <= f"{year}-01-01" <= PUBLIC_CASE["effective_end"]]
    observed_years = sorted({row["names_record"]["candidate_year"] for row in overlap})
    all_match = sum(all(row["literal_comparisons"].values()) for row in overlap)
    summary = {
        "schema_version": 1,
        "status": "SAVED_NAMES_PUBLIC_REVISION_COMPARISON_NOT_VINTAGE_IDENTIFICATION",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": canonical_hash(config),
        "public_revision_case": PUBLIC_CASE,
        "listing_receipt_sha256": bundle.sha256,
        "source_inventory_sha256": bundle.receipt["source"]["inventory_receipt_sha256"],
        "original_names_source_sha256": bundle.receipt["source"]["source_sha256"],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "names_parts_verified": len(bundle.parts),
        "annual_names_rows_scanned": rows_seen,
        "target_annual_occurrences": len(selected),
        "target_occurrences_with_selection_in_correction_interval": len(overlap),
        "target_occurrences_outside_correction_interval": len(outside),
        "expected_annual_selection_years_within_interval": expected_years,
        "observed_annual_selection_years_within_interval": observed_years,
        "missing_annual_selection_years_within_interval": sorted(set(expected_years) - set(observed_years)),
        "overlap_occurrences_matching_both_published_literals": all_match,
        "overlap_occurrences_with_literal_disagreement": len(overlap) - all_match,
        "overlap_occurrences_with_ambiguous_names_snapshot": sum(
            row["names_record"]["ambiguous_security_year"] for row in overlap),
        "comparison_scope": "Saved January 1 Names occurrences; primaryexch and tradingstatusflg literal text only",
        "other_release_fields_mapped": False,
        "complete_daily_interval_compared": False,
        "prior_vintage_compared": False,
        "source_vintage_identified": False,
        "historical_availability_supplied": False,
        "known_at": None,
        "available_at": None,
        "original_names_csv_reread": False,
        "daily_market_files_opened": False,
        "market_outcomes_read": False,
        "final_period_opened": False,
        "prior_arithmetic_review_modified": False,
        "source_approvals": 0,
        "model_ready": False,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".revision-case-", dir=out.parent) as temporary:
        work = Path(temporary) / "bundle"
        work.mkdir()
        private_raw = b"".join(json.dumps(row, ensure_ascii=True, sort_keys=True).encode() + b"\n" for row in selected)
        (work / "matched_names_records.jsonl").write_bytes(private_raw)
        summary["private_occurrences_sha256"] = hashlib.sha256(private_raw).hexdigest()
        summary["private_occurrences_bytes"] = len(private_raw)
        (work / "receipt.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        liquidity._guard([bundle], rehash=True)
        if out.exists():
            raise ValueError("Output appeared during construction; existing evidence preserved")
        os.rename(work, out)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listing-candidates", required=True)
    parser.add_argument("--listing-receipt-sha256", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--protocol", default="configs/protocol.json")
    args = parser.parse_args()
    summary = check_saved_case(args.listing_candidates,
                               receipt_sha256=args.listing_receipt_sha256,
                               output=args.output, config=load_protocol(args.protocol))
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
