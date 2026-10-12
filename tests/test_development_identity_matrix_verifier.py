"""Synthetic independent reconstruction and adversarial private-matrix tests."""

import json

import pandas as pd
import pytest

from disclosure_research.development_identity_matrix import run_development_identity_matrix
from disclosure_research.development_identity_matrix_verifier import independently_verify_event_matrix
from test_development_identity_matrix import prepared as matrix_fixture  # noqa: F401
from test_pilot_issuer_anchor import example as issuer_fixture  # noqa: F401


@pytest.fixture
def ready(matrix_fixture):  # noqa: F811
    x = matrix_fixture
    run_development_identity_matrix(
        x["market"], x["names"], x["inventory"], x["ccm"], x["ccm_summary"],
        x["sec_gzip"], x["sec_execution"], x["tenk"], x["anchor"], x["output"],
        config=x["config"], repo_root=x["repo"],
    )
    return x


def verify(x):
    return independently_verify_event_matrix(
        x["output"], x["market"] / "candidate_calculations.parquet", x["names"],
        x["ccm"], x["sec_gzip"], x["anchor"], x["repo"] / "reports" / "independent.json",
        config=x["config"], repo_root=x["repo"],
    )


def _tamper_private_rehash(x, update):
    file = x["output"] / "review_queue_private.jsonl"
    rows = [json.loads(line) for line in file.read_text().splitlines()]
    update(rows)
    file.chmod(0o600)
    file.write_text("".join(json.dumps(row) + "\n" for row in rows))
    receipt_file = x["output"] / "receipt.json"
    receipt_file.chmod(0o600)
    receipt = json.loads(receipt_file.read_text())
    import hashlib
    payload = file.read_bytes()
    receipt["files"]["review_queue_private.jsonl"] = {
        "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
    }
    receipt_file.write_text(json.dumps(receipt))


def test_independent_recomputes_complete_source_history_without_approvals(ready):
    result = verify(ready)
    assert result["independently_rebuilt_events"] == 135
    assert result["independently_rebuilt_session_checks"] == 10935
    assert result["independently_verified_issuers"] == 20
    assert result["independent_year_and_event_counts_match"]
    assert result["full_private_per_event_review_flag_comparison_passed"]
    assert result["original_names_rows_examined"] == 20
    assert not result["model_ready"]
    assert not result["final_period_opened"]
    assert not result["continuous_CIK_PERMNO_link_approved"]
    assert not result["historical_known_at_established"]
    assert result["source_approvals_created"] == 0
    public = (ready["repo"] / "reports" / "independent.json").read_text()
    assert "original_SEC_CIK" not in public
    assert "candidate_CRSP_PERMNO" not in public
    assert "observed_names_CUSIP8_raw" not in public


def test_original_source_hash_change_refused(ready):
    ready["names"].write_text(ready["names"].read_text() + "\n")
    with pytest.raises(ValueError, match="Names source fingerprint"):
        verify(ready)


def test_original_m5_market_source_change_refused(ready):
    file = ready["market"] / "candidate_calculations.parquet"
    file.write_bytes(file.read_bytes() + b"CHANGED")
    with pytest.raises(ValueError, match="M5 candidate table fingerprint"):
        verify(ready)


def test_unapproved_event_source_flag_cannot_be_silently_rewritten(ready):
    def mutate(rows):
        rows[0]["review_flags"].remove("HISTORICAL_CIK_TO_SECURITY_KNOWN_AT_UNKNOWN")
    _tamper_private_rehash(ready, mutate)
    with pytest.raises(ValueError, match="mandatory unresolved gates"):
        verify(ready)


def test_event_vendor_security_identifier_change_rejected(ready):
    def mutate(rows):
        rows[0]["candidate_CRSP_PERMNO"] = "99999999"
    _tamper_private_rehash(ready, mutate)
    with pytest.raises(ValueError, match="original M5 CIK/security/time"):
        verify(ready)


def test_event_review_flag_conflict_rejected_even_with_new_receipt(ready):
    def mutate(rows):
        row = next(x for x in rows if x["original_CCM_company_header_CIK"] != x["original_SEC_CIK"])
        row["review_flags"].remove("CURRENT_COMPANY_HEADER_CIK_CONFLICT")
    _tamper_private_rehash(ready, mutate)
    with pytest.raises(ValueError, match="review flag disagrees"):
        verify(ready)


def test_original_sec_gzip_changed_refused(ready):
    ready["sec_gzip"].write_bytes(ready["sec_gzip"].read_bytes() + b"junk")
    with pytest.raises(ValueError, match="SEC original-source gzip fingerprint"):
        verify(ready)


def test_output_is_immutable_by_path(ready):
    verify(ready)
    with pytest.raises(ValueError, match="new public report"):
        verify(ready)


def test_private_rehash_without_forged_source_proof_detected(ready):
    def mutate(rows):
        rows[0]["source_names_record_ordinals"] = [500]
    _tamper_private_rehash(ready, mutate)
    with pytest.raises(ValueError, match="original Names history differs"):
        verify(ready)


def test_year_counts_not_trusted_from_public_summary(ready):
    summary_file = ready["output"] / "public_summary.json"
    summary_file.chmod(0o600)
    summary = json.loads(summary_file.read_text())
    summary["year_counts"]["2015"]["events"] = 42
    summary_file.write_text(json.dumps(summary))
    receipt_file = ready["output"] / "receipt.json"
    receipt_file.chmod(0o600)
    receipt = json.loads(receipt_file.read_text())
    import hashlib
    receipt["files"]["public_summary.json"]["sha256"] = hashlib.sha256(
        summary_file.read_bytes()
    ).hexdigest()
    receipt["files"]["public_summary.json"]["bytes"] = summary_file.stat().st_size
    receipt_file.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="totals/years differ"):
        verify(ready)


def test_model_readiness_false_even_with_valid_original_market_target(ready):
    # Changed model targets do not enter identity reconstruction; the source
    # byte hash is still required, so even a numerically plausible modification
    # can't enter a new run against an unchanged pinned identity matrix.
    market = ready["market"] / "candidate_calculations.parquet"
    df = pd.read_parquet(market)
    assert df["model_ready"].eq(False).all()
    df["target"] = 0.001
    df.to_parquet(market, index=False)
    with pytest.raises(ValueError, match="M5 candidate table fingerprint"):
        verify(ready)



def test_edited_same_company_security_context_is_rejected_even_if_rehashed(ready):
    def mutate(rows):
        rows[0]["alternative_active_same_PERMCO_security_ids_raw"] = ["99999999"]
    _tamper_private_rehash(ready, mutate)
    with pytest.raises(ValueError, match="share-class context"):
        verify(ready)
