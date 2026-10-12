"""Independent coverage/definition diagnostic for saved CRSP and public Fama-French daily series.

Never substitute the public factor's different historical U.S. equity universe for
the locked study benchmark or read protected holdout target observations.
"""

import csv
import hashlib
import io
import json
import os
import re
import tempfile
import zipfile
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median

from .protocol import canonical_hash

STATUS = "PUBLIC_COMPARISON_NOT_PRIMARY_SOURCE_APPROVAL"
PUBLIC_URL = "https://mba.tuck.dartmouth.edu/pages/Faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip"
MAX_ZIP_BYTES = 12 * 1024 * 1024
MAX_FF_BYTES = 64 * 1024 * 1024
EARLIEST_BOUNDARY = "2009-10-07"
LATEST_BOUNDARY = "2022-02-02"
EXPECTED_HEADER = ["", "Mkt-RF", "SMB", "HML", "RF"]
_PREAMBLE = re.compile(r"^This file was created by using the ([0-9]{6}) CRSP database\.$")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _day(value):
    _require(isinstance(value, str) and re.fullmatch(r"\d{8}", value),
             "Expected strict 8-digit date in public factor")
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except ValueError as exc:
        raise ValueError("Invalid public factor date") from exc


def _crsp_rows(raw):
    """Only a previously preserved two-field CRSP daily market export is accepted."""
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), restkey="extra")
    _require(reader.fieldnames and set(reader.fieldnames) == {"dlycaldt", "vwretd"}
             and len(reader.fieldnames) == 2, "CRSP source needs exact two-field header")
    rows = {}
    for index, entry in enumerate(reader, start=2):
        _require("extra" not in entry and None not in entry.values(),
                 f"Malformed source at record {index}")
        try:
            day = date.fromisoformat(entry["dlycaldt"])
            value = Decimal(entry["vwretd"])
        except (ValueError, InvalidOperation) as exc:
            raise ValueError(f"Invalid CRSP date or return at record {index}") from exc
        _require(day.isoformat() == entry["dlycaldt"] and value.is_finite(),
                 f"Invalid source value at record {index}")
        _require(EARLIEST_BOUNDARY <= day.isoformat() <= LATEST_BOUNDARY,
                 "Out-of-range source crosses the development return boundary")
        _require(value >= -1, "CRSP daily benchmark total return cannot be below -100%")
        _require(day not in rows, f"Duplicate source market date at record {index}")
        rows[day] = value
    _require(rows, "CRSP source contains no sessions")
    return rows


def _fama_french_rows(raw):
    """Parse current published public ZIP, stopping before any later factor *values*."""
    _require(0 < len(raw) <= MAX_ZIP_BYTES, "Fama-French ZIP exceeds bounded input size")
    try:
        bundle = zipfile.ZipFile(io.BytesIO(raw))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("Invalid public factor ZIP") from exc
    with bundle:
        members = bundle.infolist()
        _require(len(members) == 1 and members[0].file_size <= MAX_FF_BYTES
                 and members[0].filename == "F-F_Research_Data_Factors_daily.csv",
                 "Unexpected Fama-French source ZIP shape or size")
        result = {}
        with bundle.open(members[0], "r") as binary:
            text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
            reader = csv.reader(text, strict=True)
            first = next(reader, None)
            _require(first is not None and len(first) == 1
                     and _PREAMBLE.fullmatch(first[0]), "Unexpected public file vintage preamble")
            vintage = _PREAMBLE.fullmatch(first[0]).group(1)
            found_header = False
            stopped_at = None
            previous_day = None
            for row in reader:
                if not found_header:
                    if row == EXPECTED_HEADER:
                        found_header = True
                    continue
                if not row:
                    continue
                if len(row) == 1 and row[0].startswith("Copyright"):
                    break
                _require(len(row) == 5, "Unexpected factor data width")
                day = _day(row[0].strip())
                _require(previous_day is None or day > previous_day,
                         "Public factor dates are not strictly increasing")
                previous_day = day
                if day.isoformat() > LATEST_BOUNDARY:
                    stopped_at = day.isoformat()
                    break
                # Fama-French's Mkt-RF and RF are both percentage points per day.
                try:
                    excess = Decimal(row[1].strip())
                    rf = Decimal(row[4].strip())
                except InvalidOperation as exc:
                    raise ValueError("Invalid public factor numeric value") from exc
                _require(excess.is_finite() and rf.is_finite(),
                         "Nonfinite public factor components")
                _require(day not in result, "Duplicate public market date")
                result[day] = (excess + rf) / Decimal(100)
        _require(found_header and result, "No usable public daily factor table")
        _require(stopped_at is not None, "Public file did not reach the development-tail cutoff")
    return result, vintage, stopped_at


def compare_public_benchmark(public_zip, market_csv, market_receipt, output, *,
                             config, repo_root):
    root = Path(repo_root).resolve(strict=True)
    destination = Path(output).resolve()
    _require(any(destination.is_relative_to(root / d) and destination != root / d
                 for d in ("data", "outputs")), "Comparison output must be a new private directory")
    _require(not destination.exists(), "Cannot overwrite any comparison result")
    public_zip = Path(public_zip).resolve(strict=True)
    market_csv = Path(market_csv).resolve(strict=True)
    market_receipt = Path(market_receipt).resolve(strict=True)
    for path in (public_zip, market_csv, market_receipt):
        _require(path.is_file() and not path.is_symlink(), "Input source must be an ordinary file")
        _require(not destination.is_relative_to(path.parent), "Output may not nest in input directory")
    _require(market_csv.stat().st_size < 2_000_000
             and market_receipt.stat().st_size < 200_000, "CRSP market source unexpectedly large")
    public_bytes = public_zip.read_bytes()
    market_bytes = market_csv.read_bytes()
    receipt_bytes = market_receipt.read_bytes()
    receipt = json.loads(receipt_bytes)
    source = receipt.get("source", {})
    _require(receipt.get("status") == "RAW_MANUAL_WRDS_MARKET_INVENTORY_NOT_SOURCE_APPROVED"
             and receipt.get("model_ready") is False
             and receipt.get("source_approvals") == 0
             and receipt.get("protocol_sha256") == canonical_hash(config),
             "CRSP inventory is not the preserved, unapproved development source")
    _require(source.get("sha256") == _sha(market_bytes)
             and source.get("bytes") == len(market_bytes)
             and source.get("observed_header") == ["dlycaldt", "vwretd"],
             "Raw CRSP source disagrees with preserved inventory receipt")
    _require(config["holdout_start"] == 2022 and config["development_end"] == 2021,
             "Unexpected frozen calendar boundary")
    crsp = _crsp_rows(market_bytes)
    public, vintage, stopped_at = _fama_french_rows(public_bytes)
    overlap = sorted(set(crsp) & set(public))
    missing = set(crsp) - set(public)
    additional = set(public) - set(crsp)
    _require(overlap, "No common development sessions for comparison")
    diffs = [abs(public[day] - crsp[day]) for day in overlap]
    summary = {
        "schema_version": 1, "status": STATUS, "data_kind": "PUBLIC_AND_UNAPPROVED_MARKET_SOURCE_DIAGNOSTIC",
        "public_source": PUBLIC_URL,
        "public_zip_sha256": _sha(public_bytes),
        "public_zip_bytes": len(public_bytes),
        "public_file_reported_upstream_crsp_yyyymm": vintage,
        "source_vintage_caveat": "Published public factors can include retrospective revisions; not a point-in-time benchmark",
        "private_crsp_source_sha256": _sha(market_bytes),
        "private_inventory_receipt_sha256": _sha(receipt_bytes),
        "development_return_cutoff": LATEST_BOUNDARY,
        "stopped_before_later_public_factor_values": stopped_at,
        "crsp_sessions": len(crsp),
        "public_sessions_through_cutoff": len(public),
        "overlap_sessions": len(overlap),
        "crsp_sessions_missing_in_public": len(missing),
        "public_sessions_not_in_crsp": len(additional),
        "missing_crsp_coverage_by_year": {str(k): v for k, v in
                                          sorted(Counter(d.year for d in missing).items())},
        "independent_index_definition": "Fama-French US Mkt-RF plus RF; factor units are percentage points, divided by 100",
        "identical_vendor_series_claimed": False,
        "same_historical_vintage_claimed": False,
        "daily_exact_equality_days": sum(x == 0 for x in diffs),
        "median_abs_daily_difference": str(median(diffs)),
        "max_abs_daily_difference": str(max(diffs)),
        "daily_differences_gt_1bp": sum(x > Decimal("0.0001") for x in diffs),
        "daily_differences_gt_5bp": sum(x > Decimal("0.0005") for x in diffs),
        "benchmark_selected": False,
        "comparison_only": True, "model_ready": False, "final_period_opened": False,
        "approved_historical_identity": False,
        "research_interpretation": "Independent coverage and definition diagnostic only; does not resolve primary source or historical data availability",
    }
    for path, blob in ((public_zip, public_bytes), (market_csv, market_bytes),
                       (market_receipt, receipt_bytes)):
        _require(_sha(path.read_bytes()) == _sha(blob), "Source file changed during comparison")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".public-benchmark-", dir=destination.parent) as scratch:
        staged = Path(scratch) / "result"
        staged.mkdir(mode=0o700)
        (staged / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        os.chmod(staged / "summary.json", 0o400)
        receipt_out = {
            "schema_version": 1, "status": STATUS,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "data_kind": summary["data_kind"],
            "summary_sha256": _sha((staged / "summary.json").read_bytes()),
            "source_hashes_sha256": {
                "public_zip": _sha(public_bytes),
                "private_crsp_csv": _sha(market_bytes),
                "private_crsp_receipt": _sha(receipt_bytes),
            },
            "source_approvals": 0, "benchmark_selected": False,
            "final_period_opened": False, "model_ready": False,
        }
        (staged / "receipt.json").write_text(json.dumps(receipt_out, indent=2) + "\n")
        os.chmod(staged / "receipt.json", 0o400)
        staged.rename(destination)
    return summary
