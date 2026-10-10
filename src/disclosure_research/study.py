"""Outcome-free full-study export planning and historical-universe SEC ingestion."""

import io
import json
import tempfile
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
from pandas.api.types import is_integer_dtype

from .dataset import _valid_universe
from .ingest import ingest_smoke
from .market_data import development_return_end, fingerprint, sha256, strings
from .protocol import canonical_hash
from .timing import NY, event_window
from .universe import MEMBERSHIP_COLUMNS, UNIVERSE_TABLES, year_start_window


def build_full_export_plan(output, config) -> dict:
    """Request historical populations and split sources without inspecting returns."""
    out = Path(output)
    if out.exists():
        raise ValueError("Export-plan output exists; preserve prior requests")
    windows = [{"universe_year": year, **{key: value for key, value in
                year_start_window(year, config).items() if key != "sessions"}}
               for year in range(config["initial_train_start"], config["holdout_end"] + 1)]
    last = event_window(datetime(config["holdout_end"], 12, 31, 23, 59, tzinfo=NY)).label_end
    plan = {"schema_version": 1, "protocol_sha256": canonical_hash(config),
            "outcomes_loaded": False, "universe_selection_years": len(windows),
            "maximum_issuers_per_year": config["universe_max_issuers"],
            "population": "All historically eligible US common stocks, including later delistings",
            "never_use": "A current constituent list or the 20-issuer parser pilot",
            "universe_normalized_columns": {key: sorted(value) for key, value in UNIVERSE_TABLES.items()},
            "development": {"filing_acceptance_years": [config["initial_train_start"], config["development_end"]],
                            "last_label_session": development_return_end(config),
                            "return_target_values": "development_only_separate_export"},
            "holdout": {"filing_acceptance_years": [config["holdout_start"], config["holdout_end"]],
                        "last_label_session": last, "return_target_values": "separate_sealed_export",
                        "access": "validated_development_freeze_prerequisites_required"},
            "sec_predecessor_filing_year": config["initial_train_start"] - 1,
            "source_review_required": ["exact vendor release and query metadata",
               "historical population and common-stock classification coverage",
               "dated CIK/security links including share classes and finite end bounds",
               "USD price/volume and capitalization units", "total return with dividends and delisting once",
               "value-weighted total-return benchmark", "historical availability versus later revisions"],
            "license": "Keep raw market exports and event-level market values private"}
    out.mkdir(parents=True)
    pd.DataFrame(windows).to_csv(out / "year_start_windows.csv", index=False)
    plan["windows_sha256"] = sha256((out / "year_start_windows.csv").read_bytes())
    (out / "full_export_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    return plan


def ingest_historical_universe(universe, client, output, config, *, partition="development",
                              rules=None, authorization=None) -> dict:
    """Ingest historical members, preserving original filings and excluded pairs.

    Source collection is not identity or extraction sign-off. Holdout collection
    additionally requires a freshly verified development prerequisite callback.
    """
    folder, out = Path(universe), Path(output)
    if out.exists():
        raise ValueError("Historical ingestion output exists; use a new checkpoint")
    manifest = json.loads((folder / "universe_manifest.json").read_text())
    signed = {key: value for key, value in manifest.items() if key != "universe_id"}
    if (manifest.get("universe_id") != fingerprint(signed)
            or manifest.get("protocol_sha256") != canonical_hash(config)):
        raise ValueError("Historical universe receipt changed")
    raw = (folder / "universe.parquet").read_bytes()
    if sha256(raw) != manifest["files"]["universe.parquet"]:
        raise ValueError("Historical membership table changed")
    if partition == "development":
        start, end = config["initial_train_start"], config["development_end"]
    elif partition == "holdout":
        if not callable(authorization):
            raise ValueError("Holdout source collection requires verified development prerequisites")
        receipt = authorization()
        if (not isinstance(receipt, dict) or receipt.get("prerequisites_verified") is not True
                or receipt.get("protocol_sha256") != canonical_hash(config)):
            raise ValueError("Holdout source collection remains blocked by research prerequisites")
        start, end = config["holdout_start"], config["holdout_end"]
    else:
        raise ValueError("Unknown historical ingestion partition")
    # Parse exactly the bytes whose hash was checked above. Validate individual
    # memberships too: a refreshed outer receipt must not hide stale row proofs.
    members = pd.read_parquet(io.BytesIO(raw))
    if set(MEMBERSHIP_COLUMNS) - set(members.columns):
        raise ValueError("Historical membership table is missing selection evidence columns")
    if not is_integer_dtype(members.universe_year) or members.universe_year.isna().any():
        raise ValueError("Historical membership years must be explicit integers")
    members = members.loc[members.universe_year.between(start, end)]
    if set(members.universe_year) != set(range(start, end + 1)):
        raise ValueError("Historical universe has an unexplained missing study year")
    for column in ("cik", "security_id", "universe_membership_id"):
        strings(members[column], f"universe.{column}")
    if not members.cik.str.fullmatch(r"\d{10}").all() or (members.cik == "0000000000").any():
        raise ValueError("Historical members require canonical nonzero 10-digit CIK strings")
    if (members.duplicated(["universe_year", "cik"]).any() or
            members.duplicated(["universe_year", "security_id"]).any()):
        raise ValueError("Historical members must contain one share class per issuer/year")
    _valid_universe(members, config, partition)
    companies = [{"cik": cik, "name": f"Historical CIK {cik}"} for cik in sorted(members.cik.unique())]
    request = {"companies": companies, "filing_year_start": start - 1, "filing_year_end": end,
               "pair_year_start": start, "pair_year_end": end,
               "purpose": f"historical_{partition}_source_collection_not_audit_approval"}
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".historical-ingest-", dir=out.parent) as temporary:
        stage = Path(temporary) / "collection"
        summary = ingest_smoke(request, client, stage, rules)
        pairs_path = stage / "filing_pairs.parquet"
        exclusions = []
        if pairs_path.exists():
            pairs = pd.read_parquet(pairs_path)
            summary["pairs_before_membership_filter"] = len(pairs)
            keys = set(zip(members.cik, members.universe_year, strict=True))
            keep = [(cik, int(date[:4])) in keys for cik, date in
                    zip(pairs.cik, pairs.acceptance_date, strict=True)]
            exclusions = [{"observation_id": row.accession, "cik": row.cik,
                           "reason": "not_in_historical_universe_for_acceptance_year"}
                          for row in pairs.loc[[not value for value in keep]].itertuples()]
            pairs = pairs.loc[keep]
            pairs.to_parquet(pairs_path, index=False)
            with duckdb.connect(str(stage / "research.duckdb")) as con:
                con.register("accepted_pairs", pairs)
                con.execute("CREATE OR REPLACE TABLE filing_pairs AS SELECT * FROM accepted_pairs")
            summary["historical_pairs_retained"] = len(pairs)
            summary["pairs_ready_for_manual_review"] = len(pairs)
            summary["coverage_by_acceptance_year"] = pairs.assign(
                year=pairs.acceptance_date.str[:4]).groupby("year").size().to_dict()
        else:
            summary["pairs_before_membership_filter"] = 0
            summary["historical_pairs_retained"] = 0
            summary["pairs_ready_for_manual_review"] = 0
            summary["coverage_by_acceptance_year"] = {}
        summary.update({"partition": partition, "universe_id": manifest["universe_id"],
                        "protocol_sha256": canonical_hash(config), "market_returns_loaded": False,
                        "membership_exclusions": len(exclusions), "empirical_ready": False})
        (stage / "membership_exclusions.json").write_text(json.dumps(exclusions, indent=2) + "\n")
        (stage / "ingestion_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        stage.rename(out)
    return summary
