# Actual MiniLM execution on the audited SEC text pilot

The pinned model completed an actual CPU run on **135 annual pairs from 155 unique filing texts** in the 20-issuer supplied pilot. These are descriptive text results; no market outcomes or final-period observations were opened. Named human semantic and filing reviews remain pending.

## Execution and coverage

| Measure | Observed value |
|---|---:|
| Annual pairs | 135 |
| Unique documents | 155 |
| Issuers | 20 |
| Content WordPiece tokens encoded | 1,459,865 |
| Document chunks encoded | 5,828 |
| Tokens truncated | 0 |
| Cached model initialization | 1.522 seconds |
| Unique-document inference | 468.774 seconds |
| Total validation, including rechecks and artifact writes | 487.606 seconds |

The run used torch `2.14.1+cpu`, Transformers `5.19.0`, Python `3.12.14`, and one CPU thread. Checkpoint revision: `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Weights SHA-256: `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db`.

All model inputs contain at most 254 content tokens plus two special tokens. Every document produced a finite, normalized 384-dimensional vector. Both the model weights and the five configuration/tokenizer artifacts matched the prescribed hashes.

## Numerical reproducibility

3 source documents selected before inference were encoded again independently of the document cache. Repeated batch-16 encodings use a maximum coordinate-error tolerance of `1e-12`; batch-1 versus batch-16 uses `1e-6`. All checks passed.

| Recheck accession | Same-batch maximum difference | Batch 1 versus 16 maximum difference |
|---|---:|---:|
| 0000050863-15-000015 | 0 | 0 |
| 0000080424-18-000055 | 0 | 4.74e-09 |
| 0000021344-21-000008 | 0 | 1.33e-09 |

A second independent Python process reproduced all 155 document vectors and 135 pair feature rows exactly. Maximum absolute vector difference: `0`. The second run used a hardened plan validator that rederives the exact recheck sample; the encoder and source texts were unchanged.

## Descriptive distances

| Statistic | Cosine distance |
|---|---:|
| minimum | 0.00093841 |
| p10 | 0.00268151 |
| median | 0.00632819 |
| p90 | 0.01756768 |
| maximum | 0.10261717 |

These magnitudes have no calibrated economic interpretation and do not demonstrate return predictability. Document averaging can dilute a localized addition, so passage-level interpretation requires separate review. The complete pair table is in [all_pair_distances.csv](all_pair_distances.csv).

### Source examples selected before inference

| Acceptance date | Current filing | Previous filing | Cosine distance |
|---|---|---|---:|
| 2015-02-13 | [0000050863-15-000015](https://www.sec.gov/Archives/edgar/data/50863/000005086315000015/a10kdocument12272014.htm) | [0000050863-14-000020](https://www.sec.gov/Archives/edgar/data/50863/000005086314000020/a10kdocument12282013.htm) | 0.01160099 |
| 2018-08-07 | [0000080424-18-000055](https://www.sec.gov/Archives/edgar/data/80424/000008042418000055/fy171810-kreport.htm) | [0000080424-17-000047](https://www.sec.gov/Archives/edgar/data/80424/000008042417000047/fy161710-kreport.htm) | 0.01191953 |
| 2021-02-25 | [0000021344-21-000008](https://www.sec.gov/Archives/edgar/data/21344/000002134421000008/ko-20201231.htm) | [0000021344-20-000006](https://www.sec.gov/Archives/edgar/data/21344/000002134420000006/a2019123110-k.htm) | 0.00697729 |

Links point to the resolved risk-source document when the audited section was incorporated by reference. The complete source mapping and text hashes are in [source_examples.json](source_examples.json). No filing excerpts or document vectors are published here.

### Constructed diagnostic examples

| Example | Actual model distance | Human verdict |
|---|---:|---|
| unchanged | 0.00000000 | Pending |
| rewording | 0.30430815 | Pending |
| new_risk | 0.31481497 | Pending |

These three short controls are constructed diagnostic inputs, not quotations from the SEC sample. The unchanged result checks numerical identity. Rewording and added-risk scores have no prespecified semantic-quality threshold; their inspection requires a named human reviewer.

## Research status and limitations

The source audit verifies 155 cached filing/header/risk-source records and reports 0 filings with blocking automated source issues. Its 72 API/header timestamp disagreements remain explicitly recorded; source evidence uses the audited header timestamp. Completed human filing reviews: 0.

The original pilot is a purposive parser sample, not the historical investment universe. The recorded model-repository creation timestamp is 2022-03-02T23:29:05.000Z, and this pinned revision timestamp is 2026-06-01T06:29:13.000Z; pretraining and fine-tuning cutoffs remain unverified. These embeddings therefore remain retrospective secondary features. They never enter the primary three-feature model.

Actual inference, artifact verification and numerical reproducibility are now evidenced. Named human review, an audited market dataset, development selection and the final empirical access gates remain separate requirements. This report supplies no forecasting score or final result.

## Reproduce and inspect

Use [the validation commands](../../docs/semantic_validation.md) to prepare a new immutable plan and run the exact pinned checkpoint. [validation_receipt.json](validation_receipt.json) binds the original input, implementation, model and output hashes. [method_record.json](method_record.json) records the declared sample and numerical criteria. The raw text package and model weights remain in the local data/output cache.

Model sources: [pinned checkpoint](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/1110a243fdf4706b3f48f1d95db1a4f5529b4d41) and [model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).
