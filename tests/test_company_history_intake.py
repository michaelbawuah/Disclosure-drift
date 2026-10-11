"""Synthetic only: no WRDS data, historical approvals, or final-evaluation records."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from disclosure_research.company_history_intake import build_company_history_intake
from disclosure_research.protocol import canonical_hash

COLUMNS = ("GVKEY", "HCIK", "HCHGDT", "HCHGENDDT", "LPERMNO")
CONFIG = {"test": "synthetic-only"}


def bundle(tmp_path, records=None, **changes):
    repo = tmp_path / "repo"
    (repo / "outputs").mkdir(parents=True)
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    path = incoming / "companyhistory.csv"
    if records is None:
        records = [
            ("000123", "0000001111", "20100101", "20101231", "1234"),
            ("000123", "2222", "20100601", "20110101", "1234"),
            ("000456", "3333", "20110501", "99999999", "0"),
            ("000456", "4444", "20230701", "99999999", "5555"),
            ("000456", "", "20110101", "20110102", "6666"),
            ("000777", "8888", "20110302", "20110301", "7777"),
            ("000123", "0000001111", "20100101", "20101231", "1234"),
            ("000888", "9999", "20111301", "99999999", "8888"),
            ("000999", "1010", "20000101", "20080930", "9999"),
        ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(COLUMNS)
        wr.writerows(records)
    meta = {
        "schema_version": 1, "product": "crsp_m_ccm", "table": "companyhistory",
        "data_kind": "SYNTHETIC_ENGINEERING_FIXTURE",
        "protocol_sha256": canonical_hash(CONFIG),
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "columns": {"gvkey": "GVKEY", "hcik": "HCIK", "valid_from": "HCHGDT",
                    "valid_to": "HCHGENDDT", "permno": "LPERMNO"},
        "date_format": "YYYYMMDD", "open_start_values": ["00000000"],
        "open_end_values": ["99999999"], "claimed_known_at": None,
        "source_approved": False, "source_release": None, "exported_at": None,
    }
    meta.update(changes)
    manifest = incoming / "manifest.json"
    manifest.write_text(json.dumps(meta))
    return repo, path, manifest, repo / "outputs" / "first"


def run(paths):
    repo, source, manifest, out = paths
    return build_company_history_intake(source, manifest, out, config=CONFIG, repo_root=repo)


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_stages_candidates_with_pending_availability(tmp_path):
    paths = bundle(tmp_path)
    summary = run(paths)
    out = paths[-1]
    assert summary["raw_rows"] == 9
    assert summary["effective_interval_candidates"] == 4
    assert summary["counts_by_issue"]["NO_LINKED_PERMNO"] == 1
    assert summary["counts_by_issue"]["OUTSIDE_DEVELOPMENT_SCOPE"] == 1
    assert summary["counts_by_issue"]["BEFORE_DEVELOPMENT_SCOPE"] == 1
    assert summary["counts_by_issue"]["INVALID_HCIK"] == 1
    assert summary["counts_by_issue"]["REVERSED_EFFECTIVE_BOUNDS"] == 1
    assert summary["counts_by_issue"]["UNRESOLVED_EFFECTIVE_BOUNDS"] == 1
    assert summary["counts_by_issue"]["duplicate_interval_projection_excess"] == 1
    assert summary["counts_by_issue"]["DUPLICATE_INTERVAL_PROJECTION"] == 1
    assert summary["overlapping_different_cik_pair_counts"] == {
        "GVKEY_OVERLAP_DIFFERENT_CIK": 2, "PERMNO_OVERLAP_DIFFERENT_CIK": 2,
    }
    rows = read_csv(out / "candidate_intervals.csv")
    assert len(rows) == 4
    assert rows[0]["hcik_10"] == "0000001111"
    assert rows[1]["hcik_10"] == "0000002222"
    assert rows[2]["open_end"] == "True"
    assert rows[2]["valid_to"] == ""
    assert all(row["known_at"] == "" and row["mapping_approved"] == "false" for row in rows)
    assert "2023" not in (out / "candidate_intervals.csv").read_text()
    assert any(row["source_record"] == "7" and row["issue"] == "DUPLICATE_INTERVAL_PROJECTION"
               for row in read_csv(out / "review_issues.csv"))
    assert len(read_csv(out / "overlap_examples.csv")) == 4
    assert (out / "original.csv").read_bytes() == paths[1].read_bytes()
    receipt = json.loads((out / "receipt.json").read_text())
    assert receipt["data_kind"] == "SYNTHETIC_ENGINEERING_FIXTURE"
    assert not receipt["historical_known_at_established"]
    assert not receipt["final_period_opened"]
    assert not receipt["model_ready"]
    assert receipt["source_approvals"] == receipt["identity_approvals"] == 0
    for name, record in receipt["files"].items():
        raw = (out / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == record["sha256"]
        assert len(raw) == record["bytes"]


@pytest.mark.parametrize("change", [
    {"source_sha256": "0" * 64},
    {"protocol_sha256": "0" * 64},
    {"source_approved": True},
    {"claimed_known_at": "2020-01-01T00:00:00+00:00"},
    {"known_at": "2020-01-01T00:00:00+00:00"},
    {"available_at": "2020-01-01T00:00:00+00:00"},
    {"columns": {"gvkey": "HCIK", "hcik": "HCIK", "valid_from": "HCHGDT",
                 "valid_to": "HCHGENDDT", "permno": "LPERMNO"}},
    {"columns": {"gvkey": "GVKEY", "hcik": "HCIK", "valid_from": "HCHGDT",
                 "valid_to": "HCHGENDDT"}},
    {"date_format": "auto"},
    {"table": "ccmxpf_lnkhist"},
    {"data_kind": "UNKNOWN"},
    {"data_kind": "AUTHORIZED_VENDOR_EXPORTS"},
    {"open_end_values": ["99999999", "99999999"]},
])
def test_refuses_unverified_or_ambiguous_metadata(tmp_path, change):
    with pytest.raises(ValueError):
        run(bundle(tmp_path, **change))


def test_rejects_duplicate_source_headers_and_malformed_rows(tmp_path):
    paths = bundle(tmp_path)
    paths[1].write_text("GVKEY,HCIK,HCHGDT,HCHGENDDT,GVKEY\n1,123,20100101,20101231,22\n")
    payload = json.loads(paths[2].read_text())
    payload["columns"]["permno"] = None
    payload["source_sha256"] = hashlib.sha256(paths[1].read_bytes()).hexdigest()
    paths[2].write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="duplicate"):
        run(paths)
    assert not paths[-1].exists()


def test_rejects_csv_field_count_mismatch(tmp_path):
    paths = bundle(tmp_path)
    with paths[1].open("a") as fh:
        fh.write("1,2,3\n")
    payload = json.loads(paths[2].read_text())
    payload["source_sha256"] = hashlib.sha256(paths[1].read_bytes()).hexdigest()
    paths[2].write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="column count"):
        run(paths)
    assert not paths[-1].exists()


def test_refuses_existing_output_and_source_hash_mutation(tmp_path):
    paths = bundle(tmp_path)
    run(paths)
    with pytest.raises(ValueError):
        run(paths)
    paths[1].write_text("mutated")
    with pytest.raises(ValueError, match="Unmatched raw source"):
        build_company_history_intake(paths[1], paths[2], paths[0] / "outputs" / "second",
                                     config=CONFIG, repo_root=paths[0])


def test_open_start_and_missing_permno_mapping_remain_unapproved(tmp_path):
    paths = bundle(tmp_path, records=[
        ("000101", "9", "00000000", "20181231", ""),
        ("000102", "0000000001", "20180101", "20181231", ""),
    ])
    manifest = json.loads(paths[2].read_text())
    manifest["columns"]["permno"] = None
    paths[2].write_text(json.dumps(manifest))
    result = run(paths)
    rows = read_csv(paths[-1] / "candidate_intervals.csv")
    assert result["effective_interval_candidates"] == 2
    assert result["counts_by_issue"]["NO_LINKED_PERMNO"] == 2
    assert rows[0]["open_start"] == "True"
    assert rows[0]["valid_from"] == ""
    assert rows[0]["hcik_10"] == "0000000009"
    assert rows[1]["hcik_10"] == "0000000001"


def test_yyyy_mm_dd_and_interval_boundary_is_inclusive(tmp_path):
    paths = bundle(tmp_path, records=[
        ("1", "1", "2010-01-01", "2010-07-01", "100"),
        ("1", "2", "2010-07-01", "2010-12-31", "100"),
        ("1", "3", "2010-07-02", "2010-12-31", "200"),
    ], date_format="YYYY-MM-DD", open_start_values=[], open_end_values=[])
    result = run(paths)
    assert result["effective_interval_candidates"] == 3
    assert result["overlapping_different_cik_pair_counts"] == {
        "GVKEY_OVERLAP_DIFFERENT_CIK": 2, "PERMNO_OVERLAP_DIFFERENT_CIK": 1,
    }


def test_unsupported_identifiers_remain_issues_not_implicit_normalizations(tmp_path):
    paths = bundle(tmp_path, records=[
        ("=HYPERLINK('x')", "123", "20100101", "20101231", "1"),
        ("1", "12345678901", "20100101", "20101231", "1"),
        ("2", "0", "20100101", "20101231", "1"),
    ])
    result = run(paths)
    assert result["effective_interval_candidates"] == 0
    assert result["counts_by_issue"]["INVALID_HCIK"] == 2
    assert result["counts_by_issue"]["INVALID_GVKEY"] == 1


def test_empty_csv_is_not_a_successful_export(tmp_path):
    paths = bundle(tmp_path, records=[])
    with pytest.raises(ValueError, match="no data"):
        run(paths)
    assert not paths[-1].exists()


def test_bad_permno_and_cik_are_flagged_without_number_conversion_errors(tmp_path):
    paths = bundle(tmp_path, records=[
        ("100", "6", "20100101", "20101231", "9" * 5000),
        ("101", "8" * 5000, "20100101", "20101231", "100"),
    ])
    summary = run(paths)
    assert summary["effective_interval_candidates"] == 1
    assert summary["counts_by_issue"]["INVALID_HCIK"] == 1
    assert summary["counts_by_issue"]["NO_LINKED_PERMNO"] == 1


def test_source_snapshot_is_readonly_private_and_original_is_not_rewritten(tmp_path):
    paths = bundle(tmp_path)
    source_before = paths[1].read_bytes()
    run(paths)
    assert paths[1].read_bytes() == source_before
    assert paths[-1].stat().st_mode & 0o077 == 0
    for name in ("original.csv", "candidate_intervals.csv", "review_issues.csv",
                 "input_manifest.json", "receipt.json", "public_summary.json"):
        assert (paths[-1] / name).stat().st_mode & 0o222 == 0


def test_normalized_key_collision_is_not_labeled_exact_raw_duplicate(tmp_path):
    paths = bundle(tmp_path, records=[
        ("000001", "1", "20100101", "20101231", "00012"),
        ("000001", "0000000001", "20100101", "20101231", "12"),
    ])
    summary = run(paths)
    assert summary["effective_interval_candidates"] == 2
    assert summary["counts_by_issue"]["duplicate_interval_projection_excess"] == 1
    assert summary["counts_by_issue"]["DUPLICATE_INTERVAL_PROJECTION"] == 1
    assert summary["overlapping_different_cik_pair_counts"] == {}
    rows = read_csv(paths[-1] / "candidate_intervals.csv")
    assert rows[0]["hcik_raw"] != rows[1]["hcik_raw"]
    assert rows[0]["permno_raw"] != rows[1]["permno_raw"]
