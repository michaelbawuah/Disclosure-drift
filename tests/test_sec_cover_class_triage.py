"""Only invented original-SEC lexical contexts and synthetic 135-record matrix receipts."""

import gzip
import hashlib
import json

import pytest

from disclosure_research.protocol import canonical_hash, load_protocol
from disclosure_research.sec_cover_class_triage import (
    _render_private, _source_contexts, _triage_group,
    run_cover_class_triage,
)


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _context(cik, suffix, ordinal, *, member=None, end="2019-12-31"):
    dims = []
    if member:
        namespace = "http://fasb.org/us-gaap/2019-01-31" if member.startswith("us-gaap:") else "https://issuer.example/schema"
        dims = [{
            "dimension_qname_raw": "us-gaap:StatementClassOfStockAxis",
            "dimension_namespace": {
                "namespace_uri": "http://fasb.org/us-gaap/2019-01-31",
                "status": "DECLARATION_FOUND_IN_PARSED_HTML",
            },
            "member_namespace": {
                "qname_raw": member,
                "namespace_uri": namespace,
                "status": "DECLARATION_FOUND_IN_PARSED_HTML",
            },
        }]
    return {
        "context_id_raw": suffix, "context_element_ordinal": ordinal,
        "entity_identifiers": [{
            "scheme_raw": "http://www.sec.gov/CIK",
            "text_from_parsed_html": cik,
        }],
        "period_components": [{"kind": "enddate", "text_from_parsed_html": end}],
        "dimensions": dims,
    }


def _fact(concept, symbol, context, ordinal, *, issues=None, hidden=False):
    return {
        "concept_qname_raw": concept,
        "concept_namespace": {
            "qname_raw": concept,
            "namespace_uri": "http://xbrl.sec.gov/dei/2019-01-31",
            "status": "DECLARATION_FOUND_IN_PARSED_HTML",
        },
        "text_from_parsed_html": symbol,
        "contextref_raw": context,
        "context_element_ordinals": [ordinal],
        "lexical_issues": issues or [],
        "nil_attributes_raw": [],
        "inside_hidden_element": hidden,
        "hidden_by_inline_style_observed": hidden,
    }


def _source(cik, symbol, context, ordinal, *, member=None, title="Common Stock",
            include_exchange=True, hidden=False, end="2019-12-31"):
    fs = [
        _fact("dei:TradingSymbol", symbol, context, ordinal, hidden=hidden),
        _fact("dei:Security12bTitle", title, context, ordinal),
    ]
    if include_exchange:
        fs.append(_fact(
            "dei:SecurityExchangeName", "New York Stock Exchange", context, ordinal,
            issues=["format_transformation_not_interpreted"],
        ))
    return {
        "cover_evidence": {
            "contexts": [_context(cik, context, ordinal, member=member, end=end)],
            "facts": fs,
        },
    }


@pytest.fixture
def snapshot(tmp_path):
    root = tmp_path / "research"
    p = root / "outputs" / "old-matrix"
    s = root / "reports"
    p.mkdir(parents=True)
    s.mkdir()
    config = load_protocol()
    records, events = [], []
    for i in range(135):
        cik = f"{1000000000+i:010d}"
        acc = f"{cik}-20-{i+1:06d}"
        symbol = f"T{i:03d}"
        base = {
            "observation_id": acc, "original_SEC_CIK": cik, "year": 2020,
            "candidate_CRSP_PERMNO": str(5000+i),
            "acceptance_timestamp": "2020-03-01T09:00:00-05:00",
            "observed_names_trading_symbols_raw": [symbol],
            "2019q4_issuer_anchor_reported_before_10k": i < 3,
            "original_10k_symbol_fact_count": 1 if i < 3 else 0,
            "historical_CIK_to_PERMNO_approved": False,
            "historical_known_at": None,
            "market_available_at": None,
            "model_ready": False,
            "source_release_verified": False,
        }
        events.append(base)
        kinds = [
            "us-gaap:CommonStockMember",
            "issuer:ClassACommonStockMember",
            None,
        ]
        original = (_source(
            cik, symbol, f"ctx{i}", i+2, member=kinds[i],
            include_exchange=(i != 2), title=("Capital stock" if i == 2 else "Common Stock"),
        ) if i < 3 else {"cover_evidence": {"contexts": [], "facts": []}})
        original.update({
            "accession": acc, "manifest_cik_raw": cik,
            "recorded_acceptance_timestamp": base["acceptance_timestamp"],
            "header_identity": {"header_identity_consistent": True},
            "available_at": None, "known_at": None, "security_link_created": False,
        })
        records.append(original)
    for i in range(80):
        records.append({"accession": f"9999999999-14-{i+1:06d}"})
    report = {
        "status": "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED",
        "protocol_sha256": canonical_hash(config),
        "original_sec_bytes_reread": True,
        "xbrl_fact_values_interpreted": False,
        "source_approvals": 0, "final_period_opened": False,
        "records": records,
    }
    raw_sec = json.dumps(report).encode()
    gz = gzip.compress(raw_sec, mtime=0)
    sec_file = s / "source.json.gz"
    sec_file.write_bytes(gz)
    sec_exec = s / "source_execution.json"
    sec_exec.write_text(json.dumps({
        "publication": {
            "sha256": _hash(gz), "bytes": len(gz),
            "uncompressed_sha256": _hash(raw_sec), "uncompressed_bytes": len(raw_sec),
        }
    }))
    saved = "".join(json.dumps(x)+"\n" for x in events).encode()
    summary = {
        "status": "DEVELOPMENT_EVENT_IDENTITY_MATRIX_DESCRIPTORS_NOT_APPROVED",
        "provenance": {
            "sec_identity_gzip": _hash(gz),
            "sec_identity_execution": _hash(sec_exec.read_bytes()),
            "sec_identity_original_json": _hash(raw_sec),
        },
        "model_ready": False, "final_period_opened": False,
        "counts": {
            "events": 135,
            "events_with_both_prior_Q4_filing_date_anchor_and_10K_cover_symbol": 3,
        },
    }
    public_bytes = (json.dumps(summary)+"\n").encode()
    (p / "review_queue_private.jsonl").write_bytes(saved)
    (p / "public_summary.json").write_bytes(public_bytes)
    (p / "receipt.json").write_text(json.dumps({
        "status": summary["status"],
        "source_bindings": summary["provenance"],
        "model_ready": False, "final_period_opened": False,
        "source_approvals": 0, "historical_links_approved": 0,
        "files": {
            "public_summary.json": {"sha256": _hash(public_bytes), "bytes": len(public_bytes)},
            "review_queue_private.jsonl": {"sha256": _hash(saved), "bytes": len(saved)},
        },
    }))
    return {
        "root": root, "matrix": p, "gz": sec_file,
        "sec_exec": sec_exec, "output": root / "outputs" / "result",
        "config": config,
    }


def run(x):
    return run_cover_class_triage(
        x["matrix"], x["gz"], x["sec_exec"], x["output"],
        config=x["config"], repo_root=x["root"],
    )


def _modify_gzip(x, callback):
    report = json.loads(gzip.decompress(x["gz"].read_bytes()))
    callback(report)
    plain = json.dumps(report).encode()
    zipped = gzip.compress(plain, mtime=0)
    x["gz"].write_bytes(zipped)
    x["sec_exec"].write_text(json.dumps({
        "publication": {
            "sha256": _hash(zipped), "bytes": len(zipped),
            "uncompressed_sha256": _hash(plain), "uncompressed_bytes": len(plain),
        }
    }))
    meta_file = x["matrix"] / "public_summary.json"
    meta = json.loads(meta_file.read_text())
    meta["provenance"]["sec_identity_gzip"] = _hash(zipped)
    meta["provenance"]["sec_identity_execution"] = _hash(x["sec_exec"].read_bytes())
    meta["provenance"]["sec_identity_original_json"] = _hash(plain)
    bytes_meta = (json.dumps(meta)+"\n").encode()
    meta_file.write_bytes(bytes_meta)
    receipt_file = x["matrix"] / "receipt.json"
    receipt = json.loads(receipt_file.read_text())
    receipt["source_bindings"] = meta["provenance"]
    receipt["files"]["public_summary.json"] = {
        "sha256": _hash(bytes_meta), "bytes": len(bytes_meta),
    }
    receipt_file.write_text(json.dumps(receipt))


def test_context_class_triad_and_closed_gates(snapshot):
    out = run(snapshot)
    counts = out["counts"]
    assert counts["reviewed_doubly_corroborated_filings"] == 3
    assert counts["matching_original_SEC_10K_trading_symbol_facts"] == 3
    assert counts["exclusive_group:STANDARD_COMMON_LEXICAL_CONTEXT_PRESENT"] == 1
    assert counts["exclusive_group:ISSUER_SPECIFIC_CLASS_CONTEXT_REQUIRES_INTERPRETATION"] == 1
    assert counts["exclusive_group:NO_STANDARD_CLASS_AXIS_REQUIRES_INDEPENDENT_CLASS_EVIDENCE"] == 1
    assert counts["filings_with_matching_same_context_Common_Stock_title_literal"] == 2
    assert counts["filings_with_matched_symbol_title_and_exchange_in_one_context"] == 2
    assert counts["filings_with_uninterpreted_associated_title_exchange_format"] == 2
    assert counts["filings_standard_common_member_without_fact_lexical_warnings"] == 1
    assert counts["filings_with_any_structural_or_lexical_context_warning"] == 1
    assert out["human_reviews_created"] == 0
    assert out["source_approvals_created"] == 0
    assert not out["historical_security_class_approved"]
    assert not out["historical_CIK_to_PERMNO_known_at_established"]
    assert not out["final_period_opened"]
    folder = snapshot["output"]
    receipt = json.loads((folder / "receipt.json").read_text())
    assert folder.stat().st_mode & 0o077 == 0
    for filename, evidence in receipt["files"].items():
        path = folder / filename
        assert _hash(path.read_bytes()) == evidence["sha256"]
        assert evidence["bytes"] == path.stat().st_size
        assert path.stat().st_mode & 0o222 == 0
    private = [json.loads(line) for line in (
        folder / "private_context_review.jsonl").read_text().splitlines()]
    assert len(private) == 3
    assert all(row["historical_known_at"] is None and row["source_publication_verified"] is False
               and row["historical_security_class_approved"] is False for row in private)
    assert "<script" not in (folder / "private_context_review.html").read_text().lower()


def test_existing_output_not_overwritten(snapshot):
    run(snapshot)
    with pytest.raises(ValueError, match="unused private"):
        run(snapshot)


def test_matrix_source_digest_mismatch_refused(snapshot):
    (snapshot["matrix"] / "review_queue_private.jsonl").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="Matrix source receipts"):
        run(snapshot)


def test_original_sec_gzip_digest_mismatch_refused(snapshot):
    snapshot["gz"].write_bytes(snapshot["gz"].read_bytes() + b"junk")
    with pytest.raises(ValueError, match="original SEC gzip/execution"):
        run(snapshot)


def test_original_sec_semantic_approval_not_fabricated(snapshot):
    def mutate(obj):
        obj["xbrl_fact_values_interpreted"] = True
    _modify_gzip(snapshot, mutate)
    with pytest.raises(ValueError, match="unverified XBRL"):
        run(snapshot)


def test_context_ordinal_mismatch_remains_visible(snapshot):
    def mutate(obj):
        obj["records"][0]["cover_evidence"]["facts"][0]["context_element_ordinals"] = [777]
    _modify_gzip(snapshot, mutate)
    result = run(snapshot)
    assert result["counts"]["filings_with_any_structural_or_lexical_context_warning"] == 2
    rows = [json.loads(line) for line in (
        snapshot["output"] / "private_context_review.jsonl").read_text().splitlines()]
    flags = {f for row in rows for case in row["matched_symbol_source_contexts"]
             for f in case["lexical_review_reasons"]}
    assert "CONTEXT_ORDINAL_DISAGREEMENT" in flags
    assert result["source_approvals_created"] == 0


def test_forged_sec_entity_CIK_disagreement_is_not_approved(snapshot):
    def mutate(obj):
        obj["records"][0]["cover_evidence"]["contexts"][0]["entity_identifiers"][0][
            "text_from_parsed_html"
        ] = "0000000009"
    _modify_gzip(snapshot, mutate)
    result = run(snapshot)
    assert result["counts"]["filings_with_any_structural_or_lexical_context_warning"] == 2
    assert result["historical_security_class_approved"] is False


def test_context_period_later_than_original_filing_is_flagged(snapshot):
    def mutate(obj):
        obj["records"][0]["cover_evidence"]["contexts"][0]["period_components"][0][
            "text_from_parsed_html"
        ] = "2025-12-31"
    _modify_gzip(snapshot, mutate)
    run(snapshot)
    rows = [json.loads(line) for line in (
        snapshot["output"] / "private_context_review.jsonl").read_text().splitlines()]
    assert any("CONTEXT_PERIOD_END_UNSUPPORTED" in f["lexical_review_reasons"]
               for row in rows for f in row["matched_symbol_source_contexts"])


def test_missing_same_context_title_not_imputed(snapshot):
    def mutate(obj):
        obj["records"][0]["cover_evidence"]["facts"] = [
            f for f in obj["records"][0]["cover_evidence"]["facts"]
            if f["concept_qname_raw"] != "dei:Security12bTitle"
        ]
    _modify_gzip(snapshot, mutate)
    result = run(snapshot)
    assert result["counts"]["filings_with_matching_same_context_Common_Stock_title_literal"] == 1
    assert result["source_approvals_created"] == 0


def test_issuer_specific_member_not_mistaken_for_standard_common_stock():
    doc = _source("0000000009", "XX", "ctx", 30, member="issuer:CommonStockMember")
    found = _source_contexts(doc, {"XX"}, "0000000009", "2020-03-01")
    assert len(found) == 1
    assert found[0]["class_context_mode"] == "ISSUER_SPECIFIC_OR_OTHER_CLASS_MEMBER"
    assert _triage_group(found) == "ISSUER_SPECIFIC_CLASS_CONTEXT_REQUIRES_INTERPRETATION"


def test_private_html_escapes_html_and_filters_external_urls():
    rows = [{
        "observation_id": "test", "acceptance_date": "2020-01-01",
        "original_issuer_CIK": "0000000012", "candidate_CRSP_PERMNO": "2",
        "source_context_review_group": "STANDARD_COMMON_LEXICAL_CONTEXT_PRESENT",
        "matched_symbol_source_contexts": [{
            "trading_symbol": "<script>alert(1)</script>",
            "class_context_mode": "STANDARD_GAAP_COMMON_STOCK_MEMBER",
            "source_contextref": "<img src=x onerror=alert(1)>",
            "class_members_raw": [{"member_qname": "us-gaap:CommonStockMember"}],
            "same_context_registered_titles_raw": ["Common stock"],
            "same_context_exchange_names_raw": ["NYSE"],
            "lexical_review_reasons": [],
            "associated_fact_transformation_caveats": [],
        }],
    }]
    body = _render_private(rows, {"test": {
        "primary_source": {"url": "https://www.sec.gov/Archives/edgar/data/1/file.htm"},
        "header_source": {"url": "https://evil.example.com/attack"},
    }})
    assert "<script" not in body.lower()
    assert "<img" not in body.lower()
    assert "&lt;script&gt;" in body
    assert "evil.example" not in body
    assert "sec.gov/Archives/edgar/data" in body


def test_future_period_holdout_source_refused(snapshot):
    def mutate(obj):
        obj["records"][0]["recorded_acceptance_timestamp"] = "2025-03-01T09:00:00-05:00"
    _modify_gzip(snapshot, mutate)
    with pytest.raises(ValueError, match="issuer/clock"):
        run(snapshot)

def test_older_source_row_claiming_known_at_is_rejected_even_when_receipt_rehashed(snapshot):
    path = snapshot["matrix"] / "review_queue_private.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    rows[0]["historical_known_at"] = "2019-01-01"
    modified = "".join(json.dumps(x) + chr(10) for x in rows).encode()
    path.write_bytes(modified)
    receipt_path = snapshot["matrix"] / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["files"]["review_queue_private.jsonl"] = {
        "sha256": _hash(modified), "bytes": len(modified)
    }
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="event-level approval gates were changed"):
        run(snapshot)


def test_malformed_calendar_date_in_context_must_be_flagged(snapshot):
    def mutate(obj):
        obj["records"][0]["cover_evidence"]["contexts"][0]["period_components"][0][
            "text_from_parsed_html"
        ] = "2018-99-99"
    _modify_gzip(snapshot, mutate)
    run(snapshot)
    rows = [json.loads(x) for x in (
        snapshot["output"] / "private_context_review.jsonl"
    ).read_text().splitlines()]
    assert any(
        "CONTEXT_PERIOD_END_UNSUPPORTED" in f["lexical_review_reasons"]
        for row in rows for f in row["matched_symbol_source_contexts"]
    )
