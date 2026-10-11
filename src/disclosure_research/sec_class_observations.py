"""Source-bound lexical class comparisons, never historical security approvals.

The caller pins the original SEC report and the private Names evidence. This
module reads neither original documents nor vendor files. It preserves context
occurrences and compares already recorded text; it is not an XBRL interpreter.
"""

import copy
import hashlib
import json
import re
from collections import defaultdict
from html.parser import HTMLParser
from urllib.parse import urlsplit

VERSION = "sec-class-observations-lexical-v1"
_SHA = re.compile(r"[0-9a-f]{64}")
_CIK = re.compile(r"[0-9]{1,10}")
_DEI = re.compile(r"https?://xbrl\.sec\.gov/dei/[0-9]{4}-[0-9]{2}-[0-9]{2}")
_GAAP = re.compile(r"https?://fasb\.org/us-gaap/[0-9]{4}-[0-9]{2}-[0-9]{2}")
_IX = {"http://www.xbrl.org/2008/inlineXBRL", "http://www.xbrl.org/2013/inlineXBRL"}
_XBRLI = "http://www.xbrl.org/2003/instance"
_XBRLDI = "http://xbrl.org/2006/xbrldi"
_CLASS_AXES = {"StatementClassOfStockAxis", "CapitalUnitsByClassAxis"}
_SECURITY = {"Security12bTitle", "Security12gTitle", "TradingSymbol", "SecurityExchangeName"}
_CLASS_TOKEN = re.compile(r"\bclass\s+([A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)(?=$|[\s,;:)])", re.I)
_NAMES_FIELDS = ("ticker", "shareclass", "issuernm", "securitytype", "securitysubtype",
                 "sharetype", "issuertype", "primaryexch")


def _sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _fingerprint(value):
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))


def _cik(value):
    if not isinstance(value, str) or not _CIK.fullmatch(value) or not value.strip("0"):
        return None
    return value.zfill(10)


def _namespace(value, *, local=None, uri=None, pattern=None):
    if not isinstance(value, dict) or value.get("status") != "DECLARATION_FOUND_IN_PARSED_HTML":
        return False
    if local is not None and value.get("local_name") != local:
        return False
    actual = value.get("namespace_uri")
    return (isinstance(actual, str) and bool(actual.strip()) and (uri is None or actual == uri)
            and (pattern is None or pattern.fullmatch(actual) is not None))


def _local_name(fact):
    qname = fact.get("concept_qname_raw")
    return qname.split(":")[-1] if isinstance(qname, str) else None


def _source_issues(record, names, matching):
    issues = []
    original = _cik(record.get("manifest_cik_raw"))
    if original is None:
        issues.append("original_filer_cik_unresolved")
    if record.get("cover_evidence", {}).get("status") not in {
            "LEXICAL_COVER_FACTS_RETAINED", "NO_SUPPORTED_INLINE_COVER_FACTS", "HTML_PARSE_UNRESOLVED"}:
        issues.append("cover_evidence_status_unresolved")
    for field in ("primary_source", "header_source"):
        source = record.get(field, {})
        try:
            url = urlsplit(source.get("url", ""))
            valid_url = (url.scheme == "https" and url.hostname == "www.sec.gov"
                         and not url.username and not url.password and url.port is None
                         and not url.query and not url.fragment
                         and url.path.startswith("/Archives/edgar/data/"))
        except (TypeError, ValueError):
            valid_url = False
        if (not valid_url or not isinstance(source.get("sha256"), str)
                or not _SHA.fullmatch(source["sha256"])
                or not isinstance(source.get("cache_metadata_sha256"), str)
                or not _SHA.fullmatch(source["cache_metadata_sha256"])
                or source.get("original_bytes_reverified") is not True):
            issues.append(f"{field}_binding_unresolved")
    header = record.get("header_identity", {})
    filers = header.get("filers", [])
    matched = [f for f in filers if f.get("matches_manifest_cik") is True]
    if (header.get("header_identity_consistent") is not True or header.get("issues")
            or len(matched) != 1 or not isinstance(matching, dict) or matched[0] != matching
            or matching.get("filer_fields_unambiguous") is not True
            or matching.get("cik_comparison_key") != original):
        issues.append("original_matching_filer_unresolved")
    for field in ("source_sha256", "source_inventory_sha256"):
        if not isinstance(names.get(field), str) or not _SHA.fullmatch(names[field]):
            issues.append(f"names_{field}_unresolved")
    ordinal = names.get("source_csv_record")
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 2:
        issues.append("names_source_csv_record_unresolved")
    return issues


class _FragmentText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, value):
        self.parts.append(value)


def _fact_issues(fact):
    issues = list(fact.get("lexical_issues", []))
    concept = fact.get("concept_namespace", {})
    local = concept.get("local_name")
    if not _namespace(concept, pattern=_DEI):
        issues.append("concept_namespace_unresolved")
    inline = fact.get("inline_element_namespace", {})
    if not _namespace(inline, local="nonnumeric") or inline.get("namespace_uri") not in _IX:
        issues.append("inline_element_unresolved")
    qname = fact.get("concept_qname_raw")
    if not isinstance(qname, str) or qname.split(":")[-1] != local:
        issues.append("concept_name_disagrees_with_namespace_observation")
    fragment = fact.get("serialized_parsed_html")
    if not isinstance(fragment, str) or _sha(fragment) != fact.get("parsed_serialization_sha256"):
        issues.append("fact_fragment_hash_unresolved")
    else:
        reader = _FragmentText()
        reader.feed(fragment)
        if "".join(reader.parts) != fact.get("text_from_parsed_html"):
            issues.append("fact_text_disagrees_with_serialized_fragment")
    if fact.get("continuedat_raw") is not None:
        issues.append("continuation_not_interpreted")
    if fact.get("format_raw") is not None:
        issues.append("format_transformation_not_interpreted")
    if fact.get("nil_attributes_raw"):
        issues.append("nil_attribute_not_interpreted")
    if fact.get("contains_exclude_element") is True:
        issues.append("exclude_content_not_interpreted")
    if not isinstance(fact.get("text_from_parsed_html"), str) or not fact["text_from_parsed_html"].strip():
        issues.append("fact_text_missing")
    return sorted(set(issues))


def _context_issues(contexts, facts, reference, original):
    issues, scope_issues = [], []
    if not reference or len(contexts) != 1:
        return ["context_reference_missing_or_ambiguous"], ["entity_scope_unresolved"]
    context = contexts[0]
    if context.get("context_id_raw") != reference:
        issues.append("context_reference_disagrees")
    ordinal = context.get("context_element_ordinal")
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 1:
        issues.append("context_occurrence_ordinal_unresolved")
    if any(f.get("context_element_ordinals") != [ordinal] for f in facts):
        issues.append("fact_context_occurrence_binding_disagrees")
    if (context.get("recognized_context_namespace") is not True
            or not _namespace(context.get("element_namespace"), local="context", uri=_XBRLI)):
        issues.append("context_namespace_unresolved")
    fragment = context.get("serialized_parsed_html")
    if not isinstance(fragment, str) or _sha(fragment) != context.get("parsed_serialization_sha256"):
        issues.append("context_fragment_hash_unresolved")
    identifiers = context.get("entity_identifiers", [])
    if (len(identifiers) != 1 or identifiers[0].get("scheme_raw") != "http://www.sec.gov/CIK"
            or not _namespace(identifiers[0].get("element_namespace"), local="identifier", uri=_XBRLI)
            or _cik(identifiers[0].get("text_from_parsed_html")) != original or original is None):
        scope_issues.append("context_entity_does_not_uniquely_match_original_filer")
    dimension_keys = set()
    for dimension in context.get("dimensions", []):
        axis = dimension.get("dimension_namespace", {})
        if _namespace(axis):
            key = (axis.get("namespace_uri"), axis.get("local_name"))
            if key in dimension_keys:
                issues.append("repeated_context_dimension_key")
            dimension_keys.add(key)
        if axis.get("local_name") == "LegalEntityAxis":
            scope_issues.append("legal_entity_dimension_requires_separate_scope_review")
        elif (dimension.get("kind") != "explicitmember"
              or not _namespace(dimension.get("element_namespace"), local="explicitmember", uri=_XBRLDI)
              or not _namespace(axis, pattern=_GAAP) or axis.get("local_name") not in _CLASS_AXES
              or not _namespace(dimension.get("member_namespace"))):
            scope_issues.append("context_dimension_scope_not_interpreted")
    identity_facts = [f for f in facts if _local_name(f) == "EntityCentralIndexKey"]
    if (len(identity_facts) > 1 or any(_fact_issues(f) or _cik(f.get("text_from_parsed_html")) != original
                                      for f in identity_facts)):
        scope_issues.append("same_context_cik_fact_conflicting_or_unresolved")
    return sorted(set(issues)), sorted(set(scope_issues))


def _title_observation(title):
    if title is None:
        return {"kind": "TITLE_UNRESOLVED", "explicit_class_tokens": []}
    tokens = _CLASS_TOKEN.findall(title)
    if re.search(r"\b(preferred|notes?|debentures?|bonds?|warrants?|rights?)\b", title, re.I):
        kind = "NONCOMMON_SECURITY_TERMS_PRESENT"
    elif re.search(r"\b(depositary|depository|units?|ADS|ADR)\b", title, re.I):
        kind = "DEPOSITARY_OR_UNIT_TERMS_UNINTERPRETED"
    elif re.search(r"\b(?:common|ordinary)\s+(?:stock|shares?)\b", title, re.I):
        kind = "COMMON_OR_ORDINARY_TERMS_PRESENT"
    else:
        kind = "SECURITY_TITLE_TERMS_UNINTERPRETED"
    return {"kind": kind, "explicit_class_tokens": tokens,
            "token_rule": "Literal token following the word class; spelling/case retained, no vendor meaning or class selection inferred."}


def _observation(record, names, matching, facts, contexts, reference, source_issues):
    cover = record.get("cover_evidence", {})
    by_name = defaultdict(list)
    for fact in facts:
        by_name[_local_name(fact)].append(fact)
    titles = [f for key in ("Security12bTitle", "Security12gTitle") for f in by_name[key]]
    symbols, exchanges = by_name["TradingSymbol"], by_name["SecurityExchangeName"]
    title = titles[0].get("text_from_parsed_html") if len(titles) == 1 else None
    symbol = symbols[0].get("text_from_parsed_html") if len(symbols) == 1 else None
    title_facts_issues = sorted({issue for f in titles for issue in _fact_issues(f)})
    symbol_facts_issues = sorted({issue for f in symbols for issue in _fact_issues(f)})
    exchange_issues = sorted({issue for f in exchanges for issue in _fact_issues(f)})
    context_issues, scope_issues = _context_issues(contexts, facts, reference, _cik(record.get("manifest_cik_raw")))
    local_issues = set(title_facts_issues + symbol_facts_issues)
    if len(titles) != 1:
        local_issues.add("security_title_missing_or_multiple")
    if len(symbols) != 1:
        local_issues.add("trading_symbol_missing_or_multiple")
    ordinals = [f.get("fact_element_ordinal") for f in facts]
    if any(not isinstance(i, int) or isinstance(i, bool) or i < 1 for i in ordinals) or len(set(ordinals)) != len(ordinals):
        local_issues.add("fact_occurrence_ordinal_missing_or_multiple")
    diagnostics = cover.get("parser_diagnostic_counts", {})
    fatal_parser = cover.get("status") == "HTML_PARSE_UNRESOLVED" or diagnostics.get("FATAL", 0) > 0
    title_observation = _title_observation(title)
    if len(title_observation["explicit_class_tokens"]) > 1:
        local_issues.add("multiple_explicit_title_class_tokens")
    if title and re.search(r"\bclass\s+[A-Za-z0-9.-]+\s+(?:and|or|&)\s+[A-Za-z0-9.-]+\b", title, re.I):
        local_issues.add("coordinated_title_class_tokens_uninterpreted")
    raw_names_ticker, raw_names_class = names.get("ticker"), names.get("shareclass")
    ticker_comparison = ("UNRESOLVED_OR_MISSING_TEXT" if not isinstance(symbol, str) or not symbol
                         or not isinstance(raw_names_ticker, str) or not raw_names_ticker
                         else "EXACT_RAW_TEXT" if symbol == raw_names_ticker else "DIFFERENT_RAW_TEXT")
    tokens = title_observation["explicit_class_tokens"]
    class_comparison = ("NO_SINGLE_EXPLICIT_CLASS_TOKEN" if len(tokens) != 1
                        else "NAMES_CLASS_TEXT_MISSING" if not isinstance(raw_names_class, str) or not raw_names_class
                        else "EXACT_RAW_TOKEN_TEXT" if tokens[0] == raw_names_class else "DIFFERENT_RAW_TOKEN_TEXT")
    security_facts_present = any(by_name[key] for key in _SECURITY)
    usable = not (source_issues or fatal_parser or context_issues or scope_issues or local_issues)
    if source_issues:
        status = "UNRESOLVED_SOURCE_EVIDENCE"
    elif fatal_parser:
        status = "UNRESOLVED_PARSER_EVIDENCE"
    elif not facts:
        status = "NO_INLINE_COVER_FACTS"
    elif not security_facts_present:
        status = "NO_SECURITY_CLASS_FACTS"
    elif context_issues:
        status = "UNRESOLVED_CONTEXT"
    elif scope_issues:
        status = "UNRESOLVED_ENTITY_SCOPE"
    elif local_issues:
        status = "UNRESOLVED_TITLE_OR_SYMBOL"
    elif by_name["Security12gTitle"]:
        status = "SECTION_12G_LEXICAL_OBSERVATION"
    elif title_observation["kind"] != "COMMON_OR_ORDINARY_TERMS_PRESENT":
        status = "NONCOMMON_OR_UNINTERPRETED_TITLE_OBSERVATION"
    elif ticker_comparison == "DIFFERENT_RAW_TEXT":
        status = "LEXICAL_TICKER_TEXT_CONFLICT"
    elif ticker_comparison != "EXACT_RAW_TEXT":
        status = "LEXICAL_TITLE_SYMBOL_OBSERVATION"
    elif class_comparison == "DIFFERENT_RAW_TOKEN_TEXT":
        status = "LEXICAL_TICKER_MATCH_CLASS_TOKEN_CONFLICT"
    elif class_comparison == "EXACT_RAW_TOKEN_TEXT":
        status = "LEXICAL_TICKER_AND_CLASS_TOKEN_TEXT_MATCH"
    else:
        status = "LEXICAL_TICKER_MATCH_CLASS_UNSPECIFIED"
    result = {
        "schema_version": 1, "version": VERSION, "status": status,
        "inherited_cover_status": cover.get("status"),
        "accession": record.get("accession"), "original_filer_cik": record.get("manifest_cik_raw"),
        "source_bindings": {key: copy.deepcopy(record.get(key)) for key in ("primary_source", "header_source")},
        "matching_filer_observation": copy.deepcopy(matching),
        "contextref_raw": reference, "context_occurrences": copy.deepcopy(contexts),
        "facts": copy.deepcopy(facts), "fact_element_ordinals": ordinals,
        "names_observation": {key: names.get(key) for key in (*_NAMES_FIELDS, "source_sha256", "source_inventory_sha256", "source_csv_record")},
        "title_lexical_observation": title_observation,
        "ticker_comparison": ticker_comparison, "shareclass_token_comparison": class_comparison,
        "ticker_comparison_rule": "Exact raw recorded text; no case, whitespace, punctuation or exchange normalization.",
        "title_symbol_lexically_usable": usable,
        "source_issues": sorted(source_issues), "context_issues": context_issues,
        "entity_scope_issues": scope_issues, "title_symbol_issues": sorted(local_issues),
        "exchange_issues": exchange_issues, "exchange_code_mapping_performed": False,
        "parser_diagnostic_counts": copy.deepcopy(diagnostics),
        "parser_scope": "Whole-document recovery diagnostics are retained; only fatal parser state or detected local ambiguity blocks this text comparison. No full tree or XBRL validity is asserted.",
        "comparison_scope": "Mechanical same-context lexical text observations only; no CIK/PERMNO identity, share-class selection or continuous historical interval is established.",
        "cross_context_security_assembly_performed": False, "context_period_is_link_validity": False,
        "original_sec_bytes_reread": False, "xbrl_values_interpreted": False,
        "identity_approved": False, "share_class_approved": False,
        "model_ready": False, "historical_security_links_created": 0,
        "known_at": None, "available_at": None,
    }
    result["observation_id"] = _fingerprint(result)
    return result


def observe_security_classes(sec_record, names_row, matching_filer):
    """Return every context's preserved lexical evidence and conservative status.

    Duplicate context IDs stay together as ambiguous occurrences; no first value
    or first share class is selected. Facts without contextRef remain individual
    unresolved observations. An untagged filing returns one explicit placeholder.
    The function never mutates inputs, reads files or makes source approvals.
    """
    if not isinstance(sec_record, dict) or not isinstance(names_row, dict):
        raise ValueError("SEC and Names observations must be dictionaries")
    cover = sec_record.get("cover_evidence", {})
    facts, contexts = cover.get("facts", []), cover.get("contexts", [])
    if (not isinstance(facts, list) or not isinstance(contexts, list)
            or any(not isinstance(row, dict) for row in facts + contexts)):
        raise ValueError("SEC lexical facts and contexts must be lists of dictionaries")
    if len(facts) > 4096 or len(contexts) > 4096:
        raise ValueError("SEC lexical observation count exceeds source collector bounds")
    issues = _source_issues(sec_record, names_row, matching_filer)
    grouped, context_groups = {}, defaultdict(list)
    for context in contexts:
        reference = context.get("context_id_raw")
        if isinstance(reference, str) and reference:
            context_groups[reference].append(context)
    for position, fact in enumerate(facts):
        reference = fact.get("contextref_raw")
        key = ("context", reference) if isinstance(reference, str) and reference else ("missing", position)
        grouped.setdefault(key, []).append(fact)
    if not grouped:
        return [_observation(sec_record, names_row, matching_filer, [], [], None, issues)]
    result = []
    for (kind, key), group in grouped.items():
        reference = key if kind == "context" else None
        result.append(_observation(sec_record, names_row, matching_filer, group,
                                   context_groups.get(reference, []), reference, issues))
    return result
