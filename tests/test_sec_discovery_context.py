"""Synthetic source bindings for the public-only discovery inspector."""

import csv
import hashlib
import json
import runpy
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from disclosure_research.manual_wrds_identity_candidates import STATUS
from disclosure_research.protocol import canonical_hash, load_protocol

SCRIPT = runpy.run_path(str(Path(__file__).parents[1] / "scripts/inspect_sec_discovery_context.py"))
inspect = SCRIPT["inspect"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path, mutate=None, day="2020-02-20"):
    folder = tmp_path / "identity"
    folder.mkdir()
    rows = []
    for i in (1, 2):
        rows.append({"cik": f"{i:010d}", "name": f"Invented filer {i}",
                     "accessionNumber": f"{i:010d}-20-000001", "acceptance_date": day,
                     "source_url": f"https://www.sec.gov/Archives/synthetic/{i}.htm",
                     "header_url": f"https://www.sec.gov/Archives/synthetic/{i}.sgml",
                     "download_sha256": "a" * 64, "header_sha256": "b" * 64})
    manifest = folder / "manifest.csv"
    with manifest.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=SCRIPT["PUBLIC_FIELDS"])
        writer.writeheader()
        writer.writerows(rows)
    ledger = [{"sec_manifest_sha256": digest(manifest), "sec_manifest_csv_record": i + 2,
               "accession": row["accessionNumber"], "sec_filer_cik_raw": row["cik"],
               "recorded_acceptance_date": row["acceptance_date"],
               "coverage_status": SCRIPT["MATCHED"] if i == 0 else SCRIPT["UNMATCHED"],
               "unused_vendor_field": "SYNTHETIC_VENDOR_SENTINEL"}
              for i, row in enumerate(rows)]
    if mutate:
        mutate(ledger)
    part = folder / "coverage.parquet"
    pq.write_table(pa.Table.from_pylist(ledger), part)
    receipt = {"status": STATUS, "model_ready": False, "source_approvals": 0,
               "protocol_sha256": canonical_hash(load_protocol()), "original_sec_bytes_reread": False,
               "prior_arithmetic_review_modified": False, "final_period_opened": False,
               "sec_manifest": {"provided": True, "sha256": digest(manifest), "rows": 2,
                                "snapshot": {"file": manifest.name, "sha256": digest(manifest),
                                             "bytes": manifest.stat().st_size}},
               "tables": {"sec_manifest_coverage": {"rows": 2, "parts": [
                   {"file": part.name, "sha256": digest(part), "bytes": part.stat().st_size, "rows": 2}]}},
               "sec_manifest_coverage_counts": {SCRIPT["MATCHED"]: 1, SCRIPT["UNMATCHED"]: 1}}
    (folder / "receipt.json").write_text(json.dumps(receipt))
    return folder, digest(folder / "receipt.json")


def test_only_public_columns_are_read_and_unmatched_manifest_facts_exported(tmp_path, monkeypatch):
    folder, sha = fixture(tmp_path)
    original = pq.read_table
    calls = []

    def projected(*args, **kwargs):
        calls.append(kwargs["columns"])
        return original(*args, **kwargs)

    monkeypatch.setattr(pq, "read_table", projected)
    result = inspect(folder, sha, tmp_path / "public.json")
    assert calls == [SCRIPT["COLUMNS"]]
    assert result["verified_manifest_records"] == 2
    assert result["unmatched_original_filer_counts"] == {"0000000002": 1}
    assert len(result["public_unmatched_filings"]) == 1
    assert "SYNTHETIC_VENDOR_SENTINEL" not in json.dumps(result)
    assert result["source_files_rehashed"] == 3
    assert result["model_ready"] is False and result["human_reviews_added"] == 0
    with pytest.raises(ValueError, match="Preserve prior"):
        inspect(folder, sha, tmp_path / "public.json")


@pytest.mark.parametrize("target", ["receipt.json", "manifest.csv", "coverage.parquet"])
def test_input_tampering_is_rejected_before_a_report_is_written(tmp_path, target):
    folder, sha = fixture(tmp_path)
    with (folder / target).open("ab") as stream:
        stream.write(b"changed")
    output = tmp_path / "public.json"
    with pytest.raises(ValueError, match="pinned hash or size"):
        inspect(folder, sha, output)
    assert not output.exists()


@pytest.mark.parametrize("field,value", [
    ("sec_manifest_csv_record", 2), ("accession", "wrong"), ("sec_filer_cik_raw", "0000000001"),
    ("recorded_acceptance_date", "2020-02-21"), ("sec_manifest_sha256", "c" * 64),
    ("coverage_status", "APPROVED"),
])
def test_hash_bound_ledger_still_must_match_every_original_manifest_key(tmp_path, field, value):
    folder, sha = fixture(tmp_path, lambda rows: rows[1].update({field: value}))
    with pytest.raises(ValueError, match="manifest ordinal|public filing metadata"):
        inspect(folder, sha, tmp_path / "public.json")


def test_receipt_pin_is_required(tmp_path):
    folder, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match="explicit identity receipt"):
        inspect(folder, None, tmp_path / "public.json")


@pytest.mark.parametrize("day", ["2025-02-20", "2009-02-20", "2020-02-30", "20200220"])
def test_invalid_or_outside_development_dates_fail_before_ledger_is_read(tmp_path, monkeypatch, day):
    folder, sha = fixture(tmp_path, day=day)

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid dates must be rejected before reading the coverage table")

    monkeypatch.setattr(pq, "read_table", forbidden)
    with pytest.raises(ValueError):
        inspect(folder, sha, tmp_path / "public.json")
    assert not (tmp_path / "public.json").exists()
