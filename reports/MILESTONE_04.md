# Milestone 04 — expanded source verification and market-data staging

**9 October 2026.** Tested code: `7653be88c3c7d907e6441bcb273992bd8ea9776e`.
The complete source pilot now includes 155 original filings and
135 annual pairs across 20 issuers. The new
market import and label pipeline has been verified with invented returns only.

## Full pilot comparison

| Measure | Milestone 02 baseline | Current resolved pilot |
|---|---:|---:|
| Original 2014–2021 filings | 155 | 155 |
| Automated extraction accepted | 141 | 155 |
| Eligible annual pairs | 121 | 135 |
| Unresolved extraction cases | 14 | 0 |
| Completed human filing reviews | 0 | 0 |

Every primary filing and SGML-header hash matches the published milestone 02
manifest. All 141 unregistered control texts match
their earlier extraction hashes. The 14 registered GE, Intel and J&J resolutions
reproduce their pinned section hashes. Every original acceptance timestamp,
reference session and label end is unchanged; the fresh offline audit also
recomputes controls dates against the exchange calendar.

The full sample still has 72 API/header
timestamp disagreements. Those are retained as cautions; SGML local time remains
the specified basis for the two-session availability proxy. Zero automated
blockers does not establish correct public-dissemination time or human approval.

The three source-method transitions remain J&J 2017, Intel 2018 and GE 2015.
Disney's newer CIK is kept separate; its 2019 filing has no preceding original
filing in this sample and is excluded from pairing. No predecessor is invented.
The 20 selected issuers are document-format cases, **not a historical investment
universe or an extraction-accuracy estimate for all issuers**.

## Inspect the evidence

- [Filing review packet](expanded_audit.html): all 155 source cards,
  original SEC/header links, boundary snippets, methods, timing and review fingerprints.
- [Issuer coverage](expanded_coverage.csv) and [source manifest](expanded_filing_manifest.csv).
- [Initial review sample](expanded_review_pairs.csv): 30
  annual pairs selected with the frozen issuer-spread sampling rule.
- [Pending review template](expanded_reviews.template.jsonl): copy before editing;
  a template is not sign-off. Review the full linked sources, not just the snippets.
- [Machine-readable evidence](milestone_04.json), including artifact hashes.

Rebuild with an identifying SEC User-Agent:

```bash
make pilot-resolved-reproduce
```

The current run reacquired missing public cache entries and made
326 network requests with zero reported
failures. Reproduction against an intact cache should not require those downloads.
Full source text and the local DuckDB/Parquet data remain outside git.

## Market-data handoff

The added `import-market` command accepts documented, already normalized Parquet
returns, a declared value-weighted benchmark, and dated security links. It verifies
hashes, key uniqueness, numeric/boolean types, exchange dates, identity intervals
and terminal-event ordering before publishing a new local bundle and DuckDB tables.
It records the source field mapping and return convention without certifying them.

`export-label-events` produced 135 public filing events bound to the
fresh audit hashes. Their human-review count remains 0.
No market returns were needed to create that event queue.

`prepare-labels` resolves the permanent security ID at the reference date and
compounds the next 20 sessions. It records missing identity or return windows as
explicit exclusions. Synthetic and real inputs cannot be mixed. Its outputs are
engineering staging tables, without text predictors or market controls; they do
not authorize model fitting.

The invented three-event integration check produces two correct labels and one
missing-session exclusion. The valid cases cover a continuing security and a
delisting payoff followed by cash. Independent arithmetic verifies reference-day
exclusion and compounding. **These are software results, not investment findings.**

See [the runnable workflow](../docs/market_import.md) and
[manifest template](../configs/market_manifest.template.json). Actual CRSP source
fields, entitlement and version conventions remain unverified.

## Verification and remaining work

`make reproduce` passes lint, 103 tests, the protocol lock and both synthetic
examples in the cloud, on the owner's Mac, and in
[GitHub Actions](https://github.com/michaelbawuah/Disclosure-drift/actions/runs/38000988340).
All runs reported four existing exchange-calendar/NumPy deprecation warnings.
The public-source rerun was performed in the cloud. The Mac's earlier SEC HTTP 403
was not retried for this milestone.

Next, obtain a small authorized market export and its release dictionary; complete
human filing review; then implement and audit historical universe selection,
share-class linkage and pre-event controls. No real return dataset, development
selection, semantic checkpoint or 2022–2025 final outcome has been evaluated.
The frozen study specification remains unchanged.
