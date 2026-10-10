import json

import numpy as np
import pandas as pd
import pytest

from disclosure_research.cli import synthetic_dataset
from disclosure_research.market_data import sha256
from disclosure_research.pilot_checkpoint import build_pilot_checkpoint, describe_pairs, pilot_baseline
from disclosure_research.protocol import load_protocol
from disclosure_research.semantic import aggregate_chunks, cosine_distance, token_chunks, validate_spec


@pytest.fixture
def checkpoint_inputs(tmp_path):
    accessions = [f"0000000001-{year % 100:02d}-000001" for year in range(2018, 2021)]
    texts = ["Market risk and credit exposure.", "Market risk and funding pressure.",
             "Market risk and supply constraints."]
    urls = [f"https://www.sec.gov/Archives/{accession}.htm" for accession in accessions]
    filings = pd.DataFrame({"accessionNumber": accessions})
    pairs = pd.DataFrame([
        {"accession": accessions[i], "previous_accession": accessions[i - 1], "cik": "0000000001",
         "acceptance_date": f"{2018 + i}-02-05", "previous_text": texts[i - 1], "current_text": texts[i],
         "source_url": urls[i], "previous_source_url": urls[i - 1]} for i in [1, 2]])
    evidence = pd.DataFrame([
        {"accession": accession, "cik": "0000000001", "risk_text_sha256": sha256(texts[i].encode()),
         "source_url": urls[i], "acceptance_timestamp": f"{2018 + i}-02-05T18:30:00Z",
         "blocking_issues": [], "cautions": ["api_header_timestamp_disagreement"] if i == 0 else [],
         "resolution_method": "registered_reference" if i == 0 else "numbered_item1a",
         "automated_evidence_ok": True, "human_review_complete": False, "assistant_review_complete": False,
         "verified_source": True, "verified_header": True, "verified_risk_source": True}
        for i, accession in enumerate(accessions)])
    paths = {"pairs": tmp_path / "pairs.parquet", "filings": tmp_path / "filings.parquet",
             "evidence": tmp_path / "filing_evidence.parquet", "audit": tmp_path / "audit_summary.json"}
    for name, frame in [("pairs", pairs), ("filings", filings), ("evidence", evidence)]:
        frame.to_parquet(paths[name], index=False)
    audit = {"filings": 3, "issuers": 1, "annual_pairs": 2, "automated_evidence_ok": 3,
             "filings_with_blocking_issues": 0, "human_reviews_complete": 0, "assistant_reviews_complete": 0,
             "timestamp_disagreements": 1, "reference_resolutions": 1,
             "pair_table_sha256": sha256(paths["pairs"].read_bytes()),
             "source_table_sha256": sha256(paths["filings"].read_bytes()),
             "evidence_table_sha256": sha256(paths["evidence"].read_bytes())}
    paths["audit"].write_text(json.dumps(audit))
    return paths, audit


def _build_checkpoint(paths, tmp_path):
    return build_pilot_checkpoint(paths["pairs"], paths["filings"], paths["audit"].parent,
                                  tmp_path / "output", load_protocol())


def test_checkpoint_claims_are_derived_from_hash_bound_filing_evidence(checkpoint_inputs, tmp_path):
    paths, _ = checkpoint_inputs
    receipt = _build_checkpoint(paths, tmp_path)
    assert (receipt["filings"], receipt["pairs"], receipt["source_audit_passes"]) == (3, 2, 3)
    assert receipt["timestamp_disagreements"] == receipt["reference_resolutions"] == 1
    assert receipt["human_filing_reviews"] == 0
    assert receipt["sources"]["filing_evidence"] == sha256(paths["evidence"].read_bytes())
    assert receipt["returns_read"] is receipt["predictive_performance_claim"] is False


@pytest.mark.parametrize("name,match", [("pairs", "matching successful source audit"),
                                        ("filings", "matching successful source audit"),
                                        ("evidence", "fingerprint")])
def test_checkpoint_rejects_mutated_source_bytes(checkpoint_inputs, tmp_path, name, match):
    paths, _ = checkpoint_inputs
    paths[name].write_bytes(paths[name].read_bytes() + b"mutated")
    with pytest.raises(ValueError, match=match):
        _build_checkpoint(paths, tmp_path)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("count", ["filings", "annual_pairs", "automated_evidence_ok",
                                   "human_reviews_complete", "timestamp_disagreements", "reference_resolutions"])
def test_checkpoint_rejects_inconsistent_summary_claims(checkpoint_inputs, tmp_path, count):
    paths, audit = checkpoint_inputs
    audit[count] += 1
    paths["audit"].write_text(json.dumps(audit))
    with pytest.raises(ValueError, match=f"summary differs.*{count}"):
        _build_checkpoint(paths, tmp_path)


def test_checkpoint_pair_must_match_audited_extracted_text(checkpoint_inputs, tmp_path):
    paths, audit = checkpoint_inputs
    pairs = pd.read_parquet(paths["pairs"])
    pairs.loc[0, "current_text"] = "Altered text with a refreshed table fingerprint."
    pairs.to_parquet(paths["pairs"], index=False)
    audit["pair_table_sha256"] = sha256(paths["pairs"].read_bytes())
    paths["audit"].write_text(json.dumps(audit))
    with pytest.raises(ValueError, match="text or source differs"):
        _build_checkpoint(paths, tmp_path)


def test_checkpoint_rejects_unverified_evidence_even_if_summary_passes(checkpoint_inputs, tmp_path):
    paths, audit = checkpoint_inputs
    evidence = pd.read_parquet(paths["evidence"])
    evidence.loc[0, "verified_risk_source"] = False
    evidence.to_parquet(paths["evidence"], index=False)
    audit["evidence_table_sha256"] = sha256(paths["evidence"].read_bytes())
    paths["audit"].write_text(json.dumps(audit))
    with pytest.raises(ValueError, match="blocking or unverified"):
        _build_checkpoint(paths, tmp_path)


def test_descriptive_vocabulary_never_uses_future_year_text():
    frame = synthetic_dataset().rename(columns={"observation_id": "accession"})
    frame["cik"] = "0000000001"
    frame["source_url"] = frame["previous_source_url"] = "https://example.test/synthetic"
    before = describe_pairs(frame, load_protocol())
    changed = frame.copy()
    changed.loc[changed.acceptance_date.str.startswith("2021"), "current_text"] = "futureonly " * 200
    after = describe_pairs(changed, load_protocol())
    columns = ["log_length_change", "jaccard_distance", "tfidf_cosine_distance"]
    np.testing.assert_allclose(before.loc[before.year < 2021, columns],
                               after.loc[after.year < 2021, columns], equal_nan=True)
    assert before.loc[before.year == 2010, "tfidf_cosine_distance"].isna().all()
    assert before.loc[before.year == 2011, "vocabulary_training_pairs"].eq(12).all()


def test_pilot_refuses_pending_evidence_and_holdout():
    frame = synthetic_dataset()
    frame = frame.loc[frame.acceptance_date.str[:4].astype(int).ge(2019)]
    with pytest.raises(ValueError, match="model-ready"):
        pilot_baseline(frame, load_protocol(), evidence={"model_ready": False})
    result, receipt = pilot_baseline(frame, load_protocol(), evidence={
        "model_ready": True, "data_kind": "SYNTHETIC_ENGINEERING_FIXTURE"})
    assert set(result.year) == {2020, 2021}
    assert receipt["predictive_performance_claim"] is False
    assert result.loc[result.year == 2020, "train_rows"].eq(12).all()
    bad = frame.copy()
    bad.loc[bad.index[0], "acceptance_date"] = "2022-02-01"
    with pytest.raises(ValueError, match="Final-period"):
        pilot_baseline(bad, load_protocol(), evidence={"model_ready": True})


def test_semantic_chunking_preserves_every_token_and_weight():
    ids = list(range(2037))
    chunks = token_chunks(ids)
    assert [token for chunk in chunks for token in chunk] == ids
    assert all(len(chunk) <= 254 for chunk in chunks)
    assert len(chunks[-1]) == 5
    vector = aggregate_chunks([[1, 0], [0, 1]], [3, 1])
    np.testing.assert_allclose(vector, np.array([3, 1]) / np.sqrt(10))
    assert cosine_distance(vector, vector) == pytest.approx(0, abs=1e-14)
    assert cosine_distance([1, 0], [-1, 0]) == 2
    with pytest.raises(ValueError, match="Zero"):
        aggregate_chunks([[0, 0]], [1])


def test_semantic_spec_is_pinned_and_cannot_be_claimed_primary():
    with open("configs/semantic_retrospective.json") as stream:
        spec = json.load(stream)
    validate_spec(spec)
    spec["primary_model_input"] = True
    with pytest.raises(ValueError, match="retrospective"):
        validate_spec(spec)
