import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from disclosure_research.dataset import EMPIRICAL, build_dataset, load_dataset, run_synthetic_dataset_demo
from disclosure_research.market_data import SYNTHETIC, fingerprint, sha256
from disclosure_research.protocol import load_protocol


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("historical-dataset") / "demo"
    run_synthetic_dataset_demo(root, load_protocol())
    return root


def source_copy(demo, tmp_path, partition="development"):
    source = tmp_path / "source"
    shutil.copytree(demo / f"{partition}-source", source)
    return source / "manifest.json"


def update_manifest(path, update):
    source = json.loads(path.read_bytes())
    update(source)
    path.write_text(json.dumps(source))


def rebind_source(path, table=None, modify=None):
    """Refresh fixture hashes to isolate downstream validation failure cases."""
    source = json.loads(path.read_bytes())
    if table:
        location = path.parent / source["tables"][table]["path"]
        frame = pd.read_parquet(location)
        frame = modify(frame)
        frame.to_parquet(location, index=False)
        source["tables"][table]["sha256"] = sha256(location.read_bytes())
    evidence = [json.loads(line) for line in (path.parent / "evidence.jsonl").read_text().splitlines()]
    for row in evidence:
        row["source_tables"] = {name: source["tables"][name]["sha256"] for name in row["source_tables"]}
    lookup = {row["evidence_id"]: row for row in evidence}
    reviews = [json.loads(line) for line in (path.parent / "reviews.jsonl").read_text().splitlines()]
    for row in reviews:
        row["evidence_sha256"] = fingerprint(lookup[row["evidence_id"]])
    for name, records in (("evidence", evidence), ("reviews", reviews)):
        location = path.parent / f"{name}.jsonl"
        location.write_text("".join(json.dumps(row) + "\n" for row in records))
        source[name]["sha256"] = sha256(location.read_bytes())
    path.write_text(json.dumps(source))


def edit_reviews(path, modify):
    location = path.parent / "reviews.jsonl"
    reviews = [json.loads(line) for line in location.read_text().splitlines()]
    location.write_text("".join(json.dumps(row) + "\n" for row in modify(reviews)))
    update_manifest(path, lambda source: source["reviews"].update(sha256=sha256(location.read_bytes())))


def test_complete_synthetic_builder_separates_partitions_and_never_claims_empirical_readiness(demo):
    development, receipt = load_dataset(demo / "development", load_protocol())
    holdout, final_receipt = load_dataset(demo / "holdout", load_protocol(), "holdout")
    assert len(development) == 144 and len(holdout) == 48
    assert development.acceptance_date.str[:4].max() == "2021"
    assert holdout.acceptance_date.str[:4].min() == "2022"
    assert set(development.observation_id).isdisjoint(holdout.observation_id)
    for manifest in (receipt, final_receipt):
        assert manifest["data_kind"] == SYNTHETIC
        assert manifest["model_ready"] is False
        assert manifest["human_reviews"] == 0
        assert manifest["synthetic_fixture_validated"] is True
    features = pd.read_parquet(demo / "holdout" / "features.parquet")
    assert not {"target", "stock_return", "market_return"} & set(features.columns)
    assert set(pd.read_parquet(demo / "holdout" / "targets.parquet").columns) == {"observation_id", "target"}


def test_duplicate_join_keys_are_not_silently_multiplied(demo, tmp_path):
    source = source_copy(demo, tmp_path)
    rebind_source(source, "labels", lambda frame: pd.concat([frame, frame.iloc[:1]], ignore_index=True))
    with pytest.raises(ValueError, match="one-to-one"):
        build_dataset(source, tmp_path / "result", load_protocol())


def test_orphan_labels_are_rejected(demo, tmp_path):
    source = source_copy(demo, tmp_path)

    def change(frame):
        frame.loc[0, "observation_id"] = "unpaired-event"
        return frame

    rebind_source(source, "labels", change)
    with pytest.raises(ValueError, match="orphan"):
        build_dataset(source, tmp_path / "result", load_protocol())


def test_missing_control_is_explicit_unresolved_exclusion(demo, tmp_path):
    source = source_copy(demo, tmp_path)
    rebind_source(source, "controls", lambda frame: frame.iloc[1:])
    summary = build_dataset(source, tmp_path / "result", load_protocol())
    ledger = pd.read_parquet(tmp_path / "result" / "exclusions.parquet")
    assert summary["observations"] == 143
    assert summary["unresolved_events"] == 1
    assert ledger.reason.tolist() == ["missing_label_or_control_record"]
    with pytest.raises(ValueError, match="staging-only"):
        load_dataset(tmp_path / "result", load_protocol())


def test_holdout_dates_are_rejected_before_any_outcome_file_read(demo, tmp_path, monkeypatch):
    source = source_copy(demo, tmp_path, "holdout")
    update_manifest(source, lambda manifest: manifest.update(partition="development"))
    original = Path.read_bytes

    def fail_on_outcome(path):
        if path.name == "labels.parquet":
            pytest.fail("Outcome file read before acceptance-partition guard")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", fail_on_outcome)
    with pytest.raises(ValueError, match="mixing blocked"):
        build_dataset(source, tmp_path / "result", load_protocol())


def test_empirical_holdout_requires_gate_before_outcome_read(demo, tmp_path, monkeypatch):
    source = source_copy(demo, tmp_path, "holdout")
    update_manifest(source, lambda manifest: manifest.update(data_kind=EMPIRICAL))
    original = Path.read_bytes

    def fail_on_outcome(path):
        if path.name == "labels.parquet":
            pytest.fail("Empirical holdout outcome read without prerequisites")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", fail_on_outcome)
    with pytest.raises(ValueError, match="blocked"):
        build_dataset(source, tmp_path / "result", load_protocol(), "holdout")


def test_metadata_only_load_does_not_read_target_bytes(demo, monkeypatch):
    original = Path.read_bytes

    def fail_on_outcome(path):
        if path.name == "targets.parquet":
            pytest.fail("Metadata-only gate touched heldout targets")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", fail_on_outcome)
    features, _ = load_dataset(demo / "holdout", load_protocol(), "holdout", features_only=True)
    assert len(features) == 48 and "target" not in features


def test_failed_prepared_audit_gate_does_not_read_target_bytes(demo, tmp_path, monkeypatch):
    source = source_copy(demo, tmp_path, "holdout")

    def remove_one(rows):
        identity = next(row["evidence_id"] for row in rows if row["evidence_id"].startswith("fixture-label-"))
        return [row for row in rows if row["evidence_id"] != identity]

    edit_reviews(source, remove_one)
    build_dataset(source, tmp_path / "staging", load_protocol(), "holdout")
    original = Path.read_bytes

    def fail_on_outcome(path):
        if path.name == "targets.parquet":
            pytest.fail("Prepared audit gate failed after touching heldout targets")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", fail_on_outcome)
    with pytest.raises(ValueError, match="staging-only"):
        load_dataset(tmp_path / "staging", load_protocol(), "holdout")


def test_assistant_reviews_and_booleans_cannot_approve_empirical_data(demo, tmp_path):
    source = source_copy(demo, tmp_path)
    update_manifest(source, lambda manifest: manifest.update(data_kind=EMPIRICAL, model_ready=True, human_approved=True))
    summary = build_dataset(source, tmp_path / "result", load_protocol())
    assert summary["data_kind"] == EMPIRICAL
    assert summary["model_ready"] is False
    assert summary["approval_status"] == "pending"
    assert summary["observations"] == 0
    assert summary["unresolved_events"] == 144
    ledger = pd.read_parquet(tmp_path / "result" / "exclusions.parquet")
    assert ledger.reason.str.contains("requires_human").all()


def test_failed_review_remains_unresolved_while_explicit_exclusion_is_resolved(demo, tmp_path):
    source = source_copy(demo, tmp_path)

    def fail_one(rows):
        label = next(row for row in rows if row["evidence_id"].startswith("fixture-label-"))
        label["verdict"] = "fail"
        return rows

    edit_reviews(source, fail_one)
    result = build_dataset(source, tmp_path / "failed", load_protocol())
    assert result["unresolved_events"] == 1
    assert result["synthetic_fixture_validated"] is False

    def exclude_one(rows):
        for row in rows:
            if row["verdict"] == "fail":
                row["verdict"] = "exclude"
                row["notes"] = "Explicit synthetic fixture exclusion for this unit test."
        return rows

    edit_reviews(source, exclude_one)
    result = build_dataset(source, tmp_path / "excluded", load_protocol())
    assert result["unresolved_events"] == 0
    assert result["synthetic_fixture_validated"] is True


def test_stale_review_fingerprint_is_rejected(demo, tmp_path):
    source = source_copy(demo, tmp_path)

    def stale(rows):
        rows[0]["evidence_sha256"] = "0" * 64
        return rows

    edit_reviews(source, stale)
    with pytest.raises(ValueError, match="Stale review"):
        build_dataset(source, tmp_path / "result", load_protocol())


def test_completed_review_cannot_be_dated_in_the_future(demo, tmp_path):
    source = source_copy(demo, tmp_path)

    def future(rows):
        rows[0]["reviewed_at"] = "2099-01-01T00:00:00Z"
        return rows

    edit_reviews(source, future)
    with pytest.raises(ValueError, match="future timestamps"):
        build_dataset(source, tmp_path / "result", load_protocol())


@pytest.mark.parametrize("table,column,value,reason", [
    ("pairs", "previous_cik", "0000000999", "Cross-issuer"),
    ("pairs", "previous_form", "10-K/A", "original 10-K"),
    ("pairs", "current_text", "", "current_text"),
    ("controls", "control_history_sessions", 59, "exactly the prior 60"),
    ("labels", "target", 123.0, "matched market"),
    ("labels", "security_id", "WRONG-CLASS", "share class"),
])
def test_invalid_event_has_one_exclusion_and_cannot_become_ready(demo, tmp_path, table, column, value, reason):
    source = source_copy(demo, tmp_path)

    def mutate(frame):
        frame.loc[0, column] = value
        return frame

    rebind_source(source, table, mutate)
    result = build_dataset(source, tmp_path / "result", load_protocol())
    exclusions = pd.read_parquet(tmp_path / "result" / "exclusions.parquet")
    assert result["observations"] == 143 and result["exclusions"] == 1
    assert result["synthetic_fixture_validated"] is False
    assert reason in exclusions.reason.iloc[0]


def test_selection_security_identity_must_cover_the_filing_event(demo, tmp_path):
    source = source_copy(demo, tmp_path)

    def mutate(frame):
        row = frame.loc[0].to_dict()
        row["identity_valid_to"] = f"{int(row['universe_year'])}-01-10"
        from disclosure_research.universe import MEMBERSHIP_COLUMNS
        row["universe_membership_id"] = fingerprint({key: row[key] for key in MEMBERSHIP_COLUMNS if key != "universe_membership_id"})
        for key, value in row.items():
            frame.loc[0, key] = value
        return frame

    rebind_source(source, "universe", mutate)
    # This deliberately leaves the old audited subject: a changed membership
    # cannot reuse the approval of its earlier historical identity interval.
    result = build_dataset(source, tmp_path / "result", load_protocol())
    exclusions = pd.read_parquet(tmp_path / "result" / "exclusions.parquet")
    assert result["unresolved_events"] == 1
    assert exclusions.reason.str.contains("invalid_universe_evidence_scope").any()


def test_changed_audit_artifact_is_detected(demo, tmp_path):
    source = source_copy(demo, tmp_path)
    (source.parent / "synthetic-source-notes.txt").write_text("Changed audit source")
    with pytest.raises(ValueError, match="Hash mismatch"):
        build_dataset(source, tmp_path / "result", load_protocol())


def test_hash_bound_built_table_tamper_is_detected(demo, tmp_path):
    shutil.copytree(demo / "development", tmp_path / "bundle")
    path = tmp_path / "bundle" / "dataset.parquet"
    frame = pd.read_parquet(path)
    frame.loc[0, "target"] += 1
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="Hash mismatch"):
        load_dataset(tmp_path / "bundle", load_protocol())


def test_existing_output_is_preserved(demo, tmp_path):
    with pytest.raises(ValueError, match="exists"):
        build_dataset(demo / "development-source" / "manifest.json", demo / "development", load_protocol())
