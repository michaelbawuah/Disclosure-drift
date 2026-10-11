"""Resolve the pinned cutoff queue offline on the authorized Mac.

The original Mac HTTP403 run stays immutable. Public originals collected using
ordinary container HTTPS must be transferred byte-for-byte before this runs.
"""
import argparse
import collections
import datetime as dt
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cutoff_metadata_audit", ROOT / "scripts/ownership_cutoff_clock_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
FAILED_REPORT_SHA = "3194c73ebeaeee8211c1102044dbfa5a26f91fbcd86b9c80f43bb1e85da512c1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="outputs/cutoff-clock-followup-20261011")
    parser.add_argument("--output", default="outputs/cutoff-clock-followup-20261011/resolved")
    parser.add_argument("--report", default="reports/ownership_cutoff_clock_resolved.json")
    args = parser.parse_args()
    base, out, report_path = (ROOT / x for x in (args.base, args.output, args.report))
    if out.exists() or report_path.exists():
        raise FileExistsError("Use new output and report paths")
    started = audit.now()
    old_path = ROOT / "reports/ownership_cutoff_clock_audit.json"
    old_bytes = old_path.read_bytes()
    if audit.digest(old_bytes) != FAILED_REPORT_SHA:
        raise ValueError("Original Mac attempt report pin differs")
    old = json.loads(old_bytes)
    executed_snapshot = base / "ownership_cutoff_clock_audit.executed.py"
    if audit.digest(executed_snapshot.read_bytes()) != old["script"]["sha256"]:
        raise ValueError("Preserved executed original audit code differs")
    inspector = audit.bound(ROOT / "scripts/ownership_cutoff_clock_audit.py")
    for relative, binding in old["inputs"].items():
        if audit.bound(ROOT / relative) != binding:
            raise ValueError("Original pinned input or calendar code differs")
    receipt_path = ROOT / "data/private/sec-ownership-corrob/development-v1/receipt.json"
    if audit.digest(receipt_path.read_bytes()) != old["bundle_receipt_sha256"]:
        raise ValueError("Original bundle receipt differs")
    before = {str(p.relative_to(ROOT)): audit.digest(p.read_bytes()) for p in receipt_path.parent.rglob("*") if p.is_file()}
    queue_path = base / "queue.json"
    if audit.bound(queue_path) != old["queue"]:
        raise ValueError("Original complete queue differs")
    queue = json.loads(queue_path.read_bytes())
    selected_path = base / "private/selected_cases.json"
    if audit.bound(selected_path) != old["private_evidence_bindings"]["selected_cases.json"]:
        raise ValueError("Original private case binding differs")
    private = json.loads(selected_path.read_bytes())
    cases = {x["security_id"]: x for x in private["cohort"]}
    observations = private["observations"]
    if len(cases) != 14 or len(observations) != 39:
        raise ValueError("Complete original case accounting differs")
    source_dir = base / "container-originals"
    collection_path = source_dir / "collection_receipt.json"
    collection = json.loads(collection_path.read_bytes())
    if (collection["queue_sha256"] != old["queue"]["sha256"]
            or collection["accessions"] != old["summary"]["distinct_original_accessions"]):
        raise ValueError("Public collection is bound to a different queue")
    collector = ROOT / collection["collector"]["path"]
    if audit.digest(collector.read_bytes()) != collection["collector"]["sha256"]:
        raise ValueError("Executed public collector differs")
    source_receipts, records = {}, []
    cutoff = dt.datetime.fromisoformat(old["calendar"]["cutoff_utc"])
    for row in queue["source_occurrences"]:
        accession = row["ACCESSION_NUMBER"]
        source_path = source_dir / (accession + ".txt")
        receipt = json.loads((source_dir / (accession + ".receipt.json")).read_bytes())
        body = source_path.read_bytes()
        url = f"https://www.sec.gov/Archives/edgar/data/{int(row['ISSUERCIK'])}/{accession.replace('-', '')}/{accession}.txt"
        if (audit.digest(body) != receipt["sha256"] or len(body) != receipt["bytes"]
                or receipt["url"] != url or receipt["final_url"] != url
                or receipt["path"] != str(source_path.relative_to(ROOT)) or receipt["http_status"] != 200):
            raise ValueError("Transferred public source bytes or receipt differ")
        source_receipts[accession] = {**receipt, "receipt": audit.bound(source_dir / (accession + ".receipt.json"))}
        record = {"quarterly_source_occurrence": row, "source_id": accession}
        try:
            record.update(audit.inspect(body, row))
            accepted = dt.datetime.fromisoformat(record["header"]["acceptance_utc"])
            record.update(acceptance_vs_cutoff=("BEFORE_CUTOFF" if accepted < cutoff else "AFTER_CUTOFF" if accepted > cutoff else "AT_CUTOFF"),
                          acceptance_minus_cutoff_seconds=(accepted - cutoff).total_seconds())
        except Exception as exc:
            record.update(status="SOURCE_STRUCTURE_OR_METADATA_UNRESOLVED", error_type=type(exc).__name__,
                          error=str(exc), acceptance_vs_cutoff="UNRESOLVED")
        record.update(known_at=None, available_at=None, effective_start=None, effective_end=None,
                      historical_security_link_created=False)
        records.append(record)
    by_record = {x["quarterly_source_occurrence"]["source_tsv_record"]: x for x in records}
    private_results = []
    for security in cases:
        ordinals = sorted({x["source_tsv_record"] for x in observations if x["security_id"] == security})
        relations = collections.Counter(by_record[n]["acceptance_vs_cutoff"] for n in ordinals)
        values = set(relations)
        status = ("ALL_ORIGINAL_ACCEPTANCES_BEFORE_CUTOFF" if values == {"BEFORE_CUTOFF"} else
                  "ALL_ORIGINAL_ACCEPTANCES_AFTER_CUTOFF" if values == {"AFTER_CUTOFF"} else
                  "ORIGINAL_ACCEPTANCES_BOTH_BEFORE_AND_AFTER" if values == {"BEFORE_CUTOFF", "AFTER_CUTOFF"} else
                  "HAS_AT_CUTOFF_OR_UNRESOLVED_ACCEPTANCE")
        private_results.append({"security_id": security, "source_tsv_records": ordinals, "clock_status": status,
                                "acceptance_relation_occurrences": dict(relations), "known_at": None, "available_at": None})
    out.mkdir(parents=True, mode=0o700)
    (out / "private").mkdir(mode=0o700)
    audit.write_new(out / "private/case_results.json", private_results, private=True)
    inspected = [x for x in records if "comparisons" in x]
    grouped = collections.defaultdict(list)
    for record in records:
        grouped[record["source_id"]].append(record)
    unique_clocks = {}
    for accession, group in grouped.items():
        clock_values = {x["acceptance_vs_cutoff"] for x in group}
        unique_clocks[accession] = next(iter(clock_values)) if len(clock_values) == 1 else "INCONSISTENT_OCCURRENCE_CLOCKS"
    summary = {**old["summary"],
        "original_sources_preserved": len(source_receipts),
        "source_bytes": sum(x["bytes"] for x in source_receipts.values()),
        "occurrence_acceptance_relation_counts": dict(collections.Counter(x["acceptance_vs_cutoff"] for x in records)),
        "distinct_accession_acceptance_relation_counts": dict(collections.Counter(unique_clocks.values())),
        "case_clock_status_counts": dict(collections.Counter(x["clock_status"] for x in private_results)),
        "case_counts_with_at_least_one_acceptance": {relation: sum(x["acceptance_relation_occurrences"].get(relation, 0) > 0 for x in private_results)
                                                    for relation in ("BEFORE_CUTOFF", "AT_CUTOFF", "AFTER_CUTOFF", "UNRESOLVED")},
        "original_inspection_status_counts": dict(collections.Counter(x["status"] for x in records)),
        "comparison_true_counts": {key: sum(x["comparisons"][key] for x in inspected) for key in inspected[0]["comparisons"]} if inspected else {},
        "reporting_owner_role_occurrences": sum(x["header"]["reporting_owner_role_count"] for x in inspected),
        "source_structure_or_metadata_errors": len(records) - len(inspected), "source_preservation_errors": 0,
        "prior_mac_http403_accessions": old["summary"]["source_preservation_errors"],
        "minimum_acceptance_eastern": min(x["header"]["acceptance_eastern"] for x in inspected) if inspected else None,
        "maximum_acceptance_eastern": max(x["header"]["acceptance_eastern"] for x in inspected) if inspected else None
    }
    resolver = audit.bound(Path(__file__).resolve())
    report = {**old, "status": "ORIGINAL_SEC_ACCEPTANCE_CLOCKS_RESOLVED_NO_AVAILABILITY_INFERRED",
        "started_utc": started, "completed_utc": audit.now(), "original_mac_attempt_report": audit.bound(old_path),
        "script": resolver, "original_audit_script": old["script"],
        "preserved_original_audit_script": audit.bound(executed_snapshot),
        "metadata_inspector_script": inspector,
        "inspector_change_since_mac_attempt": "Only E402 noqa annotations on the two repository bootstrap imports; original executed bytes retained",
        "public_collection_script": audit.bound(collector), "collection_receipt": audit.bound(collection_path),
        "source_receipts": source_receipts, "records": records, "summary": summary,
        "request_policy": collection["request_policy"],
        "private_evidence_bindings": {"selected_cases.json": audit.bound(selected_path),
                                      "case_results.json": audit.bound(out / "private/case_results.json")},
        "scope": {**old["scope"], "all_distinct_accessions_inspected": len(inspected) == len(records)},
        "source_transport": {"request_host": "Ordinary container urllib HTTPS", "inspection_host": "Authorized Mac",
                             "identical_urls_and_honest_user_agent": True, "original_mac_http403_receipts_preserved": True,
                             "byte_hashes_checked_on_mac_before_and_after_inspection": True,
                             "initial_one_source_inline_probe_receipt_preserved": True}
    }
    after = {str(p.relative_to(ROOT)): audit.digest(p.read_bytes()) for p in receipt_path.parent.rglob("*") if p.is_file()}
    if after != before or old_path.read_bytes() != old_bytes:
        raise ValueError("Original bundle or Mac attempt evidence changed")
    for relative, binding in old["inputs"].items():
        if audit.bound(ROOT / relative) != binding:
            raise ValueError("Original consumed input changed")
    for source in source_receipts.values():
        body = (ROOT / source["path"]).read_bytes()
        if len(body) != source["bytes"] or audit.digest(body) != source["sha256"]:
            raise ValueError("Transferred source changed during inspection")
    if audit.bound(Path(__file__).resolve()) != resolver or audit.bound(ROOT / inspector["path"]) != inspector:
        raise ValueError("Resolver or metadata inspector code changed")
    audit.write_new(report_path, report)
    audit.write_new(out / "execution_receipt.json", {"report": audit.bound(report_path), "script": resolver,
                    "completed_utc": audit.now(), "summary": summary})
    print(json.dumps({"report": audit.bound(report_path), "summary": summary}, indent=2), flush=True)


if __name__ == "__main__":
    main()

