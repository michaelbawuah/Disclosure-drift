import csv
import gzip
import hashlib
import io
import json
import runpy
from pathlib import Path

import pytest

from disclosure_research import manual_wrds_metadata as metadata
from disclosure_research.protocol import load_protocol, write_lock


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "configs").mkdir()
    write_lock(load_protocol(), tmp_path / "configs" / "protocol.lock.json")
    return tmp_path


def row(role="names", **changes):
    result = dict.fromkeys(metadata.SCHEMAS[role], "")
    if role == "names":
        result.update(permno="0010001", permco="0020001", secinfostartdt="2000-01-01",
                      secinfoenddt="2025-12-31", securitybegdt="1925-01-01",
                      securityenddt="2025-12-31", issuernm="Private invented corporation",
                      ticker="PRIVATETICKER", siccd="0123")
    else:
        result.update(gvkey="000001", liid="01", lpermno="0010001", lpermco="0020001",
                      linkdt="2000-01-01", linkenddt="2025-12-31", linktype="LC", linkprim="P",
                      cik="0000123456", conm="Private invented corporation", tic="PRIVATETICKER")
    result.update(changes)
    return result


def source(repo, records, *, role="names", header=None, compressed=False):
    header = list(metadata.SCHEMAS[role]) if header is None else header
    content = io.StringIO(newline="")
    writer = csv.writer(content)
    writer.writerow(header)
    for record in records:
        writer.writerow([record.get(field.lower(), "private extra value") for field in header])
    data = content.getvalue().encode()
    path = repo / "invented-download.bin"
    path.write_bytes(gzip.compress(data, mtime=0) if compressed else data)
    return path


def inventory(repo, path, *, role="names", sql=None):
    return metadata.inventory_metadata(path, role=role, request_start="2009-10-07",
                                       request_end="2022-02-02", output=repo / "data" / "inventory",
                                       config=load_protocol(), repo_root=repo, sql_source=sql)


@pytest.mark.parametrize("role,compressed", [("names", False), ("names", True), ("ccm", True)])
def test_preserves_bytes_case_order_modern_metadata_and_private_receipt(repo, role, compressed):
    header = [field.upper() for field in reversed(metadata.SCHEMAS[role])]
    if role == "ccm":
        header.extend(["EXTRA_CONTACT", "EXTRA_BUSINESS_DESCRIPTION"])
    path = source(repo, [row(role)], role=role, header=header, compressed=compressed)
    result = inventory(repo, path, role=role)
    saved = repo / "data" / "inventory" / result["source"]["preserved_file"]
    assert saved.read_bytes() == path.read_bytes()
    assert result["source"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["source"]["observed_header"] == header
    assert result["definite_requested_overlap"]["rows"] == 1
    assert result["source"]["source_release"] is None
    assert result["model_ready"] is False and result["source_approvals"] == 0
    assert result["prior_arithmetic_review_modified"] is False
    serialized = json.dumps(result)
    assert "PRIVATETICKER" not in serialized and "Private invented corporation" not in serialized
    assert "0000123456" not in serialized and "private extra value" not in serialized
    assert saved.stat().st_mode & 0o222 == 0
    assert json.loads((saved.parent / "receipt.json").read_text()) == result
    assert not list(saved.parent.glob("metadata-inventory-*"))


def test_all_bounds_preserved_and_open_invalid_reversed_are_unresolved(repo):
    records = [row("ccm", linkdt="B", linkenddt="E"),
               row("ccm", linkdt="", linkenddt="E"),
               row("ccm", linkdt="2009-02-30", linkenddt="other text"),
               row("ccm", linkdt="2021-12-31", linkenddt="2000-01-01"),
               row("ccm", linkdt="1925-01-01", linkenddt="1950-01-01"),
               row("ccm", linkdt="2023-01-01", linkenddt="2025-01-01"), row("ccm")]
    path = source(repo, records, role="ccm")
    result = inventory(repo, path, role="ccm")
    assert result["date_bounds"]["linkdt"]["literal_B"] == 1
    assert result["date_bounds"]["linkdt"]["blank"] == 1
    assert result["date_bounds"]["linkdt"]["other_or_invalid"] == 1
    assert result["date_bounds"]["linkenddt"]["literal_E"] == 2
    assert result["interval_classifications"]["linkdt/linkenddt"] == {
        "finite_requested_overlap": 1, "finite_before_request": 1, "finite_after_request": 1,
        "reversed_finite_bounds": 1, "unresolved_nonfinite_bounds": 3}
    assert result["all_rows"]["rows"] == 7
    assert result["definite_requested_overlap"]["rows"] == 1
    assert result["interval_overlap_candidates"]["rows_with_unresolved_or_reversed_bounds"] == 4
    assert result["rows_dropped"] == result["values_normalized"] == result["values_filled"] == 0


def test_full_row_duplicates_historical_key_conflicts_and_interval_candidates_separate(repo):
    records = [row(secinfoenddt="2010-12-31"), row(secinfoenddt="2010-12-31"),
               row(secinfoenddt="2010-12-31", siccd="5678"),
               row(secinfostartdt="2010-12-31", secinfoenddt="2015-12-31"),
               row(secinfostartdt="2016-01-01", secinfoenddt="2025-12-31")]
    result = inventory(repo, source(repo, records))
    counts = result["all_rows"]
    assert counts["rows"] == 5 and counts["distinct_full_rows"] == 4
    assert counts["exact_full_duplicate_row_excess"] == 1
    assert counts["historical_keys_with_conflicting_full_rows"] == 1
    assert counts["duplicate_historical_keys"] == 1
    overlap = result["interval_overlap_candidates"]
    assert overlap["distinct_finite_intervals"] == 3
    assert overlap["finite_intervals_overlapping_an_earlier_distinct_interval"] == 1
    assert overlap["groups_with_finite_overlap_candidates"] == 1
    assert overlap["finite_intervals_with_multiple_distinct_full_rows"] == 1
    assert overlap["overlap_candidates_resolved"] is False


def test_ccm_group_detects_competing_permno_intervals_but_not_approved_identity(repo):
    records = [row("ccm"), row("ccm", lpermno="0020002", linkdt="2005-01-01")]
    result = inventory(repo, source(repo, records, role="ccm"), role="ccm")
    assert result["all_rows"]["distinct_historical_keys"] == 2
    assert result["interval_overlap_candidates"]["groups_with_finite_overlap_candidates"] == 1
    assert result["interval_overlap_group_fields"] == ["gvkey", "liid"]


def test_identical_ccm_bounds_on_competing_securities_still_require_review(repo):
    records = [row("ccm"), row("ccm", lpermno="0020002")]
    result = inventory(repo, source(repo, records, role="ccm"), role="ccm")
    overlap = result["interval_overlap_candidates"]
    assert overlap["distinct_finite_intervals"] == 1
    assert overlap["groups_with_multiple_full_rows_on_identical_finite_bounds"] == 1
    assert overlap["groups_with_any_finite_interval_ambiguity"] == 1
    assert overlap["overlap_candidates_resolved"] is False


@pytest.mark.parametrize("header", [list(metadata.NAMES_FIELDS)[:-1],
                                    [*metadata.NAMES_FIELDS, "PERMNO"],
                                    [*metadata.NAMES_FIELDS, "extra"]])
def test_names_missing_ambiguous_or_extra_headers_fail(repo, header):
    path = source(repo, [row()], header=header)
    with pytest.raises(ValueError, match="fields|headers|schema"):
        inventory(repo, path)


def test_ccm_extra_fields_participate_in_full_row_equality(repo):
    path = source(repo, [row("ccm", extra="one"), row("ccm", extra="two")], role="ccm",
                  header=[*metadata.CCM_FIELDS, "extra"])
    counts = inventory(repo, path, role="ccm")["all_rows"]
    assert counts["exact_full_duplicate_row_excess"] == 0
    assert counts["historical_keys_with_conflicting_full_rows"] == 1


def test_known_names_sql_preserved_hashed_and_syntactically_recognized_only(repo):
    sql = repo / "supplied.sql"
    query = "SELECT " + ",\n".join("crsp_a_stock.wrds_names_query." + field
                                     for field in metadata.NAMES_FIELDS)
    query += " FROM crsp_a_stock.wrds_names_query WHERE 1 = 1;\n"
    sql.write_text(query)
    result = inventory(repo, source(repo, [row()]), sql=sql)
    evidence = result["sql"]
    assert (repo / "data" / "inventory" / "query.sql").read_bytes() == sql.read_bytes()
    assert evidence["sha256"] == hashlib.sha256(sql.read_bytes()).hexdigest()
    assert evidence["analysis"]["status"] == "recognized_restricted_select"
    assert evidence["analysis"]["syntactic_scope"] == "unrestricted_single_source_select"
    assert evidence["analysis"]["vendor_execution_verified"] is False
    assert evidence["analysis"]["source_completeness_verified"] is False
    assert query not in json.dumps(result)


@pytest.mark.parametrize("suffix", ["WHERE permno IN ('SECRET_IDENTIFIER')", "WHERE 1=1 LIMIT 1",
                                    "INNER JOIN other_table ON 1=1", "WHERE 1=1; DROP TABLE ignored",
                                    "WHERE 1=1 -- https://example.invalid/session-secret"])
def test_unknown_sql_scope_never_blocks_bytes_or_echoes_literals(repo, suffix):
    sql = repo / "supplied.sql"
    query = "SELECT " + ",".join(metadata.NAMES_FIELDS) + " FROM crsp_a_stock.wrds_names_query " + suffix
    sql.write_text(query)
    result = inventory(repo, source(repo, [row()]), sql=sql)
    assert result["sql"]["analysis"]["status"] == "unsupported"
    assert result["all_rows"]["rows"] == 1
    assert (repo / "data" / "inventory" / "query.sql").read_text() == query
    serialized = json.dumps(result)
    assert "SECRET_IDENTIFIER" not in serialized and "session-secret" not in serialized


@pytest.mark.parametrize("sql", [None, "not-downloaded.sql"])
def test_absent_or_missing_sql_does_not_block_preservation(repo, sql):
    result = inventory(repo, source(repo, [row()]), sql=None if sql is None else repo / sql)
    assert result["sql"]["sha256"] is None
    assert result["source"]["vendor_execution_verified"] is False
    assert result["all_rows"]["rows"] == 1


def test_sql_projection_mismatch_and_unknown_identity_are_unsupported():
    for query in ["SELECT * FROM crsp_a_stock.wrds_names_query WHERE 1=1",
                  "SELECT permno FROM crsp_a_stock.wrds_names_query WHERE 1=1",
                  "SELECT " + ",".join(metadata.NAMES_FIELDS) + " FROM unknown.private_source WHERE 1=1"]:
        analysis = metadata.analyze_metadata_sql(query, "names", list(metadata.NAMES_FIELDS))
        assert analysis["status"] == "unsupported"
        assert analysis["source_identifier_from_sql"] is None


def test_sql_ordering_and_no_where_supported_without_execution():
    query = "SELECT " + ",".join(metadata.NAMES_FIELDS) + " FROM crsp_a_stock.wrds_names_query ORDER BY permno,secinfostartdt DESC"
    analysis = metadata.analyze_metadata_sql(query, "names", list(metadata.NAMES_FIELDS))
    assert analysis["status"] == "recognized_restricted_select"
    assert analysis["sql_executed"] is False


def test_oversized_sql_preserved_without_unbounded_analysis(repo):
    sql = repo / "supplied.sql"
    sql.write_bytes(b"x" * (metadata._MAX_SQL_BYTES + 1))
    result = inventory(repo, source(repo, [row()]), sql=sql)
    assert result["sql"]["bytes"] == metadata._MAX_SQL_BYTES + 1
    assert result["sql"]["analysis"]["reason"] == "oversized_sql_preserved_without_analysis"


def test_locked_protocol_and_private_output_are_enforced_before_source_read(repo):
    config = {**load_protocol(), "seed": 1}
    with pytest.raises(ValueError, match="Protocol has changed"):
        metadata.inventory_metadata(repo / "does-not-exist", role="names", request_start="2009-10-07",
                                    request_end="2022-02-02", output=repo / "data" / "inventory",
                                    config=config, repo_root=repo)
    with pytest.raises(ValueError, match="private directory"):
        metadata.inventory_metadata(repo / "does-not-exist", role="names", request_start="2009-10-07",
                                    request_end="2022-02-02", output=repo / "reports" / "inventory",
                                    config=load_protocol(), repo_root=repo)


def test_source_snapshot_mutation_is_detected(repo, monkeypatch):
    path = source(repo, [row()])
    original = metadata._metadata_rows

    @metadata.contextmanager
    def mutate(snapshot, role):
        with original(snapshot, role) as content:
            yield content
        snapshot.chmod(0o600)
        snapshot.write_bytes(snapshot.read_bytes() + b"\n")

    monkeypatch.setattr(metadata, "_metadata_rows", mutate)
    with pytest.raises(ValueError, match="snapshot changed"):
        inventory(repo, path)
    assert not (repo / "data" / "inventory" / "receipt.json").exists()


def test_batch_boundary_and_output_overwrite(repo, monkeypatch):
    monkeypatch.setattr(metadata, "_BATCH", 2)
    monkeypatch.setattr(metadata, "_MAX_BATCH_BYTES", 1)
    path = source(repo, [row()] * 5)
    result = inventory(repo, path)
    assert result["all_rows"]["exact_full_duplicate_row_excess"] == 4
    with pytest.raises(ValueError, match="output exists"):
        inventory(repo, path)


def test_cli_help_offline(capsys):
    main = runpy.run_path(str(Path("scripts/wrds_manual_metadata.py")))["main"]
    with pytest.raises(SystemExit) as code:
        main(["inventory", "--help"])
    assert code.value.code == 0
    text = capsys.readouterr().out
    assert "--role" in text and "--sql" in text and "--request-start" in text
