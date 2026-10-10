"""Actual pinned MiniLM validation on source-audited, development-period SEC text.

This module accepts filing text and audit artifacts only. It never loads market
tables, fits a return model, or certifies human review. The prepare/run split
binds the outcome-free sample and numerical checks before model execution.
"""

import argparse
import hashlib
import importlib.metadata
import io
import json
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from . import semantic
from .pilot_checkpoint import _pilot_evidence
from .protocol import canonical_hash, guard_development, load_protocol

DATA_KIND = "REAL_SEC_TEXT_DESCRIPTIVE_PILOT"
FORBIDDEN = {"target", "stock_return", "market_return", "excess_return", "abnormal_return",
             "ret", "retx", "dlret", "prediction", "baseline_prediction", "text_prediction"}
PAIR_COLUMNS = ["accession", "previous_accession", "cik", "acceptance_date",
                "previous_text", "current_text", "source_url", "previous_source_url"]
SOURCE_FILES = {"pairs": "source_pairs.parquet", "filings": "source_filings.parquet",
                "audit": "audit_summary.json", "evidence": "filing_evidence.parquet",
                "spec": "semantic_spec.json", "protocol": "protocol.json"}
CHECKS = {"batch_size": 16, "cpu_threads": 1, "deterministic_algorithms": True,
          "same_batch_max_abs_tolerance": 1e-12, "different_batch_max_abs_tolerance": 1e-6,
          "unit_norm_tolerance": 1e-12, "unchanged_distance_tolerance": 1e-12,
          "tokens_truncated_allowed": 0, "expected_embedding_dimensions": 384}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(path: Path, value: dict) -> None:
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def _schema(raw: bytes, name: str) -> None:
    columns = {name.lower() for name in pq.ParquetFile(io.BytesIO(raw)).schema_arrow.names}
    if columns & FORBIDDEN:
        raise ValueError(f"Semantic text validation rejects outcome-bearing {name}")


def _source_inputs(raw: dict[str, bytes], config: dict) -> tuple[pd.DataFrame, dict]:
    for name in ("pairs", "filings", "evidence"):
        _schema(raw[name], name)
    audit = json.loads(raw["audit"])
    if (audit.get("pair_table_sha256") != _sha(raw["pairs"])
            or audit.get("source_table_sha256") != _sha(raw["filings"])):
        raise ValueError("Semantic source tables differ from their source audit")
    dates = pd.read_parquet(io.BytesIO(raw["pairs"]), columns=["acceptance_date"])
    if dates.empty or pd.to_datetime(dates.acceptance_date, errors="coerce").isna().any():
        raise ValueError("Semantic validation requires nonempty dated development text")
    guard_development(dates, config)
    evidence_dates = pd.read_parquet(io.BytesIO(raw["evidence"]), columns=["acceptance_timestamp"])
    accepted = pd.to_datetime(evidence_dates.acceptance_timestamp, errors="coerce", utc=True)
    if accepted.isna().any():
        raise ValueError("Semantic filing evidence requires valid acceptance timestamps")
    guard_development(pd.DataFrame({"acceptance_date": accepted.dt.tz_convert("America/New_York")}), config)
    pairs = pd.read_parquet(io.BytesIO(raw["pairs"]), columns=PAIR_COLUMNS)
    if pairs.accession.isna().any() or pairs.accession.duplicated().any():
        raise ValueError("Semantic validation pairs require unique accession identifiers")
    for column in ("previous_text", "current_text"):
        if not pairs[column].map(lambda value: isinstance(value, str) and bool(value.strip())).all():
            raise ValueError("Semantic validation excludes empty or invalid filing text")
    filings = pd.read_parquet(io.BytesIO(raw["filings"]), columns=["accessionNumber"])
    counts = _pilot_evidence(raw["evidence"], audit, pairs, filings)
    return pairs.sort_values(["acceptance_date", "accession"]).reset_index(drop=True), counts


def _code_files() -> dict:
    # These files implement the sample gate, encoder and check definitions.
    return {name: _sha((Path(__file__).parent / name).read_bytes()) for name in (
        "semantic.py", "semantic_validation.py", "pilot_checkpoint.py", "protocol.py")}


def _recheck_ids(pairs: pd.DataFrame, config: dict) -> list[str]:
    years = sorted(pd.to_datetime(pairs.acceptance_date).dt.year.unique())
    chosen_years = sorted({int(years[0]), int(years[len(years) // 2]), int(years[-1])})
    result = []
    for year in chosen_years:
        candidates = pairs.loc[pd.to_datetime(pairs.acceptance_date).dt.year.eq(year)]
        result.append(min(candidates.accession, key=lambda value: _sha(f'{config["seed"]}:{value}'.encode())))
    return result


def prepare_validation(pairs_path, filings_path, audit_dir, spec_path, output, config) -> dict:
    """Create an immutable, source-bound plan before any model is instantiated."""
    out = Path(output)
    if out.exists():
        raise ValueError("Output exists; preserve the previous semantic validation plan")
    paths = {"pairs": Path(pairs_path), "filings": Path(filings_path),
             "audit": Path(audit_dir) / "audit_summary.json",
             "evidence": Path(audit_dir) / "filing_evidence.parquet", "spec": Path(spec_path)}
    raw = {name: path.read_bytes() for name, path in paths.items()}
    raw["protocol"] = (json.dumps(config, indent=2) + "\n").encode()
    spec = json.loads(raw["spec"])
    semantic.validate_spec(spec)
    pairs, counts = _source_inputs(raw, config)
    rechecks = _recheck_ids(pairs, config)
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2],
                         capture_output=True, text=True, check=False)
    plan = {"schema_version": 1, "data_kind": DATA_KIND, "analysis": "RETROSPECTIVE_TEXT_ENCODER_VALIDATION",
            "created_at": datetime.now(timezone.utc).isoformat(), "protocol_sha256": canonical_hash(config),
            "sources": {name: {"file": SOURCE_FILES[name], "sha256": _sha(value)} for name, value in raw.items()},
            "source_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "code_commit": git.stdout.strip() if git.returncode == 0 else None,
            "code_files": _code_files(), "source_audit": counts,
            "sample_rule": "all source-audited pairs in the supplied development-only pilot",
            "recheck_selection": "minimum SHA256(protocol seed:accession) in first, middle and last acceptance years",
            "recheck_observation_ids": rechecks,
            "checks": dict(CHECKS),
            "returns_read": False, "final_period_opened": False, "primary_model_input": False,
            "model_ready": False, "empirical_gate_satisfied": False,
            "manual_validation_status": "pending_named_human_review"}
    plan["validation_id"] = canonical_hash(plan)
    out.mkdir(parents=True)
    for name, value in raw.items():
        (out / SOURCE_FILES[name]).write_bytes(value)
    _json(out / "validation_plan.json", plan)
    return plan


def load_validation_plan(package) -> tuple[dict, pd.DataFrame, dict]:
    package = Path(package)
    plan = json.loads((package / "validation_plan.json").read_bytes())
    unsigned = {name: value for name, value in plan.items() if name != "validation_id"}
    if plan.get("validation_id") != canonical_hash(unsigned):
        raise ValueError("Semantic validation plan fingerprint differs")
    if (plan.get("data_kind") != DATA_KIND or plan.get("primary_model_input") is not False
            or plan.get("returns_read") is not False or plan.get("final_period_opened") is not False
            or plan.get("model_ready") is not False or plan.get("empirical_gate_satisfied") is not False):
        raise ValueError("Semantic validation plan must retain its text-only retrospective status")
    if plan.get("code_files") != _code_files():
        raise ValueError("Semantic implementation changed after the validation plan was prepared")
    if plan.get("checks") != CHECKS:
        raise ValueError("Semantic numerical check definitions differ from the declared implementation")
    raw = {}
    if set(plan.get("sources", {})) != set(SOURCE_FILES):
        raise ValueError("Semantic validation plan has incomplete source bindings")
    for name, filename in SOURCE_FILES.items():
        binding = plan["sources"][name]
        if binding.get("file") != filename:
            raise ValueError("Semantic validation source filename differs")
        raw[name] = (package / filename).read_bytes()
        if _sha(raw[name]) != binding.get("sha256"):
            raise ValueError(f"Semantic validation source changed: {name}")
    config, spec = json.loads(raw["protocol"]), json.loads(raw["spec"])
    if plan.get("protocol_sha256") != canonical_hash(config):
        raise ValueError("Semantic validation protocol differs")
    semantic.validate_spec(spec)
    pairs, counts = _source_inputs(raw, config)
    if counts != plan.get("source_audit"):
        raise ValueError("Semantic validation source review counts differ")
    if plan.get("recheck_observation_ids") != _recheck_ids(pairs, config):
        raise ValueError("Semantic reproducibility sample differs from the exact declared selection")
    return plan, pairs, spec


def _versions() -> dict:
    names = ["torch", "transformers", "huggingface-hub", "safetensors", "tokenizers", "numpy",
             "pandas", "pyarrow"]
    return {name: importlib.metadata.version(name) for name in names}


def _coverage(vector, receipt, checks) -> None:
    if (np.asarray(vector).shape != (checks["expected_embedding_dimensions"],)
            or not np.isfinite(vector).all()
            or abs(float(np.linalg.norm(vector)) - 1) > checks["unit_norm_tolerance"]):
        raise ValueError("Actual semantic document vector violates dimension, finiteness or norm checks")
    if (receipt["tokens_encoded"] != receipt["content_tokens"] or receipt["tokens_truncated"] != 0
            or receipt["chunks"] != (receipt["content_tokens"] + 253) // 254):
        raise ValueError("Actual semantic encoding does not cover every content token")


def run_validation(package, output, *, cache_dir=None, local_model_dir=None) -> dict:
    """Execute the actual checkpoint; never substitute a toy encoder on failure."""
    out = Path(output)
    if out.exists():
        raise ValueError("Output exists; preserve prior semantic validation results")
    plan, pairs, spec = load_validation_plan(package)
    checks = plan["checks"]
    import torch

    torch.set_num_threads(checks["cpu_threads"])
    torch.use_deterministic_algorithms(checks["deterministic_algorithms"])
    start = time.perf_counter()
    encoder = semantic.PinnedSemanticEncoder(spec, cache_dir, checks["batch_size"],
                                             local_model_dir=local_model_dir)
    initialization_seconds = time.perf_counter() - start
    out.mkdir(parents=True)
    # This receipt proves the pre-existing plan and actual backend were selected
    # before text inference. A failed run leaves this attempt without a success receipt.
    _json(out / "execution_started.json", {"validation_id": plan["validation_id"],
          "started_at": datetime.now(timezone.utc).isoformat(), "backend": _versions(),
          "actual_checkpoint_loaded": True, "checkpoint_revision": spec["revision"],
          "weights_sha256": spec["weights_sha256"], "initialization_seconds": initialization_seconds})
    documents, sources = {}, {}
    for row in pairs.itertuples():
        for accession, text, url in [(row.previous_accession, row.previous_text, row.previous_source_url),
                                     (row.accession, row.current_text, row.source_url)]:
            digest = _sha(text.encode())
            documents[digest] = text
            sources.setdefault(digest, {})[accession] = url
    cache, document_rows = {}, []
    inference_start = time.perf_counter()
    for number, digest in enumerate(sorted(documents), 1):
        vector, receipt = encoder.encode(documents[digest])
        _coverage(vector, receipt, checks)
        if receipt["document_sha256"] != digest:
            raise ValueError("Actual semantic receipt differs from source text")
        cache[digest] = (vector, receipt)
        document_rows.append({**receipt, "embedding_norm": float(np.linalg.norm(vector)),
                              "embedding_dimensions": len(vector),
                              "accessions": sorted(sources[digest]),
                              "source_urls": [sources[digest][key] for key in sorted(sources[digest])]})
        if number % 20 == 0 or number == len(documents):
            print(json.dumps({"stage": "actual_pilot_documents", "completed": number,
                              "total": len(documents), "seconds": time.perf_counter() - inference_start}), flush=True)
    inference_seconds = time.perf_counter() - inference_start
    rows = []
    for row in pairs.itertuples():
        old_sha, new_sha = _sha(row.previous_text.encode()), _sha(row.current_text.encode())
        old, new = cache[old_sha], cache[new_sha]
        rows.append({"observation_id": row.accession, "previous_accession": row.previous_accession,
                     "cik": row.cik, "acceptance_date": row.acceptance_date,
                     "semantic_distance": semantic.cosine_distance(old[0], new[0]),
                     "previous_text_sha256": old_sha, "current_text_sha256": new_sha,
                     "previous_chunks": old[1]["chunks"], "current_chunks": new[1]["chunks"],
                     "previous_tokens": old[1]["content_tokens"], "current_tokens": new[1]["content_tokens"],
                     "tokens_truncated": 0, "source_url": row.source_url,
                     "previous_source_url": row.previous_source_url})
    rechecks = []
    for accession in plan["recheck_observation_ids"]:
        row = pairs.set_index("accession").loc[accession]
        digest = _sha(row.current_text.encode())
        original = cache[digest][0]
        encoder.batch_size = checks["batch_size"]
        repeated, receipt = encoder.encode(row.current_text)
        _coverage(repeated, receipt, checks)
        encoder.batch_size = 1
        one_at_a_time, receipt = encoder.encode(row.current_text)
        _coverage(one_at_a_time, receipt, checks)
        same_error = float(np.max(np.abs(original - repeated)))
        batch_error = float(np.max(np.abs(original - one_at_a_time)))
        passed = (same_error <= checks["same_batch_max_abs_tolerance"]
                  and batch_error <= checks["different_batch_max_abs_tolerance"])
        rechecks.append({"accession": accession, "document_sha256": digest, "source_url": row.source_url,
                         "same_batch_bitwise_equal": bool(np.array_equal(original, repeated)),
                         "same_batch_max_abs_difference": same_error,
                         "batch_1_vs_16_max_abs_difference": batch_error,
                         "unchanged_document_distance": semantic.cosine_distance(original, repeated),
                         "passed": passed})
    encoder.batch_size = checks["batch_size"]
    controls = []
    for example in spec["validation_examples"]:
        old, _ = encoder.encode(example["previous"])
        new, _ = encoder.encode(example["current"])
        distance = semantic.cosine_distance(old, new)
        controls.append({**example, "actual_model_cosine_distance": distance,
                         "input_kind": "CONSTRUCTED_DIAGNOSTIC_EXAMPLE", "reviewer_type": None,
                         "verdict": "pending", "human_review_complete": False})
        if example["id"] == "unchanged" and distance > checks["unchanged_distance_tolerance"]:
            raise ValueError("Actual unchanged-text diagnostic failed")
    if not all(row["passed"] for row in rechecks):
        _json(out / "reproducibility_failure.json", {"checks": checks, "rechecks": rechecks})
        raise ValueError("Actual semantic reproducibility check failed its predeclared tolerance")
    frame = pd.DataFrame(rows)
    frame.to_parquet(out / "semantic_features.parquet", index=False)
    frame.to_csv(out / "semantic_features.csv", index=False)
    pd.DataFrame(document_rows).to_parquet(out / "document_encoding_receipts.parquet", index=False)
    np.savez_compressed(out / "document_embeddings.npz", document_sha256=np.asarray(sorted(cache)),
                        embeddings=np.stack([cache[key][0] for key in sorted(cache)]))
    _json(out / "reproducibility_checks.json", {"checks": checks, "rechecks": rechecks})
    _json(out / "manual_examples.json", {"status": "pending_named_human_review", "examples": controls})
    (out / "semantic_spec.json").write_bytes((Path(package) / "semantic_spec.json").read_bytes())
    distances = frame.semantic_distance
    receipt = {"schema_version": 1, "status": "actual_checkpoint_text_validation_completed",
               "analysis": "RETROSPECTIVE_TEXT_ENCODER_VALIDATION", "data_kind": DATA_KIND,
               "validation_id": plan["validation_id"], "plan_sha256": _sha((Path(package) / "validation_plan.json").read_bytes()),
               "actual_checkpoint_execution": True, "synthetic_encoder_used": False,
               "checkpoint_revision": spec["revision"], "weights_sha256": spec["weights_sha256"],
               "artifact_sha256": spec["artifact_sha256"], "spec_sha256": plan["sources"]["spec"]["sha256"],
               "code_commit": plan["code_commit"], "code_files": plan["code_files"],
               "protocol_sha256": plan["protocol_sha256"], "sources": plan["sources"],
               "source_audit": plan["source_audit"], "rows": len(frame), "unique_documents": len(cache),
               "source_filings": plan["source_audit"]["filings"], "issuers": int(frame.cik.nunique()),
               "year_counts": {str(year): int(count) for year, count in
                               pd.to_datetime(frame.acceptance_date).dt.year.value_counts().sort_index().items()},
               "content_tokens_encoded": sum(row["content_tokens"] for row in document_rows),
               "chunks_encoded": sum(row["chunks"] for row in document_rows), "tokens_truncated": 0,
               "dimensions": 384, "distance_summary": {"minimum": float(distances.min()),
                   "median": float(distances.median()), "p10": float(distances.quantile(.1)),
                   "p90": float(distances.quantile(.9)), "maximum": float(distances.max())},
               "reproducibility_checks_passed": len(rechecks), "numerical_checks": checks,
               "backend": _versions(), "execution": {"cpu_threads": torch.get_num_threads(),
                   "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
                   "model_training": encoder.model.training, "model_device": str(next(encoder.model.parameters()).device),
                   "model_dtype": str(next(encoder.model.parameters()).dtype),
                   "tokenizer_class": type(encoder.tokenizer).__name__},
               "platform": {"python": platform.python_version(),
                   "system": platform.system(), "machine": platform.machine()},
               "runtime_seconds": {"model_initialization_including_cache_access": initialization_seconds,
                   "unique_document_inference": inference_seconds, "total": time.perf_counter() - start},
               "chronology_scope": "retrospective_only", "primary_model_input": False,
               "returns_read": False, "final_period_opened": False, "predictive_performance_claim": False,
               "model_ready": False, "empirical_gate_satisfied": False,
               "human_manual_validation_complete": False, "manual_validation_status": "pending_named_human_review",
               "limitations": ["Purposive parser sample is not the historical investment universe",
                   "Training and fine-tuning data cutoffs are unverified; no historical checkpoint availability claim",
                   "Actual diagnostic results are not named human reviews or semantic-quality validation",
                   "Descriptive semantic distances are not evidence of return predictability"],
               "files": {path.name: _sha(path.read_bytes()) for path in sorted(out.iterdir())}}
    _json(out / "semantic_validation_receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    for name in ("pairs", "filings", "audit", "spec", "output"):
        prepare.add_argument(f"--{name}", required=True)
    prepare.add_argument("--protocol", default="configs/protocol.json")
    run = commands.add_parser("run")
    run.add_argument("--package", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--cache-dir")
    run.add_argument("--local-model-dir")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_validation(args.pairs, args.filings, args.audit, args.spec, args.output,
                                    load_protocol(args.protocol))
        print(json.dumps({"validation_id": result["validation_id"], "source_audit": result["source_audit"]}))
    else:
        result = run_validation(args.package, args.output, cache_dir=args.cache_dir,
                                local_model_dir=args.local_model_dir)
        print(json.dumps({"status": result["status"], "rows": result["rows"],
                          "unique_documents": result["unique_documents"], "runtime_seconds": result["runtime_seconds"]}))


if __name__ == "__main__":
    main()
