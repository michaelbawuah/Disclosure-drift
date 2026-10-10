# M5 review follow-up

**Recorded update:** the user's explicit **20/20 arithmetic and printed-timing
pass** is now bound to the original packet and saved results in the
[review-progress record](review_progress.md). The original review time was not
recovered and is not invented. The older pending draft remains preserved; it does
not negate the completed numerical review or require the user to repeat it.

Milestone 05 remains open. The original 20 trace selections, evidence IDs, generated
packets and pending verdicts are unchanged. This follow-up adds review coverage and
locates the existing filing sample; it does not complete human reviews or approve
identities, source availability or model inputs.

## Review fields

| Field | Accepted values |
|---|---|
| `controls_verdict` | `pending`, `pass`, `fail` |
| `label_verdict` | `pending`, `pass`, `fail` |
| `reviewer_type` | `human`, `assistant`; blank is allowed while both verdicts are pending |

Any completed verdict also needs a nonblank reviewer and notes, a timezone-aware
`reviewed_at` timestamp, and a nonempty list of `source_references`. Keep the original
event and evidence IDs. Unknown events, duplicate events and stale evidence are
rejected. Both verdicts must pass with reviewer type `human` to count toward the
20-trace human gate. The type describes who actually reviewed the evidence; disclose
AI assistance in the notes. An assistant-only check cannot be recorded as human.

Trace verdicts concern controls/label timing, source rows and arithmetic conditional
on the candidate security. They do not certify the separate historical identity.
A reviewer may record that distinction in the notes; identity remains pending in
its own packet until its required evidence is resolved.

## Why every open link end is unresolved

All 20 sampled traces (and all 135 candidate events) use a CCM record with the
literal end marker `E`. The source is not an ISO date. The official
[WRDS CIZ macro](https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/wrds-macro-indratios-ciz/)
accepts a link when the observation is before `LINKENDDT` or `LINKENDDT = .E`.
That supports treating the marker as open-ended for candidate discovery.

An open end is consistent with a link ongoing as of a vendor snapshot; it is not
proof that the link is active today or that the current company header is valid
for every historical year. Here the flag means the extract-specific interpretation
and supported normalization bound have not yet been signed off. It is not evidence
that every link is broken. Preserve `E` and document the dictionary/release, query
coverage and supported interval instead of substituting today's date.

The flag allows provisional arithmetic QA but blocks final identity/interval
approval and promotion under the current contract. Exact source release and
point-in-time availability are separate pending questions.

## Submitted arithmetic check and raw-row follow-up

The submitted `pilot-recheck.py` was run unchanged on the existing HTML packet:
20 of 20 traces pass, with maximum observed difference **1.27675647831893e-15**.
The older draft has 20 valid evidence bindings and its original fields remain
pending. Its first AAPL 2019 note says `1e-03`; the saved result and rerun give
approximately `1.28e-15`. The separate recorded user verdict credits the actual
20/20 numerical pass and observed errors. The original attachment is preserved.

The script's configured recomputation tolerance is `2e-5`, even though its observed
errors are much smaller. For future runs, use `1e-12` for comparisons with the full
independent-decimal column, retain `5e-7` for the displayed six-decimal pipeline
column, and return a nonzero process status if any issues are found. Those changes
are suggestions, not silent edits to the submitted check. Consecutive CSV records
are an export-layout check, not a general requirement: cash continuation has no
stock source row. The exchange-session sequence is the general timing invariant.

The follow-up checks every cited record against the hash-bound original CSVs:
1,200 control references, 400 stock-label references, 400 benchmark references,
20 capitalization references and 20 dated Names references. All **2,040 record
references** match. These counts include repeated references, not distinct source
records. This is an assistant-run original-source check; it is distinct from the
user's completed arithmetic check on the printed packet. No human original-CSV
review or vendor historical-availability judgment is inferred from either result.

## Supplemental coverage

The fixed 20 cases cover 13 PERMNOs. Preserve that outcome-independent sample and
review the following directed cases separately:

| Case | Evidence and scope |
|---|---|
| Exxon 2015, earliest flagged event | Actual filing, 60 controls and 20 labels; historical CIK `0000034088` differs from CCM header `0002115436`; candidate PERMNO `11850`; identity remains pending |
| WFM ordinary plus terminal | Actual delivered returns with an artificial event clock; 20 label sessions, including 10 cash-continuation sessions |
| WFM terminal only | Actual delivered returns with an artificial event clock; terminal return followed by 19 cash sessions |
| 59-session control history | Explicit synthetic fault injection; the calculator rejects incomplete history without filling or predecessor splicing |

WFM is label-only QA: the terminal export does not supply 60 prior control sessions.
Cash rows explicitly have no stock CSV record; the benchmark continues from actual
daily observations. Neither WFM clock is represented as a real filing event.
No real small-cap history has been added; the current daily pilot cannot establish
small-cap coverage. The existing GE dated-identifier check remains available too.

Four of the fixed traces already have an accession prefix different from the SEC
issuer CIK: Microsoft 2015/2016/2017 and IBM 2020. Their cached SEC FILER company CIKs
are rechecked against the original issuer. The
[SEC explains](https://www.sec.gov/submit-filings/filer-support-resources/how-do-i-guides/understand-select-set-default-login-cik)
that the first ten accession digits identify the submitting login CIK, which may
belong to a filing agent. That difference is distinct from a CCM header-versus-
historical-issuer mismatch. It should not be turned into an issuer join failure.

Supplemental templates use `case_id` and a separate pending `verdict`; they are
review notes and are not accepted by the fixed-event trace importer. They do not
increase the required fixed-sample count or silently satisfy any of its reviews.

## Where the 30-pair filing packet is

The existing public full reading packet is [expanded_audit.html](../reports/expanded_audit.html),
with [expanded_review_pairs.csv](../reports/expanded_review_pairs.csv) specifying the
30 pairs. It was separate from the arithmetic HTML. The follow-up creates a focused
`filing_pairs_30.html` with both sides, SEC document/header links, timing, boundary
context and full extracted risk sections. The original pair list and evidence IDs
are verified and preserved. There are **58 distinct filings across 30 pairs**;
`filing_reviews.template.jsonl` supplies one pending record per distinct accession.

The separate [registered-reference packet](../reports/reference_audit.html) and
[reference pair list](../reports/reference_review_pairs.csv) remain required; the
30-pair sample does not replace reference-resolution or flagged-case review.

## Rebuild privately

With the original private M5 archive present, run from the repository root:

```bash
uv run --locked python scripts/build_review_followup.py \
  --output data/reviews/m5-followup-v1
```

Optionally provide `--recheck-results path/to/results.json` and
`--draft path/to/review-verdicts-DRAFT.jsonl`. Run the submitted recheck separately
in its own output directory. The helper validates the returned IDs, errors and
pending draft; it does not execute an arbitrary supplied script or ingest sign-off.
Use a new output directory for another run. Public aggregate evidence is recorded
in [review_followup_summary.json](../reports/review_followup_summary.json).
