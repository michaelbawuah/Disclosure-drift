# Disclosure Drift — 135-event historical identity evidence matrix

**11 October 2026.** Completed offline, source-bound development candidate
reconciliation. This is a fixed **20-issuer SEC parser pilot**, not the
historically selected full U.S. equity population. It required **no new WRDS
login or download**. All licensed CRSP/CCM event-level identifiers remain
private on the authorized Mac.

## Verified event-window coverage

The [matrix builder](../src/disclosure_research/development_identity_matrix.py)
reconstructed each event's 60 pre-reference XNYS control sessions,
reference session and 20 return sessions, checked each against the original
complete 191,048-row CRSP Names history, and cross-referenced the saved
original CCM links, original SEC filing report, 2019Q4 ownership corroboration,
and original 10-K TradingSymbol audit.

| Retrospective source check | Result |
| --- | ---: |
| Original 10-K event CIK and acceptance clock bound to earlier SEC source report | **135/135** |
| Distinct issuer/security candidate pairs | **20** |
| Exactly one dated Names descriptor for all 81 dates per event | **10,935/10,935** |
| One CCM link **candidate** at each original filing date | **135/135** |
| Same Names/CCM PERMCO for every required date | **135/135** |
| Windows spanning a new dated Names *source record* | **6** |
| Source CUSIP8 changes within those 81-session windows | **0** |
| Source trading-symbol changes within those 81-session windows | **0** |
| Other simultaneously active original PERMNO at the selected `PERMCO` on the filing date | **0** |
| Original Names `shareclass` literal blank | **135** |
| Current CCM company-header CIK disagreements | **7** |
| CCM link candidate end-marker literal `E` (not resolved) | **135** |

A unique **historical descriptor** is not a validated historical issuer link.
The source `shareclass` is blank, so the Names classification hasn't been
approved as eligible common stock. Absence of another simultaneously active
PERMNO with the same source PERMCO narrows a specific collision risk but does
not interpret SEC XBRL classes. None of the `E` end bounds was replaced
with an invented date.

## The next review queue

The separately verified original 2019Q4 SEC ownership forms provide
strictly earlier *filing-date* issuer observations for all 20 securities
at the 2020 selection anchor. Original 10-K `TradingSymbol` lexical facts
match dated Names for 43 of the 135 filings, but 21 have multiple distinct
symbols, 3 have lexical issues, and 5 contain hidden facts; only 17 satisfy
the stricter clean/single/non-hidden criterion.

| Additional corroboration relative to a particular 10-K | Events |
| --- | ---: |
| Original 10-K `TradingSymbol` **and** prior reported 2019Q4 issuer filing date | **41** |
| 10-K `TradingSymbol` but no prior 2019Q4 filing-date anchor | **2** |
| Earlier-dated 2019Q4 anchor but no direct 10-K lexical symbol | **0** |
| Neither additional source | **92** |
| **Total** | **135** |

These are overlapping types of *historical documentary evidence*, not a
graded signal of investment eligibility or point-in-time availability.
**Every event already has an original SEC filer CIK and full retrospective
Names window.** The 2019Q4 quarterly source's reported filing date does
**not** certify its first public availability. A 2019 issuer observation cannot
retroactively establish who owned the stock or what was known in 2015.

Prioritize the **41 doubly corroborated records** for actual stock-class,
source-vintage and human review, retaining all **six** descriptor transitions
and **seven** conflicting current headers. Then investigate the **two**
direct-symbol-only events and the **92** requiring earlier or alternate issuer
anchors. No row is auto-excluded, auto-approved, or selected based on a future
market outcome.

## Private readable audit and independent verifier

The source-pinned private output
`outputs/development-identity-matrix-20261011-final-v4/` includes:
`review_queue_private.jsonl`, `private_review.html`, `public_summary.json`
and `receipt.json`.

Open **`private_review.html` on your Mac in Safari**. It contains 135
expandable, read-only original filing entries, grouped by year, with original
SEC URL links when preserved in the earlier verified report. Each entry shows
source CIK, provisional security ID, original CCM/Names source row numbers,
source CUSIP/class literals, and unresolved research questions. It records
**no** reviewer decisions, approvals or generated timestamps. Everything
identifying a specific CRSP security or event-level market candidate stays in
the gitignored private folder; don't upload that HTML or JSONL publicly.

The separate
[independent source verifier](../src/disclosure_research/development_identity_matrix_verifier.py)
derives XNYS dates with an independent bisect-based algorithm rather than
reusing the matrix builder's event window/Names-matching functions. It rereads
the original Names and CCM CSVs, original SEC report, 2019Q4 anchor and
135 market-candidate records. It reconstructed all **10,935 positions** and
all public year/count totals, and checked every private event source flag.
The [independent public receipt](../reports/development_identity_matrix_independent.json)
contains aggregate-only evidence and unchanged closed gates.

Synthetic mutation tests verify protection against future-year filing leakage,
wrong CIK/PERMNO, inaccurate SEC acceptance clock, stale source fingerprints,
ambiguous Names history, mismatched PERMCO, source CUSIP or classification
changes, missing review flags, forged source approvals, and unsafe HTML text.

## Reproduce from preserved local sources

Build to a **new, unused private directory**:

```bash
uv run --locked --python 3.12 python scripts/build_development_identity_matrix.py \
  --market-candidates data/reviews/market-pilot-m5-v1 \
  --names-csv data/private/wrds-intake/names-v2/source.csv \
  --names-inventory data/private/wrds-intake/names-v2/receipt.json \
  --ccm data/raw/wrds/2026-10-09/crsp_ccm_pilot.csv data/raw/wrds/2026-10-09/crsp_ccm_xom.csv \
  --identity-summary reports/identity_pilot_summary.json \
  --sec-report-gzip reports/sec_identity_evidence.json.gz \
  --sec-execution reports/sec_identity_evidence_execution.json \
  --tenk-audit outputs/tenk-symbol-corrob-20261011-v3 \
  --issuer-anchor outputs/pilot-issuer-anchor-20261011-v2 \
  --output outputs/development-identity-NEW
```

Independently verify without reading the builder's relationship-join logic:

```bash
uv run --locked --python 3.12 python scripts/verify_development_identity_matrix.py \
  --matrix outputs/development-identity-NEW \
  --market data/reviews/market-pilot-m5-v1/candidate_calculations.parquet \
  --names data/private/wrds-intake/names-v2/source.csv \
  --ccm data/raw/wrds/2026-10-09/crsp_ccm_pilot.csv data/raw/wrds/2026-10-09/crsp_ccm_xom.csv \
  --sec-gzip reports/sec_identity_evidence.json.gz \
  --anchor outputs/pilot-issuer-anchor-20261011-v2 \
  --output reports/independent-development-NEW.json
```

All raw sources are read-only, fingerprinted and rechecked; prior user
**20/20 independent arithmetic review** and assistant filing reviews retain
their credit. The original SEC 10-K bodies were verified in the *earlier*
source audit; this audit binds the preserved report and does not reopen
each original HTML/SGML filing body.

## Still required before claiming empirical forecast performance

Historical CIK–security *effective intervals*, source-known dates for
identities/listings, daily observation availability and revision evidence,
correct security-class mappings, a defensible population/selection, reviewed
benchmark and complete human source audits remain open. Even a 41-event
source-corroborated subset cannot bypass those requirements. The original
2016–2021 full development comparisons and 2022–2025 sealed final test are
not completed by this review matrix. No forecasting claim, new source approval,
source-availability timestamp or historical link approval was created.

See the [research completion gates](research_completion_gates.md)
and [public aggregate summary](../reports/development_identity_matrix_checkpoint.json).

## Repeated real-data reproducibility

The [final reproducibility receipt](../reports/development_identity_matrix_reproduction.json)
records **1,115 passing tests**, successful Ruff checks, and a complete
invented-data study pipeline run. Two fresh private executions using the same
locked original source evidence produced **byte-identical** versions of
`review_queue_private.jsonl`, `private_review.html`, and
`public_summary.json`. A second independent original-source verifier run
reproduced all 135 events, all 10,935 XNYS positions and every event-level
review flag. Its run-specific receipt fingerprint is expected to differ.
These checks confirm code/data reproducibility only: they do **not** create
a historical CIK availability date or confer a source/human approval.
