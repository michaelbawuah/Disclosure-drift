"""Synthetic independent original-SEC annual registration pair verification."""

import hashlib
import json

import pytest

from disclosure_research.paired_stock_class_review import build_paired_stock_class_review
from disclosure_research.paired_stock_class_verifier import verify_paired_source
from test_paired_stock_class_review import upstream as initial_source  # noqa: F401
from test_sec_cover_class_triage import snapshot as base_source  # noqa: F401


@pytest.fixture
def evidence(initial_source):  # noqa: F811
    x = initial_source
    build_paired_stock_class_review(
        x["output"], x["gz"], x["sec_exec"], x["paired"],
        config=x["config"], repo_root=x["root"],
    )
    x["verification"] = x["root"] / "reports" / "independent-pair.json"
    return x


def verify(x):
    return verify_paired_source(
        x["paired"], x["output"], x["gz"], x["verification"],
        config=x["config"], repo_root=x["root"],
    )


def edit_private_and_rehash(x, filename, change):
    path = x["paired"] / filename
    current = path.read_text()
    changed = change(current)
    path.chmod(0o600)
    path.write_text(changed)
    receipt_path = x["paired"] / "receipt.json"
    receipt_path.chmod(0o600)
    receipt = json.loads(receipt_path.read_text())
    blob = path.read_bytes()
    receipt["files"][filename] = {
        "sha256": hashlib.sha256(blob).hexdigest(),
        "bytes": len(blob),
    }
    receipt_path.write_text(json.dumps(receipt))


def test_independent_source_recomputes_unapproved_single_synthetic_case(evidence):
    summary = verify(evidence)
    assert summary["independent_source_facts_checked"] == 1
    assert summary["independently_rebuilt_issuer_pairs"] == 1
    assert summary["original_SEC_source_fact_class_and_registered_title_recomputed"]
    assert summary["paired_year_symbol_title_exchange_stability_recomputed"]
    assert summary["historical_security_class_approved"] is False
    assert summary["historical_CIK_PERMNO_known_at_established"] is False
    assert summary["source_approvals_created"] == 0
    assert summary["model_ready"] is False
    assert summary["final_period_opened"] is False
    assert "candidate_PERMNO" not in evidence["verification"].read_text()


def test_forged_paired_common_stock_title_cannot_pass_when_private_hashes_updated(evidence):
    def edit(raw):
        group = [json.loads(s) for s in raw.splitlines()]
        group[0]["filings"][0]["registered_stock_title_raw"] = "FORGED CLASS A COMMON STOCK"
        return "".join(json.dumps(x) + "\n" for x in group)
    edit_private_and_rehash(evidence, "private_issuer_pairs.jsonl", edit)
    with pytest.raises(ValueError, match="registered title/exchange"):
        verify(evidence)


def test_forged_private_model_or_class_approval_rejected(evidence):
    def edit(raw):
        group = [json.loads(s) for s in raw.splitlines()]
        group[0]["filings"][0]["historical_security_class_approved"] = True
        return "".join(json.dumps(x) + "\n" for x in group)
    edit_private_and_rehash(evidence, "private_issuer_pairs.jsonl", edit)
    with pytest.raises(ValueError, match="fabricated approval"):
        verify(evidence)


def test_original_sec_source_hash_mutation_rejected(evidence):
    evidence["gz"].write_bytes(evidence["gz"].read_bytes() + b"poison")
    with pytest.raises(ValueError, match="source report fingerprint"):
        verify(evidence)


def test_forged_paired_year_stability_must_be_checked_against_actual_years(evidence):
    def edit(raw):
        group = [json.loads(s) for s in raw.splitlines()]
        group[0]["same_original_trading_symbol"] = True
        group[0]["same_normalized_registered_title"] = True
        group[0]["same_normalized_exchange_name"] = True
        group[0]["pair_source_stability"] = "TWO_CONSECUTIVE_ORIGINAL_10K_REPORTS_LEXICALLY_STABLE"
        return "".join(json.dumps(x) + "\n" for x in group)
    edit_private_and_rehash(evidence, "private_issuer_pairs.jsonl", edit)
    with pytest.raises(ValueError, match="paired-year evidence differs"):
        verify(evidence)


def test_forged_public_review_count_rejected_even_when_receipt_rehashed(evidence):
    def edit(raw):
        public = json.loads(raw)
        public["counts"]["filings_with_standard_member_without_structural_warning"] = 99
        return json.dumps(public)
    edit_private_and_rehash(evidence, "public_summary.json", edit)
    with pytest.raises(ValueError, match="totals fail reconciliation"):
        verify(evidence)


def test_existing_independent_report_not_overwritten(evidence):
    verify(evidence)
    with pytest.raises(ValueError, match="new path"):
        verify(evidence)


def test_html_script_injection_rejected_even_with_matching_sha(evidence):
    def edit(raw):
        return raw + "<script>alert(1)</script>"
    edit_private_and_rehash(evidence, "private_review.html", edit)
    with pytest.raises(ValueError, match="unsafe"):
        verify(evidence)


def test_mutating_earlier_41_case_source_row_rejected(evidence):
    earlier = evidence["output"] / "private_context_review.jsonl"
    earlier.chmod(0o600)
    earlier.write_text(earlier.read_text() + "\n")
    with pytest.raises(ValueError, match="earlier 41-case|Earlier 41-case"):
        verify(evidence)


def test_fake_source_approval_is_rejected_even_with_rehashed_report(evidence):
    def edit(raw):
        public = json.loads(raw)
        public["historical_CIK_to_security_link_approved"] = True
        return json.dumps(public)
    edit_private_and_rehash(evidence, "public_summary.json", edit)
    with pytest.raises(ValueError, match="research source/identity restrictions|restrictions"):
        verify(evidence)
