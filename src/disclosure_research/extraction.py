"""Conservative Item 1A extraction; ambiguous output remains explicitly flagged."""

import re
from dataclasses import asdict, dataclass

from lxml import html

VERSION = "item1a-v1"
EXTRACTION_VERSION = "item1a-v2-continued-headings"
BLOCKS = {"p", "div", "table", "tr", "td", "th", "h1", "h2", "h3", "h4", "li", "br", "hr"}
START = re.compile(r"(?im)^\s*item\s*1\s*a\s*[.\-:–—]*\s*risk\s+factors\b")
END = re.compile(r"(?im)^\s*item\s*(?:1\s*[bc]|2)\s*[.\-:–—]*\s*"
                 r"(?:unresolved\s+staff\s+comments|cybersecurity|properties)\b")
TOKEN = re.compile(r"\b[a-zA-Z]{2,}\b")
CONTINUED = re.compile(r"[ \t]*(?:\([ \t]*continued[ \t]*\)|[—–:-][ \t]*continued\b|continued\b)",
                       re.I)


def clean_html(raw: bytes | str) -> str:
    root = html.fromstring(raw, parser=html.HTMLParser(remove_comments=True))
    for node in list(root.iter()):
        tag = str(node.tag).split("}")[-1].lower()
        style = re.sub(r"\s", "", node.get("style", "").lower())
        if (tag in {"script", "style", "noscript", "ix:hidden"} or
                tag.endswith(":hidden") or "display:none" in style or "visibility:hidden" in style):
            if node.getparent() is not None:
                node.drop_tree()
    parts = []
    def walk(node):
        tag = str(node.tag).split("}")[-1].lower()
        if tag in BLOCKS:
            parts.append("\n")
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
            if child.tail:
                parts.append(child.tail)
        if tag in BLOCKS:
            parts.append("\n")
    walk(root)
    text = "".join(parts).replace("\xa0", " ").replace("\u200b", "")
    lines = [re.sub(r"[\t \r\f\v]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


@dataclass(frozen=True)
class Extraction:
    status: str
    text: str
    token_count: int
    candidate_count: int
    start_offset: int | None
    end_offset: int | None
    reason: str
    version: str = VERSION

    def as_dict(self):
        return asdict(self)


def extract_risk_factors(raw: bytes | str, min_tokens: int = 200) -> Extraction:
    text = clean_html(raw)
    # A repeated page heading belongs to the section already in progress.
    # Treating it as another candidate previously discarded every page before
    # the final continuation heading. Keep the normalized source unchanged so
    # registered offsets and source hashes remain meaningful.
    all_starts = list(START.finditer(text))
    starts = [match for match in all_starts
              if not CONTINUED.match(text, match.end())]
    version = EXTRACTION_VERSION if len(starts) != len(all_starts) else VERSION
    ends = list(END.finditer(text))
    candidates = []
    for i, start in enumerate(starts):
        next_start = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        end = next((x for x in ends if start.end() < x.start() < next_start), None)
        if end:
            body = text[start.end():end.start()].strip(" .:-\n")
            candidates.append((len(TOKEN.findall(body)), start.end(), end.start(), body))
    if not candidates:
        return Extraction("missing", "", 0, 0, None, None,
                          "No bounded Item 1A section; requires manual inspection", version)
    count, start, end, body = max(candidates)
    long_count = sum(x[0] >= min_tokens for x in candidates)
    status = "ok" if count >= min_tokens and long_count == 1 else "review"
    reason = "Unique substantive bounded section" if status == "ok" else "Short or ambiguous section"
    return Extraction(status, body, count, len(candidates), start, end, reason, version)


def pair_filings(records: list[dict], start_year: int, end_year: int) -> tuple[list[dict], list[dict]]:
    """Pair chronology first; never skip a failed prior extraction to reach older text."""
    groups = {}
    for record in records:
        groups.setdefault(record["cik"], []).append(record)
    pairs, excluded = [], []
    for cik, group in groups.items():
        group.sort(key=lambda r: (r["acceptance_date"], r["accessionNumber"]))
        for i, current in enumerate(group):
            if not start_year <= int(current["acceptance_date"][:4]) <= end_year:
                continue
            reason = None
            previous = group[i - 1] if i else None
            if previous is None:
                reason = "missing_previous_original_filing"
            elif current["extraction_status"] != "ok" or previous["extraction_status"] != "ok":
                reason = "current_or_previous_extraction_requires_review"
            elif current.get("reportDate") == previous.get("reportDate"):
                reason = "duplicate_report_period"
            elif not current.get("reportDate") or not previous.get("reportDate"):
                reason = "missing_report_period"
            else:
                from datetime import date
                gap = (date.fromisoformat(current["reportDate"]) -
                       date.fromisoformat(previous["reportDate"])).days
                if not 300 <= gap <= 430:
                    reason = "nonannual_or_missing_report_period"
            if reason:
                excluded.append({"cik": cik, "accession": current["accessionNumber"], "reason": reason})
                continue
            pairs.append({"cik": cik, "accession": current["accessionNumber"],
                          "previous_accession": previous["accessionNumber"],
                          "acceptance_date": current["acceptance_date"],
                          "previous_acceptance_date": previous["acceptance_date"],
                          "current_text": current["risk_text"], "previous_text": previous["risk_text"],
                          "reference_session": current["reference_session"],
                          "label_end": current["label_end"],
                          "source_url": current["source_url"],
                          "previous_source_url": previous["source_url"],
                          "risk_source_url": current.get("risk_source_url", current["source_url"]),
                          "previous_risk_source_url": previous.get("risk_source_url", previous["source_url"]),
                          "resolution_method": current.get("resolution_method", "numbered_item1a"),
                          "previous_resolution_method": previous.get("resolution_method", "numbered_item1a"),
                          "resolution_method_changed": current.get("resolution_method", "numbered_item1a") !=
                          previous.get("resolution_method", "numbered_item1a")})
    return pairs, excluded
