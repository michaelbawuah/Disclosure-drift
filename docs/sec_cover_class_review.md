# Disclosure Drift — original 10-K stock-class context review

**Source-backed lexical triage: 11 October 2026.** This is the next offline
research checkpoint after the [135-event development identity
matrix](development_identity_matrix.md). We inspect the **41** development
filings with both a matching original SEC 10-K `dei:TradingSymbol` fact and
an independent 2019Q4 issuer observation whose *reported filing date* precedes
the 10-K acceptance. These were selected from fixed original-source evidence
and not from any market-return outcome.

We do **not** interpret the original source report as a validating XBRL
processor. The previously source-checked report expressly sets
`xbrl_fact_values_interpreted=false`; this checkpoint follows lexical
namespace declarations, contextRef references and same-context fact text.
The original SEC HTML/SGML filing bytes were verified previously but were
not reopened in this audit.

## Results from 41 already-pinned original SEC filings

| Source observation | Original 10-K filings |
| --- | ---: |
| Doubly corroborated original filing events examined | **41** |
| Matched original `dei:TradingSymbol` fact occurrences | **55** |
| At least one matched symbol linked to a lexical standard `us-gaap:CommonStockMember` dimension | **19** |
| **Among those 19**, a matched standard-member fact without a recorded structural/symbol lexical warning | **16** |
| Issuer-specific or other class member, **without** a standard common-stock member | **4** |
| No matching standard stock-class axis or member in the preserved lexical report | **18** |
| Same-context security title containing the literal words “Common Stock” | **39** |
| At least one matching symbol with a same-context security title **and** exchange-name fact | **39** |
| Filings reporting multiple distinct trading symbols | **21** |
| Standard common-stock member **and** additional symbols (overlap) | **14** |
| Filings with a structural/context/symbol warning requiring closer reading | **7** |
| Filings with an uninterpreted **associated title/exchange formatting transformation** | **38** |

The **19 / 4 / 18** categories are exclusive triage groups by the best
lexical stock-class axis evidence, and total **41**. Other counts overlap.
The 38 formatting caveats are tracked separately from structural symbol
warnings: the original parsed exchange name may be readable, but its XBRL
format transformation was not evaluated. A matching `CommonStockMember`
QName is stronger documentary context than a ticker alone, **not** proof
of a historically valid share-class identity or trading eligibility.

Among the 55 matching original `TradingSymbol` occurrences, all resolved
their preserved context reference to the expected source context ordinal;
the context entity CIK matched the original 10-K filer, and no context end
period was later than the 10-K acceptance date. Those are lexical checks,
not public-dissemination or class approvals.

## Practical reviewer priority

The **first 16** have an exact original SEC symbol, prior reported quarterly
issuer anchor, matched dated CRSP Names candidate, standard
`us-gaap:CommonStockMember` lexical context and no source-context warning
on that standard-member fact. They are a *documentary review shortlist*,
not 16 eligible training observations. Multiple other symbols (including
notes or preferred classes) may still be present in the same 10-K, and
the full set of SEC document/security registration facts is not yet
semantically checked.

The remaining three standard-member filings require source-context/lexical
review; the four issuer-specific-only records need an authoritative meaning
for their custom class member; the 18 no-standard-axis cases need independent
stock-class documentation. Other flags in the
[135-event source matrix](development_identity_matrix.md)—such as the six
Names descriptor transitions and seven company-header CIK conflicts—remain
relevant to any overlapping case.

Open the **read-only private, 41-filing source-context reviewer** on the
authorized Mac:

```bash
open -a Safari ~/Disclosure-drift/outputs/sec-cover-class-20261011-final-v3/private_context_review.html
```

Every expandable case shows the exact original SEC symbol, contextRef,
recorded XBRL class-axis/member QName, context-linked security title and
exchange, associated formatting caveats and original SEC filing/header links.
Full source context references, individual CIK/PERMNO and licensed per-event
details are stored in gitignored private files, **not published on GitHub**.
The review page has no form, verdict writer, source approval or execution
capability.

## Source provenance, execution and independent verification

The [read-only lexical audit](../src/disclosure_research/sec_cover_class_triage.py)
verifies SHA-256 and length of the original 215-filing SEC gzip publication
and execution receipt, and the original 135-event source-matrix receipt and
private source rows. It checks one-to-one issuer/acceptance evidence,
the original symbol and context IDs, entity CIK, original context period,
`dei` fact and `us-gaap` member namespace declarations, same-context
registered security title/exchange, XBRL lexical/hidden issues and unapproved
status. Per-case source information goes only to a fresh immutable, private
local output directory.

```bash
uv run --locked --python 3.12 python scripts/audit_sec_cover_class.py \
  --matrix outputs/development-identity-matrix-20261011-final-v5 \
  --sec-gzip reports/sec_identity_evidence.json.gz \
  --sec-execution reports/sec_identity_evidence_execution.json \
  --output outputs/sec-cover-class-NEW
```

The separately written [independent verifier](../src/disclosure_research/sec_cover_class_verifier.py)
rereads all original lexical facts and their context references and reconstructs
each source member, title/exchange text, class review group, associated
format transformation and structural warning. It recomputes all 41-event
overlap/class counts rather than trusting the first audit's labels.

```bash
uv run --locked --python 3.12 python scripts/verify_sec_cover_class.py \
  --class-audit outputs/sec-cover-class-NEW \
  --sec-gzip reports/sec_identity_evidence.json.gz \
  --output reports/independent-sec-cover-NEW.json
```

The [aggregate source checkpoint](../reports/sec_cover_class_checkpoint.json)
and [independent verification](../reports/sec_cover_class_independent.json)
contain only counts, source hashes and explicit no-approval statements.
Synthetic-only adversarial tests reject changed original SEC reports,
incorrect original issuer times, false source or stock-class approvals,
forged class QNames and associated title text, missing/ambiguous contexts,
invalid source periods and unsupported source links in the private HTML.
Successful reproduction does **not** establish source known-at or correctness
of XBRL semantic interpretation.

## Next evidence needed

The 16 highest-priority cases need explicit original filing/class
registration review, original SEC context and amendment checks, independent
security class/source identity corroboration, and the historical `known_at`
and `available_at` determinations required by the locked protocol.
The historical population remains a purposive 20-issuer parser pilot,
not the predeclared full investable universe. Previous conditional
prediction comparisons, benchmark source discrepancies and the
**sealed 2022–2025 final evaluation** remain unchanged.

Neither the 41 reviewed lexical cases nor the 16 promising standard-member
source contexts are approved model observations. No historical security
links, market-vintage decisions, empirical performance findings, or human
approval were generated here.

## Final deterministic execution receipt

The [public reproduction record](../reports/sec_cover_class_reproduction.json)
binds a full **1,137-test** passing repository suite, Ruff and the invented
end-to-end software study. Two separate real source-bound executions produced
**byte-identical** `private_context_review.jsonl`,
`private_context_review.html`, and `public_summary.json` outputs.
A second independently implemented original-source verifier also reconstructed
all 41 private SEC cases, 55 matching lexical TradingSymbol facts,
their exact context membership, same-context titles/exchanges, recorded
source warnings, year counts and priority groups. Its run-specific receipt
hash differs, as expected.

These are deterministic-processing and source-traceability checks only.
They are not XBRL schema certification, human-reviewed CIK mappings,
vendor release timestamps or valid empirical forecast findings.
