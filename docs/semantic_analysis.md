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

## Actual text-only execution and remaining review

The actual pinned MiniLM weights have now executed on the original audited
20-issuer SEC text pilot: 135 annual pairs from 155 unique documents. The run
encoded all 1,459,865 WordPiece content tokens in 5,828 chunks with zero
truncation. Three preselected real documents passed repeated-encoding and
batch-size agreement checks. This is evidence of backend execution and
numerical reproducibility, with no market outcomes opened or forecast model fit.

The [execution report](../reports/semantic_validation/report.md) contains the
source-bound distances, artifact hashes, exact runtime, environment and
reproducibility evidence. [Reproduction commands](semantic_validation.md) cover
the ordinary semantic extra, the isolated CPU environment and an offline
hash-verified snapshot. Real execution also exposed and corrected a Transformers
5 tokenizer compatibility bug; the intended complete-token method is unchanged.

The unchanged, rewording and new-risk diagnostic examples have actual model
scores. Their named human reviews remain pending, as do the filing reviews and
audited market-data prerequisites. Record the reviewer's evidence and chronology
judgment before empirical access. Assistant checks do not supply that judgment,
and this text-only result does not satisfy the empirical freeze or establish
semantic forecast performance.
