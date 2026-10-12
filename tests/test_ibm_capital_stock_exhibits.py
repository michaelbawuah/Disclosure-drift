"""Invented SEC Exhibit 4.1 source files; never use a real licensed market row."""

import gzip
import hashlib
import json

import pytest

from disclosure_research.ibm_capital_stock_exhibits import (
    EXPECTED, REGISTERED_TITLE,
    _capital_equity_excerpt, audit_ibm_capital_stock_exhibits,
)
from disclosure_research.ibm_capital_stock_exhibits_verifier import (
    _independent_extract, independently_verify_ibm_exhibits,
)
from disclosure_research.protocol import canonical_hash, load_protocol


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _synthetic_ibm_exhibit(report_year, *, missing=""):
    texts = [
        "SUMMARY DESCRIPTION OF THE CAPITAL STOCK REGISTERED UNDER SECTION 12 "
        "OF THE SECURITIES EXCHANGE ACT OF 1934",
        "International Business Machines Corporation registered synthetic capital stock "
        "under the Exchange Act's registration description, with formal filed equity rights.",
        "The company is authorized to issue up to 4,687,500,000 shares of capital stock, "
        "$0.20 par value per share.",
        f"As of December 31, {report_year}, 1,500,000 shares of capital stock were issued "
        "and 1,000,000 were outstanding.",
        "The company has no other class of equity securities issued and outstanding.",
        "Holders of capital stock are entitled to receive dividends, when the directors "
        "authorize a distribution in accordance with outstanding equity rights.",
        "Each holder of capital stock is entitled to one vote per share on "
        "shareholder matters determined under the certificate.",
        "Holders of capital stock will be entitled to share equally in our assets "
        "available for distribution after creditors and senior claims have been paid.",
        "Shares of capital stock are not redeemable and have no subscription, conversion "
        "or preemptive rights.",
        "All shares of issued and outstanding capital stock are listed on the "
        "New York Stock Exchange and the Chicago Stock Exchange under the ticker symbol “IBM”.",
        "This invented fixture is only for validating the source-bound "
        "corroboration and is not an actual issuer security statement.",
        "SUMMARY DESCRIPTION OF THE DEBT SECURITIES REGISTERED UNDER SECTION 12 "
        "OF THE SECURITIES EXCHANGE ACT OF 1934",
        "Independent debt and other senior securities are not included in the equity section.",
    ]
    texts = [s for s in texts if missing not in s] if missing else texts
    return ('<html><head><meta charset="utf-8"></head><body><h1>Invented Exhibit 4.1</h1>' +
            "".join("<p>" + s + "</p>" for s in texts) + "</body></html>").encode()


def _synthetic_index(accession, report_year, filename, accepted, *, missing_exhibit=False):
    base = f"/Archives/edgar/data/51143/{accession.replace('-', '')}/"
    link = base + filename
    index = (
        '<html><head><title>EDGAR Filing Documents</title></head><body>'
        '<h2>EDGAR Filing Documents</h2>'
        '<p>Form 10-K - Annual report SEC Accession No. ' + accession
        + f' Filing Date {accepted[:10]} Accepted {accepted.replace("T", " ")} '
        + f'Documents 209 Period of Report {report_year}-12-31</p>'
        '<table><tr><th>Seq</th><th>Document</th><th>Type</th></tr>'
    )
    if missing_exhibit:
        index += '<tr><td>3</td><td>EX-4.1</td><td><a href="/Archives/edgar/data/51143/wrong.htm">wrong</a></td><td>EX-4.1</td></tr>'
    else:
        index += f'<tr><td>3</td><td>EX-4.1</td><td><a href="{link}">{filename}</a></td><td>EX-4.1</td></tr>'
    index += '</table></body></html>'
    return index.encode()


@pytest.fixture
def demo(tmp_path):
    root = tmp_path / "repo"
    source = root / "outputs" / "exhibits"
    prior = root / "outputs" / "prior-pairs"
    reports = root / "reports"
    source.mkdir(parents=True)
    prior.mkdir()
    reports.mkdir()
    config = load_protocol()
    filed, original = [], []
    original_dates = {
        "2020": "2020-02-25T16:54:20",
        "2021": "2021-02-23T17:08:23",
    }
    for year, spec in EXPECTED.items():
        accession = spec["accession"]
        source_date = original_dates[year]
        stamp = source_date + "-05:00"
        files = [
            source / f'{year}-{spec["exhibit"]}',
            source / f'{year}-{accession}-index.html',
            source / f'{year}-index.json',
        ]
        exhibit = _synthetic_ibm_exhibit(spec["report_year"])
        files[0].write_bytes(exhibit)
        files[1].write_bytes(_synthetic_index(
            accession, spec["report_year"], spec["exhibit"], source_date
        ))
        directory = {"directory": {"item": [
            {"name": spec["exhibit"], "size": str(len(exhibit)), "last-modified": source_date.replace("T", " ")},
            {"name": spec["filing_primary"], "size": "2000"},
            {"name": accession + "-index.html", "size": "200"},
            {"name": "FilingSummary.xml", "size": "100"},
            {"name": "MetaLinks.json", "size": "100"},
        ]}}
        files[2].write_text(json.dumps(directory))
        filed.append({
            "accession": accession,
            "registered_stock_title_raw": REGISTERED_TITLE,
            "stock_symbol_raw": "IBM",
            "source_class_member_qname": "us-gaap:CommonStockMember",
            "acceptance_date": source_date[:10],
            "historical_security_class_approved": False,
            "historical_security_link_known_at": None,
        })
        original.append({
            "accession": accession,
            "manifest_cik_raw": "0000051143",
            "acceptance_date": source_date[:10],
            "recorded_acceptance_timestamp": stamp,
            "header_identity": {"header_identity_consistent": True},
            "known_at": None, "available_at": None,
            "security_link_created": False,
        })
    original_packet = {
        "status": "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED",
        "original_sec_bytes_reread": True,
        "source_approvals": 0,
        "final_period_opened": False,
        "xbrl_fact_values_interpreted": False,
        "protocol_sha256": canonical_hash(config),
        "records": original,
    }
    gz = reports / "prior_sec_original.gz"
    gz.write_bytes(gzip.compress(json.dumps(original_packet).encode(), mtime=0))
    pair_record = {
        "issuer_CIK": "0000051143",
        "filings": filed,
        "historical_security_identity_known_at": None,
        "human_approved_historical_class": False,
    }
    pair_blob = (json.dumps(pair_record) + "\n").encode()
    pub = {
        "status": "ORIGINAL_10K_REGISTERED_STOCK_PAIRED_YEAR_REVIEW_NOT_APPROVED",
        "source_fingerprints": {
            "locked_protocol": canonical_hash(config),
            "original_sec_gzip": sha(gz.read_bytes()),
        },
        "source_approvals_created": 0, "historical_CIK_to_security_link_approved": False,
        "human_source_review_completed": False,
        "model_ready": False, "final_period_opened": False,
    }
    pub_raw = json.dumps(pub).encode()
    (prior / "private_issuer_pairs.jsonl").write_bytes(pair_blob)
    (prior / "public_summary.json").write_bytes(pub_raw)
    (prior / "receipt.json").write_text(json.dumps({
        "status": pub["status"],
        "source_approvals": 0, "class_approvals": 0,
        "files": {
            "private_issuer_pairs.jsonl": {"sha256": sha(pair_blob), "bytes": len(pair_blob)},
            "public_summary.json": {"sha256": sha(pub_raw), "bytes": len(pub_raw)},
        },
    }))
    pin = reports / "source_pin.json"
    pinned = {
        "schema_version": 1,
        "status": "CURRENT_SEC_IBM_10K_EX4_SOURCE_BYTES_PINNED_NOT_HISTORICAL_PUBLICATION",
        "issuer_CIK": "0000051143",
        "first_publication_known_at": None, "security_link_known_at": None,
        "source_approved_for_empirical_model": False,
        "filings": {},
    }
    for year, source_spec in EXPECTED.items():
        acc = source_spec["accession"]
        base = f"https://www.sec.gov/Archives/edgar/data/51143/{acc.replace('-', '')}/"
        objects = {}
        for kind, name, url in (
            ("exhibit", f'{year}-{source_spec["exhibit"]}', base + source_spec["exhibit"]),
            ("filing_index_html", f'{year}-{acc}-index.html', base + acc + "-index.html"),
            ("directory_index_json", f"{year}-index.json", base + "index.json"),
        ):
            data = (source / name).read_bytes()
            objects[kind] = {
                "local_file": name, "url": url,
                "sha256": sha(data), "bytes": len(data),
            }
        pinned["filings"][year] = {
            "accession": acc,
            "accepted_at_new_york_local": original_dates[year],
            "report_year_end": source_spec["report_year"],
            "objects": objects,
        }
    pin.write_text(json.dumps(pinned))
    return {
        "root": root, "source": source, "pin": pin,
        "prior": prior, "gz": gz, "config": config,
        "output": root / "outputs" / "capital-check",
        "verify_output": root / "reports" / "independent.json",
    }


def refresh_pin(d):
    path = d["pin"]
    cfg = json.loads(path.read_text())
    for yr, meta in cfg["filings"].items():
        for kind, original in meta["objects"].items():
            data = (d["source"] / original["local_file"]).read_bytes()
            original["sha256"] = sha(data)
            original["bytes"] = len(data)
    path.write_text(json.dumps(cfg))


def run(d):
    return audit_ibm_capital_stock_exhibits(
        d["source"], d["prior"], d["gz"], d["output"],
        source_pin_path=d["pin"], config=d["config"], repo_root=d["root"],
    )


def verify(d):
    return independently_verify_ibm_exhibits(
        d["source"], d["output"], d["verify_output"],
        source_pin_path=d["pin"], config=d["config"], repo_root=d["root"],
    )


def test_two_original_exhibit_sources_and_closed_gates(demo):
    summary = run(demo)
    assert summary["official_SEC_EX_4_1_documents_verified"] == 2
    assert summary["both_exhibits_expressly_state_no_other_issued_outstanding_equity_class"]
    assert summary["both_exhibits_describe_capital_stock_voting_dividends_residual_rights"]
    assert summary["both_exhibits_identify_IBM_capital_stock_ticker_and_NYSE_listing"]
    assert summary["IBM_capital_stock_title_equity_nature_corroborated"]
    assert summary["current_SEC_archive_directory_advertised_size_equal_to_retrieved_Exhibit_4_1_count"] == 2
    assert summary["current_SEC_archive_directory_size_minus_retrieved_exhibit_bytes"] == [0, 0]
    assert summary["historical_CRSP_CIK_PERMNO_mapping_approved"] is False
    assert summary["IBM_capital_stock_automatically_approved_common_stock"] is False
    assert summary["source_or_human_approvals_created"] == 0
    assert summary["model_ready"] is False and summary["final_period_opened"] is False
    result = demo["output"]
    assert result.stat().st_mode & 0o077 == 0
    receipt = json.loads((result / "receipt.json").read_text())
    for name, entry in receipt["files"].items():
        raw = (result / name).read_bytes()
        assert sha(raw) == entry["sha256"]
        assert (result / name).stat().st_mode & 0o222 == 0
    assert "candidate_PERMNO" not in (result / "public_summary.json").read_text()
    assert '"historical_source_known_at":' not in (result / "public_summary.json").read_text()


def test_independent_HTMLParser_rebuilds_both_exhibits(demo):
    run(demo)
    new = verify(demo)
    assert new["independently_verified_official_exhibit_4_1_documents"] == 2
    assert new["original_IBM_single_equity_class_and_capital_stock_rights_verified"]
    assert new["original_SEC_official_filing_index_and_exhibit_document_matches"]
    assert new["independent_stdlib_HTMLParser_used_instead_of_initial_lxml_parser"]
    assert new["historical_CRSP_IBM_common_stock_class_approved"] is False
    assert new["source_known_at_or_available_at_established"] is False
    assert new["source_fingerprints"]["protocol_sha256"] == canonical_hash(demo["config"])


def test_reject_missing_unique_outstanding_equity_class_statement(demo):
    path = demo["source"] / "2020-ex-4d1.htm"
    path.write_bytes(_synthetic_ibm_exhibit(2019, missing="The company has no other class"))
    refresh_pin(demo)
    with pytest.raises(ValueError, match="Both source-bound IBM exhibits"):
        run(demo)


def test_reject_missing_registered_equity_voting_rights_statement(demo):
    path = demo["source"] / "2021-ibm-20201231xex4d1.htm"
    path.write_bytes(_synthetic_ibm_exhibit(2020, missing="Each holder of capital stock"))
    refresh_pin(demo)
    with pytest.raises(ValueError, match="Both source-bound IBM exhibits"):
        run(demo)


def test_reject_renamed_stock_ticker_without_source_equivalence(demo):
    path = demo["source"] / "2020-ex-4d1.htm"
    path.write_bytes(path.read_bytes().replace(b'symbol \xe2\x80\x9cIBM\xe2\x80\x9d', b'symbol \xe2\x80\x9cIBX\xe2\x80\x9d'))
    refresh_pin(demo)
    with pytest.raises(ValueError, match="Both source-bound IBM exhibits"):
        run(demo)


def test_reject_wrong_SEC_accepted_clock_even_if_it_looks_plausible(demo):
    p = demo["source"] / "2020-0001558370-20-001334-index.html"
    p.write_text(p.read_text().replace("2020-02-25 16:54:20", "2020-02-25 16:54:21"))
    refresh_pin(demo)
    with pytest.raises(ValueError, match="acceptance timestamp differs"):
        run(demo)


def test_reject_SEC_exhibit_missing_from_official_index(demo):
    p = demo["source"] / "2020-0001558370-20-001334-index.html"
    p.write_bytes(_synthetic_index(
        "0001558370-20-001334", 2019, "ex-4d1.htm",
        "2020-02-25T16:54:20", missing_exhibit=True,
    ))
    refresh_pin(demo)
    with pytest.raises(ValueError, match="Exhibit 4.1 document isn't uniquely indexed"):
        run(demo)


def test_reject_missing_source_directory_exhibit_record(demo):
    p = demo["source"] / "2020-index.json"
    info = json.loads(p.read_text())
    info["directory"]["item"][0]["name"] = "wrong-exhibit.htm"
    p.write_text(json.dumps(info))
    refresh_pin(demo)
    with pytest.raises(ValueError, match="directory index does not include Exhibit"):
        run(demo)


def test_prior_10K_stock_class_is_not_silently_approved(demo):
    pair_path = demo["prior"] / "private_issuer_pairs.jsonl"
    info = json.loads(pair_path.read_text().strip())
    info["filings"][0]["historical_security_class_approved"] = True
    raw = (json.dumps(info) + "\n").encode()
    pair_path.write_bytes(raw)
    receipt_file = demo["prior"] / "receipt.json"
    receipt = json.loads(receipt_file.read_text())
    receipt["files"]["private_issuer_pairs.jsonl"]["sha256"] = sha(raw)
    receipt_file.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="original SEC cover stock was not a pending"):
        run(demo)


def test_original_source_exhibit_tamper_rejected_by_independent_verifier(demo):
    run(demo)
    p = demo["source"] / "2020-ex-4d1.htm"
    p.write_bytes(p.read_bytes() + b"\nTAMPER")
    with pytest.raises(ValueError, match="index bytes changed"):
        verify(demo)


def test_independent_rejects_forged_IBM_historical_class_approval_with_rehashed_public(demo):
    run(demo)
    pub = demo["output"] / "public_summary.json"
    info = json.loads(pub.read_text())
    info["IBM_capital_stock_automatically_approved_common_stock"] = True
    raw = json.dumps(info).encode()
    pub.chmod(0o600)
    pub.write_bytes(raw)
    receipt_file = demo["output"] / "receipt.json"
    receipt_file.chmod(0o600)
    receipt = json.loads(receipt_file.read_text())
    receipt["files"]["public_summary.json"]["sha256"] = sha(raw)
    receipt["files"]["public_summary.json"]["bytes"] = len(raw)
    receipt_file.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="research/class approval gates"):
        verify(demo)


def test_private_original_evidence_export_immutable(demo):
    run(demo)
    with pytest.raises(ValueError, match="new private"):
        run(demo)


def test_same_SEC_parsed_exhibit_corrupted_year_not_admitted(demo):
    p = demo["source"] / "2020-ex-4d1.htm"
    p.write_bytes(p.read_bytes().replace(b"December 31, 2019", b"December 31, 2025"))
    refresh_pin(demo)
    with pytest.raises(ValueError, match="registered equity date"):
        run(demo)


def test_independent_source_extraction_retains_rights_and_section_hash(demo):
    source = demo["source"] / "2020-ex-4d1.htm"
    first = _capital_equity_excerpt(source.read_bytes(), 2019)
    second = _independent_extract(source.read_bytes(), 2019)
    assert first["source_section_sha256"] == second["section_sha256"]
    assert first["year_end_outstanding_capital_stock_shares"] == second["outstanding_capital_stock_shares"]
    assert second["all_independently_checked_equity_rights_present"]
    assert first["source_claims"]["original_IBM_equity_ticker"] is True
    assert first["all_expected_equity_nature_claims_present"] is True


def test_prevent_source_symlinks(demo):
    f = demo["source"] / "2020-ex-4d1.htm"
    original = demo["source"] / "original_exhibit.htm"
    f.rename(original)
    f.symlink_to(original)
    with pytest.raises(ValueError, match="symlink"):
        run(demo)



def test_original_official_SEC_source_hash_pin_detects_mutation_before_source_parsing(demo):
    p = demo["source"] / "2020-ex-4d1.htm"
    p.write_bytes(p.read_bytes() + b"\nFORGED_SOURCE_TRAILER")
    with pytest.raises(ValueError, match="differs from checked-in source pin"):
        run(demo)


def test_source_pin_must_not_assert_historical_publication(demo):
    cfg = json.loads(demo["pin"].read_text())
    cfg["first_publication_known_at"] = "2020-02-25T16:54:20-05:00"
    demo["pin"].write_text(json.dumps(cfg))
    with pytest.raises(ValueError, match="source pin is missing"):
        run(demo)


def test_archival_index_size_mismatch_is_reported_not_mistaken_for_approval(demo):
    index = demo["source"] / "2020-index.json"
    info = json.loads(index.read_text())
    size = int(info["directory"]["item"][0]["size"])
    info["directory"]["item"][0]["size"] = str(size - 111)
    index.write_text(json.dumps(info))
    refresh_pin(demo)
    out = run(demo)
    assert out["current_SEC_archive_directory_size_minus_retrieved_exhibit_bytes"] == [-111, 0]
    assert out["current_SEC_archive_directory_advertised_size_equal_to_retrieved_Exhibit_4_1_count"] == 1
    assert out["earliest_SEC_public_dissemination_verified"] is False


def test_independent_verifier_refuses_forged_share_balance_with_rehashed_private_audit(demo):
    run(demo)
    file = demo["output"] / "private_exhibit_review.jsonl"
    rows = [json.loads(t) for t in file.read_text().splitlines()]
    rows[0]["exhibit_equity_nature"]["year_end_outstanding_capital_stock_shares"] += 10
    changed = "".join(json.dumps(row) + chr(10) for row in rows).encode()
    file.chmod(0o600)
    file.write_bytes(changed)
    receipt_path = demo["output"] / "receipt.json"
    receipt_path.chmod(0o600)
    receipt = json.loads(receipt_path.read_text())
    receipt["files"]["private_exhibit_review.jsonl"] = {
        "sha256": sha(changed), "bytes": len(changed),
    }
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="equity-source values differ"):
        verify(demo)
