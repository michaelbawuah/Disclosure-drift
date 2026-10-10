import json

import numpy as np
import pandas as pd
import pytest

from disclosure_research.market_data import SYNTHETIC, sha256
from disclosure_research.protocol import load_protocol
from disclosure_research.universe import (
    UNIVERSE_TABLES,
    build_universe,
    select_historical_universe,
    year_start_window,
)


def inputs(config=None):
    config = config or load_protocol()
    window = year_start_window(2021, config)
    listings, links, daily = [], [], []
    for security, cik, value, valid in [("class-a", "0000000001", 100.0, 60),
                                       ("class-b", "0000000001", 200.0, 60),
                                       ("other", "0000000002", 300.0, 60),
                                       ("short", "0000000003", 900.0, 39),
                                       ("foreign", "0000000004", 1000.0, 60)]:
        listings.append({"security_id": security, "valid_from": "2010-01-01", "valid_to": "2025-12-31",
                         "market_country": "GB" if security == "foreign" else "US",
                         "share_type": "COMMON_STOCK", "listing_status": "ACTIVE",
                         "known_at": "2010-01-01T00:00:00+00:00", "classification_source": "synthetic history",
                         "evidence_id": "historical-record"})
        links.append({"security_id": security, "cik": cik, "valid_from": "2010-01-01", "valid_to": "2025-12-31",
                      "known_at": "2010-01-01T00:00:00+00:00", "mapping_source": "synthetic historical link",
                      "evidence_id": "historical-record"})
        for session in window["sessions"][-valid:]:
            daily.append({"security_id": security, "session": session, "dollar_volume_usd": value,
                          "available_at": f"{session}T20:00:00-05:00"})
    # A daily value can be available at the close; the last session's value must
    # not be discarded by a helper's after-close publication convention.
    for row in daily:
        if row["session"] == window["liquidity_end"]:
            row["available_at"] = window["information_cutoff"]
    return pd.DataFrame(listings), pd.DataFrame(daily), pd.DataFrame(links)


def select(tables, config=None):
    return select_historical_universe(tables[0], tables[1], tables[2], [2021], config or load_protocol())


def test_historical_selection_minimum_class_choice_and_rank():
    members, exclusions = select(inputs())
    assert members.security_id.tolist() == ["other", "class-b"]
    assert members.issuer_rank.tolist() == [1, 2]
    assert members.valid_liquidity_sessions.tolist() == [60, 60]
    assert set(exclusions.security_id) == {"class-a", "short", "foreign"}
    assert exclusions.set_index("security_id").loc["short", "valid_liquidity_sessions"] == 39
    assert members.cik.nunique() == len(members)


def test_forty_valid_prior_sessions_qualify_without_imputation():
    listings, daily, links = inputs()
    extra = daily.loc[daily.security_id == "class-a"].iloc[0].to_dict()
    extra.update(security_id="short", dollar_volume_usd=900.0)
    daily = pd.concat([daily, pd.DataFrame([extra])], ignore_index=True)
    members, _ = select((listings, daily, links))
    assert members.iloc[0].security_id == "short"
    assert members.iloc[0].valid_liquidity_sessions == 40


def test_future_bad_liquidity_and_later_delisting_cannot_change_selection():
    tables = inputs()
    expected, _ = select(tables)
    listings, daily, links = [table.copy() for table in tables]
    daily = pd.concat([daily, pd.DataFrame([{"security_id": "class-a", "session": "2021-12-01",
                                          "dollar_volume_usd": "unusable future value", "available_at": "future unknown"}])],
                      ignore_index=True)
    # A future terminal date does not make the selected class disappear at January 1.
    listings.loc[listings.security_id == "class-b", "valid_to"] = "2021-06-01"
    members, _ = select((listings, daily, links))
    pd.testing.assert_frame_equal(expected, members)


def test_values_published_after_selection_cannot_help_liquidity_minimum():
    listings, daily, links = inputs()
    affected = daily.index[daily.security_id == "class-b"][:21]
    daily.loc[affected, "available_at"] = "2021-01-02T00:00:00+00:00"
    members, ledger = select((listings, daily, links))
    assert "class-b" not in set(members.security_id)
    assert "class-a" in set(members.security_id)
    assert ledger.set_index("security_id").loc["class-b", "valid_liquidity_sessions"] == 39


def test_missing_historical_classification_cannot_be_backfilled_from_future():
    listings, daily, links = inputs()
    listings.loc[listings.security_id == "other", "share_type"] = None
    future = listings.loc[listings.security_id == "other"].iloc[0].to_dict()
    future.update(share_type="COMMON_STOCK", known_at="2022-01-01T00:00:00+00:00")
    listings = pd.concat([listings, pd.DataFrame([future])], ignore_index=True)
    members, ledger = select((listings, daily, links))
    assert "other" not in set(members.security_id)
    assert ledger.set_index("security_id").loc["other", "reason"] == "missing_historical_classification_or_evidence"


def test_ambiguous_permanent_security_mapping_fails_closed():
    listings, daily, links = inputs()
    duplicate = links.iloc[0].to_dict()
    duplicate["cik"] = "0000000999"
    links = pd.concat([links, pd.DataFrame([duplicate])], ignore_index=True)
    with pytest.raises(ValueError, match="Ambiguous"):
        select((listings, daily, links))


def test_duplicate_daily_key_fails_closed():
    listings, daily, links = inputs()
    daily = pd.concat([daily, daily.iloc[:1]], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate historical"):
        select((listings, daily, links))


def test_naive_historical_availability_is_rejected():
    listings, daily, links = inputs()
    daily.loc[0, "available_at"] = "2020-10-01T12:00:00"
    with pytest.raises(ValueError, match="timezone"):
        select((listings, daily, links))


def test_invalid_liquidity_values_are_excluded_from_valid_count():
    listings, daily, links = inputs()
    affected = daily.index[daily.security_id == "class-b"][:21]
    daily.loc[affected, "dollar_volume_usd"] = np.nan
    members, ledger = select((listings, daily, links))
    assert "class-b" not in set(members.security_id)
    assert ledger.set_index("security_id").loc["class-b", "valid_liquidity_sessions"] == 39


def test_rank_cutoff_applies_after_share_class_deduplication():
    config = {**load_protocol(), "universe_max_issuers": 1}
    members, ledger = select(inputs(config), config)
    assert members.security_id.tolist() == ["other"]
    assert ledger.set_index("security_id").loc["class-b", "reason"] == "outside_frozen_issuer_rank"


def test_selection_is_stable_under_source_row_reordering():
    tables = inputs()
    expected, ledger = select(tables)
    actual, other_ledger = select(tuple(frame.sample(frac=1, random_state=12) for frame in tables))
    pd.testing.assert_frame_equal(expected, actual)
    pd.testing.assert_frame_equal(ledger.sort_values("security_id").reset_index(drop=True),
                                  other_ledger.sort_values("security_id").reset_index(drop=True))


def test_file_wrapper_hashes_sources_and_does_not_claim_approval(tmp_path):
    listings, daily, links = inputs()
    frames = {"listings": listings, "daily_liquidity": daily, "identity_links": links}
    evidence = tmp_path / "history.txt"
    evidence.write_text("Invented historical classifications and mapping document for a unit test.")
    specs = {}
    for name, frame in frames.items():
        path = tmp_path / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        specs[name] = {"path": path.name, "sha256": sha256(path.read_bytes()),
                       "field_mapping": {column: f"synthetic {column}" for column in UNIVERSE_TABLES[name]}}
    source = {"schema_version": 1, "data_kind": SYNTHETIC, "provider": "unit test",
              "normalization_notes": "Invented USD volumes", "population_coverage": "five synthetic classes",
              "exported_at": "2026-01-01T00:00:00Z", "years": [2021], "tables": specs,
              "evidence": {"historical-record": {"path": evidence.name, "sha256": sha256(evidence.read_bytes())}}}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(source))
    summary = build_universe(path, tmp_path / "built", load_protocol())
    assert summary["memberships"] == 2
    assert summary["model_ready"] is False
    evidence.write_text("Changed source document")
    with pytest.raises(ValueError, match="Hash mismatch"):
        build_universe(path, tmp_path / "changed", load_protocol())
