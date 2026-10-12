"""Synthetic independent source-context reconstruction and forged-result checks."""

import hashlib
import json

import pytest

from disclosure_research.sec_cover_class_triage import run_cover_class_triage
from disclosure_research.sec_cover_class_verifier import verify_original_cover_class
from test_sec_cover_class_triage import snapshot as source_snapshot  # noqa: F401


@pytest.fixture
def reviewed(source_snapshot):  # noqa: F811
    x = source_snapshot
    run_cover_class_triage(
        x["matrix"], x["gz"], x["sec_exec"], x["output"],
        config=x["config"], repo_root=x["root"],
    )
    x["verify_output"] = x["root"] / "reports" / "independent.json"
    return x


def verify(x):
    return verify_original_cover_class(
        x["output"], x["gz"], x["verify_output"],
        config=x["config"], repo_root=x["root"],
    )


def _change_and_rehash(x, filename, mutator):
    folder = x["output"]
    path = folder / filename
    original = path.read_text()
    modified = mutator(original)
    path.chmod(0o600)
    path.write_text(modified)
    receipt_path = folder / "receipt.json"
    receipt_path.chmod(0o600)
    receipt = json.loads(receipt_path.read_text())
    contents = path.read_bytes()
    receipt["files"][filename] = {
        "sha256": hashlib.sha256(contents).hexdigest(),
        "bytes": len(contents),
    }
    receipt_path.write_text(json.dumps(receipt))


def test_independent_original_source_rebuilds_each_context(reviewed):
    result = verify(reviewed)
    assert result["independently_checked_doubly_corroborated_filings"] == 3
    assert result["original_SEC_matching_symbol_contexts_reconstructed"] == 3
    assert result["standard_common_member_filings"] == 1
    assert result["full_original_source_facts_and_each_review_flag_verified"]
    assert result["exclusive_review_groups_and_overlap_counts_recomputed"]
    assert not result["stock_class_or_CIK_PERMNO_approved"]
    assert not result["model_ready"]
    assert not result["final_period_opened"]
    assert result["source_approvals_created"] == 0
    output = reviewed["verify_output"].read_text()
    assert "candidate_CRSP_PERMNO" not in output
    assert "original_issuer_CIK" not in output
    assert "contextref" not in output


def test_rehashed_fake_common_stock_member_class_refused(reviewed):
    def alter(raw):
        rows = [json.loads(x) for x in raw.splitlines()]
        actual = next(row for row in rows
                      if row["source_context_review_group"]
                      == "ISSUER_SPECIFIC_CLASS_CONTEXT_REQUIRES_INTERPRETATION")
        actual["matched_symbol_source_contexts"][0]["class_context_mode"] = "STANDARD_GAAP_COMMON_STOCK_MEMBER"
        return "".join(json.dumps(x) + "\n" for x in rows)
    _change_and_rehash(reviewed, "private_context_review.jsonl", alter)
    with pytest.raises(ValueError, match="stock-axis QName differs"):
        verify(reviewed)


def test_rehashed_false_original_title_is_rejected(reviewed):
    def alter(raw):
        rows = [json.loads(x) for x in raw.splitlines()]
        rows[0]["matched_symbol_source_contexts"][0]["same_context_registered_titles_raw"] = ["Common Stock forged"]
        return "".join(json.dumps(x) + "\n" for x in rows)
    _change_and_rehash(reviewed, "private_context_review.jsonl", alter)
    with pytest.raises(ValueError, match="title/exchange facts differ"):
        verify(reviewed)


def test_rehashed_hidden_structural_warning_is_detected(reviewed):
    def alter(raw):
        rows = [json.loads(x) for x in raw.splitlines()]
        rows[2]["matched_symbol_source_contexts"][0]["lexical_review_reasons"] = []
        return "".join(json.dumps(x) + "\n" for x in rows)
    _change_and_rehash(reviewed, "private_context_review.jsonl", alter)
    with pytest.raises(ValueError, match="structural review flags were altered"):
        verify(reviewed)


def test_original_sec_gzip_tamper_fails(reviewed):
    reviewed["gz"].write_bytes(reviewed["gz"].read_bytes() + b"mutation")
    with pytest.raises(ValueError, match="fingerprint differs"):
        verify(reviewed)


def test_rehashed_forged_public_metric_fails(reviewed):
    def alter(raw):
        data = json.loads(raw)
        data["counts"]["filings_with_standard_gaap_CommonStockMember"] = 99
        return json.dumps(data)
    _change_and_rehash(reviewed, "public_summary.json", alter)
    with pytest.raises(ValueError, match="counts fail reconciliation"):
        verify(reviewed)


def test_rehashed_forged_class_approval_fails(reviewed):
    def alter(raw):
        data = json.loads(raw)
        data["historical_security_class_approved"] = True
        return json.dumps(data)
    _change_and_rehash(reviewed, "public_summary.json", alter)
    with pytest.raises(ValueError, match="pending research state"):
        # The verifier must reject approval flags even if someone changes the
        # public report and its private receipt to matching SHA fingerprints.
        verify(reviewed)


def test_independent_receipt_output_not_overwritten(reviewed):
    verify(reviewed)
    with pytest.raises(ValueError, match="fresh aggregate"):
        verify(reviewed)
