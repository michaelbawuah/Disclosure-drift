import json

import duckdb
import numpy as np
import pandas as pd
import pytest

from disclosure_research.cli import main
from disclosure_research.labels import prepare_labels
from disclosure_research.market_data import (
    NORMALIZED, import_market, load_market, sha256, validate_tables,
)
from disclosure_research.market_demo import write_fixture
from disclosure_research.protocol import load_protocol


@pytest.fixture
def inputs(tmp_path):
    manifest, events = write_fixture(tmp_path / "source")
    return manifest, events, tmp_path / "bundle", load_protocol()


def edit_table(manifest_path, name, edit):
    manifest = json.loads(manifest_path.read_text())
    path = manifest_path.parent / manifest["tables"][name]["path"]
    frame = edit(pd.read_parquet(path))
    frame.to_parquet(path, index=False)
    manifest["tables"][name]["sha256"] = sha256(path.read_bytes())
    manifest_path.write_text(json.dumps(manifest))


def test_import_preserves_inputs_and_builds_queryable_tables(inputs):
    manifest, _, bundle, config = inputs
    before = manifest.read_bytes()
    receipt = import_market(manifest, bundle, config)
    frames, reloaded = load_market(bundle, config)
    assert reloaded == receipt and manifest.read_bytes() == before
    with duckdb.connect(str(bundle / "market.duckdb"), read_only=True) as con:
        assert con.sql("SELECT count(*) FROM daily_returns").fetchone()[0] == len(frames["daily_returns"])
    assert receipt["last_permitted_return_session"].startswith("2022-")


@pytest.mark.parametrize("case,pattern", [
    ("duplicate", "duplicate"), ("missing", "missing"), ("below_minus_one", "at least -1"),
    ("infinite", "finite"), ("weekend", "non-XNYS"), ("timestamp", "ISO dates"),
    ("holdout_returns", "holdout blocked"), ("numeric_id", "never coerced"),
    ("string_terminal", "boolean"), ("post_terminal", "post-terminal"),
])
def test_bad_return_inputs_fail_before_output_is_published(inputs, case, pattern):
    manifest, _, bundle, config = inputs

    def mutate(frame):
        if case == "duplicate":
            return pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
        column, value = {
            "missing": ("total_return", np.nan), "below_minus_one": ("total_return", -1.01),
            "infinite": ("total_return", np.inf), "weekend": ("session", "2021-07-10"),
            "timestamp": ("session", "2021-07-07T00:00:00"),
            "holdout_returns": ("session", "2022-12-01"),
            "numeric_id": ("security_id", 123), "string_terminal": ("terminal_event", "False"),
            "post_terminal": ("terminal_event", True),
        }[case]
        if case == "numeric_id":
            frame[column] = 123
        elif case == "string_terminal":
            frame[column] = "False"
        else:
            frame.loc[0, column] = value
        return frame

    edit_table(manifest, "daily_returns", mutate)
    with pytest.raises(ValueError, match=pattern):
        import_market(manifest, bundle, config)
    assert not bundle.exists()


def test_numeric_boolean_returns_are_not_accepted_as_financial_values(inputs):
    manifest, _, bundle, config = inputs
    edit_table(manifest, "market_returns", lambda f: f.assign(total_return=True))
    with pytest.raises(ValueError, match="numeric"):
        import_market(manifest, bundle, config)


@pytest.mark.parametrize("case", ["same_id_overlap", "multiple_classes", "multiple_issuers"])
def test_ambiguous_or_duplicate_historical_links_are_rejected(inputs, case):
    manifest, _, bundle, config = inputs

    def mutate(frame):
        extra = frame.iloc[[0]].copy()
        if case == "multiple_classes":
            extra["security_id"] = "other-class"
        elif case == "multiple_issuers":
            extra["cik"] = "0000000999"
        return pd.concat([frame, extra], ignore_index=True)

    edit_table(manifest, "security_links", mutate)
    with pytest.raises(ValueError, match="Overlapping historical links"):
        import_market(manifest, bundle, config)


def test_adjacent_link_intervals_are_inclusive_and_must_not_share_endpoint(inputs):
    manifest, _, bundle, config = inputs

    def adjacent(frame):
        extra = frame.iloc[[0]].copy()
        frame.loc[0, "valid_to"] = "2021-07-06"
        extra["valid_from"] = "2021-07-07"
        extra["security_id"] = "new-permanent-id"
        return pd.concat([frame, extra], ignore_index=True)

    edit_table(manifest, "security_links", adjacent)
    import_market(manifest, bundle, config)
    frames, _ = load_market(bundle, config)
    frames["security_links"].loc[0, "valid_to"] = "2021-07-07"
    with pytest.raises(ValueError, match="Overlapping"):
        validate_tables(frames, config)


@pytest.mark.parametrize("case,pattern", [
    ("hash", "hash mismatch"), ("normalization", "normalization code"),
    ("field_mapping", "source field"), ("convention", "delisting"),
    ("benchmark", "value-weighted"), ("outside_path", "inside the manifest"),
])
def test_provenance_is_required_before_import(inputs, case, pattern):
    manifest, _, bundle, config = inputs
    document = json.loads(manifest.read_text())
    if case == "hash":
        document["tables"]["daily_returns"]["sha256"] = "0" * 64
    elif case == "normalization":
        document["normalization_code_sha256"] = "pending"
    elif case == "field_mapping":
        document["tables"]["daily_returns"]["field_mapping"].pop("terminal_event")
    elif case == "convention":
        document["stock_return_convention"] = "unknown_vendor_format"
    elif case == "benchmark":
        document["benchmark_convention"] = "price_only_index"
    else:
        document["tables"]["daily_returns"]["path"] = "../unrelated.parquet"
    manifest.write_text(json.dumps(document))
    with pytest.raises(ValueError, match=pattern):
        import_market(manifest, bundle, config)
    assert not bundle.exists()


@pytest.mark.parametrize("which", ["table", "receipt", "manifest"])
def test_changed_import_cannot_be_used_for_labels(inputs, which):
    manifest, events, bundle, config = inputs
    import_market(manifest, bundle, config)
    path = bundle / {"table": "daily_returns.parquet", "receipt": "import_receipt.json",
                     "manifest": "source_manifest.json"}[which]
    if which == "receipt":
        value = json.loads(path.read_text())
        value["data_kind"] = NORMALIZED
        path.write_text(json.dumps(value))
    else:
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="changed"):
        prepare_labels(events, bundle, bundle.parent / "labels", config)


def test_label_staging_handles_delisting_and_keeps_missing_record_out(inputs):
    manifest, events, bundle, config = inputs
    import_market(manifest, bundle, config)
    output = bundle.parent / "labels"
    summary = prepare_labels(events, bundle, output, config)
    result = pd.read_parquet(output / "event_labels.parquet").set_index("event_id")
    assert summary["labels_prepared"] == 2 and summary["events_excluded"] == 1
    assert not summary["model_ready"] and not summary["final_period_opened"]
    continuing = result.loc["SYNTHETIC-EVENT-continuing"]
    assert continuing.reference_session == "2021-07-07"
    assert continuing.horizon_sessions == 20
    assert continuing.target == pytest.approx(1.01 ** 20 - 1.002 ** 20)
    assert result.loc["SYNTHETIC-EVENT-delisted", "target"] == pytest.approx(1.01 ** 2 * 0.5 - 1.002 ** 20)
    assert pd.isna(result.loc["SYNTHETIC-EVENT-missing_session", "target"])


def test_missing_benchmark_is_never_filled(inputs):
    manifest, events, bundle, config = inputs
    edit_table(manifest, "market_returns", lambda f: f.drop(index=2))
    import_market(manifest, bundle, config)
    summary = prepare_labels(events, bundle, bundle.parent / "labels", config)
    assert summary["labels_prepared"] == 0
    assert all(reason.startswith("Missing benchmark") for reason in summary["exclusion_reasons"])


def test_missing_historical_identity_is_an_explicit_exclusion(inputs):
    manifest, events, bundle, config = inputs
    edit_table(manifest, "security_links", lambda f: f.assign(valid_to="2021-07-06"))
    import_market(manifest, bundle, config)
    summary = prepare_labels(events, bundle, bundle.parent / "labels", config)
    assert summary["events_excluded"] == 3
    assert all("identity is missing" in reason for reason in summary["exclusion_reasons"])


def test_final_period_event_rejected_before_market_bundle_is_opened(inputs):
    _, events, bundle, config = inputs
    frame = pd.read_parquet(events)
    frame.loc[0, "acceptance_timestamp"] = "2022-01-03T12:00:00-05:00"
    frame.to_parquet(events, index=False)
    with pytest.raises(ValueError, match="holdout events are blocked"):
        prepare_labels(events, bundle, bundle.parent / "labels", config)
    assert not bundle.exists()


def test_synthetic_returns_cannot_be_joined_to_real_filing_events(inputs):
    manifest, events, bundle, config = inputs
    import_market(manifest, bundle, config)
    pd.read_parquet(events).assign(data_kind="REAL_FILING_EVENTS").to_parquet(events, index=False)
    with pytest.raises(ValueError, match="must never be mixed"):
        prepare_labels(events, bundle, bundle.parent / "labels", config)


def test_existing_import_is_preserved(inputs):
    manifest, _, bundle, config = inputs
    original = import_market(manifest, bundle, config)
    with pytest.raises(ValueError, match="already exists"):
        import_market(manifest, bundle, config)
    assert json.loads((bundle / "import_receipt.json").read_text()) == original


def test_market_demo_cli_checks_independent_arithmetic(tmp_path):
    assert main(["market-demo", "--output", str(tmp_path)]) == 0
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["independent_arithmetic_check"] == "passed"
    assert summary["data_kind"] == "SYNTHETIC_ENGINEERING_FIXTURE"
