# SEC/CRSP issuer anchor: original-source verification

**11 October 2026. Historical crosswalk remains unapproved.**

The saved 20-issuer SEC parser pilot has 135 2015-2021 development events.
A new offline audit linked **all 135 original SEC filing CIKs and acceptance
timestamps** to their previously source-verified original filing headers.
All **20 of 20** pilot securities were found in the saved 2020 candidate
cohort, with at least one matching *strictly earlier, unambiguous* SEC
ownership-form issuer CIK and dated CRSP Names descriptor.

The 2019Q4 original-source audit found **419** qualifying observations
filed before Dec. 31, 2019; **five cutoff-day observations** are separately
unresolved. We reread the original 424 SEC quarterly source records and
the 20 distinct original CRSP Names records, checking exact ticker, CIK,
PERMNO, dated listing descriptor and security lifetime. Nineteen issuer
current-header comparisons agree; one has competing header evidence
consistent with the separately documented Exxon successor case. None is
silently corrected or promoted into an approved historical link.

The [primary checkpoint](../reports/pilot_issuer_anchor_checkpoint.json)
retains aggregate counts and hashes only. Detailed issuer and licensed
source identifiers remain private and gitignored.
The [independent source check](../reports/pilot_issuer_anchor_independent.json)
reconstructed the same **419 earlier / five cutoff-day** counts by scanning
all **38,145** original SEC Q4 submissions and **191,048** original CRSP Names
records. Its separate algorithm did **not** reuse the derived SEC/Names
relationship tables; it checked global symbol collisions and same-security
overlaps and found no ambiguous selected matches.

This is **retrospective 2019Q4 issuer corroboration**, not a continuously
valid 2015-2021 CIK-PERMNO crosswalk, historical known-at, source vintage,
original website-publication timestamp, approved market universe, or
validated forecast result. The older SEC original-source report was rechecked
by hash here; its original 10-K HTML/SGML was not reread in this run.
All source/review approvals remain zero, and the frozen 2022-2025 final
evaluation stays unopened.

Implementation: [source audit](../src/disclosure_research/pilot_issuer_anchor.py),
[independent verifier](../src/disclosure_research/pilot_issuer_anchor_verifier.py),
[synthetic mutation tests](../tests/test_pilot_issuer_anchor.py).
The commands [reconcile_pilot_issuer_anchor.py](../scripts/reconcile_pilot_issuer_anchor.py)
and [verify_pilot_issuer_anchor.py](../scripts/verify_pilot_issuer_anchor.py)
consume existing local immutable sources and require fresh output paths.
No additional WRDS query, account, or source approval was needed.

The outstanding work is historical identity continuity and availability
evidence, share-class and corporate-transition review, confirmed source
releases, source-backed benchmark choice, and human research decisions.
See [completion gates](research_completion_gates.md).

## Complete source and validation receipts

The read-only original-source audit requires the previously published exact
SHA-256 of the original ownership and M5 market-candidate receipts as explicit
CLI arguments. See its `--help` and
[full research execution log](../reports/RESEARCH_EXECUTION_UPDATE.md)
for the initial source inventory and current review limitations.
The [fresh-directory reproduction record](../reports/pilot_issuer_anchor_reproduction.json)
records **1,075 passing tests**, successful Ruff checks and complete synthetic
study verification. Two separately executed original-source audits produced
byte-identical private per-issuer evidence and public summary; both independent
raw-source reconstructions agreed after excluding each run's uniquely bound
receipt SHA. These reproducibility checks are engineering evidence, not a
source-version guarantee or forecast-performance result.
