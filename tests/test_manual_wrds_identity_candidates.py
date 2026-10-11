"""Synthetic-only preservation and search-scope checks for identity evidence."""

import csv
import gzip
import hashlib
import io
import json
import runpy
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from disclosure_research import manual_wrds_identity_candidates as identity
from disclosure_research import manual_wrds_listing_candidates as listing
from disclosure_research.manual_wrds_metadata import CCM_FIELDS, NAMES_FIELDS, inventory_metadata
from disclosure_research.protocol import load_protocol, write_lock
from disclosure_research.universe import year_start_window


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "configs").mkdir()
    write_lock(load_protocol(), tmp_path / "configs/protocol.lock.json")
    (tmp_path / "configs/protocol.json").write_text(json.dumps(load_protocol()))
    return tmp_path


def _name(permno="10", **changes):
    row = dict.fromkeys(NAMES_FIELDS, "")
    row.update(permno=permno, permco="900", secinfostartdt="2021-01-01", secinfoenddt="2021-12-31",
               securitybegdt="1925-01-01", securityenddt="2025-12-31", issuernm="PRIVATE INVENTED ISSUER",
               ticker="PRIVATE\nMULTILINE", cusip="12345678", securitytype="EQTY", securitysubtype="COM",
               sharetype="NS", issuertype="CORP", primaryexch="N", tradingstatusflg="A",
               hdrprimaryexch="X", hdrsiccd="9999", siccd="0123", usincflg="N", securityactiveflg="N")
    row.update(changes)
    return row


def _ccm(permno="10", **changes):
    row = dict.fromkeys(CCM_FIELDS, "")
    row.update(lpermno=permno, lpermco="900", gvkey="001234", liid="01", linkprim="P", linktype="LC",
               linkdt="2000-01-01", linkenddt="2025-12-31", cik="123", conm="PRIVATE COMPANY\nNAME",
               tic="SECRET_TICKER", cusip="87654321", busdesc="PRIVATE BUSINESS DESCRIPTION",
               weburl="https://private.example.invalid/SECRET_URL")
    row.update(changes)
    return row


def _inventory(repo, rows, role, *, compressed=False):
    fields = NAMES_FIELDS if role == "names" else (*CCM_FIELDS, "busdesc", "weburl")
    header = [field.upper() for field in reversed(fields)]
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(header)
    writer.writerows([[row[field.lower()] for field in header] for row in rows])
    raw = text.getvalue().encode()
    source = repo / f"invented-{role}.bin"
    source.write_bytes(gzip.compress(raw, mtime=0) if compressed else raw)
    directory = repo / "data" / f"{role}-inventory"
    inventory_metadata(source, role=role, request_start="2009-10-07", request_end="2022-02-02",
                       output=directory, config=load_protocol(), repo_root=repo)
    return directory


def _inputs(repo, *, names=None, ccm=None, compressed=False):
    names = [_name()] if names is None else names
    ccm = [_ccm()] if ccm is None else ccm
    names_inventory = _inventory(repo, names, "names")
    directory = repo / "data/listing"
    listing.build_listing_candidates(names_inventory, output=directory, config=load_protocol(), repo_root=repo)
    return _inventory(repo, ccm, "ccm", compressed=compressed), directory


def _run(repo, inputs, **options):
    return identity.build_identity_candidates(*inputs, **{
        "output": repo / "data/identity", "config": load_protocol(), "repo_root": repo, **options})


def _rows(repo, receipt, table):
    return [row for part in receipt["tables"][table]["parts"]
            for row in pq.read_table(repo / "data/identity" / part["file"]).to_pylist()]


def _receipt(directory):
    return json.loads((directory / "receipt.json").read_text())


def _save_receipt(directory, receipt):
    path = directory / "receipt.json"
    path.chmod(0o600)
    path.write_text(json.dumps(receipt))


def _source(directory):
    return directory / _receipt(directory)["source"]["preserved_file"]


def _mutate_source(directory, before, after, *, rebind=False):
    path = _source(directory)
    raw = path.read_bytes().replace(before, after)
    path.chmod(0o600)
    path.write_bytes(raw)
    path.chmod(0o400)
    if rebind:
        receipt = _receipt(directory)
        receipt["source"].update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        _save_receipt(directory, receipt)


def _change_names(directory, update):
    receipt = _receipt(directory)
    part = receipt["projection"]["parts"][0]
    path = directory / part["file"]
    table = pq.read_table(path)
    rows = table.to_pylist()
    update(rows)
    path.chmod(0o600)
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), path)
    path.chmod(0o400)
    part.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size, rows=len(rows))
    _save_receipt(directory, receipt)


def _sec_row(cik="0000000123", accession="0000000123-21-000001", **changes):
    row = dict.fromkeys(identity.SEC_FIELDS, "")
    row.update(cik=cik, name="PUBLIC SYNTHETIC ISSUER", accessionNumber=accession, reportDate="2020-12-31",
               acceptance_date="2021-02-15", acceptance_timestamp="2021-02-15T12:00:00-05:00",
               source_url="https://www.sec.gov/Archives/edgar/data/123/example.htm",
               header_url="https://www.sec.gov/Archives/edgar/data/123/example.hdr.sgml",
               risk_source_url="https://www.sec.gov/Archives/edgar/data/123/risk.htm",
               download_sha256="a" * 64, header_sha256="b" * 64, risk_source_sha256="c" * 64,
               extraction_status="accepted", risk_token_count="1234", extraction_version="synthetic")
    row.update(changes)
    return row


def _manifest(repo, rows):
    path = repo / "invented-sec-manifest.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=identity.SEC_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.mark.parametrize("compressed", [False, True])
def test_real_upstream_bytes_records_parts_and_unknown_history(repo, monkeypatch, compressed):
    monkeypatch.setattr(identity, "_BATCH", 2)
    inputs = _inputs(repo, names=[_name(secinfostartdt="2009-01-01", secinfoenddt="2025-12-31")],
                     ccm=[_ccm(), _ccm("", linktype="NU", cik=""), _ccm("20")], compressed=compressed)
    originals = {path: path.read_bytes() for directory in inputs for path in directory.rglob("*") if path.is_file()}
    result = _run(repo, inputs)
    out = repo / "data/identity"
    assert result["years"] == list(range(2010, 2022))
    assert result["tables"]["ccm_records"]["rows"] == 3
    assert result["tables"]["relationships"]["rows"] == result["tables"]["annual_evidence"]["rows"] == 12
    assert result["source_inventory"]["ccm_records_with_no_related_names_snapshot"] == 2
    assert result["source_inventory"]["identifier_grammar_counts"]["lpermno"] == {
        "positive_ascii_integer": 2, "blank": 1}
    for table_name, table in result["tables"].items():
        for part in table["parts"]:
            path = out / part["file"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == part["sha256"]
            assert path.stat().st_size == part["bytes"]
            assert pq.read_metadata(path).num_rows == part["rows"]
            if table_name != "names_evidence":
                assert part["rows"] <= 2
                for row in pq.read_table(path).to_pylist():
                    assert row["known_at"] is row["available_at"] is None
                    assert row["identity_approved"] is False
    assert all(path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o400)
               for path in [out, *out.rglob("*")])
    assert all(path.read_bytes() == raw for path, raw in originals.items())
    assert (out / "input_receipts/ccm_inventory.json").read_bytes() == originals[inputs[0] / "receipt.json"]
    assert (out / "input_receipts/listing_candidates.json").read_bytes() == originals[inputs[1] / "receipt.json"]
    for part in result["tables"]["names_evidence"]["parts"]:
        assert (out / part["file"]).read_bytes() == originals[inputs[1] / part["upstream_part"]]
    ccm = _rows(repo, result, "ccm_records")
    assert [row["ccm_source_csv_record"] for row in ccm] == [2, 3, 4]
    assert ccm[0]["ccm_conm_raw"] == "PRIVATE COMPANY\nNAME"
    raw_order = [field.lower() for field in result["inputs"]["ccm_observed_header"]]
    expected = hashlib.sha256(json.dumps([_ccm()[field] for field in raw_order],
                                        ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
    assert ccm[0]["full_delivered_row_sha256"] == expected
    assert ccm[0]["ccm_header_cik_raw"] == "123"
    assert ccm[0]["header_cik_comparison_key"] == "0000000123"
    for row in _rows(repo, result, "annual_evidence"):
        window = year_start_window(row["candidate_year"], load_protocol())
        assert row["information_cutoff"] == window["information_cutoff"]
        assert row["selection_asof"] == window["selection_asof"]
        assert row["evidence_status"] == "SINGLE_CANDIDATE_REQUIRES_HISTORICAL_IDENTITY_EVIDENCE"
    summary = json.dumps(identity.aggregate_summary(result))
    for secret in ("PRIVATE COMPANY", "PRIVATE INVENTED", "SECRET_TICKER", "SECRET_URL", "0000000123", "001234"):
        assert secret not in summary
    assert result["source_approvals"] == result["approved_security_links_created"] == 0
    assert all(result[field] is False for field in (
        "model_ready", "historical_cik_supplied", "historical_availability_supplied", "original_sec_bytes_reread",
        "source_population_completeness_verified", "prior_arithmetic_review_modified", "final_period_opened",
        "returns_read", "market_outcomes_read", "universe_membership_created"))


def test_every_interval_occurrence_retained_future_and_expired_context_excluded(repo):
    bounds = [
        ("2021-01-01", "2021-01-01", "FINITE_INCLUSIVE_CANDIDATE", True),
        ("2021-01-02", "2025-12-31", "AFTER_SELECTION_CONTEXT", False),
        ("2000-01-01", "2020-12-31", "BEFORE_SELECTION_CONTEXT", False),
        ("2022-01-01", "2020-12-31", "REVERSED_FINITE_CONTEXT", False),
        ("B", "E", "OPEN_MARKER_BOUNDS_UNRESOLVED_CANDIDATE", True),
        ("", "E", "OPEN_MARKER_BOUNDS_UNRESOLVED_CANDIDATE", True),
        ("nonsense", " ", "OTHER_BOUNDS_UNRESOLVED_CANDIDATE", True),
        ("2022-01-01", "E", "AFTER_SELECTION_CONTEXT", False),
        ("B", "2020-12-31", "BEFORE_SELECTION_CONTEXT", False),
        ("", "", "OTHER_BOUNDS_UNRESOLVED_CANDIDATE", True),
    ]
    inputs = _inputs(repo, ccm=[_ccm(linkdt=first, linkenddt=last) for first, last, _, _ in bounds])
    result = _run(repo, inputs)
    pairs = _rows(repo, result, "relationships")
    assert [(row["ccm_linkdt_raw"], row["ccm_linkenddt_raw"], row["date_relation"], row["candidate_search"])
            for row in pairs] == bounds
    annual = _rows(repo, result, "annual_evidence")[0]
    assert annual["related_ccm_records"] == annual["related_pair_rows"] == 10
    assert annual["candidate_ccm_records"] == annual["candidate_pair_rows"] == 5
    assert annual["finite_candidate_ccm_records"] == 1
    assert annual["open_marker_candidate_ccm_records"] == annual["other_unresolved_candidate_ccm_records"] == 2
    assert annual["evidence_status"] == "MULTIPLE_OR_AMBIGUOUS_CANDIDATE_EVIDENCE"


def test_duplicates_share_classes_and_all_link_codes_never_filtered(repo):
    first = _ccm(linktype="NU", linkprim="J")
    rows = [first, dict(first), _ccm(linktype="LS", liid="02", cik="456", lpermco="901"),
            _ccm(linktype="PRIVATE_UNKNOWN", linkprim="PRIVATE_FLAG", cik="", lpermco="")]
    inputs = _inputs(repo, names=[_name(), _name(), _name(shareclass="B")], ccm=rows)
    result = _run(repo, inputs)
    annual = _rows(repo, result, "annual_evidence")[0]
    assert annual["names_record_count"] == 3
    assert annual["names_distinct_projection_count"] == 2
    assert annual["names_exact_duplicate_record_excess"] == 1
    assert annual["names_ambiguous"] is True and annual["ordinary_listing_candidate"] is False
    assert annual["related_pair_rows"] == annual["candidate_pair_rows"] == 12
    assert annual["candidate_ccm_records"] == 4
    assert annual["candidate_header_cik_keys"] == 2
    assert annual["candidate_blank_header_cik_records"] == 1
    assert annual["candidate_permco_disagreement_pairs"] == annual["candidate_permco_unresolved_pairs"] == 3
    detail = _rows(repo, result, "ccm_records")
    assert detail[0]["full_delivered_row_sha256"] == detail[1]["full_delivered_row_sha256"]
    assert [row["ccm_liid_raw"] for row in detail] == ["01", "01", "02", "01"]
    assert result["source_inventory"]["link_flag_counts"]["linktype"]["__UNRECOGNIZED__"] == 1
    assert "PRIVATE_UNKNOWN" not in json.dumps(identity.aggregate_summary(result))


def test_identifier_grammar_and_aliases_are_comparison_only(repo):
    bad = ["", " ", "10.0", "+10", "-10", "1e1", "10 ", "０１０", "0", "0" * 21]
    inputs = _inputs(repo, names=[_name("10"), _name("0010"), _name("30"), _name("40", permco="")],
                     ccm=[_ccm("10"), _ccm("00010"), *[_ccm(value) for value in bad],
                          _ccm("40", cik="0000000000")])
    result = _run(repo, inputs)
    pairs = _rows(repo, result, "relationships")
    assert len(pairs) == 5
    assert {row["ccm_lpermno_raw"] for row in pairs} == {"10", "00010", "40"}
    assert {row["id_comparison"] for row in pairs} == {"EXACT_RAW_TEXT", "LEADING_ZERO_COMPARISON_ONLY"}
    annual = {row["names_permno_raw"]: row for row in _rows(repo, result, "annual_evidence")}
    for key in ("10", "0010"):
        assert annual[key]["raw_names_ids_sharing_comparison_key"] == 2
        assert annual[key]["evidence_status"] == "MULTIPLE_OR_AMBIGUOUS_CANDIDATE_EVIDENCE"
    assert annual["30"]["evidence_status"] == "NO_RELATED_CCM_RECORD"
    assert annual["40"]["evidence_status"] == "SINGLE_CANDIDATE_HEADER_CIK_MISSING_OR_UNSUPPORTED"
    assert annual["40"]["candidate_permco_unresolved_pairs"] == 1
    records = _rows(repo, result, "ccm_records")
    assert [row["ccm_lpermno_raw"] for row in records][2:-1] == bad
    assert all(row["permno_comparison_key"] is None for row in records[2:-1])


def test_gvkey_nonblank_count_uses_inventory_whitespace_semantics_without_trimming_raw_ids(repo):
    gvkeys = ["\t", "\n", " \t\n\u00a0 ", "001234", " 001234 "]
    inputs = _inputs(repo, ccm=[_ccm(gvkey=value) for value in gvkeys])
    result = _run(repo, inputs)
    annual = _rows(repo, result, "annual_evidence")[0]
    assert annual["candidate_ccm_records"] == 5
    assert annual["candidate_nonblank_raw_gvkeys"] == 2
    assert _receipt(inputs[0])["columns"]["gvkey"] == {"blank": 3, "nonblank": 2}
    assert result["source_inventory"]["identifier_grammar_counts"]["gvkey"] == {
        "blank": 3, "positive_ascii_integer": 1, "unsupported_text": 1}
    assert [row["ccm_gvkey_raw"] for row in _rows(repo, result, "ccm_records")] == gvkeys


def test_sec_manifest_discovery_is_same_year_header_only_and_unmatched_retained(repo):
    inputs = _inputs(repo, names=[_name(secinfoenddt="2021-01-01")], ccm=[
        _ccm(linkenddt="2021-01-31"), _ccm("20", cik="456"),
        _ccm(linkdt="2021-02-01", cik="789"),
    ])
    manifest = _manifest(repo, [_sec_row(), _sec_row("0000000456", "0000000456-21-000001"),
                              _sec_row("0000000789", "0000000789-21-000001"),
                              _sec_row("0000000123", "0000000123-20-000001", acceptance_date="2020-02-15",
                                       acceptance_timestamp="2020-02-15T12:00:00-05:00", reportDate="2019-12-31")])
    original = manifest.read_bytes()
    result = _run(repo, inputs, sec_manifest=manifest)
    assert result["tables"]["sec_discovery"]["rows"] == 1
    assert result["tables"]["sec_manifest_coverage"]["rows"] == 4
    match = _rows(repo, result, "sec_discovery")[0]
    assert match["cik_comparison"] == "LEADING_ZERO_COMPARISON_ONLY"
    assert match["ccm_date_compatible_at_acceptance"] is False
    assert match["names_secinfo_covers_acceptance"] is False
    assert match["ccm_relation_at_acceptance"] == "BEFORE_SELECTION_CONTEXT"
    assert match["known_at"] is match["available_at"] is None
    assert match["original_sec_bytes_reread"] is match["identity_approved"] is False
    coverage = _rows(repo, result, "sec_manifest_coverage")
    assert [row["discovery_pair_rows"] for row in coverage] == [1, 0, 0, 0]
    assert [row["sec_manifest_csv_record"] for row in coverage] == [2, 3, 4, 5]
    assert (repo / "data/identity/input_receipts/sec_manifest.csv").read_bytes() == original
    assert result["sec_manifest"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert result["sec_manifest"]["recorded_source_hashes_verified_against_original_bytes"] is False
    annual = _rows(repo, result, "annual_evidence")[0]
    assert annual["sec_manifest_discovery_pairs"] == annual["sec_manifest_discovery_filings"] == 1


@pytest.mark.parametrize("names_match", [False, True])
def test_zero_relationships_and_zero_manifest_have_schema_and_no_lost_rows(repo, names_match):
    names = [_name()] if names_match else [_name(secinfostartdt="2023-01-01", secinfoenddt="2025-12-31")]
    inputs = _inputs(repo, names=names, ccm=[_ccm("", linkdt="B", linkenddt="E", cik="")])
    manifest = _manifest(repo, [])
    result = _run(repo, inputs, sec_manifest=manifest)
    assert result["source_inventory"]["date_bounds"]["linkdt"]["first_finite_date"] is None
    assert result["tables"]["ccm_records"]["rows"] == 1
    assert result["tables"]["annual_evidence"]["rows"] == int(names_match)
    for table, schema in (("relationships", identity.PAIR_SCHEMA), ("sec_discovery", identity.SEC_MATCH_SCHEMA),
                          ("sec_manifest_coverage", identity.SEC_COVERAGE_SCHEMA)):
        assert result["tables"][table]["rows"] == 0
        part = result["tables"][table]["parts"][0]
        assert pq.read_schema(repo / "data/identity" / part["file"]) == schema
    assert result["sec_manifest"]["provided"] is True


def test_context_only_never_promotes_sec_discovery(repo):
    inputs = _inputs(repo, ccm=[_ccm(linkdt="2022-01-01", linkenddt="E")])
    result = _run(repo, inputs, sec_manifest=_manifest(repo, [_sec_row()]))
    annual = _rows(repo, result, "annual_evidence")[0]
    assert annual["evidence_status"] == "DATED_CONTEXT_ONLY_NO_JANUARY1_CANDIDATE"
    assert annual["candidate_ccm_records"] == annual["sec_manifest_discovery_pairs"] == 0
    assert result["tables"]["relationships"]["rows"] == 1


def test_header_only_ccm_contract_has_zero_bounds_and_preserves_names_coverage(repo):
    # The current inventory producer refuses empty downloads. A fully declared
    # zero-row schema remains a safe consumer edge case, with no invented link.
    inputs = _inputs(repo)
    directory = inputs[0]
    receipt = _receipt(directory)
    content = io.StringIO(newline="")
    csv.writer(content).writerow(receipt["source"]["observed_header"])
    raw = content.getvalue().encode()
    path = _source(directory)
    path.chmod(0o600)
    path.write_bytes(raw)
    path.chmod(0o400)
    receipt["source"].update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    for key in ("all_rows", "definite_requested_overlap"):
        receipt[key] = dict.fromkeys(receipt[key], 0)
    for values in receipt["columns"].values():
        values.update(blank=0, nonblank=0)
    for values in receipt["date_bounds"].values():
        values.update(dict.fromkeys(identity.BOUND_KINDS, 0), first_finite_date=None, last_finite_date=None)
    receipt["interval_classifications"]["linkdt/linkenddt"] = dict.fromkeys(identity.INTERVAL_KINDS, 0)
    _save_receipt(directory, receipt)
    result = _run(repo, inputs)
    assert result["tables"]["ccm_records"]["rows"] == result["tables"]["relationships"]["rows"] == 0
    assert result["source_inventory"]["ccm_records_with_no_related_names_snapshot"] == 0
    annual = _rows(repo, result, "annual_evidence")[0]
    assert annual["names_record_count"] == 1
    assert annual["evidence_status"] == "NO_RELATED_CCM_RECORD"


@pytest.mark.parametrize("field,value", [
    ("acceptance_date", "2022-01-01"), ("acceptance_timestamp", "2021-02-15T12:00:00"),
    ("acceptance_timestamp", "2021-02-16T12:00:00-05:00"), ("cik", "123.0"),
    ("accessionNumber", "private malformed accession"), ("download_sha256", "unknown"),
    ("source_url", "https://private.example.invalid/SECRET_TOKEN"),
    ("header_url", "https://www.sec.gov/Archives/edgar/data/123/doc?token=SECRET"),
])
def test_invalid_or_final_sec_manifest_rejected_before_vendor_inputs(repo, monkeypatch, field, value):
    def prohibited(*args, **kwargs):
        raise AssertionError("Vendor input opened before SEC preflight completed")
    monkeypatch.setattr(identity.liquidity, "_load", prohibited)
    manifest = _manifest(repo, [_sec_row(**{field: value})])
    with pytest.raises(ValueError):
        _run(repo, (repo / "absent-ccm", repo / "absent-names"), sec_manifest=manifest)
    assert not (repo / "data/identity").exists()


def test_duplicate_manifest_accession_rejected_before_inputs(repo):
    manifest = _manifest(repo, [_sec_row(), _sec_row()])
    with pytest.raises(ValueError, match="repeats an accession"):
        _run(repo, (repo / "absent-ccm", repo / "absent-names"), sec_manifest=manifest)


@pytest.mark.parametrize("change", ["hash", "header", "width", "row_count", "bounds", "columns", "role", "protocol", "path", "normalized"])
def test_ccm_binding_schema_accounting_and_safe_paths(repo, change):
    inputs = _inputs(repo)
    directory = inputs[0]
    if change == "hash":
        _mutate_source(directory, b"SECRET_TICKER", b"ALTERED_TICKER")
    elif change == "width":
        _mutate_source(directory, b"SECRET_TICKER", b"SECRET_TICKER,extra", rebind=True)
    else:
        receipt = _receipt(directory)
        if change == "header":
            receipt["source"]["observed_header"][0] = "EXTRA_NAME"
        elif change == "row_count":
            receipt["all_rows"]["rows"] += 1
        elif change == "bounds":
            receipt["date_bounds"]["linkenddt"]["last_finite_date"] = "2024-12-31"
        elif change == "columns":
            receipt["columns"]["cik"] = {"blank": 1, "nonblank": 0}
        elif change == "role":
            receipt["role"] = "names"
        elif change == "protocol":
            receipt["protocol_sha256"] = "f" * 64
        elif change == "normalized":
            receipt["values_normalized"] = 1
        else:
            receipt["source"]["preserved_file"] = "../invented-ccm.bin"
        _save_receipt(directory, receipt)
    with pytest.raises(ValueError):
        _run(repo, inputs)
    assert not (repo / "data/identity").exists()


@pytest.mark.parametrize("field,value", [
    ("candidate_year", 2022), ("known_at", "2020-01-01T00:00:00Z"),
    ("source_csv_record", 100), ("source_inventory_sha256", "a" * 64),
    ("secinfoenddt", "2020-12-31"),
])
def test_names_date_and_provenance_pass_finishes_before_matching(repo, monkeypatch, field, value):
    inputs = _inputs(repo)
    _change_names(inputs[1], lambda rows: rows[0].update({field: value}))
    def prohibited(*args, **kwargs):
        raise AssertionError("Identity matching began before full source preflight")
    monkeypatch.setattr(identity, "_write_pairs", prohibited)
    with pytest.raises(ValueError):
        _run(repo, inputs)


def test_names_declared_ambiguity_must_match_actual_occurrences(repo):
    inputs = _inputs(repo, names=[_name(), _name()])
    def change(rows):
        for row in rows:
            row.update(security_year_record_count=1, security_year_distinct_projection_count=1,
                       ambiguous_security_year=False, ordinary_candidate=True,
                       candidate_status="ORDINARY_CORPORATE_COMMON_CANDIDATE")
    _change_names(inputs[1], change)
    with pytest.raises(ValueError, match="actual overlap groups"):
        _run(repo, inputs)


@pytest.mark.parametrize("target", ["ccm", "names", "sec"])
def test_final_source_mutation_guard_prevents_published_bundle(repo, monkeypatch, target):
    inputs = _inputs(repo)
    manifest = _manifest(repo, [_sec_row()])
    original = identity._write_annual
    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        if target == "ccm":
            _mutate_source(inputs[0], b"SECRET_TICKER", b"ALTERED_TICKER")
        elif target == "names":
            _change_names(inputs[1], lambda rows: rows[0].update(ticker="ALTERED"))
        else:
            manifest.write_bytes(manifest.read_bytes() + b"\n")
        return result
    monkeypatch.setattr(identity, "_write_annual", mutate)
    with pytest.raises(ValueError, match="changed"):
        _run(repo, inputs, sec_manifest=manifest)
    assert not (repo / "data/identity").exists()


def test_protocol_private_destination_and_no_overwrite(repo):
    inputs = _inputs(repo)
    with pytest.raises(ValueError):
        _run(repo, inputs, output=repo / "public-evidence")
    with pytest.raises(ValueError, match="separate"):
        _run(repo, inputs, output=inputs[0] / "nested")
    _run(repo, inputs)
    with pytest.raises(ValueError):
        _run(repo, inputs)
    changed = load_protocol()
    changed["development_end"] = 2022
    with pytest.raises(ValueError):
        _run(repo, inputs, output=repo / "data/changed-protocol", config=changed)


def test_cli_success_and_error_are_aggregate_only(repo, monkeypatch, capsys):
    cli = runpy.run_path(str(Path(__file__).parents[1] / "scripts/wrds_manual_identity_candidates.py"))["main"]
    inputs = _inputs(repo, ccm=[_ccm(linkprim="PRIVATE_FLAG", linktype="SECRET_LINK")])
    monkeypatch.chdir(repo)
    args = ["--ccm-inventory", str(inputs[0]), "--listing-candidates", str(inputs[1]),
            "--output", str(repo / "data/identity")]
    assert cli(args) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["source_approvals"] == 0
    assert all(secret not in output for secret in ("SECRET", "PRIVATE COMPANY", "PRIVATE_FLAG", "0000000123"))
    assert cli(args) == 1
    failed = json.loads(capsys.readouterr().out)
    assert set(failed) == {"status", "error_type", "model_ready", "source_approvals"}
