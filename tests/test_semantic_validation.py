"""Engineering guard tests; actual MiniLM execution is recorded separately."""

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from disclosure_research import semantic_validation as validation
from disclosure_research.protocol import canonical_hash, load_protocol
from disclosure_research.semantic import bert_chunk_inputs, token_chunks, validate_spec


@pytest.fixture
def text_audit(tmp_path):
    """Small fabricated audit used only to test the guard, never a real result."""
    accessions = [f"0000000001-{year % 100:02d}-000001" for year in [2018, 2019, 2020]]
    texts = ["Synthetic credit exposure.", "Synthetic credit and funding exposure.",
             "Synthetic supplier and funding exposure."]
    urls = [f"https://example.test/fixture/{accession}" for accession in accessions]
    pd.DataFrame({"accessionNumber": accessions}).to_parquet(tmp_path / "filings.parquet", index=False)
    pairs = pd.DataFrame([
        {"accession": accessions[i], "previous_accession": accessions[i - 1], "cik": "0000000001",
         "acceptance_date": f"{2018 + i}-02-05", "previous_text": texts[i - 1], "current_text": texts[i],
         "source_url": urls[i], "previous_source_url": urls[i - 1]} for i in [1, 2]])
    pairs.to_parquet(tmp_path / "pairs.parquet", index=False)
    evidence = pd.DataFrame([
        {"accession": accession, "cik": "0000000001", "risk_text_sha256": hashlib.sha256(texts[i].encode()).hexdigest(),
         "source_url": urls[i], "acceptance_timestamp": f"{2018 + i}-02-05T18:30:00Z",
         "blocking_issues": [], "cautions": [], "resolution_method": "numbered_item1a",
         "automated_evidence_ok": True, "human_review_complete": False, "assistant_review_complete": False,
         "verified_source": True, "verified_header": True, "verified_risk_source": True}
        for i, accession in enumerate(accessions)])
    evidence.to_parquet(tmp_path / "filing_evidence.parquet", index=False)
    audit = {"filings": 3, "issuers": 1, "annual_pairs": 2, "automated_evidence_ok": 3,
             "filings_with_blocking_issues": 0, "human_reviews_complete": 0, "assistant_reviews_complete": 0,
             "timestamp_disagreements": 0, "reference_resolutions": 0}
    for name, file in [("pair", "pairs.parquet"), ("source", "filings.parquet"), ("evidence", "filing_evidence.parquet")]:
        audit[f"{name}_table_sha256"] = validation._sha((tmp_path / file).read_bytes())
    (tmp_path / "audit_summary.json").write_text(json.dumps(audit))
    return tmp_path


def prepare(root):
    return validation.prepare_validation(root / "pairs.parquet", root / "filings.parquet", root,
        "configs/semantic_retrospective.json", root / "plan", load_protocol())


def rebind(root, key, filename):
    path = root / "audit_summary.json"
    audit = json.loads(path.read_text())
    audit[key] = validation._sha((root / filename).read_bytes())
    path.write_text(json.dumps(audit))


def test_native_bert_chunk_wrapping_preserves_exact_wordpiece_ids():
    ids = list(range(2037))
    wrapped = [bert_chunk_inputs(chunk, 101, 102) for chunk in token_chunks(ids)]
    assert [value for row in wrapped for value in row["input_ids"][1:-1]] == ids
    assert max(len(row["input_ids"]) for row in wrapped) == 256
    assert len(wrapped[-1]["input_ids"]) == 7
    for row in wrapped:
        assert row["input_ids"][0] == 101 and row["input_ids"][-1] == 102
        assert row["attention_mask"] == [1] * len(row["input_ids"])
        assert row["token_type_ids"] == [0] * len(row["input_ids"])


@pytest.mark.parametrize("field,value", [("pooling", "cls_only"), ("precision", "float16_cuda"),
    ("max_model_tokens", 512), ("checkpoint_historical_availability_claim", True),
    ("training_data_cutoff_verified", True), ("fine_tuning_cutoff_verified", True)])
def test_semantic_spec_cannot_silently_change_implemented_method(field, value):
    spec = json.loads(Path("configs/semantic_retrospective.json").read_text())
    spec[field] = value
    with pytest.raises(ValueError, match="changed|historical"):
        validate_spec(spec)


def test_plan_revalidates_bound_audit_and_preserves_pending_review(text_audit):
    plan = prepare(text_audit)
    loaded, frame, spec = validation.load_validation_plan(text_audit / "plan")
    assert loaded == plan and len(frame) == 2
    assert spec["chronology_scope"] == "retrospective_only"
    assert plan["source_audit"]["human_reviews_complete"] == 0
    assert plan["checks"] == validation.CHECKS
    assert plan["returns_read"] is plan["final_period_opened"] is plan["model_ready"] is False
    assert plan["empirical_gate_satisfied"] is False
    with pytest.raises(ValueError, match="preserve"):
        prepare(text_audit)


@pytest.mark.parametrize("file", ["source_pairs.parquet", "source_filings.parquet", "filing_evidence.parquet",
                                 "audit_summary.json", "semantic_spec.json", "protocol.json"])
def test_changed_plan_source_is_rejected_before_backend_load(text_audit, file):
    prepare(text_audit)
    path = text_audit / "plan" / file
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="source changed"):
        validation.run_validation(text_audit / "plan", text_audit / "results")
    assert not (text_audit / "results").exists()


def test_outcome_schema_is_rejected_without_deserializing_any_payload(text_audit, monkeypatch):
    path = text_audit / "pairs.parquet"
    frame = pd.read_parquet(path)
    frame["target"] = [1, 2]
    frame.to_parquet(path, index=False)
    rebind(text_audit, "pair_table_sha256", "pairs.parquet")

    def forbidden(*args, **kwargs):
        pytest.fail("Outcome-bearing source must be rejected from Parquet metadata alone")

    monkeypatch.setattr(pd, "read_parquet", forbidden)
    with pytest.raises(ValueError, match="outcome-bearing"):
        prepare(text_audit)


@pytest.mark.parametrize("hidden_in_previous", [False, True])
def test_final_period_text_is_rejected_before_loading_text(text_audit, monkeypatch, hidden_in_previous):
    if hidden_in_previous:
        path = text_audit / "filing_evidence.parquet"
        frame = pd.read_parquet(path)
        frame.loc[0, "acceptance_timestamp"] = "2022-02-05T18:30:00Z"
        frame.to_parquet(path, index=False)
        rebind(text_audit, "evidence_table_sha256", path.name)
    else:
        path = text_audit / "pairs.parquet"
        frame = pd.read_parquet(path)
        frame.loc[0, "acceptance_date"] = "2022-02-05"
        frame.to_parquet(path, index=False)
        rebind(text_audit, "pair_table_sha256", path.name)
    read = pd.read_parquet

    def date_columns_only(*args, **kwargs):
        assert kwargs["columns"] in (["acceptance_date"], ["acceptance_timestamp"])
        return read(*args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", date_columns_only)
    with pytest.raises(ValueError, match="Final-period"):
        prepare(text_audit)


def test_refreshing_outer_table_hash_cannot_rebind_changed_text(text_audit):
    path = text_audit / "pairs.parquet"
    frame = pd.read_parquet(path)
    frame.loc[0, "current_text"] = "Different invented text, still a unit-test fixture."
    frame.to_parquet(path, index=False)
    rebind(text_audit, "pair_table_sha256", path.name)
    with pytest.raises(ValueError, match="text or source differs"):
        prepare(text_audit)


def test_changed_encoder_code_invalidates_plan(text_audit, monkeypatch):
    prepare(text_audit)
    monkeypatch.setattr(validation, "_code_files", lambda: {"semantic.py": "different"})
    with pytest.raises(ValueError, match="implementation changed"):
        validation.run_validation(text_audit / "plan", text_audit / "results")


def test_relaxed_reproducibility_tolerance_is_not_accepted(text_audit):
    plan = prepare(text_audit)
    plan["checks"]["different_batch_max_abs_tolerance"] = 1
    plan["validation_id"] = canonical_hash({key: value for key, value in plan.items() if key != "validation_id"})
    (text_audit / "plan" / "validation_plan.json").write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="check definitions differ"):
        validation.load_validation_plan(text_audit / "plan")


@pytest.mark.parametrize("change", ["empty", "drop", "duplicate", "reorder"])
def test_rehashed_plan_cannot_omit_or_change_declared_recheck_sample(text_audit, change):
    plan = prepare(text_audit)
    selected = plan["recheck_observation_ids"]
    plan["recheck_observation_ids"] = {"empty": [], "drop": selected[:1],
        "duplicate": [selected[0], selected[0]], "reorder": list(reversed(selected))}[change]
    plan["validation_id"] = canonical_hash({key: value for key, value in plan.items() if key != "validation_id"})
    (text_audit / "plan" / "validation_plan.json").write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="exact declared selection"):
        validation.run_validation(text_audit / "plan", text_audit / "results")
    assert not (text_audit / "results").exists()


@pytest.mark.parametrize("key,value", [("tokens_encoded", 100), ("tokens_truncated", 1), ("chunks", 1)])
def test_missing_or_truncated_tokens_fail_coverage(key, value):
    vector = np.ones(384) / np.sqrt(384)
    receipt = {"tokens_encoded": 300, "tokens_truncated": 0, "content_tokens": 300, "chunks": 2}
    validation._coverage(vector, receipt, validation.CHECKS)
    changed = copy.deepcopy(receipt)
    changed[key] = value
    with pytest.raises(ValueError, match="every content token"):
        validation._coverage(vector, changed, validation.CHECKS)


@pytest.mark.parametrize("vector", [np.ones(384), np.full(384, np.nan), np.ones(383) / np.sqrt(383)])
def test_wrong_dimension_nonfinite_or_unnormalized_vectors_fail(vector):
    receipt = {"tokens_encoded": 300, "tokens_truncated": 0, "content_tokens": 300, "chunks": 2}
    with pytest.raises(ValueError, match="dimension, finiteness or norm"):
        validation._coverage(vector, receipt, validation.CHECKS)
