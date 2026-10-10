"""Pinned retrospective semantic distances with complete token coverage.

This secondary comparator never participates in primary feature selection.
Transformer dependencies are optional: ``uv sync --extra semantic``.
"""

import hashlib
import json
import re
from pathlib import Path

import numpy as np


def token_chunks(tokens: list[int], content_tokens: int = 254) -> list[list[int]]:
    if isinstance(content_tokens, bool) or not isinstance(content_tokens, int) or content_tokens < 1:
        raise ValueError("Chunk size must be a positive integer")
    if not tokens:
        raise ValueError("Empty semantic input is excluded")
    return [tokens[i:i + content_tokens] for i in range(0, len(tokens), content_tokens)]


def bert_chunk_inputs(chunk: list[int], cls_token_id: int, sep_token_id: int) -> dict:
    """Wrap existing WordPiece IDs without decoding or tokenizing them again.

    Transformers 5 removed ``prepare_for_model`` from its Rust-backed tokenizer
    interface. The pinned BERT single-sequence layout is checked against the
    tokenizer's native output when the encoder loads.
    """
    ids = [cls_token_id, *chunk, sep_token_id]
    return {"input_ids": ids, "token_type_ids": [0] * len(ids), "attention_mask": [1] * len(ids)}


def aggregate_chunks(embeddings, token_counts) -> np.ndarray:
    vectors, counts = np.asarray(embeddings, dtype=float), np.asarray(token_counts, dtype=float)
    if (vectors.ndim != 2 or len(vectors) == 0 or counts.shape != (len(vectors),)
            or not np.isfinite(vectors).all() or not np.isfinite(counts).all() or (counts <= 0).any()):
        raise ValueError("Invalid semantic chunk vectors or token counts")
    norms = np.linalg.norm(vectors, axis=1)
    if (norms == 0).any():
        raise ValueError("Zero semantic chunk vector")
    mean = np.average(vectors / norms[:, None], weights=counts, axis=0)
    norm = np.linalg.norm(mean)
    if norm == 0:
        raise ValueError("Zero semantic document vector")
    return mean / norm


def cosine_distance(previous, current) -> float:
    a, b = np.asarray(previous, dtype=float), np.asarray(current, dtype=float)
    if a.ndim != 1 or a.shape != b.shape or not len(a) or not np.isfinite([a, b]).all():
        raise ValueError("Semantic document vectors must be aligned and finite")
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    if denominator == 0:
        raise ValueError("Zero semantic document vector")
    return float(np.clip(1 - np.dot(a, b) / denominator, 0, 2))


def validate_spec(spec: dict) -> None:
    if (spec.get("schema_version") != 1 or spec.get("primary_model_input") is not False
            or spec.get("chronology_scope") != "retrospective_only"):
        raise ValueError("Semantic comparator requires explicit retrospective secondary status")
    if (spec.get("model_id") != "sentence-transformers/all-MiniLM-L6-v2"
            or spec.get("pooling") != "attention_mask_mean_including_special_tokens"
            or spec.get("precision") != "float32_cpu_eval"
            or spec.get("max_model_tokens") != 256):
        raise ValueError("Semantic architecture, pooling, precision or sequence limit changed")
    if (spec.get("training_data_cutoff_verified") is not False
            or spec.get("fine_tuning_cutoff_verified") is not False
            or spec.get("checkpoint_historical_availability_claim") is not False):
        raise ValueError("This retrospective checkpoint has no verified historical availability or training cutoff")
    if not re.fullmatch(r"[0-9a-f]{40}", spec.get("revision", "")):
        raise ValueError("Pin the exact semantic checkpoint revision")
    if not re.fullmatch(r"[0-9a-f]{64}", spec.get("weights_sha256", "")):
        raise ValueError("Pin the semantic weights SHA-256")
    if spec.get("chunking") != {"content_tokens": 254, "special_tokens": 2, "overlap": 0,
                                "truncate": False, "aggregation": "content_token_weighted_normalized_mean"}:
        raise ValueError("Semantic chunking specification changed")
    files = spec.get("artifact_sha256", {})
    required = {"config.json", "tokenizer.json", "tokenizer_config.json", "vocab.txt", "special_tokens_map.json"}
    if set(files) != required or any(not re.fullmatch(r"[0-9a-f]{64}", s) for s in files.values()):
        raise ValueError("Pin every semantic configuration and tokenizer file")


class PinnedSemanticEncoder:
    """CPU, evaluation mode, safetensors-only; no remote model code or truncation."""

    def __init__(self, spec: dict, cache_dir=None, batch_size: int = 16, *, local_model_dir=None):
        validate_spec(spec)
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        try:
            import torch
            from huggingface_hub import snapshot_download
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("Install the pinned semantic extra: uv sync --extra semantic") from exc
        names = ["model.safetensors"] + list(spec["artifact_sha256"])
        location = (Path(local_model_dir) if local_model_dir is not None else
                    Path(snapshot_download(repo_id=spec["model_id"], revision=spec["revision"],
                                           allow_patterns=names, cache_dir=cache_dir)))
        expected = {**spec["artifact_sha256"], "model.safetensors": spec["weights_sha256"]}
        for name, digest in expected.items():
            if hashlib.sha256((location / name).read_bytes()).hexdigest() != digest:
                raise ValueError(f"Semantic checkpoint artifact changed: {name}")
        self.tokenizer = AutoTokenizer.from_pretrained(location, local_files_only=True, trust_remote_code=False)
        if self.tokenizer.num_special_tokens_to_add(pair=False) != 2:
            raise ValueError("Tokenizer special-token layout differs from frozen specification")
        if (self.tokenizer.cls_token_id, self.tokenizer.sep_token_id, self.tokenizer.pad_token_id) != (101, 102, 0):
            raise ValueError("Pinned BERT special-token identifiers differ")
        probe = "Verify the pinned single sequence token layout."
        content = self.tokenizer.encode(probe, add_special_tokens=False, truncation=False)
        if dict(self.tokenizer(probe, add_special_tokens=True, truncation=False)) != bert_chunk_inputs(content, 101, 102):
            raise ValueError("Pinned BERT chunk layout differs from native tokenizer processing")
        self.model = AutoModel.from_pretrained(location, local_files_only=True,
                                               trust_remote_code=False, use_safetensors=True).float().cpu().eval()
        self.torch, self.spec, self.batch_size, self.location = torch, spec, batch_size, location

    def encode(self, text: str) -> tuple[np.ndarray, dict]:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Empty semantic input is excluded")
        ids = self.tokenizer.encode(text, add_special_tokens=False, truncation=False)
        chunks = token_chunks(ids, self.spec["chunking"]["content_tokens"])
        vectors = []
        with self.torch.inference_mode():
            for start in range(0, len(chunks), self.batch_size):
                rows = [bert_chunk_inputs(chunk, self.tokenizer.cls_token_id, self.tokenizer.sep_token_id)
                        for chunk in chunks[start:start + self.batch_size]]
                batch = self.tokenizer.pad(rows, padding=True, return_tensors="pt")
                if batch["input_ids"].shape[1] > 256:
                    raise ValueError("Semantic sequence exceeds its frozen maximum")
                hidden = self.model(**batch).last_hidden_state
                mask = batch["attention_mask"].unsqueeze(-1)
                pooled = (hidden * mask).sum(1) / mask.sum(1)
                vectors.extend(pooled.cpu().numpy())
        counts = [len(chunk) for chunk in chunks]
        if sum(counts) != len(ids):
            raise ValueError("Semantic document token coverage is incomplete")
        return aggregate_chunks(vectors, counts), {"content_tokens": len(ids), "chunks": len(chunks),
                 "tokens_encoded": sum(counts), "tokens_truncated": 0,
                 "document_sha256": hashlib.sha256(text.encode()).hexdigest(),
                 "checkpoint_revision": self.spec["revision"], "chronology_scope": "retrospective_only"}


def compute_semantic_pairs(pairs, spec_path, output, *, cache_dir=None) -> dict:
    """Write a separate retrospective feature table; never silently join to primary."""
    import pandas as pd

    out = Path(output)
    if out.exists():
        raise ValueError("Output exists; preserve previous semantic outputs")
    if pairs.empty or not {"observation_id", "previous_text", "current_text"}.issubset(pairs.columns):
        raise ValueError("Semantic pairs are missing required fields")
    if pairs.observation_id.isna().any() or pairs.observation_id.duplicated().any():
        raise ValueError("Semantic observations must have distinct identifiers")
    spec_raw = Path(spec_path).read_bytes()
    spec = json.loads(spec_raw)
    encoder = PinnedSemanticEncoder(spec, cache_dir)
    rows = []
    cache = {}
    for row in pairs.itertuples():
        embedded = []
        for text in [row.previous_text, row.current_text]:
            digest = hashlib.sha256(text.encode()).hexdigest()
            if digest not in cache:
                cache[digest] = encoder.encode(text)
            embedded.append(cache[digest])
        rows.append({"observation_id": row.observation_id,
                     "semantic_distance": cosine_distance(embedded[0][0], embedded[1][0]),
                     "previous_text_sha256": embedded[0][1]["document_sha256"],
                     "current_text_sha256": embedded[1][1]["document_sha256"],
                     "previous_chunks": embedded[0][1]["chunks"], "current_chunks": embedded[1][1]["chunks"],
                     "previous_tokens": embedded[0][1]["content_tokens"], "current_tokens": embedded[1][1]["content_tokens"],
                     "tokens_truncated": 0})
    out.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(out / "semantic_features.parquet", index=False)
    receipt = {"schema_version": 1, "analysis": "RETROSPECTIVE_SEMANTIC_SECONDARY",
               "primary_model_input": False, "rows": len(rows), "unique_documents": len(cache),
               "data_kind": pairs.attrs.get("data_kind", "UNCLASSIFIED_INPUT"),
               "checkpoint_revision": spec["revision"], "weights_sha256": spec["weights_sha256"],
               "spec_sha256": hashlib.sha256(spec_raw).hexdigest(),
               "features_sha256": hashlib.sha256((out / "semantic_features.parquet").read_bytes()).hexdigest(),
               "tokens_truncated": 0, "chronology_scope": "retrospective_only"}
    (out / "semantic_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt
