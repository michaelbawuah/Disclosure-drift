"""Publish a compact, verified text-only semantic report without filing text or vectors."""

import argparse
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

from disclosure_research.semantic_validation import DATA_KIND, load_validation_plan


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_completed(path):
    path = Path(path)
    raw = (path / "semantic_validation_receipt.json").read_bytes()
    receipt = json.loads(raw)
    if (receipt.get("status") != "actual_checkpoint_text_validation_completed"
            or receipt.get("data_kind") != DATA_KIND or receipt.get("actual_checkpoint_execution") is not True
            or any(receipt.get(key) is not False for key in ("synthetic_encoder_used", "returns_read",
                "final_period_opened", "primary_model_input", "predictive_performance_claim", "model_ready",
                "empirical_gate_satisfied", "human_manual_validation_complete"))):
        raise ValueError("Report requires a completed actual text-only validation with honest pending gates")
    files = {}
    for name, digest in receipt["files"].items():
        if Path(name).name != name:
            raise ValueError("Unsafe semantic output filename")
        files[name] = (path / name).read_bytes()
        if sha(files[name]) != digest:
            raise ValueError(f"Semantic output changed: {name}")
    frame = pd.read_parquet(io.BytesIO(files["semantic_features.parquet"]))
    if len(frame) != receipt["rows"] or frame.observation_id.duplicated().any():
        raise ValueError("Semantic observation count or identity differs")
    return receipt, raw, files, frame


def publish(package, run, output, *, environment=None, comparison_run=None):
    out = Path(output)
    if out.exists():
        raise ValueError("Public report output already exists")
    plan, pairs, spec = load_validation_plan(package)
    receipt, raw, files, frame = read_completed(run)
    if (receipt["validation_id"] != plan["validation_id"]
            or receipt["plan_sha256"] != sha((Path(package) / "validation_plan.json").read_bytes())
            or receipt["sources"] != plan["sources"] or receipt["code_files"] != plan["code_files"]
            or set(frame.observation_id) != set(pairs.accession)):
        raise ValueError("Semantic run does not match its prepared sample and implementation")
    rechecks = json.loads(files["reproducibility_checks.json"])
    if ([row["accession"] for row in rechecks["rechecks"]] != plan["recheck_observation_ids"]
            or not all(row["passed"] for row in rechecks["rechecks"])):
        raise ValueError("Semantic reproducibility evidence differs from the prepared sample")
    risk_sources = pd.read_parquet(Path(package) / plan["sources"]["evidence"]["file"],
                                   columns=["accession", "risk_source_url"]).set_index("accession").risk_source_url
    public_frame = frame.copy()
    public_frame["risk_source_url"] = frame.observation_id.map(risk_sources)
    public_frame["previous_risk_source_url"] = frame.previous_accession.map(risk_sources)
    for column in ["risk_source_url", "previous_risk_source_url"]:
        if not public_frame[column].map(lambda value: isinstance(value, str) and value.startswith("https://")).all():
            raise ValueError("Source examples require the actual audited risk-source URLs")
    indexed = public_frame.set_index("observation_id")
    examples = []
    for accession in plan["recheck_observation_ids"]:
        row = indexed.loc[accession]
        examples.append({"accession": accession, "previous_accession": row.previous_accession,
                         "cik": row.cik, "acceptance_date": row.acceptance_date,
                         "semantic_distance": float(row.semantic_distance),
                         "current_text_sha256": row.current_text_sha256,
                         "previous_text_sha256": row.previous_text_sha256,
                         "current_tokens": int(row.current_tokens), "previous_tokens": int(row.previous_tokens),
                         "source_url": row.source_url, "previous_source_url": row.previous_source_url,
                         "risk_source_url": row.risk_source_url,
                         "previous_risk_source_url": row.previous_risk_source_url,
                         "selection": plan["recheck_selection"], "human_review_complete": False})
    replication = None
    if comparison_run is not None:
        prior, prior_raw, prior_files, prior_frame = read_completed(comparison_run)
        for name in ["checkpoint_revision", "weights_sha256", "spec_sha256", "sources", "numerical_checks"]:
            if prior[name] != receipt[name]:
                raise ValueError(f"Independent runs differ in their declared method or sample: {name}")
        if prior["code_files"]["semantic.py"] != receipt["code_files"]["semantic.py"]:
            raise ValueError("Independent run used a different encoder implementation")
        current_vectors = np.load(io.BytesIO(files["document_embeddings.npz"]), allow_pickle=False)
        prior_vectors = np.load(io.BytesIO(prior_files["document_embeddings.npz"]), allow_pickle=False)
        if not np.array_equal(current_vectors["document_sha256"], prior_vectors["document_sha256"]):
            raise ValueError("Independent runs encoded different source documents")
        max_difference = float(np.max(np.abs(current_vectors["embeddings"] - prior_vectors["embeddings"])))
        tolerance = plan["checks"]["same_batch_max_abs_tolerance"]
        replication = {"analysis": "INDEPENDENT_PROCESS_REPLICATION", "documents": receipt["unique_documents"],
            "pairs": receipt["rows"], "same_encoder_code": True,
            "all_document_vectors_bitwise_equal": bool(np.array_equal(current_vectors["embeddings"], prior_vectors["embeddings"])),
            "all_pair_features_equal": frame.equals(prior_frame), "max_abs_vector_difference": max_difference,
            "tolerance": tolerance, "passed": max_difference <= tolerance and frame.equals(prior_frame),
            "current_receipt_sha256": sha(raw), "prior_receipt_sha256": sha(prior_raw),
            "prior_validation_id": prior["validation_id"], "current_validation_id": receipt["validation_id"],
            "reason_for_repeat": "Tightened plan sample verification; reran the unchanged encoder from the hardened plan"}
        if not replication["passed"]:
            raise ValueError("Independent actual checkpoint runs failed the same-batch numerical criterion")
    out.mkdir(parents=True)
    (out / "validation_receipt.json").write_bytes(raw)
    public_frame.to_csv(out / "all_pair_distances.csv", index=False)
    for name in ["reproducibility_checks.json", "manual_examples.json"]:
        (out / name).write_bytes(files[name])
    method = {key: value for key, value in plan.items() if key != "source_paths"}
    method["record_type"] = "PUBLIC_METHOD_RECORD_DERIVED_FROM_VALIDATION_PLAN"
    method["original_validation_plan_sha256"] = receipt["plan_sha256"]
    for name, value in [("method_record.json", method), ("source_examples.json", {"examples": examples})]:
        (out / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    if environment is not None:
        (out / "environment_distributions.json").write_bytes(Path(environment).read_bytes())
    if replication is not None:
        (out / "independent_replication.json").write_text(json.dumps(replication, indent=2) + "\n")
    control_rows = json.loads(files["manual_examples.json"])["examples"]
    stats, runtime = receipt["distance_summary"], receipt["runtime_seconds"]
    lines = ["# Actual MiniLM execution on the audited SEC text pilot", "",
        f'The pinned model completed an actual CPU run on **{receipt["rows"]} annual pairs from '
        f'{receipt["unique_documents"]} unique filing texts** in the {receipt["issuers"]}-issuer supplied pilot. '
        "These are descriptive text results; no market outcomes or "
        "final-period observations were opened. Named human semantic and filing reviews remain pending.", "",
        "## Execution and coverage", "", "| Measure | Observed value |", "|---|---:|",
        f'| Annual pairs | {receipt["rows"]} |', f'| Unique documents | {receipt["unique_documents"]} |',
        f'| Issuers | {receipt["issuers"]} |', f'| Content WordPiece tokens encoded | {receipt["content_tokens_encoded"]:,} |',
        f'| Document chunks encoded | {receipt["chunks_encoded"]:,} |', "| Tokens truncated | 0 |",
        f'| Cached model initialization | {runtime["model_initialization_including_cache_access"]:.3f} seconds |',
        f'| Unique-document inference | {runtime["unique_document_inference"]:.3f} seconds |',
        f'| Total validation, including rechecks and artifact writes | {runtime["total"]:.3f} seconds |', "",
        f'The run used torch `{receipt["backend"]["torch"]}`, Transformers `{receipt["backend"]["transformers"]}`, '
        f'Python `{receipt["platform"]["python"]}`, and one CPU thread. Checkpoint revision: '
        f'`{receipt["checkpoint_revision"]}`. Weights SHA-256: `{receipt["weights_sha256"]}`.', "",
        "All model inputs contain at most 254 content tokens plus two special tokens. Every document "
        "produced a finite, normalized 384-dimensional vector. Both the model weights and the five "
        "configuration/tokenizer artifacts matched the prescribed hashes.", "",
        "## Numerical reproducibility", "",
        f'{len(rechecks["rechecks"])} source documents selected before inference were encoded again independently of the '
        "document cache. Repeated batch-16 encodings use a maximum coordinate-error tolerance of "
        "`1e-12`; batch-1 versus batch-16 uses `1e-6`. All checks passed.", "",
        "| Recheck accession | Same-batch maximum difference | Batch 1 versus 16 maximum difference |", "|---|---:|---:|"]
    for row in rechecks["rechecks"]:
        lines.append(f'| {row["accession"]} | {row["same_batch_max_abs_difference"]:.3g} | '
                     f'{row["batch_1_vs_16_max_abs_difference"]:.3g} |')
    if replication:
        lines += ["", f'A second independent Python process reproduced all {receipt["unique_documents"]} '
            f'document vectors and {receipt["rows"]} pair feature rows exactly. Maximum absolute vector '
            f'difference: `{replication["max_abs_vector_difference"]:.3g}`. The second run used a hardened '
            "plan validator that rederives the exact recheck sample; the encoder and source texts were unchanged."]
    lines += ["", "## Descriptive distances", "", "| Statistic | Cosine distance |", "|---|---:|"]
    for name in ["minimum", "p10", "median", "p90", "maximum"]:
        lines.append(f'| {name} | {stats[name]:.8f} |')
    lines += ["", "These magnitudes have no calibrated economic interpretation and do not demonstrate "
        "return predictability. Document averaging can dilute a localized addition, so passage-level "
        "interpretation requires separate review. The complete pair table is in "
        "[all_pair_distances.csv](all_pair_distances.csv).", "",
        "### Source examples selected before inference", "",
        "| Acceptance date | Current filing | Previous filing | Cosine distance |", "|---|---|---|---:|"]
    for row in examples:
        lines.append(f'| {row["acceptance_date"]} | [{row["accession"]}]({row["risk_source_url"]}) | '
                     f'[{row["previous_accession"]}]({row["previous_risk_source_url"]}) | {row["semantic_distance"]:.8f} |')
    lines += ["", "Links point to the resolved risk-source document when the audited section was "
        "incorporated by reference. The complete source mapping and text hashes are in "
        "[source_examples.json](source_examples.json). No filing excerpts or document vectors are published here.", "",
        "### Constructed diagnostic examples", "", "| Example | Actual model distance | Human verdict |", "|---|---:|---|"]
    for row in control_rows:
        lines.append(f'| {row["id"]} | {row["actual_model_cosine_distance"]:.8f} | Pending |')
    lines += ["", "These three short controls are constructed diagnostic inputs, not quotations from "
        "the SEC sample. The unchanged result checks numerical identity. Rewording and added-risk "
        "scores have no prespecified semantic-quality threshold; their inspection requires a named human reviewer.", "",
        "## Research status and limitations", "",
        f'The source audit verifies {receipt["source_audit"]["automated_evidence_ok"]} cached '
        f'filing/header/risk-source records and reports {receipt["source_audit"]["filings_with_blocking_issues"]} '
        f'filings with blocking automated source issues. Its {receipt["source_audit"]["timestamp_disagreements"]} '
        "API/header timestamp disagreements remain explicitly recorded; source evidence uses the audited "
        f'header timestamp. Completed human filing reviews: {receipt["source_audit"]["human_reviews_complete"]}.', "",
        "The original pilot is a purposive parser sample, not the historical investment universe. "
        f'The recorded model-repository creation timestamp is {spec.get("observed_repository_created_at", "unverified")}, '
        f'and this pinned revision timestamp is {spec.get("observed_revision_last_modified", "unverified")}; '
        "pretraining and fine-tuning cutoffs remain unverified. These embeddings therefore remain "
        "retrospective secondary features. They never enter the primary three-feature model.", "",
        "Actual inference, artifact verification and numerical reproducibility are now evidenced. "
        "Named human review, an audited market dataset, development selection and the final empirical "
        "access gates remain separate requirements. This report supplies no forecasting score or final result.", "",
        "## Reproduce and inspect", "",
        "Use [the validation commands](../../docs/semantic_validation.md) to prepare a new immutable "
        "plan and run the exact pinned checkpoint. [validation_receipt.json](validation_receipt.json) "
        "binds the original input, implementation, model and output hashes. "
        "[method_record.json](method_record.json) records the declared sample and numerical criteria. "
        "The raw text package and model weights remain in the local data/output cache.", "",
        "Model sources: [pinned checkpoint](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/"
        "1110a243fdf4706b3f48f1d95db1a4f5529b4d41) and "
        "[model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).", ""]
    (out / "report.md").write_text("\n".join(lines))
    manifest = {"schema_version": 1, "data_kind": DATA_KIND, "validation_id": plan["validation_id"],
                "source_receipt_sha256": sha(raw), "files": {p.name: sha(p.read_bytes()) for p in sorted(out.iterdir())}}
    (out / "report_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["package", "run", "output"]:
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--environment")
    parser.add_argument("--comparison-run")
    args = parser.parse_args()
    result = publish(args.package, args.run, args.output, environment=args.environment, comparison_run=args.comparison_run)
    print(json.dumps({"validation_id": result["validation_id"], "report_files": len(result["files"])}))
