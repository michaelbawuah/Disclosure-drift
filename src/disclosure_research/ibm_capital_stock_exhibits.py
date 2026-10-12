"""IBM 'Capital stock' evidence from original SEC 10-K EX-4.1 source exhibits.

Source-only, offline reinspection: equity characteristics and exclusive issued
equity class are documentary facts, not an adjudicated common-share class,
historical CIK-PERMNO validity, public dissemination or vendor known_at.
"""

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from lxml import html

from .protocol import canonical_hash

STATUS = "IBM_2019_2020_CAPITAL_STOCK_EXHIBIT_EQUITY_RIGHTS_CORROBORATED_NOT_APPROVED"
EARLIER_STATUS = "ORIGINAL_10K_REGISTERED_STOCK_PAIRED_YEAR_REVIEW_NOT_APPROVED"
ORIGINAL_SEC_STATUS = "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED"
SEC_HOST = "www.sec.gov"
CIK = "0000051143"
REGISTERED_TITLE = "Capital stock, par value $.20 per share"
EXPECTED = {
    "2020": {
        "accession": "0001558370-20-001334",
        "report_year": 2019,
        "exhibit": "ex-4d1.htm",
        "filing_primary": "ibm-20191231x10k2af531.htm",
    },
    "2021": {
        "accession": "0001558370-21-001489",
        "report_year": 2020,
        "exhibit": "ibm-20201231xex4d1.htm",
        "filing_primary": "ibm-20201231x10k.htm",
    },
}
START = "SUMMARY DESCRIPTION OF THE CAPITAL STOCK REGISTERED UNDER SECTION 12"
END = "SUMMARY DESCRIPTION OF THE DEBT SECURITIES REGISTERED UNDER SECTION 12"
RIGHTS = {
    "single_outstanding_equity_class": (
        r"the company has no other class of equity securities issued and outstanding"
    ),
    "one_vote_per_share": (
        r"each holder of capital stock is entitled to one vote per share"
    ),
    "dividends_for_capital_stock_holders": (
        r"holders of capital stock are entitled to receive dividends"
    ),
    "residual_liquidation_distribution": (
        r"holders of capital stock will be entitled to share equally in our assets available for distribution"
    ),
    "no_redemption_or_conversion": (
        r"shares of capital stock are not redeemable and have no subscription, conversion or preemptive rights"
    ),
    "registered_exchange_new_york": (
        r"all shares of issued and outstanding capital stock are listed on the new york stock exchange"
    ),
    "registered_exchange_chicago": (
        r"and the chicago stock exchange under the ticker symbol"
    ),
    "original_IBM_equity_ticker": (
        r'under the ticker symbol [“"\x22]IBM[”"\x22]'
    ),
}
PAR = re.compile(
    r"authorized to issue up to ([0-9,]+) shares of capital stock, "
    r"\$0\.20 par value per share", flags=re.I
)
OUTSTANDING = re.compile(
    r"as of december 31, (\d{4}), ([0-9,]+) shares of capital stock "
    r"were issued and ([0-9,]+) were outstanding", flags=re.I
)
IDENTITY = "international business machines corporation"


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _source(path, cap=8 * 1024 * 1024):
    initial = Path(path)
    _require(not initial.is_symlink(), "Source symlink is not permitted")
    path = initial.resolve(strict=True)
    _require(path.is_file() and path.stat().st_size <= cap,
             "Original SEC source absent or oversized")
    return path, path.read_bytes()


def _plain(raw):
    parser = html.HTMLParser(no_network=True, recover=True, huge_tree=False)
    root = html.fromstring(raw, parser=parser)
    text = " ".join(root.itertext())
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    return " ".join(text.split()), root


def _sec_href(href, accession, filename):
    expected = (
        "/Archives/edgar/data/51143/"
        + accession.replace("-", "") + "/" + filename
    )
    if href != expected:
        return False
    parsed = urlsplit("https://" + SEC_HOST + href)
    return (parsed.scheme == "https" and parsed.netloc == SEC_HOST
            and parsed.path == expected and not parsed.query and not parsed.fragment)


def _source_pin_data(pin_path, source_dir):
    """Require all six SEC original sources to match public checked-in pins."""
    _, blob = _source(pin_path, 128 * 1024)
    settings = json.loads(blob)
    _require(
        settings.get("schema_version") == 1
        and settings.get("status") ==
        "CURRENT_SEC_IBM_10K_EX4_SOURCE_BYTES_PINNED_NOT_HISTORICAL_PUBLICATION"
        and settings.get("issuer_CIK") == CIK
        and settings.get("first_publication_known_at") is None
        and settings.get("security_link_known_at") is None
        and settings.get("source_approved_for_empirical_model") is False
        and set(settings.get("filings", {})) == set(EXPECTED),
        "Original SEC source pin is missing, unapproved fields changed or unknown filings added",
    )
    source_dir = Path(source_dir).resolve(strict=True)
    for year, values in sorted(EXPECTED.items()):
        expected = settings["filings"][year]
        _require(
            expected.get("accession") == values["accession"]
            and expected.get("report_year_end") == values["report_year"]
            and len(expected.get("objects", {})) == 3
            and set(expected["objects"]) == {
                "exhibit", "filing_index_html", "directory_index_json",
            }, "Source pin SEC accession, year or object list differs",
        )
        base = (
            "https://" + SEC_HOST + "/Archives/edgar/data/51143/"
            + values["accession"].replace("-", "") + "/"
        )
        local = {
            "exhibit": f'{year}-{values["exhibit"]}',
            "filing_index_html": f'{year}-{values["accession"]}-index.html',
            "directory_index_json": f"{year}-index.json",
        }
        online = {
            "exhibit": base + values["exhibit"],
            "filing_index_html": base + values["accession"] + "-index.html",
            "directory_index_json": base + "index.json",
        }
        for name in local:
            record = expected["objects"][name]
            _require(
                record.get("local_file") == local[name]
                and record.get("url") == online[name]
                and isinstance(record.get("sha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", record["sha256"])
                and type(record.get("bytes")) is int
                and 100 <= record["bytes"] <= 8 * 1024 * 1024,
                "Source pin SEC URL/local filename/expected digest does not match verified filing",
            )
            _, original = _source(source_dir / local[name])
            _require(
                _sha(original) == record["sha256"]
                and len(original) == record["bytes"],
                "Original SEC Exhibit 4.1/current index differs from checked-in source pin",
            )
    return settings, _sha(blob)


def _verified_prior_pair(prior_dir, sec_prior_gzip, config):
    prior = Path(prior_dir).resolve(strict=True)
    _, receipt_raw = _source(prior / "receipt.json", 128_000)
    _, summary_raw = _source(prior / "public_summary.json", 128_000)
    _, private_raw = _source(prior / "private_issuer_pairs.jsonl", 1024 * 1024)
    receipt, summary = json.loads(receipt_raw), json.loads(summary_raw)
    _require(
        receipt["status"] == summary["status"] == EARLIER_STATUS
        and receipt["files"]["private_issuer_pairs.jsonl"]["sha256"] == _sha(private_raw)
        and receipt["files"]["public_summary.json"]["sha256"] == _sha(summary_raw)
        and summary["source_fingerprints"]["locked_protocol"] == canonical_hash(config)
        and summary["source_approvals_created"] == 0
        and receipt["source_approvals"] == 0
        and receipt["class_approvals"] == 0
        and summary["historical_CIK_to_security_link_approved"] is False
        and summary["human_source_review_completed"] is False
        and summary["model_ready"] is False
        and summary["final_period_opened"] is False,
        "Earlier IBM capital-stock pair source lost unapproved original filing gates"
    )
    source_pairs = [json.loads(line) for line in private_raw.decode().splitlines()]
    issuer = [case for case in source_pairs if case["issuer_CIK"] == CIK]
    _require(len(issuer) == 1 and len(issuer[0]["filings"]) == 2
             and issuer[0]["historical_security_identity_known_at"] is None
             and issuer[0]["human_approved_historical_class"] is False,
             "Two original 10-K IBM stock pair sources are missing or approved")
    filings = {case["accession"]: case for case in issuer[0]["filings"]}
    _require(set(filings) == {entry["accession"] for entry in EXPECTED.values()},
             "Unexpected IBM original 10-K SEC accessions")
    for case in filings.values():
        _require(case["registered_stock_title_raw"] == REGISTERED_TITLE
                 and case["stock_symbol_raw"] == "IBM"
                 and case["source_class_member_qname"] == "us-gaap:CommonStockMember"
                 and case["historical_security_class_approved"] is False
                 and case["historical_security_link_known_at"] is None,
                 "IBM original SEC cover stock was not a pending matched capital-stock case")
    _, gz = _source(sec_prior_gzip, 8 * 1024 * 1024)
    _require(_sha(gz) == summary["source_fingerprints"]["original_sec_gzip"],
             "Original SEC lexical source not the verified pair input")
    import gzip
    unpacked = gzip.decompress(gz)
    _require(len(unpacked) < 16 * 1024 * 1024, "Original source gzip expands beyond limit")
    source = json.loads(unpacked)
    _require(source["status"] == ORIGINAL_SEC_STATUS
             and source["original_sec_bytes_reread"] is True
             and source["source_approvals"] == 0
             and source["final_period_opened"] is False
             and source["xbrl_fact_values_interpreted"] is False
             and source["protocol_sha256"] == canonical_hash(config),
             "Earlier original SEC report was not locked lexical-only evidence")
    report = {entry["accession"]: entry for entry in source["records"]}
    for acc, case in filings.items():
        original = report[acc]
        _require(
            original["manifest_cik_raw"] == CIK
            and original["acceptance_date"] == case["acceptance_date"]
            and original["header_identity"]["header_identity_consistent"] is True
            and original["known_at"] is None
            and original["available_at"] is None
            and original["security_link_created"] is False,
            "Original 10-K filer/clock is not the preserved IBM report"
        )
    return filings, report, {
        "prior_pair_receipt_sha256": _sha(receipt_raw),
        "prior_private_pair_rows_sha256": _sha(private_raw),
        "prior_original_sec_gzip_sha256": _sha(gz),
        "protocol_sha256": canonical_hash(config),
    }


def _index_evidence(index_html, index_json, accession, entry):
    plain, root = _plain(index_html)
    _require(
        f"SEC Accession No. {accession}" in plain
        and "Form 10-K - Annual report" in plain
        and "EX-4.1" in plain,
        "Official SEC filing index accession/type not supported"
    )
    metadata = re.search(
        r"SEC Accession No\.\s*" + re.escape(accession) +
        r"\s*Filing Date\s*(\d{4}-\d{2}-\d{2})\s*"
        r"Accepted\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2}).*?"
        r"Period of Report\s*(\d{4}-\d{2}-\d{2})", plain, re.I,
    )
    _require(metadata is not None, "Original SEC index acceptance/period fields missing")
    filing_day, accepted_date, accepted_time, period = metadata.groups()
    _require(filing_day == accepted_date and period == f'{entry["report_year"]}-12-31',
             "Official SEC index period of report and filing date disagree")
    matched_rows = []
    for tr in root.xpath("//tr"):
        labels = " ".join(" ".join(tr.itertext()).split())
        if re.search(r"\bEX-4\.1\b", labels):
            a = tr.xpath(".//a")
            for anchor in a:
                link = anchor.get("href")
                if _sec_href(link, accession, entry["exhibit"]):
                    matched_rows.append((labels, link))
    _require(len(matched_rows) == 1,
             "The exact original SEC Exhibit 4.1 document isn't uniquely indexed")
    json_index = json.loads(index_json)
    directory = json_index.get("directory", {}).get("item", [])
    _require(isinstance(directory, list) and len(directory) >= 5,
             "Official SEC filing directory JSON appears incomplete")
    observed = [x for x in directory if x.get("name") == entry["exhibit"]]
    _require(len(observed) == 1 and observed[0].get("size", "").isdigit(),
             "Original SEC directory index does not include Exhibit 4.1 source file")
    return {
        "accession": accession,
        "accepted_at_new_york_local_text": accepted_date + "T" + accepted_time,
        "filing_date": filing_day,
        "period_end": period,
        "exhibit_type": "EX-4.1",
        "exhibit_indexed_relative_path": matched_rows[0][1],
        "exhibit_archive_index_file_size_bytes": int(observed[0]["size"]),
        "exhibit_archive_index_last_modified_text": observed[0].get("last-modified"),
        "exhibit_index_file_size_is_current_download_size": None,
        "archive_metadata_first_publication_inferred": False,
    }


def _capital_equity_excerpt(exhibit_bytes, year):
    full, _ = _plain(exhibit_bytes)
    start = full.find(START)
    end = full.find(END)
    _require(start >= 0 and end > start and full.find(START, start + 1) < 0,
             "Original Exhibit 4.1 doesn't contain one bounded equity registration section")
    only = full[start:end]
    _require(500 <= len(only) <= 11000
             and IDENTITY in only.casefold()
             and "CAPITAL STOCK REGISTERED UNDER SECTION 12" in only,
             "Original SEC capital-stock registration section missing IBM identity")
    flags = {name: bool(re.search(pattern, only, re.I)) for name, pattern in RIGHTS.items()}
    p = PAR.search(only)
    out = OUTSTANDING.search(only)
    _require(p is not None and out is not None,
             "Official IBM Exhibit 4.1 equity par value or outstanding shares text missing")
    observed_year = int(out.group(1))
    _require(observed_year == year, "Exhibit registered equity date doesn't match reporting year")
    authorized, issued, outstanding = int(p.group(1).replace(",", "")), int(out.group(2).replace(",", "")), int(out.group(3).replace(",", ""))
    _require(0 < outstanding <= issued <= authorized,
             "SEC original registered capital stock share counts are inconsistent")
    return {
        "source_claims": flags,
        "all_expected_equity_nature_claims_present": all(flags.values()),
        "authorized_capital_stock_shares": authorized,
        "year_end_issued_capital_stock_shares": issued,
        "year_end_outstanding_capital_stock_shares": outstanding,
        "source_section_sha256": _sha(only.encode("utf-8")),
        "source_section_text_private": only,
        "exhibit_full_plaintext_sha256": _sha(full.encode("utf-8")),
        "source_has_other_class_of_issued_equity": not flags["single_outstanding_equity_class"],
        "exhibit_source_XBRL_semantics_validated": False,
    }


def audit_ibm_capital_stock_exhibits(discovery_dir, paired, original_sec_gzip, output, *,
                                     source_pin_path, config, repo_root):
    repo = Path(repo_root).resolve(strict=True)
    dest = Path(output).resolve()
    _require(not dest.exists()
             and dest.is_relative_to(repo / "outputs")
             and dest != repo / "outputs",
             "Output must be a new private location under outputs/")
    files = Path(discovery_dir).resolve(strict=True)
    _require(not dest.is_relative_to(files), "Output cannot nest in source folder")
    source_pin, source_pin_sha256 = _source_pin_data(source_pin_path, files)
    pairs, earlier_original, source_pins = _verified_prior_pair(paired, original_sec_gzip, config)
    source_pins["original_sec_exhibit_pin_sha256"] = source_pin_sha256
    private_rows = []
    sec_evidence = []
    source_inputs = []
    for selection_year, meta in sorted(EXPECTED.items()):
        index_file = files / f'{selection_year}-{meta["accession"]}-index.html'
        directory_file = files / f"{selection_year}-index.json"
        exhibit_file = files / f'{selection_year}-{meta["exhibit"]}'
        idx_path, idx_bytes = _source(index_file)
        dir_path, dir_bytes = _source(directory_file)
        exh_path, exhibit_bytes = _source(exhibit_file)
        source_inputs.extend([(idx_path, _sha(idx_bytes)), (dir_path, _sha(dir_bytes)), (exh_path, _sha(exhibit_bytes))])
        accession = meta["accession"]
        current_index = _index_evidence(idx_bytes, dir_bytes, accession, meta)
        _require(
            current_index["accepted_at_new_york_local_text"]
            == source_pin["filings"][selection_year]["accepted_at_new_york_local"],
            "Original SEC indexed acceptance timestamp differs from locked Exhibit 4.1 source pin",
        )
        original = earlier_original[accession]
        _require(current_index["filing_date"] == original["acceptance_date"],
                 "SEC package filing date doesn't match earlier original SEC 10-K")
        original_stamp = datetime.fromisoformat(
            original["recorded_acceptance_timestamp"].replace("Z", "+00:00")
        ).astimezone(ZoneInfo("America/New_York"))
        _require(original_stamp.strftime("%Y-%m-%dT%H:%M:%S") == current_index["accepted_at_new_york_local_text"],
                 "Original SEC indexed accepted clock doesn't match prior source-verified SGML")
        exhibit = _capital_equity_excerpt(exhibit_bytes, meta["report_year"])
        current_index["exhibit_archive_index_file_size_is_current_download_size"] = (
            current_index["exhibit_archive_index_file_size_bytes"] == len(exhibit_bytes)
        )
        earlier_case = pairs[accession]
        _require(
            earlier_case["registered_stock_title_raw"] == REGISTERED_TITLE
            and earlier_case["stock_symbol_raw"] == "IBM"
            and earlier_case["historical_security_class_approved"] is False,
            "Official original Exhibit 4.1 isn't connected to the original IBM stock case"
        )
        record = {
            "selection_year": int(selection_year),
            "year_end": meta["report_year"],
            "accession": accession,
            "issuer_CIK": CIK,
            "original_SEC_registered_title": earlier_case["registered_stock_title_raw"],
            "original_SEC_common_stock_member_lexical": earlier_case["source_class_member_qname"],
            "index": current_index,
            "exhibit_url": (
                "https://" + SEC_HOST + current_index["exhibit_indexed_relative_path"]
            ),
            "exhibit_filename": meta["exhibit"],
            "source_exhibit_bytes": len(exhibit_bytes),
            "source_exhibit_sha256": _sha(exhibit_bytes),
            "index_HTML_sha256": _sha(idx_bytes),
            "index_directory_JSON_sha256": _sha(dir_bytes),
            "exhibit_equity_nature": exhibit,
            "exhibit_registered_capital_stock_is_single_equity_class_candidate": (
                exhibit["all_expected_equity_nature_claims_present"]
            ),
            "historical_CRSP_class_approved": False,
            "historical_security_link_validity_approved": False,
            "historical_source_known_at": None,
            "earliest_public_dissemination_verified": False,
            "human_source_review_approved": False,
        }
        private_rows.append(record)
        sec_evidence.append({
            "SEC_10K_accession": accession,
            "current_public_Exhibit_4_1_url": record["exhibit_url"],
            "source_exhibit_sha256": record["source_exhibit_sha256"],
            "equity_facts_supported": exhibit["all_expected_equity_nature_claims_present"],
            "single_issued_equity_class_claim_present": exhibit["source_claims"]["single_outstanding_equity_class"],
            "capital_stock_voting_rights_supported": exhibit["source_claims"]["one_vote_per_share"],
            "capital_stock_dividend_rights_supported": exhibit["source_claims"]["dividends_for_capital_stock_holders"],
            "capital_stock_IBM_exchange_listing_supported": (
                exhibit["source_claims"]["original_IBM_equity_ticker"]
                and exhibit["source_claims"]["registered_exchange_new_york"]
            ),
            "exhibit_year_end_outstanding_shares_public": exhibit["year_end_outstanding_capital_stock_shares"],
            "exhibit_issued_equity_class_status": "EXHIBIT_EQUITY_RIGHTS_DOCUMENTED_CLASS_APPROVAL_PENDING",
        })
    _require(len(private_rows) == len(sec_evidence) == 2
             and all(x["exhibit_equity_nature"]["all_expected_equity_nature_claims_present"]
                     for x in private_rows),
             "Both source-bound IBM exhibits must support every documented capital-stock characteristic")
    _require(private_rows[0]["exhibit_equity_nature"]["authorized_capital_stock_shares"]
             == private_rows[1]["exhibit_equity_nature"]["authorized_capital_stock_shares"]
             and private_rows[1]["exhibit_equity_nature"]["year_end_outstanding_capital_stock_shares"]
             >= private_rows[0]["exhibit_equity_nature"]["year_end_outstanding_capital_stock_shares"],
             "Observed two-year IBM equity authorization/outstanding history requires review")
    for filename, digest in source_inputs:
        _require(_sha(filename.read_bytes()) == digest,
                 "Original SEC IBM indexed exhibit source changed during audit")
    result = {
        "schema_version": 1,
        "status": STATUS,
        "issuer": "International Business Machines Corporation (IBM)",
        "original_10K_filings_with_capital_stock_cover_title": len(private_rows),
        "official_SEC_EX_4_1_documents_verified": len(sec_evidence),
        "separate_reporting_year_ends": [2019, 2020],
        "all_original_SEC_filing_index_accessions_and_accepted_clocks_match_prior_10K": True,
        "SEC_equity_registration_evidence": sec_evidence,
        "both_exhibits_expressly_state_no_other_issued_outstanding_equity_class": True,
        "both_exhibits_describe_capital_stock_voting_dividends_residual_rights": True,
        "both_exhibits_identify_IBM_capital_stock_ticker_and_NYSE_listing": True,
        "all_sec_original_exhibit_source_hashes_preserved": True,
        "current_SEC_archive_directory_advertised_size_equal_to_retrieved_Exhibit_4_1_count":
            sum(
                item["index"]["exhibit_archive_index_file_size_is_current_download_size"]
                for item in private_rows
            ),
        "current_SEC_archive_directory_size_minus_retrieved_exhibit_bytes": [
            item["index"]["exhibit_archive_index_file_size_bytes"] -
            item["source_exhibit_bytes"] for item in private_rows
        ],
        "source_fingerprints": source_pins,
        "source_current_index_metadata_not_first_publication_proof": True,
        "IBM_capital_stock_title_equity_nature_corroborated": True,
        "IBM_capital_stock_automatically_approved_common_stock": False,
        "historical_CRSP_CIK_PERMNO_mapping_approved": False,
        "historical_source_known_at_or_vendor_available_at_established": False,
        "earliest_SEC_public_dissemination_verified": False,
        "source_or_human_approvals_created": 0,
        "full_iXBRL_semantic_validation_performed": False,
        "model_ready": False,
        "final_period_opened": False,
        "interpretation": (
            "Both IBM original SEC Exhibit 4.1s document a single issued equity class "
            "with residual/voting/dividend rights listed as IBM on NYSE, explaining "
            "the SEC 10-K 'Capital stock' title; this is not historical security "
            "identity, stock-class eligibility, first-publication or source known-at approval."
        ),
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ibm-exhibit-audit-", dir=dest.parent) as temp:
        stage = Path(temp) / "audit"
        stage.mkdir(mode=0o700)
        (stage / "private_exhibit_review.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in private_rows)
        )
        (stage / "public_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        receipt = {
            "schema_version": 1, "status": STATUS,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "files": {
                name: {"sha256": _sha((stage / name).read_bytes()),
                       "bytes": (stage / name).stat().st_size}
                for name in ("private_exhibit_review.jsonl", "public_summary.json")
            },
            "source_fingerprints": result["source_fingerprints"],
            "historical_CRSP_class_approvals": 0, "human_reviews": 0,
            "model_ready": False, "final_period_opened": False,
        }
        (stage / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        for f in stage.iterdir():
            os.chmod(f, 0o400)
        stage.rename(dest)
    return result
