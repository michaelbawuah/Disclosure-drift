"""Synthetic comparison test cases. No actual Fama-French or CRSP data are in the tests."""

import csv
import hashlib
import io
import json
import zipfile

import pytest

from disclosure_research.protocol import canonical_hash, load_protocol
from disclosure_research.public_benchmark_check import (
    STATUS, _fama_french_rows, compare_public_benchmark,
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _zip_bytes(text, *, filename="F-F_Research_Data_Factors_daily.csv"):
    buff = io.BytesIO()
    with zipfile.ZipFile(buff, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename, text)
    return buff.getvalue()


@pytest.fixture
def setup(tmp_path):
    repo = tmp_path / "repo"
    private = repo / "data" / "wrds"
    public = repo / "outputs" / "download"
    private.mkdir(parents=True)
    public.mkdir(parents=True)
    config = load_protocol()
    raw_rows = [
        ("2016-01-04", "0.0010"),
        ("2016-01-05", "-0.0020"),
        ("2016-01-06", "0.0030"),
        ("2016-01-07", "0.0040"),
    ]
    csv_stream = io.StringIO(newline="")
    writer = csv.writer(csv_stream)
    writer.writerow(["dlycaldt", "vwretd"])
    writer.writerows(raw_rows)
    (private / "source.csv").write_text(csv_stream.getvalue())
    original = (private / "source.csv").read_bytes()
    receipt = {
        "status": "RAW_MANUAL_WRDS_MARKET_INVENTORY_NOT_SOURCE_APPROVED",
        "model_ready": False, "source_approvals": 0,
        "protocol_sha256": canonical_hash(config),
        "source": {
            "sha256": _sha(original),
            "bytes": len(original),
            "observed_header": ["dlycaldt", "vwretd"],
        },
    }
    (private / "receipt.json").write_text(json.dumps(receipt))
    factors = (
        "This file was created by using the 202608 CRSP database.\n"
        "Fama French independent source fixture only\n"
        ",Mkt-RF,SMB,HML,RF\n"
        "20160104,0.10,0.0,0.0,0.0\n"
        "20160105,-0.20,0.0,0.0,0.0\n"
        "20160106,0.31,0.0,0.0,0.0\n"
        "20160107,0.39,0.0,0.0,0.01\n"
        "20220203,SHOULD_NOT_READ_NUMERIC_VALUES,NA,NA,NA\n"
        "Copyright 2026 Eugene F. Fama and Kenneth R. French\n"
    )
    (public / "factors.zip").write_bytes(_zip_bytes(factors))
    return {
        "root": repo,
        "public": public / "factors.zip",
        "private": private / "source.csv",
        "receipt": private / "receipt.json",
        "out": repo / "outputs" / "comparison",
        "config": config,
        "factors": factors,
    }


def run(x):
    return compare_public_benchmark(x["public"], x["private"], x["receipt"],
                                    x["out"], config=x["config"], repo_root=x["root"])


def test_realistic_comparison_persists_hashes_and_keeps_holdout_closed(setup):
    result = run(setup)
    assert result["status"] == STATUS
    assert result["overlap_sessions"] == result["crsp_sessions"] == 4
    assert result["crsp_sessions_missing_in_public"] == 0
    assert result["daily_exact_equality_days"] == 3
    assert result["median_abs_daily_difference"] == "0.0000"
    assert result["max_abs_daily_difference"] == "0.0001"
    assert result["stopped_before_later_public_factor_values"] == "2022-02-03"
    assert result["public_file_reported_upstream_crsp_yyyymm"] == "202608"
    assert result["benchmark_selected"] is False
    assert result["final_period_opened"] is False
    assert result["model_ready"] is False
    out = setup["out"]
    receipt = json.loads((out / "receipt.json").read_text())
    assert receipt["source_approvals"] == 0
    assert _sha((out / "summary.json").read_bytes()) == receipt["summary_sha256"]
    assert out.stat().st_mode & 0o077 == 0
    assert (out / "summary.json").stat().st_mode & 0o222 == 0


def test_does_not_overwrite_existing_source_audit(setup):
    run(setup)
    with pytest.raises(ValueError, match="overwrite"):
        run(setup)


def test_source_hash_mismatch_refused(setup):
    setup["private"].write_text(setup["private"].read_text() + "2016-01-08,0.01\n")
    with pytest.raises(ValueError, match="disagrees"):
        run(setup)


def test_forged_source_status_refused(setup):
    receipt = json.loads(setup["receipt"].read_text())
    receipt["source_approvals"] = 1
    setup["receipt"].write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="preserved"):
        run(setup)


def test_wrong_date_or_duplicate_original_series_refused(setup):
    with setup["private"].open("a") as f:
        f.write("2016-01-04,0.02000\n")
    receipt = json.loads(setup["receipt"].read_text())
    receipt["source"]["sha256"] = _sha(setup["private"].read_bytes())
    receipt["source"]["bytes"] = setup["private"].stat().st_size
    setup["receipt"].write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="Duplicate"):
        run(setup)


def test_public_header_poison_is_rejected(setup):
    setup["public"].write_bytes(_zip_bytes(setup["factors"].replace(
        ",Mkt-RF,SMB,HML,RF", ",Mkt-RF,NEW,HML,RF"
    )))
    with pytest.raises(ValueError, match="factor"):
        run(setup)


def test_malformed_public_factor_refused(setup):
    setup["public"].write_bytes(_zip_bytes(setup["factors"].replace(
        "20160106,0.31", "20160106,not-a-number"
    )))
    with pytest.raises(ValueError, match="numeric"):
        run(setup)


def test_public_duplicate_factor_date_refused(setup):
    setup["public"].write_bytes(_zip_bytes(setup["factors"].replace(
        "20160107,0.39", "20160106,0.39"
    )))
    with pytest.raises(ValueError, match="not strictly increasing"):
        run(setup)


def test_public_zip_without_expected_exact_member_refused(setup):
    setup["public"].write_bytes(_zip_bytes(setup["factors"], filename="../secret.csv"))
    with pytest.raises(ValueError, match="ZIP shape"):
        run(setup)


def test_public_future_values_not_decoded_as_numbers(setup):
    factor, vintage, boundary = _fama_french_rows(setup["public"].read_bytes())
    assert len(factor) == 4
    assert vintage == "202608"
    assert boundary == "2022-02-03"


def test_output_must_be_private_to_project(setup):
    setup["out"] = setup["root"].parent / "outside"
    with pytest.raises(ValueError, match="Comparison output"):
        run(setup)


def test_rejects_empty_crsp_export_even_if_receipt_rehashes(setup):
    setup["private"].write_text("dlycaldt,vwretd\n")
    receipt = json.loads(setup["receipt"].read_text())
    receipt["source"]["sha256"] = _sha(setup["private"].read_bytes())
    receipt["source"]["bytes"] = setup["private"].stat().st_size
    setup["receipt"].write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="no sessions"):
        run(setup)
