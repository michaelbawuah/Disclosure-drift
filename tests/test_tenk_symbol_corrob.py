"""Invented 10-K cover symbols and invented 24-field CRSP Names fixtures only."""

import csv
import gzip
import hashlib
import json

import pandas as pd
import pytest

from disclosure_research.tenk_symbol_corrob import run_tenk_symbol_corrob
from test_pilot_issuer_anchor import example as issuer_fixture  # noqa: F401


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _fact(symbol, *, context="CommonStockMember", issues=None, hidden=False):
    return {
        "concept_qname_raw": "dei:TradingSymbol",
        "text_from_parsed_html": symbol,
        "contextref_raw": context,
        "lexical_issues": [] if issues is None else issues,
        "nil_attributes_raw": [],
        "inside_hidden_element": hidden,
        "hidden_by_inline_style_observed": hidden,
        "interpreted_xbrl_value": None,
        "security_link_created": False,
    }


@pytest.fixture
def inputs(issuer_fixture):  # noqa: F811
    x = issuer_fixture
    originals = json.loads(gzip.decompress(x["sec_gzip"].read_bytes()))
    original_events = originals["records"]
    for item in original_events:
        item["cover_evidence"] = {"facts": []}
    candidate = pd.read_parquet(x["market"] / "candidate_calculations.parquet")
    acc = [candidate.iloc[i].event_id for i in range(5)]
    original_by_acc = {r["accession"]: r for r in original_events}
    original_by_acc[acc[0]]["cover_evidence"]["facts"] = [_fact("Q00")]
    original_by_acc[acc[1]]["cover_evidence"]["facts"] = [
        _fact("Q01", context="ClassA"), _fact("Q01B", context="ClassB")]
    original_by_acc[acc[2]]["cover_evidence"]["facts"] = [_fact("Q02", issues=["unrecognized-format"])]
    original_by_acc[acc[3]]["cover_evidence"]["facts"] = [_fact("Q03", hidden=True)]
    original_by_acc[acc[4]]["cover_evidence"]["facts"] = [_fact("UNLISTED")]
    originals["xbrl_fact_values_interpreted"] = False
    originals["original_sec_bytes_reread"] = True
    originals["status"] = "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED"
    originals["source_approvals"] = 0
    originals["final_period_opened"] = False
    raw = json.dumps(originals).encode()
    zipped = gzip.compress(raw, mtime=0)
    x["sec_gzip"].write_bytes(zipped)
    execution = {
        "publication": {"sha256": _sha(zipped), "bytes": len(zipped),
                        "uncompressed_sha256": _sha(raw), "uncompressed_bytes": len(raw)},
    }
    x["sec_execution"].write_text(json.dumps(execution))
    receipt = {
        "status": "RAW_MANUAL_WRDS_METADATA_INVENTORY_NOT_SOURCE_APPROVED",
        "protocol_sha256": __import__("disclosure_research.protocol", fromlist=["canonical_hash"]).canonical_hash(x["config"]),
        "model_ready": False,
        "source_approvals": 0,
        "source": {
            "sha256": _sha(x["names"].read_bytes()),
            "bytes": x["names"].stat().st_size,
            "observed_header": next(csv.reader(x["names"].open())),
        },
        "all_rows": {"rows": 20},
    }
    inventory = x["names"].parent / "names_receipt.json"
    inventory.write_text(json.dumps(receipt))
    x["inventory"] = inventory
    return x


def run(x, label="one"):
    return run_tenk_symbol_corrob(
        x["market"], x["sec_gzip"], x["sec_execution"],
        x["names"], _sha(x["names"].read_bytes()), x["inventory"],
        x["repo"] / "outputs" / label,
        config=x["config"], repo_root=x["repo"],
    )


def refresh_sec(x, mutate):
    original = json.loads(gzip.decompress(x["sec_gzip"].read_bytes()))
    mutate(original)
    raw = json.dumps(original).encode()
    zipped = gzip.compress(raw, mtime=0)
    x["sec_gzip"].write_bytes(zipped)
    d = json.loads(x["sec_execution"].read_text())
    d["publication"] = {
        "sha256": _sha(zipped), "bytes": len(zipped),
        "uncompressed_sha256": _sha(raw), "uncompressed_bytes": len(raw),
    }
    x["sec_execution"].write_text(json.dumps(d))


def test_audit_keeps_multiclass_lexical_and_hidden_cases_pending(inputs):
    summary = run(inputs)
    assert summary["original_source_filing_pairs"] == 135
    assert summary["filings_with_original_10k_TradingSymbol_lexical_facts"] == 5
    assert summary["filings_with_at_least_one_dated_names_candidate_match"] == 4
    assert summary["filings_without_supported_TradingSymbol_facts"] == 130
    assert summary["filings_with_multiple_distinct_reported_trading_symbols"] == 1
    assert summary["filings_with_symbol_lexical_issues"] == 1
    assert summary["filings_with_hidden_symbol_facts"] == 1
    assert summary["filings_with_clean_single_unhidden_symbol_and_unique_names_candidate"] == 1
    assert summary["original_names_rows_reread"] == 20
    assert summary["source_approvals"] == 0
    assert summary["approved_security_links"] == 0
    assert not summary["model_ready"]
    assert not summary["actual_final_2022_2025_opened"]
    out = inputs["repo"] / "outputs" / "one"
    saved = json.loads((out / "receipt.json").read_text())
    assert saved["security_links_approved"] == 0
    assert out.stat().st_mode & 0o077 == 0
    for name, info in saved["files"].items():
        file = out / name
        assert _sha(file.read_bytes()) == info["sha256"]
        assert file.stat().st_mode & 0o222 == 0
    private = [json.loads(line) for line in (out/"private_filing_symbol_contexts.jsonl").read_text().splitlines()]
    assert len(private) == 5
    assert all(r["known_at"] is None and r["available_at"] is None
               and not r["candidate_security_identity_approved"] for r in private)
    assert "candidate_permno" not in (out / "public_summary.json").read_text()


def test_original_sec_report_changed_with_old_execution_hash_fails(inputs):
    inputs["sec_gzip"].write_bytes(inputs["sec_gzip"].read_bytes() + b"poison")
    with pytest.raises(ValueError, match="publication hash"):
        run(inputs)


def test_false_sec_xbrl_interpretation_is_rejected(inputs):
    refresh_sec(inputs, lambda d: d.update(xbrl_fact_values_interpreted=True))
    with pytest.raises(ValueError, match="Original SEC lexical evidence"):
        run(inputs)


def test_marked_interpreted_fact_refused_even_with_rehashed_source(inputs):
    def change(d):
        for record in d["records"]:
            if record["cover_evidence"]["facts"]:
                record["cover_evidence"]["facts"][0]["interpreted_xbrl_value"] = "Q00"
                break
    refresh_sec(inputs, change)
    with pytest.raises(ValueError, match="validated semantics"):
        run(inputs)


def test_names_original_sha_mismatch_rejected(inputs):
    inputs["names"].write_text(inputs["names"].read_text() + "\n")
    with pytest.raises(ValueError, match="Original Names CSV SHA"):
        run(inputs)


def test_names_source_receipt_mismatch_rejected(inputs):
    rec = json.loads(inputs["inventory"].read_text())
    rec["source_approvals"] = 1
    inputs["inventory"].write_text(json.dumps(rec))
    with pytest.raises(ValueError, match="Wrong original unapproved Names inventory"):
        run(inputs)


def test_holdout_filing_is_rejected(inputs):
    path = inputs["market"] / "candidate_calculations.parquet"
    frame = pd.read_parquet(path)
    frame.loc[0, "acceptance_timestamp"] = "2025-01-03T08:00:00-05:00"
    frame.to_parquet(path, index=False)
    receipt = json.loads((inputs["market"] / "audit_summary.json").read_text())
    receipt["files"]["candidate_calculations.parquet"] = _sha(path.read_bytes())
    (inputs["market"] / "audit_summary.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="Later-year"):
        run(inputs)


def test_no_overwrite(inputs):
    run(inputs)
    with pytest.raises(ValueError, match="new private"):
        run(inputs)


def test_duplicate_global_symbol_does_not_become_approved_match(inputs):
    with inputs["names"].open("r", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    rows[1]["ticker"] = "Q00"
    rows[1]["tradingsymbol"] = "Q00"
    with inputs["names"].open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    receipt = json.loads(inputs["inventory"].read_text())
    receipt["source"]["sha256"] = _sha(inputs["names"].read_bytes())
    receipt["source"]["bytes"] = inputs["names"].stat().st_size
    inputs["inventory"].write_text(json.dumps(receipt))
    summary = run(inputs)
    assert summary["filings_with_at_least_one_dated_names_candidate_match"] == 2
    assert summary["filings_with_clean_single_unhidden_symbol_and_unique_names_candidate"] == 0


def test_original_sec_10k_cik_mutation_detected(inputs):
    def change(d):
        for row in d["records"]:
            if row["cover_evidence"]["facts"]:
                row["manifest_cik_raw"] = "9999999999"
                break
    refresh_sec(inputs, change)
    with pytest.raises(ValueError, match="Original SEC 10-K CIK"):
        run(inputs)


def test_strict_filing_metadata_verification_excludes_missing_header(inputs):
    def change(d):
        for row in d["records"]:
            if row["cover_evidence"]["facts"]:
                row["header_identity"]["header_identity_consistent"] = False
                break
    refresh_sec(inputs, change)
    with pytest.raises(ValueError, match="Original SEC 10-K CIK"):
        run(inputs)
