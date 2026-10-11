"""Source-bound ownership reconciliation using invented metadata only."""

import csv
import hashlib
import json
import runpy
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from disclosure_research import historical_foundation as foundation
from disclosure_research import sec_ownership_corrob as ownership
from disclosure_research.universe import year_start_window

import test_historical_foundation as foundation_tests
from test_historical_foundation import make_inputs  # noqa: F401 - shared synthetic source fixture
from test_manual_wrds_identity_candidates import _ccm, _name
from test_manual_wrds_liquidity_candidates import _daily


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(path, raw):
    if path.exists():
        path.chmod(0o600)
    path.write_bytes(raw)


def _json_write(path, value):
    _write(path, json.dumps(value).encode())


def _submission(symbol="FOO", cik="0000000123", day="20-NOV-2019", **changes):
    row = dict.fromkeys(ownership.SEC_FIELDS, "")
    row.update(ACCESSION_NUMBER="0000000999-19-000001", FILING_DATE=day, PERIOD_OF_REPORT="19-NOV-2019",
               DOCUMENT_TYPE="4", ISSUERCIK=cik, ISSUERNAME="PUBLIC INVENTED ISSUER", ISSUERTRADINGSYMBOL=symbol)
    row.update(changes)
    return row


def _public(root, rows):
    source = root / "submission.tsv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ownership.SEC_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    dates = [ownership._filing_date(row["FILING_DATE"]) for row in rows]
    specification = {"sha256": _sha(source), "bytes": source.stat().st_size, "rows": len(rows),
        "delivered_field_order": list(ownership.SEC_FIELDS),
        "accession_duplicates_excess": len(rows) - len({row["ACCESSION_NUMBER"] for row in rows}),
        "document_type_counts": dict(Counter(row["DOCUMENT_TYPE"] for row in rows)),
        "filing_dates": {"min": min(dates), "max": max(dates)}}
    archive = {"url": "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/2019q4_form345.zip",
               "sha256": "a" * 64}
    collection = {"schema_version": 1, "archive_members_read": ["SUBMISSION.tsv"],
        "final_period_sources_read": False, "reportingowner_member_read": False, "transaction_or_holdings_members_read": False,
        "submission": specification, "source_receipts": {"insider_2019q4": archive}}
    collection_path = root / "collection.json"
    _json_write(collection_path, collection)
    ledger = {"schema_version": 1, "status": "PUBLIC_HISTORICAL_IDENTITY_CORROBORATION_NOT_APPROVED_LINKS",
        "collection_receipt": {"sha256": _sha(collection_path)},
        "insider_2019q4_metadata_demo": {"submission": specification},
        "source_receipts": {"insider_2019q4": archive}}
    ledger_path = root / "ledger.json"
    _json_write(ledger_path, ledger)
    return {"sec_submission_path": source, "sec_ledger_path": ledger_path, "sec_ledger_sha256": _sha(ledger_path),
            "sec_collection_receipt_path": collection_path}


@pytest.fixture
def prepared(request, tmp_path, monkeypatch):
    def prepare(*, names=None, ccm=None, securities=("10", "20"), public=None):
        make = request.getfixturevalue("make_inputs")
        config = foundation_tests.load_protocol()
        window = year_start_window(2020, config)
        numerical = foundation_tests._numerical
        with monkeypatch.context() as patch:
            patch.setattr(foundation_tests, "_numerical",
                          lambda root, rows: numerical(root, rows, request=(window["liquidity_start"], window["liquidity_end"])))
            args = make(names=names if names is not None else [
                _name("10", secinfostartdt="2019-01-01", ticker="FOO", tradingsymbol="FOO"),
                _name("20", secinfostartdt="2019-01-01", ticker="BAR")],
                ccm=ccm if ccm is not None else [_ccm("10"), _ccm("20", cik="")],
                daily=[_daily(day, security) for security in securities for day in window["sessions"][:40]])
        foundation.build_historical_foundation_review(**args)
        names_inventory = tmp_path / "data/names-inventory"
        return {"foundation_directory": args["output"], "identity_directory": args["identity_directory"],
                "names_inventory": names_inventory, "foundation_receipt_sha256": _sha(args["output"] / "receipt.json"),
                "identity_receipt_sha256": args["identity_receipt_sha256"],
                "names_receipt_sha256": _sha(names_inventory / "receipt.json"),
                **_public(tmp_path, public if public is not None else [
                    _submission(REMARKS="literal\ttab and\nnew line", PERIOD_OF_REPORT="05-DEC-0019"),
                    _submission(DOCUMENT_TYPE="4/A", DATE_OF_ORIG_SUB="20-NOV-2019")]),
                "output": tmp_path / "data/ownership", "config": config, "repo_root": tmp_path}
    return prepare


def _rows(args, receipt, table):
    return [row for part in receipt["tables"][table]["parts"]
            for row in pq.read_table(args["output"] / part["file"]).to_pylist()]


def _source(args):
    receipt = json.loads((args["names_inventory"] / "receipt.json").read_text())
    return args["names_inventory"] / receipt["source"]["preserved_file"]


def test_full_cohort_source_occurrences_and_exact_original_content_preserved(prepared):
    args = prepared()
    original_bytes = args["sec_submission_path"].read_bytes()
    result = ownership.build_sec_ownership_corrob(**args)
    assert result["counts"]["cohort_rows"] == 2
    assert result["counts"]["cohort_rows_with_any_sec_observation"] == 1
    assert result["counts"]["cohort_rows_without_sec_observation"] == 1
    assert result["counts"]["original_sec_occurrences"] == result["counts"]["observation_rows"] == 2
    assert (args["output"] / "original_SUBMISSION.tsv").read_bytes() == original_bytes
    original = json.loads((args["foundation_directory"] / "receipt.json").read_text())
    expected = [row for spec in original["tables"]["annual_foundation"]["parts"]
                for row in pq.read_table(args["foundation_directory"] / spec["file"]).to_pylist()
                if row["candidate_year"] == 2020 and row["rank_eligible_by_candidate_policy"]]
    assert _rows(args, result, "cohort") == expected
    sec = _rows(args, result, "sec_occurrences")
    assert [row["source_tsv_record"] for row in sec] == [2, 3]
    assert sec[0]["REMARKS"] == "literal\ttab and\nnew line"
    assert sec[0]["PERIOD_OF_REPORT"] == "05-DEC-0019"
    assert sec[1]["DOCUMENT_TYPE"] == "4/A" and sec[1]["DATE_OF_ORIG_SUB"] == "20-NOV-2019"
    assert all(row["accession_occurrences"] == 2 for row in sec)
    observations = _rows(args, result, "observations")
    assert len({row["observation_id"] for row in observations}) == 2
    assert all(json.loads(row["matched_fields_json"]) == ["ticker", "tradingsymbol"] for row in observations)
    assert all(row["unambiguous_exact_literal_observation"] for row in observations)
    assert {row["cik_comparison"] for row in _rows(args, result, "header_comparisons")} == {"LEADING_ZERO_COMPARISON_ONLY"}
    summary = {row["security_id"]: row for row in _rows(args, result, "cohort_summary")}
    assert summary["20"]["observation_status"] == "NO_EXACT_SINGLE_LITERAL_SEC_OBSERVATION"
    assert summary["20"]["original_relationship_rows"] == 1
    assert any(row["security_id"] == "20" and row["accession"] is None
               for row in _rows(args, result, "original_source_followup"))
    for table in result["tables"]:
        assert all(row["known_at"] is None and row["available_at"] is None and row["identity_approved"] is False
                   for row in _rows(args, result, table))
    for path in args["output"].rglob("*"):
        assert path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o400)
    public = json.dumps(ownership.aggregate_summary(result))
    assert "PRIVATE INVENTED" not in public and "0000000123" not in public and str(args["repo_root"]) not in public
    assert result["historical_cik_links_created"] == 0 and result["final_period_opened"] is False
    with pytest.raises(ValueError, match="exists"):
        ownership.build_sec_ownership_corrob(**args)


def test_descriptor_changes_inclusive_bounds_and_original_cusip_class_retained(prepared):
    args = prepared(names=[
        _name(secinfostartdt="2019-10-01", secinfoenddt="2019-11-20", ticker="OLD", cusip="00123456", shareclass="A"),
        _name(secinfostartdt="2019-11-21", ticker="NEW", cusip="00987654", shareclass="B", siccd="0456")],
        securities=("10",), public=[_submission("OLD"), _submission("NEW", day="21-NOV-2019")])
    result = ownership.build_sec_ownership_corrob(**args)
    observations = _rows(args, result, "observations")
    assert len(observations) == 2 and all(row["unambiguous_exact_literal_observation"] for row in observations)
    assert [row["names_record_covers_selection"] for row in observations] == [False, True]
    records = _rows(args, result, "names_records")
    assert [(row["cusip"], row["shareclass"]) for row in records] == [("00123456", "A"), ("00987654", "B")]
    assert records[1]["siccd"] == "0456"


def test_global_collision_outside_cohort_prevents_false_unique_match(prepared):
    args = prepared(names=[_name(secinfostartdt="2019-01-01", ticker="FOO"),
                           _name("99", secinfostartdt="2019-10-01", secinfoenddt="2019-12-01", ticker="FOO")],
                    securities=("10",), public=[_submission()])
    result = ownership.build_sec_ownership_corrob(**args)
    observed = _rows(args, result, "observations")[0]
    assert observed["global_symbol_record_count"] == 2 and observed["security_date_record_count"] == 1
    assert observed["unambiguous_exact_literal_observation"] is False
    assert {row["permno"] for row in _rows(args, result, "names_records")} == {"10", "99"}
    assert result["counts"]["cohort_rows_with_unambiguous_earlier_date_observation"] == 0


def test_overlapping_same_security_with_different_ticker_remains_ambiguous(prepared):
    args = prepared(names=[_name(secinfostartdt="2019-01-01", ticker="FOO"),
                           _name(secinfostartdt="2019-11-01", secinfoenddt="2019-12-01", ticker="DIFFERENT")],
                    securities=("10",), public=[_submission()])
    result = ownership.build_sec_ownership_corrob(**args)
    observed = _rows(args, result, "observations")[0]
    assert observed["global_symbol_record_count"] == 1 and observed["security_date_record_count"] == 2
    assert observed["unambiguous_exact_literal_observation"] is False
    assert result["counts"]["retained_names_source_records"] == 2


@pytest.mark.parametrize("variant", ["0010", "10"])
def test_raw_alias_and_duplicate_source_occurrences_never_deduplicate(prepared, variant):
    duplicate = _name(variant, secinfostartdt="2019-11-01", secinfoenddt="2019-12-01", ticker="FOO")
    args = prepared(names=[_name(secinfostartdt="2019-01-01", ticker="FOO"), duplicate, duplicate],
                    securities=("10",), public=[_submission()])
    result = ownership.build_sec_ownership_corrob(**args)
    observations = _rows(args, result, "observations")
    assert len(observations) == 3
    assert all(row["global_symbol_record_count"] == 3 and not row["unambiguous_exact_literal_observation"]
               for row in observations)
    assert {row["names_source_csv_record"] for row in observations} == {2, 3, 4}
    if variant == "0010":
        assert "LEADING_ZERO_COMPARISON_ONLY" in {row["cohort_identifier_comparison"] for row in observations}


def test_cutoff_day_never_enters_earlier_corroboration_even_with_earlier_report_date(prepared):
    args = prepared(public=[_submission(day="31-DEC-2019", PERIOD_OF_REPORT="20-NOV-2019")])
    result = ownership.build_sec_ownership_corrob(**args)
    summary = {row["security_id"]: row for row in _rows(args, result, "cohort_summary")}["10"]
    assert summary["observation_status"] == "CUTOFF_DAY_OBSERVATIONS_ONLY"
    assert summary["cutoff_day_sec_occurrences"] == 1 and summary["earlier_date_sec_occurrences"] == 0
    assert summary["earlier_candidate_header_agreement"] is False
    assert json.loads(summary["earlier_issuer_cik_literals_json"]) == []
    followup = next(row for row in _rows(args, result, "original_source_followup") if row["accession"])
    assert "CUTOFF_DAY_CLOCK_UNKNOWN" in json.loads(followup["reasons_json"])


def test_multiple_issuer_keys_and_every_current_header_candidate_are_retained(prepared):
    args = prepared(ccm=[_ccm("10"), _ccm("10", cik="999", gvkey="999")],
                    public=[_submission(), _submission(cik="0000000999")])
    result = ownership.build_sec_ownership_corrob(**args)
    comparisons = _rows(args, result, "header_comparisons")
    assert len(comparisons) == 4
    assert {row["ccm_source_csv_record"] for row in comparisons} == {2, 3}
    assert Counter(row["cik_comparison"] for row in comparisons) == {
        "LEADING_ZERO_COMPARISON_ONLY": 2, "DIFFERENT_VALID_COMPARISON_KEYS": 2}
    summary = next(row for row in _rows(args, result, "cohort_summary") if row["security_id"] == "10")
    assert summary["observation_status"] == "MULTIPLE_EARLIER_ISSUER_KEYS_OBSERVED"
    assert summary["earlier_candidate_header_agreement"] and summary["earlier_candidate_header_disagreement"]
    assert len(json.loads(summary["earlier_issuer_cik_literals_json"])) == 2


def test_missing_ccm_relation_is_explicit_not_dropped(prepared):
    args = prepared(ccm=[_ccm("999")], public=[_submission()])
    result = ownership.build_sec_ownership_corrob(**args)
    comparison = _rows(args, result, "header_comparisons")[0]
    assert comparison["cik_comparison"] == "NO_RELATED_CCM_RECORD"
    assert comparison["ccm_source_csv_record"] is comparison["candidate_search"] is None
    assert result["counts"]["cohort_rows"] == 2


def test_multiple_earlier_keys_include_ambiguous_observations_without_promoting_header_comparisons(prepared):
    args = prepared(names=[_name(secinfostartdt="2019-01-01", ticker="FOO"),
                           _name("99", secinfostartdt="2019-11-20", secinfoenddt="2019-11-20", ticker="FOO")],
                    securities=("10",), public=[_submission(cik="0000000999"),
                                                _submission(day="21-NOV-2019")])
    result = ownership.build_sec_ownership_corrob(**args)
    summary = _rows(args, result, "cohort_summary")[0]
    assert summary["earlier_date_sec_occurrences"] == 2
    assert summary["unambiguous_earlier_date_sec_occurrences"] == 1
    assert len(json.loads(summary["earlier_issuer_cik_comparison_keys_json"])) == 2
    assert result["counts"]["cohort_rows_with_multiple_earlier_issuer_keys"] == 1
    assert summary["earlier_candidate_header_agreement"] is True
    assert summary["earlier_candidate_header_disagreement"] is False


def test_placeholder_combined_and_case_variants_preserved_without_invented_aliases(prepared):
    args = prepared(public=[_submission("NONE"), _submission("N/A"), _submission("ISCA, ISCB"),
                            _submission("foo"), _submission("FOO")])
    result = ownership.build_sec_ownership_corrob(**args)
    assert result["counts"]["original_sec_occurrences"] == 5
    assert result["counts"]["observation_rows"] == 1
    assert [row["ISSUERTRADINGSYMBOL"] for row in _rows(args, result, "sec_occurrences")] == [
        "NONE", "N/A", "ISCA, ISCB", "foo", "FOO"]


@pytest.mark.parametrize("pin", ["foundation_receipt_sha256", "identity_receipt_sha256", "names_receipt_sha256", "sec_ledger_sha256"])
def test_explicit_source_pins_fail_closed(prepared, pin):
    args = prepared()
    args[pin] = "0" * 64
    with pytest.raises(ValueError, match="pin|pin differs"):
        ownership.build_sec_ownership_corrob(**args)
    assert not args["output"].exists()


def test_rebound_postcutoff_or_final_filing_rejected_before_private_inputs(prepared, monkeypatch):
    args = prepared()
    args.update(_public(args["repo_root"], [_submission(), _submission(day="01-JAN-2022")]))
    monkeypatch.setattr(ownership, "_load_private", lambda *a, **k: pytest.fail("Private input opened before public date preflight"))
    with pytest.raises(ValueError, match="outside the fixed development quarter"):
        ownership.build_sec_ownership_corrob(**args)
    assert not args["output"].exists()


def test_tampered_identity_part_rejected_before_original_names_opened(prepared, monkeypatch):
    args = prepared()
    receipt = json.loads((args["identity_directory"] / "receipt.json").read_text())
    path = args["identity_directory"] / receipt["tables"]["relationships"]["parts"][0]["file"]
    _write(path, path.read_bytes() + b"altered")
    monkeypatch.setattr(ownership.listing, "_load_source", lambda *a, **k: pytest.fail("Names opened before part validation"))
    with pytest.raises(ValueError, match="byte binding"):
        ownership.build_sec_ownership_corrob(**args)
    assert not args["output"].exists()


@pytest.mark.parametrize("source", ["names", "sec"])
def test_source_mutation_during_matching_prevents_publication(prepared, monkeypatch, source):
    args = prepared()
    observe = ownership._observe
    changed = False
    def mutation(*a, **k):
        nonlocal changed
        result = observe(*a, **k)
        if not changed:
            path = _source(args) if source == "names" else args["sec_submission_path"]
            _write(path, path.read_bytes() + b"\n")
            changed = True
        return result
    monkeypatch.setattr(ownership, "_observe", mutation)
    with pytest.raises(ValueError, match="changed"):
        ownership.build_sec_ownership_corrob(**args)
    assert not args["output"].exists()


def test_rebound_loss_of_eligible_foundation_row_is_rejected(prepared):
    args = prepared()
    path = args["foundation_directory"] / "receipt.json"
    receipt = json.loads(path.read_text())
    spec = receipt["tables"]["annual_foundation"]["parts"][0]
    part = args["foundation_directory"] / spec["file"]
    table = pq.read_table(part)
    rows = table.to_pylist()
    rows = [row for row in rows if not (row["candidate_year"] == 2020 and row["security_id"] == "20")]
    part.chmod(0o600)
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), part)
    spec.update(sha256=_sha(part), bytes=part.stat().st_size, rows=len(rows))
    receipt["tables"]["annual_foundation"]["rows"] = len(rows)
    _json_write(path, receipt)
    args["foundation_receipt_sha256"] = _sha(path)
    with pytest.raises(ValueError, match="accounting"):
        ownership.build_sec_ownership_corrob(**args)
    assert not args["output"].exists()


def test_cli_failure_never_prints_private_paths_or_rows(prepared, monkeypatch, capsys):
    args = prepared()
    monkeypatch.chdir(args["repo_root"])
    main = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/reconcile_sec_ownership.py"))["main"]
    options = {"foundation": args["foundation_directory"], "foundation-receipt-sha256": "0" * 64,
        "identity": args["identity_directory"], "identity-receipt-sha256": args["identity_receipt_sha256"],
        "names-inventory": args["names_inventory"], "names-receipt-sha256": args["names_receipt_sha256"],
        "sec-submission": args["sec_submission_path"], "sec-ledger": args["sec_ledger_path"],
        "sec-ledger-sha256": args["sec_ledger_sha256"], "sec-collection-receipt": args["sec_collection_receipt_path"],
        "output": args["output"]}
    assert main([item for key, value in options.items() for item in ("--" + key, str(value))]) == 1
    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "SEC_OWNERSHIP_CORROBORATION_FAILED"
    assert str(args["repo_root"]) not in output and "PRIVATE" not in output
