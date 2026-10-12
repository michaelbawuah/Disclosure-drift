"""Complete-source and event-date checks using invented metadata only."""

import hashlib
import json
import re
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from disclosure_research import dated_names_evidence as dated
from disclosure_research import historical_foundation as foundation

from test_historical_foundation import make_inputs  # noqa: F401 - shared synthetic fixture
from test_manual_wrds_identity_candidates import _ccm, _name


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(path, data):
    path.chmod(0o600)
    path.write_bytes(data)


def _json_write(path, value):
    _write(path, json.dumps(value).encode())


@pytest.fixture
def prepared(request, tmp_path):
    def prepare(**kwargs):
        kwargs.setdefault("names", [_name(secinfostartdt="2020-01-01")])
        source_args = request.getfixturevalue("make_inputs")(**kwargs)
        foundation.build_historical_foundation_review(**source_args)
        names = tmp_path / "data/names-inventory"
        return {"foundation_directory": source_args["output"], "names_inventory": names,
                "foundation_receipt_sha256": _sha(source_args["output"] / "receipt.json"),
                "names_receipt_sha256": _sha(names / "receipt.json"),
                "sec_evidence_path": source_args["sec_evidence_path"], "sec_manifest_path": source_args["sec_manifest_path"],
                "output": tmp_path / "data/dated", "config": source_args["config"], "repo_root": tmp_path}
    return prepare


def _rows(args, receipt, table):
    return [row for spec in receipt["tables"][table]["parts"]
            for row in pq.read_table(args["output"] / spec["file"]).to_pylist()]


def _source(args):
    receipt = json.loads((args["names_inventory"] / "receipt.json").read_text())
    return args["names_inventory"] / receipt["source"]["preserved_file"]


def _rebind_names_for_preflight(args):
    """Bind a changed synthetic inventory so the complete date pass must inspect it."""
    names_path = args["names_inventory"] / "receipt.json"
    names = json.loads(names_path.read_text())
    names["source"].update(sha256=_sha(_source(args)), bytes=_source(args).stat().st_size)
    _json_write(names_path, names)
    args["names_receipt_sha256"] = _sha(names_path)
    root = args["foundation_directory"]
    identity_path = root / "input_receipts/identity.json"
    identity = json.loads(identity_path.read_text())
    spec = next(spec for spec in identity["input_receipts"] if spec["file"] == "input_receipts/names_inventory.json")
    spec.update(sha256=_sha(names_path), bytes=names_path.stat().st_size)
    _json_write(identity_path, identity)
    receipt_path = root / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["inputs"]["identity_receipt_sha256"] = _sha(identity_path)
    spec = next(spec for spec in receipt["input_receipts"] if spec["file"] == "input_receipts/identity.json")
    spec.update(sha256=_sha(identity_path), bytes=identity_path.stat().st_size)
    _json_write(receipt_path, receipt)
    args["foundation_receipt_sha256"] = _sha(receipt_path)


def test_later_descriptor_resolves_snapshot_gap_and_preserves_all_originals(prepared):
    args = prepared(names=[_name(secinfostartdt="2020-01-01", secinfoenddt="2021-01-31"),
                           _name(secinfostartdt="2021-02-01", ticker="NEW\nTICKER", cusip="87654321",
                                 shareclass="B", siccd="0456", naics="123456")])
    raw_source = _source(args).read_bytes()
    result = dated.build_dated_names_evidence(**args)
    assert _source(args).read_bytes() == raw_source
    assert result["counts"]["discoveries"] == 1
    assert result["counts"]["requested_points"] == 82
    assert result["counts"]["original_snapshot_acceptance_gaps"] == 1
    assert result["counts"]["original_snapshot_gaps_with_unique_full_history_acceptance"] == 1
    assert result["counts"]["discoveries_with_complete_unambiguous_coverage"] == 1
    assert result["counts"]["discoveries_with_descriptor_text_changes"] == 1
    assert result["point_status_counts"] == {"UNIQUE_RECORD": 82}
    assert {role: sum(counts.values()) for role, counts in result["point_status_counts_by_role"].items()} == {
        "acceptance": 1, "reference": 1, "control": 60, "label": 20}
    original = json.loads((args["foundation_directory"] / "receipt.json").read_text())
    for before, after in (("filing_candidate_corroboration", "original_discoveries"),
                          ("filing_coverage", "original_filing_coverage")):
        expected = [row for spec in original["tables"][before]["parts"]
                    for row in pq.read_table(args["foundation_directory"] / spec["file"]).to_pylist()]
        assert _rows(args, result, after) == expected
    assert _rows(args, result, "original_discoveries")[0]["names_secinfo_covers_acceptance"] is False
    names = _rows(args, result, "names_records")
    assert [row["source_csv_record"] for row in names] == [2, 3]
    assert names[1]["ticker"] == "NEW\nTICKER" and names[1]["siccd"] == "0456"
    assert names[1]["shareclass"] == "B" and names[1]["cusip"] == "87654321"
    for name in result["tables"]:
        for row in _rows(args, result, name):
            assert row["known_at"] is None and row["available_at"] is None and row["identity_approved"] is False
    for path in args["output"].rglob("*"):
        assert path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o400)
    assert json.loads((args["output"] / "aggregate.json").read_text()) == dated.aggregate_summary(result)
    # A short synthetic identifier can coincide with four hex characters
    # inside a legitimate SHA-256 provenance digest. Redact complete digests
    # before testing that the public text does not include raw record values.
    public = re.sub(r"\b[0-9a-f]{64}\b", "<SHA256>", json.dumps(dated.aggregate_summary(result)))
    assert "NEW" not in public and "87654321" not in public and "0456" not in public
    with pytest.raises(ValueError, match="exists"):
        dated.build_dated_names_evidence(**args)


def test_missing_interval_is_not_extended_using_security_lifetime(prepared):
    args = prepared(names=[_name(secinfostartdt="2020-01-01", secinfoenddt="2021-01-31"),
                           _name(secinfostartdt="2021-02-20")])
    result = dated.build_dated_names_evidence(**args)
    summary = _rows(args, result, "discovery_summary")[0]
    assert summary["acceptance_match_status"] == "MISSING"
    assert summary["reference_match_status"] == "MISSING"
    assert summary["missing_points"] > 0 and summary["full_window_status"].startswith("INCOMPLETE")
    assert result["counts"]["original_snapshot_gaps_with_unique_full_history_acceptance"] == 0


@pytest.mark.parametrize("change,expected", [({}, "AMBIGUOUS_EXACT_DUPLICATES"), ({"siccd": "9999"}, "AMBIGUOUS_DISTINCT_RECORDS")])
def test_overlaps_preserve_every_source_occurrence_without_choosing_first(prepared, change, expected):
    later = _name(secinfostartdt="2021-02-01")
    args = prepared(names=[_name(secinfostartdt="2020-01-01", secinfoenddt="2021-01-31"), later, {**later, **change}])
    result = dated.build_dated_names_evidence(**args)
    acceptance = next(point for point in _rows(args, result, "date_evidence") if point["role"] == "acceptance")
    assert acceptance["match_status"] == expected
    assert json.loads(acceptance["source_records_json"]) == [3, 4]
    assert acceptance["matching_records"] == 2
    assert result["counts"]["discoveries_with_ambiguous_points"] == 1
    assert result["counts"]["discoveries_with_complete_unambiguous_coverage"] == 0


def test_identifier_aliases_are_visible_and_not_accepted_as_exact_raw_coverage(prepared):
    args = prepared(names=[_name(secinfostartdt="2020-01-01", secinfoenddt="2021-01-31"),
                           _name("0010", secinfostartdt="2021-02-01")])
    result = dated.build_dated_names_evidence(**args)
    acceptance = next(point for point in _rows(args, result, "date_evidence") if point["role"] == "acceptance")
    assert acceptance["match_status"] == "UNIQUE_RECORD"
    assert acceptance["identifier_comparison"] == "ALIAS_RAW_ONLY"
    assert result["counts"]["discoveries_with_identifier_variants"] == 1
    assert result["counts"]["discoveries_with_complete_unambiguous_coverage"] == 0
    assert result["counts"]["original_snapshot_gaps_with_unique_full_history_acceptance"] == 0


def test_permco_change_is_named_literal_names_comparison(prepared):
    args = prepared(names=[_name(secinfostartdt="2020-01-01", secinfoenddt="2021-01-31"),
                           _name(secinfostartdt="2021-02-01", permco="901")])
    result = dated.build_dated_names_evidence(**args)
    assert result["counts"]["discoveries_with_permco_text_changes"] == 1
    assert result["counts"]["discoveries_with_complete_unambiguous_coverage"] == 1
    assert "not a CCM agreement" in result["policies"]["permco"]


def test_no_discoveries_still_retains_original_unmatched_filing(prepared):
    args = prepared(ccm=[_ccm(cik="999")])
    result = dated.build_dated_names_evidence(**args)
    assert result["counts"]["discoveries"] == result["counts"]["requested_points"] == 0
    assert result["counts"]["filings"] == result["counts"]["filings_without_discovery"] == 1
    assert len(_rows(args, result, "original_filing_coverage")) == 1
    assert result["tables"]["date_evidence"]["parts"][0]["rows"] == 0


@pytest.mark.parametrize("field", ["foundation_receipt_sha256", "names_receipt_sha256"])
def test_explicit_receipt_pins_are_required(prepared, field):
    args = prepared()
    args[field] = "0" * 64
    with pytest.raises(ValueError, match="pin|pin differs"):
        dated.build_dated_names_evidence(**args)
    assert not args["output"].exists()


def test_stale_foundation_part_hash_fails_before_names_lookup(prepared, monkeypatch):
    args = prepared()
    receipt = json.loads((args["foundation_directory"] / "receipt.json").read_text())
    spec = receipt["tables"]["filing_candidate_corroboration"]["parts"][0]
    path = args["foundation_directory"] / spec["file"]
    _write(path, path.read_bytes() + b"changed")
    monkeypatch.setattr(dated.listing, "_load_source", lambda *a, **k: pytest.fail("Names opened before part hash rejection"))
    with pytest.raises(ValueError, match="byte binding"):
        dated.build_dated_names_evidence(**args)


def test_source_mutation_during_lookup_prevents_output_publication(prepared, monkeypatch):
    args = prepared()
    original = dated._observe_point
    changed = False
    def mutate(*a, **k):
        nonlocal changed
        result = original(*a, **k)
        if not changed:
            path = _source(args)
            _write(path, path.read_bytes().replace(b"PRIVATE INVENTED ISSUER", b"ALTERED INVENTED ISSUER"))
            changed = True
        return result
    monkeypatch.setattr(dated, "_observe_point", mutate)
    with pytest.raises(ValueError, match="changed"):
        dated.build_dated_names_evidence(**args)
    assert not args["output"].exists()


@pytest.mark.parametrize("replacement", [b"2024-13-11", b"E", b"2026-11-11"])
def test_complete_source_preflight_rejects_unrelated_bad_date_before_matching(prepared, monkeypatch, replacement):
    args = prepared(names=[_name(secinfostartdt="2020-01-01"),
                           _name("99", secinfostartdt="2024-11-11", secinfoenddt="2025-12-31")])
    source = _source(args)
    _write(source, source.read_bytes().replace(b"2024-11-11", replacement))
    _rebind_names_for_preflight(args)
    monkeypatch.setattr(dated, "_emit", lambda *a, **k: pytest.fail("Matched before whole-source date rejection"))
    with pytest.raises(ValueError):
        dated.build_dated_names_evidence(**args)
    assert not args["output"].exists()


def test_final_period_sec_manifest_rejected_before_parquet_or_names(prepared, monkeypatch):
    args = prepared()
    path = args["sec_manifest_path"]
    path.write_text(path.read_text().replace("2021-02-15", "2022-02-15"))
    receipt_path = args["foundation_directory"] / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["inputs"]["sec_manifest_sha256"] = _sha(path)
    _json_write(receipt_path, receipt)
    args["foundation_receipt_sha256"] = _sha(receipt_path)
    monkeypatch.setattr(dated, "_foundation_tables", lambda *a, **k: pytest.fail("Parquet opened before final-period refusal"))
    with pytest.raises(ValueError, match="development filings only"):
        dated.build_dated_names_evidence(**args)


def test_rebound_changed_original_discovery_is_rejected(prepared):
    args = prepared()
    receipt_path = args["foundation_directory"] / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    spec = receipt["tables"]["filing_candidate_corroboration"]["parts"][0]
    path = args["foundation_directory"] / spec["file"]
    table = pq.read_table(path)
    rows = table.to_pylist()
    rows[0]["names_source_csv_record"] = 999
    path.chmod(0o600)
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), path)
    spec.update(sha256=_sha(path), bytes=path.stat().st_size)
    _json_write(receipt_path, receipt)
    args["foundation_receipt_sha256"] = _sha(receipt_path)
    with pytest.raises(ValueError, match="fingerprint"):
        dated.build_dated_names_evidence(**args)
    assert not args["output"].exists()
