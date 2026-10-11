"""Audit seven multi-CIK cases from the pinned 2020 ownership cohort.

This is a bounded empirical-source follow-up, not a generalized data importer.
Original ownership parsing is reused from the previously verified 47-source
inspector. Only issuer/header/XML-prefix metadata is inspected. Private
security associations stay on the Mac; public outputs contain SEC facts only.
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
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/multi-cik-followup-20261011"
BUNDLE = ROOT / "data/private/sec-ownership-corrob/development-v1"
BUNDLE_SHA = "85358e4f928687ed9fc3da3813e87980321bbd155b24c952f7a955c5c92a8442"
SUBMISSION_SHA = "0f73eaa50e3964641fe180cb2db299d94ae5b77e4d12d3a68ba1ab5b663b6e2c"
REPORT = ROOT / "reports/ownership_multi_cik_originals.json"
UA = "Michael Baffour Awuah Disclosure-drift research https://github.com/michaelbawuah/Disclosure-drift"
MAX_BYTES = 8 * 1024 * 1024
RATE_LOCK = threading.Lock()
LAST_REQUEST = 0.0
PUBLIC_FIELDS = ("ACCESSION_NUMBER", "DOCUMENT_TYPE", "FILING_DATE",
                 "ISSUERCIK", "ISSUERNAME", "ISSUERTRADINGSYMBOL", "source_tsv_record")
PROTECTED = ("configs/protocol.json", "configs/protocol.lock.json",
             "reports/review_progress/user_arithmetic_receipt.json",
             "reports/filing_review/assistant/receipt.json",
             "reports/sec_ownership_original_followup.json",
             "reports/sec_ownership_execution.json",
             "reports/sec_ownership_verification.json")

def digest(body):
    return hashlib.sha256(body).hexdigest()

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def dump(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()

def bound(path):
    raw = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(raw), "sha256": digest(raw)}

def write_new(path, body):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, 0o400)

def protected():
    return {name: bound(ROOT / name)["sha256"] for name in PROTECTED}

def assert_preserved():
    expected = json.loads((OUT / "protected_before.json").read_bytes())
    if protected() != expected:
        raise ValueError("Existing protected evidence changed")
    selection = json.loads((OUT / "selection_receipt.json").read_bytes())
    for spec in selection["verified_input_files"]:
        path = ROOT / spec["path"]
        if bound(path) != spec:
            raise ValueError("Pinned selection input changed")
    for name in ("queue", "private_associations"):
        spec = selection[name]
        if bound(ROOT / spec["path"]) != spec:
            raise ValueError("Fixed selection output changed")

def select():
    import pyarrow.parquet as pq
    from disclosure_research import sec_ownership_corrob as contract
    if OUT.exists():
        raise FileExistsError("Select requires a fresh dedicated output directory")
    guards = []
    def checked(path, expected_sha=None, expected_bytes=None):
        raw = path.read_bytes()
        if expected_sha is not None and digest(raw) != expected_sha:
            raise ValueError("Pinned source hash differs")
        if expected_bytes is not None and len(raw) != expected_bytes:
            raise ValueError("Pinned source size differs")
        guards.append({"path": str(path.relative_to(ROOT)), "bytes": len(raw), "sha256": digest(raw)})
        return raw
    raw = checked(BUNDLE / "receipt.json", BUNDLE_SHA)
    receipt = json.loads(raw)
    assert receipt["cohort_year"] == 2020
    assert receipt["source_quarter"] == "2019Q4"
    assert receipt["model_ready"] is False and receipt["final_period_opened"] is False
    schemas = {"cohort_summary": contract.SUMMARY_SCHEMA,
               "observations": contract.OBSERVATION_SCHEMA,
               "sec_occurrences": contract.SEC_SCHEMA,
               "original_source_followup": contract.FOLLOWUP_SCHEMA}
    data = {}
    for name, schema in schemas.items():
        result = []
        for spec in receipt["tables"][name]["parts"]:
            path = (BUNDLE / spec["file"]).resolve()
            assert path.is_relative_to(BUNDLE.resolve()) and not path.is_symlink()
            body = checked(path, spec["sha256"], spec["bytes"])
            table = pq.read_table(io.BytesIO(body))
            assert table.schema.equals(schema, check_metadata=True)
            assert table.num_rows == spec["rows"]
            result.extend(table.to_pylist())
        assert len(result) == receipt["tables"][name]["rows"]
        data[name] = result
    original_spec = next(s for s in receipt["input_receipts"] if s["file"] == "original_SUBMISSION.tsv")
    original = checked(BUNDLE / original_spec["file"], SUBMISSION_SHA, original_spec["bytes"])
    original_rows = list(csv.DictReader(io.StringIO(original.decode("utf-8-sig")), delimiter="\t"))
    assert len(original_rows) == len(data["sec_occurrences"]) == 38145
    sec_by_record = {}
    for r in data["sec_occurrences"]:
        ordinal = r["source_tsv_record"]
        assert ordinal not in sec_by_record and 2 <= ordinal <= len(original_rows) + 1
        assert {k: r[k] for k in contract.SEC_FIELDS} == original_rows[ordinal - 2]
        assert r["source_sha256"] == SUBMISSION_SHA
        sec_by_record[ordinal] = r
    summaries = {r["security_id"]: r for r in data["cohort_summary"]}
    assert len(summaries) == 4122
    by_security = collections.defaultdict(list)
    observation_ids = set()
    for r in data["observations"]:
        assert r["observation_id"] not in observation_ids
        observation_ids.add(r["observation_id"])
        assert r["security_id"] in summaries and r["sec_source_sha256"] == SUBMISSION_SHA
        sec = sec_by_record[r["source_tsv_record"]]
        assert (r["accession"], r["filing_date"], r["sec_issuer_cik_raw"],
                r["sec_issuer_cik_comparison_key"], r["sec_symbol_raw"], r["cutoff_date_relation"]) == (
                    sec["ACCESSION_NUMBER"], sec["filing_date"], sec["ISSUERCIK"],
                    sec["issuer_cik_comparison_key"], sec["ISSUERTRADINGSYMBOL"], sec["cutoff_date_relation"])
        by_security[r["security_id"]].append(r)
    reconstructed_multi = set()
    for sid, s in summaries.items():
        earlier = [r for r in by_security[sid] if r["cutoff_date_relation"] == "BEFORE_CUTOFF_DATE"]
        keys = sorted({r["sec_issuer_cik_comparison_key"] for r in earlier if r["sec_issuer_cik_comparison_key"]})
        assert keys == json.loads(s["earlier_issuer_cik_comparison_keys_json"])
        assert len(by_security[sid]) == s["observation_rows"]
        assert len({r["source_tsv_record"] for r in earlier}) == s["earlier_date_sec_occurrences"]
        if len(keys) > 1:
            reconstructed_multi.add(sid)
    supplied_multi = {sid for sid, s in summaries.items() if s["observation_status"] == "MULTIPLE_EARLIER_ISSUER_KEYS_OBSERVED"}
    assert reconstructed_multi == supplied_multi and len(supplied_multi) == 7
    groups = []
    for sid in supplied_multi:
        observations = by_security[sid]
        earlier = [r for r in observations if r["cutoff_date_relation"] == "BEFORE_CUTOFF_DATE"]
        keys = sorted({r["sec_issuer_cik_comparison_key"] for r in earlier})
        selected = []
        for key in keys:
            choices = [r for r in earlier if r["sec_issuer_cik_comparison_key"] == key]
            chosen = min(choices, key=lambda r: (r["filing_date"], r["accession"], r["source_tsv_record"]))
            selected.append({k: sec_by_record[chosen["source_tsv_record"]][k] for k in PUBLIC_FIELDS})
        occurrences = sorted({r["source_tsv_record"] for r in observations})
        followups = [r for r in data["original_source_followup"] if r["security_id"] == sid]
        assert {r["source_tsv_record"] for r in followups} == set(occurrences)
        groups.append({"security_id": sid, "public_symbols": sorted({r["sec_symbol_raw"] for r in observations}),
                       "distinct_earlier_ciks": keys, "selected": selected,
                       "observations": observations, "summary": summaries[sid], "followups": followups,
                       "public_occurrences": [{k: sec_by_record[o][k] for k in PUBLIC_FIELDS} for o in occurrences]})
    groups.sort(key=lambda r: (r["public_symbols"], r["distinct_earlier_ciks"],
                              [s["ACCESSION_NUMBER"] for s in r["selected"]]))
    public_groups, queue, private_groups = [], [], []
    for ordinal, group in enumerate(groups, 1):
        case = f"multi-cik-{ordinal:02d}"
        public_group = {"case_id": case, "public_symbols": group["public_symbols"],
                        "distinct_earlier_ciks": group["distinct_earlier_ciks"],
                        "observation_rows": len(group["observations"]),
                        "earlier_observation_rows": sum(o["cutoff_date_relation"] == "BEFORE_CUTOFF_DATE" for o in group["observations"]),
                        "unambiguous_earlier_observation_rows": sum(o["cutoff_date_relation"] == "BEFORE_CUTOFF_DATE" and o["unambiguous_exact_literal_observation"] for o in group["observations"]),
                        "original_source_occurrences": group["public_occurrences"],
                        "selected_public_occurrences": group["selected"]}
        public_groups.append(public_group)
        private_groups.append({"case_id": case, **group})
        for s in group["selected"]:
            queue.append({"case_id": case, **s})
    assert len(queue) == 14 and len({r["ACCESSION_NUMBER"] for r in queue}) == 14
    prior = json.loads(checked(ROOT / "reports/sec_ownership_original_followup.json"))
    prior_accessions = {r["queued_public_source_occurrence"]["ACCESSION_NUMBER"] for r in prior["records"]}
    assert not prior_accessions.intersection(r["ACCESSION_NUMBER"] for r in queue)
    policy = "Every security with >1 distinct positive earlier CIK comparison key; earliest reported filing_date, then accession, then original TSV record per security/CIK; no uniqueness filtering or voting"
    payload = {"schema_version": 1, "status": "FIXED_MULTI_CIK_PUBLIC_SOURCE_QUEUE",
               "bundle_receipt_sha256": BUNDLE_SHA, "submission_source_sha256": SUBMISSION_SHA,
               "selection_policy": policy, "information_cutoff": receipt["information_cutoff"],
               "groups": public_groups, "selected_occurrences": queue,
               "licensed_identifiers_or_names_rows_exported": False}
    before = protected()
    OUT.mkdir(mode=0o700)
    write_new(OUT / "protected_before.json", dump(before))
    write_new(OUT / "queue.json", dump(payload))
    write_new(OUT / "private_associations.json", dump({"groups": private_groups}))
    result = {"schema_version": 1, "status": "FIXED_7_SECURITY_14_CIK_SOURCE_SELECTION_VERIFIED",
              "created_at": now(), "script": bound(Path(__file__).resolve()),
              "ownership_bundle_receipt_sha256": BUNDLE_SHA,
              "verified_input_files": guards, "queue": bound(OUT / "queue.json"),
              "private_associations": bound(OUT / "private_associations.json"),
              "full_summary_rows": len(summaries), "full_observation_rows": len(data["observations"]),
              "all_original_sec_occurrences_checked": len(original_rows),
              "multi_cik_security_count": 7, "selected_original_filings": len(queue),
              "contributing_observation_rows": sum(len(g["observations"]) for g in groups),
              "contributing_unique_sec_occurrences": len({o["source_tsv_record"] for g in groups for o in g["observations"]}),
              "completed_47_case_overlap": 0, "selection_policy": policy,
              "historical_links_created": 0, "known_at_inferred": False, "source_approvals": 0,
              "human_reviews_created": 0, "market_files_read": False, "final_period_opened": False}
    write_new(OUT / "selection_receipt.json", dump(result))
    assert_preserved()
    print(json.dumps({k: result[k] for k in ("status", "multi_cik_security_count",
                         "selected_original_filings", "contributing_observation_rows",
                         "contributing_unique_sec_occurrences", "completed_47_case_overlap")}), flush=True)

def rate_limit():
    global LAST_REQUEST
    with RATE_LOCK:
        delay = 0.6 - (time.monotonic() - LAST_REQUEST)
        if delay > 0:
            time.sleep(delay)
        LAST_REQUEST = time.monotonic()

def collect_one(entry):
    ordinal, row = entry
    accession = row["ACCESSION_NUMBER"]
    assert re.fullmatch(r"\d{10}-19-\d{6}", accession)
    url = f"https://www.sec.gov/Archives/edgar/data/{int(row['ISSUERCIK'])}/{accession.replace('-', '')}/{accession}.txt"
    target = OUT / (accession + ".txt")
    attempt = {"queue_ordinal": ordinal, "case_id": row["case_id"], "accession": accession,
               "source_tsv_record": row["source_tsv_record"], "candidate_url": url,
               "candidate_path_issuer_is_not_assumed_correct": True, "attempt_recorded_utc": now()}
    try:
        if target.exists() or (OUT / (accession + ".receipt.json")).exists():
            raise FileExistsError("Existing source preservation; no replacement")
        rate_limit()
        started = now()
        request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200 or urllib.parse.urlparse(response.url).hostname != "www.sec.gov":
                raise ValueError("Unexpected source response")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES or not body.startswith(("<SEC-DOCUMENT>" + accession + ".txt").encode()):
                raise ValueError("Original response size or accession wrapper differs")
            receipt = {"url": url, "final_url": response.url, "download_started_utc": started,
                       "download_completed_utc": now(), "sha256": digest(body), "bytes": len(body),
                       "http_status": response.status,
                       "response_metadata": {key: response.headers.get(key) for key in ("Content-Type", "Last-Modified", "ETag", "Date", "Content-Length", "Content-Encoding")},
                       "path": str(target.relative_to(ROOT)), "historical_availability_inferred": False,
                       "collector_sha256": digest(Path(__file__).read_bytes())}
        write_new(target, body)
        receipt_path = OUT / (accession + ".receipt.json")
        write_new(receipt_path, dump(receipt))
        attempt.update(status="DOWNLOADED_ORIGINAL_WRAPPER_MATCHED", receipt_path=str(receipt_path.relative_to(ROOT)), sha256=receipt["sha256"], bytes=receipt["bytes"])
    except urllib.error.HTTPError as exc:
        attempt.update(status="HTTP_ERROR", http_status=exc.code, error_type=type(exc).__name__,
                       alternate_path_or_403_bypass_attempted=False)
    except Exception as exc:
        attempt.update(status="PRESERVATION_ERROR", error_type=type(exc).__name__)
    attempt["attempt_completed_utc"] = now()
    write_new(OUT / (accession + ".attempt.json"), dump(attempt))
    print(json.dumps({key: attempt.get(key) for key in ("queue_ordinal", "accession", "status", "bytes", "http_status")}), flush=True)
    return attempt

def collect():
    assert_preserved()
    if (OUT / "collection_receipt.json").exists():
        raise FileExistsError("Collection is already recorded")
    queue_bytes = (OUT / "queue.json").read_bytes()
    queue = json.loads(queue_bytes)
    started = now()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        attempts = list(executor.map(collect_one, enumerate(queue["selected_occurrences"], 1)))
    assert_preserved()
    result = {"schema_version": 1, "status": "COMPLETE_FIXED_MULTI_CIK_QUEUE_ATTEMPTED",
              "started_utc": started, "completed_utc": now(), "queue_sha256": digest(queue_bytes),
              "attempts": attempts, "queue_entries": len(attempts),
              "preserved_sources": sum(a["status"] == "DOWNLOADED_ORIGINAL_WRAPPER_MATCHED" for a in attempts),
              "request_policy": {"workers": 2, "minimum_seconds_between_request_starts": 0.6,
                                 "timeout_seconds": 30, "maximum_source_bytes": MAX_BYTES,
                                 "user_agent": UA, "automatic_retries": 0, "alternate_paths_after_403": False},
              "transaction_fields_parsed": False, "final_period_sources_requested": False}
    write_new(OUT / "collection_receipt.json", dump(result))
    print(json.dumps({key: result[key] for key in ("status", "queue_entries", "preserved_sources")}), flush=True)

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


def inspect_sources():
    assert_preserved()
    queue_bytes = (OUT / "queue.json").read_bytes()
    queue = json.loads(queue_bytes)
    selection = json.loads((OUT / "selection_receipt.json").read_bytes())
    collection = json.loads((OUT / "collection_receipt.json").read_bytes())
    assert collection["queue_sha256"] == digest(queue_bytes)
    assert collection["queue_entries"] == len(queue["selected_occurrences"]) == 14
    cutoff = dt.datetime.fromisoformat(queue["information_cutoff"])
    records, sources = [], {}
    for ordinal, (row, attempt) in enumerate(zip(queue["selected_occurrences"], collection["attempts"], strict=True), 1):
        accession = row["ACCESSION_NUMBER"]
        assert attempt["queue_ordinal"] == ordinal and attempt["accession"] == accession
        record = {"queue_ordinal": ordinal, "case_id": row["case_id"],
                  "queued_public_source_occurrence": row, "preservation_attempt": attempt}
        if attempt["status"] != "DOWNLOADED_ORIGINAL_WRAPPER_MATCHED":
            record.update(status="SOURCE_NOT_PRESERVED", known_at=None, available_at=None)
            records.append(record)
            continue
        receipt_path = ROOT / attempt["receipt_path"]
        receipt = json.loads(receipt_path.read_bytes())
        source_path = ROOT / receipt["path"]
        body = source_path.read_bytes()
        assert digest(body) == receipt["sha256"] == attempt["sha256"]
        assert len(body) == receipt["bytes"] == attempt["bytes"]
        assert receipt["url"] == receipt["final_url"]
        sources[accession] = {**receipt, "receipt_file": bound(receipt_path)}
        record["source_id"] = accession
        try:
            record.update(inspect(body, row))
            accepted = dt.datetime.fromisoformat(record["header"]["acceptance_eastern"])
            record["acceptance_precedes_information_cutoff"] = accepted < cutoff
        except Exception as exc:
            record.update(status="SOURCE_PRESERVED_STRUCTURE_UNRESOLVED",
                          inspection_error={"type": type(exc).__name__, "message": str(exc)},
                          known_at=None, available_at=None, historical_security_link_created=False)
        records.append(record)
    complete = [r for r in records if "comparisons" in r]
    groups = []
    for group in queue["groups"]:
        group_records = [r for r in records if r["case_id"] == group["case_id"]]
        confirmed = all(r["status"] == "ORIGINAL_ISSUER_CIK_SYMBOL_AND_NAMES_CONFIRMED" for r in group_records)
        groups.append({**group, "original_source_status": "MULTIPLE_ORIGINAL_ISSUERS_REPORT_THE_SAME_LITERAL_SYMBOL" if confirmed else "ORIGINAL_SOURCE_DISCREPANCY_OR_STRUCTURE_UNRESOLVED",
                       "selected_original_sources_confirmed": sum(r["status"] == "ORIGINAL_ISSUER_CIK_SYMBOL_AND_NAMES_CONFIRMED" for r in group_records),
                       "historical_relationship_or_symbol_cause": "PENDING_SEPARATE_ORIGINAL_CORPORATE_SOURCE_REVIEW"})
    summary = {"cases": len(groups), "selected_original_sources": len(records),
               "preserved_original_sources": len(sources),
               "original_source_bytes": sum(s["bytes"] for s in sources.values()),
               "structured_issuer_inspections": len(complete),
               "status_counts": dict(collections.Counter(r["status"] for r in records)),
               "comparison_true_counts": {key: sum(r["comparisons"][key] for r in complete) for key in complete[0]["comparisons"]} if complete else {},
               "contributing_observation_rows": selection["contributing_observation_rows"],
               "contributing_unique_sec_occurrences": selection["contributing_unique_sec_occurrences"],
               "header_reporting_owner_role_occurrences": sum(r["header"]["reporting_owner_role_count"] for r in complete),
               "acceptance_precedes_information_cutoff_count": sum(r.get("acceptance_precedes_information_cutoff", False) for r in complete),
               "completed_47_cases_repeated": 0}
    report = {"schema_version": 1, "status": "BOUNDED_MULTI_CIK_ORIGINAL_SOURCE_AUDIT",
              "recorded_at_utc": now(), "inputs": {"selection_receipt": bound(OUT / "selection_receipt.json"),
              "queue": bound(OUT / "queue.json"), "collection_receipt": bound(OUT / "collection_receipt.json"),
              "script": bound(Path(__file__).resolve()), "ownership_bundle_receipt_sha256": BUNDLE_SHA,
              "submission_source_sha256": SUBMISSION_SHA},
              "selection_policy": queue["selection_policy"],
              "information_cutoff": queue["information_cutoff"],
              "groups": groups, "records": records, "source_receipts": sources, "summary": summary,
              "request_policy": collection["request_policy"],
              "selection_scope": "All 4122 stored cohort summaries and all 31466 stored observations were checked, earlier distinct CIK sets independently regrouped; exact selected SEC rows checked against all 38145 original TSV occurrences. Underlying Names/CCM matching and cohort selection were not rerun.",
              "parsing_scope": "Original SEC header and original ownershipDocument prefix through issuer end only. Remaining ownership, transaction, holdings, remarks and signature content is preserved but not parsed.",
              "protected_before": json.loads((OUT / "protected_before.json").read_bytes()),
              "protected_after": protected(),
              "historical_security_links_created": 0, "source_approvals_created": 0,
              "human_reviews_created": 0, "known_at_inferred": False,
              "historical_availability_inferred": False, "continuous_intervals_inferred": False,
              "vendor_identifiers_exported": False, "vendor_names_rows_exported": False,
              "market_returns_read": False, "final_period_sources_requested": False,
              "final_period_outcomes_opened": False, "model_ready": False}
    assert_preserved()
    for source in sources.values():
        assert bound(ROOT / source["path"])["sha256"] == source["sha256"]
    write_new(REPORT, dump(report))
    print(json.dumps({"report": bound(REPORT), "summary": summary}, indent=2), flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("select", "collect", "inspect"))
    phase = parser.parse_args().phase
    {"select": select, "collect": collect, "inspect": inspect_sources}[phase]()

if __name__ == "__main__":
    main()

