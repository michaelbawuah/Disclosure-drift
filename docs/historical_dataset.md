# Historical universe and audited model datasets

Milestone 07 implements historical selection and the audited dataset join. It
does **not** establish that the full historical market population has been
obtained or reviewed. The live pilot remains separate from the synthetic
demonstration described below. Restricted source tables stay local.

## Runnable fixture

```python
from disclosure_research.dataset import run_synthetic_dataset_demo, load_dataset
from disclosure_research.protocol import load_protocol

config = load_protocol()
summary = run_synthetic_dataset_demo("outputs/dataset-demo", config)
development, manifest = load_dataset("outputs/dataset-demo/development", config)
```

The fixture invents 12 issuers, 13 share classes and 60 prior-session USD-volume
observations per class/year. The historical selector retains 12 issuers per year
over 2010–2025, including the most liquid of the first issuer's two classes.
The builder produces 144 development observations and 48 separate holdout
observations. These counts describe a software fixture, not study coverage.

All fixture manifests declare `SYNTHETIC_ENGINEERING_FIXTURE`, zero human
reviews, `model_ready: false`, and `approval_status: synthetic_fixture_only`.
An additional `synthetic_fixture_validated` field reports whether the fixture
passed its own input/audit checks. It never authorizes empirical use.

## 1. Historical selection

The callable API is:

```python
from disclosure_research.universe import select_historical_universe, build_universe

members, exclusions = select_historical_universe(
    listings, daily_liquidity, identity_links, years, config
)
receipt = build_universe("private/universe-source/manifest.json", "private/universe", config)
```

`build_universe` reads three normalized Parquet tables. No vendor-code adapter,
current ticker mapping or current survivor list is inferred.

| Table | Required fields |
|---|---|
| `listings` | `security_id`, `valid_from`, `valid_to`, `market_country`, `share_type`, `listing_status`, `known_at`, `classification_source`, `evidence_id` |
| `identity_links` | `security_id`, `cik`, `valid_from`, `valid_to`, `known_at`, `mapping_source`, `evidence_id` |
| `daily_liquidity` | `security_id`, `session`, `dollar_volume_usd`, `available_at` |

The explicit eligible classifications are `market_country=US`,
`share_type=COMMON_STOCK`, `listing_status=ACTIVE`. `market_country` identifies
the listing market; the adapter must not silently substitute issuer domicile or
an ADR code. Explain the exact vendor mapping in the source manifest and obtain
the historical universe audit before using the output in research.

Dates must be `YYYY-MM-DD`; CIKs must be nonzero, zero-padded 10-digit strings.
Validity intervals are inclusive. `known_at` and `available_at` require an ISO
timestamp with an explicit UTC offset. They mean historical availability of the
fact, not the date a researcher downloaded the table. Never replace unavailable
historical classifications with today's classifications.

The selection date is January 1. The information cutoff is the final XNYS close
of the preceding year; the liquidity window contains that session and its 59
predecessors. At least 40 finite, nonnegative USD-volume observations are
required. Zero is a valid recorded zero; missing, negative and infinite values
do not count and are not imputed. Duplicate security/session rows are rejected.
The source contract must document price/volume adjustment conventions, USD
conversion and actual population coverage.

Eligible classes are ranked by their pre-year mean dollar volume. Only the most
liquid class is retained for each CIK, then up to 500 issuers are retained.
Exact ties use ascending permanent security ID, followed by CIK, so input row
order cannot change selection. Later delistings never remove a year-start
membership. Dated identity remains attached to the selected security; the event
builder will not substitute a surviving replacement class.

Ambiguous overlapping security-to-issuer links are errors. Missing historical
identity, classification, availability or adequate liquidity produces an
explicit exclusion. Future liquidity and classifications do not influence an
earlier year's choice.

The universe source manifest requires:

- `schema_version: 1`, `data_kind` equal to `SYNTHETIC_ENGINEERING_FIXTURE` or
  `NORMALIZED_MARKET_DATA`, `provider`, `normalization_notes`,
  `population_coverage`, timezone-aware `exported_at`, and explicit `years`.
- `tables`: each table's relative `path`, file `sha256`, and a `field_mapping`
  entry describing every required normalized field.
- `evidence`: a nonempty map from source `evidence_id` to an actual relative
  document `path` and `sha256`. Selected classifications and links must reference
  one of those documents.

Output files are `universe.parquet`, `exclusions.parquet`,
`source_manifest.json`, and `universe_manifest.json`. Each membership has its
own fingerprint, selected share class, historical identity interval, exact
liquidity dates, observation count, mean and rank. This stage records source
declarations and always reports `model_ready: false`; population completeness
and historical vendor mappings still need independent review.

## 2. Normalized dataset inputs

```python
from disclosure_research.dataset import build_dataset, load_dataset

manifest = build_dataset(
    "private/development-source/manifest.json",
    "private/development-dataset",
    config,
    partition="development",
)
frame, manifest = load_dataset("private/development-dataset", config)
```

The dataset source manifest is version 1 and declares `data_kind`, `partition`,
`protocol_sha256`, timezone-aware `created_at`, `normalization_notes`,
`normalization_evidence_id`, `tables`, `evidence`, and `reviews`. Each file
specification consists of a relative `path` and `sha256`. Paths may not leave
the manifest's directory, including through symlinks.

| Table | Required content |
|---|---|
| `pairs` | `observation_id` for the current accession; `cik`, `previous_cik`, `previous_accession`; `form`, `previous_form`; timezone-aware current/previous acceptance timestamps; `report_date`, `previous_report_date`; current/previous text and source URLs; current/previous filing evidence IDs, pair evidence ID, availability status and evidence ID |
| `labels` | `observation_id`, `security_id`, `reference_session`, `label_end`, `stock_return`, `market_return`, `target`, `horizon_sessions`, `label_evidence_id` |
| `controls` | `observation_id`, `security_id`, `controls_asof`, `control_history_start`, `control_history_sessions`, `momentum_20`, `momentum_60`, `volatility_20`, `log_market_cap`, `industry`, `industry_scheme`, `controls_evidence_id` |
| `universe` | The complete historical selector membership row plus `universe_evidence_id`, identifying the independent selection/source audit |

The exact field names are exported as `dataset.TABLE_COLUMNS` and
`universe.MEMBERSHIP_COLUMNS`. Existing filing, label-staging and controls
outputs must be normalized into this contract explicitly; renaming a pending
candidate calculation as an approved label is insufficient.

The builder rejects duplicate keys and orphan label/control IDs before joining.
It joins labels and controls one-to-one by event ID and the annual universe
many-events-to-one by acceptance year and CIK. Every retained label and control
must use the selected permanent security. Its identity interval must also cover
the event; a later reorganization never causes automatic return splicing.

For each event, the builder independently recalculates the primary two-session
reference date, 20-session label end and preceding 60-session control window.
It checks current/previous CIKs, original 10-K forms, ordered acceptance times,
annual report-period spacing, nonempty tokenizable text, official SEC source
URLs for empirical records, finite controls/labels, and
`target = stock_return - market_return` within numerical tolerance.
Source-bound pair review is still responsible for confirming the immediate
original annual predecessor against the complete filings history.

`availability_status` is either `verified` or `documented_assumption`, with
explicit evidence and review in both cases. `verified` additionally requires
timezone-aware `public_available_at`. If a timestamp is supplied for either
status, it must not precede recorded SEC acceptance and must be strictly before
the prediction open. An unverified two-session proxy remains an assumption;
the dataset does not certify public dissemination from acceptance alone.

## 3. Evidence and review contract

An evidence JSONL record names:

```json
{
  "evidence_id": "label-review-event-001",
  "kind": "label",
  "subjects": ["event-001"],
  "source_tables": {"pairs": "<actual SHA-256>", "labels": "<actual SHA-256>"},
  "artifacts": [{"path": "audits/event-001-label-review.json", "sha256": "<actual SHA-256>"}]
}
```

The placeholders above are documentation, not usable evidence. Audit artifacts
must exist and match their byte hashes. Evidence scopes are checked for filing,
pair, availability, label, controls and universe subjects. The normalization
record must cover all four tables and subject `dataset`, including underlying
return-convention, source-release, mapping, entitlements and population-coverage
audits. This is a review of the source work, not merely a summary boolean.

A review record must reference both `evidence_id` and `evidence_sha256`, where
the latter is `market_data.fingerprint(complete_evidence_record)`. It also names
`reviewer`, `reviewer_type` (`human` or `assistant`), timezone-aware
`reviewed_at`, `verdict` and substantive `notes`. Completed reviews may not be
dated in the future. Changing an input table, artifact or evidence scope
invalidates the old review fingerprint.

Empirical acceptance requires a named human `pass` for every retained event's
evidence and the normalization record. Assistant checks are recorded distinctly
and can validate synthetic fixtures only. A `pending` or missing review remains
unresolved. A `fail` also remains unresolved, so dropping one failed extraction
cannot make the rest of the bundle approved. A deliberate reviewed `exclude`
can remove an event with a recorded reason. These are recorded reviewer
assertions and provenance checks, not an authentication system.

## 4. Separation, reload checks and completion limits

Development permits only 2010–2021 acceptance years. It projects timestamps and
rejects mixed or holdout dates before parsing the source label table. Late-2021
events may still have 2022 label-end sessions under the fixed horizon.

Holdout staging accepts only 2022–2025 acceptance years and writes
`features.parquet` without `target`, `stock_return`, or `market_return`, plus a
separate `targets.parquet` containing exactly `observation_id` and `target`.
For empirical holdout staging, `build_dataset(..., partition="holdout",
authorization=callback)` calls the prerequisites verifier before reading source
labels. Its receipt must bind this protocol and report verified prerequisites.
The final evaluation workflow owns that verifier and the subsequent freeze.

Every output includes `exclusions.parquet`, immutable source/evidence snapshots,
and `dataset_manifest.json`. The manifest binds all output files, protocol,
source tables, observations, exclusions, availability assumptions, review types
and unresolved-event count. Existing outputs are preserved, not overwritten.

`load_dataset` rechecks file hashes, original source/audit bindings, evidence
documents, named review scopes, observation/exclusion counts and partition
dates. `require_approved=False` is for staging inspection; it does not make a
bundle eligible for empirical modeling. Metadata verification for the final
gate uses:

```python
features, manifest = load_dataset(
    "private/holdout-dataset", config, partition="holdout",
    require_approved=True, features_only=True,
)
```

This mode does not read target bytes. The final evaluator verifies and reads
the separate target file only after its prerequisites and freeze checks pass.
Ordinary empirical holdout loading additionally requires an authorization
callback before target parsing.

Only fully resolved empirical bundles can report `EMPIRICAL_RESEARCH_DATA`,
`approval_status: approved`, and `model_ready: true`. This status says that the
specified observations are eligible inputs; it does not imply full period
coverage, a completed model study, significant predictive results or trading
profits. Development/final evaluators independently enforce chronological
coverage, model-selection and final-access requirements.
