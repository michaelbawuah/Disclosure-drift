"""Invented-only SEC inline-HTML DOM tests and end-to-end mocked originals."""

import csv
import gzip
import hashlib
import json

import pytest

import disclosure_research.sec_original_revisit as fetcher
from disclosure_research.sec_identity_evidence import cover_evidence
from disclosure_research.sec_original_dom_crosscheck import (
    _source_dom_check, check_current_sec_dom16,
)
from disclosure_research.sec_original_revisit_verifier import reparse_16_sec_originals
from test_sec_original_revisit import sources  # noqa: F401


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _html(cik="1000000000", symbol="SYN", title="Common Stock",
          exchange="NYSE", member="us-gaap:CommonStockMember",
          period="2019-12-31", repeated=False):
    sym = (
        '<ix:nonNumeric name="dei:TradingSymbol" contextRef="StockClass">'
        + symbol + '</ix:nonNumeric>'
    )
    return (f'''
<html xmlns:dei="http://xbrl.sec.gov/dei/2019-01-31"
      xmlns:us-gaap="http://fasb.org/us-gaap/2019-01-31"
      xmlns:xbrli="http://www.xbrl.org/2003/instance">
<body>
<xbrli:context id="StockClass">
  <xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">{cik}</xbrli:identifier>
  <xbrli:segment>
    <xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">{member}</xbrldi:explicitMember>
  </xbrli:segment></xbrli:entity>
  <xbrli:period><xbrli:endDate>{period}</xbrli:endDate></xbrli:period>
</xbrli:context>
{sym}
{sym if repeated else ''}
<ix:nonNumeric name="dei:Security12bTitle" contextRef="StockClass">{title}</ix:nonNumeric>
<ix:nonNumeric name="dei:SecurityExchangeName" contextRef="StockClass">{exchange}</ix:nonNumeric>
</body></html>
''').encode()


def _case(symbol="SYN", title="Common Stock", exchange="NYSE"):
    return {
        "stock_symbol_raw": symbol, "source_contextref": "StockClass",
        "registered_stock_title_raw": title, "registered_exchange_raw": exchange,
        "source_class_member_qname": "us-gaap:CommonStockMember",
        "historical_security_class_approved": False,
        "historical_security_link_known_at": None,
        "original_10k_HTML_bytes_reopened_here": False,
    }


def test_direct_dom_facts_member_original_issuer_title_exchange():
    result = _source_dom_check(_html(), _case(), "1000000000", "2020-02-01")
    assert result["source_member_present"]
    assert result["original_context_identifier_equal"]
    assert result["original_symbol_fact_equal"]
    assert result["original_registered_title_equal"]
    assert result["original_registered_exchange_equal"]
    assert result["original_source_facts_semantically_validated"] is False


@pytest.mark.parametrize("mutation,reason", [
    ({"cik": "9999999999"}, "context issuer CIK differs"),
    ({"symbol": "OTHER"}, "one matching original stock-class symbol fact"),
    ({"title": "Security note"}, "title/exchange differs"),
    ({"exchange": "OTHER EXCHANGE"}, "title/exchange differs"),
    ({"member": "issuer:CommonStockMember"}, "no unambiguous common-stock member"),
    ({"period": "2025-12-31"}, "future filing period"),
    ({"repeated": True}, "one matching original stock-class symbol fact"),
])
def test_original_current_dom_forgery_or_ambiguity_rejected(mutation, reason):
    with pytest.raises(ValueError, match=reason):
        _source_dom_check(_html(**mutation), _case(), "1000000000", "2020-02-01")


def test_false_source_class_approval_rejected():
    case = _case()
    case["historical_security_class_approved"] = True
    with pytest.raises(ValueError, match="misrepresented"):
        _source_dom_check(_html(), case, "1000000000", "2020-02-01")


def test_unverified_namespace_rejected():
    body = _html().replace(
        b"http://fasb.org/us-gaap/2019-01-31",
        b"https://issuer.example/other",
    )
    with pytest.raises(ValueError, match="namespace declarations changed"):
        _source_dom_check(body, _case(), "1000000000", "2020-02-01")


def _rebind_all_originals(x, monkeypatch):
    """Replace all 16 fake source primaries with minted source XBRL HTML.

    Historical source primaries contain a harmless four-byte trailer so
    the current retriever will detect a byte-level difference while
    reparsing the same lexical fact projections.
    """
    earlier = json.loads(gzip.decompress(x["earlier"].read_bytes()))
    prior = {r["accession"]: r for r in earlier["records"]}
    manifest_path = x["manifest"]
    with manifest_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames
        rows = list(reader)
    for row in rows:
        if row["source_url"] not in x["lookup"]:
            continue
        accession = row["accessionNumber"]
        cik = row["cik"]
        symbol = "S" + accession[-3:]
        current = _html(cik, symbol)
        original = current + b" \n  "
        assert cover_evidence(current) == cover_evidence(original)
        x["lookup"][row["source_url"]] = current
        row["download_sha256"] = _sha(original)
        prior[accession]["primary_source"]["sha256"] = _sha(original)
        prior[accession]["primary_source"]["bytes"] = len(original)
        prior[accession]["cover_evidence"] = cover_evidence(original)
    with manifest_path.open("w", newline="") as handle:
        wr = csv.DictWriter(handle, fieldnames=header)
        wr.writeheader()
        wr.writerows(rows)
    monkeypatch.setattr(fetcher, "MANIFEST_HASH", _sha(manifest_path.read_bytes()))
    zipped_plain = json.dumps(earlier).encode()
    zipped = gzip.compress(zipped_plain, mtime=0)
    x["earlier"].write_bytes(zipped)
    x["execution"].write_text(json.dumps({
        "publication": {
            "sha256": _sha(zipped), "bytes": len(zipped),
            "uncompressed_sha256": _sha(zipped_plain),
            "uncompressed_bytes": len(zipped_plain),
        }
    }))
    pairs_path = x["paired"] / "private_issuer_pairs.jsonl"
    paired = [json.loads(line) for line in pairs_path.read_text().splitlines()]
    for issuer in paired:
        for filing in issuer["filings"]:
            accession = filing["accession"]
            filing.update({
                "acceptance_date": prior[accession]["recorded_acceptance_timestamp"][:10],
                "stock_symbol_raw": "S" + accession[-3:],
                "source_contextref": "StockClass",
                "registered_stock_title_raw": "Common Stock",
                "registered_exchange_raw": "NYSE",
                "source_class_member_qname": "us-gaap:CommonStockMember",
                "original_10k_HTML_bytes_reopened_here": False,
            })
    paired_blob = "".join(json.dumps(row) + "\n" for row in paired).encode()
    pairs_path.write_bytes(paired_blob)
    summary_file = x["paired"] / "public_summary.json"
    summary = json.loads(summary_file.read_text())
    summary["source_fingerprints"]["original_sec_gzip"] = _sha(zipped)
    summary_blob = json.dumps(summary).encode()
    summary_file.write_bytes(summary_blob)
    receipt_file = x["paired"] / "receipt.json"
    receipt = json.loads(receipt_file.read_text())
    receipt["files"]["private_issuer_pairs.jsonl"]["sha256"] = _sha(paired_blob)
    receipt["files"]["public_summary.json"]["sha256"] = _sha(summary_blob)
    receipt_file.write_text(json.dumps(receipt))


def test_independent_dom_all_sixteen_direct_original_html(sources, monkeypatch):  # noqa: F811
    _rebind_all_originals(sources, monkeypatch)
    fetcher.fetch_original_sec_16(
        sources["paired"], sources["manifest"], sources["earlier"],
        sources["execution"], sources["fetch_output"],
        user_agent="DisclosureDrift Academic (researcher@university.edu)",
        config=sources["cfg"], repo_root=sources["repo"], delay=1.1,
    )
    reparse = reparse_16_sec_originals(
        sources["fetch_output"], sources["earlier"], sources["execution"],
        sources["verify_output"], config=sources["cfg"], repo_root=sources["repo"],
    )
    assert reparse["all_current_source_lexical_evidence_matches_earlier_verified_packet"]
    final = check_current_sec_dom16(
        sources["fetch_output"], sources["paired"], sources["verify_output"],
        sources["repo"] / "reports" / "dom-original.json",
        config=sources["cfg"], repo_root=sources["repo"],
    )
    assert final["direct_current_original_SEC_html_source_contexts_checked"] == 16
    assert final["current_original_primary_source_sha256_mismatch_count"] == 16
    assert final["filing_year_counts"] == {"2020": 8, "2021": 8}
    assert final["direct_source_facts_and_registered_title_exchange_verified"]
    assert final["historical_issuer_or_stock_class_approved"] is False
    assert final["model_ready"] is False and final["final_period_opened"] is False
