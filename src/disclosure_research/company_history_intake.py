"""Offline, fail-closed intake of manually authorized CRSP Company History CSV.

The output contains *effective-interval candidates*, not approved issuer links.
Neither effective dates nor the date of export establish point-in-time known_at.
"""
import csv
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from .manual_wrds_intake import _copy_source, _hash, _private_directory
from .protocol import canonical_hash

STATUS = "COMPANY_HISTORY_EFFECTIVE_INTERVAL_CANDIDATES_NOT_APPROVED"
FIELDS = ("gvkey", "hcik", "valid_from", "valid_to", "permno")
SHA256 = re.compile(r"[0-9a-f]{64}")
INTEGER = re.compile(r"[0-9]+")
HEADER = re.compile(r"[A-Za-z_][A-Za-z_0-9]{0,127}")
CANDIDATE_HEADER = (
    "source_record", "gvkey_raw", "hcik_raw", "hcik_10", "permno_raw",
    "valid_from_raw", "valid_to_raw", "valid_from", "valid_to",
    "open_start", "open_end", "known_at", "mapping_approved",
)
ISSUE_HEADER = ("source_record", "issue")
CONFLICT_HEADER = ("kind", "left_source_record", "right_source_record")
DEVELOPMENT_LAST = "2022-02-02"


def _load_manifest(path, expected_protocol):
    payload = Path(path).read_bytes()
    if len(payload) > 65536:
        raise ValueError("Source manifest exceeds 64 KiB")
    obj = json.loads(payload)
    if not isinstance(obj, dict) or type(obj.get("schema_version")) is not int or obj["schema_version"] != 1:
        raise ValueError("Expected schema_version=1 metadata object")
    if obj.get("product") not in {"crsp_a_ccm", "crsp_m_ccm", "crsp_q_ccm"}:
        raise ValueError("Unknown CRSP/Compustat product")
    if obj.get("table") not in {"companyhistory", "comphist"}:
        raise ValueError("Not a declared Company History table")
    if obj.get("data_kind") not in {"AUTHORIZED_VENDOR_EXPORT", "SYNTHETIC_ENGINEERING_FIXTURE"}:
        raise ValueError("Source data_kind must distinguish real vendor exports from fixtures")
    if obj.get("protocol_sha256") != expected_protocol:
        raise ValueError("Manifest is not bound to the locked protocol")
    if not isinstance(obj.get("source_sha256"), str) or not SHA256.fullmatch(obj["source_sha256"]):
        raise ValueError("Source SHA-256 must be provided")
    if obj.get("date_format") not in {"YYYYMMDD", "YYYY-MM-DD"}:
        raise ValueError("Explicit date_format required")
    columns = obj.get("columns")
    if not isinstance(columns, dict) or set(columns) != set(FIELDS):
        raise ValueError("Explicit five-field mapping required (permno may be null)")
    present = [x for x in columns.values() if x is not None]
    if (any(not isinstance(x, str) or not HEADER.fullmatch(x) for x in present)
            or any(columns[k] is None for k in FIELDS if k != "permno")
            or len({x.lower() for x in present}) != len(present)):
        raise ValueError("Invalid or ambiguous explicit field names")
    for side in ("open_start_values", "open_end_values"):
        values = obj.get(side)
        if (not isinstance(values, list) or len(values) > 12
                or any(not isinstance(v, str) or len(v) > 32 for v in values)
                or len(values) != len(set(values))):
            raise ValueError("Explicit unique open-bound values required, even when empty")
    # Date semantics and source vintage require independent documentation/review.
    if (obj.get("claimed_known_at") is not None
            or obj.get("known_at") is not None or obj.get("available_at") is not None
            or obj.get("source_approved") is not False):
        raise ValueError("Company History intake cannot approve known_at or source")
    return obj, payload


def _date_value(raw, *, side, manifest):
    sentinels = manifest["open_start_values" if side == "start" else "open_end_values"]
    if raw in sentinels:
        return "", True
    if manifest["date_format"] == "YYYYMMDD":
        if not re.fullmatch(r"[0-9]{8}", raw):
            raise ValueError("non-calendar date")
        val = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    else:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw):
            raise ValueError("non-calendar date")
        val = raw
    date.fromisoformat(val)
    return val, False


def _cik_key(raw):
    if not INTEGER.fullmatch(raw) or len(raw) > 10 or int(raw) == 0:
        return None
    return raw.zfill(10)


def _conflicts(conn, target, *, cap=500):
    """Count overlapping different-CIK intervals, retaining bounded examples."""
    total = Counter()
    with target.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CONFLICT_HEADER)
        for kind, key in (("GVKEY_OVERLAP_DIFFERENT_CIK", "gvkey"),
                          ("PERMNO_OVERLAP_DIFFERENT_CIK", "permno")):
            sql = (f"SELECT source_record, {key}, hcik, start_cmp, end_cmp FROM stage "
                   f"WHERE {key} IS NOT NULL ORDER BY {key}, start_cmp, end_cmp, source_record")
            previous_key, active = None, []
            for record, observed_key, cik, start, end in conn.execute(sql):
                if observed_key != previous_key:
                    previous_key, active = observed_key, []
                active = [a for a in active if a[2] >= start]
                if len(active) > 10000:
                    raise ValueError("Overlapping-history fanout exceeds safety bound")
                for left_record, left_cik, _ in active:
                    if left_cik != cik:
                        total[kind] += 1
                        if sum(total.values()) <= cap:
                            writer.writerow((kind, left_record, record))
                active.append((record, cik, end))
    return total


def build_company_history_intake(source, metadata, output, *, config, repo_root):
    """Preserve raw bytes, stage bounded candidates, and report conflicts for review.

    A successful result is not a research approval and must never populate known_at.
    Only history starting by the late-development boundary is interpreted.
    """
    root = Path(repo_root).resolve(strict=True)
    source = Path(source).resolve(strict=True)
    metadata = Path(metadata).resolve(strict=True)
    destination = _private_directory(output, root)
    if not source.is_file() or not metadata.is_file():
        raise ValueError("Require existing regular source and manifest files")
    if source.stat().st_size > 4 * 1024**3:
        raise ValueError("Company History exceeds 4 GiB intake safety bound")
    protocol_sha = canonical_hash(config)
    manifest, manifest_bytes = _load_manifest(metadata, protocol_sha)
    if _hash(source) != manifest["source_sha256"]:
        raise ValueError("Unmatched raw source SHA-256")
    if destination.is_relative_to(source.parent) or destination.is_relative_to(metadata.parent):
        # Do not create output as a child of a consumed source directory.
        raise ValueError("Output must not nest within a source directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".company-history-", dir=destination.parent))
    tmp.chmod(0o700)
    try:
        preserved = tmp / "original.csv"
        copied_sha, copied_bytes = _copy_source(source, preserved)
        if copied_sha != manifest["source_sha256"]:
            raise ValueError("Source changed during preservation")
        (tmp / "input_manifest.json").write_bytes(manifest_bytes)
        os.chmod(tmp / "input_manifest.json", 0o400)
        db = sqlite3.connect(tmp / "processing.sqlite")
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("CREATE TABLE stage (source_record INTEGER PRIMARY KEY, gvkey TEXT, "
                   "permno TEXT, hcik TEXT, start_cmp TEXT, end_cmp TEXT, "
                   "start_raw TEXT, end_raw TEXT)")
        count = Counter()
        candidate_file, issue_file = tmp / "candidate_intervals.csv", tmp / "review_issues.csv"
        with (preserved.open("r", encoding="utf-8-sig", newline="") as raw,
              candidate_file.open("x", encoding="utf-8", newline="") as candidate_handle,
              issue_file.open("x", encoding="utf-8", newline="") as issue_handle):
            reader = csv.reader(raw, strict=True)
            header = next(reader, None)
            if (not header or len(header) > 256
                    or any(not HEADER.fullmatch(h) for h in header)
                    or len({h.lower() for h in header}) != len(header)):
                raise ValueError("Malformed or duplicate source CSV header")
            indices = {name: [h.lower() for h in header].index(field.lower())
                       for name, field in manifest["columns"].items() if field is not None}
            cand_writer, issue_writer = csv.writer(candidate_handle), csv.writer(issue_handle)
            cand_writer.writerow(CANDIDATE_HEADER)
            issue_writer.writerow(ISSUE_HEADER)
            for ordinal, row in enumerate(reader, start=1):
                if ordinal > 5_000_000:
                    raise ValueError("Company History exceeds 5 million records")
                if len(row) != len(header):
                    raise ValueError(f"Malformed CSV column count at record {ordinal}")
                value = {k: row[i] for k, i in indices.items()}
                value.setdefault("permno", "")
                count["raw_rows"] += 1
                flagged = []
                cik = _cik_key(value["hcik"])
                if cik is None:
                    flagged.append("INVALID_HCIK")
                if (not INTEGER.fullmatch(value["gvkey"]) or len(value["gvkey"]) > 12
                        or int(value["gvkey"]) == 0):
                    flagged.append("INVALID_GVKEY")
                try:
                    first, open_first = _date_value(value["valid_from"], side="start", manifest=manifest)
                    last, open_last = _date_value(value["valid_to"], side="end", manifest=manifest)
                except ValueError:
                    flagged.append("UNRESOLVED_EFFECTIVE_BOUNDS")
                    first = last = ""
                    open_first = open_last = False
                if first and last and first > last:
                    flagged.append("REVERSED_EFFECTIVE_BOUNDS")
                permno = value["permno"]
                if (not permno or not INTEGER.fullmatch(permno) or len(permno) > 20
                        or int(permno) == 0):
                    flagged.append("NO_LINKED_PERMNO")
                    permno_key = None
                else:
                    permno_key = str(int(permno))
                if not flagged or flagged == ["NO_LINKED_PERMNO"]:
                    if first and first > DEVELOPMENT_LAST:
                        flagged.append("OUTSIDE_DEVELOPMENT_SCOPE")
                    elif last and last < "2009-10-07":
                        flagged.append("BEFORE_DEVELOPMENT_SCOPE")
                    else:
                        cand_writer.writerow((
                            ordinal, value["gvkey"], value["hcik"], cik, permno, value["valid_from"],
                            value["valid_to"], first, last, open_first, open_last, "", "false",
                        ))
                        count["effective_interval_candidates"] += 1
                        db.execute("INSERT INTO stage VALUES (?,?,?,?,?,?,?,?)",
                                   (ordinal, value["gvkey"], permno_key, cik,
                                    first or "0000-01-01", last or "9999-12-31",
                                    value["valid_from"], value["valid_to"]))
                for reason in flagged:
                    count[reason] += 1
                    issue_writer.writerow((ordinal, reason))
                if ordinal % 10000 == 0:
                    db.commit()
        db.commit()
        if count["raw_rows"] == 0:
            raise ValueError("Company History export has no data rows")
        duplicate_projections = db.execute(
            "SELECT COALESCE(SUM(n-1),0) FROM "
            "(SELECT COUNT(*) AS n FROM stage "
            "GROUP BY gvkey,permno,hcik,start_cmp,end_cmp HAVING COUNT(*)>1)"
        ).fetchone()[0]
        count["duplicate_interval_projection_excess"] = duplicate_projections
        # Preserve normalized comparison-key collisions, including those whose
        # raw CIK or PERMNO spelling differs. These are not necessarily byte-
        # identical original records. Candidate rows are never removed.
        with issue_file.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            for (record,) in db.execute(
                "SELECT source_record FROM (SELECT source_record, "
                "ROW_NUMBER() OVER (PARTITION BY gvkey,permno,hcik,start_cmp,end_cmp "
                "ORDER BY source_record) AS duplicate_rank FROM stage) "
                "WHERE duplicate_rank>1 ORDER BY source_record"
            ):
                writer.writerow((record, "DUPLICATE_INTERVAL_PROJECTION"))
                count["DUPLICATE_INTERVAL_PROJECTION"] += 1
        if count["DUPLICATE_INTERVAL_PROJECTION"] != duplicate_projections:
            raise ValueError("Candidate projection duplication accounting mismatch")
        overlaps = _conflicts(db, tmp / "overlap_examples.csv")
        db.close()
        (tmp / "processing.sqlite").unlink()
        if _hash(source) != copied_sha:
            raise ValueError("Source changed after processing")
        public = {
            "schema_version": 1, "status": STATUS, "product": manifest["product"],
            "table": manifest["table"], "data_kind": manifest["data_kind"], "raw_rows": count["raw_rows"],
            "effective_interval_candidates": count["effective_interval_candidates"],
            "counts_by_issue": dict(sorted(count.items())),
            "overlapping_different_cik_pair_counts": dict(sorted(overlaps.items())),
            "example_cap": 500, "source_approvals": 0, "identity_approvals": 0,
            "historical_known_at_established": False, "model_ready": False,
            "final_period_opened": False,
        }
        summary_bytes = (json.dumps(public, indent=2, sort_keys=True) + "\n").encode()
        (tmp / "public_summary.json").write_bytes(summary_bytes)
        files = ("original.csv", "input_manifest.json", "candidate_intervals.csv",
                 "review_issues.csv", "overlap_examples.csv", "public_summary.json")
        receipt = {
            "schema_version": 1, "status": STATUS, "data_kind": manifest["data_kind"],
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "protocol_sha256": protocol_sha,
            "source_sha256": copied_sha, "source_bytes": copied_bytes,
            "input_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "files": {name: {"sha256": _hash(tmp / name), "bytes": (tmp / name).stat().st_size}
                      for name in files},
            "model_ready": False, "source_approvals": 0, "identity_approvals": 0,
            "historical_known_at_established": False, "prior_arithmetic_review_modified": False,
            "final_period_opened": False, "research_release": "blocked",
        }
        (tmp / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        for name in (*files, "receipt.json"):
            os.chmod(tmp / name, 0o400)
        # The final bundle is immutable for this run and never overwrites an existing output.
        tmp.rename(destination)
        return public
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
