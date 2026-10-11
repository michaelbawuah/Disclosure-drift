# Complete Names histories at filing and research dates

The foundation comparison used each discovery's saved January 1 descriptor.
Fifteen of its 207 discovery rows had a descriptor ending before filing
acceptance. The completed full-history run found a unique applicable descriptor
for every one of those 15 cases. This consumer answers that source-coverage
question without replacing the original annual diagnostic or approving a
historical issuer/security link.

## Measured execution

The actual Mac run on October 11, 2026 used commit
`16ca9e5fb1b76fa5fb149c58e64976b8b88935a1` and finished in **2.272097 seconds**.
It scanned all **191,048 original Names rows** and found unique records at all
**16,974 role/date observations** for the existing **207 discoveries**. There
were no missing, overlapping or identifier-variant matches. The output retains
**65 original Names occurrences**, records descriptor-text changes for **18
discoveries**, and preserves all **215 filing-coverage rows**, including the
**eight unmatched original Exxon filings**. PERMCO text comparisons against the
January Names records show no changes.

The private receipt SHA-256 is
`da2e4b3f7e15a9b8ad2696df62d412bb7eff3266781a1c097102acc536b8a5cc`.
See the [aggregate](../reports/dated_names_aggregate.json),
[execution and input bindings](../reports/names_history_execution.json),
[verification](../reports/names_history_verification.json), and
[results and limits](dated_names_results.md).

## Run against the preserved development inputs

From the repository on the computer holding the private source files:

```bash
uv run --locked --python 3.12 python scripts/reconcile_dated_names.py \
  --foundation data/private/historical-foundation/development-v1 \
  --foundation-receipt-sha256 9162a16107fca15233400cb8cfc1e56fad61de541c5586fc6d54ac49f9493c7d \
  --names-inventory data/private/wrds-intake/names-v2 \
  --names-receipt-sha256 24e3dd6e85a716a87e572d0e824935c63c70930a7777214732ca0445073b5fcb \
  --sec-evidence reports/sec_identity_evidence.json.gz \
  --sec-manifest reports/pilot_expansion/filing_sources.csv \
  --output data/private/dated-names/development-v1
```

This is the completed execution's command. Choose a new output path for a rerun;
the existing `development-v1` evidence is preserved.
The foundation receipt supplies the exact SEC report/manifest hashes. The Names
inventory pin must also agree with the inventory snapshot bound through the
foundation's preserved identity receipt. That original CSV has SHA-256
`74195ec05a8b392fcef880750aa73e6f7860f927b042e404c0f9a8c28d1858a9`.
The command does not connect to WRDS or read daily returns.

## What is checked

All foundation parts are verified against their declared byte hashes, schemas
and row counts. Only its two filing metadata tables are interpreted; annual
liquidity observations and ranks are not used. Every original discovery
fingerprint, annual Names occurrence and SEC manifest relationship is checked.

The original Names CSV/gzip is reopened using its observed 24-field header and
CSV record numbering. Every source row and all four date fields are checked
before any descriptor lookup. Finite historical metadata after 2021 is allowed;
it does not create final-period events. Blank, open, malformed or reversed Names
bounds fail the complete-source preflight. Neither security-lifetime bound
extends a `SecInfo` descriptor interval.

Each existing discovery receives **82 role/date observations**: acceptance,
60 control sessions, the reference session and 20 label sessions. The locked
two-session timing rule supplies these dates. Acceptance can fall on a holiday
or repeat a date occurring in the control window; the roles remain separate and
unique-date counts are reported. All observation dates remain within the
permitted development source horizon, including the late-2021 label tail.

Matching uses inclusive `SecInfo` bounds and the same nonzero ASCII-integer
PERMNO comparison syntax as the earlier identity evidence. Every matching raw
occurrence is retained. Missing records, exact repeated records, conflicting
overlaps and leading-zero identifier variants are separate observations.
Variants never count as unambiguous exact-raw coverage. No first-row selection,
interval merging, CIK inference, filling or new discovery search occurs.

Raw text changes are compared with the same original January Names occurrence.
The private record table retains all 24 fields, including CUSIP, share class,
SIC, NAICS, ticker and the exact bounds. Point evidence lists every changed raw
field and a separately declared descriptor-field subset. PERMCO results mean
literal Names-versus-January-Names comparisons; they do not claim agreement with
CCM, and a descriptor change does not by itself establish a corporate event.

## Outputs and limits

| Private table | Contents |
| --- | --- |
| `original_discoveries` | Every original foundation discovery row, unchanged |
| `original_filing_coverage` | Every original coverage row, including unmatched filings |
| `date_evidence` | Every required role/date and all matching source record references |
| `discovery_summary` | Coverage, ambiguity and text-change counts for each discovery |
| `names_records` | Original 24-field records used as snapshots or date matches, once per source ordinal |

`receipt.json` binds the source snapshots, code, output tables and coverage
accounting. `aggregate.json` contains only counts, hashes and scope declarations;
only this summary and an execution record are suitable for public Git. Source
rows and detailed candidate relationships remain private. Output directories
have mode `0700` and files `0400`. Construction uses a temporary directory,
rechecks source/output hashes, and publishes only a complete new bundle.
An existing output is preserved.

Complete descriptor coverage does not establish historical CIK continuity,
share-class eligibility, source vintage, contemporaneous availability or human
review. All `known_at` and `available_at` fields remain null; every identity
approval stays false. No actual labels, controls, model input or final-period
results are generated. The completed arithmetic review and the original
foundation evidence retain their existing scope.
