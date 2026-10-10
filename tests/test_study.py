import json

import duckdb
import pandas as pd
import pytest

from disclosure_research.market_data import SYNTHETIC, fingerprint, sha256
from disclosure_research.protocol import canonical_hash, load_protocol
from disclosure_research.study import build_full_export_plan, ingest_historical_universe
from disclosure_research.universe import MEMBERSHIP_COLUMNS, year_start_window


def universe_bundle(tmp_path, config):
    """Two invented members; issuer two qualifies only in even-numbered years."""
    folder = tmp_path / "universe"
    folder.mkdir()
    rows = []
    for year in range(config["initial_train_start"], config["holdout_end"] + 1):
        window = {key: value for key, value in year_start_window(year, config).items() if key != "sessions"}
        for issuer in [1, 2] if year % 2 == 0 else [1]:
            row = {"universe_year": year, "cik": f"{issuer:010d}", "security_id": f"synthetic-security-{issuer}",
                   **window, "valid_liquidity_sessions": 60, "mean_dollar_volume_usd": float(3 - issuer),
                   "issuer_rank": issuer, "identity_valid_from": "2008-01-01", "identity_valid_to": "2028-12-31",
                   "identity_evidence_id": "synthetic-identity", "classification_evidence_id": "synthetic-classification"}
            row["universe_membership_id"] = fingerprint(row)
            rows.append(row)
    pd.DataFrame(rows, columns=MEMBERSHIP_COLUMNS).to_parquet(folder / "universe.parquet", index=False)
    manifest = {"schema_version": 1, "data_kind": SYNTHETIC, "protocol_sha256": canonical_hash(config),
                "files": {"universe.parquet": sha256((folder / "universe.parquet").read_bytes())},
                "model_ready": False}
    manifest["universe_id"] = fingerprint(manifest)
    (folder / "universe_manifest.json").write_text(json.dumps(manifest))
    return folder


def rebind_outer_receipt(folder):
    path = folder / "universe_manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["files"]["universe.parquet"] = sha256((folder / "universe.parquet").read_bytes())
    manifest["universe_id"] = fingerprint({key: value for key, value in manifest.items() if key != "universe_id"})
    path.write_text(json.dumps(manifest))


def fake_sec(monkeypatch):
    """Run the actual ingestion/parser against explicitly invented SEC bodies."""
    requests = []

    def list_original_filings(client, cik, start, end):
        requests.append((cik, start, end))
        return [{"cik": cik, "accessionNumber": f"{cik}-{year % 100:02d}-000001",
                 "filingDate": f"{year}-03-01", "reportDate": f"{year - 1}-12-31", "form": "10-K",
                 "acceptanceDateTime": f"{year}-03-01T15:00:00Z",
                 "source_url": f"https://www.sec.gov/{cik}/{year}.htm",
                 "header_url": f"https://www.sec.gov/{cik}/{year}.sgml"}
                for year in range(start, end + 1)]

    monkeypatch.setattr("disclosure_research.ingest.list_original_filings", list_original_filings)

    class Client:
        network_requests = 0

        def fetch(self, url):
            self.network_requests += 1
            year = url.rsplit("/", 1)[-1][:4]
            if url.endswith("sgml"):
                body = f"<ACCEPTANCE-DATETIME>{year}0301100000".encode()
            else:
                body = ("<h2>Item 1A. Risk Factors</h2><p>" + "synthetic competition " * 150 +
                        "</p><h2>Item 2. Properties</h2>").encode()
            return body, {"sha256": sha256(body), "fetched_at": "2026-01-01T00:00:00Z"}

    return Client(), requests


def prohibit_ingestion(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("SEC ingestion was invoked before its historical/prerequisite guard")

    monkeypatch.setattr("disclosure_research.study.ingest_smoke", forbidden)


def test_full_export_plan_has_exact_historical_windows_and_final_2026_tail(tmp_path):
    config = load_protocol()
    summary = build_full_export_plan(tmp_path / "plan", config)
    assert summary["outcomes_loaded"] is False
    assert summary["protocol_sha256"] == canonical_hash(config)
    assert summary["maximum_issuers_per_year"] == 500
    assert summary["universe_selection_years"] == 16
    assert summary["sec_predecessor_filing_year"] == 2009
    assert summary["development"]["filing_acceptance_years"] == [2010, 2021]
    assert summary["development"]["last_label_session"] == "2022-02-02"
    assert summary["holdout"]["filing_acceptance_years"] == [2022, 2025]
    assert summary["holdout"]["last_label_session"] == "2026-02-03"
    assert summary["holdout"]["return_target_values"] == "separate_sealed_export"
    path = tmp_path / "plan" / "year_start_windows.csv"
    assert summary["windows_sha256"] == sha256(path.read_bytes())
    windows = pd.read_csv(path).set_index("universe_year")
    assert windows.index.tolist() == list(range(2010, 2026))
    assert windows.loc[2010, "selection_session"] == "2010-01-04"
    assert windows.loc[2010, "liquidity_start"] == "2009-10-07"
    assert windows.loc[2010, "liquidity_end"] == "2009-12-31"
    assert windows.loc[2025, "selection_session"] == "2025-01-02"
    assert windows.loc[2025, "liquidity_end"] == "2024-12-31"
    assert (windows.liquidity_end < windows.selection_asof).all()
    assert json.loads((tmp_path / "plan" / "full_export_plan.json").read_bytes()) == summary


def test_export_plan_preserves_an_existing_checkpoint(tmp_path):
    folder = tmp_path / "plan"
    folder.mkdir()
    marker = folder / "previous.txt"
    marker.write_text("preserve this source request")
    with pytest.raises(ValueError, match="preserve"):
        build_full_export_plan(folder, load_protocol())
    assert marker.read_text() == "preserve this source request"


def test_ingestion_filters_pairs_by_historical_acceptance_year_membership_and_updates_duckdb(tmp_path, monkeypatch):
    config = load_protocol()
    universe = universe_bundle(tmp_path, config)
    client, requests = fake_sec(monkeypatch)
    out = tmp_path / "collected"
    summary = ingest_historical_universe(universe, client, out, config)
    assert requests == [("0000000001", 2009, 2021), ("0000000002", 2009, 2021)]
    assert summary["filings_downloaded"] == 26
    assert summary["pairs_before_membership_filter"] == 24
    assert summary["pairs_ready_for_manual_review"] == summary["historical_pairs_retained"] == 18
    assert summary["membership_exclusions"] == 6
    assert summary["manual_audit"] == "pending"
    assert summary["market_returns_loaded"] is False
    assert summary["empirical_ready"] is False
    assert summary["partition"] == "development"
    pairs = pd.read_parquet(out / "filing_pairs.parquet")
    issuer_two = pairs.loc[pairs.cik == "0000000002"]
    assert issuer_two.acceptance_date.str[:4].astype(int).tolist() == [2010, 2012, 2014, 2016, 2018, 2020]
    assert pairs.loc[pairs.accession == "0000000002-10-000001", "previous_accession"].item() == "0000000002-09-000001"
    # Preserve source/predecessor filings for audit even where annual membership
    # excludes the corresponding forecast event.
    assert len(pd.read_parquet(out / "filings.parquet")) == 26
    excluded = json.loads((out / "membership_exclusions.json").read_bytes())
    assert len(excluded) == 6
    assert all(row["cik"] == "0000000002" for row in excluded)
    assert set(row["observation_id"] for row in excluded).isdisjoint(pairs.accession)
    with duckdb.connect(str(out / "research.duckdb"), read_only=True) as connection:
        sql_pairs = connection.execute("SELECT * FROM filing_pairs ORDER BY accession").df()
    pd.testing.assert_frame_equal(pairs.sort_values("accession").reset_index(drop=True), sql_pairs, check_dtype=False)
    assert json.loads((out / "ingestion_summary.json").read_bytes()) == summary


@pytest.mark.parametrize("authorization", [None, lambda: None, lambda: True, lambda: {},
                                           lambda: {"prerequisites_verified": False},
                                           lambda: {"prerequisites_verified": True, "protocol_sha256": "0" * 64}])
def test_holdout_refusal_occurs_before_ingestion(tmp_path, monkeypatch, authorization):
    config = load_protocol()
    universe = universe_bundle(tmp_path, config)
    prohibit_ingestion(monkeypatch)
    with pytest.raises(ValueError, match="prerequisites|blocked"):
        ingest_historical_universe(universe, object(), tmp_path / "collected", config,
                                   partition="holdout", authorization=authorization)
    assert not (tmp_path / "collected").exists()


def test_verified_holdout_collection_requests_predecessor_but_retains_only_holdout_pairs(tmp_path, monkeypatch):
    config = load_protocol()
    universe = universe_bundle(tmp_path, config)
    client, requests = fake_sec(monkeypatch)
    authorization_calls = []

    def authorize():
        authorization_calls.append("checked")
        return {"prerequisites_verified": True, "protocol_sha256": canonical_hash(config)}

    out = tmp_path / "holdout"
    summary = ingest_historical_universe(universe, client, out, config, partition="holdout", authorization=authorize)
    assert authorization_calls == ["checked"]
    assert requests == [("0000000001", 2021, 2025), ("0000000002", 2021, 2025)]
    assert summary["pairs_before_membership_filter"] == 8
    assert summary["historical_pairs_retained"] == 6
    assert summary["membership_exclusions"] == 2
    assert summary["empirical_ready"] is False
    pairs = pd.read_parquet(out / "filing_pairs.parquet")
    assert set(pairs.acceptance_date.str[:4]) == {"2022", "2023", "2024", "2025"}
    assert pairs.loc[pairs.accession == "0000000001-22-000001", "previous_accession"].item() == "0000000001-21-000001"


def test_changed_membership_table_is_rejected_before_source_collection(tmp_path, monkeypatch):
    config = load_protocol()
    universe = universe_bundle(tmp_path, config)
    frame = pd.read_parquet(universe / "universe.parquet")
    frame.loc[0, "mean_dollar_volume_usd"] += 1
    frame.to_parquet(universe / "universe.parquet", index=False)
    prohibit_ingestion(monkeypatch)
    with pytest.raises(ValueError, match="membership table changed"):
        ingest_historical_universe(universe, object(), tmp_path / "collected", config)


def test_stale_membership_fingerprint_is_rejected_even_with_refreshed_outer_hashes(tmp_path, monkeypatch):
    config = load_protocol()
    universe = universe_bundle(tmp_path, config)
    frame = pd.read_parquet(universe / "universe.parquet")
    frame.loc[0, "mean_dollar_volume_usd"] += 1
    frame.to_parquet(universe / "universe.parquet", index=False)
    rebind_outer_receipt(universe)
    prohibit_ingestion(monkeypatch)
    with pytest.raises(ValueError, match="membership fingerprint changed"):
        ingest_historical_universe(universe, object(), tmp_path / "collected", config)


def test_missing_historical_year_is_not_silently_skipped(tmp_path, monkeypatch):
    config = load_protocol()
    universe = universe_bundle(tmp_path, config)
    frame = pd.read_parquet(universe / "universe.parquet")
    frame.loc[frame.universe_year != 2017].to_parquet(universe / "universe.parquet", index=False)
    rebind_outer_receipt(universe)
    prohibit_ingestion(monkeypatch)
    with pytest.raises(ValueError, match="missing study year"):
        ingest_historical_universe(universe, object(), tmp_path / "collected", config)


def test_duplicate_issuer_year_is_not_interpreted_as_multiple_classes_to_ingest(tmp_path, monkeypatch):
    config = load_protocol()
    universe = universe_bundle(tmp_path, config)
    frame = pd.read_parquet(universe / "universe.parquet")
    pd.concat([frame, frame.iloc[:1]], ignore_index=True).to_parquet(universe / "universe.parquet", index=False)
    rebind_outer_receipt(universe)
    prohibit_ingestion(monkeypatch)
    with pytest.raises(ValueError, match="one share class"):
        ingest_historical_universe(universe, object(), tmp_path / "collected", config)


def test_historical_ingestion_does_not_overwrite_existing_sources(tmp_path, monkeypatch):
    config = load_protocol()
    universe = universe_bundle(tmp_path, config)
    out = tmp_path / "collected"
    out.mkdir()
    (out / "checkpoint.txt").write_text("original source checkpoint")
    prohibit_ingestion(monkeypatch)
    with pytest.raises(ValueError, match="exists"):
        ingest_historical_universe(universe, object(), out, config)
    assert (out / "checkpoint.txt").read_text() == "original source checkpoint"
