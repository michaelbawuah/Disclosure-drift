"""Invented source fragments test lexical comparison without mapping approvals."""

import copy
import hashlib
import json

import pytest

from disclosure_research.sec_class_observations import observe_security_classes
from disclosure_research.sec_identity_evidence import cover_evidence, header_identity


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _context(key="common", *, cik="0000000123", axis=None, member=None):
    segment = (f'<xbrli:segment><xbrldi:explicitMember dimension="{axis}">'
               f'{member}</xbrldi:explicitMember></xbrli:segment>') if axis else ""
    return (f'<xbrli:context id="{key}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">'
            f'{cik}</xbrli:identifier>{segment}</xbrli:entity><xbrli:period>'
            '<xbrli:startDate>2020-01-01</xbrli:startDate><xbrli:endDate>2020-12-31</xbrli:endDate>'
            '</xbrli:period></xbrli:context>')


def _fact(concept, value, context="common", **attrs):
    extra = " ".join(f'{key}="{value}"' for key, value in attrs.items())
    return f'<ix:nonNumeric name="dei:{concept}" contextRef="{context}" {extra}>{value}</ix:nonNumeric>'


def _registration(title="Class A common stock", symbol="EX.A", context="common", *, exchange_format=None):
    attrs = {"format": exchange_format} if exchange_format else {}
    return (_fact("Security12bTitle", title, context) + _fact("TradingSymbol", symbol, context)
            + _fact("SecurityExchangeName", "New York Stock Exchange", context, **attrs))


def _filer(cik, name):
    return f'<FILER><COMPANY-DATA><CIK>{cik}\n<CONFORMED-NAME>{name}\n</COMPANY-DATA></FILER>'


def _inputs(inner=None, *, cofilers=False):
    if inner is None:
        inner = _context(axis="us-gaap:StatementClassOfStockAxis", member="us-gaap:CommonClassAMember") + _registration()
    raw = ('<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" '
           'xmlns:dei="http://xbrl.sec.gov/dei/2020-01-31" '
           'xmlns:xbrli="http://www.xbrl.org/2003/instance" '
           'xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
           'xmlns:us-gaap="http://fasb.org/us-gaap/2020-01-31" '
           'xmlns:custom="https://example.test/20201231" '
           'xmlns:ixt="http://www.xbrl.org/inlineXBRL/transformation/2020-02-12" '
           f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><body>{inner}</body></html>').encode()
    header = ('<ACCESSION-NUMBER>0000000123-21-000001\n<TYPE>10-K\n'
              + _filer("0000000123", "Invented Corporation")
              + (_filer("0000000456", "Invented Subsidiary LLC") if cofilers else "")).encode()
    identity = header_identity(header, expected_cik="0000000123", expected_accession="0000000123-21-000001")
    record = {"accession": "0000000123-21-000001", "manifest_cik_raw": "0000000123",
              "acceptance_date": "2021-02-01", "header_identity": identity,
              "primary_source": {"url": "https://www.sec.gov/Archives/edgar/data/123/invented.htm",
                                 "sha256": _sha(raw), "cache_metadata_sha256": "a" * 64,
                                 "original_bytes_reverified": True},
              "header_source": {"url": "https://www.sec.gov/Archives/edgar/data/123/invented.hdr.sgml",
                                "sha256": _sha(header), "cache_metadata_sha256": "b" * 64,
                                "original_bytes_reverified": True},
              "cover_evidence": cover_evidence(raw)}
    names = {"ticker": "EX.A", "shareclass": "A", "issuernm": "INVENTED CORPORATION",
             "securitytype": "EQTY", "securitysubtype": "COM", "sharetype": "NS",
             "issuertype": "CORP", "primaryexch": "N", "source_sha256": "c" * 64,
             "source_inventory_sha256": "d" * 64, "source_csv_record": 2}
    return record, names, identity["filers"][0]


def _security(results):
    return [row for row in results if any(f["concept_namespace"]["local_name"].startswith("Security12")
                                        for f in row["facts"])]


def test_exact_same_context_text_match_is_deterministic_and_never_approval():
    inputs = _inputs()
    before = copy.deepcopy(inputs)
    first = observe_security_classes(*inputs)
    assert first == observe_security_classes(*inputs)
    assert inputs == before
    observation, = first
    assert observation["status"] == "LEXICAL_TICKER_AND_CLASS_TOKEN_TEXT_MATCH"
    assert observation["title_symbol_lexically_usable"] is True
    assert observation["ticker_comparison"] == "EXACT_RAW_TEXT"
    assert observation["shareclass_token_comparison"] == "EXACT_RAW_TOKEN_TEXT"
    assert len(observation["context_occurrences"]) == 1
    assert len(observation["facts"]) == 3
    assert observation["facts"] == inputs[0]["cover_evidence"]["facts"]
    assert observation["context_occurrences"] == inputs[0]["cover_evidence"]["contexts"]
    for row in first:
        assert row["known_at"] is row["available_at"] is None
        assert row["identity_approved"] is row["share_class_approved"] is False
        assert row["cross_context_security_assembly_performed"] is False
        assert row["context_period_is_link_validity"] is False
        assert row["original_sec_bytes_reread"] is False
        assert row["xbrl_values_interpreted"] is False
    assert json.loads(json.dumps(first, allow_nan=False)) == first


@pytest.mark.parametrize("ticker", ["EX-A", "ex.a", " EX.A", "EX.A "])
def test_ticker_punctuation_case_and_whitespace_are_never_normalized(ticker):
    record, names, filer = _inputs()
    names["ticker"] = ticker
    row, = observe_security_classes(record, names, filer)
    assert row["ticker_comparison"] == "DIFFERENT_RAW_TEXT"
    assert row["status"] == "LEXICAL_TICKER_TEXT_CONFLICT"


def test_generic_common_title_does_not_claim_exact_class():
    row, = observe_security_classes(*_inputs(_context() + _registration("Common Stock")))
    assert row["title_lexical_observation"]["explicit_class_tokens"] == []
    assert row["shareclass_token_comparison"] == "NO_SINGLE_EXPLICIT_CLASS_TOKEN"
    assert row["status"] == "LEXICAL_TICKER_MATCH_CLASS_UNSPECIFIED"
    assert row["share_class_approved"] is False


@pytest.mark.parametrize("class_token", ["A", "B"])
def test_nike_and_visa_shaped_unsegmented_contexts_preserve_title_class(class_token):
    inputs = _inputs(_context() + _registration(f"Class {class_token} Common Stock"))
    inputs[1]["shareclass"] = class_token
    row, = observe_security_classes(*inputs)
    assert row["context_occurrences"][0]["dimensions"] == []
    assert row["title_lexical_observation"]["explicit_class_tokens"] == [class_token]
    assert row["status"] == "LEXICAL_TICKER_AND_CLASS_TOKEN_TEXT_MATCH"


def test_explicit_title_class_conflict_is_visible_despite_matching_ticker():
    row, = observe_security_classes(*_inputs(_context() + _registration("Class B common stock")))
    assert row["status"] == "LEXICAL_TICKER_MATCH_CLASS_TOKEN_CONFLICT"
    assert row["ticker_comparison"] == "EXACT_RAW_TEXT"
    assert row["shareclass_token_comparison"] == "DIFFERENT_RAW_TOKEN_TEXT"


@pytest.mark.parametrize("title", ["Class A/B common stock", "Class A and B common stock",
                                   "Class A and Class B common stock"])
def test_composite_class_description_cannot_be_reduced_to_class_a_match(title):
    row, = observe_security_classes(*_inputs(_context() + _registration(title)))
    assert row["status"] != "LEXICAL_TICKER_AND_CLASS_TOKEN_TEXT_MATCH"
    assert row["share_class_approved"] is False


def test_common_and_debt_contexts_are_not_assembled_or_selected_first():
    inputs = _inputs(_context("debt") + _context("common")
                     + _registration("2% notes due 2029", "EX.A", "debt")
                     + _registration(context="common"))
    debt, common = observe_security_classes(*inputs)
    assert debt["status"] == "NONCOMMON_OR_UNINTERPRETED_TITLE_OBSERVATION"
    assert common["status"] == "LEXICAL_TICKER_AND_CLASS_TOKEN_TEXT_MATCH"
    assert not set(debt["fact_element_ordinals"]) & set(common["fact_element_ordinals"])
    assert debt["contextref_raw"] == "debt" and common["contextref_raw"] == "common"


def test_title_and_ticker_in_different_contexts_never_become_one_match():
    results = observe_security_classes(*_inputs(_context("a") + _context("b")
        + _fact("Security12bTitle", "Class A common stock", "a") + _fact("TradingSymbol", "EX.A", "b")))
    assert len(results) == 2
    assert all(r["status"] == "UNRESOLVED_TITLE_OR_SYMBOL" for r in results)
    assert all(r["title_symbol_lexically_usable"] is False for r in results)


def test_duplicate_context_occurrences_are_retained_and_cannot_support_match():
    inputs = _inputs(_context() + _context(cik="0000000456") + _registration())
    row, = observe_security_classes(*inputs)
    assert len(row["context_occurrences"]) == 2
    assert row["status"] == "UNRESOLVED_CONTEXT"
    assert row["ticker_comparison"] == "EXACT_RAW_TEXT"
    assert row["title_symbol_lexically_usable"] is False


def test_duplicate_identical_symbol_facts_remain_ambiguous():
    row, = observe_security_classes(*_inputs(_context() + _registration() + _fact("TradingSymbol", "EX.A")))
    assert row["status"] == "UNRESOLVED_TITLE_OR_SYMBOL"
    assert row["ticker_comparison"] == "UNRESOLVED_OR_MISSING_TEXT"
    assert len(row["facts"]) == 4


def test_comcast_shaped_cofiler_dimension_cannot_inherit_principal_security():
    inner = (_context("parent") + _context("subsidiary", axis="dei:LegalEntityAxis",
             member="custom:SubsidiaryMember") + _registration(context="parent")
             + _fact("EntityCentralIndexKey", "0000000456", "subsidiary")
             + _registration(context="subsidiary"))
    parent, subsidiary = observe_security_classes(*_inputs(inner, cofilers=True))
    assert parent["status"] == "LEXICAL_TICKER_AND_CLASS_TOKEN_TEXT_MATCH"
    assert subsidiary["status"] == "UNRESOLVED_ENTITY_SCOPE"
    assert subsidiary["context_occurrences"][0]["entity_identifiers"][0]["text_from_parsed_html"] == "0000000123"
    assert "legal_entity_dimension_requires_separate_scope_review" in subsidiary["entity_scope_issues"]
    assert "same_context_cik_fact_conflicting_or_unresolved" in subsidiary["entity_scope_issues"]
    assert subsidiary["title_symbol_lexically_usable"] is False


def test_visa_shaped_12g_classes_remain_separate_without_invented_ticker():
    inner = (_context("a") + _context("b", axis="us-gaap:StatementClassOfStockAxis", member="us-gaap:CommonClassBMember")
             + _registration(context="a") + _fact("Security12gTitle", "Class B common stock", "b"))
    rows = observe_security_classes(*_inputs(inner))
    assert len(rows) == 2 and rows[0]["status"] == "LEXICAL_TICKER_AND_CLASS_TOKEN_TEXT_MATCH"
    assert rows[1]["title_lexical_observation"]["explicit_class_tokens"] == ["B"]
    assert rows[1]["ticker_comparison"] == "UNRESOLVED_OR_MISSING_TEXT"
    assert rows[1]["title_symbol_lexically_usable"] is False


def test_exchange_transform_is_retained_separately_from_title_symbol_usability():
    row, = observe_security_classes(*_inputs(_context() + _registration(exchange_format="ixt:exchnameen")))
    assert row["status"] == "LEXICAL_TICKER_AND_CLASS_TOKEN_TEXT_MATCH"
    assert row["title_symbol_lexically_usable"] is True
    assert "format_transformation_not_interpreted" in row["exchange_issues"]
    assert row["exchange_code_mapping_performed"] is False


@pytest.mark.parametrize("attrs,issue", [({"continuedAt": "more"}, "continuation_not_interpreted"),
    ({"format": "ixt:anything"}, "format_transformation_not_interpreted"),
    ({"xsi:nil": "false"}, "nil_attribute_not_interpreted")])
def test_uninterpreted_title_semantics_block_positive_lexical_use(attrs, issue):
    inner = (_context() + _fact("Security12bTitle", "Class A common stock", **attrs)
             + _fact("TradingSymbol", "EX.A"))
    row, = observe_security_classes(*_inputs(inner))
    assert row["status"] == "UNRESOLVED_TITLE_OR_SYMBOL"
    assert issue in row["title_symbol_issues"]
    assert row["title_symbol_lexically_usable"] is False


def test_local_namespace_problem_blocks_match_without_blessing_year_only_declaration():
    record, names, filer = _inputs()
    record["cover_evidence"]["facts"][0]["concept_namespace"]["namespace_uri"] = "http://xbrl.sec.gov/dei/2021"
    row, = observe_security_classes(record, names, filer)
    assert row["status"] == "UNRESOLVED_TITLE_OR_SYMBOL"
    assert "concept_namespace_unresolved" in row["title_symbol_issues"]


def test_unrecognized_namespace_does_not_erase_a_recorded_security_concept():
    record, names, filer = _inputs()
    record["cover_evidence"]["facts"][0]["concept_namespace"] = {
        "local_name": None, "namespace_uri": None, "status": "MISSING_OR_UNSUPPORTED_QNAME"}
    row, = observe_security_classes(record, names, filer)
    assert row["status"] == "UNRESOLVED_TITLE_OR_SYMBOL"
    assert len(row["facts"]) == 3
    assert row["title_symbol_lexically_usable"] is False


@pytest.mark.parametrize("alteration", ["source_hash", "source_url", "filer", "names_hash", "names_record"])
def test_unresolved_source_or_original_filer_binding_never_supports_match(alteration):
    record, names, filer = _inputs()
    if alteration == "source_hash":
        record["primary_source"]["sha256"] = "not-a-hash"
    elif alteration == "source_url":
        record["primary_source"]["url"] = "https://not-sec.example/Archives/edgar/data/123/invented.htm"
    elif alteration == "filer":
        filer = {**filer, "cik_comparison_key": "0000000456"}
    elif alteration == "names_hash":
        names["source_sha256"] = None
    else:
        names["source_csv_record"] = True
    row, = observe_security_classes(record, names, filer)
    assert row["status"] == "UNRESOLVED_SOURCE_EVIDENCE"
    assert row["title_symbol_lexically_usable"] is False


@pytest.mark.parametrize("mutation,expected", [("fact_text", "UNRESOLVED_TITLE_OR_SYMBOL"),
    ("fact_hash", "UNRESOLVED_TITLE_OR_SYMBOL"), ("context_hash", "UNRESOLVED_CONTEXT"),
    ("context_binding", "UNRESOLVED_CONTEXT")])
def test_local_fragment_and_occurrence_disagreement_remains_unresolved(mutation, expected):
    record, names, filer = _inputs()
    fact = record["cover_evidence"]["facts"][0]
    if mutation == "fact_text":
        fact["text_from_parsed_html"] = "Class B common stock"
    elif mutation == "fact_hash":
        fact["parsed_serialization_sha256"] = "0" * 64
    elif mutation == "context_hash":
        record["cover_evidence"]["contexts"][0]["parsed_serialization_sha256"] = "0" * 64
    else:
        fact["context_element_ordinals"] = [999]
    row, = observe_security_classes(record, names, filer)
    assert row["status"] == expected
    assert row["title_symbol_lexically_usable"] is False


def test_routine_global_parser_diagnostics_remain_visible_without_overstating_local_ambiguity():
    record, names, filer = _inputs()
    record["cover_evidence"]["parser_diagnostic_counts"] = {"ERROR": 42, "WARNING": 1}
    row, = observe_security_classes(record, names, filer)
    assert row["parser_diagnostic_counts"] == {"ERROR": 42, "WARNING": 1}
    assert row["status"] == "LEXICAL_TICKER_AND_CLASS_TOKEN_TEXT_MATCH"
    record["cover_evidence"]["parser_diagnostic_counts"]["FATAL"] = 1
    row, = observe_security_classes(record, names, filer)
    assert row["status"] == "UNRESOLVED_PARSER_EVIDENCE"
    assert row["title_symbol_lexically_usable"] is False


def test_untagged_and_entity_only_sources_are_not_dropped():
    untagged, = observe_security_classes(*_inputs("<p>Invented untagged filing</p>"))
    assert untagged["status"] == "NO_INLINE_COVER_FACTS"
    assert untagged["facts"] == untagged["context_occurrences"] == []
    entity, = observe_security_classes(*_inputs(_context() + _fact("EntityCentralIndexKey", "0000000123")))
    assert entity["status"] == "NO_SECURITY_CLASS_FACTS"
    assert len(entity["facts"]) == len(entity["context_occurrences"]) == 1


def test_missing_contextref_facts_remain_individual_unresolved_observations():
    record, names, filer = _inputs()
    for fact in record["cover_evidence"]["facts"]:
        fact["contextref_raw"] = None
        fact["context_element_ordinals"] = []
    rows = observe_security_classes(record, names, filer)
    assert len(rows) == 3 and all(len(r["facts"]) == 1 for r in rows)
    assert all(r["status"] == "UNRESOLVED_CONTEXT" for r in rows)
    assert all(r["title_symbol_lexically_usable"] is False for r in rows)


def test_unrecognized_context_dimension_cannot_assert_legal_entity_scope():
    row, = observe_security_classes(*_inputs(_context(axis="custom:UninterpretedAxis", member="custom:Member")
                                            + _registration()))
    assert row["status"] == "UNRESOLVED_ENTITY_SCOPE"
    assert "context_dimension_scope_not_interpreted" in row["entity_scope_issues"]


@pytest.mark.parametrize("second_member", ["CommonClassAMember", "CommonClassBMember"])
def test_repeated_expanded_class_axis_retains_both_members_without_lexical_support(second_member):
    context = _context(axis="us-gaap:StatementClassOfStockAxis", member="us-gaap:CommonClassAMember")
    context = context.replace("</xbrli:segment>",
        '<xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">'
        f'us-gaap:{second_member}</xbrldi:explicitMember></xbrli:segment>')
    row, = observe_security_classes(*_inputs(context + _registration()))
    assert len(row["context_occurrences"][0]["dimensions"]) == 2
    assert row["status"] == "UNRESOLVED_CONTEXT"
    assert "repeated_context_dimension_key" in row["context_issues"]
    assert row["title_symbol_lexically_usable"] is False


def test_output_objects_do_not_alias_source_fragments():
    record, names, filer = _inputs()
    rows = observe_security_classes(record, names, filer)
    rows[0]["facts"][0]["lexical_issues"].append("added_later")
    rows[0]["context_occurrences"][0]["dimensions"].clear()
    assert "added_later" not in record["cover_evidence"]["facts"][0]["lexical_issues"]
    assert record["cover_evidence"]["contexts"][0]["dimensions"]
