"""Invented SEC documents exercise source bindings and lexical ambiguity."""

import csv
import hashlib
import io
import json
import runpy
from pathlib import Path

import pytest

from disclosure_research import sec_identity_evidence as evidence
from disclosure_research.audit import cached_body
from disclosure_research.protocol import load_protocol, write_lock


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "configs").mkdir()
    write_lock(load_protocol(), tmp_path / "configs/protocol.lock.json")
    (tmp_path / "configs/protocol.json").write_text(json.dumps(load_protocol()))
    return tmp_path


def _filer(cik="0000000123", name="Invented Corporation"):
    return f"<FILER><COMPANY-DATA><CIK>{cik}\n<CONFORMED-NAME>{name}\n</COMPANY-DATA></FILER>"


def _header(filers=None, *, accession="0000000123-21-000001", form="10-K", clock="20210215120000"):
    return (f"<ACCESSION-NUMBER>{accession}\n<TYPE>{form}\n<ACCEPTANCE-DATETIME>{clock}\n"
            + "".join([_filer()] if filers is None else filers)).encode()


def _context(context_id="base", member=None, *, cik="0000000123"):
    segment = (f'<xbrli:segment><xbrldi:explicitMember dimension="custom:ShareClassAxis">'
               f'custom:{member}</xbrldi:explicitMember></xbrli:segment>') if member else ""
    return (f'<xbrli:context id="{context_id}"><xbrli:entity><xbrli:identifier '
            f'scheme="http://www.sec.gov/CIK">{cik}</xbrli:identifier>{segment}</xbrli:entity>'
            '<xbrli:period><xbrli:startDate>2020-01-01</xbrli:startDate>'
            '<xbrli:endDate>2020-12-31</xbrli:endDate></xbrli:period></xbrli:context>')


def _fact(name="TradingSymbol", text="EXAMPLE", context="a", **attrs):
    attributes = " ".join(f'{key}="{value}"' for key, value in attrs.items())
    return f'<ix:nonNumeric name="dei:{name}" contextRef="{context}" {attributes}>{text}</ix:nonNumeric>'


def _html(inner=None):
    if inner is None:
        inner = ('<ix:header><ix:resources>' + _context() + _context("a", "ClassAMember")
                 + _context("b", "ClassBMember") + '</ix:resources><ix:hidden>'
                 + _fact("EntityCentralIndexKey", "0000000123", "base")
                 + _fact("EntityRegistrantName", "Invented &amp; Co", "base") + '</ix:hidden></ix:header>'
                 + _fact("Security12bTitle", "Class A common stock", "a")
                 + _fact("TradingSymbol", "EX.A", "a") + _fact("SecurityExchangeName", "NYSE", "a")
                 + _fact("Security12bTitle", "Class B preferred stock", "b")
                 + _fact("TradingSymbol", "EX.B", "b") + _fact("SecurityExchangeName", "NASDAQ", "b"))
    return ('<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" '
            'xmlns:dei="http://xbrl.sec.gov/dei/2020-01-31" '
            'xmlns:xbrli="http://www.xbrl.org/2003/instance" '
            'xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
            'xmlns:custom="urn:invented:classes" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<body>' + inner + '</body></html>').encode()


def _cache(cache, url, raw):
    cache.mkdir(exist_ok=True)
    key = _sha(url.encode())
    (cache / f"{key}.bin").write_bytes(raw)
    (cache / f"{key}.json").write_text(json.dumps({"url": url, "sha256": _sha(raw), "bytes": len(raw),
                                                 "status": 200, "fetched_at": "2026-10-11T00:00:00Z"}))


def _inputs(repo, *, body=None, header=None, changes=None):
    row = dict.fromkeys(evidence.SEC_FIELDS, "")
    row.update(cik="0000000123", name="Invented Corporation", accessionNumber="0000000123-21-000001",
               reportDate="2020-12-31", acceptance_date="2021-02-15",
               acceptance_timestamp="2021-02-15T12:00:00-05:00",
               source_url="https://www.sec.gov/Archives/edgar/data/123/example.htm",
               header_url="https://www.sec.gov/Archives/edgar/data/123/example.hdr.sgml",
               extraction_version="synthetic")
    body = _html() if body is None else body
    header = _header() if header is None else header
    row.update(download_sha256=_sha(body), header_sha256=_sha(header))
    row.update(changes or {})
    cache = repo / "cache"
    _cache(cache, row["source_url"], body)
    _cache(cache, row["header_url"], header)
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=evidence.SEC_FIELDS)
    writer.writeheader()
    writer.writerow(row)
    manifest = repo / "filing_sources.csv"
    manifest.write_text(text.getvalue())
    return {"manifest": manifest, "manifest_sha256": _sha(manifest.read_bytes()), "cache": cache,
            "config": load_protocol(), "repo_root": repo}


def _build(inputs):
    return evidence.build_sec_identity_evidence(**inputs)


def test_bound_sources_hidden_multiclass_contexts_and_deterministic_report(repo):
    inputs = _inputs(repo, header=_header([_filer(), _filer("0000000456", "Other Registrant")]))
    original = {path: path.read_bytes() for path in inputs["cache"].iterdir()}
    first = _build(inputs)
    second = _build(inputs)
    assert first == second
    assert first["manifest_sha256"] == inputs["manifest_sha256"]
    assert first["summary"]["unique_manifest_filer_matches"] == 1
    assert first["summary"]["header_filer_observations"] == 2
    assert first["summary"]["filings_with_multiple_filers"] == 1
    assert first["summary"]["facts_in_hidden_elements"] == 2
    assert first["summary"]["facts_with_lexical_issues"] == 0
    record = first["records"][0]
    assert record["manifest_csv_record"] == 2
    assert record["primary_source"]["original_bytes_reverified"] is True
    assert record["acceptance_clock"]["matches_manifest"] is True
    filers = record["header_identity"]["filers"]
    assert [f["matches_manifest_cik"] for f in filers] == [True, False]
    cover = record["cover_evidence"]
    assert len(cover["facts"]) == 8 and len(cover["contexts"]) == 3
    contexts = {c["context_element_ordinal"]: c for c in cover["contexts"]}
    symbols = [f for f in cover["facts"] if f["concept_qname_raw"] == "dei:TradingSymbol"]
    assert [f["text_from_parsed_html"] for f in symbols] == ["EX.A", "EX.B"]
    assert symbols[0]["context_element_ordinals"] != symbols[1]["context_element_ordinals"]
    assert [contexts[f["context_element_ordinals"][0]]["dimensions"][0]["text_from_parsed_html"]
            for f in symbols] == ["custom:ClassAMember", "custom:ClassBMember"]
    for fact in cover["facts"]:
        assert fact["concept_namespace"]["namespace_uri"] == "http://xbrl.sec.gov/dei/2020-01-31"
        assert fact["interpreted_xbrl_value"] is None and fact["security_link_created"] is False
        assert fact["serialization_is_original_source_bytes"] is False
        assert fact["parsed_serialization_sha256"] == _sha(fact["serialized_parsed_html"].encode())
    assert next(f for f in cover["facts"] if f["concept_qname_raw"] == "dei:EntityRegistrantName")["text_from_parsed_html"] == "Invented & Co"
    assert all(path.read_bytes() == raw for path, raw in original.items())
    assert record["known_at"] is record["available_at"] is None
    assert first["original_sec_bytes_reread"] is True
    assert first["source_approvals"] == first["human_reviews_created"] == first["historical_security_links_created"] == 0
    assert all(first[field] is False for field in ("public_dissemination_verified", "full_filing_bodies_in_report",
               "xbrl_fact_values_interpreted", "prior_arithmetic_review_modified", "model_ready", "final_period_opened"))
    destination = repo / "report.json"
    binding = evidence.write_report(first, destination)
    assert binding["sha256"] == _sha(destination.read_bytes())
    assert json.loads(destination.read_text()) == first
    assert destination.stat().st_mode & 0o222 == 0
    with pytest.raises(ValueError, match="new JSON"):
        evidence.write_report(first, destination)


@pytest.mark.parametrize("change", ["primary_body", "header_body", "metadata_url", "metadata_hash", "manifest", "pin"])
def test_source_hash_and_manifest_tampering_fails_closed(repo, change):
    inputs = _inputs(repo)
    row = next(csv.DictReader(inputs["manifest"].open()))
    if change in {"primary_body", "header_body"}:
        url = row["source_url" if change == "primary_body" else "header_url"]
        (inputs["cache"] / f"{_sha(url.encode())}.bin").write_bytes(b"changed")
    elif change.startswith("metadata_"):
        path = inputs["cache"] / f"{_sha(row['source_url'].encode())}.json"
        value = json.loads(path.read_text())
        value["url" if change == "metadata_url" else "sha256"] = "incorrect"
        path.write_text(json.dumps(value))
    elif change == "manifest":
        inputs["manifest"].write_bytes(inputs["manifest"].read_bytes() + b"\n")
    else:
        inputs["manifest_sha256"] = "a" * 64
    with pytest.raises(ValueError):
        _build(inputs)


@pytest.mark.parametrize("filers", [[], [_filer("0000000456")], [_filer(), _filer()],
                                    [_filer(), "<FILER><COMPANY-DATA><CIK>0000000456</COMPANY-DATA></FILER>"]])
def test_missing_duplicate_or_malformed_filer_never_satisfies_unique_match(repo, filers):
    raw = _header(filers)
    parsed = evidence.header_identity(raw, expected_cik="0000000123", expected_accession="0000000123-21-000001")
    assert parsed["header_identity_consistent"] is False
    assert len(parsed["filers"]) == len(filers)
    with pytest.raises(ValueError, match="uniquely corroborate"):
        _build(_inputs(repo, header=raw))


@pytest.mark.parametrize("changes", [{"accession": "0000000456-21-000001"}, {"form": "10-K/A"},
                                    {"clock": "20210215130000"}, {"clock": "20210230090000"}])
def test_original_accession_form_and_acceptance_are_required(repo, changes):
    with pytest.raises(ValueError):
        _build(_inputs(repo, header=_header(**changes)))


def test_duplicate_acceptance_clock_cannot_select_first(repo):
    raw = _header() + b"\n<ACCEPTANCE-DATETIME>20210215120000\n"
    with pytest.raises(ValueError, match="exactly one"):
        _build(_inputs(repo, header=raw))


def test_clock_compares_aware_instants_while_retaining_original_representations(repo):
    result = _build(_inputs(repo, changes={"acceptance_timestamp": "2021-02-15T17:00:00Z"}))
    clock = result["records"][0]["acceptance_clock"]
    assert clock["manifest_timestamp_raw"] == "2021-02-15T17:00:00Z"
    assert clock["interpreted_acceptance_timestamp"] == "2021-02-15T12:00:00-05:00"
    assert clock["matches_manifest"] is True


@pytest.mark.parametrize("extra", ["<COMPANY-DATA>", "</COMPANY-DATA>"])
def test_malformed_extra_company_blocks_cannot_be_unambiguous(repo, extra):
    block = _filer().replace("</FILER>", extra + "</FILER>")
    raw = _header([block])
    parsed = evidence.header_identity(raw, expected_cik="0000000123", expected_accession="0000000123-21-000001")
    assert parsed["header_identity_consistent"] is False
    assert "unresolved_filer_company_identity" in parsed["issues"]
    with pytest.raises(ValueError, match="uniquely corroborate"):
        _build(_inputs(repo, header=raw))


@pytest.mark.parametrize("mutation,issue", [
    (lambda s: s.replace('xmlns:dei="http://xbrl.sec.gov/dei/2020-01-31"', 'xmlns:dei="urn:not-dei"'),
     "dei_namespace_unrecognized_or_unresolved"),
    (lambda s: s.replace('xmlns:dei="http://xbrl.sec.gov/dei/2020-01-31"', ''),
     "dei_namespace_unrecognized_or_unresolved"),
    (lambda s: s.replace('xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"', 'xmlns:ix="urn:not-inline"'),
     "inline_namespace_unrecognized_or_unresolved"),
    (lambda s: s.replace('xmlns:xbrli="http://www.xbrl.org/2003/instance"', 'xmlns:xbrli="urn:not-context"'),
     "context_namespace_unrecognized_or_unresolved"),
    (lambda s: s.replace('name="dei:TradingSymbol"', 'name="DEI:TradingSymbol"'),
     "dei_namespace_unrecognized_or_unresolved"),
])
def test_namespace_unknowns_remain_lexical_facts(mutation, issue):
    body = mutation(_html(_context("a") + _fact()).decode()).encode()
    cover = evidence.cover_evidence(body)
    assert len(cover["facts"]) == 1
    assert issue in cover["facts"][0]["lexical_issues"]
    assert cover["facts"][0]["interpreted_xbrl_value"] is None


def test_namespace_shadowing_is_resolved_at_the_fact_and_recorded():
    body = _html(_context("a") + '<div xmlns:dei="urn:shadowed">' + _fact() + '</div>' + _fact(text="OUTSIDE"))
    cover = evidence.cover_evidence(body)
    assert [fact["concept_namespace"]["namespace_uri"] for fact in cover["facts"]] == [
        "urn:shadowed", "http://xbrl.sec.gov/dei/2020-01-31"]
    assert cover["facts"][0]["lexical_issues"] and not cover["facts"][1]["lexical_issues"]


@pytest.mark.parametrize("contexts,reference,issue", [("", "absent", "referenced_context_missing"),
    (_context("a") + _context("a", "DifferentMember"), "a", "referenced_context_id_ambiguous"),
    (_context("a"), "", "contextref_missing")])
def test_missing_or_duplicate_contexts_do_not_drop_the_fact(contexts, reference, issue):
    cover = evidence.cover_evidence(_html(contexts + _fact(context=reference)))
    fact = cover["facts"][0]
    assert issue in fact["lexical_issues"] and fact["text_from_parsed_html"] == "EXAMPLE"
    assert len(fact["context_element_ordinals"]) == (2 if issue == "referenced_context_id_ambiguous" else 0)
    assert len(cover["contexts"]) == len(fact["context_element_ordinals"])


def test_continuation_transform_nil_and_exclusion_are_not_interpreted():
    first = _fact(text='HEAD<ix:exclude> OMITTED-BY-XBRL </ix:exclude>',
                  continuedAt="tail", format="custom:transform", **{"xsi:nil": "false"})
    tail = '<ix:continuation id="tail">UNJOINED TAIL</ix:continuation>'
    cover = evidence.cover_evidence(_html(_context("a") + first + tail))
    fact = cover["facts"][0]
    assert fact["continuedat_raw"] == "tail" and fact["format_raw"] == "custom:transform"
    assert fact["nil_attributes_raw"] == [["xsi:nil", "false"]]
    assert "OMITTED-BY-XBRL" in fact["text_from_parsed_html"]
    assert "UNJOINED TAIL" not in fact["text_from_parsed_html"]
    assert set(fact["lexical_issues"]) == {"continuation_not_interpreted", "format_transformation_not_interpreted",
                                          "nil_attribute_not_interpreted", "exclude_content_not_interpreted"}
    assert fact["interpreted_xbrl_value"] is None


def test_typed_legal_entity_context_keeps_entity_identifier_separate_from_fact_cik():
    context = _context("legal").replace('</xbrli:entity>',
        '<xbrli:segment><xbrldi:typedMember dimension="custom:LegalEntityAxis">'
        '<custom:Entity>Other Registrant</custom:Entity></xbrldi:typedMember></xbrli:segment></xbrli:entity>')
    cover = evidence.cover_evidence(_html(context + _fact("EntityCentralIndexKey", "0000000456", "legal")))
    assert cover["facts"][0]["text_from_parsed_html"] == "0000000456"
    assert cover["contexts"][0]["entity_identifiers"][0]["text_from_parsed_html"] == "0000000123"
    dimension = cover["contexts"][0]["dimensions"][0]
    assert dimension["kind"] == "typedmember" and dimension["member_namespace"] is None
    assert dimension["dimension_namespace"]["namespace_uri"] == "urn:invented:classes"
    assert "Other Registrant" in dimension["serialized_parsed_html"]


def test_untagged_and_unparseable_documents_get_explicit_coverage(repo):
    first = _build(_inputs(repo, body=b"<html><body>Invented untagged annual report.</body></html>"))
    cover = first["records"][0]["cover_evidence"]
    assert cover["status"] == "NO_SUPPORTED_INLINE_COVER_FACTS"
    assert cover["facts"] == cover["contexts"] == []
    assert evidence.cover_evidence(b"")["status"] == "HTML_PARSE_UNRESOLVED"


def test_entire_manifest_date_pass_precedes_cache_reads(repo, monkeypatch):
    inputs = _inputs(repo)
    rows = list(csv.DictReader(inputs["manifest"].open()))
    rows.append({**rows[0], "accessionNumber": "0000000123-22-000001", "acceptance_date": "2022-01-03",
                 "acceptance_timestamp": "2022-01-03T12:00:00-05:00"})
    with inputs["manifest"].open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=evidence.SEC_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    inputs["manifest_sha256"] = _sha(inputs["manifest"].read_bytes())
    def prohibited(*args, **kwargs):
        raise AssertionError("Original sources opened before full manifest date preflight")
    monkeypatch.setattr(evidence, "cached_body", prohibited)
    with pytest.raises(ValueError, match="final period"):
        _build(inputs)


@pytest.mark.parametrize("target", ["manifest", "body", "metadata"])
def test_final_identity_and_hash_guards_reject_midrun_changes(repo, monkeypatch, target):
    inputs = _inputs(repo)
    original = evidence.cover_evidence
    def mutate(raw):
        result = original(raw)
        if target == "manifest":
            path = inputs["manifest"]
        else:
            row = next(csv.DictReader(inputs["manifest"].open()))
            path = inputs["cache"] / (_sha(row["source_url"].encode()) + (".bin" if target == "body" else ".json"))
        path.write_bytes(path.read_bytes() + b" ")
        return result
    monkeypatch.setattr(evidence, "cover_evidence", mutate)
    with pytest.raises(ValueError, match="changed"):
        _build(inputs)


def test_size_and_symlink_limits_fail_before_unbounded_source_read(repo, monkeypatch):
    inputs = _inputs(repo)
    monkeypatch.setattr(evidence, "_MAX_BODY_BYTES", 3)
    def prohibited(*args, **kwargs):
        raise AssertionError("Oversized body was read")
    monkeypatch.setattr(evidence, "cached_body", prohibited)
    with pytest.raises(ValueError, match="bounded size"):
        _build(inputs)
    monkeypatch.setattr(evidence, "_MAX_BODY_BYTES", 40 * 1024 * 1024)
    monkeypatch.setattr(evidence, "cached_body", cached_body)
    row = next(csv.DictReader(inputs["manifest"].open()))
    path = inputs["cache"] / f"{_sha(row['source_url'].encode())}.bin"
    moved = repo / "moved-source"
    path.rename(moved)
    path.symlink_to(moved)
    with pytest.raises(ValueError, match="nonsymlink"):
        _build(inputs)


def test_lexical_budget_does_not_silently_truncate_a_selected_fact(monkeypatch):
    monkeypatch.setattr(evidence, "_MAX_TEXT", 20)
    with pytest.raises(ValueError, match="text budget"):
        evidence.cover_evidence(_html(_context("a") + _fact(text="X" * 100)))


def test_growth_after_source_stat_is_refused_before_an_unbounded_read(repo, monkeypatch):
    inputs = _inputs(repo)
    original = evidence.cached_body
    def grow(cache, url, expected):
        path = inputs["cache"] / f"{_sha(url.encode())}.bin"
        path.write_bytes(path.read_bytes() + b"X" * 10000)
        return original(cache, url, expected)
    monkeypatch.setattr(evidence, "cached_body", grow)
    with pytest.raises(ValueError, match="before its bounded read"):
        _build(inputs)


def test_cli_writes_complete_public_report_and_sanitizes_failures(repo, monkeypatch, capsys):
    inputs = _inputs(repo)
    script = Path(__file__).parents[1] / "scripts/verify_sec_identity_evidence.py"
    cli = runpy.run_path(str(script))["main"]
    monkeypatch.chdir(repo)
    output = repo / "report.json"
    args = ["--manifest", str(inputs["manifest"]), "--manifest-sha256", inputs["manifest_sha256"],
            "--cache", str(inputs["cache"]), "--output", str(output)]
    assert cli(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["report"]["sha256"] == _sha(output.read_bytes())
    assert json.loads(output.read_text())["records"][0]["cover_evidence"]["facts"]
    assert cli(args) == 1
    failed = json.loads(capsys.readouterr().out)
    assert set(failed) == {"status", "error_type", "model_ready", "source_approvals"}
