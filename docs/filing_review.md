# Filing review on your Mac

Open `reports/filing_review/index.html` from your local Disclosure-drift folder.
The page works as a normal file: no server, terminal, WRDS session or manual
JSON editing is needed to record your work. Original SEC links need an internet
connection. You can also reach the [review page](../reports/filing_review/index.html)
from the repository's local README.

## Start with one filing

1. Select **01** in the fixed-pair queue. The **Previous filing** opens first.
2. Open **Complete filing**, **Risk source** and **SEC header**. Read the original
   material, compare it with the extracted text and boundary context, and check
   the timing fields. The complete original documents are linked; the page
   embeds the extracted risk section only.
3. Enter your name and choose **Human** when you personally performed the review.
   Record your boundary and timing judgments, add notes describing what you
   checked, then tick the source-inspection declaration and click **Record this
   review**. Leave a judgment **Pending** if you have not reached it. Use **Fail**
   when the source does not support a pass, and explain the issue. Identify any
   assistant help in your notes.
4. Select **Current filing** and repeat. Click **Download draft** before you stop.
   When you have recorded decisions to submit, click **Export recorded reviews**.

You can stop after any filing. The export contains only explicitly recorded
decisions, including partial judgments or failures; it does not mark unseen
filings complete. A shared filing uses the same record wherever it occurs.

For the boundary judgment, check the issuer and annual period, the true start and
end of the risk disclosure, omitted/extra material, and any incorporation by
reference. Compare both sides of an annual pair and its predecessor relationship.
Use the [reference-resolution policy](reference_resolution.md) for indirect
disclosures and method transitions. Record pair-specific limitations in the notes.

For timing, compare the original SEC header acceptance clock with the displayed
clock and the [protocol's exchange-session rule](../protocol.md). Preserved API
timestamp disagreements are cautions to inspect, not a reason to silently replace
the header. A pass concerns the recorded header and declared session proxy; it
does not establish the exact first public dissemination time.

## Keep and resume your work

The page attempts to keep changes in this browser. Its status line tells you if
browser storage is unavailable. A downloaded draft is the portable copy to keep:
use **Import draft** to resume it on another browser or after browser data is
cleared. Keep the draft with the same review page. Drafts from a different packet,
changed evidence, unknown filings or invalid records are rejected.

An import preserves the original recorded times. Recording a decision captures
the current time. Editing a recorded filing removes that record from the export
until you click **Record this review** again. There is no bulk-pass action.

**Download draft** produces a `.json` file with unfinished work and recorded
decisions. **Export recorded reviews** produces the `.jsonl` file for the existing
offline audit. You do not need to edit either file by hand. Download a draft even
if you also export reviews, because the audit export omits unrecorded work.

## Exactly what this packet covers

The existing fixed 30 annual pairs contain **58 distinct filings**. All **24**
pending reference-template filings match evidence in the same audited 155-filing
cohort; **nine** also occur in the fixed pairs. This page therefore contains
**73 distinct filings**, with 15 additional reference filings listed separately.
The fixed selection and every original evidence ID are preserved.

Other flagged filings, the five later registered expansion cases, full-source
market-trace review, semantic judgments, historical identities and source
availability remain separate requirements. This page does not create those
approvals or promote the dataset. Your completed **20/20 arithmetic and
printed-timing review remains credited**, with its unknown original timestamp
preserved. The actual 2022–2025 evaluation remains unopened.

## Validate an exported review file

The following is the maintainer step after an actual reviewer exports decisions.
Run from the repository root. Replace the reviews path with the downloaded
`.jsonl` file. Keep the packet hash pinned to the published receipt.

```bash
uv run --locked python scripts/build_filing_review.py validate \
  --packet reports/filing_review/packet.json \
  --packet-sha256 9e1281c0bd58837c1f7a3e7b63f5a73ae36a890d52c55a2b53dde14d6d9ee814 \
  --reviews /absolute/path/to/filing-reviews.jsonl
```

A valid export still needs the existing source audit. Use the preserved cache
and source tables for this exact cohort, and a new output directory:

```bash
uv run --locked disclosure audit \
  --filings data/processed/pilot-resolved/filings.parquet \
  --pairs data/processed/pilot-resolved/filing_pairs.parquet \
  --cache data/raw/sec_cache \
  --reviews /absolute/path/to/filing-reviews.jsonl \
  --output outputs/audit-filing-reviews-v1
```

The validator checks declarations, identifiers, fingerprints and timestamps.
The source audit reopens original cached SEC bytes and applies the existing
review rules. An assistant record remains an assistant record; a partial or
failed judgment does not count as a completed human pass. The whole-table
`manual_audit` field can remain pending after a selected sample is reviewed.
The later [dataset evidence contract](historical_dataset.md) still applies.

## Rebuild the pending page

This command uses only the existing public SEC audit inputs and preserves the
frozen selection. It creates zero reviewer decisions. The recorded hashes must
match; a changed input needs an explicitly reviewed new packet.

```bash
uv run --locked python scripts/build_filing_review.py build \
  --filings data/processed/pilot-resolved/filings.parquet \
  --pairs data/processed/pilot-resolved/filing_pairs.parquet \
  --audit outputs/audit-pilot-resolved \
  --audit-summary-sha256 3afa6c4f90b2e162458d16b0d64b63206561f0da8155a5cb022085b78c4b9ccb \
  --selected-pairs reports/expanded_review_pairs.csv \
  --selected-pairs-sha256 60bb6099ca250668c5724bad42dd284b2731f620c1b12643d9422f8ae5a00278 \
  --reference-template reports/reference_reviews.template.jsonl \
  --reference-template-sha256 24bfb83b67b3324562d2f37849bce031f40d1f6591dfa3890da2f9c2549dd85b \
  --output outputs/filing-review-new
```

The builder refuses an existing output directory, verifies hashes and source
relationships, and checks development dates before decoding full text. It does
not reopen original SEC documents; its receipt says so explicitly. The original
source audit is still required when applying recorded judgments.
