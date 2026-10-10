"""Only invented metadata is used in these candidate-evidence tests."""

import csv
import gzip
import hashlib
import io
import json
import runpy
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from disclosure_research import manual_wrds_listing_candidates as candidates
from disclosure_research.manual_wrds_metadata import NAMES_FIELDS, inventory_metadata
from disclosure_research.protocol import load_protocol, write_lock
from disclosure_research.universe import year_start_window


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "configs").mkdir()
    write_lock(load_protocol(), tmp_path / "configs" / "protocol.lock.json")
    (tmp_path / "configs" / "protocol.json").write_text(json.dumps(load_protocol()))
    return tmp_path


def row(**changes):
    result = dict.fromkeys(NAMES_FIELDS, "")
    result.update(permno="0010001", permco="0020001", secinfostartdt="2010-01-01",
                  secinfoenddt="2010-12-31", securitybegdt="1925-01-01",
                  securityenddt="2025-12-31", issuernm="Private invented corporation",
                  ticker="PRIVATE\nTICKER", cusip="12345678", securitytype="EQTY",
                  securitysubtype="COM", sharetype="NS", issuertype="CORP",
                  primaryexch="N", tradingstatusflg="A", securityactiveflg="N",
                  hdrprimaryexch="X", hdrsiccd="9999", siccd="0123", usincflg="N")
    result.update(changes)
    return result


def inventory(repo, rows, *, header=None, compressed=False):
    header = list(header or NAMES_FIELDS)
    content = io.StringIO(newline="")
    writer = csv.writer(content)
    writer.writerow(header)
    for record in rows:
        writer.writerow([record.get(field.lower(), "private extra") for field in header])
    raw = content.getvalue().encode()
    source = repo / "invented-download.bin"
    source.write_bytes(gzip.compress(raw, mtime=0) if compressed else raw)
    directory = repo / "data" / "names"
    inventory_metadata(source, role="names", request_start="2009-10-07", request_end="2022-02-02",
                       output=directory, config=load_protocol(), repo_root=repo)
    return directory


def run(repo, directory, **options):
    return candidates.build_listing_candidates(directory, **{
        "output": repo / "data" / "candidates", "config": load_protocol(), "repo_root": repo, **options})


def source_path(directory):
    receipt = json.loads((directory / "receipt.json").read_text())
    return directory / receipt["source"]["preserved_file"]


def output_rows(repo, receipt):
    rows = []
    for part in receipt["projection"]["parts"]:
        rows.extend(pq.read_table(repo / "data" / "candidates" / part["file"]).to_pylist())
    return rows


def change_receipt(directory, change):
    path = directory / "receipt.json"
    receipt = json.loads(path.read_text())
    change(receipt)
    path.write_text(json.dumps(receipt))


def mutate_source(directory, before, after, *, update_binding=False):
    path = source_path(directory)
    raw = path.read_bytes().replace(before, after)
    path.chmod(0o600)
    path.write_bytes(raw)
    path.chmod(0o400)
    if update_binding:
        change_receipt(directory, lambda receipt: receipt["source"].update(
            sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)))


@pytest.mark.parametrize("compressed", [False, True])
def test_real_inventory_compatibility_byte_bindings_parts_and_calendar_cutoffs(repo, monkeypatch, compressed):
    monkeypatch.setattr(candidates, "_BATCH_ROWS", 2)
    directory = inventory(repo, [row(secinfostartdt="2009-01-01", secinfoenddt="2025-12-31")],
                          header=[field.upper() for field in reversed(NAMES_FIELDS)], compressed=compressed)
    original = source_path(directory).read_bytes()
    input_receipt = (directory / "receipt.json").read_bytes()
    result = run(repo, directory)
    out = repo / "data" / "candidates"
    assert source_path(directory).read_bytes() == original
    assert (out / "input_receipts" / "names.json").read_bytes() == input_receipt
    assert result["source"]["source_sha256"] == hashlib.sha256(original).hexdigest()
    assert result["source"]["source_rows"] == 1
    assert result["projection"]["rows"] == 12
    assert result["years"] == list(range(2010, 2022))
    assert (out.stat().st_mode & 0o777) == 0o700
    records = output_rows(repo, result)
    for part in result["projection"]["parts"]:
        path = out / part["file"]
        assert pq.read_schema(path) == candidates.CANDIDATE_SCHEMA
        assert part["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert part["bytes"] == path.stat().st_size
        assert part["rows"] == pq.read_metadata(path).num_rows <= 2
        assert path.stat().st_mode & 0o222 == 0
    for record in records:
        expected = year_start_window(record["candidate_year"], load_protocol())
        assert record["selection_asof"] == expected["selection_asof"]
        assert record["information_cutoff"] == expected["information_cutoff"]
        assert record["selection_session"] == expected["selection_session"]
        assert record["known_at"] is None and record["source_csv_record"] == 2
        assert record["ordinary_candidate"] is True
        assert record["source_sha256"] == result["source"]["source_sha256"]
        assert record["source_inventory_sha256"] == hashlib.sha256(input_receipt).hexdigest()
        assert record["ticker"] == "PRIVATE\nTICKER" and record["permno"] == "0010001"
        assert "cik" not in record and "issuer_rank" not in record
    assert result["known_at_null_rows"] == 12
    assert result["prior_arithmetic_review_modified"] is False
    assert result["model_ready"] is False and result["source_approvals"] == 0
    assert result["final_period_opened"] is False
    assert json.loads((out / "receipt.json").read_text()) == result
    assert not list(out.glob("listing-candidates-*"))


def test_inclusive_secinfo_bounds_control_snapshots_and_life_does_not_extend_them(repo):
    directory = inventory(repo, [
        row(permno="10001", secinfostartdt="2010-01-01", secinfoenddt="2010-01-01"),
        row(permno="10002", secinfostartdt="2009-12-31", secinfoenddt="2010-01-01"),
        row(permno="10003", secinfostartdt="2010-01-02", secinfoenddt="2010-12-31"),
        row(permno="10004", secinfostartdt="2022-01-01", secinfoenddt="2025-12-31"),
    ])
    result = run(repo, directory)
    records = output_rows(repo, result)
    assert [(record["candidate_year"], record["source_csv_record"]) for record in records] == [(2010, 2), (2010, 3)]
    assert result["source"]["source_rows_with_annual_snapshot"] == 2
    assert result["source"]["source_rows_without_annual_snapshot"] == 2
    assert result["source"]["full_history_retained_in_original"] is True
    assert result["source"]["original_source_rows_removed"] == 0
    assert result["projection"]["all_matching_source_record_year_pairs_retained"] is True


def test_header_future_descriptors_active_flag_and_incorporation_do_not_change_history(repo, monkeypatch):
    directory = inventory(repo, [row(hdrprimaryexch="future-private-exchange", hdrsiccd="future-private-industry",
                                    securityactiveflg="N", usincflg="N", primaryexch="R"),
                                 row(secinfostartdt="2023-01-01", secinfoenddt="2025-12-31",
                                     securitytype="future-private-classification")])
    original = candidates._classify

    def classify(record):
        assert record["securitytype"] != "future-private-classification"
        return original(record)

    monkeypatch.setattr(candidates, "_classify", classify)
    result = run(repo, directory)
    records = output_rows(repo, result)
    assert len(records) == 1 and records[0]["ordinary_candidate"] is True
    assert records[0]["primaryexch"] == "R" and records[0]["siccd"] == "0123"
    assert records[0]["hdrsiccd"] == "future-private-industry"
    assert records[0]["securityactiveflg"] == "N" and records[0]["known_at"] is None


def test_exact_repeats_and_different_overlapping_projections_are_retained_and_ambiguous(repo):
    records = [row(), row(), row(siccd="5678"),
               row(secinfostartdt="2011-01-01", secinfoenddt="2012-12-31"),
               row(secinfostartdt="2012-01-01", secinfoenddt="2013-12-31")]
    result = run(repo, inventory(repo, records))
    saved = output_rows(repo, result)
    first = [record for record in saved if record["candidate_year"] == 2010]
    assert len(first) == 3
    assert all(record["candidate_status"] == "AMBIGUOUS_DATED_RECORDS" for record in first)
    assert all(record["ordinary_candidate"] is False for record in first)
    assert all(record["security_year_record_count"] == 3 for record in first)
    assert all(record["security_year_distinct_projection_count"] == 2 for record in first)
    counts = result["year_summaries"][0]
    assert counts["exact_24_field_duplicate_snapshot_excess"] == 1
    assert counts["security_year_groups_with_different_24_field_projections"] == 1
    assert counts["ambiguous_candidate_rows"] == 3
    assert next(record for record in saved if record["candidate_year"] == 2011)["ordinary_candidate"] is True
    assert all(record["ambiguous_security_year"] for record in saved if record["candidate_year"] == 2012)
    assert next(record for record in saved if record["candidate_year"] == 2013)["ordinary_candidate"] is True


@pytest.mark.parametrize("changes,status", [
    ({"issuertype": "REIT"}, "SCOPE_REVIEW_REIT_COMMON"),
    ({"sharetype": "SB"}, "SCOPE_REVIEW_BENEFICIAL_INTEREST_COMMON"),
    ({"sharetype": "AD"}, "SCOPE_REVIEW_ADR_COMMON"),
    ({"sharetype": "CE"}, "SCOPE_REVIEW_CERTIFICATE_COMMON"),
    ({"sharetype": "UG"}, "SCOPE_REVIEW_UNIT_COMMON"),
    ({"sharetype": "private-unrecognized-code"}, "SCOPE_REVIEW_UNKNOWN_COMMON_FORM"),
    ({"securitytype": "FUND", "securitysubtype": "ETF"}, "KNOWN_NON_COMMON_CLASSIFICATION"),
    ({"securitytype": "eqty"}, "UNRESOLVED_SECURITY_CLASSIFICATION"),
    ({"primaryexch": "X"}, "UNRESOLVED_LISTING_VENUE"),
    ({"tradingstatusflg": "D"}, "DATED_DELISTED"),
    ({"tradingstatusflg": "H"}, "DATED_HALTED"),
    ({"tradingstatusflg": "S"}, "DATED_SUSPENDED"),
    ({"tradingstatusflg": "X"}, "UNRESOLVED_TRADING_STATUS"),
    ({"permno": ""}, "UNRESOLVED_SECURITY_IDENTIFIER"),
])
def test_classification_scope_and_unknowns_never_become_final_exclusions(repo, changes, status):
    result = run(repo, inventory(repo, [row(**changes)]))
    record = output_rows(repo, result)[0]
    assert record["candidate_status"] == status
    assert record["ordinary_candidate"] is False
    assert result["final_exclusions_created"] is False
    assert result["universe_membership_created"] is False
    assert result["source_population_completeness_verified"] is False


@pytest.mark.parametrize("venue", ["A", "B", "I", "N", "Q", "R"])
def test_all_recognized_us_venues_can_be_ordinary_candidates(repo, venue):
    result = run(repo, inventory(repo, [row(primaryexch=venue, issuertype="ACOR")]))
    assert output_rows(repo, result)[0]["ordinary_candidate"] is True


@pytest.mark.parametrize("changes", [
    {"secinfostartdt": "B"}, {"secinfoenddt": "E"}, {"securitybegdt": ""},
    {"securityenddt": "2025-02-30"}, {"secinfostartdt": "2010-1-1"},
    {"secinfostartdt": "2011-01-01", "secinfoenddt": "2010-12-31"},
    {"securitybegdt": "2026-01-01", "securityenddt": "2025-12-31"},
])
def test_full_source_interval_validation_precedes_every_classification(repo, monkeypatch, changes):
    directory = inventory(repo, [row(), row(permno="10002", **changes)])
    monkeypatch.setattr(candidates, "_classify", lambda _: pytest.fail("Classification opened before full date validation"))
    with pytest.raises(ValueError):
        run(repo, directory)
    out = repo / "data" / "candidates"
    assert not (out / "receipt.json").exists()
    assert list((out / "candidates").iterdir()) == []


@pytest.mark.parametrize("change", ["hash", "header", "width", "count", "bounds", "protocol", "schema", "role"])
def test_source_receipt_hash_schema_header_width_and_counts_are_verified(repo, monkeypatch, change):
    directory = inventory(repo, [row()])
    if change == "hash":
        mutate_source(directory, b"CORP", b"ACOR")
    elif change == "header":
        mutate_source(directory, b"permno,", b"PERMNO,", update_binding=True)
    elif change == "width":
        mutate_source(directory, b"EQTY,", b"EQTY,extra,", update_binding=True)
    elif change == "count":
        change_receipt(directory, lambda receipt: receipt["all_rows"].update(rows=2))
    elif change == "bounds":
        change_receipt(directory, lambda receipt: receipt["date_bounds"]["secinfostartdt"].update(first_finite_date="2009-01-01"))
    elif change == "protocol":
        change_receipt(directory, lambda receipt: receipt.update(protocol_sha256="0" * 64))
    elif change == "schema":
        change_receipt(directory, lambda receipt: receipt.update(schema_version=2))
    else:
        change_receipt(directory, lambda receipt: receipt.update(role="ccm"))
    monkeypatch.setattr(candidates, "_classify", lambda _: pytest.fail("Unverified source reached classification"))
    with pytest.raises(ValueError):
        run(repo, directory)


@pytest.mark.parametrize("target", ["source", "receipt"])
def test_mutation_after_date_preflight_refuses_classification(repo, monkeypatch, target):
    directory = inventory(repo, [row()])
    original = candidates._date_preflight

    def mutate(*args):
        result = original(*args)
        if target == "source":
            mutate_source(directory, b"CORP", b"ACOR")
        else:
            change_receipt(directory, lambda receipt: receipt.update(unreviewed_change=True))
        return result

    monkeypatch.setattr(candidates, "_date_preflight", mutate)
    monkeypatch.setattr(candidates, "_classify", lambda _: pytest.fail("Changed source reached classification"))
    with pytest.raises(ValueError, match="changed"):
        run(repo, directory)


def test_source_mutation_during_output_prevents_success_receipt(repo, monkeypatch):
    directory = inventory(repo, [row()])
    original = candidates._emit_candidates

    def mutate(*args):
        result = original(*args)
        mutate_source(directory, b"CORP", b"ACOR")
        return result

    monkeypatch.setattr(candidates, "_emit_candidates", mutate)
    with pytest.raises(ValueError, match="changed"):
        run(repo, directory)
    assert not (repo / "data" / "candidates" / "receipt.json").exists()


def test_unknown_flag_text_and_identifiers_never_enter_aggregate_summary(repo, monkeypatch, capsys):
    main = runpy.run_path(str(Path("scripts/wrds_manual_listing_candidates.py").resolve()))["main"]
    directory = inventory(repo, [row(sharetype="https://example.invalid/private-session-token")])
    monkeypatch.chdir(repo)
    assert main(["--names-inventory", str(directory), "--output", "data/candidates"]) == 0
    printed = capsys.readouterr().out
    summary = json.loads(printed)
    assert all(secret not in printed for secret in ("private-session-token", "0010001", "0020001", "Private invented", "PRIVATE", str(repo)))
    counts = summary["year_summaries"][0]["known_flag_counts"]["sharetype"]
    assert counts["unknown_or_blank_rows"] == 1
    assert sum(counts["known_code_counts"].values()) == 0
    assert main(["--names-inventory", str(directory), "--output", "data/candidates"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "LISTING_CANDIDATES_FAILED"


def test_frozen_years_paths_and_overwrite_guards(repo):
    directory = inventory(repo, [row()])
    with pytest.raises(ValueError, match="Protocol has changed"):
        run(repo, directory, config={**load_protocol(), "development_end": 2022})
    changed = {**load_protocol(), "initial_train_start": 2009}
    (repo / "configs" / "protocol.lock.json").unlink()
    write_lock(changed, repo / "configs" / "protocol.lock.json")
    with pytest.raises(ValueError, match="2010 through 2021"):
        run(repo, directory, config=changed)
    (repo / "configs" / "protocol.lock.json").unlink()
    write_lock(load_protocol(), repo / "configs" / "protocol.lock.json")
    with pytest.raises(ValueError, match="private directory"):
        run(repo, directory, output=repo / "reports" / "public")
    change_receipt(directory, lambda receipt: receipt["source"].update(preserved_file="../escape.csv"))
    with pytest.raises(ValueError, match="safe relative path"):
        run(repo, directory)


def test_cli_has_no_holdout_year_override(capsys):
    main = runpy.run_path(str(Path("scripts/wrds_manual_listing_candidates.py")))["main"]
    with pytest.raises(SystemExit) as raised:
        main(["--names-inventory", "invented", "--output", "data/invented", "--years", "2022"])
    assert raised.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err
