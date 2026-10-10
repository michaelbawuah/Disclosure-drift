import json
from dataclasses import asdict
from pathlib import Path

import httpx
import pandas as pd
import pytest

from disclosure_research.edgar import SecClient
from disclosure_research.extraction import extract_risk_factors, pair_filings
from disclosure_research.market_data import sha256
from disclosure_research.pilot_expansion import combine_pilot_sources
from disclosure_research.protocol import load_protocol
from disclosure_research.timing import acceptance_from_header, event_window


@pytest.fixture
def pilot_sources(tmp_path):
    responses = {}
    client = SecClient(tmp_path / "cache", "Fixture fixture@example.test", sleep=lambda _: None,
                       transport=httpx.MockTransport(lambda request: httpx.Response(
                           200, content=responses[str(request.url)])))
    sources = []
    for issuer in [123, 456]:
        rows = []
        for year in [2018, 2019]:
            accession = f"{issuer:010d}-{year % 100:02d}-000001"
            source = f"https://www.sec.gov/Archives/fixture/{accession}.htm"
            header_url = f"https://www.sec.gov/Archives/fixture/{accession}.sgml"
            raw = ("<h2>Item 1A. Risk Factors</h2><p>" + "supply competition " * year +
                   "</p><h2>Item 1B. Unresolved Staff Comments</h2>").encode()
            header = f"<ACCEPTANCE-DATETIME>{year}0301100000".encode()
            responses.update({source: raw, header_url: header})
            _, body_meta = client.fetch(source)
            _, header_meta = client.fetch(header_url)
            accepted = acceptance_from_header(header.decode())
            window, extracted = event_window(accepted), extract_risk_factors(raw)
            rows.append({"accessionNumber": accession, "cik": f"{issuer:010d}",
                         "name": "Invented fixture issuer", "filingDate": f"{year}-03-01",
                         "reportDate": f"{year - 1}-12-31", "source_url": source,
                         "header_url": header_url, "download_sha256": body_meta["sha256"],
                         "header_sha256": header_meta["sha256"], "risk_text": extracted.text,
                         "risk_token_count": extracted.token_count, "extraction_version": extracted.version,
                         "extraction_status": extracted.status, "acceptance_timestamp": accepted.isoformat(),
                         "acceptanceDateTime": f"{year}-03-01T15:00:00Z",
                         **{key: value for key, value in asdict(window).items() if key != "return_sessions"}})
        path = tmp_path / str(issuer)
        path.mkdir()
        pd.DataFrame(rows).to_parquet(path / "filings.parquet", index=False)
        pairs, _ = pair_filings(rows, 2019, 2021)
        pd.DataFrame(pairs).to_parquet(path / "filing_pairs.parquet", index=False)
        sources.append(path)
    return {"source_directories": sources, "output": tmp_path / "combined",
            "cache": tmp_path / "cache", "resolutions": None, "config": load_protocol()}


def test_combination_preserves_sources_and_reaudits_all_original_filings(pilot_sources):
    hashes = {str(path): sha256(path.read_bytes()) for directory in pilot_sources["source_directories"]
              for path in directory.glob("*.parquet")}
    result = combine_pilot_sources(**pilot_sources)
    assert result["filings"] == result["source_audit"]["automated_evidence_ok"] == 4
    assert result["original_pairs_preserved"] == result["pairs"] == 2
    assert result["source_audit"]["human_reviews_complete"] == 0
    assert result["returns_read"] is result["historical_universe_claim"] is False
    assert result["planned_pilot_pair_count_met"] is False
    checkpoint = json.loads((pilot_sources["output"] / "checkpoint/pilot_checkpoint.json").read_text())
    assert checkpoint["pairs"] == 2
    assert hashes == {path: sha256(Path(path).read_bytes()) for path in hashes}


def test_overlapping_source_accessions_cannot_replace_existing_evidence(pilot_sources):
    first, second = pilot_sources["source_directories"]
    for name in ["filings.parquet", "filing_pairs.parquet"]:
        (second / name).write_bytes((first / name).read_bytes())
    with pytest.raises(ValueError, match="overlap"):
        combine_pilot_sources(**pilot_sources)
    assert not pilot_sources["output"].exists()


def test_mutated_original_pair_is_not_silently_replaced_by_canonical_text(pilot_sources):
    path = pilot_sources["source_directories"][0] / "filing_pairs.parquet"
    frame = pd.read_parquet(path)
    frame.loc[0, "current_text"] = "silently altered risk section"
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="change an existing pair"):
        combine_pilot_sources(**pilot_sources)
    assert not pilot_sources["output"].exists()


def test_holdout_dates_are_rejected_before_loading_full_text(pilot_sources, monkeypatch):
    path = pilot_sources["source_directories"][0] / "filings.parquet"
    pd.DataFrame({"acceptance_date": ["2022-03-01"]}).to_parquet(path, index=False)
    original = pd.read_parquet
    reads = []
    def read(path, *args, **kwargs):
        reads.append(kwargs.get("columns"))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(pd, "read_parquet", read)
    with pytest.raises(ValueError, match="Final-period"):
        combine_pilot_sources(**pilot_sources)
    assert reads == [["acceptance_date"]]
    assert not pilot_sources["output"].exists()


@pytest.mark.parametrize("table", ["filings", "filing_pairs"])
def test_accidental_market_column_is_refused_before_table_deserialization(pilot_sources, monkeypatch, table):
    path = pilot_sources["source_directories"][0] / f"{table}.parquet"
    frame = pd.read_parquet(path)
    frame["target"] = .12345
    frame.to_parquet(path, index=False)
    original, full_reads = pd.read_parquet, []
    def read(*args, **kwargs):
        if kwargs.get("columns") is None:
            full_reads.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(pd, "read_parquet", read)
    with pytest.raises(ValueError, match="only SEC source columns"):
        combine_pilot_sources(**pilot_sources)
    assert full_reads == []
    assert not pilot_sources["output"].exists()


def test_source_changes_after_date_check_cannot_replace_the_bound_snapshot(pilot_sources, monkeypatch):
    path = pilot_sources["source_directories"][0] / "filings.parquet"
    before = path.read_bytes()
    changed = pd.read_parquet(path)
    changed["target"] = .12345
    original, mutated = pd.read_parquet, []
    def read(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs.get("columns") == ["acceptance_date"] and not mutated:
            changed.to_parquet(path, index=False)
            mutated.append(True)
        return result
    monkeypatch.setattr(pd, "read_parquet", read)
    result = combine_pilot_sources(**pilot_sources)
    assert result["input_sources"][0]["filings_sha256"] == sha256(before)
    assert sha256(path.read_bytes()) != sha256(before)
    assert "target" not in original(pilot_sources["output"] / "filings.parquet").columns


def test_corrupt_source_cache_never_produces_a_successful_checkpoint(pilot_sources):
    next(pilot_sources["cache"].glob("*.bin")).write_bytes(b"changed source")
    with pytest.raises(ValueError, match="blocking findings"):
        combine_pilot_sources(**pilot_sources)
    assert not (pilot_sources["output"] / "checkpoint").exists()
    receipt = json.loads((pilot_sources["output"] / "combination_receipt.json").read_text())
    assert receipt["status"] == "blocked_source_audit"
