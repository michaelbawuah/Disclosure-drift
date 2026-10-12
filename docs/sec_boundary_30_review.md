# Disclosure Drift — thirty original SEC 10-K Item 1A boundary evidence cases

**12 October 2026. Source-derived automated reading packet, not an
approved complete human filing review.**

This audit uses only **previously downloaded original SEC 10-K primary HTML
files** from two private source-verified research caches on the authorized
Mac: the 16 original document stock-class audit and the 16 original
Item 1A exploratory diagnostic audit. Two original filings appear in both
caches, giving **30 distinct original 10-K documents from 11 issuers** in
2018–2021. This is *not* a 30-case random sample, an approved population
or a replacement for the previously prepared 73-filing review workflow.

## Source-bound results

| Original SEC source and boundary checks | Observed |
| --- | ---: |
| Current original HTML files across two source caches | **32** |
| Duplicate originals in both caches with identical current bytes | **2** |
| Distinct SEC original 10-K filings verified | **30** |
| Distinct issuer CIKs in this selected source packet | **11** |
| Current originals with substantive directly numbered Item 1A source sections | **28 / 30** |
| General Electric originals requiring previously registered Item 1A source ranges | **2 / 30** |
| Current SEC source text token counts agreeing with original 215-filing manifest | **30 / 30** |
| Original issuer CIK and filing acceptance clock traceable to earlier source-verified report | **30 / 30** |
| Current HTML SHA-256 *identical* to earlier original primary HTML SHA-256 | **0 / 30** |
| New human boundary or timing review decisions inferred | **0** |
| Forecasting/model-ready/final 2022–2025 observations unlocked | **0** |

| SEC acceptance year | Distinct original documents in this audit |
| --- | ---: |
| 2018 | 4 |
| 2019 | 5 |
| 2020 | 11 |
| 2021 | 10 |

The first-pass [boundary matrix](../src/disclosure_research/sec_boundary_review_matrix.py)
rechecks all 30 source accessions, original filing links, CIKs, and
acceptance clocks against the previously verified 215-original-file SEC
report and the pinned original filing source manifest. It then normalizes
the **current locally preserved HTML bytes** using the existing conservative
Item 1A extractor, preserving original ranges, selected text SHA-256,
token counts, preceding source context, first/last extracted words,
and next-section heading evidence. None of these automated checks implies
signed human review.

## The two original GE special cases

Two GE source documents use a *table-of-contents Item 1A pointer*.
The default conservative numbered-heading extractor therefore correctly
returns a non-substantive/review candidate instead of pretending that
the risk discussion lies inside the table of contents.

The research repository already had prior **assistant-proposed,
human-pending** rules in
[`configs/section_resolutions.json`](../configs/section_resolutions.json).
The current original SEC HTML files, although **not raw-byte-equivalent to
the old downloaded versions**, have the exact same normalized source
ranges and source text digests:

| Original GE accession | Current normalized extracted source tokens | Previously registered source text |
| --- | ---: | --- |
| `0000040545-20-000009` | **7,472** | Exact SHA-256 match |
| `0000040545-21-000011` | **8,398** | Exact SHA-256 match |

The offset ranges (**242737–293802** and **226302–283477**) reproduce
the archived *normalized text*, not the old raw-source byte fingerprints.
This is excellent protection against accidentally substituting the TOC
for the full Risk Factors disclosure. It does not override the source
hash guard in the original registered resolver, grant a human pass,
or resolve source first-publication time.

## Private, read-only source review page

The Mac now has:

`outputs/sec-boundary-review-20261012-v1/private_review.html`

It lists all 30 sources by accession and acceptance year with the
previous page text, first Item 1A words, final Item 1A words, next
source heading and the original official SEC Archive link. It also
marks the two GE reference cases separately and preserves the
**unapproved source-boundary and historical availability status**.
The private `private_filing_boundaries.jsonl` has all original CIKs,
individual source text SHA/offsets and input receipt fingerprints.
Neither artifact should be uploaded to GitHub.

**A reviewer can open the page in Safari** with:

```bash
open -a Safari ~/Disclosure-drift/outputs/sec-boundary-review-20261012-v1/private_review.html
```

This is a reading aid, not a verdict-recording interface. The existing
[73-filing review guide](research_completion_gates.md#filing-boundaries-annual-pairs-and-reference-cases)
and [local official review interface](../reports/filing_review/index.html)
remain the correct places to complete real source-bound filing reviews.
Their previously recorded assistant and user reviews retain credit;
none is overwritten or upgraded to a user/human approval by this audit.

The source audit overlaps with **six** of the existing assistant-reviewed
filings; the other 24 add source-context observations to the review queue.
This is a difference in evidence coverage, not 24 new human-reviewed
filings or a new predeclared random review sample.

## Independent reproducibility

The separately written [boundary verifier](../src/disclosure_research/sec_boundary_review_verifier.py)
does not reuse the first audit's source-row mapping or normalized-range
comparison helper. It rereads the original SEC manifest, both source
cache receipts, all 30 original HTML files, original source identity/clock
report and special GE source rules to reproduce:

- the 28 directly bounded source Risk Factors sections,
- both original GE source section SHA-256 and token-count matches,
- all 30 original Item 1A normalized start/end/context excerpts,
- all 30 prior SEC CIK/timestamp and manifest source relations,
- the two exact duplicate current HTML objects and all aggregate year/issuer counts.

**Parsing limitation:** Both execution paths intentionally reuse the
existing, conservative `clean_html`/`extract_risk_factors` source parser.
They are independent *source/reconciliation and numerical* implementations,
**not independent human semantic boundary interpretation**. Only actual
file inspection and documented signed verdicts can complete the
human boundary review. The published [aggregate source checkpoint](../reports/sec_boundary_30_checkpoint.json)
and [independent source verifier report](../reports/sec_boundary_30_independent.json)
contain no issuer-specific private source offsets.

Synthetic-only tests include source tampering, a forged registered GE text
hash, conflicting duplicate SEC files, changed acceptance years,
unexpected source URLs, forged approval flags, and HTML markup injection
in the read-only review page.

## Run offline from the preserved source caches

Both commands **reuse previously downloaded SEC files** and do not make
network requests. Use fresh destination paths for additional runs.

```bash
uv run --locked --python 3.12 python scripts/audit_sec_boundary_matrix.py \
  --diagnostic outputs/sec-original-extremes-20261012-v1 \
  --class-source outputs/sec-original-revisit-20261012-v1 \
  --output outputs/sec-boundary-review-NEW
```

```bash
uv run --locked --python 3.12 python scripts/verify_sec_boundary_matrix.py \
  --diagnostic outputs/sec-original-extremes-20261012-v1 \
  --class-source outputs/sec-original-revisit-20261012-v1 \
  --matrix outputs/sec-boundary-review-NEW \
  --output reports/independent-sec-boundary-NEW.json
```

## Historical availability and security-mapping gates

All 30 original filing acceptance clocks are source-bound via the
earlier verified SGML/header record. The current 2026 HTML downloads
do **not** provide their own first-publication timestamps in the
original filing years. The frozen protocol permits an explicitly
documented two-exchange-session prediction reference assumption when
properly reviewed; the existence of the proxy does **not** make the
underlying historical HTML version or a CIK–PERMNO crosswalk approved.

Historical effective security identity intervals, vintage/release
evidence, eligible market universe, market `available_at`, issuer
class mapping and separate 2016–2021 model-development comparisons
still require their own evidence and real review. The actual
**2022–2025 sealed final return evaluation has not been opened**.

## Repeated offline source and full test verification

The [public reproducibility record](../reports/sec_boundary_30_reproduction.json)
binds **1,257 passing tests**, Ruff and the complete *synthetic* study
software pipeline. Two independent private source-matrix executions,
without new SEC/WRDS requests, produced **byte-identical**
`private_filing_boundaries.jsonl`, `private_review.html` and
`public_summary.json` outputs. The independent verifier reran and
again reconstructed all 30 original source bodies, 28 direct Item 1A
extractions, two registered GE text SHA/ranges and exact duplicate-source
checks. Its run-specific receipt fingerprint differs, as expected.

The source-input proof is *not* a signed manual filing boundary review,
historical HTML-version equivalence, CIK–PERMNO availability approval or
real forecast result. None of those previously documented gates was opened.
