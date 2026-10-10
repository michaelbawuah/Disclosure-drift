# Actual MiniLM validation on the SEC text pilot

The standalone validator executes the exact pinned MiniLM checkpoint on audited
development-period filing text. It produces descriptive distances, complete
token-coverage receipts, saved document vectors, and numerical reproducibility
checks. It accepts no return table and does not fit a market-outcome model.

The encoder remains a retrospective secondary method. Its checkpoint and unknown
training-data cutoffs cannot establish historical availability. Source audits
and numerical checks do not supply the named human review required by the
research freeze.

## Prepare the source-bound plan

```bash
uv run --locked python -m disclosure_research.semantic_validation prepare \
  --pairs data/processed/pilot-resolved/filing_pairs.parquet \
  --filings data/processed/pilot-resolved/filings.parquet \
  --audit outputs/audit-pilot-recovered \
  --spec configs/semantic_retrospective.json \
  --output outputs/semantic-validation-plan
```

Preparation checks the Parquet schemas for outcome-bearing columns, verifies the
source-audit table fingerprints, and checks acceptance dates before deserializing
filing text. Both current and predecessor source evidence must remain in the
development period. Every pair must match its audited issuer, accession, text
hash and source URL. Review counts are recomputed from the bound evidence rows.

The package copies the exact source artifacts and records their hashes, the
unchanged primary protocol hash, the base Git commit, and hashes of the actual
implementation files. Its numerical checks and outcome-free recheck sample are
set before inference. Reusing an existing output directory is an error.

## Run the actual checkpoint

On a machine using the normal semantic extra:

```bash
uv run --locked --extra semantic python -m disclosure_research.semantic_validation run \
  --package outputs/semantic-validation-plan \
  --output outputs/semantic-validation \
  --cache-dir data/raw/semantic-model-cache
```

The first run downloads only the exact checkpoint's safetensors weights and five
configuration/tokenizer artifacts. Every file must match its pinned SHA-256.
`trust_remote_code=False`, local-only model loading after verification, CPU
float32, evaluation mode and deterministic algorithms are required.

To use an already downloaded snapshot without network access, replace
`--cache-dir` with:

```bash
--local-model-dir data/raw/semantic-model-cache/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41
```

The same artifact-hash checks apply to the local directory. There is no synthetic
fallback if the backend, model download, artifact verification or inference fails.

### Isolated CPU installation used for the 2026-10-10 execution

The Linux runtime used a separate CPU environment so the ordinary project
environment remained unchanged. The two package-index steps are intentional:
the PyTorch CPU index supplies its wheel; the following step resolves the
transformer and project packages against the normal package index using the
repository's locked constraints.

```bash
uv venv outputs/semantic-runtime/.venv --python 3.12

uv pip install --python outputs/semantic-runtime/.venv/bin/python \
  --index https://download.pytorch.org/whl/cpu 'torch==2.14.1'

uv export --locked --extra semantic --no-emit-project --no-hashes \
  --format requirements-txt \
  --output-file outputs/semantic-runtime/locked-constraints.txt

uv pip install --python outputs/semantic-runtime/.venv/bin/python \
  -c outputs/semantic-runtime/locked-constraints.txt \
  'transformers==5.19.0' -e .

outputs/semantic-runtime/.venv/bin/python -m disclosure_research.semantic_validation run \
  --package outputs/semantic-validation-plan \
  --output outputs/semantic-validation \
  --cache-dir data/raw/semantic-model-cache
```

The execution receipt records the actually installed model, tokenizer, array and
table-library versions. The CPU wheel's local version suffix is reported as
`2.14.1+cpu`; it is not represented as the GPU build. Runtime measurements include
the observed machine and single-thread setting and are not universal speed claims.
The timed total starts immediately before model construction and includes
inference, numerical rechecks and artifact creation. Python startup and the prior
source-plan validation are outside that timer.

## What the numerical checks establish

| Check | Prespecified rule |
|---|---|
| WordPiece coverage | Every full-document content token encoded exactly once; zero truncated tokens |
| Chunk size | At most 254 content tokens plus `[CLS]` and `[SEP]`; model input at most 256 tokens |
| Document vector | 384 finite dimensions; unit-norm absolute error at most `1e-12` |
| Recheck sample | Lowest SHA-256 of `protocol seed:accession` in first, middle and last acceptance years |
| Repeated encoding | Same document, same batch size: maximum absolute coordinate difference at most `1e-12` |
| Batch-size agreement | The same document in batches of 1 versus 16 chunks: maximum difference at most `1e-6` |
| Unchanged control | Cosine distance at most `1e-12` |
| Rewording and added-risk controls | Actual scores recorded; no score threshold or automatic semantic-quality verdict |

Complete-text tokenization can emit the library's advisory about exceeding the
model's nominal sequence length. The encoder never sends that unsplit sequence
to the model: it verifies each actual model input is at most 256 tokens. Coverage
is checked against the complete token stream, not against a truncated prefix.

### Transformers 5 compatibility correction

The first real invocation found that Transformers 5's Rust-backed BERT tokenizer
does not expose the earlier `prepare_for_model` method. The correction wraps the
already produced WordPiece IDs in the pinned BERT single-sequence layout and
constructs the attention mask and token-type IDs directly. It does not decode and
retokenize chunks. At initialization, this construction must match the native
tokenizer output on a fixed probe, and the special-token IDs must be exactly
101, 102 and 0. The token-preservation regression test covers 2,037 content IDs
across multiple chunks.

See the upstream [Transformers 5 migration guide](https://github.com/huggingface/transformers/blob/main/MIGRATION_GUIDE_V5.md)
and the repository's pinned [checkpoint](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/1110a243fdf4706b3f48f1d95db1a4f5529b4d41).

## Outputs and interpretation

The run writes:

- `semantic_features.parquet` and `.csv`: one distance per source-bound annual pair.
- `document_encoding_receipts.parquet`: token counts, chunk counts, vector dimensions,
  text hashes, accessions and source URLs for every unique text.
- `document_embeddings.npz`: normalized vectors keyed by document hash.
- `reproducibility_checks.json`: the selected real documents and observed numerical errors.
- `manual_examples.json`: actual scores on the three constructed diagnostic examples,
  with named human reviews still pending.
- `semantic_validation_receipt.json`: source, code, model, environment and output hashes;
  completed checks and measured runtime.

Full filing text and vectors stay in the reproducible local package. Public
reporting uses counts, hashes, source links and descriptive statistics, with no
long source excerpts. Descriptive distance magnitudes do not have a calibrated
economic interpretation and do not demonstrate predictive performance. The
receipt keeps `returns_read`, `final_period_opened`, `primary_model_input`,
`model_ready` and `empirical_gate_satisfied` false.

The compact public report can be regenerated from the completed run without
copying filing text or embedding vectors:

```bash
uv run --locked python scripts/publish_semantic_validation.py \
  --package outputs/semantic-validation-plan \
  --run outputs/semantic-validation \
  --output reports/semantic_validation
```

An optional `--comparison-run` accepts another completed actual run of the same
source texts, pinned model and encoder. It compares all saved document vectors
and pair feature rows across independent processes. A comparison failure is
reported as an error and cannot be silently presented as successful replication.
