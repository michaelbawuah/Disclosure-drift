"""Historical year-start issuer selection from an explicit normalized contract.

This module does not translate vendor codes or infer identity from current tickers.
``listings`` has security_id, valid_from, valid_to, market_country (US for a US
listing), share_type (COMMON_STOCK), listing_status (ACTIVE), known_at,
classification_source and evidence_id. Other explicit classifications are
ineligible. The inclusive intervals describe historical listing classifications.
``identity_links`` has security_id, cik, valid_from, valid_to, known_at,
mapping_source and evidence_id. Several classes may map to one issuer, but a
security may have exactly one issuer at selection. ``daily_liquidity`` has
security_id, session, dollar_volume_usd and available_at. USD dollar volume must
already have its documented price/volume adjustment and currency conversion.

Selection is effective January 1, using only facts known by the final XNYS close
of the previous year and its preceding 59 sessions. Missing/invalid numeric
liquidity observations do not count toward the 40-observation minimum. No current
survival filter is used. Liquidity ties use permanent security_id, then CIK, in
ascending order. Source documentation must establish historical population
coverage; successful arithmetic alone cannot certify it.
"""

import io
import json
import tempfile
from datetime import datetime, timezone
from numbers import Real
from pathlib import Path

import numpy as np
import pandas as pd

from .market_data import NORMALIZED, SYNTHETIC, fingerprint, iso_dates, required_text, sha256, strings
from .protocol import canonical_hash
from .timing import calendar

UNIVERSE_TABLES = {
    "listings": {"security_id", "valid_from", "valid_to", "market_country", "share_type",
                 "listing_status", "known_at", "classification_source", "evidence_id"},
    "identity_links": {"security_id", "cik", "valid_from", "valid_to", "known_at",
                       "mapping_source", "evidence_id"},
    "daily_liquidity": {"security_id", "session", "dollar_volume_usd", "available_at"},
}
MEMBERSHIP_COLUMNS = [
    "universe_year", "cik", "security_id", "selection_asof", "selection_session",
    "information_cutoff", "liquidity_start", "liquidity_end", "valid_liquidity_sessions",
    "mean_dollar_volume_usd", "issuer_rank", "identity_valid_from", "identity_valid_to",
    "identity_evidence_id", "classification_evidence_id", "universe_membership_id",
]
EXCLUSION_COLUMNS = ["universe_year", "security_id", "cik", "reason",
                     "valid_liquidity_sessions", "mean_dollar_volume_usd"]


def aware_timestamp(value, label: str) -> pd.Timestamp:
    """Parse only explicit ISO timestamps; dates and naive wall times are unsafe."""
    required_text(value, label)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} requires an ISO timestamp with timezone") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} requires an explicit timezone")
    return pd.Timestamp(parsed).tz_convert("UTC")


def year_start_window(year: int, config: dict) -> dict:
    """Return the fixed pre-year liquidity sessions and information cutoff."""
    if isinstance(year, bool) or not isinstance(year, int):
        raise ValueError("Universe year must be an integer")
    if not config["initial_train_start"] <= year <= config["holdout_end"]:
        raise ValueError("Universe year is outside the frozen study period")
    cal = calendar()
    sessions = cal.sessions.strftime("%Y-%m-%d").tolist()
    asof = f"{year:04d}-01-01"
    first = next((i for i, value in enumerate(sessions) if value >= asof), None)
    lookback = config["liquidity_lookback_sessions"]
    if first is None or first < lookback:
        raise ValueError("Insufficient calendar coverage for historical universe")
    expected = sessions[first - lookback:first]
    return {"selection_asof": asof, "selection_session": sessions[first],
            "information_cutoff": cal.session_close(expected[-1]).isoformat(),
            "liquidity_start": expected[0], "liquidity_end": expected[-1],
            "sessions": tuple(expected)}


def _table_contract(frame: pd.DataFrame, name: str) -> None:
    missing = UNIVERSE_TABLES[name] - set(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {sorted(missing)}")
    strings(frame.security_id, f"{name}.security_id")
    if name == "daily_liquidity":
        iso_dates(frame.session, "daily_liquidity.session", sessions=True)
        return
    for column in ("valid_from", "valid_to"):
        iso_dates(frame[column], f"{name}.{column}")
    if (frame.valid_from > frame.valid_to).any():
        raise ValueError(f"{name} has reversed historical intervals")


def _known_snapshot(frame: pd.DataFrame, name: str, window: dict) -> pd.DataFrame:
    """Future classifications never participate in historical eligibility."""
    relevant = frame.loc[(frame.valid_from <= window["selection_asof"]) &
                         (frame.valid_to >= window["selection_asof"])].copy()
    cutoff = pd.Timestamp(window["information_cutoff"])
    stamps = relevant.known_at.map(lambda value: aware_timestamp(value, f"{name}.known_at"))
    relevant = relevant.loc[stamps <= cutoff]
    if relevant.security_id.duplicated().any():
        raise ValueError(f"Ambiguous overlapping historical {name} by permanent security_id")
    return relevant


def select_historical_universe(listings: pd.DataFrame, daily_liquidity: pd.DataFrame,
                               identity_links: pd.DataFrame, years: list[int],
                               config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select one class per issuer without inspecting future liquidity/survival.

    Returns memberships and an explicit candidate-level exclusion ledger. These
    are engineering outputs; use hash-bound source reviews before empirical use.
    """
    if not years or len(set(years)) != len(years):
        raise ValueError("Supply nonempty, unique universe years")
    limit, minimum = config["universe_max_issuers"], config["liquidity_min_valid_sessions"]
    if not 1 <= minimum <= config["liquidity_lookback_sessions"] or limit < 1:
        raise ValueError("Invalid universe liquidity minimum or issuer limit")
    for name, frame in [("listings", listings), ("daily_liquidity", daily_liquidity),
                        ("identity_links", identity_links)]:
        _table_contract(frame, name)
    selected, excluded = [], []
    for year in sorted(years):
        window = year_start_window(year, config)
        known_listings = _known_snapshot(listings, "listings", window)
        links = _known_snapshot(identity_links, "identity_links", window).set_index("security_id")
        historical = daily_liquidity.loc[daily_liquidity.session.isin(window["sessions"])].copy()
        # Validate values only AFTER the historical session cut. Changing a
        # future dollar-volume value, delisting or listing cannot select firms.
        if historical.duplicated(["security_id", "session"]).any():
            raise ValueError("Duplicate historical dollar-volume observations")
        cutoff = pd.Timestamp(window["information_cutoff"])
        availability = historical.available_at.map(
            lambda value: aware_timestamp(value, "daily_liquidity.available_at"))
        historical = historical.loc[availability <= cutoff]
        groups = {key: value for key, value in historical.groupby("security_id", sort=False)}
        relevant_listing_ids = set(listings.loc[(listings.valid_from <= window["selection_asof"]) &
                                                (listings.valid_to >= window["selection_asof"]),
                                                "security_id"])

        def exclude(security, reason, cik="", valid=0, mean=None):
            excluded.append({"universe_year": year, "security_id": security, "cik": cik,
                             "reason": reason, "valid_liquidity_sessions": valid,
                             "mean_dollar_volume_usd": mean})

        for security in sorted(relevant_listing_ids - set(known_listings.security_id)):
            exclude(security, "historical_classification_not_available_by_cutoff")
        candidates = []
        for listing in known_listings.sort_values("security_id").itertuples():
            security = listing.security_id
            fields = [listing.market_country, listing.share_type, listing.listing_status,
                      listing.classification_source, listing.evidence_id]
            if any(not isinstance(value, str) or not value.strip() for value in fields):
                exclude(security, "missing_historical_classification_or_evidence")
                continue
            if (listing.market_country, listing.share_type, listing.listing_status) != (
                    "US", "COMMON_STOCK", "ACTIVE"):
                exclude(security, "ineligible_historical_listing_classification")
                continue
            if security not in links.index:
                exclude(security, "missing_historical_identity")
                continue
            link = links.loc[security]
            if (not isinstance(link.cik, str) or len(link.cik) != 10 or not link.cik.isdigit()
                    or link.cik == "0000000000"):
                raise ValueError("Historical identity requires canonical nonzero 10-digit CIK strings")
            required_text(link.mapping_source, "identity_links.mapping_source")
            required_text(link.evidence_id, "identity_links.evidence_id")
            observations = groups.get(security)
            if observations is None:
                exclude(security, "insufficient_prior_liquidity_sessions", link.cik)
                continue
            values = observations.dollar_volume_usd
            # A future string can make the full source column object-typed;
            # validate historical scalar values instead of its global dtype.
            if any(isinstance(value, (bool, np.bool_)) or
                   (not pd.isna(value) and not isinstance(value, Real)) for value in values):
                raise ValueError("Historical dollar_volume_usd requires numeric values; no coercion")
            numbers = np.array([np.nan if pd.isna(value) else float(value) for value in values])
            valid = numbers[np.isfinite(numbers) & (numbers >= 0)]
            mean = float(valid.mean()) if len(valid) else None
            if len(valid) < minimum:
                exclude(security, "insufficient_prior_liquidity_sessions", link.cik, len(valid), mean)
                continue
            if mean is None or not np.isfinite(mean):
                raise ValueError("Mean dollar volume overflowed; verify source units")
            candidates.append({"universe_year": year, "cik": link.cik, "security_id": security,
                               **{key: value for key, value in window.items() if key != "sessions"},
                               "valid_liquidity_sessions": len(valid), "mean_dollar_volume_usd": mean,
                               "identity_valid_from": link.valid_from,
                               "identity_valid_to": link.valid_to,
                               "identity_evidence_id": link.evidence_id,
                               "classification_evidence_id": listing.evidence_id})
        candidates.sort(key=lambda row: (-row["mean_dollar_volume_usd"], row["security_id"], row["cik"]))
        issuer_seen, rank = set(), 0
        for row in candidates:
            cik = row["cik"]
            if cik in issuer_seen:
                exclude(row["security_id"], "less_liquid_share_class_or_permanent_id_tiebreak", cik,
                        row["valid_liquidity_sessions"], row["mean_dollar_volume_usd"])
                continue
            issuer_seen.add(cik)
            rank += 1
            if rank > limit:
                exclude(row["security_id"], "outside_frozen_issuer_rank", cik,
                        row["valid_liquidity_sessions"], row["mean_dollar_volume_usd"])
                continue
            row["issuer_rank"] = rank
            row["universe_membership_id"] = fingerprint(row)
            selected.append(row)
    return (pd.DataFrame(selected, columns=MEMBERSHIP_COLUMNS),
            pd.DataFrame(excluded, columns=EXCLUSION_COLUMNS))


def _relative_bytes(root: Path, spec: dict, label: str) -> bytes:
    required_text(spec.get("path"), f"{label}.path")
    relative = Path(spec["path"])
    resolved = (root / relative).resolve()
    if relative.is_absolute() or not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"{label} path must remain inside its source directory")
    body = resolved.read_bytes()
    if sha256(body) != spec.get("sha256"):
        raise ValueError(f"Hash mismatch: {label}")
    return body


def build_universe(manifest_path: str | Path, output: str | Path, config: dict) -> dict:
    """Publish selection/exclusions with source hashes; never imply human approval.

    Manifest version 1 declares data_kind, provider, normalization_notes,
    population_coverage, timezone-aware exported_at, years, and ``tables`` with
    path/SHA-256 and an explicit field_mapping for every normalized column.
    ``evidence`` is a nonempty mapping from evidence_id to local path/SHA-256.
    Listed classifications and mappings must refer to one of those documents.
    """
    path, output = Path(manifest_path), Path(output)
    if output.exists():
        raise ValueError("Universe output exists; preserve the prior source-bound selection")
    raw = path.read_bytes()
    manifest = json.loads(raw)
    if manifest.get("schema_version") != 1 or manifest.get("data_kind") not in {SYNTHETIC, NORMALIZED}:
        raise ValueError("Unknown universe source schema or data kind")
    for key in ("provider", "normalization_notes", "population_coverage"):
        required_text(manifest.get(key), key)
    aware_timestamp(manifest.get("exported_at"), "exported_at")
    if set(manifest.get("tables", {})) != set(UNIVERSE_TABLES):
        raise ValueError("Universe source must supply all three normalized tables")
    evidence = manifest.get("evidence")
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError("Historical classification and identity evidence is required")
    for evidence_id, spec in evidence.items():
        required_text(evidence_id, "evidence_id")
        _relative_bytes(path.parent, spec, evidence_id)
    tables = {}
    for name, columns in UNIVERSE_TABLES.items():
        spec = manifest["tables"][name]
        if set(spec.get("field_mapping", {})) != columns:
            raise ValueError(f"Record every normalized {name} field mapping")
        for value in spec["field_mapping"].values():
            required_text(value, f"{name}.field_mapping")
        body = _relative_bytes(path.parent, spec, name)
        tables[name] = pd.read_parquet(io.BytesIO(body), columns=sorted(columns))
    members, exclusions = select_historical_universe(
        tables["listings"], tables["daily_liquidity"], tables["identity_links"],
        manifest.get("years", []), config)
    for column in ("identity_evidence_id", "classification_evidence_id"):
        if not set(members[column]).issubset(evidence):
            raise ValueError("Selected historical facts lack hash-bound source evidence")
    summary = {"schema_version": 1, "data_kind": manifest["data_kind"],
               "protocol_sha256": canonical_hash(config), "created_at": datetime.now(timezone.utc).isoformat(),
               "source_manifest_sha256": sha256(raw), "years": sorted(manifest["years"]),
               "memberships": len(members), "exclusions": len(exclusions),
               "selection_rule": "prior_60_XNYS_sessions; minimum_40_valid; most_liquid_class; up_to_500_issuers",
               "tie_rule": "ascending_permanent_security_id_then_cik",
               "approval_status": "source_declarations_recorded_not_independent_approval",
               "model_ready": False, "later_delistings_removed": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".universe-", dir=output.parent) as temporary:
        stage = Path(temporary) / "universe"
        stage.mkdir()
        members.to_parquet(stage / "universe.parquet", index=False)
        exclusions.to_parquet(stage / "exclusions.parquet", index=False)
        (stage / "source_manifest.json").write_bytes(raw)
        summary["files"] = {p.name: sha256(p.read_bytes()) for p in sorted(stage.iterdir())}
        summary["universe_id"] = fingerprint(summary)
        (stage / "universe_manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
        stage.rename(output)
    return summary
