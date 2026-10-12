"""Independent exact-literal SEC ownership to complete dated CRSP Names check.

Reconstructs the 2019Q4 pilot anchor from original raw source files without
reading the upstream calculated SEC/Names relationship Parquet tables.
All returned metrics are aggregate, never verified CIK known-at times.
"""

import csv
import hashlib
import json
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from .pilot_issuer_anchor import STATUS as ANCHOR_STATUS

STATUS = "ORIGINAL_SEC_AND_NAMES_INDEPENDENT_2020_ANCHOR_RECONCILED_NOT_APPROVED"
CIK = re.compile(r"[0-9]{10}")
PERMNO = re.compile(r"[0-9]{1,20}")
SEC_FIELDS = (
    "ACCESSION_NUMBER", "FILING_DATE", "PERIOD_OF_REPORT", "DATE_OF_ORIG_SUB",
    "NO_SECURITIES_OWNED", "NOT_SUBJECT_SEC16", "FORM3_HOLDINGS_REPORTED",
    "FORM4_TRANS_REPORTED", "DOCUMENT_TYPE", "ISSUERCIK", "ISSUERNAME",
    "ISSUERTRADINGSYMBOL", "REMARKS",
)


def _require(ok, why):
    if not ok:
        raise ValueError(why)


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _row_cik(raw):
    if not isinstance(raw, str) or not re.fullmatch(r"[0-9]{1,10}", raw) or int(raw) == 0:
        return None
    return str(int(raw)).zfill(10)


def _source_file(path, *, limit):
    source = Path(path)
    _require(not source.is_symlink(), "Original source must not be a symlink")
    source = source.resolve(strict=True)
    _require(source.is_file() and source.stat().st_size <= limit,
             "Original source missing or exceeds size limit")
    return source


def independently_verify_anchor(anchor_dir, ownership_receipt, original_sec_tsv,
                                original_names_csv, output, *, repo_root):
    root = Path(repo_root).resolve(strict=True)
    out = Path(output).resolve()
    _require(not out.exists() and out.is_relative_to(root / "reports"),
             "Output must be a new aggregate report in the repository reports directory")
    anchor = Path(anchor_dir).resolve(strict=True)
    info = json.loads((anchor / "public_summary.json").read_bytes())
    receipt = json.loads((anchor / "receipt.json").read_bytes())
    source_data = (anchor / "private_issuer_rows.jsonl").read_bytes()
    _require(info["status"] == receipt["status"] == ANCHOR_STATUS
             and not info["final_period_opened"] and not info["model_ready"]
             and not info["historical_known_at_established"]
             and info["security_links_approved"] == 0
             and receipt["source_approvals"] == 0,
             "Original pilot anchor is not the unapproved source")
    for name in ("public_summary.json", "private_issuer_rows.jsonl"):
        file = anchor / name
        _require(receipt["files"][name]["sha256"] == _sha(file)
                 and receipt["files"][name]["bytes"] == file.stat().st_size,
                 "Original pilot anchor output hash mismatch")
    details = [json.loads(line) for line in source_data.decode("utf-8").splitlines()]
    ciks = {row["original_sec_filer_cik"]: row["pilot_candidate_permno"] for row in details}
    _require(len(details) == len(ciks) == info["pilot_issuers"] == 20
             and len(set(ciks.values())) == 20
             and all(CIK.fullmatch(k) for k in ciks)
             and all(isinstance(v, str) and PERMNO.fullmatch(v) and int(v) > 0
                     for v in ciks.values()),
             "Private issuer anchors have invalid CIK/PERMNO uniqueness")
    _require(all(row["known_at"] is None and row["available_at"] is None
                 and row["source_identity_approval"] is False
                 and row["historical_link_validity_established"] is False
                 for row in details), "An earlier issuer anchor cannot establish approved historical known-at")
    private_per_cik = {row["original_sec_filer_cik"]: row for row in details}
    pin = info["provenance"]
    ownership_receipt = _source_file(ownership_receipt, limit=1024 * 1024)
    sec_path = _source_file(original_sec_tsv, limit=32 * 1024 * 1024)
    names_path = _source_file(original_names_csv, limit=256 * 1024 * 1024)
    _require(pin["ownership_cohort_receipt_sha256"] == _sha(ownership_receipt)
             and pin["original_SEC_quarterly_TSV_sha256"] == _sha(sec_path)
             and pin["original_CRSP_Names_CSV_sha256"] == _sha(names_path),
             "Independent source bytes do not match original pinned evidence")
    owner = json.loads(ownership_receipt.read_bytes())
    _require(owner["inputs"]["sec_submission_sha256"] == pin["original_SEC_quarterly_TSV_sha256"]
             and owner["inputs"]["names_source_sha256"] == pin["original_CRSP_Names_CSV_sha256"]
             and owner["source_quarter"] == "2019Q4" and owner["cohort_year"] == 2020
             and owner["source_approvals"] == 0 and owner["final_period_opened"] is False,
             "Source provenance or scope changed from original SEC/Names cohort")
    # Rebuild an entirely new symbol/CIK path directly from original quarterly
    # issuer fields; neither reporter CIK nor accession-prefix issuer is used.
    sec_records, rows_total = [], 0
    with sec_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t", strict=True, restkey="__extra__")
        _require(reader.fieldnames == list(SEC_FIELDS),
                 "Original quarterly submission table has different columns")
        for record in reader:
            rows_total += 1
            _require("__extra__" not in record and None not in record.values(),
                     "Malformed original SEC quarterly source row")
            cik = _row_cik(record["ISSUERCIK"])
            if cik in ciks:
                date_record = datetime.strptime(record["FILING_DATE"], "%d-%b-%Y").date().isoformat()
                _require("2019-10-01" <= date_record <= "2019-12-31",
                         "Wrong quarter for selected original SEC issuer record")
                sec_records.append((cik, date_record, record["ISSUERTRADINGSYMBOL"]))
    _require(rows_total == owner["counts"]["original_sec_occurrences"],
             "Original SEC quarter did not retain all submitted occurrences")
    symbols = {sym for _, _, sym in sec_records}
    symbol_index, security_index = defaultdict(list), defaultdict(list)
    names_total = 0
    with names_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, strict=True, restkey="__extra__")
        mandatory = {
            "permno", "ticker", "tradingsymbol", "secinfostartdt", "secinfoenddt",
            "securitybegdt", "securityenddt",
        }
        _require(reader.fieldnames is not None and mandatory.issubset(reader.fieldnames)
                 and len(reader.fieldnames) == 24 and len(reader.fieldnames) == len(set(reader.fieldnames)),
                 "Original Names data dictionary field coverage differs")
        for record in reader:
            names_total += 1
            _require("__extra__" not in record and None not in record.values(),
                     "Malformed original Names source record")
            row = (
                record["permno"], record["secinfostartdt"], record["secinfoenddt"],
                record["securitybegdt"], record["securityenddt"],
                record["ticker"], record["tradingsymbol"],
            )
            if row[0] in ciks.values():
                security_index[row[0]].append(row)
            for sym in {record["ticker"], record["tradingsymbol"]} & symbols:
                symbol_index[sym].append(row)
    _require(names_total == owner["counts"]["original_names_source_rows_checked"],
             "Original complete Names source row count changed")
    counts, matching = Counter(), Counter()
    for cik, day, symbol in sec_records:
        # A global exact-symbol match is NOT enough. Every original descriptor
        # for this security on that date must be checked for overlaps.
        candidates = [r for r in symbol_index.get(symbol, ())
                      if r[1] <= day <= r[2]]
        if len(candidates) != 1:
            counts["missing_or_globally_ambiguous_symbol"] += 1
            continue
        row = candidates[0]
        if row[0] != ciks[cik]:
            counts["matched_other_security"] += 1
            continue
        same_security = [r for r in security_index[row[0]]
                         if r[1] <= day <= r[2]]
        if len(same_security) != 1:
            counts["overlapping_security_descriptors"] += 1
            continue
        if not (row[3] <= day <= row[4] and row[1] <= "2020-01-01" <= row[2]):
            counts["outside_security_lifetime_or_selection_interval"] += 1
            continue
        if day < "2019-12-31":
            counts["strictly_earlier"] += 1
            matching[(cik, "earlier")] += 1
        else:
            counts["unresolved_cutoff_day"] += 1
            matching[(cik, "cutoff")] += 1
    _require(not any(counts.get(k) for k in (
        "missing_or_globally_ambiguous_symbol", "matched_other_security",
        "overlapping_security_descriptors", "outside_security_lifetime_or_selection_interval",
    )), "Independent literal issuer mapping found ambiguous or mismatched records")
    _require(counts["strictly_earlier"] == info["strictly_earlier_dated_SEC_ownership_name_observations"]
             and counts["unresolved_cutoff_day"] ==
             info["cutoff_day_observations_retained_but_not_used_as_earlier"]
             and sum(counts.values()) == len(sec_records),
             "Independent SEC/Names anchors disagree with previous candidate evidence")
    _require(len({key for key in ciks if matching[(key, "earlier")] > 0}) ==
             info["securities_with_strictly_earlier_unambiguous_matching_issuer_cik"],
             "Independent issuer coverage differs")
    for cik in ciks:
        _require(matching[(cik, "earlier")] ==
                 private_per_cik[cik]["strictly_earlier_2019q4_source_observations"]
                 and matching[(cik, "cutoff")] ==
                 private_per_cik[cik]["unresolved_clock_2019q4_source_observations"],
                 "Independent per-issuer original-source counts changed")
    _require(_sha(sec_path) == pin["original_SEC_quarterly_TSV_sha256"]
             and _sha(names_path) == pin["original_CRSP_Names_CSV_sha256"],
             "An original source file changed during independent verification")
    public = {
        "schema_version": 1, "status": STATUS,
        "independent_method": "Literal SEC ISSUERCIK/ISSUERTRADINGSYMBOL + original complete dated CRSP Names",
        "quarter": "2019Q4", "selection_year": 2020,
        "original_sec_submissions_reexamined": rows_total,
        "original_names_descriptors_reexamined": names_total,
        "original_sec_submissions_from_20_pilot_ciks": len(sec_records),
        "pilot_issuer_security_pairs": len(ciks),
        "securities_with_independently_matched_strictly_earlier_anchors": len(
            {key for key in ciks if matching[(key, "earlier")] > 0}
        ),
        "strictly_earlier_unambiguous_issuer_security_observations": counts["strictly_earlier"],
        "cutoff_day_unresolved_observations": counts["unresolved_cutoff_day"],
        "ambiguous_or_mismatched_source_observations": 0,
        "per_issuer_earlier_and_cutoff_counts_identical_to_first_audit": True,
        "complete_raw_SEC_and_Names_source_hashes_rechecked": True,
        "first_audit_receipt_sha256": _sha(anchor / "receipt.json"),
        "original_source_sha256": {
            "sec_submission_tsv": pin["original_SEC_quarterly_TSV_sha256"],
            "crsp_names_csv": pin["original_CRSP_Names_CSV_sha256"],
            "cohort_receipt": pin["ownership_cohort_receipt_sha256"],
        },
        "new_security_link_approvals": 0,
        "historical_effective_interval_established": False,
        "historical_known_at_established": False,
        "source_release_or_vendor_availability_verified": False,
        "model_ready": False, "actual_final_2022_2025_opened": False,
        "caveat": "Independent original-source matching confirms one quarter's issuer observations, not continuous historical links or publication time.",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pilot-independent-", dir=out.parent) as scratch:
        temp = Path(scratch) / "summary.json"
        temp.write_text(json.dumps(public, indent=2, sort_keys=True) + "\n")
        temp.replace(out)
    return public
