"""Complete the fixed 14-source audit using ordinary research-container requests.

Mac HTTP 403 receipts stay unchanged. One earlier successful container source
is reused byte-for-byte; each remaining source gets one honest-UA request.
Stop issuing further requests if this environment returns HTTP 403.
"""
import collections
import datetime as dt
import json
from pathlib import Path
import ownership_multi_cik as core

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/multi-cik-followup-20261011"
OUT = BASE / "container-originals"
QUEUE_SHA = "4c681c125f3e5e1b555675cb281b1df7aea23b494ea50d47858c065da176b6f5"
MAC_FAILURE_SHA = "b518a1bd5135f611d308a85c3deaac0707be60bfd00577781c9a060260c7c74a"
REPORT = ROOT / "reports/ownership_multi_cik_source_validation.json"

def main():
    raw = (BASE / "queue.json").read_bytes()
    assert core.digest(raw) == QUEUE_SHA
    queue = json.loads(raw)
    selection = json.loads((BASE / "selection_receipt.json").read_bytes())
    assert core.bound(BASE / "queue.json") == selection["queue"]
    mac_failure = ROOT / "reports/ownership_multi_cik_originals.json"
    assert core.digest(mac_failure.read_bytes()) == MAC_FAILURE_SHA
    assert json.loads(mac_failure.read_bytes())["summary"]["status_counts"] == {"SOURCE_NOT_PRESERVED": 14}
    assert not OUT.exists() and not REPORT.exists()
    OUT.mkdir(mode=0o700)
    core.OUT = OUT
    attempts = []
    stopped = False
    for ordinal, row in enumerate(queue["selected_occurrences"], 1):
        accession = row["ACCESSION_NUMBER"]
        if ordinal == 1:
            p = BASE / "container-probe-0001437749-19-021150.txt"
            probe_path = BASE / "container-probe-attempt.json"
            probe = json.loads(probe_path.read_bytes())
            body = p.read_bytes()
            assert accession == "0001437749-19-021150"
            assert probe["status"] == "ORIGINAL_SOURCE_PRESERVED" and probe["http_status"] == 200
            assert core.digest(body) == probe["sha256"] and len(body) == probe["bytes"]
            source_path = OUT / (accession + ".txt")
            core.write_new(source_path, body)
            receipt = {"url": probe["url"], "final_url": probe["final_url"],
                       "download_started_utc": probe["started_utc"], "download_completed_utc": probe["completed_utc"],
                       "sha256": probe["sha256"], "bytes": probe["bytes"], "http_status": 200,
                       "response_metadata": probe["headers"], "path": str(source_path.relative_to(ROOT)),
                       "environment": "research_container", "original_probe": core.bound(probe_path),
                       "historical_availability_inferred": False}
            receipt_path = OUT / (accession + ".receipt.json")
            core.write_new(receipt_path, core.dump(receipt))
            attempt = {"queue_ordinal": ordinal, "case_id": row["case_id"], "accession": accession,
                       "source_tsv_record": row["source_tsv_record"], "status": "PRESERVED_EARLIER_CONTAINER_PROBE",
                       "receipt_path": str(receipt_path.relative_to(ROOT)),
                       "sha256": receipt["sha256"], "bytes": receipt["bytes"], "new_request_issued": False}
            core.write_new(OUT / (accession + ".attempt.json"), core.dump(attempt))
        elif stopped:
            attempt = {"queue_ordinal": ordinal, "case_id": row["case_id"], "accession": accession,
                       "source_tsv_record": row["source_tsv_record"],
                       "status": "NOT_ATTEMPTED_AFTER_CONTAINER_ACCESS_DENIAL"}
            core.write_new(OUT / (accession + ".attempt.json"), core.dump(attempt))
        else:
            attempt = core.collect_one((ordinal, row))
            if attempt.get("http_status") == 403:
                stopped = True
        attempts.append(attempt)
    collection = {"schema_version": 1, "status": "FIXED_QUEUE_CONTAINER_ATTEMPTS_COMPLETED",
                  "recorded_at_utc": core.now(), "queue_sha256": QUEUE_SHA,
                  "mac_failures": core.bound(mac_failure), "attempts": attempts,
                  "request_policy": {"workers": 1, "minimum_seconds_between_request_starts": 0.6,
                                     "user_agent": core.UA, "timeout_seconds": 30,
                                     "automatic_retries": 0, "alternate_paths": False,
                                     "stop_after_403": True, "earlier_container_probe_reused": 1}}
    collection_path = OUT / "collection_receipt.json"
    core.write_new(collection_path, core.dump(collection))
    sources, records = {}, []
    cutoff = dt.datetime.fromisoformat(queue["information_cutoff"])
    for ordinal, (row, attempt) in enumerate(zip(queue["selected_occurrences"], attempts, strict=True), 1):
        record = {"queue_ordinal": ordinal, "case_id": row["case_id"],
                  "queued_public_source_occurrence": row, "preservation_attempt": attempt}
        if attempt["status"] not in {"DOWNLOADED_ORIGINAL_WRAPPER_MATCHED", "PRESERVED_EARLIER_CONTAINER_PROBE"}:
            record.update(status="SOURCE_NOT_PRESERVED", known_at=None, available_at=None)
            records.append(record)
            continue
        receipt_path = ROOT / attempt["receipt_path"]
        receipt = json.loads(receipt_path.read_bytes())
        body = (ROOT / receipt["path"]).read_bytes()
        assert core.digest(body) == receipt["sha256"] == attempt["sha256"]
        assert len(body) == receipt["bytes"] == attempt["bytes"]
        assert receipt["url"] == receipt["final_url"]
        sources[row["ACCESSION_NUMBER"]] = {**receipt, "receipt_file": core.bound(receipt_path)}
        record["source_id"] = row["ACCESSION_NUMBER"]
        try:
            record.update(core.inspect(body, row))
            record["acceptance_precedes_information_cutoff"] = dt.datetime.fromisoformat(record["header"]["acceptance_eastern"]) < cutoff
        except Exception as exc:
            record.update(status="SOURCE_PRESERVED_STRUCTURE_UNRESOLVED",
                          inspection_error={"type": type(exc).__name__, "message": str(exc)},
                          known_at=None, available_at=None, historical_security_link_created=False)
        records.append(record)
    complete = [r for r in records if "comparisons" in r]
    groups = []
    for group in queue["groups"]:
        selected = [r for r in records if r["case_id"] == group["case_id"]]
        all_confirmed = all(r["status"] == "ORIGINAL_ISSUER_CIK_SYMBOL_AND_NAMES_CONFIRMED" for r in selected)
        groups.append({**group, "source_status": "MULTIPLE_ORIGINAL_ISSUERS_REPORT_SAME_LITERAL_SYMBOL" if all_confirmed else "SOURCE_DIFFERENCE_OR_STRUCTURE_REQUIRES_REVIEW",
                       "selected_sources_confirmed": sum(r["status"] == "ORIGINAL_ISSUER_CIK_SYMBOL_AND_NAMES_CONFIRMED" for r in selected)})
    summary = {"cases": len(groups), "selected_original_sources": len(records),
               "preserved_original_sources": len(sources),
               "original_source_bytes": sum(s["bytes"] for s in sources.values()),
               "structured_issuer_inspections": len(complete),
               "status_counts": dict(collections.Counter(r["status"] for r in records)),
               "comparison_true_counts": {key: sum(r["comparisons"][key] for r in complete) for key in complete[0]["comparisons"]} if complete else {},
               "header_reporting_owner_role_occurrences": sum(r["header"]["reporting_owner_role_count"] for r in complete),
               "acceptance_precedes_information_cutoff_count": sum(r.get("acceptance_precedes_information_cutoff", False) for r in complete),
               "contributing_observation_rows": selection["contributing_observation_rows"],
               "contributing_unique_sec_occurrences": selection["contributing_unique_sec_occurrences"],
               "completed_47_case_overlap": 0, "mac_http_403_attempts_preserved": 14}
    report = {"schema_version": 1, "status": "BOUNDED_MULTI_CIK_ORIGINAL_SOURCE_VALIDATION",
              "recorded_at_utc": core.now(), "inputs": {"queue": core.bound(BASE / "queue.json"),
              "selection_receipt": core.bound(BASE / "selection_receipt.json"),
              "mac_failure_record": core.bound(mac_failure), "collection_receipt": core.bound(collection_path),
              "source_script": core.bound(Path(__file__).resolve()), "selector_and_issuer_parser": core.bound(ROOT / "scripts/ownership_multi_cik.py"),
              "ownership_bundle_receipt_sha256": core.BUNDLE_SHA, "submission_source_sha256": core.SUBMISSION_SHA},
              "selection_policy": queue["selection_policy"], "information_cutoff": queue["information_cutoff"],
              "groups": groups, "records": records, "source_receipts": sources, "summary": summary,
              "request_policy": collection["request_policy"],
              "parsing_scope": "Original SEC header and original ownershipDocument prefix through issuer end only. No parser receives subsequent holdings, transaction, remarks or signature content.",
              "selection_scope": "Pinned Mac selection regrouped all cohort summaries/observations and checked exact original SEC TSV lineage; this source collector rereads public queue and original public submissions only.",
              "historical_security_links_created": 0, "source_approvals_created": 0, "human_reviews_created": 0,
              "known_at_inferred": False, "historical_availability_inferred": False,
              "continuous_intervals_inferred": False, "vendor_identifiers_exported": False,
              "vendor_names_rows_exported": False, "market_returns_read": False,
              "final_period_sources_requested": False, "final_period_outcomes_opened": False, "model_ready": False}
    assert core.digest((BASE / "queue.json").read_bytes()) == QUEUE_SHA
    assert core.digest(mac_failure.read_bytes()) == MAC_FAILURE_SHA
    for source in sources.values():
        assert core.bound(ROOT / source["path"])["sha256"] == source["sha256"]
    core.write_new(REPORT, core.dump(report))
    print(json.dumps({"report": core.bound(REPORT), "summary": summary}, indent=2), flush=True)
    for record in records:
        print(json.dumps({"case": record["case_id"], "accession": record["queued_public_source_occurrence"]["ACCESSION_NUMBER"],
                          "status": record["status"], "comparisons": record.get("comparisons"),
                          "inspection_error": record.get("inspection_error"),
                          "acceptance": record.get("header", {}).get("acceptance_eastern")}), flush=True)

if __name__ == "__main__":
    main()

