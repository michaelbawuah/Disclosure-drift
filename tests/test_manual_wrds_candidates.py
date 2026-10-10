import copy
import hashlib
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from disclosure_research import manual_wrds_candidates as candidates
from disclosure_research.manual_wrds_intake import DAILY_FIELDS
from disclosure_research.market_data import development_return_end
from disclosure_research.protocol import canonical_hash, load_protocol, write_lock


@pytest.fixture
def config():
    return load_protocol()


def _raw(record=2, **changes):
    row = dict(zip(DAILY_FIELDS, ["101", "201", "ABCD1234", "TEST", "2020-01-02",
                                 "20", "100", "TR", ".01", "NA", "N", "500", ".002"],
                   strict=True))
    row.update(source_sha256="a" * 64, source_inventory_sha256="b" * 64,
               source_csv_record=record, in_requested_window=True)
    row.update(changes)
    return row


def _write_part(path, rows):
    schema = pa.schema([(name, pa.string()) for name in DAILY_FIELDS] + [
        ("source_sha256", pa.string()), ("source_inventory_sha256", pa.string()),
        ("source_csv_record", pa.int64()), ("in_requested_window", pa.bool_())])
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)
    return {"file": "projections/" + path.name, "rows": len(rows),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


def _bundle(tmp_path, config, groups, *, reconciled=True):
    (tmp_path / "configs").mkdir(exist_ok=True)
    write_lock(config, tmp_path / "configs" / "protocol.lock.json")
    stage = tmp_path / "data" / "stage"
    (stage / "projections").mkdir(parents=True)
    parts, sources = [], {}
    requested = 0
    for index, rows in enumerate(groups, start=1):
        parts.append(_write_part(stage / "projections" / f"part-{index:06d}.parquet", rows))
        for row in rows:
            pair = row["source_sha256"], row["source_inventory_sha256"]
            sources[pair] = sources.get(pair, 0) + 1
            requested += int(row["in_requested_window"])
    manifest = {
        "schema_version": 1, "status": candidates.STAGE_STATUS,
        "protocol_sha256": canonical_hash(config),
        "model_ready": False, "source_approvals": 0, "final_period_opened": False,
        "request": {"start": "2020-01-02", "end": "2020-01-03",
                    "last_permitted_development_return_date": development_return_end(config)},
        "projection": {"fields": list(DAILY_FIELDS), "provenance_fields": list(candidates.PROVENANCE),
                       "all_source_records_preserved": True, "duplicate_rows_retained": True,
                       "duplicate_comparison_scope": "required_13_fields_in_canonical_order",
                       "parts": parts, "rows": sum(sources.values()), "requested_rows": requested},
        "sources": [{"role": "daily", "source_sha256": pair[0],
                     "inventory_receipt_sha256": pair[1], "rows": rows}
                    for pair, rows in sources.items()],
        "reconciliation": {"requested_window_numerically_reconciled": reconciled},
    }
    _receipt(stage, manifest)
    return stage, manifest


def _receipt(stage, manifest):
    (stage / "receipt.json").write_text(json.dumps(manifest))


def _build(tmp_path, config, stage):
    return candidates.build_candidates(stage, output=tmp_path / "data" / "result",
                                       config=config, repo_root=tmp_path)


def _output_rows(tmp_path):
    rows = []
    for path in sorted((tmp_path / "data" / "result" / "candidates").glob("*.parquet")):
        rows.extend(pq.read_table(path).to_pylist())
    return rows


def test_candidates_collapse_projection_duplicates_keep_provenance_and_units(tmp_path, config):
    day3 = _raw(4, dlycaldt="2020-01-03", dlyvol="0", dlyprcflg="BA")
    early = _raw(5, dlycaldt="2019-12-31", in_requested_window=False)
    stage, _ = _bundle(tmp_path, config, [[_raw(), _raw(3), day3, early]])
    receipt = _build(tmp_path, config, stage)
    rows = _output_rows(tmp_path)
    assert len(rows) == 2
    assert rows[0]["total_return_candidate"] == .01
    assert rows[0]["market_cap_usd_candidate"] == 500_000
    assert rows[0]["closing_price_volume_usd_candidate"] == 2_000
    assert rows[1]["closing_price_volume_usd_candidate"] == 0
    assert rows[0]["projection_record_count"] == 2
    assert rows[0]["representative_source_csv_record"] == 2
    assert receipt["projection"]["equivalent_13_field_record_excess"] == 1
    assert receipt["coverage"]["outside_request_rows_retained_in_source_stage"] == 1
    assert receipt["model_ready"] is False
    assert receipt["source_approvals"] == 0
    assert receipt["prior_arithmetic_review_modified"] is False
    assert receipt["historical_availability_supplied"] is False
    assert receipt["approved_terminal_events_supplied"] is False
    assert "terminal_event" not in rows[0]
    assert (tmp_path / "data/result/source_stage_receipt.json").read_bytes() == (stage / "receipt.json").read_bytes()
    assert (tmp_path / "data/result").stat().st_mode & 0o777 == 0o700
    assert (tmp_path / "data/result/candidates").stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o400
               for path in (tmp_path / "data/result").rglob("*") if path.is_file())
    with pytest.raises(ValueError, match="exists"):
        _build(tmp_path, config, stage)


def test_all_conflicting_key_projections_are_preserved_but_withheld(tmp_path, config):
    stage, _ = _bundle(tmp_path, config, [[_raw(), _raw(3, ticker="CHANGED")]])
    receipt = _build(tmp_path, config, stage)
    rows = _output_rows(tmp_path)
    assert len(rows) == 2
    assert receipt["projection"]["conflicting_security_date_keys"] == 1
    assert all(row["total_return_candidate"] is None for row in rows)
    assert all(row["market_cap_usd_candidate"] is None for row in rows)
    assert all(row["closing_price_volume_usd_candidate"] is None for row in rows)
    assert all(row["return_status"] == "conflicting_security_date_projection" for row in rows)


def test_numeric_mv_and_delisting_are_not_ordinary_approved_events(tmp_path, config):
    stage, _ = _bundle(tmp_path, config, [[_raw(dlyretmissflg="MV"),
                                        _raw(3, dlycaldt="2020-01-03", dlydelflg="Y")]],
                       reconciled=False)
    receipt = _build(tmp_path, config, stage)
    ordinary, terminal = _output_rows(tmp_path)
    assert ordinary["total_return_candidate"] is None
    assert ordinary["return_missing_flag"] == "MV"
    assert ordinary["return_status"] == "unresolved_return_flag"
    assert terminal["total_return_candidate"] == .01
    assert terminal["delisting_status"] == "PAYOFF_AND_TERMINATION_REVIEW_REQUIRED"
    assert receipt["reconciliation"]["requested_window_numerically_reconciled"] is False


def test_date_preflight_visits_later_parts_before_any_numeric_conversion(tmp_path, config, monkeypatch):
    future = _raw(3, dlycaldt="2022-03-01", in_requested_window=False)
    stage, _ = _bundle(tmp_path, config, [[_raw(dlyret="NOT_A_NUMBER")], [future]])
    def forbidden(*args, **kwargs):
        raise AssertionError("Numeric conversion must not run before all dates pass")
    monkeypatch.setattr(candidates, "_number", forbidden)
    with pytest.raises(ValueError, match="holdout blocked"):
        _build(tmp_path, config, stage)
    assert not (tmp_path / "data/result").exists()


def test_hash_tampering_and_unsafe_part_paths_fail(tmp_path, config):
    stage, manifest = _bundle(tmp_path, config, [[_raw()]])
    part = stage / manifest["projection"]["parts"][0]["file"]
    original = part.read_bytes()
    part.write_bytes(original + b"tampered")
    with pytest.raises(ValueError, match="size or SHA-256"):
        _build(tmp_path, config, stage)
    part.write_bytes(original)
    manifest["projection"]["parts"][0]["file"] = "../escape.parquet"
    _receipt(stage, manifest)
    with pytest.raises(ValueError, match="safe relative"):
        _build(tmp_path, config, stage)


def test_protocol_lock_and_stage_approval_claim_cannot_be_bypassed(tmp_path, config):
    stage, manifest = _bundle(tmp_path, config, [[_raw()]])
    changed = copy.deepcopy(config)
    changed["version"] += "-changed"
    with pytest.raises(ValueError, match="Protocol has changed"):
        _build(tmp_path, changed, stage)
    manifest["model_ready"] = True
    _receipt(stage, manifest)
    with pytest.raises(ValueError, match="unapproved development"):
        _build(tmp_path, config, stage)


def test_repeated_source_record_is_not_disguised_as_duplicate_value(tmp_path, config):
    stage, _ = _bundle(tmp_path, config, [[_raw(), _raw()]])
    with pytest.raises(ValueError, match="record provenance is repeated"):
        _build(tmp_path, config, stage)


def test_window_flag_and_source_record_count_are_verified(tmp_path, config):
    stage, manifest = _bundle(tmp_path, config, [[_raw(in_requested_window=False)]])
    with pytest.raises(ValueError, match="flag contradicts"):
        _build(tmp_path, config, stage)
    manifest["projection"]["requested_rows"] = 500
    _receipt(stage, manifest)
    with pytest.raises(ValueError):
        _build(tmp_path, config, stage)


def test_mutation_after_date_pass_is_detected(tmp_path, config, monkeypatch):
    stage, manifest = _bundle(tmp_path, config, [[_raw()]])
    original = candidates._preflight
    def mutate(*args):
        result = original(*args)
        path = stage / manifest["projection"]["parts"][0]["file"]
        path.write_bytes(path.read_bytes() + b"changed")
        return result
    monkeypatch.setattr(candidates, "_preflight", mutate)
    with pytest.raises(ValueError, match="changed during"):
        _build(tmp_path, config, stage)
    assert not (tmp_path / "data/result").exists()


@pytest.mark.parametrize("updates,field,status", [
    ({"dlyret": "-1.000000000000000000000000000001"}, "return", "return_below_minus_one"),
    ({"dlyret": "1e-500"}, "return", "not_representable_as_finite_float"),
    ({"dlyret": "-1e-500"}, "return", "not_representable_as_finite_float"),
    ({"dlyprc": "-20"}, "liquidity", "nonpositive_ciz_price"),
    ({"dlyprcflg": "DA"}, "liquidity", "unsupported_liquidity_price_flag"),
    ({"dlyvol": "-1"}, "liquidity", "negative_volume"),
    ({"dlycap": "0"}, "capitalization", "nonpositive_capitalization"),
    ({"dlycap": "NaN"}, "capitalization", "unsupported_numeric_text"),
    ({"dlycap": "1e99999999"}, "capitalization", "numeric_exponent_outside_candidate_range"),
    ({"dlycap": "1e308"}, "capitalization", "not_representable_as_positive_finite_float"),
    ({"dlyvol": "1e-500", "dlyprc": "1e-500"}, "liquidity", "not_representable_as_nonnegative_finite_float"),
    ({"permno": "0"}, "return", "invalid_permanent_identifier"),
    ({"dlycaldt": "2020-01-04"}, "return", "not_an_exchange_session"),
])
def test_conservative_candidate_conventions(updates, field, status):
    raw = _raw(**updates)
    raw.update(record_count=1, source_file_count=1, variants=1, projection_sha256="c" * 64,
               representative={key: raw[key] for key in candidates.PROVENANCE[:3]})
    row = candidates._candidate(raw, {"2020-01-02", "2020-01-03"})
    assert row[field + "_status"] == status


def test_two_files_same_projection_have_one_candidate_and_complete_source_count(tmp_path, config):
    other = _raw(source_sha256="c" * 64, source_inventory_sha256="d" * 64)
    stage, _ = _bundle(tmp_path, config, [[other], [_raw()]])
    _build(tmp_path, config, stage)
    [row] = _output_rows(tmp_path)
    assert row["projection_record_count"] == 2
    assert row["projection_source_file_count"] == 2
    assert row["representative_source_sha256"] == "a" * 64
    assert row["representative_source_inventory_sha256"] == "b" * 64
    assert row["representative_source_csv_record"] == 2


def test_unknown_flag_text_stays_private_and_streamed_parts_remain_bound(tmp_path, config, monkeypatch):
    unusual = "UNRECOGNIZED_PRIVATE_FLAG_" + "x" * 5000
    stage, _ = _bundle(tmp_path, config, [[_raw(dlyretmissflg=unusual),
                                        _raw(3, dlycaldt="2020-01-03")]])
    monkeypatch.setattr(candidates, "_BATCH_BYTES", 32_768)
    monkeypatch.setattr(candidates, "_PART_ROWS", 1)
    receipt = _build(tmp_path, config, stage)
    assert receipt["processing"]["arrow_reader_batch_rows"] == 1
    assert len(receipt["projection"]["parts"]) == 2
    assert receipt["counts"]["return_missing_flag"] == {"NA": 1, "__UNRECOGNIZED__": 1}
    assert unusual not in json.dumps(receipt)
    assert _output_rows(tmp_path)[0]["return_missing_flag"] == unusual
    for part in receipt["projection"]["parts"]:
        path = tmp_path / "data/result" / part["file"]
        assert part["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert part["rows"] == pq.ParquetFile(path).metadata.num_rows


def test_duplicate_json_keys_are_rejected(tmp_path, config):
    stage, _ = _bundle(tmp_path, config, [[_raw()]])
    receipt = stage / "receipt.json"
    receipt.write_text('{"model_ready":true,' + receipt.read_text()[1:])
    with pytest.raises(ValueError, match="duplicate JSON keys"):
        _build(tmp_path, config, stage)


def test_single_oversized_record_refuses_before_numeric_conversion(tmp_path, config, monkeypatch):
    stage, _ = _bundle(tmp_path, config, [[_raw()]])
    monkeypatch.setattr(candidates, "_BATCH_BYTES", 1024)
    def forbidden(*args, **kwargs):
        raise AssertionError("Oversized row must fail before conversion")
    monkeypatch.setattr(candidates, "_number", forbidden)
    with pytest.raises(ValueError, match="row exceeds"):
        _build(tmp_path, config, stage)


def test_request_before_frozen_source_start_is_refused(tmp_path, config):
    stage, manifest = _bundle(tmp_path, config, [[_raw(dlycaldt="2009-07-10")]])
    manifest["request"].update(start="2009-07-10", end="2009-07-10")
    _receipt(stage, manifest)
    with pytest.raises(ValueError, match="locked development window"):
        _build(tmp_path, config, stage)
