"""Offline original SEC identity/cover evidence, without security-link inference.

Inline HTML is parsed for lexical evidence only. Serialized fragments and element
ordinals describe that parsed tree; they are not exact source bytes or byte offsets.
No XBRL transformation, continuation, taxonomy or fact-value semantics is applied.
"""

import csv
import hashlib
import io
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from lxml import etree, html

from .audit import cached_body
from .manual_wrds_identity_candidates import SEC_FIELDS, _integer_key
from .manual_wrds_intake import _fd_identity, _hash, _identity, _iso
from .protocol import canonical_hash, verify_lock
from .timing import acceptance_from_header
from .universe import aware_timestamp

STATUS = "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED"
VERSION = "sec-identity-lexical-v1"
TARGETS = frozenset({"EntityCentralIndexKey", "EntityRegistrantName", "Security12bTitle",
                     "Security12gTitle", "TradingSymbol", "SecurityExchangeName"})
_SHA = re.compile(r"[0-9a-f]{64}")
_QNAME = re.compile(r"(?:[A-Za-z_][A-Za-z_0-9.-]*:)?[A-Za-z_][A-Za-z_0-9.-]*")
_IX = {"http://www.xbrl.org/2008/inlineXBRL", "http://www.xbrl.org/2013/inlineXBRL"}
_XBRLI = "http://www.xbrl.org/2003/instance"
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_MAX_FILINGS = 1000
_MAX_BODY_BYTES = 40 * 1024 * 1024
_MAX_HEADER_BYTES = 1024 * 1024
_MAX_METADATA_BYTES = 64 * 1024
_MAX_TEXT = 32 * 1024
_MAX_FACTS = 4096
_MAX_CONTEXTS = 4096
_MAX_DOCUMENT_EVIDENCE_BYTES = 8 * 1024 * 1024
_MAX_REPORT_BYTES = 64 * 1024 * 1024


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _small_text(value):
    if len(value) > _MAX_TEXT:
        raise ValueError("SEC lexical evidence exceeds the per-value text budget")
    return value


def _sgml_values(text, tag):
    return [_small_text(value) for value in re.findall(r"<" + tag + r">([^<\r\n]*)", text, flags=re.I)]


def header_identity(raw, *, expected_cik, expected_accession):
    """Retain every FILER; only one valid matching CIK may establish consistency.

    SGML tag-value boundary whitespace is stripped for comparisons, while raw
    captured values remain in the evidence. Other valid filers are context.
    Acceptance-clock checks are separate so existing review gates do not change.
    """
    if len(raw) > _MAX_HEADER_BYTES:
        raise ValueError("SEC header exceeds the bounded source size")
    text = raw.decode("utf-8")
    expected, kind = _integer_key(expected_cik, cik=True)
    if kind != "positive_ascii_integer":
        raise ValueError("Expected original filer CIK is unsupported")
    blocks = re.findall(r"<FILER>(.*?)</FILER>", text, flags=re.I | re.S)
    issues, filers = [], []
    if (not 1 <= len(blocks) <= 256 or len(re.findall(r"<FILER>", text, re.I)) != len(blocks)
            or len(re.findall(r"</FILER>", text, re.I)) != len(blocks)):
        issues.append("missing_or_malformed_filer_blocks")
    for ordinal, block in enumerate(blocks, 1):
        companies = re.findall(r"<COMPANY-DATA>(.*?)</COMPANY-DATA>", block, flags=re.I | re.S)
        ciks = [value for company in companies for value in _sgml_values(company, "CIK")]
        names = [value for company in companies for value in _sgml_values(company, "CONFORMED-NAME")]
        key, grammar = _integer_key(ciks[0].strip(), cik=True) if len(ciks) == 1 else (None, "ambiguous")
        consistent = (len(companies) == 1
                      and len(re.findall(r"<COMPANY-DATA>", block, re.I)) == 1
                      and len(re.findall(r"</COMPANY-DATA>", block, re.I)) == 1
                      and len(ciks) == len(names) == 1
                      and grammar == "positive_ascii_integer" and bool(names[0].strip()))
        if not consistent:
            issues.append("unresolved_filer_company_identity")
        filers.append({"filer_ordinal": ordinal, "company_data_count": len(companies),
                       "cik_raw_values": ciks, "conformed_name_raw_values": names,
                       "cik_comparison_key": key, "cik_grammar": grammar,
                       "filer_fields_unambiguous": consistent,
                       "matches_manifest_cik": consistent and key == expected})
    accessions, forms = _sgml_values(text, "ACCESSION-NUMBER"), _sgml_values(text, "TYPE")
    if len(accessions) != 1 or accessions[0].strip() != expected_accession:
        issues.append("header_accession_missing_ambiguous_or_different")
    if len(forms) != 1 or forms[0].strip() != "10-K":
        issues.append("header_form_missing_ambiguous_or_not_original_10k")
    matching = [row for row in filers if row["matches_manifest_cik"]]
    if len(matching) != 1:
        issues.append("manifest_cik_requires_exactly_one_matching_filer")
    return {"accession_raw_values": accessions, "form_raw_values": forms, "filers": filers,
            "filer_count": len(filers), "matching_filer_count": len(matching),
            "header_identity_consistent": not issues, "issues": sorted(set(issues))}


def _clock(raw, expected_timestamp, expected_date):
    text = raw.decode("utf-8")
    values = _sgml_values(text, "ACCEPTANCE-DATETIME")
    if len(values) != 1 or not re.fullmatch(r"[0-9]{14}", values[0].strip()):
        raise ValueError("SEC header requires exactly one complete acceptance clock")
    accepted = acceptance_from_header(text)
    expected = aware_timestamp(expected_timestamp, "Manifest acceptance timestamp")
    if accepted != expected or accepted.date().isoformat() != expected_date:
        raise ValueError("Original SEC acceptance clock disagrees with the manifest")
    return {"raw_acceptance_datetime": values[0], "interpreted_acceptance_timestamp": accepted.isoformat(),
            "manifest_timestamp_raw": expected_timestamp, "comparison": "same_aware_instant_and_New_York_date",
            "matches_manifest": True, "public_dissemination_verified": False}


def _namespace(node, qname):
    """QName declaration evidence from the parsed HTML, never taxonomy validation."""
    result = {"qname_raw": qname, "prefix": None, "local_name": None, "namespace_uri": None,
              "declaration_element_path": None, "status": "MISSING_OR_UNSUPPORTED_QNAME"}
    if not isinstance(qname, str) or not _QNAME.fullmatch(qname):
        return result
    prefix, local = qname.split(":", 1) if ":" in qname else ("", qname)
    result.update(prefix=prefix, local_name=local)
    # HTML parsing lowercases attribute names, including xmlns prefixes. Do not
    # silently turn an uppercase XML prefix into an established namespace.
    if prefix != prefix.lower():
        result["status"] = "PREFIX_CASE_UNRESOLVED_BY_HTML_PARSER"
        return result
    attribute = "xmlns:" + prefix if prefix else "xmlns"
    for ancestor in [node, *node.iterancestors()]:
        if attribute in ancestor.attrib:
            result.update(namespace_uri=_small_text(ancestor.attrib[attribute]),
                          declaration_element_path=ancestor.getroottree().getpath(ancestor),
                          status="DECLARATION_FOUND_IN_PARSED_HTML")
            return result
    result["status"] = "NAMESPACE_DECLARATION_MISSING"
    return result


def _local(node):
    return node.tag.split(":")[-1].lower() if isinstance(node.tag, str) else ""


def _text(node):
    # Includes descendant/excluded text as lexical evidence. This is deliberately
    # not an Inline XBRL fact-value algorithm or a source-byte reconstruction.
    return _small_text("".join(node.itertext()))


def _fragment(node):
    return _small_text(etree.tostring(node, encoding="unicode", method="html", with_tail=False))


def _context(node, ordinal):
    identifiers, periods, dimensions = [], [], []
    for child in node.iter():
        local = _local(child)
        if local == "identifier":
            identifiers.append({"scheme_raw": child.get("scheme"), "text_from_parsed_html": _text(child),
                                "element_namespace": _namespace(child, child.tag)})
        elif local in {"startdate", "enddate", "instant", "forever"}:
            periods.append({"kind": local, "text_from_parsed_html": _text(child),
                            "element_namespace": _namespace(child, child.tag)})
        elif local in {"explicitmember", "typedmember"}:
            text = _text(child)
            dimensions.append({"kind": local, "dimension_qname_raw": child.get("dimension"),
                               "dimension_namespace": _namespace(child, child.get("dimension")),
                               "text_from_parsed_html": text,
                               "member_namespace": _namespace(child, text) if local == "explicitmember" else None,
                               "serialized_parsed_html": _fragment(child),
                               "element_namespace": _namespace(child, child.tag)})
    fragment = _fragment(node)
    namespace = _namespace(node, node.tag)
    return {"context_element_ordinal": ordinal, "context_id_raw": node.get("id"),
            "element_path": node.getroottree().getpath(node), "element_namespace": namespace,
            "recognized_context_namespace": namespace["namespace_uri"] == _XBRLI,
            "entity_identifiers": identifiers, "period_components": periods, "dimensions": dimensions,
            "serialized_parsed_html": fragment,
            "parsed_serialization_sha256": hashlib.sha256(fragment.encode()).hexdigest(),
            "serialization_is_original_source_bytes": False, "context_period_is_link_validity": False}


def cover_evidence(raw):
    """Collect bounded lexical facts and referenced contexts, retaining ambiguity."""
    if len(raw) > _MAX_BODY_BYTES:
        raise ValueError("SEC primary document exceeds the bounded source size")
    parser = html.HTMLParser(no_network=True, recover=True, huge_tree=False, remove_comments=False)
    try:
        tree = html.fromstring(raw, parser=parser)
    except (etree.ParserError, etree.XMLSyntaxError):
        return {"status": "HTML_PARSE_UNRESOLVED", "facts": [], "contexts": [],
                "facts_by_local_name": {}, "parser_diagnostic_counts": {}, "lexical_issues": ["html_parse_unresolved"]}
    selected, context_nodes = [], {}
    for ordinal, node in enumerate(tree.iter(), 1):
        local = _local(node)
        if local == "context":
            context_nodes.setdefault(node.get("id"), []).append((ordinal, node))
        name = node.get("name", "") if isinstance(node.tag, str) else ""
        if local in {"nonnumeric", "nonfraction"} and name.split(":")[-1] in TARGETS:
            selected.append((ordinal, node))
            if len(selected) > _MAX_FACTS:
                raise ValueError("SEC document exceeds the bounded cover-fact count")
    facts, contexts, context_keys, issues, counts = [], [], {}, Counter(), Counter()
    for ordinal, node in selected:
        name, reference = node.get("name"), node.get("contextref")
        concept, inline = _namespace(node, name), _namespace(node, node.tag)
        matches = context_nodes.get(reference, []) if reference else []
        fact_issues = []
        if inline["namespace_uri"] not in _IX:
            fact_issues.append("inline_namespace_unrecognized_or_unresolved")
        uri = concept["namespace_uri"]
        if uri is None or re.fullmatch(r"https?://xbrl\.sec\.gov/dei/[0-9]{4}-[0-9]{2}-[0-9]{2}", uri) is None:
            fact_issues.append("dei_namespace_unrecognized_or_unresolved")
        if not reference:
            fact_issues.append("contextref_missing")
        elif not matches:
            fact_issues.append("referenced_context_missing")
        elif len(matches) > 1:
            fact_issues.append("referenced_context_id_ambiguous")
        for context_ordinal, context in matches:
            if context_ordinal not in context_keys:
                if len(contexts) >= _MAX_CONTEXTS:
                    raise ValueError("SEC document exceeds the bounded referenced-context count")
                record = _context(context, context_ordinal)
                contexts.append(record)
                context_keys[context_ordinal] = record
            if not context_keys[context_ordinal]["recognized_context_namespace"]:
                fact_issues.append("context_namespace_unrecognized_or_unresolved")
        descendants, ancestors = list(node.iter()), list(node.iterancestors())
        hidden = any(_local(parent) == "hidden" for parent in ancestors)
        hidden_styles = any(re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)",
                                     parent.get("style", ""), re.I) for parent in [node, *ancestors])
        excluded = any(_local(child) == "exclude" for child in descendants)
        continuation, formatting = node.get("continuedat"), node.get("format")
        nil = [(key, value) for key, value in node.attrib.items() if key.split(":")[-1].lower() == "nil"]
        if continuation is not None:
            fact_issues.append("continuation_not_interpreted")
        if formatting is not None:
            fact_issues.append("format_transformation_not_interpreted")
        if nil:
            fact_issues.append("nil_attribute_not_interpreted")
        if excluded:
            fact_issues.append("exclude_content_not_interpreted")
        if _local(node) != "nonnumeric":
            fact_issues.append("unexpected_numeric_element_for_selected_cover_concept")
        fragment = _fragment(node)
        facts.append({"fact_element_ordinal": ordinal, "element_path": node.getroottree().getpath(node),
                      "fact_id_raw": node.get("id"), "concept_qname_raw": name,
                      "concept_namespace": concept, "inline_element_namespace": inline,
                      "contextref_raw": reference, "context_element_ordinals": [value[0] for value in matches],
                      "text_from_parsed_html": _text(node), "serialized_parsed_html": fragment,
                      "parsed_serialization_sha256": hashlib.sha256(fragment.encode()).hexdigest(),
                      "serialization_is_original_source_bytes": False,
                      "format_raw": formatting, "format_namespace": _namespace(node, formatting),
                      "nil_attributes_raw": [list(value) for value in nil], "continuedat_raw": continuation,
                      "inside_hidden_element": hidden, "hidden_by_inline_style_observed": hidden_styles,
                      "contains_exclude_element": excluded, "lexical_issues": sorted(set(fact_issues)),
                      "interpreted_xbrl_value": None, "security_link_created": False})
        counts[name.split(":")[-1]] += 1
        issues.update(set(fact_issues))
    result = {"status": "LEXICAL_COVER_FACTS_RETAINED" if facts else "NO_SUPPORTED_INLINE_COVER_FACTS",
              "facts": facts, "contexts": sorted(contexts, key=lambda row: row["context_element_ordinal"]),
              "facts_by_local_name": dict(sorted(counts.items())),
              "parser_diagnostic_counts": dict(sorted(Counter(e.level_name for e in parser.error_log).items())),
              "lexical_issue_counts": dict(sorted(issues.items())),
              "parser": "lxml.html recovered lexical tree; not a validating XBRL processor",
              "full_xbrl_validity_claimed": False, "cross_context_security_assembly_performed": False}
    if len(_json_bytes(result)) > _MAX_DOCUMENT_EVIDENCE_BYTES:
        raise ValueError("SEC document exceeds the bounded lexical-evidence size")
    return result


def _regular(path, maximum):
    if path.is_symlink() or not path.is_file():
        raise ValueError("SEC source binding requires a regular nonsymlink file")
    identity = _identity(path)
    if identity[2] > maximum:
        raise ValueError("SEC source or metadata exceeds its bounded size")
    return identity


class _BoundedFile:
    """The read methods used by cached_body, with a hard allocation limit."""

    def __init__(self, path, identity, maximum):
        self.path, self.identity, self.maximum = path, identity, maximum

    def read_bytes(self):
        with self.path.open("rb") as handle:
            if _fd_identity(handle) != self.identity:
                raise ValueError("SEC file changed before its bounded read")
            raw = handle.read(self.maximum + 1)
            if len(raw) > self.maximum:
                raise ValueError("SEC file grew beyond its bounded read size")
            if _fd_identity(handle) != self.identity or _identity(self.path) != self.identity:
                raise ValueError("SEC file changed during its bounded read")
        return raw

    def read_text(self):
        return self.read_bytes().decode("utf-8")


class _BoundedCache:
    """Provide only the two declared cache files to the existing byte checker."""

    def __init__(self, files):
        self.files = files

    def __truediv__(self, name):
        if name not in self.files:
            raise ValueError("SEC checker requested an undeclared cache file")
        return self.files[name]


def _manifest(path, expected_sha, config):
    if not isinstance(expected_sha, str) or not _SHA.fullmatch(expected_sha):
        raise ValueError("A pinned manifest SHA-256 is required")
    path = Path(path).absolute()
    identity = _regular(path, _MAX_MANIFEST_BYTES)
    raw = _BoundedFile(path, identity, _MAX_MANIFEST_BYTES).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha or _identity(path) != identity:
        raise ValueError("SEC manifest bytes disagree with the required SHA-256 pin")
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    if tuple(next(reader, [])) != SEC_FIELDS:
        raise ValueError("SEC manifest must use the supported original filing-source schema")
    rows, accessions = [], set()
    for ordinal, values in enumerate(reader, 2):
        if len(values) != len(SEC_FIELDS) or len(rows) >= _MAX_FILINGS:
            raise ValueError("SEC manifest record width or count is unsupported")
        row = dict(zip(SEC_FIELDS, values, strict=True))
        day = _iso(row["acceptance_date"], "Manifest acceptance date")
        if not config["initial_train_start"] <= int(day[:4]) <= config["development_end"]:
            raise ValueError("SEC identity evidence accepts development filings only; final period blocked")
        stamp = aware_timestamp(row["acceptance_timestamp"], "Manifest acceptance timestamp")
        if stamp.tz_convert("America/New_York").date().isoformat() != day:
            raise ValueError("Manifest date and acceptance timestamp disagree")
        _iso(row["reportDate"], "Manifest report date")
        if (_integer_key(row["cik"], cik=True)[1] != "positive_ascii_integer"
                or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", row["accessionNumber"])
                or row["accessionNumber"] in accessions):
            raise ValueError("SEC manifest identity is malformed or repeats an accession")
        for name in ("source_url", "header_url"):
            url = urlsplit(row[name])
            if (url.scheme != "https" or url.hostname != "www.sec.gov" or url.username or url.password
                    or url.port is not None or url.query or url.fragment
                    or not url.path.startswith("/Archives/edgar/data/")):
                raise ValueError("SEC identity evidence requires original official archive URLs")
        if any(not _SHA.fullmatch(row[name]) for name in ("download_sha256", "header_sha256")):
            raise ValueError("SEC original sources require recorded SHA-256 values")
        rows.append({**row, "manifest_csv_record": ordinal})
        accessions.add(row["accessionNumber"])
    if not rows:
        raise ValueError("SEC source evidence requires at least one manifest filing")
    return rows, (path, identity, expected_sha)


def _body(cache, url, expected, guards, maximum):
    key = hashlib.sha256(url.encode()).hexdigest()
    body_path, meta_path = cache / f"{key}.bin", cache / f"{key}.json"
    body_identity = _regular(body_path, maximum)
    metadata_identity = _regular(meta_path, _MAX_METADATA_BYTES)
    files = {body_path.name: _BoundedFile(body_path, body_identity, maximum),
             meta_path.name: _BoundedFile(meta_path, metadata_identity, _MAX_METADATA_BYTES)}
    metadata_hash = hashlib.sha256(files[meta_path.name].read_bytes()).hexdigest()
    raw = cached_body(_BoundedCache(files), url, expected)
    if (_identity(body_path) != body_identity or _identity(meta_path) != metadata_identity
            or _hash(meta_path) != metadata_hash):
        raise ValueError("SEC cache entry changed during source verification")
    for path, identity, digest in ((body_path, body_identity, expected), (meta_path, metadata_identity, metadata_hash)):
        binding = (identity, digest)
        if path in guards and guards[path] != binding:
            raise ValueError("SEC source changed between bound reads")
        guards[path] = binding
    return raw, {"url": url, "sha256": expected, "bytes": len(raw),
                 "cache_metadata_sha256": metadata_hash, "original_bytes_reverified": True}


def _guard(guards):
    for path, (identity, digest) in guards.items():
        if (path.is_symlink() or _identity(path) != identity or _hash(path) != digest
                or _identity(path) != identity):
            raise ValueError("SEC input bytes or identity changed during evidence construction")


def build_sec_identity_evidence(manifest, *, manifest_sha256, cache, config, repo_root="."):
    """Return deterministic, public original-source evidence; write no artifact."""
    verify_lock(config, Path(repo_root) / "configs/protocol.lock.json")
    if (config["initial_train_start"], config["development_end"], config["holdout_start"]) != (2010, 2021, 2022):
        raise ValueError("SEC evidence requires the frozen development envelope")
    rows, binding = _manifest(manifest, manifest_sha256, config)
    guards = {binding[0]: (binding[1], binding[2])}
    cache = Path(cache).resolve(strict=True)
    records, statuses, fact_presence, fact_counts, total_bytes = [], Counter(), Counter(), Counter(), 0
    for row in rows:
        raw, primary = _body(cache, row["source_url"], row["download_sha256"], guards, _MAX_BODY_BYTES)
        header, header_source = _body(cache, row["header_url"], row["header_sha256"], guards, _MAX_HEADER_BYTES)
        identity = header_identity(header, expected_cik=row["cik"], expected_accession=row["accessionNumber"])
        if not identity["header_identity_consistent"]:
            raise ValueError("SEC header identity does not uniquely corroborate the original manifest filer")
        clock = _clock(header, row["acceptance_timestamp"], row["acceptance_date"])
        cover = cover_evidence(raw)
        record = {"manifest_csv_record": row["manifest_csv_record"], "accession": row["accessionNumber"],
                  "manifest_cik_raw": row["cik"], "manifest_name": row["name"],
                  "acceptance_date": row["acceptance_date"], "recorded_acceptance_timestamp": row["acceptance_timestamp"],
                  "primary_source": primary, "header_source": header_source,
                  "header_identity": identity, "acceptance_clock": clock, "cover_evidence": cover,
                  "known_at": None, "available_at": None, "security_link_created": False}
        total_bytes += len(_json_bytes(record))
        if total_bytes > _MAX_REPORT_BYTES:
            raise ValueError("SEC evidence exceeds the bounded report size")
        records.append(record)
        statuses[cover["status"]] += 1
        fact_presence.update(cover["facts_by_local_name"].keys())
        fact_counts.update(cover["facts_by_local_name"])
    _guard(guards)
    report = {"schema_version": 1, "status": STATUS, "extractor_version": VERSION,
              "extractor_code_sha256": _hash(Path(__file__)), "protocol_sha256": canonical_hash(config),
              "parser_versions": {"lxml": ".".join(map(str, etree.LXML_VERSION)),
                                  "libxml2": ".".join(map(str, etree.LIBXML_VERSION))},
              "manifest_sha256": manifest_sha256,
              "manifest_schema": list(SEC_FIELDS), "records": records,
              "summary": {"filings": len(records), "original_primary_sources_verified": len(records),
                          "original_headers_verified": len(records), "unique_manifest_filer_matches": len(records),
                          "header_filer_observations": sum(r["header_identity"]["filer_count"] for r in records),
                          "filings_with_multiple_filers": sum(r["header_identity"]["filer_count"] > 1 for r in records),
                          "acceptance_clocks_matching_manifest": len(records),
                          "cover_status_counts": dict(sorted(statuses.items())),
                          "fact_presence_by_filing": dict(sorted(fact_presence.items())),
                          "fact_occurrence_counts": dict(sorted(fact_counts.items())),
                          "facts_in_hidden_elements": sum(f["inside_hidden_element"] for r in records for f in r["cover_evidence"]["facts"]),
                          "facts_with_lexical_issues": sum(bool(f["lexical_issues"]) for r in records for f in r["cover_evidence"]["facts"])},
              "policies": {"inline_html_evidence": "lexical text and normalized parsed-tree serialization; never exact source-byte fragments or offsets",
                           "namespace_scope": "declarations observed in parsed HTML; no taxonomy validation",
                           "xbrl_value_semantics": "transformations, nil, exclusions and continuations are retained but not interpreted",
                           "class_scope": "all fact/context occurrences retained; no cross-context title/ticker/exchange assembly",
                           "period_scope": "context periods are source metadata, not security-link validity or availability",
                           "source_scope": "primary filing and SGML header only; risk-source extraction is not rerun",
                           "prior_manifest_only_packet_modified": False},
              "original_sec_bytes_reread": True, "public_dissemination_verified": False,
              "full_filing_bodies_in_report": False, "xbrl_fact_values_interpreted": False,
              "historical_security_links_created": 0, "source_approvals": 0, "human_reviews_created": 0,
              "prior_arithmetic_review_modified": False, "model_ready": False, "final_period_opened": False}
    if len(_json_bytes(report)) > _MAX_REPORT_BYTES:
        raise ValueError("SEC evidence exceeds the bounded final report size")
    return report


def write_report(report, output):
    """Write the complete deterministic public report atomically without overwrite."""
    path = Path(output).absolute()
    if path.exists() or path.is_symlink() or path.suffix.lower() != ".json":
        raise ValueError("SEC report requires a new JSON output file")
    raw = _json_bytes(report)
    if len(raw) > _MAX_REPORT_BYTES:
        raise ValueError("SEC report exceeds its bounded file size")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".sec-evidence-", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
            temporary.chmod(0o444)
            os.link(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
