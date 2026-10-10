"""Audited, hash-bound research tables with physically distinct study partitions.

Input is a version-1 JSON manifest with data_kind, partition, protocol_sha256,
normalization_notes, timezone-aware created_at and path/SHA-256 specifications
for four normalized Parquet ``tables``: pairs, labels, controls and universe.
Their required fields are the public ``TABLE_COLUMNS`` constant below. Original
10-K pair metadata is normalized explicitly; no tickers or approval flags are
silently promoted to historical evidence. ``universe`` is the output of the
historical selector with an additional universe_evidence_id review reference.

``evidence`` and ``reviews`` name hash-bound JSONL files. An evidence record has
evidence_id, kind, subjects (explicit accession/event/membership IDs),
source_tables (input table name -> SHA-256), and nonempty artifacts (relative
path/SHA-256 specifications for actual source/audit documents). Review records
name evidence_id AND evidence_sha256=fingerprint(the complete evidence record),
reviewer, reviewer_type (human/assistant), reviewed_at, verdict (pass, exclude,
fail, pending), and notes. A review's words are recorded assertions, not identity
authentication. Synthetic assistant reviews remain distinct from empirical
human approval. The manifest's normalization_evidence_id must cover all four
source tables and subject ``dataset``.

Development accepts 2010-2021 acceptance years only, checking projected dates
before parsing outcome tables. Holdout staging uses 2022-2025 only and writes
features.parquet separately from targets.parquet. Empirical holdout parsing
requires a prerequisites callback before reading outcomes. This procedural
guard complements, and does not replace, the final freeze's byte fingerprints.
"""

import io
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import pyarrow.parquet as parquet
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from .controls import control_sessions
from .extraction import TOKEN
from .market_data import NORMALIZED, SYNTHETIC, fingerprint, iso_dates, required_text, sha256, strings
from .modeling import NUMERIC_CONTROLS, validate_dataset
from .protocol import canonical_hash
from .timing import NY, event_window
from .universe import (MEMBERSHIP_COLUMNS, UNIVERSE_TABLES, _relative_bytes, aware_timestamp,
                       build_universe, year_start_window)

EMPIRICAL = "EMPIRICAL_RESEARCH_DATA"
TABLE_COLUMNS = {
    "pairs": {"observation_id", "cik", "previous_cik", "previous_accession", "form", "previous_form",
              "acceptance_timestamp", "previous_acceptance_timestamp", "report_date", "previous_report_date",
              "current_text", "previous_text", "source_url", "previous_source_url",
              "current_evidence_id", "previous_evidence_id", "pair_evidence_id",
              "availability_status", "availability_evidence_id"},
    "labels": {"observation_id", "security_id", "reference_session", "label_end", "stock_return",
               "market_return", "target", "horizon_sessions", "label_evidence_id"},
    "controls": {"observation_id", "security_id", "controls_asof", "control_history_start",
                 "control_history_sessions", "industry", "industry_scheme", "controls_evidence_id",
                 *NUMERIC_CONTROLS},
    "universe": {*MEMBERSHIP_COLUMNS, "universe_evidence_id"},
}
EXCLUSION_COLUMNS = ["observation_id", "cik", "acceptance_date", "partition", "stage", "reason"]
AUDIT_COLUMNS = ["current_evidence_id", "previous_evidence_id", "pair_evidence_id",
                 "availability_evidence_id", "label_evidence_id", "controls_evidence_id",
                 "universe_evidence_id"]


def _jsonl(raw: bytes, label: str) -> list[dict]:
    rows = []
    for number, line in enumerate(raw.decode().splitlines(), 1):
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{label} line {number} must be an object")
            rows.append(value)
    return rows


def _audit_records(evidence_raw: bytes, reviews_raw: bytes, source_hashes: dict,
                   artifact_reader: Callable) -> tuple[dict, dict]:
    evidence, reviews = {}, {}
    for row in _jsonl(evidence_raw, "evidence"):
        identity = row.get("evidence_id")
        required_text(identity, "evidence_id")
        if identity in evidence:
            raise ValueError("Duplicate evidence identifiers")
        required_text(row.get("kind"), "evidence.kind")
        subjects = row.get("subjects")
        if (not isinstance(subjects, list) or not subjects or
                any(not isinstance(value, str) or not value.strip() for value in subjects) or
                len(subjects) != len(set(subjects))):
            raise ValueError("Evidence requires explicit unique subject identifiers")
        sources = row.get("source_tables")
        if not isinstance(sources, dict) or not sources:
            raise ValueError("Evidence must bind normalized source-table hashes")
        for name, value in sources.items():
            if name not in source_hashes or source_hashes[name] != value:
                raise ValueError(f"Stale evidence source-table fingerprint: {identity}/{name}")
        artifacts = row.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError("Evidence needs an actual source/audit document, not a pass flag")
        for spec in artifacts:
            artifact_reader(spec)
        evidence[identity] = row
    for row in _jsonl(reviews_raw, "reviews"):
        identity = row.get("evidence_id")
        if identity not in evidence or identity in reviews:
            raise ValueError("Unknown or duplicate review evidence identifier")
        if row.get("evidence_sha256") != fingerprint(evidence[identity]):
            raise ValueError(f"Stale review fingerprint: {identity}")
        if row.get("reviewer_type") not in {"human", "assistant"}:
            raise ValueError("Review must distinguish human and assistant authorship")
        if row.get("verdict") not in {"pass", "exclude", "fail", "pending"}:
            raise ValueError("Unknown evidence review verdict")
        if row["verdict"] != "pending":
            for key in ("reviewer", "notes"):
                required_text(row.get(key), f"review.{key}")
            reviewed_at = aware_timestamp(row.get("reviewed_at"), "review.reviewed_at")
            if reviewed_at > pd.Timestamp.now(tz="UTC"):
                raise ValueError("Completed reviews cannot have future timestamps")
        reviews[identity] = row
    return evidence, reviews


def _audit_reason(identity, kind: str, subject: str, sources: set[str],
                  evidence: dict, reviews: dict, synthetic: bool) -> tuple[str | None, bool]:
    record = evidence.get(identity)
    if record is None:
        return f"missing_{kind}_evidence", True
    if (record["kind"] != kind or subject not in record["subjects"] or
            not sources.issubset(record["source_tables"])):
        return f"invalid_{kind}_evidence_scope", True
    review = reviews.get(identity)
    if review is None or review["verdict"] == "pending":
        return f"pending_{kind}_review", True
    if not synthetic and review["reviewer_type"] != "human":
        return f"requires_human_{kind}_review", True
    if review["verdict"] != "pass":
        return f"review_{review['verdict']}_{kind}: {review['notes']}", review["verdict"] == "fail"
    return None, False


def _partition_dates(values: pd.Series, config: dict, partition: str) -> list:
    if partition not in {"development", "holdout"}:
        raise ValueError("Dataset partition must be development or holdout")
    windows = []
    lo, hi = ((config["initial_train_start"], config["development_end"]) if partition == "development"
              else (config["holdout_start"], config["holdout_end"]))
    for value in values:
        stamp = aware_timestamp(value, "pairs.acceptance_timestamp")
        year = stamp.tz_convert(NY).year
        if not lo <= year <= hi:
            raise ValueError(f"Acceptance year outside {partition} partition; holdout/development mixing blocked")
        windows.append(event_window(stamp.to_pydatetime(), config["reference_session_offset"],
                                    config["horizon_sessions"]))
    return windows


def _contract(tables: dict) -> None:
    for name, columns in TABLE_COLUMNS.items():
        frame = tables[name]
        if columns - set(frame.columns):
            raise ValueError(f"{name} is missing required columns: {sorted(columns - set(frame.columns))}")
        if name == "universe":
            keys = ["universe_year", "cik"]
            strings(frame.security_id, "universe.security_id")
            strings(frame.universe_membership_id, "universe.universe_membership_id")
            if frame.duplicated(keys).any() or frame.duplicated(["universe_year", "security_id"]).any():
                raise ValueError("Universe must have one permanent security per issuer/year")
        else:
            strings(frame.observation_id, f"{name}.observation_id")
            if frame.observation_id.duplicated().any():
                raise ValueError(f"Duplicate {name} observation identifiers; joins must be one-to-one")
        if name in {"labels", "controls"}:
            if not set(frame.observation_id).issubset(set(tables["pairs"].observation_id)):
                raise ValueError(f"{name} has orphan observations outside the paired event table")
            strings(frame.security_id, f"{name}.security_id")
        for column in columns:
            if column.endswith("_evidence_id"):
                strings(frame[column], f"{name}.{column}")
    for name in ("pairs", "universe"):
        values = tables[name].cik
        strings(values, f"{name}.cik")
        if not values.str.fullmatch(r"\d{10}").all() or (values == "0000000000").any():
            raise ValueError("Dataset CIKs must be canonical nonzero 10-digit strings")


def _valid_universe(frame: pd.DataFrame, config: dict, partition: str) -> None:
    low, high = ((config["initial_train_start"], config["development_end"]) if partition == "development"
                 else (config["holdout_start"], config["holdout_end"]))
    if (not is_numeric_dtype(frame.universe_year) or is_bool_dtype(frame.universe_year) or
            not frame.universe_year.between(low, high).all() or
            not (frame.universe_year % 1 == 0).all()):
        raise ValueError("Universe years must match the separate dataset partition")
    if (frame.groupby("universe_year").size() > config["universe_max_issuers"]).any():
        raise ValueError("Universe exceeds the frozen issuer maximum")
    for row in frame.to_dict("records"):
        window = year_start_window(int(row["universe_year"]), config)
        for column in ("selection_asof", "selection_session", "information_cutoff", "liquidity_start", "liquidity_end"):
            if row[column] != window[column]:
                raise ValueError(f"Historical universe window differs from frozen rule: {column}")
        valid = row["valid_liquidity_sessions"]
        if (isinstance(valid, bool) or not isinstance(valid, (int, float)) or not np.isfinite(valid) or
                int(valid) != valid or not config["liquidity_min_valid_sessions"] <= valid <=
                config["liquidity_lookback_sessions"]):
            raise ValueError("Universe lacks the frozen number of valid prior liquidity observations")
        mean = row["mean_dollar_volume_usd"]
        if isinstance(mean, bool) or not isinstance(mean, (int, float)) or not np.isfinite(mean) or mean < 0:
            raise ValueError("Universe mean dollar volume is invalid")
        _numeric(row, ["issuer_rank"], "universe")
        iso_dates(pd.Series([row["identity_valid_from"], row["identity_valid_to"]]), "universe.identity_interval")
        if not row["identity_valid_from"] <= window["selection_asof"] <= row["identity_valid_to"]:
            raise ValueError("Universe identity does not cover year-start selection")
        bound = {key: row[key] for key in MEMBERSHIP_COLUMNS if key != "universe_membership_id"}
        if row["universe_membership_id"] != fingerprint(bound):
            raise ValueError("Historical universe membership fingerprint changed")
    for _, group in frame.groupby("universe_year"):
        ranked = group.sort_values(["mean_dollar_volume_usd", "security_id", "cik"], ascending=[False, True, True])
        if ranked.issuer_rank.tolist() != list(range(1, len(ranked) + 1)):
            raise ValueError("Universe ranks disagree with historical liquidity ordering")


def _numeric(row: dict, keys: list[str], label: str) -> None:
    for key in keys:
        value = row[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
            raise ValueError(f"{label}.{key} must be finite numeric data")


def _model_row(pair: dict, label: dict, controls: dict, membership: dict, window, config: dict,
               synthetic: bool) -> dict:
    if pair["previous_cik"] != pair["cik"] or pair["observation_id"] == pair["previous_accession"]:
        raise ValueError("Cross-issuer or self-paired annual filing")
    if pair["form"] != "10-K" or pair["previous_form"] != "10-K":
        raise ValueError("Only original 10-K pairs are eligible")
    prior = aware_timestamp(pair["previous_acceptance_timestamp"], "previous_acceptance_timestamp")
    accepted = aware_timestamp(pair["acceptance_timestamp"], "acceptance_timestamp")
    if prior >= accepted:
        raise ValueError("Annual predecessor must precede current acceptance")
    iso_dates(pd.Series([pair["report_date"], pair["previous_report_date"]]), "pair.report_dates")
    days = (pd.Timestamp(pair["report_date"]) - pd.Timestamp(pair["previous_report_date"])).days
    if not 300 <= days <= 430:
        raise ValueError("Missing, duplicate or nonconsecutive annual report periods")
    if (pd.Timestamp(pair["report_date"]).date() > accepted.tz_convert(NY).date() or
            pd.Timestamp(pair["previous_report_date"]).date() > prior.tz_convert(NY).date()):
        raise ValueError("Report period ends after its filing acceptance")
    for field in ("current_text", "previous_text"):
        required_text(pair[field], field)
        if not TOKEN.findall(pair[field]):
            raise ValueError("Empty or untokenizable disclosure section")
    for field in ("source_url", "previous_source_url"):
        required_text(pair[field], field)
        parsed = urlparse(pair[field])
        if not synthetic and (parsed.scheme != "https" or parsed.hostname not in {"www.sec.gov", "data.sec.gov"}):
            raise ValueError("Empirical original filings require official HTTPS SEC source URLs")
    if pair["availability_status"] not in {"verified", "documented_assumption"}:
        raise ValueError("Unknown, missing or violated public-availability evidence")
    available = pair.get("public_available_at")
    if pair["availability_status"] == "verified" or (isinstance(available, str) and available.strip()):
        at = aware_timestamp(available, "public_available_at")
        if at < accepted:
            raise ValueError("Filing availability bound cannot precede its recorded SEC acceptance")
        if at >= pd.Timestamp(window.prediction_time_utc):
            raise ValueError("Disclosure was not available by the prediction open")
    if not membership["identity_valid_from"] <= window.reference_session <= membership["identity_valid_to"]:
        raise ValueError("Year-start security identity does not cover this event; never splice a replacement")
    if label["security_id"] != membership["security_id"] or controls["security_id"] != membership["security_id"]:
        raise ValueError("Label/control security differs from the selected historical share class")
    if label["reference_session"] != window.reference_session or label["label_end"] != window.label_end:
        raise ValueError("Label dates differ from the exact frozen event window")
    if label["horizon_sessions"] != config["horizon_sessions"]:
        raise ValueError("Label horizon differs from the frozen session count")
    expected = control_sessions(window)
    if (controls["controls_asof"] != window.controls_through or controls["control_history_start"] != expected[0]
            or controls["control_history_sessions"] != len(expected)):
        raise ValueError("Controls must use exactly the prior 60 XNYS sessions")
    _numeric(label, ["stock_return", "market_return", "target"], "labels")
    if label["stock_return"] < -1 or label["market_return"] < -1:
        raise ValueError("Compounded total returns cannot be below -1")
    if not np.isclose(label["target"], label["stock_return"] - label["market_return"], atol=1e-12, rtol=1e-12):
        raise ValueError("Target is not stock total return minus matched market total return")
    _numeric(controls, NUMERIC_CONTROLS, "controls")
    if controls["momentum_20"] < -1 or controls["momentum_60"] < -1 or controls["volatility_20"] < 0:
        raise ValueError("Impossible compounded momentum or return volatility")
    for field in ("industry", "industry_scheme"):
        required_text(controls[field], f"controls.{field}")
    # Preserve reviewed source metadata, but take dates from the independently
    # recalculated exchange calendar and controls/targets from their own tables.
    result = {key: pair[key] for key in TABLE_COLUMNS["pairs"]}
    result.update({key: label[key] for key in TABLE_COLUMNS["labels"]},
                  **{key: controls[key] for key in TABLE_COLUMNS["controls"]})
    result.update(acceptance_date=window.acceptance_date, reference_session=window.reference_session,
                  label_end=window.label_end, prediction_time_utc=window.prediction_time_utc,
                  universe_year=int(membership["universe_year"]),
                  universe_membership_id=membership["universe_membership_id"],
                  universe_evidence_id=membership["universe_evidence_id"],
                  public_available_at=available if isinstance(available, str) else "")
    return result


def _authorization(authorization, config: dict) -> dict:
    if not callable(authorization):
        raise ValueError("Empirical holdout outcome access is blocked until prerequisites are verified")
    receipt = authorization()
    if (not isinstance(receipt, dict) or receipt.get("protocol_sha256") != canonical_hash(config) or
            receipt.get("prerequisites_verified") is not True):
        raise ValueError("Holdout authorization receipt does not verify this protocol's prerequisites")
    return receipt


def _read_projected_table(body: bytes, name: str) -> pd.DataFrame:
    """Do not deserialize unrelated outcomes accidentally co-exported upstream."""
    fields = set(parquet.read_schema(io.BytesIO(body)).names)
    required = TABLE_COLUMNS[name]
    if required - fields:
        raise ValueError(f"{name} is missing required columns: {sorted(required - fields)}")
    optional = {"public_available_at"} & fields if name == "pairs" else set()
    return pd.read_parquet(io.BytesIO(body), columns=sorted(required | optional))


def build_dataset(manifest_path: str | Path, output: str | Path, config: dict,
                  partition: str = "development", *, authorization=None) -> dict:
    """Validate audited joins and publish an immutable partition plus exclusions.

    Missing/unreviewed events are retained in the exclusion ledger; they never
    become approved observations. Unresolved missing data/audits make the whole
    empirical bundle staging-only. This function never invents review records.
    """
    path, output = Path(manifest_path), Path(output)
    if output.exists():
        raise ValueError("Dataset output exists; preserve the earlier frozen observation set")
    raw = path.read_bytes()
    source = json.loads(raw)
    if source.get("schema_version") != 1 or source.get("data_kind") not in {SYNTHETIC, NORMALIZED, EMPIRICAL}:
        raise ValueError("Unknown dataset input version or data kind")
    synthetic = source["data_kind"] == SYNTHETIC
    if source.get("partition") != partition or source.get("protocol_sha256") != canonical_hash(config):
        raise ValueError("Dataset source protocol/partition differs from the requested build")
    required_text(source.get("normalization_notes"), "normalization_notes")
    aware_timestamp(source.get("created_at"), "created_at")
    if set(source.get("tables", {})) != set(TABLE_COLUMNS):
        raise ValueError("Dataset requires exactly pairs, labels, controls and universe tables")
    # Project acceptance timestamps before parsing texts, labels or controls.
    pairs_raw = _relative_bytes(path.parent, source["tables"]["pairs"], "pairs")
    metadata = pd.read_parquet(io.BytesIO(pairs_raw), columns=["acceptance_timestamp"])
    windows = _partition_dates(metadata.acceptance_timestamp, config, partition)
    gate = _authorization(authorization, config) if partition == "holdout" and not synthetic else None
    tables = {"pairs": _read_projected_table(pairs_raw, "pairs")}
    for name in ("universe", "controls", "labels"):
        tables[name] = _read_projected_table(_relative_bytes(path.parent, source["tables"][name], name), name)
    _contract(tables)
    if tables["pairs"].empty:
        raise ValueError("Dataset input pairs must not be empty")
    _valid_universe(tables["universe"], config, partition)
    evidence_raw = _relative_bytes(path.parent, source["evidence"], "evidence")
    reviews_raw = _relative_bytes(path.parent, source["reviews"], "reviews")
    artifact_bodies = {}

    def read_artifact(spec):
        body = _relative_bytes(path.parent, spec, "audit artifact")
        key = spec["path"]
        if key in artifact_bodies and artifact_bodies[key] != body:
            raise ValueError("Conflicting audit artifact paths")
        artifact_bodies[key] = body
        return body

    source_hashes = {name: spec["sha256"] for name, spec in source["tables"].items()}
    evidence, reviews = _audit_records(evidence_raw, reviews_raw, source_hashes, read_artifact)
    global_reason, global_unresolved = _audit_reason(
        source.get("normalization_evidence_id"), "normalization", "dataset", set(TABLE_COLUMNS),
        evidence, reviews, synthetic)
    labels = tables["labels"].set_index("observation_id").to_dict("index")
    controls = tables["controls"].set_index("observation_id").to_dict("index")
    universe = tables["universe"].set_index(["universe_year", "cik"]).to_dict("index")
    rows, exclusions, unresolved = [], [], 0
    for pair, window in zip(tables["pairs"].to_dict("records"), windows, strict=True):
        obs = pair["observation_id"]

        def exclude(stage, reason, pending=False):
            nonlocal unresolved
            unresolved += int(pending)
            exclusions.append({"observation_id": obs, "cik": pair["cik"],
                               "acceptance_date": window.acceptance_date, "partition": partition,
                               "stage": stage, "reason": reason})

        membership = universe.get((int(window.acceptance_date[:4]), pair["cik"]))
        if membership is None:
            exclude("universe", "outside_historical_year_start_universe")
            continue
        membership = {**membership, "universe_year": int(window.acceptance_date[:4]), "cik": pair["cik"]}
        if obs not in labels or obs not in controls:
            exclude("join", "missing_label_or_control_record", True)
            continue
        label, control = labels[obs], controls[obs]
        checks = [(pair["current_evidence_id"], "filing", obs, {"pairs"}),
                  (pair["previous_evidence_id"], "filing", pair["previous_accession"], {"pairs"}),
                  (pair["pair_evidence_id"], "pair", obs, {"pairs"}),
                  (pair["availability_evidence_id"], "availability", obs, {"pairs"}),
                  (label["label_evidence_id"], "label", obs, {"pairs", "labels"}),
                  (control["controls_evidence_id"], "controls", obs, {"pairs", "controls"}),
                  (membership["universe_evidence_id"], "universe", membership["universe_membership_id"], {"universe"})]
        reasons = [_audit_reason(*check, evidence, reviews, synthetic) for check in checks]
        if global_reason:
            reasons.append((global_reason, global_unresolved))
        rejected = [(reason, pending) for reason, pending in reasons if reason]
        if rejected:
            exclude("audit", "; ".join(reason for reason, _ in rejected), any(pending for _, pending in rejected))
            continue
        try:
            row = _model_row(pair, {"observation_id": obs, **label}, {"observation_id": obs, **control},
                             membership, window, config, synthetic)
        except ValueError as exc:
            exclude("validation", str(exc), True)
            continue
        rows.append(row)
    columns = sorted(set().union(TABLE_COLUMNS["pairs"], TABLE_COLUMNS["labels"], TABLE_COLUMNS["controls"],
                                 {"acceptance_date", "prediction_time_utc", "universe_year", "universe_membership_id",
                                  "universe_evidence_id", "public_available_at"}))
    frame = pd.DataFrame(rows, columns=columns).sort_values(["acceptance_date", "observation_id"]).reset_index(drop=True)
    excluded = pd.DataFrame(exclusions, columns=EXCLUSION_COLUMNS).sort_values("observation_id").reset_index(drop=True)
    if not frame.empty:
        validate_dataset(frame)
    approved = bool(len(frame) and not global_reason and unresolved == 0)
    summary = {"schema_version": 1, "data_kind": SYNTHETIC if synthetic else EMPIRICAL,
               "partition": partition, "protocol_sha256": canonical_hash(config),
               "created_at": datetime.now(timezone.utc).isoformat(),
               "source_manifest_sha256": sha256(raw), "source_table_sha256": source_hashes,
               "input_observations": len(tables["pairs"]), "observations": len(frame),
               "exclusions": len(excluded), "unresolved_events": unresolved,
               "approval_status": "synthetic_fixture_only" if synthetic else ("approved" if approved else "pending"),
               "model_ready": approved and not synthetic,
               "synthetic_fixture_validated": approved if synthetic else False,
               "human_reviews": sum(row["reviewer_type"] == "human" and row["verdict"] == "pass" for row in reviews.values()),
               "assistant_reviews": sum(row["reviewer_type"] == "assistant" and row["verdict"] == "pass" for row in reviews.values()),
               "availability_assumptions": int((frame.availability_status == "documented_assumption").sum()) if len(frame) else 0,
               "authorization_receipt": gate,
               "interpretation": "synthetic engineering validation only" if synthetic else "audited inputs; model performance not evaluated"}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dataset-", dir=output.parent) as temporary:
        stage = Path(temporary) / "bundle"
        stage.mkdir()
        if partition == "development":
            frame.to_parquet(stage / "dataset.parquet", index=False)
        else:
            frame.drop(columns=["target", "stock_return", "market_return"]).to_parquet(stage / "features.parquet", index=False)
            frame[["observation_id", "target"]].to_parquet(stage / "targets.parquet", index=False)
        excluded.to_parquet(stage / "exclusions.parquet", index=False)
        (stage / "source_manifest.json").write_bytes(raw)
        (stage / "audit").mkdir()
        (stage / "audit" / "evidence.jsonl").write_bytes(evidence_raw)
        (stage / "audit" / "reviews.jsonl").write_bytes(reviews_raw)
        summary["audit_artifacts"] = {}
        for source_path, body in artifact_bodies.items():
            destination = f"audit/{sha256(body)}.bin"
            (stage / destination).write_bytes(body)
            summary["audit_artifacts"][source_path] = {"path": destination, "sha256": sha256(body)}
        summary["files"] = {str(p.relative_to(stage)): sha256(p.read_bytes()) for p in sorted(stage.rglob("*")) if p.is_file()}
        summary["dataset_id"] = fingerprint(summary)
        (stage / "dataset_manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
        stage.rename(output)
    return summary


def load_dataset(bundle: str | Path, config: dict, partition: str = "development", *,
                 require_approved: bool = True, authorization=None,
                 features_only: bool = False) -> tuple[pd.DataFrame, dict]:
    """Revalidate bundle bytes and underlying reviews before model use.

    ``require_approved=False`` supports inspection of staging outputs only. A
    synthetic fixture can pass its own checks but always keeps model_ready=False.
    ``features_only=True`` for holdout revalidates source-bound review evidence
    without deserializing targets; it is the final freeze's metadata-only gate.
    """
    root = Path(bundle)
    manifest = json.loads((root / "dataset_manifest.json").read_bytes())
    signed = {key: value for key, value in manifest.items() if key != "dataset_id"}
    if manifest.get("dataset_id") != fingerprint(signed):
        raise ValueError("Dataset manifest fingerprint changed")
    if manifest.get("partition") != partition or manifest.get("protocol_sha256") != canonical_hash(config):
        raise ValueError("Dataset partition or frozen protocol changed")
    if manifest.get("data_kind") not in {SYNTHETIC, EMPIRICAL}:
        raise ValueError("Unknown prepared dataset kind")
    synthetic = manifest["data_kind"] == SYNTHETIC
    expected = ({"dataset.parquet"} if partition == "development" else {"features.parquet", "targets.parquet"})
    if not expected.union({"exclusions.parquet", "source_manifest.json", "audit/evidence.jsonl", "audit/reviews.jsonl"}).issubset(manifest.get("files", {})):
        raise ValueError("Prepared dataset is missing hash-bound partition/audit files")
    bodies = {name: _relative_bytes(root, {"path": name, "sha256": value}, name)
              for name, value in manifest["files"].items()
              if not (partition == "holdout" and name == "targets.parquet")}
    source = json.loads(bodies["source_manifest.json"])
    if sha256(bodies["source_manifest.json"]) != manifest["source_manifest_sha256"]:
        raise ValueError("Prepared dataset source manifest changed")
    if (source.get("partition") != partition or source.get("protocol_sha256") != canonical_hash(config) or
            (source.get("data_kind") == SYNTHETIC) != synthetic):
        raise ValueError("Prepared dataset source kind/protocol/partition differs")
    for name in ("evidence", "reviews"):
        if sha256(bodies[f"audit/{name}.jsonl"]) != source[name]["sha256"]:
            raise ValueError(f"Prepared {name} no longer matches the source manifest")
    source_hashes = {name: spec["sha256"] for name, spec in source["tables"].items()}
    if source_hashes != manifest["source_table_sha256"]:
        raise ValueError("Prepared source-table fingerprints differ")

    def read_artifact(spec):
        stored = manifest.get("audit_artifacts", {}).get(spec.get("path"))
        if not stored or stored["sha256"] != spec.get("sha256"):
            raise ValueError("Prepared audit artifact fingerprint changed")
        return _relative_bytes(root, stored, "prepared audit artifact")

    evidence, reviews = _audit_records(bodies["audit/evidence.jsonl"], bodies["audit/reviews.jsonl"],
                                     source_hashes, read_artifact)
    name = "dataset.parquet" if partition == "development" else "features.parquet"
    metadata = pd.read_parquet(io.BytesIO(bodies[name]), columns=["acceptance_timestamp"])
    windows = _partition_dates(metadata.acceptance_timestamp, config, partition)
    frame = pd.read_parquet(io.BytesIO(bodies[name]))
    if partition == "holdout":
        if set(frame.columns) & {"target", "stock_return", "market_return"}:
            raise ValueError("Holdout features must be physically target-free")
    excluded = pd.read_parquet(io.BytesIO(bodies["exclusions.parquet"]))
    if (set(EXCLUSION_COLUMNS) - set(excluded.columns) or excluded.observation_id.duplicated().any() or
            set(excluded.observation_id) & set(frame.observation_id)):
        raise ValueError("Excluded and retained observations must be distinct, uniquely identified records")
    if (len(frame) != manifest["observations"] or len(excluded) != manifest["exclusions"] or
            len(frame) + len(excluded) != manifest["input_observations"]):
        raise ValueError("Prepared dataset/exclusion counts changed")
    reason, _ = _audit_reason(source.get("normalization_evidence_id"), "normalization", "dataset",
                              set(TABLE_COLUMNS), evidence, reviews, synthetic)
    failures = [reason] if reason else []
    for row in frame.to_dict("records"):
        for identity, kind, subject, sources in [
                (row["current_evidence_id"], "filing", row["observation_id"], {"pairs"}),
                (row["previous_evidence_id"], "filing", row["previous_accession"], {"pairs"}),
                (row["pair_evidence_id"], "pair", row["observation_id"], {"pairs"}),
                (row["availability_evidence_id"], "availability", row["observation_id"], {"pairs"}),
                (row["label_evidence_id"], "label", row["observation_id"], {"pairs", "labels"}),
                (row["controls_evidence_id"], "controls", row["observation_id"], {"pairs", "controls"}),
                (row["universe_evidence_id"], "universe", row["universe_membership_id"], {"universe"})]:
            reason, _ = _audit_reason(identity, kind, subject, sources, evidence, reviews, synthetic)
            if reason:
                failures.append(reason)
    if require_approved or (partition == "holdout" and not features_only and not synthetic):
        eligible = manifest.get("synthetic_fixture_validated") if synthetic else (
            manifest.get("model_ready") is True and manifest.get("approval_status") == "approved")
        if not eligible or failures or frame.empty:
            raise ValueError("Dataset remains staging-only: complete source-bound reviews and resolve exclusions before modeling")
    if not frame.empty:
        if partition != "holdout":
            validate_dataset(frame)
        else:
            required = ["observation_id", "acceptance_date", "reference_session", "label_end", "current_text",
                        "previous_text", "industry", "controls_asof", *NUMERIC_CONTROLS]
            if (set(required) - set(frame.columns) or frame[required].isna().any().any() or
                    frame.observation_id.duplicated().any()):
                raise ValueError("Holdout features are missing required values or unique observation IDs")
            for row, window in zip(frame.to_dict("records"), windows, strict=True):
                _numeric(row, NUMERIC_CONTROLS, "controls")
                if (row["acceptance_date"] != window.acceptance_date or row["reference_session"] != window.reference_session or
                        row["label_end"] != window.label_end or row["controls_asof"] != window.controls_through):
                    raise ValueError("Holdout feature dates differ from the frozen event window")
    if partition == "holdout" and not features_only:
        if not synthetic:
            _authorization(authorization, config)
        target_raw = _relative_bytes(root, {"path": "targets.parquet", "sha256": manifest["files"]["targets.parquet"]},
                                     "targets.parquet")
        targets = pd.read_parquet(io.BytesIO(target_raw))
        if set(targets.columns) != {"observation_id", "target"}:
            raise ValueError("Holdout targets require only observation_id and target")
        if targets.observation_id.duplicated().any() or set(targets.observation_id) != set(frame.observation_id):
            raise ValueError("Holdout targets must join one-to-one to the identical observations")
        frame = frame.merge(targets, on="observation_id", validate="one_to_one")
        if not frame.empty:
            validate_dataset(frame)
    frame.attrs.update(data_kind=manifest["data_kind"], dataset_id=manifest["dataset_id"],
                       partition=partition, model_ready=manifest["model_ready"])
    return frame, manifest


def _write_synthetic_partition(root: Path, members: pd.DataFrame, config: dict, partition: str) -> Path:
    """Invent normalized inputs and explicitly assistant-authored fixture reviews."""
    root.mkdir()
    rng = np.random.default_rng(config["seed"])
    rows, labels, controls = [], [], []
    membership = members.copy()
    membership["universe_evidence_id"] = membership.universe_membership_id.map(lambda value: f"fixture-universe-{value}")
    for member in membership.sort_values(["universe_year", "cik"]).to_dict("records"):
        year, issuer = int(member["universe_year"]), int(member["cik"])
        accepted = datetime(year, 2 + issuer % 6, 15, 18, tzinfo=NY)
        previous = datetime(year - 1, 2 + issuer % 6, 15, 18, tzinfo=NY)
        obs, prior = f"SYNTHETIC-{year}-{issuer:02d}", f"SYNTHETIC-{year - 1}-{issuer:02d}"
        window = event_window(accepted, config["reference_session_offset"], config["horizon_sessions"])
        additions = int(rng.integers(1, 20))
        old = "supply demand competition pricing " * 20
        new = old + "cybersecurity disruption regulatory uncertainty " * additions
        rows.append({"observation_id": obs, "cik": member["cik"], "previous_cik": member["cik"],
                     "previous_accession": prior, "form": "10-K", "previous_form": "10-K",
                     "acceptance_timestamp": accepted.isoformat(),
                     "previous_acceptance_timestamp": previous.isoformat(),
                     "report_date": f"{year - 1}-12-31", "previous_report_date": f"{year - 2}-12-31",
                     "current_text": new, "previous_text": old,
                     "source_url": f"synthetic://{obs}", "previous_source_url": f"synthetic://{prior}",
                     "current_evidence_id": f"fixture-filing-{obs}",
                     "previous_evidence_id": f"fixture-filing-{prior}",
                     "pair_evidence_id": f"fixture-pair-{obs}",
                     "availability_status": "documented_assumption",
                     "availability_evidence_id": f"fixture-availability-{obs}",
                     "public_available_at": accepted.isoformat()})
        target = float(-0.04 * np.log1p(additions / 20) + rng.normal(0, 0.005))
        labels.append({"observation_id": obs, "security_id": member["security_id"],
                       "reference_session": window.reference_session, "label_end": window.label_end,
                       "stock_return": target + 0.005, "market_return": 0.005, "target": target,
                       "horizon_sessions": config["horizon_sessions"], "label_evidence_id": f"fixture-label-{obs}"})
        controls.append({"observation_id": obs, "security_id": member["security_id"],
                         "controls_asof": window.controls_through, "control_history_start": control_sessions(window)[0],
                         "control_history_sessions": 60, "momentum_20": float(rng.normal(0, 0.04)),
                         "momentum_60": float(rng.normal(0, 0.08)), "volatility_20": float(rng.uniform(0.01, 0.04)),
                         "log_market_cap": float(rng.normal(24, 1)), "industry": f"synthetic-sector-{issuer % 3}",
                         "industry_scheme": "SYNTHETIC_ENGINEERING_SECTORS",
                         "controls_evidence_id": f"fixture-controls-{obs}"})
    frames = {"pairs": pd.DataFrame(rows), "labels": pd.DataFrame(labels), "controls": pd.DataFrame(controls),
              "universe": membership}
    tables = {}
    for name, frame in frames.items():
        file = root / f"{name}.parquet"
        frame.to_parquet(file, index=False)
        tables[name] = {"path": file.name, "sha256": sha256(file.read_bytes())}
    artifact = root / "synthetic-source-notes.txt"
    artifact.write_text("SYNTHETIC ENGINEERING FIXTURE. Every issuer, filing, disclosure, liquidity, return and control "
                        "is invented. Review records are assistant-authored fixture assertions. They are not human "
                        "approval, observed market data, verified public availability or a completed empirical study. "
                        "Year-start memberships were calculated by the production historical universe selector.\n")
    spec = {"path": artifact.name, "sha256": sha256(artifact.read_bytes())}
    evidence = {}

    def add(identity, kind, subject, names):
        evidence[identity] = {"evidence_id": identity, "kind": kind, "subjects": [subject],
                              "source_tables": {name: tables[name]["sha256"] for name in sorted(names)},
                              "artifacts": [spec]}

    for pair in rows:
        obs = pair["observation_id"]
        add(pair["current_evidence_id"], "filing", obs, {"pairs"})
        add(pair["previous_evidence_id"], "filing", pair["previous_accession"], {"pairs"})
        add(pair["pair_evidence_id"], "pair", obs, {"pairs"})
        add(pair["availability_evidence_id"], "availability", obs, {"pairs"})
        add(f"fixture-label-{obs}", "label", obs, {"pairs", "labels"})
        add(f"fixture-controls-{obs}", "controls", obs, {"pairs", "controls"})
    for member in membership.to_dict("records"):
        add(member["universe_evidence_id"], "universe", member["universe_membership_id"], {"universe"})
    add("fixture-normalization", "normalization", "dataset", set(TABLE_COLUMNS))
    stamp = datetime.now(timezone.utc).isoformat()
    reviews = [{"evidence_id": row["evidence_id"], "evidence_sha256": fingerprint(row),
                "reviewer": "synthetic fixture author (assistant)", "reviewer_type": "assistant",
                "reviewed_at": stamp, "verdict": "pass",
                "notes": "Invented fixture values and source bindings checked for software validation only; no human sign-off."}
               for row in evidence.values()]
    for name, records in (("evidence", list(evidence.values())), ("reviews", reviews)):
        (root / f"{name}.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records))
    source = {"schema_version": 1, "data_kind": SYNTHETIC, "partition": partition,
              "protocol_sha256": canonical_hash(config), "created_at": stamp,
              "normalization_notes": "Synthetic normalized contract demonstration; all values are invented.",
              "tables": tables, "normalization_evidence_id": "fixture-normalization",
              **{name: {"path": f"{name}.jsonl", "sha256": sha256((root / f"{name}.jsonl").read_bytes())}
                 for name in ("evidence", "reviews")}}
    path = root / "manifest.json"
    path.write_text(json.dumps(source, indent=2) + "\n")
    return path


def run_synthetic_dataset_demo(output: str | Path, config: dict) -> dict:
    """Exercise historical selection and both isolated dataset partitions.

    This deliberately invented 12-issuer fixture is runnable without vendor
    credentials. Outputs are never valid empirical approvals or research claims.
    """
    output = Path(output)
    if output.exists():
        raise ValueError("Dataset demo output exists; choose a new directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dataset-demo-", dir=output.parent) as temporary:
        stage = Path(temporary) / "demo"
        stage.mkdir()
        sources = stage / "universe-source"
        sources.mkdir()
        years = list(range(config["initial_train_start"], config["holdout_end"] + 1))
        listings, links, liquidity = [], [], []
        for issuer in range(1, 13):
            for suffix, multiplier in (("A", 1.0), ("B", 0.5)) if issuer == 1 else (("A", 1.0),):
                security = f"SYNTHETIC-SEC-{issuer:02d}-{suffix}"
                listings.append({"security_id": security, "valid_from": "2008-01-01", "valid_to": "2028-12-31",
                                 "market_country": "US", "share_type": "COMMON_STOCK", "listing_status": "ACTIVE",
                                 "known_at": "2008-01-01T00:00:00+00:00", "classification_source": "invented fixture",
                                 "evidence_id": "synthetic-history"})
                links.append({"security_id": security, "cik": f"{issuer:010d}",
                              "valid_from": "2008-01-01", "valid_to": "2028-12-31",
                              "known_at": "2008-01-01T00:00:00+00:00", "mapping_source": "invented fixture",
                              "evidence_id": "synthetic-history"})
                for year in years:
                    for session in year_start_window(year, config)["sessions"]:
                        liquidity.append({"security_id": security, "session": session,
                                          "dollar_volume_usd": float((13 - issuer) * 1_000_000 * multiplier),
                                          "available_at": calendar_close_iso(session)})
        frames = {"listings": pd.DataFrame(listings), "identity_links": pd.DataFrame(links),
                  "daily_liquidity": pd.DataFrame(liquidity)}
        table_specs = {}
        for name, frame in frames.items():
            file = sources / f"{name}.parquet"
            frame.to_parquet(file, index=False)
            table_specs[name] = {"path": file.name, "sha256": sha256(file.read_bytes()),
                                 "field_mapping": {column: f"invented normalized {column}" for column in UNIVERSE_TABLES[name]}}
        proof = sources / "synthetic-history.txt"
        proof.write_text("SYNTHETIC fixture: 12 invented US common-stock issuers, 13 classes, static historical classification, "
                         "and 60 invented prior-session USD-volume records per class and year. No actual vendor data.\n")
        universe_source = {"schema_version": 1, "data_kind": SYNTHETIC, "provider": "invented engineering fixture",
                           "normalization_notes": "Direct invented USD dollar-volume values; no vendor code mapping.",
                           "population_coverage": "Exactly 12 invented issuers with 13 listed classes; not an empirical universe.",
                           "exported_at": datetime.now(timezone.utc).isoformat(), "years": years, "tables": table_specs,
                           "evidence": {"synthetic-history": {"path": proof.name, "sha256": sha256(proof.read_bytes())}}}
        path = sources / "manifest.json"
        path.write_text(json.dumps(universe_source, indent=2) + "\n")
        universe_manifest = build_universe(path, stage / "universe", config)
        members = pd.read_parquet(stage / "universe" / "universe.parquet")
        manifests = {}
        for partition in ("development", "holdout"):
            use = members.universe_year <= config["development_end"]
            if partition == "holdout":
                use = ~use
            source = _write_synthetic_partition(stage / f"{partition}-source", members.loc[use], config, partition)
            manifests[partition] = build_dataset(source, stage / partition, config, partition)
            load_dataset(stage / partition, config, partition)
        summary = {"schema_version": 1, "data_kind": SYNTHETIC, "empirical_model_ready": False,
                   "universe": universe_manifest, "development": manifests["development"],
                   "holdout": manifests["holdout"],
                   "paths": {"development_dataset": "development/dataset.parquet",
                             "development_manifest": "development/dataset_manifest.json",
                             "holdout_features": "holdout/features.parquet", "holdout_targets": "holdout/targets.parquet",
                             "holdout_manifest": "holdout/dataset_manifest.json"},
                   "interpretation": "Invented data validates software plumbing only; full historical market universe and empirical audits remain required."}
        (stage / "dataset_demo_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        stage.rename(output)
    return summary


def calendar_close_iso(session: str) -> str:
    """Fixture helper: explicitly record when invented liquidity is available."""
    from .timing import calendar
    return calendar().session_close(session).isoformat()
