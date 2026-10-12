# Paired SEC registered-stock title review (source-bound; not historically approved)

**Checkpoint: 12 October 2026.** This is an offline follow-up to the
[41-filing original SEC lexical stock-class triage](sec_cover_class_review.md),
restricted to the 16 cases with a matching previously parsed
`us-gaap:CommonStockMember` context and no recorded structural/symbol
lexical warning on that fact. The resulting sample is a **purposive source-review
queue**, not a population of approved common stocks or valid forecasting events.

We did not run another WRDS query or open the frozen 2022–2025 study.

## Actual verified results

| Original SEC registered-security lexical evidence | Observations |
| --- | ---: |
| First-priority original 10-K filings examined | **16** |
| Distinct issuer CIK / provisional CRSP security candidate pairs | **8** |
| Issuers with *two consecutive annual 10-K filing years* in this first-priority set | **8/8** |
| Pairs with exactly the same source trading-symbol literal | **8/8** |
| Pairs with the same registered security-title literal after whitespace/case normalization | **8/8** |
| Pairs with the same reported exchange-name literal after whitespace/case normalization | **8/8** |
| 10-K same-context title explicitly containing **Common Stock** | **14** |
| 10-K same-context title saying **Capital stock** (requires class interpretation) | **2** |
| Same-context exchange-name fact present | **16** |
| Other distinct security symbols elsewhere in the 10-K | **12** |
| Associated title/exchange formatting transformation **not interpreted** | **16** |

These eight issuer pairs are a reproducible consecutive-filing observation:
seven pairs cover **2020 and 2021**, and one covers **2019 and 2020**.
Comparisons preserve the original strings, using whitespace/case normalization
**only for the reported title and exchange across consecutive filing years**;
they never rewrite a CUSIP, issuer CIK, security PERMNO, or vendor source row.
The same-original-symbol comparison uses exact text, not fuzzy matching.

The two `Capital stock` titles occur in both filings for one issuer, while
the other 14 original titles explicitly include “Common Stock.” A
`CommonStockMember` lexical context does **not** license silently translating
“Capital stock” into “Common Stock.” Those records therefore retain an
additional manual classification issue despite clean structural source
references.

Twelve filings include **other security symbols**, including non-common-stock
instruments. This does not by itself negate the specific matched common-stock
context, but it requires review of the original registered stock-class table.
All 16 source titles/exchanges retain an uninterpreted associated formatting
transformation caveat, which is **separate** from their structurally consistent
trading-symbol context.

## Original SEC evidence and its precise limit

The [paired-year builder](../src/disclosure_research/paired_stock_class_review.py)
checks the private previous 41-case source review receipt, its file hashes,
the original 215-filing source-verified SEC lexical report gzip and execution
receipt, then independently rematches all 16 source facts to the preserved
source contexts. For each case, it preserves and checks the original SEC filing
CIK and accepted date, source `contextRef`, a declared
`us-gaap:StatementClassOfStockAxis` with lexical
`us-gaap:CommonStockMember`, registered title and exchange facts associated
with the same context, and the absence of recorded symbolic context warnings.
Every fact and corresponding private review status remains **unapproved**.

The [separate verifier](../src/disclosure_research/paired_stock_class_verifier.py)
uses another implementation to reconstruct each original SEC fact, member
namespace declaration, period and issuer identity, registered same-context
security title/exchange, SEC formatting caveat and the eight pairwise
chronological/stability comparisons. The original data are source-bound by
SHA-256. Passing a self-consistency check is **not independent historical
source-version verification or human adjudication**.

**Important source boundary:** the Mac has the gzip of the prior original-byte
verified SEC evidence, but **the original 16 SEC primary HTML/SGML filing
bodies have not been reread on this Mac in this checkpoint**. The original
SEC report records that source-byte validation ran earlier in another local
research workspace. We do not claim direct original-HTML reinspection now.
The earlier report's parsed lexical HTML fragments are not themselves
original source bytes, and its XBRL semantics were never fully validated.

## Open the private eight-issuer reading packet

The new ignored/private directory on the authorized Mac:

`outputs/sec-paired-stock-20261012-final-v2/`

contains `private_issuer_pairs.jsonl`, `private_review.html`,
`public_summary.json`, and a fingerprinted `receipt.json`. To open the
review in Safari:

```bash
open -a Safari ~/Disclosure-drift/outputs/sec-paired-stock-20261012-final-v2/private_review.html
```

The read-only page groups the 16 original filings into eight issuer pairs,
with original security titles, same-context exchange and member, exact source
SEC filing/header URLs when retained, the separate non-common-title and
formatting caveats, and explicit pending decisions. It **does not** approve
links, record a fake review or execute model predictions. The original
filing-level SEC/CRSP joined identifiers stay out of public GitHub.

### Offline reproduction

From the root of this repository, use a **new private output directory**:

```bash
uv run --locked --python 3.12 python scripts/build_paired_stock_class_review.py \
  --class-audit outputs/sec-cover-class-20261011-final-v4 \
  --sec-gzip reports/sec_identity_evidence.json.gz \
  --sec-execution reports/sec_identity_evidence_execution.json \
  --output outputs/sec-paired-stock-NEW
```

Independently verify the new packet:

```bash
uv run --locked --python 3.12 python scripts/verify_paired_stock_class_review.py \
  --paired outputs/sec-paired-stock-NEW \
  --class-audit outputs/sec-cover-class-20261011-final-v4 \
  --sec-gzip reports/sec_identity_evidence.json.gz \
  --output reports/independent-paired-stock-NEW.json
```

The [published first-pass aggregate](../reports/paired_stock_class_checkpoint.json)
and [independent source verification](../reports/paired_stock_class_independent.json)
contain counts, source fingerprints, and explicit no-approval flags rather
than individual CIK/PERMNO/source filings. The synthetic mutation tests
exercise title/namespace integrity, deliberate register-title alterations,
fabricated model and identity approvals, source-hash tampering, false
paired-year stability, original filing dates and private HTML safety.

## Remaining critical path

Original stock-class registration evidence must be interpreted in each
relevant 10-K, particularly the two **Capital stock** title cases and
additional reported security symbols. Then source first-publication evidence
and original SEC/CRSP corporate-identity effective intervals for the relevant
acceptance dates must be independently resolved. The saved CRSP
`LINKENDDT=E` values, later company header CIKs, and retrospective
Names descriptors cannot be substituted for historical CIK mapping
`known_at` or market-data `available_at`.

**No historical identity link, registered common-stock class, historical
availability date, human review, source release or empirical improvement has
been approved.** The frozen 2022–2025 final period remains unopened. A
verified eight-issuer lexical sequence is useful engineering and documentary
evidence, not statistical validation of Disclosure Drift's original
forecasting question.

## Independent repeat-run evidence

The [reproducibility report](../reports/paired_stock_class_reproduction.json)
records **1,159 passing tests**, Ruff and the complete synthetic study
software reproduction. The original real SEC evidence was processed twice
in separate new private directories; the following three results were
**byte-for-byte identical**: `private_issuer_pairs.jsonl`,
`private_review.html`, and `public_summary.json`. The independently written
source verifier also reconstructed the original 16 fact/context/title records
and all eight cross-year comparison outcomes both times. The run-specific
receipts have different timestamps/hashes, as expected.

Repeatable processing establishes code/data traceability, **not** historical
publication timing, XBRL semantic class validation, or forecasting performance.
