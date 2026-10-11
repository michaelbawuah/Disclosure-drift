"""Explain saved liquidity-only annual records using complete Names date history.

The categories describe the saved interval geometry. They do not approve an
exclusion, historical identity, source vintage, or information availability.
"""

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from disclosure_research import historical_foundation as foundation
from disclosure_research import manual_wrds_liquidity_candidates as liquidity
from disclosure_research import manual_wrds_listing_candidates as listing
from disclosure_research.manual_wrds_intake import _private_directory
from disclosure_research.protocol import canonical_hash, load_protocol, verify_lock
from disclosure_research.universe import year_start_window


def interval_geometry(records, selection):
    """Classify inclusive source intervals; every duplicate occurrence is retained."""
    if not records:
        return "NO_SAVED_NAMES_HISTORY"
    if any(row["info_start"] <= selection <= row["info_end"] for row in records):
        return "DESCRIPTOR_COVERS_SELECTION"
    if any(row["life_start"] <= selection <= row["life_end"] for row in records):
        return "DESCRIPTOR_GAP_INSIDE_RECORDED_SECURITY_LIFETIME"
    if all(row["life_end"] < selection for row in records):
        return "ALL_RECORDED_SECURITY_LIFETIMES_END_BEFORE_SELECTION"
    if all(row["life_start"] > selection for row in records):
        return "ALL_RECORDED_SECURITY_LIFETIMES_BEGIN_AFTER_SELECTION"
    return "BETWEEN_RECORDED_SECURITY_LIFETIMES"


def check_saved_coverage(foundation_directory, *, foundation_sha256, listing_directory,
                         names_inventory, names_inventory_sha256, output, config, repo_root="."):
    repo = Path(repo_root).resolve(strict=True)
    verify_lock(config, repo / "configs" / "protocol.lock.json")
    out = _private_directory(output, repo)
    bound = foundation._bundle(foundation_directory, foundation_sha256, foundation.STATUS, config)
    annual_names = liquidity._load(listing_directory, "listing", config)
    foundation._require(annual_names.sha256 == bound.receipt["inputs"]["listing_receipt_sha256"],
                        "Annual Names source differs from the completed foundation")
    foundation._require(annual_names.receipt["source"]["inventory_receipt_sha256"]
                        == liquidity._sha(names_inventory_sha256), "Original Names inventory pin differs")
    for directory in (bound.directory, annual_names.directory, Path(names_inventory).resolve(strict=True)):
        foundation._require(not out.is_relative_to(directory) and not directory.is_relative_to(out),
                            "Output must be separate from consumed input directories")
    table = bound.receipt["tables"]["liquidity_only_coverage"]
    parts = foundation._parts(bound, table, foundation.ANNUAL_SCHEMA)
    foundation._require(table["rows"] <= 100_000
                        and table["rows"] == bound.receipt["counts"]["liquidity_only_rows"],
                        "Liquidity-only table row accounting differs or exceeds its bound")
    windows = {year: year_start_window(year, config) for year in liquidity.YEARS}
    observations, seen = [], set()
    columns = ["candidate_year", "security_id", "selection_asof", "information_cutoff",
               "identity_present", "liquidity_present", "identity_evidence_status",
               "meets_numeric_minimum_40", "ordinary_numeric_candidate",
               "rank_eligible_by_candidate_policy", "known_at", "available_at", "identity_approved"]
    for row in foundation._rows(bound, parts, columns):
        year = row["candidate_year"]
        foundation._require(year in windows and row["selection_asof"] == windows[year]["selection_asof"]
                            and row["information_cutoff"] == windows[year]["information_cutoff"],
                            "Annual observation differs from the frozen development window")
        foundation._require(row["identity_present"] is False and row["liquidity_present"] is True
                            and row["identity_evidence_status"] == "NO_ANNUAL_NAMES_IDENTITY_EVIDENCE"
                            and row["ordinary_numeric_candidate"] is False
                            and row["rank_eligible_by_candidate_policy"] is False,
                            "Input is not an unchanged liquidity-only annual observation")
        key = (year, row["security_id"])
        foundation._require(key not in seen, "Annual observation is repeated")
        seen.add(key)
        observations.append(row)
    foundation._require(len(observations) == table["rows"], "Annual observations were lost")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".liquidity-only-names-", dir=out.parent) as temporary:
        work = Path(temporary)
        bundle = work / "bundle"
        bundle.mkdir(mode=0o700)
        (bundle / "input_receipts").mkdir(mode=0o700)
        source = listing._load_source(names_inventory, bundle, config)
        foundation._require(source.receipt_sha256 == names_inventory_sha256
                            and source.sha256 == annual_names.receipt["source"]["source_sha256"]
                            and source.receipt["all_rows"]["rows"] <= 2_000_000,
                            "Complete Names history differs from the bound annual source")
        for name, raw in (("foundation.json", bound.raw), ("listing.json", annual_names.raw)):
            (bundle / "input_receipts" / name).write_bytes(raw)
            (bundle / "input_receipts" / name).chmod(0o400)
        counts, adequate, inadequate = Counter(), Counter(), Counter()
        years = Counter()
        occurrences = 0
        private_path = bundle / "observations.jsonl"
        with closing(sqlite3.connect(work / "history.sqlite3")) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA cache_size=-16384")
            db.execute("PRAGMA temp_store=FILE")
            db.execute("CREATE TABLE source_rows(record INTEGER PRIMARY KEY,permno TEXT,info_start TEXT,"
                       "info_end TEXT,life_start TEXT,life_end TEXT,payload TEXT)")
            actual = listing._date_preflight(source, db)
            db.execute("CREATE INDEX source_permno ON source_rows(permno)")
            with private_path.open("x", encoding="utf-8") as handle:
                for row in sorted(observations, key=lambda item: (item["candidate_year"], item["security_id"])):
                    records = [dict(item) for item in db.execute(
                        "SELECT record,info_start,info_end,life_start,life_end FROM source_rows "
                        "WHERE permno=? ORDER BY record", (row["security_id"],))]
                    status = interval_geometry(records, row["selection_asof"])
                    counts[status] += 1
                    (adequate if row["meets_numeric_minimum_40"] else inadequate)[status] += 1
                    years[str(row["candidate_year"])] += 1
                    occurrences += len(records)
                    observation = {"original_annual_observation": row, "saved_interval_geometry": status,
                                   "source_interval_occurrences": records,
                                   "names_source_sha256": source.sha256,
                                   "names_inventory_sha256": source.receipt_sha256,
                                   "identifier_comparison": "exact raw PERMNO text",
                                   "known_at": None, "available_at": None, "exclusion_approved": False}
                    handle.write(json.dumps(observation, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        private_path.chmod(0o400)
        summary = {
            "schema_version": 1, "status": "SAVED_LIQUIDITY_ONLY_NAMES_GEOMETRY_NOT_EXCLUSION_APPROVAL",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "protocol_sha256": canonical_hash(config),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "foundation_receipt_sha256": bound.sha256,
            "listing_receipt_sha256": annual_names.sha256,
            "names_inventory_sha256": source.receipt_sha256, "names_source_sha256": source.sha256,
            "names_source_bytes": source.identity[2], "names_source_rows_preflighted": actual["rows"],
            "liquidity_only_annual_records": len(observations), "records_by_year": dict(sorted(years.items())),
            "unique_raw_security_identifiers": len({row["security_id"] for row in observations}),
            "source_interval_occurrences_retained": occurrences,
            "geometry_counts": dict(sorted(counts.items())),
            "numeric_minimum_pass_geometry_counts": dict(sorted(adequate.items())),
            "numeric_minimum_fail_geometry_counts": dict(sorted(inadequate.items())),
            "private_observations_sha256": hashlib.sha256(private_path.read_bytes()).hexdigest(),
            "private_observations_bytes": private_path.stat().st_size,
            "identifier_comparison": "exact raw PERMNO text; no normalization or new mapping",
            "all_source_intervals_validated_before_matching": True,
            "source_lifetimes_are_diagnostics_not_historical_knowledge": True,
            "prior_foundation_observations_modified": False, "prior_arithmetic_review_modified": False,
            "daily_market_values_read": False, "market_outcomes_read": False, "final_period_opened": False,
            "source_approvals": 0, "historical_cik_links_created": 0, "human_reviews_created": 0,
            "exclusions_approved": 0, "known_at_inferred": False, "available_at_inferred": False,
            "model_ready": False,
        }
        foundation._require(sum(counts.values()) == len(observations)
                            and sum(adequate.values()) + sum(inadequate.values()) == len(observations),
                            "Geometry categories do not account for all annual records")
        listing._guard(source, rehash=True)
        liquidity._guard([bound, annual_names], rehash=True)
        raw = (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode()
        (bundle / "receipt.json").write_bytes(raw)
        (bundle / "receipt.json").chmod(0o400)
        foundation._require(not out.exists(), "Output appeared while evidence was being prepared")
        bundle.rename(out)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--foundation", required=True)
    parser.add_argument("--foundation-sha256", required=True)
    parser.add_argument("--listing-candidates", required=True)
    parser.add_argument("--names-inventory", required=True)
    parser.add_argument("--names-inventory-sha256", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--protocol", default="configs/protocol.json")
    args = parser.parse_args()
    config = load_protocol(args.protocol)
    result = check_saved_coverage(
        args.foundation, foundation_sha256=args.foundation_sha256,
        listing_directory=args.listing_candidates, names_inventory=args.names_inventory,
        names_inventory_sha256=args.names_inventory_sha256,
        output=args.output, config=config)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
