"""Reproduce seven bounded public SEC cover observations from preserved bytes.

This research inspection never reads a vendor record or imports production
extraction code. Its text checks are lexical; they do not confer XBRL validity,
identify a PERMNO, or certify historical availability. Run from the repo root.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

REPORT_SHA256 = "70260a8a1e17dd37a2df0c99cf66a8eefcb1a33608336d3f238c5a42fac997f0"
PROTOCOL_SHA256 = "3951be086ed9a74ec69a304004ebcb5aed63bac161e043ff92ae4f51b8e325d9"

CASES = {
    "0000034088-20-000016": {
        "cover_needles": ["Exxon Mobil Corporation", "Common Stock, without par value", "XOM", "New York Stock Exchange"],
        "finding": "The original New Jersey registrant's cover associates its no-par common stock with XOM and NYSE. The source SGML CIK is 0000034088.",
        "limitation": "No PERMNO, GVKEY, historical CUSIP, or full validity interval is supplied by this cover.",
    },
    "0000034088-21-000012": {
        "cover_needles": ["Exxon Mobil Corporation", "Common Stock, without par value", "XOM", "New York Stock Exchange", "XOM24B"],
        "finding": "The original registrant again identifies XOM common stock. Separate listed notes have distinct symbols; the cover must not be flattened into one undifferentiated security.",
        "limitation": "Agreement with the preceding annual cover is corroboration at two filing observations, not proof of an uninterrupted historical mapping or its availability.",
    },
    "0000040545-21-000011": {
        "cover_needles": ["GENERAL ELECTRIC COMPANY", "Common stock, par value $0.06 per share", "GE", "New York Stock Exchange", "GE 22A"],
        "finding": "GE's February 2021 cover distinguishes its GE common stock from the separately listed debt instruments.",
        "limitation": "The later July 2021 reverse-split notice is separate boundary evidence. This cover does not establish the future CUSIP change or independently recompute returns.",
    },
    "0000320187-20-000047": {
        "cover_needles": ["NIKE, Inc.", "Class B Common Stock", "NKE", "New York Stock Exchange"],
        "finding": "The listed common security on NIKE's 2020 cover is specifically Class B, ticker NKE, on NYSE.",
        "limitation": "A generic common-stock match must preserve Class B. Cover text alone does not identify the corresponding vendor PERMNO or historical selection eligibility.",
    },
    "0001166691-20-000008": {
        "cover_needles": ["COMCAST CORPORATION", "NBCUNIVERSAL MEDIA, LLC", "Class A Common Stock, $0.01 par value", "CMCSA", "NASDAQ Global Select Market", "CCZ", "NBCUniversal Media, LLC – NONE"],
        "finding": "The combined cover assigns the registered instruments to Comcast. Its common security is Class A under CMCSA on NASDAQ; debt has other symbols. NBCUniversal's separate Section 12(b) and 12(g) lines state none.",
        "limitation": "The two original SGML filers remain distinct. NBCUniversal CIK 0000902739 cannot inherit Comcast's CMCSA security merely by sharing this filing. No vendor mapping is approved.",
    },
    "0001403161-20-000070": {
        "cover_needles": ["VISA INC.", "Class A Common Stock, par value $0.0001 per share", "New York Stock Exchange", "Class B common stock", "Class C common stock"],
        "finding": "Visa lists Class A as V on NYSE under Section 12(b). Its Class B and Class C securities are listed separately under Section 12(g); the cover also states that they lack an established public trading market.",
        "limitation": "Classes B and C must not be assigned the listed Class A return series. This supports a class-specific candidate review without establishing a PERMNO or historical known_at.",
    },
    "0001744489-19-000225": {
        "cover_needles": ["Common Stock, $0.01 par value", "DIS", "New York Stock Exchange"],
        "finding": "Disney's first saved 2019 filing under CIK 0001744489 identifies DIS common stock on NYSE.",
        "limitation": "This does not authorize splicing the earlier Disney registrant into a predecessor pair or projecting the new registrant backward before the acquisition/reorganization.",
    },
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def folded(text: str) -> str:
    return " ".join(text.split())


class CoverReader(HTMLParser):
    """A separate reading aid; not a CSS renderer or an XBRL interpreter."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.drop = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "ix:header"}:
            self.drop += 1
        if not self.drop and tag in {"div", "p", "tr", "br", "table", "h1", "h2"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "ix:header"} and self.drop:
            self.drop -= 1
        if not self.drop and tag in {"div", "p", "tr", "br", "table", "h1", "h2"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.drop:
            self.parts.append(data)


def source_bytes(cache: Path, declaration: dict) -> tuple[bytes, dict]:
    stem = digest(declaration["url"].encode())
    raw = (cache / f"{stem}.bin").read_bytes()
    meta_raw = (cache / f"{stem}.json").read_bytes()
    meta = json.loads(meta_raw)
    assert declaration["url"].startswith("https://www.sec.gov/Archives/edgar/data/")
    assert meta["url"] == declaration["url"]
    assert digest(raw) == declaration["sha256"] == meta["sha256"]
    assert digest(meta_raw) == declaration["cache_metadata_sha256"]
    return raw, {
        "url": declaration["url"],
        "sha256": digest(raw),
        "bytes": len(raw),
        "cache_metadata_sha256": digest(meta_raw),
        "original_bytes_reread_for_this_inspection": True,
    }


def main() -> None:
    if not __debug__:
        raise SystemExit("Run without -O or PYTHONOPTIMIZE; integrity assertions must remain enabled.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Choose a new output path; preserved evidence is never overwritten.")
    root = Path.cwd()
    raw_report = gzip.decompress((root / "reports/sec_identity_evidence.json.gz").read_bytes())
    assert digest(raw_report) == REPORT_SHA256
    protocol_raw = (root / "configs/protocol.json").read_bytes()
    protocol_canonical = json.dumps(json.loads(protocol_raw), sort_keys=True, separators=(",", ":")).encode()
    assert digest(protocol_canonical) == PROTOCOL_SHA256
    assert json.loads((root / "configs/protocol.lock.json").read_bytes())["protocol_sha256"] == PROTOCOL_SHA256
    source_report = json.loads(raw_report)
    selected = [r for r in source_report["records"] if r["accession"] in CASES]
    assert len(selected) == len(CASES)
    assert all("2010-01-01" <= r["acceptance_date"] <= "2021-12-31" for r in selected)
    cache = root / "data/raw/sec_cache"
    records = []
    for record in selected:
        case = CASES[record["accession"]]
        primary, primary_check = source_bytes(cache, record["primary_source"])
        header, header_check = source_bytes(cache, record["header_source"])
        reader = CoverReader()
        reader.feed(primary.decode("utf-8"))
        # Covers occur after potentially large hidden inline resource sections.
        # A bounded decoded-text prefix is sufficient for these inspected cases.
        cover = "\n".join(folded(s) for s in "".join(reader.parts).splitlines() if s.strip())[:6500]
        assert all(folded(s).casefold() in folded(cover).casefold() for s in case["cover_needles"])
        if record["accession"] == "0001403161-20-000070":
            assert "no established public trading market" in cover
        if record["accession"] == "0001166691-20-000008":
            assert cover.count("NBCUniversal Media, LLC – NONE") >= 2
        header_text = header.decode("utf-8")
        filer_blocks = re.findall(r"<FILER>\s*(.*?)\s*</FILER>", header_text, flags=re.S)
        filers = []
        for ordinal, block in enumerate(filer_blocks, 1):
            ciks = re.findall(r"<CIK>([^\n]+)", block)
            names = re.findall(r"<CONFORMED-NAME>([^\n]+)", block)
            assert len(ciks) == len(names) == 1
            filers.append({"filer_ordinal": ordinal, "cik": ciks[0].strip(), "name": names[0].strip()})
        assert sum(f["cik"] == record["manifest_cik_raw"] for f in filers) == 1
        clocks = re.findall(r"<ACCEPTANCE-DATETIME>([^\n]+)", header_text)
        assert len(clocks) == 1
        assert record["accession"] in header_text
        selected_facts = [
            {key: fact[key] for key in ["fact_element_ordinal", "element_path", "concept_qname_raw", "contextref_raw", "text_from_parsed_html", "lexical_issues"]}
            for fact in record["cover_evidence"]["facts"]
            if fact["concept_namespace"]["local_name"] in {"EntityCentralIndexKey", "EntityRegistrantName", "Security12bTitle", "Security12gTitle", "TradingSymbol", "SecurityExchangeName"}
        ]
        # These are inherited lexical observations, not interpreted XBRL values.
        records.append({
            "accession": record["accession"],
            "manifest_csv_record": record["manifest_csv_record"],
            "original_filer_cik": record["manifest_cik_raw"],
            "acceptance_date": record["acceptance_date"],
            "raw_sgml_acceptance": clocks[0],
            "primary_source": primary_check,
            "header_source": header_check,
            "independently_observed_sgml_filers": filers,
            "independent_cover_lexical_checks_pass": True,
            "cover_lexical_prefix_characters": len(cover),
            "cover_full_document_visual_review": False,
            "case_finding": case["finding"],
            "case_limit": case["limitation"],
            "inherited_lexical_fact_observations": selected_facts,
            "inherited_referenced_context_observations": record["cover_evidence"]["contexts"],
            "context_observation_scope": "Complete contexts from the frozen lexical report; entity identifiers and dimensions are retained without construing their periods as mapping validity or claiming full XBRL interpretation.",
            "interpreted_xbrl_values_created": False,
            "known_at": None,
            "supported_link_valid_from": None,
            "supported_link_valid_to": None,
            "security_link_created": False,
        })
        assert digest(primary) == primary_check["sha256"]
        assert digest(header) == header_check["sha256"]
    result = {
        "schema_version": 1,
        "status": "BOUNDED_ORIGINAL_SEC_COVER_CORROBORATION_NOT_VENDOR_MAPPING_APPROVAL",
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "execution_script_sha256": digest(Path(__file__).read_bytes()),
        "reviewer": "ChatGPT research assistant",
        "reviewer_type": "assistant",
        "source_report_sha256": REPORT_SHA256,
        "protocol_sha256": PROTOCOL_SHA256,
        "protocol_file_bytes_sha256": digest(protocol_raw),
        "selection_reason": "Identity ambiguities and share-class/source-context examples selected from the existing report, without access to vendor returns or model outcomes.",
        "method": "Separate Python standard-library HTMLParser reading aid and raw-SGML regular expressions; entire source bodies and metadata rehashed against the frozen report. Production identity/extraction helpers were not imported.",
        "scope": "Original filer identity and bounded cover-text corroboration at recorded filing observations; no continuous historical link, vendor mapping or point-in-time availability certification.",
        "records": records,
        "summary": {"filings": len(records), "primary_documents_reread": len(records), "headers_reread": len(records), "filer_observations": sum(len(r["independently_observed_sgml_filers"]) for r in records)},
        "private_vendor_rows_read": False,
        "market_returns_read": False,
        "source_approvals": 0,
        "human_reviews_created": 0,
        "historical_security_links_created": 0,
        "historical_availability_supplied": False,
        "model_ready": False,
        "final_period_opened": False,
        "prior_arithmetic_review_modified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as out:
        json.dump(result, out, indent=2, sort_keys=True)
        out.write("\n")
    print(json.dumps({"output": str(args.output), "sha256": digest(args.output.read_bytes()), "summary": result["summary"]}))


if __name__ == "__main__":
    main()
