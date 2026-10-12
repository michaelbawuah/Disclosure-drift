"""Synthetic-only stock-class paired-year evidence and source-mutation tests."""

import hashlib
import json

import pytest

from disclosure_research.paired_stock_class_review import (
    _normalized_literal,
    _paired_lexical_stability,
    _render_review,
    _secure_sec_url,
    _title_kind,
    build_paired_stock_class_review,
)
from disclosure_research.sec_cover_class_triage import run_cover_class_triage
from test_sec_cover_class_triage import snapshot as base_source  # noqa: F401


def _sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def upstream(base_source):  # noqa: F811
    x = base_source
    run_cover_class_triage(
        x["matrix"], x["gz"], x["sec_exec"], x["output"],
        config=x["config"], repo_root=x["root"],
    )
    x["paired"] = x["root"] / "outputs" / "registered-stock-pairs"
    return x


def run(x):
    return build_paired_stock_class_review(
        x["output"], x["gz"], x["sec_exec"], x["paired"],
        config=x["config"], repo_root=x["root"],
    )


def change_class_private(x, modifier):
    path = x["output"] / "private_context_review.jsonl"
    entries = [json.loads(x) for x in path.read_text().splitlines()]
    modifier(entries)
    blob = "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries).encode()
    path.chmod(0o600)
    path.write_bytes(blob)
    receipt_path = x["output"] / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["files"]["private_context_review.jsonl"] = {
        "sha256": _sha(blob), "bytes": len(blob),
    }
    receipt_path.chmod(0o600)
    receipt_path.write_text(json.dumps(receipt))


def _rows():
    return [
        {
            "year": 2020, "stock_symbol_raw": "SYN",
            "registered_stock_title_raw": "Common Stock, $0.01 par",
            "registered_exchange_raw": "New York Stock Exchange",
        },
        {
            "year": 2021, "stock_symbol_raw": "SYN",
            "registered_stock_title_raw": "COMMON   STOCK, $0.01 par",
            "registered_exchange_raw": "new york stock  exchange",
        },
    ]


def test_source_bound_one_case_is_pending_not_invented_consecutive_pair(upstream):
    report = run(upstream)
    assert report["issuer_pairs_in_first_review"] == 1
    assert report["counts"]["filings_with_standard_member_without_structural_warning"] == 1
    assert report["counts"]["registered_title_literal_explicit_Common_Stock"] == 1
    assert report["counts"]["same_context_exchange_present"] == 1
    assert report["counts"]["insufficient_or_nonconsecutive_filing_pairs"] == 1
    assert report["source_approvals_created"] == 0
    assert report["historical_known_at_established"] is False
    assert report["iXBRL_semantics_validated"] is False
    assert report["source_10k_HTML_bytes_directly_reread_on_this_Mac"] is False
    assert report["model_ready"] is False and report["final_period_opened"] is False
    folder = upstream["paired"]
    receipt = json.loads((folder / "receipt.json").read_text())
    assert folder.stat().st_mode & 0o077 == 0
    for filename, meta in receipt["files"].items():
        src = folder / filename
        assert meta["sha256"] == _sha(src.read_bytes())
        assert meta["bytes"] == src.stat().st_size
        assert src.stat().st_mode & 0o222 == 0
    private = [json.loads(line) for line in (folder / "private_issuer_pairs.jsonl").read_text().splitlines()]
    assert len(private) == 1 and len(private[0]["filings"]) == 1
    assert private[0]["human_approved_historical_class"] is False
    assert private[0]["historical_security_identity_known_at"] is None
    assert not private[0]["filings"][0]["original_10k_HTML_bytes_reopened_here"]
    assert "candidate_PERMNO" not in (folder / "public_summary.json").read_text()


def test_pairing_exact_lexical_source_with_whitespace_stability():
    result = _paired_lexical_stability(_rows())
    assert result["consecutive"]
    assert result["symbol_same"] and result["title_same"] and result["exchange_same"]
    assert result["pair_state"] == "TWO_CONSECUTIVE_ORIGINAL_10K_REPORTS_LEXICALLY_STABLE"
    assert _normalized_literal("  New  York Stock Exchange ") == "new york stock exchange"


def test_pairing_never_forces_nonconsecutive_or_single_source_to_stable():
    assert not _paired_lexical_stability(_rows()[:1])["consecutive"]
    pair = _rows()
    pair[1]["year"] = 2025
    assert not _paired_lexical_stability(pair)["consecutive"]


def test_pairing_tracks_symbol_title_and_exchange_changes_separately():
    for field in ("stock_symbol_raw", "registered_stock_title_raw", "registered_exchange_raw"):
        pair = _rows()
        pair[1][field] = "CHANGED"
        result = _paired_lexical_stability(pair)
        assert result["consecutive"]
        assert result["pair_state"] == "TWO_CONSECUTIVE_REPORTS_LEXICAL_CHANGE_REVIEW"
        flags = [result["symbol_same"], result["title_same"], result["exchange_same"]]
        assert flags.count(False) == 1


def test_title_lexical_category_does_not_infer_capital_equals_common():
    assert _title_kind("COMMON STOCK, $0.01") == "EXPLICIT_COMMON_STOCK_TITLE"
    assert _title_kind("Capital stock, $0.20 par") == "CAPITAL_STOCK_TITLE_CLASS_REVIEW"
    assert _title_kind("Series A Debentures") == "OTHER_REGISTERED_TITLE_CLASS_REVIEW"
    assert _title_kind("") == "NO_REGISTERED_TITLE"


def test_original_sec_source_change_is_rejected(upstream):
    upstream["gz"].write_bytes(upstream["gz"].read_bytes() + b"mutation")
    with pytest.raises(ValueError, match="Original 10-K source report"):
        run(upstream)


def test_forged_source_title_in_rehashed_class_audit_rejected(upstream):
    def forge(rows):
        r = rows[0]
        r["matched_symbol_source_contexts"][0]["same_context_registered_titles_raw"] = [
            "Forged common stock"
        ]
    change_class_private(upstream, forge)
    with pytest.raises(ValueError, match="Prior lexical context differs"):
        run(upstream)


def test_previous_class_approval_forged_and_rehashed_fails(upstream):
    def forge(rows):
        rows[0]["historical_security_class_approved"] = True
    change_class_private(upstream, forge)
    with pytest.raises(ValueError, match="upstream SEC stock-class candidate"):
        run(upstream)


def test_mismatched_sec_original_filer_acceptance_rejected(upstream):
    def forge(rows):
        rows[0]["acceptance_date"] = "2025-03-03"
    change_class_private(upstream, forge)
    with pytest.raises(ValueError, match="Unmatched original 10-K filer/date"):
        run(upstream)


def test_no_existing_private_dir_is_overwritten(upstream):
    run(upstream)
    with pytest.raises(ValueError, match="unused private"):
        run(upstream)


def test_secure_original_filing_url_and_no_untrusted_html():
    assert _secure_sec_url({"url": "https://www.sec.gov/Archives/edgar/data/1/file.htm"})
    for value in (
        "http://www.sec.gov/Archives/edgar/data/1/file.htm",
        "https://evil.example/Archives/edgar/data/1/file.htm",
        "https://www.sec.gov.evil.example/Archives/edgar/data/1/file.htm",
        "https://www.sec.gov/Archives/edgar/data/1/file.htm#bad",
        "javascript:alert(1)",
    ):
        assert not _secure_sec_url({"url": value})


def test_private_review_escapes_evil_original_stock_titles():
    row = {
        "issuer_CIK": "0000000001", "candidate_PERMNO": "3",
        "filing_years": [2020], "pair_source_stability": "PENDING",
        "pair_review_flags": ["<svg onload=alert(1)>"],
        "filings": [{
            "accession": "test", "acceptance_date": "2020-02-01",
            "title_kind": "OTHER_REGISTERED_TITLE_CLASS_REVIEW",
            "stock_symbol_raw": "<img src=x onerror=alert(1)>",
            "registered_stock_title_raw": "<script>alert(1)</script>",
            "registered_exchange_raw": "NYSE", "source_contextref": "test-context",
            "source_class_member_qname": "us-gaap:CommonStockMember",
            "review_flags": ["pending"],
            "original_sec_primary_url": "", "original_sec_header_url": "",
        }],
    }
    html = _render_review([row])
    assert "<script" not in html.lower()
    assert "<svg" not in html.lower()
    assert "<img " not in html.lower()
    assert "&lt;script&gt;" in html
    assert "&lt;svg" in html
    assert "read-only" in html.lower()
