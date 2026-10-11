"""Independently recheck the bounded seven-case and 14-case SEC follow-ups.

Offline only. Run on the authorized host containing the pinned source cohort.
The report contains hashes and aggregate checks, never licensed associations.
No audit implementation is imported; XML uses Expat rather than ElementTree.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import xml.parsers.expat
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_SHA = "85358e4f928687ed9fc3da3813e87980321bbd155b24c952f7a955c5c92a8442"
TSV_SHA = "0f73eaa50e3964641fe180cb2db299d94ae5b77e4d12d3a68ba1ab5b663b6e2c"
MULTI_BASE = Path("outputs/multi-cik-followup-20261011")
CLOCK_BASE = Path("outputs/cutoff-clock-followup-20261011")
META = ("ACCESSION_NUMBER", "DOCUMENT_TYPE", "FILING_DATE", "ISSUERCIK",
        "ISSUERNAME", "ISSUERTRADINGSYMBOL", "PERIOD_OF_REPORT", "DATE_OF_ORIG_SUB")
MULTI_META = META[:6]
ET = ZoneInfo("America/New_York")
FORBIDDEN_KEYS = {"security_id", "security_ids", "gvkey", "permno", "permco",
                  "lpermno", "lpermco", "cusip", "names_source_csv_record",
                  "matched_fields_json", "security_date_source_records_json"}
INPUTS = {}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(relative):
    path = ROOT / relative
    raw = path.read_bytes()
    INPUTS[str(path.relative_to(ROOT))] = {"sha256": sha(raw), "bytes": len(raw)}
    return raw


def document(relative):
    return json.loads(read(relative))


def positive_cik(value):
    value = value.strip()
    return value.zfill(10) if re.fullmatch(r"[0-9]{1,10}", value) and int(value) else ""


def day(value):
    return value if isinstance(value, date) else date.fromisoformat(value)


def meta(row, fields=META):
    return {key: row[key] for key in fields}


def checked_binding(spec):
    """Resolve a report's exact bytes, including explicitly saved code snapshots."""
    path = Path(spec["path"])
    candidates = [path]
    if path.name == "ownership_multi_cik.py":
        candidates += [MULTI_BASE / "ownership_multi_cik_selector_executed_mac.py",
                       MULTI_BASE / "ownership_multi_cik_parser_executed_container.py"]
    if path.name == "ownership_multi_cik_sources.py":
        candidates.append(MULTI_BASE / "ownership_multi_cik_sources_executed_container.py")
    for candidate in candidates:
        if not (ROOT / candidate).is_file():
            continue
        raw = read(candidate)
        if sha(raw) == spec["sha256"] and len(raw) == spec["bytes"]:
            return raw
    raise ValueError("No exact preserved bytes for a bound input: " + str(path))


def no_promotions(value):
    if isinstance(value, dict):
        for key, item in value.items():
            require(key.lower() not in FORBIDDEN_KEYS, "Public report contains a private association key")
            if key in {"known_at", "available_at", "effective_start", "effective_end"}:
                require(item is None, "Public audit supplied a historical fact bound")
            if key in {"historical_security_link_created", "model_ready", "known_at_inferred",
                       "available_at_inferred", "historical_availability_inferred",
                       "continuous_intervals_inferred", "continuous_identity_links_inferred"}:
                require(item is False, "Public audit promoted unreviewed source evidence")
            if key in {"historical_security_links_created", "source_approvals_created", "human_reviews_created"}:
                require(item == 0, "Audit created approvals or historical links")
            no_promotions(item)
    elif isinstance(value, list):
        for item in value:
            no_promotions(item)


def cohort(bundle, mq, cq):
    import pyarrow.parquet as pq
    receipt_raw = read(bundle / "receipt.json")
    require(sha(receipt_raw) == BUNDLE_SHA, "Pinned cohort receipt changed")
    receipt = json.loads(receipt_raw)
    require(receipt["cohort_year"] == 2020 and receipt["source_quarter"] == "2019Q4", "Unexpected cohort")
    require(receipt["model_ready"] is False and receipt["final_period_opened"] is False, "Unexpected evidence status")
    cutoff = datetime.fromisoformat(receipt["information_cutoff"])
    require(cutoff.tzinfo is not None, "Cutoff is timezone naive")
    cutoff_day = cutoff.astimezone(ET).date()
    loaded = {}
    for key in ("cohort_summary", "observations", "sec_occurrences"):
        rows = []
        for spec in receipt["tables"][key]["parts"]:
            raw = read(bundle / spec["file"])
            require(sha(raw) == spec["sha256"] and len(raw) == spec["bytes"], "Pinned cohort part changed")
            table = pq.read_table(io.BytesIO(raw))
            require(table.num_rows == spec["rows"], "Pinned part row count changed")
            rows.extend(table.to_pylist())
        require(len(rows) == receipt["tables"][key]["rows"], "Pinned table row count changed")
        loaded[key] = rows
    tsv_raw = read(bundle / "original_SUBMISSION.tsv")
    require(sha(tsv_raw) == TSV_SHA, "Original SEC quarterly file changed")
    original = list(csv.DictReader(io.StringIO(tsv_raw.decode("utf-8-sig")), delimiter="\t"))
    require(len(original) == len(loaded["sec_occurrences"]) == 38145, "Quarterly accounting changed")
    by_record = {}
    for row in loaded["sec_occurrences"]:
        ordinal = row["source_tsv_record"]
        require(ordinal not in by_record and 2 <= ordinal <= 38146, "Duplicate/outside SEC ordinal")
        require(meta(row) == meta(original[ordinal - 2]), "Original SEC metadata differs")
        require(row["source_sha256"] == TSV_SHA, "SEC lineage changed")
        observed_day = datetime.strptime(row["FILING_DATE"], "%d-%b-%Y").date()
        relation = ("BEFORE_CUTOFF_DATE" if observed_day < cutoff_day else
                    "CUTOFF_DAY_TIME_UNRESOLVED" if observed_day == cutoff_day else "AFTER_CUTOFF_DATE")
        require(row["cutoff_date_relation"] == relation and day(row["filing_date"]) == observed_day,
                "Stored SEC date relation differs from original filing date")
        require(row["issuer_cik_comparison_key"] == positive_cik(row["ISSUERCIK"]), "Stored SEC CIK normalization differs")
        by_record[ordinal] = row
    require(set(by_record) == set(range(2, 38147)), "SEC occurrence ordinal coverage incomplete")
    summaries = {row["security_id"]: row for row in loaded["cohort_summary"]}
    require(len(summaries) == len(loaded["cohort_summary"]) == 4122, "Cohort summary accounting changed")
    by_security = defaultdict(list)
    observation_ids = set()
    for row in loaded["observations"]:
        require(row["security_id"] in summaries and row["observation_id"] not in observation_ids, "Observation membership changed")
        observation_ids.add(row["observation_id"])
        sec = by_record[row["source_tsv_record"]]
        require((row["accession"], row["sec_issuer_cik_raw"], row["sec_symbol_raw"], row["sec_source_sha256"])
                == (sec["ACCESSION_NUMBER"], sec["ISSUERCIK"], sec["ISSUERTRADINGSYMBOL"], TSV_SHA), "Observation source metadata changed")
        require(day(row["filing_date"]) == day(sec["filing_date"])
                and row["cutoff_date_relation"] == sec["cutoff_date_relation"]
                and row["sec_issuer_cik_comparison_key"] == sec["issuer_cik_comparison_key"], "Observation date/key mismatch")
        by_security[row["security_id"]].append(row)
    require(len(observation_ids) == 31466, "Observation count changed")
    multi_ids, clock_ids = set(), set()
    for sid, summary in summaries.items():
        rows = by_security[sid]
        earlier = [x for x in rows if day(x["filing_date"]) < cutoff_day]
        same_day = [x for x in rows if day(x["filing_date"]) == cutoff_day]
        keys = {positive_cik(x["sec_issuer_cik_raw"]) for x in earlier} - {""}
        require(sorted(keys) == json.loads(summary["earlier_issuer_cik_comparison_keys_json"]), "Summary earlier CIK set differs")
        require(len(rows) == summary["observation_rows"] and len({x["source_tsv_record"] for x in rows}) == summary["sec_occurrences"], "Summary occurrence accounting differs")
        require(len({x["source_tsv_record"] for x in earlier}) == summary["earlier_date_sec_occurrences"]
                and len({x["source_tsv_record"] for x in same_day}) == summary["cutoff_day_sec_occurrences"], "Summary date accounting differs")
        if len(keys) > 1:
            multi_ids.add(sid)
        if same_day and not earlier:
            require(len(same_day) == len(rows), "Cutoff-only case has later source dates")
            clock_ids.add(sid)
    require(multi_ids == {sid for sid, row in summaries.items() if row["observation_status"] == "MULTIPLE_EARLIER_ISSUER_KEYS_OBSERVED"}
            and len(multi_ids) == 7, "Complete seven-case selection differs")
    require(clock_ids == {sid for sid, row in summaries.items() if row["observation_status"] == "CUTOFF_DAY_OBSERVATIONS_ONLY"}
            and len(clock_ids) == 14, "Complete 14-case selection differs")
    group_by_ordinals = {frozenset(x["source_tsv_record"] for x in by_security[sid]): sid for sid in multi_ids}
    require(len(group_by_ordinals) == len(mq["groups"]) == 7, "Multi case membership ambiguous")
    all_multi_ordinals, selected_multis = set(), []
    for group in mq["groups"]:
        ordinals = [x["source_tsv_record"] for x in group["original_source_occurrences"]]
        require(len(ordinals) == len(set(ordinals)), "Multi original occurrence omitted or collapsed")
        sid = group_by_ordinals.pop(frozenset(ordinals))
        rows = by_security[sid]
        require(group["observation_rows"] == len(rows), "Multi observation multiplicity changed")
        require(group["public_symbols"] == sorted({x["sec_symbol_raw"] for x in rows}), "Multi public symbol values differ")
        for queued in group["original_source_occurrences"]:
            require(meta(queued, MULTI_META) == meta(by_record[queued["source_tsv_record"]], MULTI_META), "Multi source occurrence mismatch")
        earlier = [x for x in rows if day(x["filing_date"]) < cutoff_day]
        keys = sorted({positive_cik(x["sec_issuer_cik_raw"]) for x in earlier} - {""})
        require(group["distinct_earlier_ciks"] == keys, "Distinct source CIK lost")
        chosen = []
        for key in keys:
            earliest = min((x for x in earlier if positive_cik(x["sec_issuer_cik_raw"]) == key),
                           key=lambda x: (day(x["filing_date"]), x["accession"], x["source_tsv_record"]))
            chosen.append({**meta(by_record[earliest["source_tsv_record"]], MULTI_META), "source_tsv_record": earliest["source_tsv_record"]})
        require(group["selected_public_occurrences"] == chosen, "Multi earliest source-per-CIK queue changed")
        selected_multis.extend({"case_id": group["case_id"], **x} for x in chosen)
        all_multi_ordinals.update(ordinals)
    require(not group_by_ordinals and mq["selected_occurrences"] == selected_multis, "Multi queue lost a case")
    require(len(selected_multis) == len({x["ACCESSION_NUMBER"] for x in selected_multis}) == 14, "Multi unique-source coverage changed")
    require(len(all_multi_ordinals) == sum(len(by_security[sid]) for sid in multi_ids) == 129, "Multi metadata occurrences lost")
    multi_accessions = {by_record[n]["ACCESSION_NUMBER"] for n in all_multi_ordinals}
    clock_observations = [x for sid in clock_ids for x in by_security[sid]]
    clock_accessions = {x["accession"] for x in clock_observations}
    expected_clock = sorted((x for x in loaded["sec_occurrences"] if x["ACCESSION_NUMBER"] in clock_accessions), key=lambda x: x["source_tsv_record"])
    require(len(expected_clock) == len(cq["source_occurrences"]), "Clock repeated source occurrence lost")
    for observed, queued in zip(expected_clock, cq["source_occurrences"], strict=True):
        require(meta(observed) == meta(queued) and observed["source_tsv_record"] == queued["source_tsv_record"]
                and queued["source_sha256"] == TSV_SHA, "Clock queue differs from complete original accession set")
    require(len(clock_accessions) == 39 and len(clock_observations) == 39, "Clock fixed-cohort count changed")
    return cutoff, by_security, clock_ids, {
        "cohort_summaries_recomputed": 4122, "observations_reconciled": 31466,
        "original_sec_occurrences_reconciled": 38145, "multi_cik_cases_recomputed": 7,
        "multi_cik_contributing_occurrences": len(all_multi_ordinals), "multi_cik_distinct_selected_sources": 14,
        "multi_cik_metadata_repeat_occurrences": len(all_multi_ordinals) - len(multi_accessions),
        "cutoff_day_only_cases_recomputed": 14, "cutoff_distinct_sources": len(clock_accessions),
        "cutoff_all_metadata_occurrences": len(expected_clock), "cutoff_metadata_repetitions": len(expected_clock) - len(clock_accessions),
        "names_ccm_matches_reused_from_pinned_bundle": True, "licensed_associations_exported": False}


class IssuerEnd(Exception):
    pass


def independently_parse(body, row):
    """Read header roles as lines and issuer prefix with independent SAX events."""
    accession = row["ACCESSION_NUMBER"]
    require(len(body) <= 8 * 1024 * 1024 and body.startswith(("<SEC-DOCUMENT>" + accession + ".txt").encode()), "Original source wrapper differs")
    hs = body.index(b"<SEC-HEADER>") + len(b"<SEC-HEADER>")
    he = body.index(b"</SEC-HEADER>", hs)
    header = body[hs:he]
    require(header.startswith((accession + ".hdr.sgml").encode()), "Header accession wrapper differs")

    def header_value(chunk, key):
        values = [line.split(b":", 1)[1].strip().decode("utf-8") for line in chunk.splitlines()
                  if line.strip().startswith(key.encode() + b":")]
        require(len(values) == 1, "Ambiguous header metadata")
        return values[0]

    acceptance = [line.split(b">", 1)[1].decode().strip() for line in header.splitlines() if line.startswith(b"<ACCEPTANCE-DATETIME>")]
    require(len(acceptance) == 1, "Acceptance clock not unique")
    accepted = datetime.strptime(acceptance[0], "%Y%m%d%H%M%S").replace(tzinfo=ET)
    roles, active = [], None
    for line in header.splitlines(keepends=True):
        if line.startswith((b"ISSUER:", b"REPORTING-OWNER:", b"FILER:", b"SUBJECT COMPANY:", b"FILED BY:")):
            active = {"role": line.split(b":", 1)[0].decode(), "lines": []}
            roles.append(active)
        elif active is not None:
            active["lines"].append(line)
    for role in roles:
        fragment = b"".join(role.pop("lines"))
        role["cik"] = positive_cik(header_value(fragment, "CENTRAL INDEX KEY"))
        require(bool(role["cik"]), "Invalid header role CIK")
        if role["role"] == "ISSUER":
            role["name"] = header_value(fragment, "COMPANY CONFORMED NAME")
    issuers = [x for x in roles if x["role"] == "ISSUER"]
    require(len(issuers) == 1 and any(x["role"] == "REPORTING-OWNER" for x in roles), "Ownership roles missing")
    require(all(x["role"] in {"ISSUER", "REPORTING-OWNER"} for x in roles), "Unsupported ownership role")
    candidates = []
    for start in (m.end() for m in re.finditer(rb"<DOCUMENT>", body)):
        end = body.index(b"</DOCUMENT>", start)
        text = body.index(b"<TEXT>", start, end)
        wrapper = body[start:text]
        kinds = [line[len(b"<TYPE>"):].strip().decode() for line in wrapper.splitlines() if line.startswith(b"<TYPE>")]
        require(len(kinds) == 1, "Ambiguous document type wrapper")
        if kinds[0] == row["DOCUMENT_TYPE"]:
            candidates.append((text + len(b"<TEXT>"), end))
    require(len(candidates) == 1, "Primary document is ambiguous")
    ts, te = candidates[0]
    xb = body.index(b"<XML>", ts, te) + len(b"<XML>")
    xe = body.index(b"</issuer>", xb, te) + len(b"</issuer>")
    prefix = body[xb:xe]
    trim = len(prefix) - len(prefix.lstrip())
    data = prefix.lstrip()
    require(len(prefix) <= 128 * 1024 and b"<!DOCTYPE" not in prefix.upper() and b"<!ENTITY" not in prefix.upper(), "Unsupported XML prefix declaration")
    parser = xml.parsers.expat.ParserCreate(namespace_separator="}")
    stack, values, spans, metadata = [], {}, {}, defaultdict(str)
    issuer_bounds = []

    def start_element(name, _attrs):
        tag = name.rsplit("}", 1)[-1]
        stack.append(tag)
        require(len(stack) != 1 or tag == "ownershipDocument", "Unexpected ownership root")
        if tag == "issuer":
            require(len(stack) == 2, "Issuer role is nested")
            issuer_bounds.append(xb + trim + parser.CurrentByteIndex)
        if len(stack) == 3 and stack[-2] == "issuer":
            require(tag not in values, "Duplicate issuer field")
            values[tag] = ""
            spans[tag] = [xb + trim + data.index(b">", parser.CurrentByteIndex) + 1]
        require(not (len(stack) > 3 and stack[1] == "issuer"), "Nested issuer field")

    def chars(value):
        if len(stack) == 3 and stack[-2] == "issuer":
            values[stack[-1]] += value
        elif len(stack) == 2 and stack[-1] != "issuer":
            metadata[stack[-1]] += value

    def end_element(name):
        tag = name.rsplit("}", 1)[-1]
        if len(stack) == 3 and stack[-2] == "issuer":
            spans[tag].append(xb + trim + parser.CurrentByteIndex)
        if tag == "issuer":
            require(len(stack) == 2, "Unexpected issuer end")
            issuer_bounds.append(xb + trim + data.index(b">", parser.CurrentByteIndex) + 1)
            raise IssuerEnd
        require(stack.pop() == tag, "XML stack mismatch")

    parser.StartElementHandler = start_element
    parser.CharacterDataHandler = chars
    parser.EndElementHandler = end_element
    try:
        parser.Parse(data, False)
    except IssuerEnd:
        pass
    require(len(issuer_bounds) == 2 and issuer_bounds[1] == xe, "XML parser did not stop at issuer end")
    require(set(values) == {"issuerCik", "issuerName", "issuerTradingSymbol"}, "Issuer field set differs")
    return {"accession": header_value(header, "ACCESSION NUMBER"),
            "form": header_value(header, "CONFORMED SUBMISSION TYPE"),
            "filed": header_value(header, "FILED AS OF DATE"),
            "changed": header_value(header, "DATE AS OF CHANGE"), "acceptance_raw": acceptance[0],
            "accepted": accepted, "roles": roles, "issuer": issuers[0], "xml": values,
            "xml_form": metadata["documentType"], "xml_spans": spans,
            "xml_prefix_bounds": [xb, xe], "xml_issuer_bounds": issuer_bounds}


def verify_record(body, row, record, cutoff):
    result = independently_parse(body, row)

    def check_spans(value):
        if isinstance(value, dict):
            if {"raw_value", "byte_start", "byte_end_exclusive"} <= set(value):
                require(body[value["byte_start"]:value["byte_end_exclusive"]].decode("utf-8") == value["raw_value"], "Reported raw header/document span differs")
            for item in value.values():
                check_spans(item)
        elif isinstance(value, list):
            for item in value:
                check_spans(item)

    check_spans(record)
    require(result["accession"] == row["ACCESSION_NUMBER"] == record["header"]["accession"]["raw_value"], "Accession check failed")
    require(result["form"] == result["xml_form"] == row["DOCUMENT_TYPE"] == record["header"]["form"]["raw_value"], "Document role/form check failed")
    require(result["filed"] == datetime.strptime(row["FILING_DATE"], "%d-%b-%Y").strftime("%Y%m%d"), "Filing day differs")
    require(result["accepted"].isoformat() == record["header"]["acceptance_eastern"]
            and result["accepted"].astimezone(timezone.utc).isoformat() == record["header"]["acceptance_utc"], "Acceptance timezone conversion differs")
    require(result["acceptance_raw"] == record["header"]["acceptance_raw"]["raw_value"], "Raw clock differs")
    require(result["filed"] == record["header"]["filed_as_of_date"]["raw_value"] and result["changed"] == record["header"]["date_as_of_change"]["raw_value"], "Header metadata differs")
    require(len(result["roles"]) == len(record["header"]["roles"]), "Reporting-owner multiplicity lost")
    for expected, reported in zip(result["roles"], record["header"]["roles"], strict=True):
        require(expected["role"] == reported["role"] and expected["cik"] == reported["cik_comparison_key"], "Issuer/reporting-owner role swap")
        begin, end = reported["block_byte_start"], reported["block_byte_end_exclusive"]
        require(body[begin:end].startswith((expected["role"] + ":").encode())
                and begin <= reported["cik"]["byte_start"] < reported["cik"]["byte_end_exclusive"] <= end, "Role CIK span escapes its source block")
        if expected["role"] == "ISSUER":
            require(expected["name"] == reported["name"]["raw_value"], "Header issuer name differs")
    for key, expected in result["xml"].items():
        field = record["ownership_xml"]["issuer_fields"][key]
        require(expected == field["parsed_text"], "XML entity decoding differs")
        require(result["xml_spans"][key] == [field["byte_start"], field["byte_end_exclusive"]], "XML source span differs")
        require(body[field["byte_start"]:field["byte_end_exclusive"]].decode("utf-8") == field["raw_xml_text"], "XML raw source bytes differ")
    for name, expected in (("issuer_prefix", result["xml_prefix_bounds"]), ("issuer_element", result["xml_issuer_bounds"])):
        require([record["ownership_xml"][name + "_byte_start"], record["ownership_xml"][name + "_byte_end_exclusive"]] == expected, "XML bounded-inspection extent differs")
    require(record["ownership_xml"]["parser_stopped_at_issuer_end"] is True and record["ownership_xml"]["full_xml_validity_claimed"] is False, "XML scope overclaimed")
    comparisons = {
        "header_issuer_cik_matches_queue": result["issuer"]["cik"] == row["ISSUERCIK"],
        "xml_issuer_cik_matches_queue": positive_cik(result["xml"]["issuerCik"]) == row["ISSUERCIK"],
        "header_and_xml_issuer_cik_agree": result["issuer"]["cik"] == positive_cik(result["xml"]["issuerCik"]),
        "header_issuer_name_exactly_matches_queue": result["issuer"]["name"] == row["ISSUERNAME"],
        "xml_issuer_name_exactly_matches_queue": result["xml"]["issuerName"] == row["ISSUERNAME"],
        "xml_symbol_exactly_matches_queue": result["xml"]["issuerTradingSymbol"] == row["ISSUERTRADINGSYMBOL"],
        "header_form_xml_form_and_queue_agree": True, "header_filing_date_matches_queue": True,
        "header_accession_matches_queue": True,
        "xml_cik_literal_has_same_zero_padding_as_queue": result["xml"]["issuerCik"] == row["ISSUERCIK"]}
    require(record["comparisons"] == comparisons, "Reported comparison differs from independent parser")
    core = all(comparisons[k] for k in ("header_issuer_cik_matches_queue", "xml_issuer_cik_matches_queue", "header_and_xml_issuer_cik_agree", "xml_symbol_exactly_matches_queue"))
    names = comparisons["header_issuer_name_exactly_matches_queue"] and comparisons["xml_issuer_name_exactly_matches_queue"]
    status = ("ORIGINAL_ISSUER_CIK_SYMBOL_AND_NAMES_CONFIRMED" if core and names else
              "ORIGINAL_ISSUER_CIK_SYMBOL_CONFIRMED_WITH_NAME_DIFFERENCE" if core else "ORIGINAL_SOURCE_IDENTITY_DIFFERENCE_UNRESOLVED")
    require(record["status"] == status, "Identity status differs")
    owners = [x for x in result["roles"] if x["role"] == "REPORTING-OWNER"]
    require(len(owners) == record["header"]["reporting_owner_role_count"], "Owner count differs")
    equal_owners = sum(x["cik"] == result["issuer"]["cik"] for x in owners)
    require(equal_owners == record["header"]["reporting_owner_ciks_equal_to_issuer_count"], "Equal owner/issuer CIK lost")
    delta = (result["accepted"] - cutoff).total_seconds()
    relation = "BEFORE_CUTOFF" if delta < 0 else "AFTER_CUTOFF" if delta > 0 else "AT_CUTOFF"
    if "acceptance_vs_cutoff" in record:
        require(record["acceptance_vs_cutoff"] == relation and record["acceptance_minus_cutoff_seconds"] == delta, "Strict cutoff clock differs")
    if "acceptance_precedes_information_cutoff" in record:
        require(record["acceptance_precedes_information_cutoff"] == (delta < 0), "Multi source cutoff differs")
    no_promotions(record)
    return {"relation": relation, "owner_roles": len(owners), "equal_owner_issuer_ciks": equal_owners,
            "acceptance_eastern": result["accepted"].isoformat(),
            "comparisons": comparisons, "entity_fields": sum("&" in body[a:b].decode("utf-8") for a, b in result["xml_spans"].values())}


def source_checks(report, queue, row_key, cutoff):
    no_promotions(report)
    require(len(report["records"]) == len(queue), "Report source occurrence count differs")
    source_map = report["source_receipts"]
    require(set(source_map) == {x["ACCESSION_NUMBER"] for x in queue}, "Report original accession coverage differs")
    results, bodies = [], {}
    for accession, source in source_map.items():
        raw = checked_binding(source)
        require(source["http_status"] == 200 and source["url"] == source["final_url"], "Container HTTP provenance differs")
        require(source["historical_availability_inferred"] is False, "Retrieval time became historical availability")
        bodies[accession] = raw
        receipt_key = "receipt_file" if "receipt_file" in source else "receipt"
        if receipt_key in source:
            saved = json.loads(checked_binding(source[receipt_key]))
            require(all(source[k] == v for k, v in saved.items()), "Embedded source receipt differs from preserved receipt")
    for queued, record in zip(queue, report["records"], strict=True):
        require(record[row_key] == queued, "Report source metadata repetitions changed")
        accession = queued["ACCESSION_NUMBER"]
        expected_url = f"https://www.sec.gov/Archives/edgar/data/{int(queued['ISSUERCIK'])}/{accession.replace('-', '')}/{accession}.txt"
        require(source_map[accession]["url"] == expected_url, "Container changed original candidate path")
        result = verify_record(bodies[accession], queued, record, cutoff)
        results.append(result)
    return results, {"original_sources_rehashed": len(bodies), "source_bytes": sum(map(len, bodies.values())),
                     "metadata_occurrences_checked": len(queue), "header_role_occurrences": sum(r["owner_roles"] + 1 for r in results),
                     "reporting_owner_occurrences": sum(r["owner_roles"] for r in results),
                     "owner_ciks_equal_to_issuer_preserved": sum(r["equal_owner_issuer_ciks"] for r in results),
                     "xml_entity_fields_independently_decoded": sum(r["entity_fields"] for r in results),
                     "clock_relation_counts": dict(Counter(r["relation"] for r in results))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", default="data/private/sec-ownership-corrob/development-v1")
    parser.add_argument("--report", default="reports/ownership_followup_verification.json")
    args = parser.parse_args()
    require(not (ROOT / args.report).exists(), "Verification report already exists; preserve original")
    mq = document(MULTI_BASE / "queue.json")
    cq = document(CLOCK_BASE / "queue.json")
    multi_report = document("reports/ownership_multi_cik_source_validation.json")
    clock_report = document("reports/ownership_cutoff_clock_resolved.json")
    cutoff, by_security, clock_ids, selection = cohort(Path(args.bundle), mq, cq)
    require(cutoff.isoformat() == "2019-12-31T21:00:00+00:00" and mq["information_cutoff"] == cq["information_cutoff"] == cutoff.isoformat(), "Cutoff mismatch")
    import exchange_calendars
    calendar = exchange_calendars.get_calendar("XNYS")
    first_session = calendar.date_to_session("2020-01-01", direction="next")
    previous_session = calendar.previous_session(first_session)
    require(calendar.session_close(previous_session).to_pydatetime() == cutoff, "Independent exchange close differs")
    multi_results, multi_summary = source_checks(multi_report, mq["selected_occurrences"], "queued_public_source_occurrence", cutoff)
    clock_results, clock_summary = source_checks(clock_report, cq["source_occurrences"], "quarterly_source_occurrence", cutoff)
    require(len(multi_report["groups"]) == len(mq["groups"]) == multi_report["summary"]["cases"] == 7, "Reported seven-case coverage differs")
    for queued, group in zip(mq["groups"], multi_report["groups"], strict=True):
        require(all(group[key] == value for key, value in queued.items()), "Reported multi-case metadata occurrences changed")
        records = [r for r in multi_report["records"] if r["case_id"] == queued["case_id"]]
        confirmed = sum(r["status"] == "ORIGINAL_ISSUER_CIK_SYMBOL_AND_NAMES_CONFIRMED" for r in records)
        require(len(records) == len(queued["selected_public_occurrences"]) and group["selected_sources_confirmed"] == confirmed,
                "Reported multi-case confirmed-source count differs")
        expected_status = "MULTIPLE_ORIGINAL_ISSUERS_REPORT_SAME_LITERAL_SYMBOL" if confirmed == len(records) else "SOURCE_DIFFERENCE_OR_STRUCTURE_REQUIRES_REVIEW"
        require(group["source_status"] == expected_status, "Reported multi-case source status differs")
    for result, summary, map_names in (
        (multi_summary, multi_report["summary"], {"original_sources_rehashed": "preserved_original_sources", "source_bytes": "original_source_bytes", "reporting_owner_occurrences": "header_reporting_owner_role_occurrences"}),
        (clock_summary, clock_report["summary"], {"original_sources_rehashed": "original_sources_preserved", "source_bytes": "source_bytes", "reporting_owner_occurrences": "reporting_owner_role_occurrences"})):
        for actual_key, report_key in map_names.items():
            require(result[actual_key] == summary[report_key], "Public report aggregate differs")
    require(multi_report["summary"]["acceptance_precedes_information_cutoff_count"] == sum(r["relation"] == "BEFORE_CUTOFF" for r in multi_results), "Multi acceptance count differs")
    require(clock_report["summary"]["occurrence_acceptance_relation_counts"] == clock_summary["clock_relation_counts"], "Clock occurrence aggregate differs")
    for report, results in ((multi_report, multi_results), (clock_report, clock_results)):
        expected = {key: sum(r["comparisons"][key] for r in results) for key in results[0]["comparisons"]}
        require(report["summary"]["comparison_true_counts"] == expected, "Comparison aggregate differs")
    require(multi_report["summary"]["status_counts"] == dict(Counter(r["status"] for r in multi_report["records"])), "Multi inspection-status aggregate differs")
    require(clock_report["summary"]["original_inspection_status_counts"] == dict(Counter(r["status"] for r in clock_report["records"])), "Clock inspection-status aggregate differs")
    require(clock_report["summary"]["document_type_counts"] == dict(Counter(r["DOCUMENT_TYPE"] for r in cq["source_occurrences"])), "Clock form aggregate differs")
    require(clock_report["summary"]["minimum_acceptance_eastern"] == min(r["acceptance_eastern"] for r in clock_results)
            and clock_report["summary"]["maximum_acceptance_eastern"] == max(r["acceptance_eastern"] for r in clock_results), "Clock extremes differ")
    clocks_by_ordinal = {row["source_tsv_record"]: result["relation"] for row, result in zip(cq["source_occurrences"], clock_results, strict=True)}
    by_accession = defaultdict(set)
    for row, result in zip(cq["source_occurrences"], clock_results, strict=True):
        by_accession[row["ACCESSION_NUMBER"]].add(result["relation"])
    require(all(len(values) == 1 for values in by_accession.values()), "Repeated accession clock inconsistent")
    unique_relation = dict(Counter(next(iter(values)) for values in by_accession.values()))
    require(clock_report["summary"]["distinct_accession_acceptance_relation_counts"] == unique_relation, "Distinct accession tally differs")
    case_statuses, any_relation = Counter(), Counter()
    for sid in clock_ids:
        values = {clocks_by_ordinal[x["source_tsv_record"]] for x in by_security[sid]}
        status = ("ALL_ORIGINAL_ACCEPTANCES_BEFORE_CUTOFF" if values == {"BEFORE_CUTOFF"} else
                  "ALL_ORIGINAL_ACCEPTANCES_AFTER_CUTOFF" if values == {"AFTER_CUTOFF"} else
                  "ORIGINAL_ACCEPTANCES_BOTH_BEFORE_AND_AFTER" if values == {"BEFORE_CUTOFF", "AFTER_CUTOFF"} else
                  "HAS_AT_CUTOFF_OR_UNRESOLVED_ACCEPTANCE")
        case_statuses[status] += 1
        any_relation.update(values)
    require(dict(case_statuses) == clock_report["summary"]["case_clock_status_counts"], "Private 14-case clock regrouping differs")
    require({key: any_relation[key] for key in ("BEFORE_CUTOFF", "AT_CUTOFF", "AFTER_CUTOFF", "UNRESOLVED")}
            == clock_report["summary"]["case_counts_with_at_least_one_acceptance"], "Case clock presence differs")
    mac_multi = document("reports/ownership_multi_cik_originals.json")
    mac_clock = document("reports/ownership_cutoff_clock_audit.json")
    no_promotions(mac_multi)
    no_promotions(mac_clock)
    mac_multi_collection = json.loads(checked_binding(mac_multi["inputs"]["collection_receipt"]))
    mac_clock_collection = json.loads(checked_binding(mac_clock["collection_receipt"]))
    for collection, expected_accessions in ((mac_multi_collection, {x["ACCESSION_NUMBER"] for x in mq["selected_occurrences"]}),
                                            (mac_clock_collection, set(by_accession))):
        require(len(collection["attempts"]) == len(expected_accessions), "Mac denied queue accounting differs")
        require({x["accession"] for x in collection["attempts"]} == expected_accessions
                and all(x["http_status"] == 403 for x in collection["attempts"]), "Mac403 ledger changed")
    require(mac_multi["summary"]["preserved_original_sources"] == mac_clock["summary"]["original_sources_preserved"] == 0, "Original Mac403 result overwritten")
    prior = document("reports/sec_ownership_original_followup.json")
    earlier_accessions = {r["queued_public_source_occurrence"]["ACCESSION_NUMBER"] for r in prior["records"]}
    current_accessions = {r["ACCESSION_NUMBER"] for r in mq["selected_occurrences"]} | set(by_accession)
    require(len(current_accessions) == 53 and not earlier_accessions.intersection(current_accessions), "Previously inspected accession repeated")
    for path, expected in mac_multi["protected_before"].items():
        require(sha(read(path)) == expected, "Previously protected research evidence changed")
    for spec in multi_report["inputs"].values():
        if isinstance(spec, dict) and {"path", "sha256", "bytes"} <= set(spec):
            checked_binding(spec)
    for spec in clock_report["inputs"].values():
        checked_binding(spec)
    for key in ("queue", "collection_receipt", "original_mac_attempt_report", "script",
                "metadata_inspector_script", "public_collection_script", "preserved_original_audit_script"):
        checked_binding(clock_report[key])
    report = {
        "schema_version": 1, "status": "PASS_INDEPENDENT_OFFLINE_OWNERSHIP_FOLLOWUP_VERIFICATION",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "verifier": {"path": str(Path(__file__).relative_to(ROOT)), "sha256": sha(Path(__file__).read_bytes())},
        "method": "Recomputed both complete source cohorts from pinned summaries/observations; checked public metadata against every original SEC quarterly ordinal; parsed original header roles as lines and issuer XML prefix with independent Expat SAX callbacks; checked exact byte spans and timezone-aware strict cutoff comparisons.",
        "selection": selection, "multi_cik": multi_summary, "cutoff_clock": {**clock_summary, "case_status_counts": dict(case_statuses)},
        "calendar": {"name": "XNYS", "exchange_calendars_version": exchange_calendars.__version__, "cutoff_utc": cutoff.isoformat(), "cutoff_eastern": cutoff.astimezone(ET).isoformat()},
        "preservation": {"original_mac_http_403_attempts_retained": 53, "distinct_container_http_200_sources_verified": 53,
                         "original_mac_reports_not_replaced": True, "protected_previous_evidence_unchanged": True},
        "scope": {"licensed_associations_read_only_on_authorized_host": True, "licensed_rows_or_identifiers_exported": False,
                  "underlying_names_ccm_matching_rerun": False, "previous_47_source_inspections_rerun": False,
                  "transaction_or_holdings_xml_parsed": False, "full_xml_validity_claimed": False,
                  "known_at_inferred": False, "available_at_inferred": False,
                  "continuous_identity_links_inferred": False, "source_approvals_created": 0,
                  "human_reviews_created": 0, "model_ready": False},
        "verified_input_bindings": INPUTS,
        "limits": ["Acceptance is a SEC header clock; it is not first public availability.",
                   "Issuer facts do not establish a vendor-security link or continuous identity interval.",
                   "Completeness is relative to the pinned saved cohort; earlier Names/CCM selection was not rerun."]}
    no_promotions(report)
    for path, spec in INPUTS.items():
        raw = (ROOT / path).read_bytes()
        require(sha(raw) == spec["sha256"] and len(raw) == spec["bytes"], "Input changed during verification")
    destination = ROOT / args.report
    with destination.open("x") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "selection": selection, "multi_cik": multi_summary,
                      "cutoff_clock": report["cutoff_clock"], "report_sha256": sha(destination.read_bytes())}, indent=2))


if __name__ == "__main__":
    main()
