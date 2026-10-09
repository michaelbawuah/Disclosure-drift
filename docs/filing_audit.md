# Filing audit workflow

The audit command produces offline source evidence, a stable pair-review sample,
and an HTML reading packet. It does not turn automated checks into human approval.
No return observations are loaded, and filings after 2021 are rejected.

## Build the evidence

Run `make ingest` and then `make audit` for the five-issuer sample. For the expanded
document-format pilot, run `make pilot-ingest` and `make pilot-audit`. Ingestion
requires an identifying `SEC_USER_AGENT`; the audit itself is offline.

The expanded configuration covers 20 purposively selected issuers and filing years
2014-2021. The current SEC ticker file supplies discovery metadata only. It does
not determine historical investment eligibility. The config records its source
hash, the historical XOM CIK override, and the decision to keep Disney's newer CIK
separate rather than splice in predecessor filings. Shorter histories are visible.

Each audit checks the stored filing and header bytes against both cache metadata
and the filing table; repeats extraction; compares the parser version and extracted
text; interprets the original acceptance header; and recomputes trading sessions.
API/header disagreements remain visible. Actual public dissemination is not
verified by an acceptance timestamp, so the declared two-session proxy remains.

Generated files in `outputs/audit-smoke/` or `outputs/audit-pilot/`:

- `audit.html`: expandable filing cards, source links, timing and brief boundary excerpts.
- `filing_evidence.parquet`: hashes, checks, cautions and review state.
- `coverage.parquet` and `coverage.csv`: issuer summaries computed through DuckDB SQL.
- `review_pairs.csv`: up to 30 eligible annual pairs selected deterministically.
- `audit_summary.json`: dataset fingerprint, coverage and unresolved issues.
- `reviews.template.jsonl`: pending records; never a completed review file.

The pair sample chooses one pair per issuer first, then fills remaining positions
by a seeded hash of CIK/accession (seed 20261009). It is independent of input row
order and any market returns. It is an engineering review sample, not a population
accuracy estimate. Review all automatically flagged filings in addition to the
selected pairs. A passing source-hash check alone cannot establish extraction quality.

## Review and record

1. Copy the template to a separate `reviews.jsonl` file. Generated templates can be
   overwritten on rerun; an existing completed review file is read, not overwritten.
2. Open the complete SEC filing and SGML header using the links in the HTML packet.
   Check the true Item 1A boundaries, tables of contents, omitted/included content,
   references to separate exhibits, acceptance interpretation and exchange dates.
3. Set boundary/timing verdicts to `pass` or `fail`. Supply a reviewer, reviewer type,
   timezone-aware review timestamp and concrete notes. Pending rows can stay pending.
4. Rebuild with `uv run disclosure audit --reviews path/to/reviews.jsonl` and the
   corresponding `--filings` / `--output` arguments for the expanded pilot.

Every review is tied to a fingerprint of accession, source hashes, parser version,
text, timestamps and event-window dates. Changed evidence invalidates a prior review.
Assistant reviews have their own count and do not satisfy the human-review count.
These declarations record who reviewed the evidence; they are not identity authentication.

The command exits nonzero for source/extraction/review blockers while still writing
the evidence report. Cautions such as API timestamp disagreement are retained even
when source consistency passes. Dataset-wide review counts do not automatically
unlock final-period evaluation or prove a statistical effect.

## Known pilot issues: indirect risk disclosures

The following describes the milestone 02 parser. The subsequent
[reference-resolution workflow](reference_resolution.md) supplies explicit,
hash-bound rules for these 14 known cases; human review remains pending.

Johnson & Johnson's 2014-2016 main-document Item 1A text directs readers to Exhibit
99. The short extracted sections are flagged for review. Do not treat these as
missing risks, silent zero-length signals or a sudden economic change. An
exhibit-resolution policy and additional provenance are required before including
such texts in a comparable annual feature dataset. The numbered-section baseline
excludes annual pairs that depend on a flagged section.

Intel's 2018-2021 filings and GE's 2015-2021 filings have numbered Item 1A entries
that contain page references rather than the substantive risk discussion. The
numbered-section baseline flags those short index entries. Inspection located
earlier risk discussions. The subsequent resolver records the selected boundaries
and their provenance explicitly; it does not complete human boundary review.

These failures describe this parser's coverage. They are not evidence that the
issuers omitted risk disclosures, and excluded examples must remain visible when
reporting later selection and coverage effects.
