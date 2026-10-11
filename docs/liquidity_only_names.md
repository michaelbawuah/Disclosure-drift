# Full Names history for liquidity-only annual observations

The completed historical foundation contains 1,341 annual observations with
saved liquidity evidence and no January 1 Names descriptor. Of those, 490 pass
the existing numerical minimum. These counts alone do not establish missing
source history: a security can have observations in the preceding liquidity
window and a recorded lifetime ending before selection.

This diagnostic checks that distinction using the complete original Names
export. It preserves the foundation and creates a separate evidence bundle.

## Measured execution

The actual Mac run on October 11, 2026 used commit
`16ca9e5fb1b76fa5fb149c58e64976b8b88935a1` and finished in **1.464616 seconds**.
After inspecting all **191,048 original Names rows**, it placed every one of
the **1,341 annual observations** in
`ALL_RECORDED_SECURITY_LIFETIMES_END_BEFORE_SELECTION`. That group includes all
**490 numerical-minimum passes** and **851 failures**. No other category has a
record in this completed result.

The diagnostic retained **7,683 annual-observation-to-source-row references**
in a **2,170,858-byte** private observations file. An independent check confirmed
these references point to **7,683 distinct source records** in this result.
The receipt SHA-256 is
`18373eef2f870882a9a81e6dc7a00c06327fc974f9e7982fc2e11187db116852`.
See the [aggregate](../reports/liquidity_only_names_aggregate.json),
[execution record](../reports/names_history_execution.json),
[verification](../reports/names_history_verification.json), and
[combined interpretation](dated_names_results.md).

These saved lifetime ends explain the missing January descriptors; the cohort
is not unexplained missing Names history. Every annual observation remains in
the foundation. No exclusion, rank change or assertion of contemporaneous
knowledge was approved by this diagnostic.

## Bound execution

Run on the computer containing the preserved private inputs:

```bash
uv run --locked --python 3.12 python scripts/check_liquidity_only_names.py \
  --foundation data/private/historical-foundation/development-v1 \
  --foundation-sha256 9162a16107fca15233400cb8cfc1e56fad61de541c5586fc6d54ac49f9493c7d \
  --listing-candidates data/private/wrds-listing-candidates/development-v1 \
  --names-inventory data/private/wrds-intake/names-v2 \
  --names-inventory-sha256 24e3dd6e85a716a87e572d0e824935c63c70930a7777214732ca0445073b5fcb \
  --output data/private/liquidity-only-names/development-v1
```

An existing output is preserved. The foundation receipt, listing receipt and
original Names inventory must agree. The consumer verifies the liquidity-only
parts and frozen annual windows, then preflights every original Names row and
all four finite, ordered date bounds before matching exact raw PERMNO text.

## What the categories mean

The following conditions are checked in order; each annual observation belongs
to exactly one category.

| Category | Saved interval geometry |
| --- | --- |
| `NO_SAVED_NAMES_HISTORY` | No original Names occurrence has that exact identifier text. |
| `DESCRIPTOR_COVERS_SELECTION` | A `SecInfo` interval includes selection; this flags an inconsistency with the earlier missing-descriptor result. |
| `DESCRIPTOR_GAP_INSIDE_RECORDED_SECURITY_LIFETIME` | No descriptor covers selection, but at least one recorded lifetime does. |
| `ALL_RECORDED_SECURITY_LIFETIMES_END_BEFORE_SELECTION` | Every matching source occurrence reports a lifetime ending before selection. |
| `ALL_RECORDED_SECURITY_LIFETIMES_BEGIN_AFTER_SELECTION` | Every matching source occurrence reports a lifetime beginning after selection. |
| `BETWEEN_RECORDED_SECURITY_LIFETIMES` | Selection falls between the recorded lifetimes. |

The public receipt reports counts for the complete cohort and for numerical
minimum passes and failures separately. Its source-occurrence count means
annual-observation-to-source-row references; one original row can be referenced
by more than one annual observation. It is not a distinct-source-row count.

The private JSONL retains every original annual observation and each matching
source interval with its original CSV record ordinal. It does not normalize
identifiers, merge intervals, remove duplicate source occurrences, or modify
rank eligibility. Original inputs and outputs are rechecked before publication.

## Interpretation boundary

These categories explain the geometry of the saved export. A recorded lifetime
ending before selection can explain the absence of a January descriptor, but
does not prove that the lifetime was known contemporaneously or authorize a
research exclusion. A descriptor gap inside a recorded lifetime requires
further source investigation. Neither category creates a historical CIK link.

No daily prices, returns or final-period outcomes are opened. All historical
availability fields remain unknown, no approvals are created, and the existing
arithmetic and filing reviews remain unchanged. The separate
[filing-date Names consumer](dated_names_evidence.md) checks the existing filing
discoveries at their acceptance and research-window dates.
