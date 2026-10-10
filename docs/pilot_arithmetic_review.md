# Pilot arithmetic review

The [review follow-up](review_followup.md) answers the verdict/open-end questions,
records the submitted independent check and raw-row reconciliation, and adds a
separate edge-case packet plus a focused view of the existing 30 filing pairs.

`audit-pilot-market` joins the source-bound development event queue to its source-bound
**candidate evidence**, then calculates labels and controls for arithmetic QA. It
checks all numeric results independently using literal CSV Decimal values. This
command creates no approved security links, market-import manifest or model dataset.
The original 20-issuer parser pilot remains separate from the investment universe.

## Reproduce the actual pilot

With the private source archive, filing audit, identity packet and CIZ staging
present, run from the repository root:

```bash
uv run --locked disclosure audit-pilot-market \
  --events data/processed/pilot-resolved/label_events.parquet \
  --filings data/processed/pilot-resolved/filings.parquet \
  --audit outputs/audit-pilot-resolved \
  --identity data/reviews/identity-pilot-v2 \
  --staging data/staging/crsp-pilot-m5-v1 \
  --daily data/raw/wrds/2026-10-10/crsp_daily_pilot.csv \
  --names data/raw/wrds/2026-10-09/crsp_names_pilot.csv \
  --plan reports/pilot_market_request \
  --output data/reviews/market-pilot-m5-v1
```

Use a new output directory for another run. The command rejects changed input
hashes, inconsistent event dates, out-of-period filings and returns, and changed
review selection. It retains ambiguous/missing candidates or calculation failures
as explicit QA issues and exits nonzero when any case is blocked. It never picks
one of several candidate rows arbitrarily. Open CCM dates and differing header
CIKs stay pending; arithmetic is conditional on the candidate, not its approval.

The independent calculation uses raw-source returns, capitalization and dated SIC.
It recomputes compounded stock/benchmark returns, their difference, 20/60-session
momentum, sample 20-session volatility and logged USD capitalization. The exchange
calendar is shared with the pipeline, and generated dates are checked against the
previously frozen export plan; this is independent arithmetic, not an independent
calendar or vendor-data certification. The reference day's return is excluded.

## Outputs

| Private file | Purpose |
|---|---|
| `candidate_calculations.parquet` | Every event's provisional values, evidence ID and unresolved identity flags |
| `pilot_qa.duckdb` | Queryable copy of the candidate calculations |
| `independent_traces.jsonl` | The 20 preselected cases, exact CSV rows and Decimal reference values |
| `review.html` | Readable calculations, dated snapshot and expandable control/label rows |
| `trace_reviews.template.jsonl` | Pending controls/label verdicts bound to exact evidence |
| `trace_reviews.recorded.jsonl` | Supplied declarations, or the unchanged pending records |
| `qa_issues.csv` | Blocked arithmetic cases; not finalized study exclusions |
| `audit_summary.json` | Counts, checks, code/input/output hashes and remaining gates |

The actual run calculates **135 of 135** cases with no failures and generates all
**20 fixed traces**. Maximum numeric difference is approximately **1.43e-15**, below
1e-12. All seven header-CIK differences and 135 unresolved open-end markers remain.
The [public aggregate receipt](../reports/pilot_arithmetic_summary.json) contains no
individual market returns or control values. No forecasting performance is estimated.

## Record a genuine review

Open `review.html` and compare the raw CSV records, source Names interval and
independent arithmetic. Check the SEC acceptance and historical security evidence
in the separate filing/identity packets. Copy the trace template, then record
`controls_verdict` and `label_verdict` as `pass`, `fail` or `pending`. A completed
verdict needs the actual reviewer, `reviewer_type` (`human` or `assistant`), a
timezone-aware timestamp, specific notes and nonempty source references.

Run the same command with `--reviews path/to/completed_reviews.jsonl` and a new
output directory. Stale evidence IDs, duplicate/unknown cases and malformed verdicts
are rejected. Human declarations are counted separately; an assistant review does
not satisfy a human trace review. Reviewer identity is a declaration, not an
authenticated signature. Even all 20 passing traces do not approve the separate
historical CIK links, source availability or filing boundaries.

## Milestone 05 closure still required

- Establish the historical company/security links, share-class choices and explicit
  bounds for the open-end CCM records. Preserve the original historical CIKs.
- Resolve the exact source release/query metadata and document historical availability
  evidence or its limitations. Retrieval date is not historical availability.
- Complete the 30-pair filing sample, registered reference-boundary reviews and the
  20 arithmetic reviews. Promote only approved inputs and finalize exclusions.

The implemented audit runs without those approvals so reviewers have concrete
calculations to inspect. It explicitly reports `milestone_05_complete=false` and
`model_ready=false`; neither output is promoted by a passing arithmetic check.
