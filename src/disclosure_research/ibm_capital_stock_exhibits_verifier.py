"""Independent raw IBM SEC Exhibit 4.1 equity fact and index reconstruction.

Uses stdlib HTMLParser instead of the first audit's lxml parser. Checks official
source bytes and pre-existing index/filing identity, but cannot establish when
the SEC or any historical data vendor first made those bytes available.
"""

import hashlib
import json
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path

from .ibm_capital_stock_exhibits import (
    CIK, EXPECTED, STATUS as FIRST_KIND,
)
from .protocol import canonical_hash

STATUS = "INDEPENDENT_IBM_ORIGINAL_EXHIBIT4_EQUITY_CLASS_EVIDENCE_RECONCILED_NOT_APPROVED"
EQUITY_START = "SUMMARY DESCRIPTION OF THE CAPITAL STOCK REGISTERED UNDER SECTION 12"
DEBT_START = "SUMMARY DESCRIPTION OF THE DEBT SECURITIES REGISTERED UNDER SECTION 12"


def _require(cond, msg):
    if not cond:
        raise ValueError(msg)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


class _OriginalText(HTMLParser):
    """Independent full-HTML text extraction, no external requests or scripts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def normalized(self):
        full = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", " ".join(self.parts))
        return " ".join(full.split())


def _read_original(path, cap=8 * 1024 * 1024):
    raw = Path(path)
    _require(not raw.is_symlink(), "Original SEC source is symlinked")
    original = raw.resolve(strict=True)
    _require(original.is_file() and original.stat().st_size <= cap,
             "Original SEC exhibit or audit source is missing/oversized")
    return original.read_bytes()


def _independent_extract(raw, source_year):
    p = _OriginalText()
    p.feed(raw.decode("utf-8", errors="replace"))
    p.close()
    full = p.normalized()
    start, end = full.find(EQUITY_START), full.find(DEBT_START)
    _require(start >= 0 and start < end
             and full.find(EQUITY_START, start + 1) == -1,
             "No unique original IBM equity section before the exhibit's debt description")
    section = full[start:end]
    _require(500 <= len(section) <= 11000
             and "International Business Machines Corporation" in section,
             "IBM issuer missing from original SEC registered-equity section")
    tests = {
        "one_outstanding_equity_class": "no other class of equity securities issued and outstanding",
        "dividend_rights": "holders of capital stock are entitled to receive dividends",
        "voting_rights": "each holder of capital stock is entitled to one vote per share",
        "residual_liquidation_rights": "holders of capital stock will be entitled to share equally in our assets available for distribution",
        "nonredeemable_no_conversion": "shares of capital stock are not redeemable and have no subscription, conversion or preemptive rights",
        "public_IBM_NYSE_listing": "all shares of issued and outstanding capital stock are listed on the new york stock exchange",
        "public_IBM_Chicago_listing": "and the chicago stock exchange under the ticker symbol",
    }
    folded = section.lower()
    _require(all(value in folded for value in tests.values()),
             "IBM original SEC exhibit rights, single equity class or exchange statement changed")
    _require(bool(re.search(r'under the ticker symbol\s*[“"\x22]IBM[”"\x22]', section)),
             "Source capital stock IBM ticker not present in the original exhibit")
    authorized = re.search(
        r"issue up to (\d[\d,]+) shares of capital stock, \$0\.20 par value per share", section, re.I,
    )
    issued = re.search(
        r"as of december 31, (\d{4}), (\d[\d,]+) shares of capital stock "
        r"were issued and (\d[\d,]+) were outstanding", section, re.I,
    )
    _require(authorized is not None and issued is not None
             and int(issued.group(1)) == source_year,
             "Original SEC authorized share and year-end capital-stock balances changed")
    values = [int(n.replace(",", "")) for n in (
        authorized.group(1), issued.group(2), issued.group(3),
    )]
    _require(0 < values[2] <= values[1] <= values[0],
             "Original equity share count bounds contradictory")
    return {
        "section_sha256": _sha(section.encode()),
        "original_html_plaintext_sha256": _sha(full.encode()),
        "authorized_stock_shares": values[0],
        "issued_capital_stock_shares": values[1],
        "outstanding_capital_stock_shares": values[2],
        "all_independently_checked_equity_rights_present": True,
    }


def independently_verify_ibm_exhibits(original_dir, first_audit_dir, out, *,
                                      source_pin_path, config, repo_root):
    root = Path(repo_root).resolve(strict=True)
    target = Path(out).resolve()
    _require(not target.exists() and target.is_relative_to(root / "reports"),
             "Independent verification must write one new aggregate report under reports/")
    first = Path(first_audit_dir).resolve(strict=True)
    receipt_raw = _read_original(first / "receipt.json", cap=128 * 1024)
    public_raw = _read_original(first / "public_summary.json", cap=128 * 1024)
    private_raw = _read_original(first / "private_exhibit_review.jsonl", cap=128 * 1024)
    receipt, public = json.loads(receipt_raw), json.loads(public_raw)
    _require(receipt["status"] == public["status"] == FIRST_KIND
             and receipt["files"]["public_summary.json"]["sha256"] == _sha(public_raw)
             and receipt["files"]["private_exhibit_review.jsonl"]["sha256"] == _sha(private_raw)
             and public["source_fingerprints"]["protocol_sha256"] == canonical_hash(config)
             and public["source_or_human_approvals_created"] == 0
             and public["historical_CRSP_CIK_PERMNO_mapping_approved"] is False
             and public["historical_source_known_at_or_vendor_available_at_established"] is False
             and public["IBM_capital_stock_automatically_approved_common_stock"] is False
             and receipt["historical_CRSP_class_approvals"] == 0
             and receipt["human_reviews"] == 0
             and public["model_ready"] is False and public["final_period_opened"] is False
             and receipt["model_ready"] is False and receipt["final_period_opened"] is False,
             "Original IBM exhibit audit no longer preserves research/class approval gates")
    stored = [json.loads(line) for line in private_raw.decode().splitlines()]
    _require(len(stored) == 2
             and {x["accession"] for x in stored}
             == {value["accession"] for value in EXPECTED.values()},
             "Original IBM exhibit source cannot identify both original annual filings")
    counts = {
        "distinct_exhibits_independently_reexamined": 0,
        "capital_stock_single_issued_equity_class_statements": 0,
        "capital_stock_voting_dividend_residual_rights_statements": 0,
        "original_IBM_exchange_listing_statements": 0,
    }
    source = Path(original_dir).resolve(strict=True)
    source_pin = json.loads(_read_original(source_pin_path, cap=128 * 1024))
    pin_hash = _sha(_read_original(source_pin_path, cap=128 * 1024))
    _require(
        pin_hash == public["source_fingerprints"]["original_sec_exhibit_pin_sha256"]
        and source_pin.get("source_approved_for_empirical_model") is False
        and source_pin.get("first_publication_known_at") is None
        and source_pin.get("security_link_known_at") is None
        and set(source_pin.get("filings", {})) == set(EXPECTED),
        "Independent original source pin or historical availability claim changed",
    )
    year_ends = []
    for row in stored:
        selection_year = str(row["selection_year"])
        _require(selection_year in EXPECTED, "Unsupported annual IBM Exhibit 4.1 event")
        spec = EXPECTED[selection_year]
        _require(row["accession"] == spec["accession"]
                 and row["issuer_CIK"] == CIK
                 and row["year_end"] == spec["report_year"]
                 and row["historical_CRSP_class_approved"] is False
                 and row["historical_source_known_at"] is None
                 and row["human_source_review_approved"] is False,
                 "IBM historical security source or accepted year was promoted")
        exhibit_raw = _read_original(source / f'{selection_year}-{spec["exhibit"]}')
        index_raw = _read_original(source / f"{selection_year}-index.json")
        filing_index = _read_original(source / f'{selection_year}-{spec["accession"]}-index.html')
        _require(_sha(exhibit_raw) == row["source_exhibit_sha256"]
                 and _sha(index_raw) == row["index_directory_JSON_sha256"]
                 and _sha(filing_index) == row["index_HTML_sha256"],
                 "Original independently verified SEC exhibit/index bytes changed")
        pinned = source_pin["filings"][selection_year]
        _require(
            pinned["accession"] == spec["accession"]
            and pinned["report_year_end"] == spec["report_year"]
            and pinned["objects"]["exhibit"]["sha256"] == _sha(exhibit_raw)
            and pinned["objects"]["filing_index_html"]["sha256"] == _sha(filing_index)
            and pinned["objects"]["directory_index_json"]["sha256"] == _sha(index_raw),
            "Original SEC Exhibit 4.1 no longer matches independently pinned downloaded bytes",
        )
        # Direct raw HTML strings prove correct original filing package and
        # exact relative indexed exhibit filename; the first audit checks the
        # full HTML row and the current JSON directory entry separately.
        raw_index = filing_index.decode("utf-8", errors="replace")
        raw_relative = (
            "/Archives/edgar/data/51143/"
            + spec["accession"].replace("-", "") + "/" + spec["exhibit"]
        )
        _require(spec["accession"] in raw_index
                 and "EX-4.1" in raw_index
                 and raw_relative in raw_index,
                 "Original official filing index doesn't independently identify IBM EX-4.1")
        parsed_index = json.loads(index_raw)
        files = parsed_index.get("directory", {}).get("item", [])
        _require(any(item.get("name") == spec["exhibit"] for item in files),
                 "SEC directory index no longer identifies the original exhibit")
        values = _independent_extract(exhibit_raw, spec["report_year"])
        earlier = row["exhibit_equity_nature"]
        _require(values["section_sha256"] == earlier["source_section_sha256"]
                 and values["original_html_plaintext_sha256"] ==
                 earlier["exhibit_full_plaintext_sha256"]
                 and values["authorized_stock_shares"] ==
                 earlier["authorized_capital_stock_shares"]
                 and values["issued_capital_stock_shares"] ==
                 earlier["year_end_issued_capital_stock_shares"]
                 and values["outstanding_capital_stock_shares"] ==
                 earlier["year_end_outstanding_capital_stock_shares"],
                 "Independent original-exhibit equity-source values differ from first audit")
        _require(earlier["all_expected_equity_nature_claims_present"] is True
                 and row["exhibit_registered_capital_stock_is_single_equity_class_candidate"] is True,
                 "Prior exhibit silently lost its single-equity-class restrictions")
        counts["distinct_exhibits_independently_reexamined"] += 1
        counts["capital_stock_single_issued_equity_class_statements"] += 1
        counts["capital_stock_voting_dividend_residual_rights_statements"] += 1
        counts["original_IBM_exchange_listing_statements"] += 1
        year_ends.append(spec["report_year"])
    _require(counts["distinct_exhibits_independently_reexamined"] ==
             public["official_SEC_EX_4_1_documents_verified"] == 2,
             "Official IBM source exhibits and published counts disagree")
    final = {
        "schema_version": 1, "status": STATUS,
        "independently_verified_official_exhibit_4_1_documents": 2,
        "report_year_ends": sorted(year_ends),
        "independent_source_equity_section_hashes_and_share_counts_match": True,
        "original_IBM_single_equity_class_and_capital_stock_rights_verified": True,
        "original_SEC_official_filing_index_and_exhibit_document_matches": True,
        "independent_stdlib_HTMLParser_used_instead_of_initial_lxml_parser": True,
        "source_fingerprints": {
            "initial_audit_receipt_sha256": _sha(receipt_raw),
            "first_audit_public_sha256": _sha(public_raw),
            "first_audit_private_exhibit_evidence_sha256": _sha(private_raw),
            "protocol_sha256": canonical_hash(config),
            "original_sec_exhibit_pin_sha256": pin_hash,
        },
        "historical_CRSP_IBM_common_stock_class_approved": False,
        "historical_CIK_PERMNO_effective_intervals_approved": False,
        "earliest_SEC_public_dissemination_established": False,
        "source_known_at_or_available_at_established": False,
        "human_review_completed": False,
        "model_ready": False, "final_period_opened": False,
        "interpretation": (
            "Independent offline HTMLParser reconstruction corroborates original IBM "
            "capital-stock rights and the sole outstanding equity class; this does not "
            "establish effective-dated market identities or time-of-first-availability."
        ),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".independent-ibm-equity-", dir=target.parent) as scratch:
        tmp = Path(scratch) / "independent.json"
        tmp.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n")
        tmp.replace(target)
    return final
