# Retrospective semantic comparison

This is a separate secondary comparison. It cannot alter the three-feature
primary model or support a claim that these model weights were available at
historical prediction times.

## Pinned artifacts and chronology

| Field | Frozen method record |
|---|---|
| Model | `sentence-transformers/all-MiniLM-L6-v2` |
| Revision | `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` |
| Safetensors SHA-256 | `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db` |
| Configuration/tokenizer | Every required file hashed in `configs/semantic_retrospective.json` |
| Observed repository creation | March 2, 2022 |
| Observed revision timestamp | June 1, 2026; not proof of the original training date |
| Verified pretraining/fine-tuning cutoffs | Unknown |
| Permitted interpretation | Retrospective secondary; no historical availability claim |

Primary sources: the [pinned Hugging Face checkpoint](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/1110a243fdf4706b3f48f1d95db1a4f5529b4d41)
and [model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).
The repository metadata does not establish when each training document was
available. Unknown cutoffs remain unknown.

## Encoding rule

The encoder downloads only the exact pinned safetensors and tokenizer/config
files, verifies their hashes, disables remote model code, and uses CPU float32
evaluation mode. Every document is tokenized without truncation and split into
nonoverlapping chunks of at most 254 content tokens plus two special tokens.

For each chunk, attention-mask mean pooling includes the special tokens but
excludes padding. Normalize each chunk vector, average with content-token-count
weights, and normalize the resulting document vector. Cosine distance between
the two document vectors is the separate semantic change feature. Empty text,
zero vectors and nonfinite values are explicit errors.

The receipt records complete token coverage, zero truncated tokens, checkpoint
identity, feature-file hashes, and current/previous document hashes. The model
stage checks these hashes against the actual dataset text and exact event IDs.

## Commands and model rule

```bash
uv run --locked --extra semantic disclosure semantic-features \
  --dataset data/processed/development --output outputs/semantic-development

uv run --locked disclosure semantic-develop \
  --bundle data/processed/development --features outputs/semantic-development \
  --output outputs/semantic-selection
```

The secondary model adds one numeric semantic distance to the same controls.
It uses the same four ridge penalties, annual development folds, training-label
maturity and train-only scaling/industry encoding as the primary comparison.
Select its penalty on development only.

Final semantic features require an audited holdout bundle and
`semantic-features --partition holdout --prerequisites-request ...`.
Bind the semantic specification, both feature files/receipts, development
selection and predictions to `secondary.semantic.model_comparison` before the
primary freeze. The final secondary runner requires that exact completed primary
run and reuses its saved baseline and targets:

```bash
uv run --locked disclosure semantic-evaluate-final \
  --final-run outputs/final-evaluation --freeze outputs/development-freeze \
  --output outputs/semantic-final
```

## What remains unverified

The checkpoint metadata and configuration hashes were retrieved. Chunking,
aggregation and model orchestration are exercised by synthetic tests. The
actual MiniLM model has **not** been executed in this build, so no runtime,
empirical semantic distance or semantic forecast result is claimed.

Before empirical access, execute and inspect the fixed unchanged, rewording
and new-risk examples; record the named reviewer's evidence and chronology
judgment. Assistant checks cannot supply the required human judgment. The
pending manual template and development choices intentionally block the real
freeze.
