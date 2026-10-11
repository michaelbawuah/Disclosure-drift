# Benchmark source-evidence packet

This offline builder packages the existing benchmark discrepancy audit with its
saved source receipts and explicitly supplied query evidence. It verifies the
small private discrepancy table and its exact Decimal diagnostics. It produces
an aggregate summary and an **unsent** vendor question draft. It does not establish
the cause, select a source, accept a tolerance or create a source approval.

The full daily comparison remains recorded by the
[upstream benchmark audit](wrds_benchmark_audit.md). This builder opens no original
CSV and no source-stage Parquet. Its only numerical input is the saved mismatch
table, which contains benchmark discrepancies rather than individual-stock
returns or identifiers.

## Production command

Run from the repository root, using the recorded successful audit receipt hash:

```bash
uv run --locked --python 3.12 python scripts/wrds_manual_benchmark_source_evidence.py \
  --audit data/private/wrds-benchmark-audit/development-v1 \
  --audit-receipt-sha256 593366dca43cdb299efcc41efd8705304df244b365043e47d61d24d49218cafc \
  --query-evidence data/private/wrds-intake/2016-2022-v1/query-evidence-v1 \
  --output data/private/wrds-benchmark-source-evidence/development-v1
```

The command requires a new private output under `data/` or `outputs/`, outside
every consumed input bundle. Existing outputs are refused. `--protocol` defaults
to `configs/protocol.json`; both its sibling lock and the repository lock must
verify. The recorded audit hash is mandatory; it must come from the successful
audit record, rather than from an unexplained replacement receipt.

`--query-evidence` is optional and repeatable. Only explicitly supplied query
bundles are read. A successful packet with no supplied query displays records
their absence. When an inventory receipt declares preserved SQL, that existing
SQL file and the current inventory receipt must match their saved hashes. The
inventory directories recorded in the stage receipt must remain available for
this small-document check. Original data files are never opened.

The Python entry point is `build_source_evidence(audit_directory,
audit_receipt_sha256=..., query_evidence=[...], output=..., config=...,
repo_root=...)` in
[the packet module](../src/disclosure_research/manual_wrds_benchmark_source_evidence.py).

## What is verified

The caller's receipt hash pins the successful audit. Its copied source-stage
receipt and every source inventory receipt must match their declared hashes,
protocol, status, source identity, row counts and observed header. Every audited
daily source is retained, including batches with zero discrepant dates. Exactly
one independent-market source is required.

The mismatch Parquet must match its recorded hash, byte count, exact schema and
row count. A complete date/provenance pass precedes any Decimal calculation.
Every date must remain inside the frozen development request; source/receipt
pairs must be bound, and the independent-market date/CSV-ordinal relationship
must be one-to-one.

The builder then recomputes the small table using the existing bounded exact
Decimal comparison helpers. It verifies each original raw spelling, exact
difference, displayed-precision descriptor, rounding diagnostic and affected-row
count, plus the reported aggregates by year and source. Repeated or reordered
groups, conflicting per-date sources and contradictory diagnostics are refused.
The complete original mismatch Parquet is copied byte-for-byte; the temporary
recalculation is not substituted for it.

The audit's counts for matching observations are copied from the pinned audit
and checked for accounting consistency. They are not independently recomputed
from millions of stock records. Original-CSV and source-stage-part integrity
continues to rely on the successful upstream audit recorded in the preserved
receipts. This distinction is explicit in the new receipt.

Consumed evidence is checked again for path, identity and hash changes before
completion. Copied documents and generated outputs are also hashed. The completed
private bundle is moved into place only after these checks pass; failed runs do
not replace a prior packet or publish a successful receipt.

## Observed query evidence and its limits

A query-evidence directory contains `observation.json`,
`inventory-reconciliation-v1.json` and the image/PDF files explicitly listed in
the observation. The builder verifies the observation's hash, its reconciliation
to an audited source/receipt hash, query-job identifier agreement, displayed and
inventoried row-count accounting, and each referenced document's actual hash and
size. It preserves all these supplied bytes without OCR, image interpretation,
SQL execution or a new human review.

Matching a displayed result count to an inventoried source is a recorded
association. **It does not certify that the query produced those particular CSV
bytes.** That limitation remains explicit even when every recorded count and
hash agrees. Observed parameter values and association descriptions remain in
the private packet; none is promoted into vendor-certified semantics.

In particular:

- A source receipt's observed columns describe the delivered header, not a
  certified vendor schema version.
- Saved SQL records statement text. The packet builder neither parses its
  semantics nor verifies vendor execution.
- Displayed query times retain their unknown timezone. They are not converted
  into source vintage or historical information-availability timestamps.
- Collapsed form parameters, method codes, all-security selection and source
  completeness remain subject to their existing evidence limitations.
- Each source explicitly retains missing vendor release/vintage and schema-version
  evidence, plus false semantic-certification and query-to-CSV-certification flags.

## The precise vendor question

The investigation compares `vwretd` attached to `wrds_dsfv2_query` with `vwretd`
from the independent `wrds_dailyindexret_query` view. The saved daily form's
library parameter is `crspa`; the observed independent SQL identifies
`crsp_a_stock.wrds_dailyindexret_query`. These are recorded query observations,
not proof that the underlying benchmark definitions and revisions are identical.

Two official WRDS examples help frame the question:

- The [CIZ beta macro](https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/wrds-macros-betas-ciz/)
  obtains daily market returns from `crsp.wrds_dailyindexret_query` and defaults
  its index variable to `VWRETD`.
- The [CIZ event-study macro](https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/run-an-event-study-ciz-format-macro/)
  likewise obtains `dlycaldt` and `vwretd` separately from the daily index view.

Those examples document an intended use of an independent market series. They
do not certify the actual downloaded files, the schema/library mapping, source
vintage, historical availability or which received number is correct.

CRSP's [migration-usage appendix](https://www.crsp.org/wp-content/uploads/appendix/FlagType_MU.html)
includes `IndexReturn` and `PassThrough` explanations concerning SIZ/CIZ
calculation paths. Its `MachinePrecision` discussion describes typical differences
below `1E-10` in that migration context. None of these entries establishes the
mechanism behind the observed `0.000001` differences between these two saved
exports.

The draft asks WRDS/CRSP to identify the exact underlying series, dividend
treatment, universe, vintage, schema and calculation/pass-through path for the
two outputs; connect any precision or formatting explanation to those outputs;
and specify a documented resolution or extraction procedure if needed. It
contains aggregate diagnostic information and transmits nothing. No recipient
is selected and no licensed detail is automatically attached.

The research decision is which documented value-weighted total-return benchmark
to use over the protocol's identical label sessions. Exact equality between
these two export views is not itself a frozen requirement. A source-backed,
human-reviewed choice may retain a disclosed unresolved discrepancy; it cannot
silently replace values or turn this packet into an approval. The current
question draft and exact diagnostic remain unchanged until actual evidence and
judgments support a decision. See the
[completion and review path](research_completion_gates.md#2-obtain-the-missing-historical-facts-and-decide-normalization).

## Output bundle and limits

| File or directory | Contents |
| --- | --- |
| `audit/` | Byte-identical audit receipt, source-stage receipt, all audited inventory receipts and complete private mismatch Parquet. |
| `source_documents/` | Any SQL that was already preserved and hash-bound by its inventory. |
| `query_evidence/` | Supplied observations, reconciliations and referenced screenshot/PDF bytes. |
| `source_evidence.json` | Private source-by-source links, observed settings, association limitations and unresolved evidence fields. |
| `public_summary.json` | Whitelisted aggregate diagnostics and evidence-coverage counts, without raw returns, individual dates, identifiers, SQL, screenshots or local paths. |
| `vendor_question_draft.md` | An aggregate-only, unsent question draft. |
| `receipt.json` | Protocol/code/input bindings, output hashes, processing bounds, evidence scope and unchanged closed gates. |

All files are saved privately with mode 0400 inside directories with mode 0700.
The aggregate summary is suitable for review without disclosing the licensed
per-date detail. The full bundle remains private.

The mismatch input is limited to 100,000 rows and 64 MiB. Reads use batches of
1,024 rows with an 8 MiB batch limit and an 8 MiB SQLite cache. Query documents
are limited to 32 MiB each and 256 MiB in total; SQL is limited to 1 MiB. Numeric
text and Decimal exponent/precision limits are inherited from the benchmark
audit. No bounded value is silently rounded to make it admissible.

Every receipt keeps `model_ready: false`, zero source approvals, an unchanged
prior arithmetic review and `final_period_opened: false`. Reconciliation remains
the audit's exact result; rounding diagnostics never approve a tolerance. This
document describes the builder and its source-evidence limits and does not
claim that a production packet has run or that a discrepancy has been explained.
