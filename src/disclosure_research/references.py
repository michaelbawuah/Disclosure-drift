"""Explicit, source-hash-bound resolutions for reviewed document-format cases.

Rules are reproducible extraction instructions, not human research sign-off.
Unknown layouts continue through the conservative numbered-section parser.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from lxml import html

from .extraction import END, START, VERSION, TOKEN, Extraction, clean_html, extract_risk_factors

RESOLUTION_VERSION = "reference-range-v1"
KINDS = {"same_document_range", "same_accession_exhibit_range",
         "same_document_repeated_heading_range", "same_document_labeled_risk_range",
         "same_document_indexed_risk_range"}


def sha256(value: bytes | str) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def load_reference_rules(path: str | Path | None) -> dict:
    if path is None:
        return {}
    document = json.loads(Path(path).read_text())
    if document.get("schema_version") != 1 or document.get("normalizer_version") != VERSION:
        raise ValueError("Unsupported reference-rule schema or normalizer version")
    rules = {}
    for rule in document["rules"]:
        accession = rule["accession"]
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession) or accession in rules:
            raise ValueError("Reference rules require unique valid accessions")
        if rule["kind"] not in KINDS:
            raise ValueError("Unsupported reference-resolution kind")
        for key in ["primary_sha256", "primary_reference_sha256", "source_sha256", "text_sha256"]:
            if not re.fullmatch(r"[0-9a-f]{64}", rule[key]):
                raise ValueError(f"Invalid {key} in reference rule")
        for key in ["start_offset", "end_offset", "token_count"]:
            if type(rule[key]) is not int or rule[key] < 0:
                raise ValueError(f"Invalid {key} in reference rule")
        if rule["start_offset"] >= rule["end_offset"] or rule["token_count"] < 200:
            raise ValueError("Reference rule must bound a substantive section")
        if rule["kind"] == "same_accession_exhibit_range":
            if not re.fullmatch(r"[0-9a-f]{64}", rule["index_sha256"]):
                raise ValueError("Invalid exhibit-index hash")
        if not rule.get("boundary_notes", "").strip():
            raise ValueError("Reference rules require boundary notes")
        rules[accession] = rule
    return rules


@dataclass(frozen=True)
class ResolvedSection:
    extraction: Extraction
    source_url: str
    source_sha256: str
    method: str = "numbered_item1a"
    rule_id: str = ""
    index_url: str = ""
    index_sha256: str = ""
    normalized_source: str | None = None

    def provenance(self) -> dict:
        return {"risk_source_url": self.source_url, "risk_source_sha256": self.source_sha256,
                "resolution_method": self.method, "resolution_rule_id": self.rule_id,
                "resolution_index_url": self.index_url, "resolution_index_sha256": self.index_sha256,
                "extraction_start": self.extraction.start_offset,
                "extraction_end": self.extraction.end_offset, "normalizer_version": VERSION}


def _filing_directory(primary_url: str, accession: str) -> str:
    parsed = urlsplit(primary_url)
    match = re.fullmatch(r"/Archives/edgar/data/\d+/(\d{18})/[\w.-]+\.html?", parsed.path)
    if (parsed.scheme != "https" or parsed.netloc != "www.sec.gov" or parsed.query or
            parsed.fragment or not match or match[1] != accession.replace("-", "")):
        raise ValueError("Reference resolution requires the original SEC accession directory")
    return primary_url.rsplit("/", 1)[0] + "/"


def _verify_exhibit(index: bytes, index_url: str, source_url: str) -> None:
    matches = []
    for row in html.fromstring(index).xpath("//tr"):
        cells = row.xpath("./td")
        # SEC document-format table: sequence, description, document, type, size.
        if len(cells) < 4:
            continue
        kind = " ".join(cells[3].text_content().split()).upper()
        for anchor in cells[2].xpath(".//a[@href]"):
            if urljoin(index_url, anchor.get("href")) == source_url:
                matches.append(kind)
    if len(matches) != 1 or not re.fullmatch(r"EX-99(?:\.\d+)?", matches[0]):
        raise ValueError("Referenced source is not a unique EX-99 document in the original filing index")


def resolve_section(raw: bytes, primary_url: str, accession: str, rules: dict,
                    fetch=None) -> ResolvedSection:
    initial = extract_risk_factors(raw)
    original_hash = sha256(raw)
    rule = rules.get(accession)
    if rule is None:
        return ResolvedSection(initial, primary_url, original_hash)
    if primary_url != rule["primary_url"] or original_hash != rule["primary_sha256"]:
        raise ValueError("Primary source differs from the registered reference rule")
    if initial.status == "ok" or sha256(initial.text) != rule["primary_reference_sha256"]:
        raise ValueError("Numbered Item 1A reference differs from the registered evidence")
    directory = _filing_directory(primary_url, accession)
    source_url, index_url, index_hash = rule["source_url"], "", ""
    if rule["kind"] in {"same_document_repeated_heading_range", "same_document_labeled_risk_range",
                         "same_document_indexed_risk_range"}:
        if source_url != primary_url:
            raise ValueError("Registered same-document boundaries cannot change the risk source")
        if rule["kind"] == "same_document_labeled_risk_range" and not re.search(
                r"\bpages?\s+\d+(?:\s*[,–—-]\s*\d+)+", initial.text, re.I):
            raise ValueError("Labeled risk range requires an explicit Item 1A page reference")
        if rule["kind"] == "same_document_indexed_risk_range" and not re.fullmatch(
                r"[1-9]\d*", initial.text):
            raise ValueError("Indexed risk range requires a single-page Item 1A index reference")
        source = raw
    elif rule["kind"] == "same_document_range":
        if source_url != primary_url or not re.fullmatch(
                r"(?:Pages?\s*)?\d+\s*[-–—]\s*\d+", initial.text, re.I):
            raise ValueError("Same-document resolution requires the original Item 1A page reference")
        source = raw
    else:
        if not re.search(r"\bexhibit\s+99\b", initial.text, re.I):
            raise ValueError("Item 1A does not refer to Exhibit 99")
        filename = source_url.removeprefix(directory)
        if (not source_url.startswith(directory) or
                not re.fullmatch(r"[\w.-]+\.html?", filename) or source_url == primary_url):
            raise ValueError("Exhibit must be an HTML document in the original accession directory")
        index_url = directory + accession + "-index.html"
        if rule["index_url"] != index_url or fetch is None:
            raise ValueError("Original filing index and a verified fetcher are required")
        index, _ = fetch(index_url)
        index_hash = sha256(index)
        if index_hash != rule["index_sha256"]:
            raise ValueError("Original filing index differs from the registered source")
        _verify_exhibit(index, index_url, source_url)
        source, _ = fetch(source_url)
    source_hash = sha256(source)
    if source_hash != rule["source_sha256"]:
        raise ValueError("Risk source differs from the registered reference rule")
    normalized = clean_html(source)
    start, end = rule["start_offset"], rule["end_offset"]
    if not 0 <= start < end <= len(normalized):
        raise ValueError("Reference range is outside the normalized source")
    if rule["kind"] == "same_document_repeated_heading_range":
        starts, ends = list(START.finditer(normalized)), list(END.finditer(normalized))
        if (not any(match.end() == start for match in starts)
                or sum(start < match.start() < end for match in starts) < 1
                or not any(match.start() == end for match in ends)
                or any(start < match.start() < end for match in ends)):
            raise ValueError("Repeated-heading range must join Item 1A pages up to the first Item 1B/2")
    elif rule["kind"] in {"same_document_labeled_risk_range", "same_document_indexed_risk_range"}:
        starts = list(re.finditer(r"(?im)^[ \t]*risk factors[ \t]*$", normalized))
        end_label = (r"quantitative and qualitative disclosures about market risks"
                     if rule["kind"] == "same_document_indexed_risk_range" else
                     r"(?:legal proceedings|properties|unresolved staff comments)")
        ends = list(re.finditer(r"(?im)^[ \t]*" + end_label + r"[ \t]*$", normalized))
        if (not any(match.end() == start for match in starts)
                or not any(match.start() == end for match in ends)
                or any(start < match.start() < end for match in ends)):
            raise ValueError("Labeled risk range must bound the complete Risk Factors section")
    text = normalized[start:end].strip(" .:-\n")
    count = len(TOKEN.findall(text))
    if count != rule["token_count"] or sha256(text) != rule["text_sha256"]:
        raise ValueError("Resolved text differs from the registered boundary evidence")
    result = Extraction("ok", text, count, 1, start, end,
                        "Hash-bound reference range; human boundary review pending", RESOLUTION_VERSION)
    return ResolvedSection(result, source_url, source_hash, rule["kind"],
                           sha256(json.dumps(rule, sort_keys=True)), index_url, index_hash, normalized)
