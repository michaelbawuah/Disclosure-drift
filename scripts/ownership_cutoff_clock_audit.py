"""Audit every original SEC accession for the 14 cutoff-day-only 2020 cases.

Run on the authorized data host. Licensed associations stay in the output's
private subdirectory. SEC metadata and aggregate clock facts may be published.
No acceptance timestamp is converted into historical public availability.
"""
import argparse
import collections
import concurrent.futures
import csv
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import exchange_calendars
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from disclosure_research.protocol import canonical_hash, load_protocol, verify_lock  # noqa: E402
from disclosure_research.universe import year_start_window  # noqa: E402

RECEIPT_SHA = "85358e4f928687ed9fc3da3813e87980321bbd155b24c952f7a955c5c92a8442"
PROTOCOL_SHA = "3951be086ed9a74ec69a304004ebcb5aed63bac161e043ff92ae4f51b8e325d9"
PUBLIC_FIELDS = ("ACCESSION_NUMBER", "DOCUMENT_TYPE", "FILING_DATE", "ISSUERCIK",
                 "ISSUERNAME", "ISSUERTRADINGSYMBOL", "PERIOD_OF_REPORT", "DATE_OF_ORIG_SUB")
UA = "Michael Baffour Awuah Disclosure-drift research https://github.com/michaelbawuah/Disclosure-drift"
MAX_BYTES = 8 * 1024 * 1024
RATE_LOCK = threading.Lock()
LAST_REQUEST = 0.0


def digest(body):
    return hashlib.sha256(body).hexdigest()


def dump(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def bound(path):
    raw = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(raw), "bytes": len(raw)}


def write_new(path, value, private=False):
    raw = value if isinstance(value, bytes) else dump(value)
    with path.open("xb") as stream:
        os.chmod(path, 0o600 if private else 0o400)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def one(matches, label):
    if len(matches) != 1:
        raise ValueError(f"Expected one {label}; observed {len(matches)}")
    return matches[0]


def line_field(body, label, offset=0):
    match = one(list(re.finditer(rb"(?m)^[\t ]*" + re.escape(label.encode()) + rb":[\t ]*([^\r\n]+)", body)), label)
    return {"raw_value": match.group(1).decode("utf-8"), "byte_start": offset + match.start(1), "byte_end_exclusive": offset + match.end(1)}


def tag_field(body, tag, offset=0):
    match = one(list(re.finditer(rb"<" + tag.encode() + rb">([^\r\n<]+)", body)), tag)
    return {"raw_value": match.group(1).decode("utf-8"), "byte_start": offset + match.start(1), "byte_end_exclusive": offset + match.end(1)}


def cik(value):
    value = value.strip()
    if not re.fullmatch(r"[0-9]{1,10}", value) or int(value) == 0:
        raise ValueError("Unsupported nonpositive/non-ASCII CIK literal")
    return value.zfill(10)


def local(tag):
    return tag.rsplit("}", 1)[-1]


def inspect(body, row):
    accession = row["ACCESSION_NUMBER"]
    if not body.startswith(("<SEC-DOCUMENT>" + accession + ".txt").encode()):
        raise ValueError("Original SEC-DOCUMENT accession differs from queue")
    hmatch = one(list(re.finditer(rb"<SEC-HEADER>(.*?)</SEC-HEADER>", body, re.S)), "SEC-HEADER")
    h = hmatch.group(1)
    if len(h) > 1024 * 1024:
        raise ValueError("Header exceeds bounded inspection size")
    if not h.startswith((accession + ".hdr.sgml").encode()):
        raise ValueError("SEC-HEADER wrapper accession differs")
    hoff = hmatch.start(1)
    header_accession = line_field(h, "ACCESSION NUMBER", hoff)
    header_form = line_field(h, "CONFORMED SUBMISSION TYPE", hoff)
    filed_date = line_field(h, "FILED AS OF DATE", hoff)
    changed_date = line_field(h, "DATE AS OF CHANGE", hoff)
    acceptance_raw = tag_field(h, "ACCEPTANCE-DATETIME", hoff)
    acceptance = dt.datetime.strptime(acceptance_raw["raw_value"], "%Y%m%d%H%M%S").replace(tzinfo=ZoneInfo("America/New_York"))
    if not dt.datetime(2019, 10, 1, tzinfo=ZoneInfo("America/New_York")) <= acceptance < dt.datetime(2020, 1, 1, tzinfo=ZoneInfo("America/New_York")):
        raise ValueError("Acceptance lies outside queued 2019Q4 source window")
    if header_accession["raw_value"] != accession or header_form["raw_value"] != row["DOCUMENT_TYPE"]:
        raise ValueError("Header accession/form differs from queued source")
    if filed_date["raw_value"] != dt.datetime.strptime(row["FILING_DATE"], "%d-%b-%Y").strftime("%Y%m%d"):
        raise ValueError("Original header filing date differs from queued source")

    markers = list(re.finditer(rb"(?m)^(ISSUER|REPORTING-OWNER|FILER|SUBJECT COMPANY|FILED BY):[^\r\n]*", h))
    roles = []
    for ordinal, marker in enumerate(markers, start=1):
        stop = markers[ordinal].start() if ordinal < len(markers) else len(h)
        fragment = h[marker.end():stop]
        role = marker.group(1).decode("ascii")
        identity = line_field(fragment, "CENTRAL INDEX KEY", hoff + marker.end())
        entry = {"role": role, "source_role_ordinal": ordinal, "block_byte_start": hoff + marker.start(), "block_byte_end_exclusive": hoff + stop, "cik": identity, "cik_comparison_key": cik(identity["raw_value"])}
        if role == "ISSUER":
            entry["name"] = line_field(fragment, "COMPANY CONFORMED NAME", hoff + marker.end())
        roles.append(entry)
    issuer_header = one([x for x in roles if x["role"] == "ISSUER"], "ISSUER role")
    owners = [x for x in roles if x["role"] == "REPORTING-OWNER"]
    if not owners or any(x["role"] not in {"ISSUER", "REPORTING-OWNER"} for x in roles):
        raise ValueError("Unexpected/missing original ownership-header roles")

    documents = list(re.finditer(rb"<DOCUMENT>(.*?)</DOCUMENT>", body, re.S))
    primary_candidates = []
    for document in documents:
        raw_document = document.group(1)
        split = raw_document.find(b"<TEXT>")
        if split < 0:
            raise ValueError("Missing document TEXT wrapper")
        wrapper = raw_document[:split]
        form = tag_field(wrapper, "TYPE", document.start(1))
        if form["raw_value"] == row["DOCUMENT_TYPE"]:
            primary_candidates.append((document, split, wrapper, form))
    document, split, wrapper, document_form = one(primary_candidates, "primary ownership document")
    filename = tag_field(wrapper, "FILENAME", document.start(1))
    sequence = tag_field(wrapper, "SEQUENCE", document.start(1))
    raw_document = document.group(1)
    text_offset = split + len(b"<TEXT>")
    text_body = raw_document[text_offset:]
    xml_marker = one(list(re.finditer(rb"<XML>", text_body)), "XML wrapper")
    xml_base = xml_marker.end()
    xml_body = text_body[xml_base:]
    issuer_match = one(list(re.finditer(rb"<issuer(?:\s[^>]*)?>(.*?)</issuer>", xml_body, re.S)), "XML issuer block")
    prefix = xml_body[:issuer_match.end()]
    if len(prefix) > 128 * 1024:
        raise ValueError("Issuer prefix exceeds 128 KiB")
    if re.search(rb"<!DOCTYPE|<!ENTITY", prefix, re.I):
        raise ValueError("DOCTYPE/entity declarations not accepted in bounded prefix")
    # Stop before reporting-owner, transaction, holdings, remarks and signature XML.
    if re.search(rb"<(?:reportingOwner|nonDerivativeTable|derivativeTable|footnotes|remarks|ownerSignature)(?:\s|>)", prefix):
        raise ValueError("Non-issuer sections occur before the selected issuer block")
    parser = ET.XMLPullParser(events=("start", "end"))
    parser.feed(prefix.lstrip())
    stack = []
    root_element = None
    issuer_element = None
    ended_direct_metadata = {}
    for event, element in parser.read_events():
        if event == "start":
            stack.append(element)
            if len(stack) == 1:
                if local(element.tag) != "ownershipDocument":
                    raise ValueError("Unexpected XML root")
                root_element = element
            if local(element.tag) == "issuer" and len(stack) != 2:
                raise ValueError("Issuer is not a direct child of ownershipDocument")
        else:
            if len(stack) == 2:
                if local(element.tag) == "issuer":
                    if issuer_element is not None:
                        raise ValueError("Multiple direct XML issuer blocks")
                    issuer_element = element
                else:
                    key = local(element.tag)
                    ended_direct_metadata.setdefault(key, []).append(element.text if element.text is not None else "")
            stack.pop()
    if root_element is None or issuer_element is None or len(stack) != 1:
        raise ValueError("Incomplete or ambiguous issuer prefix")
    xml_form = one(ended_direct_metadata.get("documentType", []), "XML documentType")
    if xml_form != row["DOCUMENT_TYPE"]:
        raise ValueError("XML form differs from queued document form")
    xml_fields = {}
    absolute_xml = document.start(1) + text_offset + xml_base
    for tag in ("issuerCik", "issuerName", "issuerTradingSymbol"):
        child = one([child for child in issuer_element if local(child.tag) == tag], tag)
        if list(child):
            raise ValueError("Unexpected nested issuer field markup")
        raw_field = one(list(re.finditer(rb"<" + tag.encode() + rb"(?:\s[^>]*)?>(.*?)</" + tag.encode() + rb">", issuer_match.group(0), re.S)), tag + " source span")
        start = absolute_xml + issuer_match.start() + raw_field.start(1)
        end = absolute_xml + issuer_match.start() + raw_field.end(1)
        xml_fields[tag] = {"parsed_text": child.text if child.text is not None else "", "raw_xml_text": body[start:end].decode("utf-8"), "byte_start": start, "byte_end_exclusive": end}
    xml_cik = cik(xml_fields["issuerCik"]["parsed_text"])
    comparison = {"header_issuer_cik_matches_queue": issuer_header["cik_comparison_key"] == row["ISSUERCIK"], "xml_issuer_cik_matches_queue": xml_cik == row["ISSUERCIK"], "header_and_xml_issuer_cik_agree": issuer_header["cik_comparison_key"] == xml_cik, "header_issuer_name_exactly_matches_queue": issuer_header["name"]["raw_value"] == row["ISSUERNAME"], "xml_issuer_name_exactly_matches_queue": xml_fields["issuerName"]["parsed_text"] == row["ISSUERNAME"], "xml_symbol_exactly_matches_queue": xml_fields["issuerTradingSymbol"]["parsed_text"] == row["ISSUERTRADINGSYMBOL"], "header_form_xml_form_and_queue_agree": True, "header_filing_date_matches_queue": True, "header_accession_matches_queue": True, "xml_cik_literal_has_same_zero_padding_as_queue": xml_fields["issuerCik"]["parsed_text"] == row["ISSUERCIK"]}
    core = all(comparison[key] for key in ("header_issuer_cik_matches_queue", "xml_issuer_cik_matches_queue", "header_and_xml_issuer_cik_agree", "xml_symbol_exactly_matches_queue"))
    names_match = comparison["header_issuer_name_exactly_matches_queue"] and comparison["xml_issuer_name_exactly_matches_queue"]
    status = "ORIGINAL_ISSUER_CIK_SYMBOL_AND_NAMES_CONFIRMED" if core and names_match else "ORIGINAL_ISSUER_CIK_SYMBOL_CONFIRMED_WITH_NAME_DIFFERENCE" if core else "ORIGINAL_SOURCE_IDENTITY_DIFFERENCE_UNRESOLVED"
    return {"status": status, "header": {"source_byte_start": hmatch.start(), "source_byte_end_exclusive": hmatch.end(), "accession": header_accession, "form": header_form, "acceptance_raw": acceptance_raw, "acceptance_eastern": acceptance.isoformat(), "acceptance_utc": acceptance.astimezone(dt.timezone.utc).isoformat(), "filed_as_of_date": filed_date, "date_as_of_change": changed_date, "roles": roles, "reporting_owner_role_count": len(owners), "reporting_owner_ciks_equal_to_issuer_count": sum(x["cik_comparison_key"] == issuer_header["cik_comparison_key"] for x in owners)}, "primary_document": {"filename": filename, "sequence": sequence, "form": document_form, "document_byte_start": document.start(), "document_byte_end_exclusive": document.end(), "all_document_wrappers_count": len(documents), "matching_ownership_document_count": 1}, "ownership_xml": {"root_tag": root_element.tag, "issuer_prefix_byte_start": absolute_xml, "issuer_prefix_byte_end_exclusive": absolute_xml + len(prefix), "issuer_element_byte_start": absolute_xml + issuer_match.start(), "issuer_element_byte_end_exclusive": absolute_xml + issuer_match.end(), "document_type_text": xml_form, "period_of_report_texts": ended_direct_metadata.get("periodOfReport", []), "date_of_original_submission_texts": ended_direct_metadata.get("dateOfOriginalSubmission", []), "issuer_fields": xml_fields, "issuer_cik_comparison_key": xml_cik, "parser_stopped_at_issuer_end": True, "full_xml_validity_claimed": False}, "comparisons": comparison, "acceptance_precedes_2020_01_01_eastern": True, "archive_directory_cik_used_as_identity_evidence": False, "accession_prefix_used_as_issuer_identity": False, "known_at": None, "available_at": None, "effective_start": None, "effective_end": None, "historical_security_link_created": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", default="data/private/sec-ownership-corrob/development-v1")
    parser.add_argument("--output", default="outputs/cutoff-clock-followup-20261011")
    parser.add_argument("--report", default="reports/ownership_cutoff_clock_audit.json")
    args = parser.parse_args()
    bundle, out, report_path = (ROOT / value for value in (args.bundle, args.output, args.report))
    if out.exists() or report_path.exists():
        raise FileExistsError("Use new output and report paths; preserved evidence is immutable")
    started = now()
    receipt_path = bundle / "receipt.json"
    receipt_bytes = receipt_path.read_bytes()
    if digest(receipt_bytes) != RECEIPT_SHA:
        raise ValueError("Original bundle receipt pin differs")
    receipt = json.loads(receipt_bytes)
    config = load_protocol(ROOT / "configs/protocol.json")
    verify_lock(config, ROOT / "configs/protocol.lock.json")
    if canonical_hash(config) != PROTOCOL_SHA or receipt["protocol_sha256"] != PROTOCOL_SHA:
        raise ValueError("Frozen protocol pin differs")
    window = year_start_window(2020, config)
    if window["information_cutoff"] != receipt["information_cutoff"]:
        raise ValueError("Reconstructed calendar cutoff differs from original receipt")
    cutoff = dt.datetime.fromisoformat(window["information_cutoff"])
    if cutoff.isoformat() != "2019-12-31T21:00:00+00:00":
        raise ValueError("Unexpected frozen cutoff")
    # Fingerprint every preserved bundle file without parsing additional data.
    preservation = {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in bundle.rglob("*") if p.is_file()}
    for spec in [x for table in receipt["tables"].values() for x in table["parts"]] + receipt["input_receipts"]:
        raw = (bundle / spec["file"]).read_bytes()
        if len(raw) != spec["bytes"] or digest(raw) != spec["sha256"]:
            raise ValueError("Original preserved input pin differs")
    consumed = {}
    for relative in ("configs/protocol.json", "configs/protocol.lock.json",
                     "src/disclosure_research/protocol.py", "src/disclosure_research/universe.py",
                     "src/disclosure_research/timing.py", "uv.lock"):
        consumed[relative] = bound(ROOT / relative)

    def rows(table, columns=None):
        result = []
        for spec in receipt["tables"][table]["parts"]:
            path = bundle / spec["file"]
            consumed[str(path.relative_to(ROOT))] = bound(path)
            result.extend(pq.read_table(path, columns=columns).to_pylist())
        if len(result) != receipt["tables"][table]["rows"]:
            raise ValueError("Pinned table row count differs")
        return result

    summaries = rows("cohort_summary")
    cases = {x["security_id"]: x for x in summaries if x["observation_status"] == "CUTOFF_DAY_OBSERVATIONS_ONLY"}
    if len(cases) != 14 or len(summaries) != 4122:
        raise ValueError("Complete expected cohort differs")
    observations = [x for x in rows("observations") if x["security_id"] in cases]
    records_by_case = {}
    for security, case in cases.items():
        selected = [x for x in observations if x["security_id"] == security]
        unique_records = {x["source_tsv_record"] for x in selected}
        if (len(selected) != case["observation_rows"] or len(unique_records) != case["sec_occurrences"]
                or len(unique_records) != case["cutoff_day_sec_occurrences"]
                or case["earlier_date_sec_occurrences"] != 0
                or any(x["cutoff_date_relation"] != "CUTOFF_DAY_TIME_UNRESOLVED" for x in selected)):
            raise ValueError("Complete case occurrence accounting differs")
        records_by_case[security] = sorted(unique_records)
    accessions = {x["accession"] for x in observations}
    # Retain all quarterly occurrences of every selected accession, including repeats.
    sec_rows = rows("sec_occurrences", [*PUBLIC_FIELDS, "source_tsv_record", "source_sha256"])
    selected_sec = sorted((x for x in sec_rows if x["ACCESSION_NUMBER"] in accessions), key=lambda x: x["source_tsv_record"])
    sec_by_record = {x["source_tsv_record"]: x for x in selected_sec}
    for observation in observations:
        original = sec_by_record[observation["source_tsv_record"]]
        if (original["ACCESSION_NUMBER"] != observation["accession"]
                or original["ISSUERCIK"] != observation["sec_issuer_cik_raw"]
                or original["ISSUERTRADINGSYMBOL"] != observation["sec_symbol_raw"]
                or original["source_sha256"] != observation["sec_source_sha256"]):
            raise ValueError("Private observation and public source occurrence differ")
    tsv = bundle / "original_SUBMISSION.tsv"
    consumed[str(tsv.relative_to(ROOT))] = bound(tsv)
    if digest(tsv.read_bytes()) != receipt["inputs"]["sec_submission_sha256"]:
        raise ValueError("Original quarterly TSV pin differs")
    seen = set()
    for ordinal, row in enumerate(csv.DictReader(io.StringIO(tsv.read_text(encoding="utf-8-sig")), delimiter="\t"), 2):
        if ordinal in sec_by_record:
            if any(row[key] != sec_by_record[ordinal][key] for key in PUBLIC_FIELDS):
                raise ValueError("Exact original TSV occurrence differs")
            seen.add(ordinal)
    if seen != set(sec_by_record):
        raise ValueError("Original TSV omits selected occurrence")
    for row in selected_sec:
        if (not re.fullmatch(r"\d{10}-19-\d{6}", row["ACCESSION_NUMBER"])
                or not re.fullmatch(r"\d{10}", row["ISSUERCIK"])
                or int(row["ISSUERCIK"]) <= 0 or row["FILING_DATE"] != "31-DEC-2019"
                or row["DOCUMENT_TYPE"] not in {"3", "3/A", "4", "4/A", "5", "5/A"}):
            raise ValueError("Unsupported public source metadata; original selection retained")
    out.mkdir(parents=True, mode=0o700)
    (out / "private").mkdir(mode=0o700)
    write_new(out / "private/selected_cases.json", {"cohort": list(cases.values()), "observations": observations}, private=True)
    public_queue = {"selection": "All original accessions for all 14 CUTOFF_DAY_OBSERVATIONS_ONLY cases; all repeated quarterly occurrences retained",
                    "bundle_receipt_sha256": RECEIPT_SHA, "information_cutoff": cutoff.isoformat(),
                    "source_occurrences": selected_sec}
    write_new(out / "queue.json", public_queue)
    script_binding = bound(Path(__file__).resolve())
    request_policy = {"workers": 2, "minimum_seconds_between_request_starts": 0.6, "timeout_seconds": 30,
                      "maximum_source_bytes": MAX_BYTES, "user_agent": UA, "automatic_retries": 0,
                      "alternate_paths_after_403": False}
    grouped = collections.defaultdict(list)
    for row in selected_sec:
        grouped[row["ACCESSION_NUMBER"]].append(row)
    ambiguous_locations = {accession for accession, group in grouped.items() if len({x["ISSUERCIK"] for x in group}) != 1}

    def fetch(accession):
        global LAST_REQUEST
        row = grouped[accession][0]
        url = f"https://www.sec.gov/Archives/edgar/data/{int(row['ISSUERCIK'])}/{accession.replace('-', '')}/{accession}.txt"
        attempt = {"accession": accession, "url": url, "started_utc": now(),
                   "archive_directory_cik_used_as_identity": False}
        try:
            if accession in ambiguous_locations:
                raise ValueError("Conflicting original issuer location candidates; no choice inferred")
            with RATE_LOCK:
                delay = 0.6 - (time.monotonic() - LAST_REQUEST)
                if delay > 0:
                    time.sleep(delay)
                LAST_REQUEST = time.monotonic()
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
            attempt["request_started_utc"] = now()
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status != 200 or response.url != url:
                    raise ValueError("Unexpected SEC response or redirect")
                body = response.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES or not body.startswith(("<SEC-DOCUMENT>" + accession + ".txt").encode()):
                    raise ValueError("Source size or exact original accession wrapper differs")
                source = {"url": url, "final_url": response.url, "http_status": response.status,
                          "request_started_utc": attempt["request_started_utc"], "retrieved_at_utc": now(),
                          "sha256": digest(body), "bytes": len(body), "path": str((out / (accession + ".txt")).relative_to(ROOT)),
                          "response_metadata": {key: response.headers.get(key) for key in
                                                ("Content-Type", "Last-Modified", "ETag", "Date", "Content-Length", "Content-Encoding")},
                          "collector": script_binding, "historical_availability_inferred": False}
            write_new(out / (accession + ".txt"), body)
            write_new(out / (accession + ".receipt.json"), source)
            attempt.update(status="ORIGINAL_PRESERVED", sha256=source["sha256"], bytes=source["bytes"])
        except Exception as exc:
            attempt.update(status="SOURCE_NOT_PRESERVED", error_type=type(exc).__name__,
                           error=str(exc), http_status=getattr(exc, "code", None), alternate_path_attempted=False)
        attempt["completed_utc"] = now()
        write_new(out / (accession + ".attempt.json"), attempt)
        print(json.dumps({"accession": accession, "status": attempt["status"]}), flush=True)
        return attempt

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        attempts = list(executor.map(fetch, sorted(accessions)))
    write_new(out / "collection_receipt.json", {"attempts": attempts, "request_policy": request_policy,
               "script": script_binding, "queue": bound(out / "queue.json")})
    attempt_by_accession = {x["accession"]: x for x in attempts}
    sources, records = {}, []
    for row in selected_sec:
        accession = row["ACCESSION_NUMBER"]
        record = {"quarterly_source_occurrence": row, "source_id": accession}
        attempt = attempt_by_accession[accession]
        if attempt["status"] == "ORIGINAL_PRESERVED":
            path = out / (accession + ".txt")
            body = path.read_bytes()
            source = json.loads((out / (accession + ".receipt.json")).read_bytes())
            if digest(body) != source["sha256"] or len(body) != source["bytes"]:
                raise ValueError("New source preservation pin differs")
            sources[accession] = {**source, "receipt": bound(out / (accession + ".receipt.json"))}
            try:
                record.update(inspect(body, row))
                accepted = dt.datetime.fromisoformat(record["header"]["acceptance_utc"])
                relation = "BEFORE_CUTOFF" if accepted < cutoff else "AFTER_CUTOFF" if accepted > cutoff else "AT_CUTOFF"
                record.update(acceptance_vs_cutoff=relation, acceptance_minus_cutoff_seconds=(accepted - cutoff).total_seconds())
            except Exception as exc:
                record.update(status="SOURCE_STRUCTURE_OR_METADATA_UNRESOLVED",
                              error_type=type(exc).__name__, error=str(exc), acceptance_vs_cutoff="UNRESOLVED")
        else:
            record.update(status="SOURCE_NOT_PRESERVED", acceptance_vs_cutoff="UNRESOLVED")
        record.update(known_at=None, available_at=None, effective_start=None, effective_end=None,
                      historical_security_link_created=False)
        records.append(record)
    by_record = {x["quarterly_source_occurrence"]["source_tsv_record"]: x for x in records}
    private_results = []
    for security, ordinals in records_by_case.items():
        relations = collections.Counter(by_record[n]["acceptance_vs_cutoff"] for n in ordinals)
        values = set(relations)
        status = ("ALL_ORIGINAL_ACCEPTANCES_BEFORE_CUTOFF" if values == {"BEFORE_CUTOFF"} else
                  "ALL_ORIGINAL_ACCEPTANCES_AFTER_CUTOFF" if values == {"AFTER_CUTOFF"} else
                  "ORIGINAL_ACCEPTANCES_BOTH_BEFORE_AND_AFTER" if values == {"BEFORE_CUTOFF", "AFTER_CUTOFF"} else
                  "HAS_AT_CUTOFF_OR_UNRESOLVED_ACCEPTANCE")
        private_results.append({"security_id": security, "source_tsv_records": ordinals, "clock_status": status,
                                "acceptance_relation_occurrences": dict(relations), "known_at": None, "available_at": None})
    write_new(out / "private/case_results.json", private_results, private=True)
    unique_records = {x["source_id"]: x for x in records}
    inspected = [x for x in records if "comparisons" in x]
    summary = {
        "complete_original_cohort_rows": len(summaries), "cutoff_day_only_cases": len(cases),
        "private_observation_relationships": len(observations),
        "unambiguous_literal_observation_relationships": sum(x["unambiguous_exact_literal_observation"] for x in observations),
        "matched_quarterly_occurrences": len({x["source_tsv_record"] for x in observations}),
        "all_quarterly_occurrences_of_selected_accessions": len(records), "distinct_original_accessions": len(accessions),
        "original_sources_preserved": len(sources), "source_bytes": sum(x["bytes"] for x in sources.values()),
        "occurrence_acceptance_relation_counts": dict(collections.Counter(x["acceptance_vs_cutoff"] for x in records)),
        "distinct_accession_acceptance_relation_counts": dict(collections.Counter(x["acceptance_vs_cutoff"] for x in unique_records.values())),
        "case_clock_status_counts": dict(collections.Counter(x["clock_status"] for x in private_results)),
        "case_counts_with_at_least_one_acceptance": {relation: sum(x["acceptance_relation_occurrences"].get(relation, 0) > 0 for x in private_results)
                                                   for relation in ("BEFORE_CUTOFF", "AT_CUTOFF", "AFTER_CUTOFF", "UNRESOLVED")},
        "original_inspection_status_counts": dict(collections.Counter(x["status"] for x in records)),
        "comparison_true_counts": {key: sum(x["comparisons"][key] for x in inspected) for key in inspected[0]["comparisons"]} if inspected else {},
        "document_type_counts": dict(collections.Counter(x["DOCUMENT_TYPE"] for x in selected_sec)),
        "original_metadata_repeat_occurrences": len(records) - len(accessions),
        "reporting_owner_role_occurrences": sum(x["header"]["reporting_owner_role_count"] for x in inspected),
        "source_structure_or_metadata_errors": sum(x["status"] == "SOURCE_STRUCTURE_OR_METADATA_UNRESOLVED" for x in records),
        "source_preservation_errors": sum(x["status"] != "ORIGINAL_PRESERVED" for x in attempts)
    }
    # No mutation to the preserved bundle, frozen protocol, calendar code or inputs.
    after = {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in bundle.rglob("*") if p.is_file()}
    if after != preservation or receipt_path.read_bytes() != receipt_bytes:
        raise ValueError("Original bundle changed during execution")
    if any(bound(ROOT / key) != value for key, value in consumed.items()):
        raise ValueError("Consumed code or input changed during execution")
    if bound(Path(__file__).resolve()) != script_binding:
        raise ValueError("Audit script changed during execution")
    report = {
        "schema_version": 1, "status": "ORIGINAL_SEC_ACCEPTANCE_CLOCK_OBSERVATIONS_ONLY",
        "started_utc": started, "completed_utc": now(), "bundle_receipt_sha256": RECEIPT_SHA,
        "protocol_sha256": PROTOCOL_SHA, "source_quarter": "2019Q4", "cohort_year": 2020,
        "calendar": {"calendar": "XNYS", "exchange_calendars_version": exchange_calendars.__version__,
                     "selection_asof": window["selection_asof"], "selection_session": window["selection_session"],
                     "cutoff_session": window["liquidity_end"], "cutoff_utc": cutoff.isoformat(),
                     "cutoff_eastern": cutoff.astimezone(ZoneInfo("America/New_York")).isoformat(),
                     "comparison": "Strict before, exact equality, and strict after remain separate"},
        "inputs": consumed, "script": script_binding, "queue": bound(out / "queue.json"),
        "collection_receipt": bound(out / "collection_receipt.json"), "source_receipts": sources,
        "private_evidence_bindings": {name: bound(out / "private" / name) for name in ("selected_cases.json", "case_results.json")},
        "records": records, "summary": summary, "request_policy": request_policy,
        "preserved_bundle_files_rehashed_unchanged": len(preservation),
        "scope": {"original_headers_and_issuer_xml_prefixes_only": True,
                  "all_distinct_accessions_inspected": len(inspected) == len(records),
                  "repeated_source_occurrences_retained": True, "transaction_or_holdings_fields_parsed": False,
                  "licensed_associations_exported": False, "market_returns_read": False, "final_period_data_opened": False,
                  "known_at_inferred": False, "available_at_inferred": False,
                  "continuous_identity_links_inferred": False, "human_reviews_created": 0,
                  "source_approvals_created": 0, "model_ready": False},
        "limits": [
            "SEC acceptance is an original header clock, not evidence of first public website availability.",
            "The exact exchange close is reconstructed from the frozen protocol calendar; filing, report and change dates do not substitute for acceptance.",
            "An issuer CIK/name/symbol observation does not establish a share class, vendor-security mapping, or continuous effective interval.",
            "All 14 saved cases and every related distinct accession are retained. Earlier selection and literal-matching decisions are reused from the pinned, independently verified bundle.",
            "Historical known_at, available_at and effective bounds remain null. Original statuses, protocol and empirical gates remain unchanged.",
            "Private selected cases and associations remain on the authorized data host; the public record contains SEC metadata and aggregates only.",
            "The XML parser stops at the direct issuer element. Full submission bytes are preserved, but remaining ownership content is not analyzed."
        ]
    }
    for source in sources.values():
        if bound(ROOT / source["path"])["sha256"] != source["sha256"]:
            raise ValueError("Source changed before report publication")
    write_new(report_path, report)
    write_new(out / "execution_receipt.json", {"report": bound(report_path), "script": script_binding,
               "summary": summary, "completed_utc": now()})
    print(json.dumps({"report": bound(report_path), "summary": summary}, indent=2), flush=True)


if __name__ == "__main__":
    main()
