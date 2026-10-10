# Experiment log

There are no experiments using actual market returns yet.

## Synthetic engineering run, 2026-10-09

- Data: 144 invented events, 2010-2021; identifiers start with SYNTHETIC.
- Goal: verify annual fold construction, eligible-label filtering, eight declared
  model/grid configurations and reproducible output files.
- Outputs: `outputs/demo/selection.json` and `development_predictions.parquet`.
- Interpretation: software integration check only. These selected penalties and
  scores are not the study's empirical model choices or findings.

## SEC extraction smoke run

- Data: original 2018-2021 filings for the five configured issuers.
- Goal: verify download, caching, acceptance parsing, Item 1A extraction and pairing.
- Evidence: `reports/milestone_01.json` after the run completes.
- Human boundary/timing audit: pending. Automated extraction success is not a
  claim of independently measured extraction accuracy.

For real development experiments, append dataset hashes, protocol/code versions,
folds, configuration, exclusion counts, predictions, scores, interpretation and
whether an idea was specified before outcomes were examined.

## Python-stack and HTTPX verification, 2026-10-09

- `make reproduce` passed lint, all 40 research-integrity tests, protocol fingerprint
  verification and the 144-row synthetic demonstration.
- A live request through HTTPX retrieved Apple's official SEC submissions JSON:
  HTTP 200, 163,882 bytes, one network request. A second identical request used the
  verified cache without another network request.
- The live environment required HTTPX's SOCKS extra; it is now in the dependency
  declaration and lockfile. No proxy settings or credentials are stored in Git.
- The downloader tests cover identifying headers, cache corruption, HTTP 429,
  non-retried HTTP 403, bounded timeout retries, document size and redirects.
- This is transport and software verification. It does not open market-return
  outcomes or complete the filing boundary/timestamp audit.

## Source recovery and descriptive pilot, 2026-10-10

- Data: original SEC sources and unchanged private vendor exports from the
  previous checkpoints. All 155 automated filing checks and all 135 conditional
  candidate arithmetic cases reproduce. Candidate/trace hashes match; DuckDB
  container metadata can differ.
- New descriptive exhibits: 135 annual text pairs across 2015–2021, including
  59 pairs in 2019–2021. Median current section length 7,601 tokens; median log
  length change 0.04595; median Jaccard distance 0.09816. TF-IDF median 0.003867
  over 116 pairs, with the initial 19 pairs unavailable.
- Vocabulary policy: strictly earlier acceptance years, separate from the
  model's annual mature-label training restriction. Example selection uses the
  frozen seed and accession hash before outcomes.
- Evidence: `reports/pilot_checkpoint/`, `reports/pilot_arithmetic_summary.json`
  and `reports/build_verification.json`. No empirical predictive model fit or
  human review was created by this descriptive work.

## Full synthetic study integration, 2026-10-10

- Data: invented historical classifications, share classes, liquidity, dated
  links, source evidence, filings, controls and outcomes. Data kind remains
  `SYNTHETIC_ENGINEERING_FIXTURE`, all human review counts zero, model-ready false.
- Selection: 192 annual memberships for 12 invented issuers, 2010–2025;
  144 development and 48 physically separate final observations.
- Primary: eight model/penalty configurations across six development years,
  development reproduction/freeze, four final annual refits, paired three- and
  six-month bootstrap intervals with 2,000 draws each.
- Secondary: six proper text-feature subsets, 24 development configurations,
  288 final ablation predictions, monthly/year/leave-one-year-out diagnostics,
  fixed size/industry reports and source-linked synthetic failures. The final
  wrapper reuses completed saved predictions without opening target tables or
  selecting new penalties.
- Delay arithmetic: independently rebuild 1-, 2- and 5-session event labels and
  controls from a separate invented daily-return source and availability table.
  These directed cases are not empirical delay-performance comparisons.
- Semantic tests: synthetic toy encoder, fixed text hashes and feature receipts,
  four-penalty development selection and frozen secondary final predictions.
  The actual MiniLM encoder was not run.
- Verification command: `make reproduce-full`; 361 tests passed in 62.30 seconds,
  Ruff passed, full demonstration completed. Four existing dependency
  deprecation warnings remain. The verification receipt binds tested source
  hashes and distinguishes all invented outcomes from observed pilot evidence.
- Interpretation: software integration only. No selected synthetic alpha or
  score is an empirical model choice or market finding. Real final access remains
  unopened and all human/source gates continue to apply.

## Expanded pilot, recorded reviews and actual MiniLM execution, 2026-10-10

- Collected 60 additional original SEC filings for 15 issuers selected without
  market outcomes. Resolved five source-bound layout cases and Ford continuation
  headings. Original 155 texts and 135 pairs remain unchanged.
- Combined fresh source audit: 215 filings, 180 pairs, 35 issuers, zero blocking
  findings. The 104 pairs in 2019–2021 meet the planned 100–150-pair count.
  Nineteen reference resolutions and 104 API/header disagreements are preserved.
- Recorded the user's previously completed 20/20 numerical and printed-timing
  review against the exact original packet. The unchanged submitted script
  reproduces saved results and detects the fourth-decimal mutation. Remaining
  source judgments are not silently approved by that arithmetic verdict.
- Actual pinned MiniLM: 155 original filing texts, 135 pairs, 1,459,865 content
  WordPiece tokens, 5,828 chunks, zero truncation. Two independent Python processes
  reproduce all document vectors and pair features exactly. Median descriptive
  distance 0.00632819; no calibrated economic interpretation or outcome model.
- Fixed a real Transformers 5 tokenizer interface incompatibility while preserving
  all chunk token IDs. Named human semantic judgments remain pending.
- Added catalog-validated, monthly, resumable WRDS source export and offline
  verification/assembly. Population defaults to 2010–2021. Both final population
  price/volume windows and final returns require development prerequisites.
  No actual full-study WRDS export occurred in this execution.
- `make reproduce-full`: Ruff and 444 tests passed; complete synthetic study
  passed. Eight dependency deprecation warnings were emitted. All invented
  outcomes remain software fixtures, separate from the real SEC text runs.
- Evidence: `reports/RESEARCH_EXECUTION_UPDATE.md`, `reports/pilot_expansion/`,
  `reports/review_progress/`, `reports/semantic_validation/`, and
  `reports/execution_verification.json`.
