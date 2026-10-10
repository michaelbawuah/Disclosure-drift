# Decision log

## 2026-10-09 - Initial protocol freeze

- Keep the annual Risk Factors / 20-session question as an extension of Lazy Prices.
- Reserve 2022-2025 for the primary untouched evaluation. Earlier 2019-2021 pilot
  observations are explicitly development data.
- Use raw market-adjusted returns as target, avoiding monthly rank maturity problems.
- Use three simple text features; fit TF-IDF/scaling in each training fold. Whole-year
  cross-sectional feature ranking is prohibited because it uses future filings.
- Select ridge penalties separately for the controls and augmented models from four
  values. Fix all three text features for the primary model, reducing model-search
  freedom; feature ablations are secondary diagnostics.
- Use second-session timing and SGML acceptance headers where retrievable, retaining
  API raw values and a separate public-availability uncertainty field.
- Bootstrap consecutive reference-month blocks, retaining both models' paired
  losses and all firms. Use three months, with six months as a declared sensitivity.
- Preregister the embedding comparison before opening holdout outcomes. Its exact
  checkpoint/chronology/chunking audit is pending and remains an access gate.
- Added-versus-removed risks and the 2020 disclosure-rule transition enter the
  interpretation/audit plan. A thematic or 2026 extension needs a separate protocol.
- Begin with five issuers as extraction fixtures. They do not establish membership
  of the historical investment universe or provide performance evidence.

## 2026-10-09 - Implementation choices

- Python package with uv dependency lock; lxml for conservative extraction, Parquet
  and DuckDB for local tables, scikit-learn for baselines, XNYS exchange calendar.
- Cache SEC response bytes and provenance; do not retry forbidden responses.
- Keep partial extraction failures visible. No silent pairing past a failed prior
  year and no return gap imputation.
- Build and test label arithmetic against invented examples while account/data
  entitlements remain unverified. The 144-row demo is synthetic throughout.
- No remote repository was supplied. This milestone is a local git project plus a
  portable source package; publishing to a GitHub repository is a later connection.

Implementation was co-developed with Codex. Human audit and independent explanation
of the study remain pending. No financial predictive finding is claimed.

## 2026-10-09 - Live-source and edge-case review

- The live sample contains disagreements between API timestamps and SGML headers.
  Preserve both, use the explicit header interpretation for timing, and record the
  difference for manual review. All 20 smoke filings supplied header evidence.
- A zero TF-IDF vector has undefined cosine, not a distance of one. Keep this value
  missing and use only the model's training-fitted imputation; expose its count.
- Remove stale generated tables after an empty ingestion result. A prior successful
  output must not appear to belong to a new failed run.

## 2026-10-09 - Python stack and reproduction command

- Use Python across the study and SQL through DuckDB. Choose pandas as the single
  DataFrame library and keep Python 3.12 as the verified runtime for this checkpoint.
- Standardize SEC transport on httpx, preserving identifying headers, cached-body
  hashes, conservative request spacing and bounded retries. Stream downloads under
  the document-size limit; surface redirects and forbidden responses for review.
- Add `make reproduce` and use it in CI. Its scope is environment synchronization,
  lint, tests, protocol verification and the explicitly synthetic demo.
- Keep the locked reference-month bootstrap and expanding, matured-label folds.
  The proposed filing-week wording does not replace the frozen primary inference.
- Plan Matplotlib/Quarto for reporting and an audited Hugging Face checkpoint for
  semantic features. Add optional statistical/tree libraries when their specified
  stage is implemented; no empirical or semantic result is claimed now.

## 2026-10-09 - Filing evidence and expanded parser pilot

- Add an offline audit command that checks both cached provenance and the stored
  extraction/timing, plus separate assistant and human review counts. Reviews are
  bound to evidence fingerprints and cannot silently survive changed text or dates.
- Use a deterministic, issuer-spread sample of up to 30 eligible pairs for initial
  review, and inspect every flagged filing separately. This is not a population
  extraction-accuracy estimate and does not unlock the final test.
- Expand document-format coverage to 20 selected issuers, using 2014-2021 filings.
  Current ticker metadata supplies discovery only. Preserve the verified historical
  XOM filing CIK; retain Disney's current CIK separately without predecessor splicing.
- Record J&J's 2014-2016 Exhibit 99 references as incomplete standalone Item 1A text.
  Keep affected pairs out until an explicit exhibit-resolution policy is audited.
- Desktop Commander reconnected and ran the existing f09d687 checkpoint on the
  owner's Mac: Python 3.12.14, macOS arm64, 40 tests passed and synthetic demo completed.

## 2026-10-09 - Expanded pilot findings and remote execution

- The audit code at 10cbc067 passed 49 tests in the cloud, on the owner's Mac,
  and in GitHub Actions. Local/Mac Python was 3.12.14; CI used 3.12.3.
- The Mac's SEC smoke download received five HTTP 403 responses and retrieved no
  filings. No forbidden response was retried. Public-source pilot evidence comes
  from the successful cloud ingestion; Mac execution verifies the code and demo.
- Preserve the first pilot summary, which used the original in-memory XOM discovery
  CIK, then rerun the corrected configuration against the existing cache.
- Intel 2018-2021 and GE 2015-2021 have short Item 1A index entries pointing to
  substantive sections elsewhere. Keep those failed extractions and affected pairs
  explicit. Add and audit a section-reference resolver in a later parser revision.
- Publishing this engineering evidence does not complete human review, establish
  a historical investment universe, or open the final evaluation period.

## 2026-10-09 - Source-bound reference resolution

- Recover 24 source filings and headers for J&J, Intel and GE after workspace
  maintenance cleared the ignored cache. Require their hashes and baseline text
  hashes to match the previously published milestone 02 manifest.
- Register explicit normalized text ranges for 11 same-document page references
  and three incorporated J&J Exhibit 99 documents. Pin source bytes and text hashes;
  verify each exhibit's unique typed entry in its original accession index.
- Keep original acceptance timing and all ten unaffected texts unchanged. Retain
  the source-method transition on each annual pair for review. No new statistical
  predictor or outcome-dependent selection rule is introduced.
- Bind reviews to the resolution rules as well as source hashes. Verify paired
  texts, source metadata and immediate annual predecessors against audited filings.
- Treat the 24-filing comparison as a targeted regression sample. It does not
  replace a rerun of the full 155-filing pilot or a human boundary/timing audit.
- The local full reproduction passes 70 tests. Market-return data and 2022-2025
  forecast outcomes have not been loaded. The primary protocol remains unchanged.

## 2026-10-09 - Market-data import and label staging

- Add an explicit normalized Parquet import with source/field declarations, hashes,
  strict return and identity checks, and queryable DuckDB tables. No CRSP adapter
  or account entitlement is presumed. Verify an actual export dictionary first.
- Record return and benchmark conventions as declarations, not proven facts. Keep
  raw missing codes upstream; reject missing values rather than convert them to zero.
- Bind event exports to the complete source-audit inputs, including pair and
  evidence hashes. Preserve pending human review. Reject duplicate annual pairs.
- Keep labels in a separate engineering staging table without text predictors or
  controls. Record every failed identity or return window as an exclusion. Synthetic
  market data cannot be attached to real filing events.
- Restrict market imports to the development label horizon, including the small
  early-2022 tail needed by late-2021 filings. Reject final-period filing events
  before loading return values. The primary protocol and final gate are unchanged.

## 2026-10-09 - Complete source comparison and checkpoint 04

- Rebuild all 155 original filings from the 20-issuer pilot with zero ingestion
  failures. A fresh offline audit accepts all 155 automated evidence records and
  produces 135 annual pairs. Human review is still pending for every filing.
- Match every original filing/header hash to milestone 02. Preserve all 141
  unregistered text hashes and every original event date; reproduce all 14
  registered risk sections. Retain 72 API/header timestamp cautions and the
  three source-method transitions. Disney's missing first predecessor stays excluded.
- Export 135 events bound to the audit's filing, pair and evidence hashes, without
  attaching any market returns. Publish the full source review packet and a
  deterministic initial sample of 30 pairs.
- Code commit 7653be88 passes 103 tests, lint, the protocol lock and both synthetic
  examples in the cloud, on the owner's Mac and in GitHub Actions. Source-data
  reproduction runs in the cloud; the Mac's earlier SEC HTTP 403 is not retried.
- No actual market export or vendor mapping has been verified. Next obtain an
  authorized sample and its dictionary, then audit historical selection and controls.

## 2026-10-09 - Milestone 05 preparation, access still pending

- Verify Cornell's published day-pass route and document a minimal AAPL daily-return
  query in January 2021. A successful export verifies that table's entitlement only;
  no authenticated export or private account entitlement has been observed yet.
- Generate exact market-data request windows from the 135 audit-bound filing events.
  Select 20 trace reviews using a seeded hash without outcomes; leave all pending.
  Preserve the separate 30-pair filing and registered-reference audit requirements.
- Implement the existing 20/60-session control definitions with complete, unfilled
  historical windows, sample daily volatility and exact-date industry/size snapshots.
  Normalize capitalization to USD before its natural log. No primary predictor,
  evaluation period or model-selection choice changes, and the protocol lock is intact.
- Test the calculator on invented values, including independently known arithmetic
  and future-outcome perturbations. A real snapshot adapter and its source-availability
  audit remain pending; label staging is still separate from model-ready data.
- Replace a broken CRSP documentation link with WRDS's current format-guidance page.

## 2026-10-09 - Real WRDS samples and header-identity mismatch

- Inspect the owner's actual daily-stock, historical Names and CCM exports; record
  exact file hashes, schemas and counts without publishing licensed source rows.
  Confirm matching bytes in the owner's Downloads folder. Sample access is now
  observed, while complete research coverage remains unverified.
- Preserve literal return-quality codes, blank optional fields and CCM end-date
  markers in the raw files. The CCM form showed 51 selected variables, but both
  returned CSVs have 47 columns; record the observed schema rather than claiming
  that all 51 were delivered. The core link fields are present.
- Accept the CCM CSV-only result with its available query-page evidence. Do not
  fabricate vendor SQL. Query 11768919 returned 60 rows for 19 requested CIKs.
  The separate XOM ticker request returned two rows carrying a different header
  CIK from the original pilot filings. Preserve both identities for dated review.
- Treat the resulting 20-security list as a candidate retrieval list only.
  Header CIKs, company names and SIC codes are not made historical by CCM link
  dates. Do not splice predecessor filings or approve identity substitutions.
- Next obtain historical Names for the candidate securities, then the requested
  development-period market windows. Keep independent human review, delisting QA,
  full-universe selection and the final-period evaluation gate unchanged.

## 2026-10-09 - Full pilot Names export checked

- Receive 237 historical security-description rows for all 20 candidate PERMNOs.
  Verify the exact 24-column order and requested identifiers against the supplied
  vendor SQL from `crsp_a_stock.wrds_names_query`; do not execute uploaded SQL.
- Check unique interval keys, valid security bounds, contiguous nonoverlapping
  histories and exactly one match at each of four boundaries for 135 pilot events.
  All 540 boundary checks pass using provisional retrieval associations only.
- Preserve the distinction between historical and header SIC. They differ at
  76 controls dates, so current header classifications cannot substitute for the
  historical snapshots. The original Apple sample is reproduced without changes.
- The historical Names records support the XOM candidate for development dates;
  they do not include CIK or replace independent identity review. The original
  filing CIKs, primary protocol and pending human audit states remain unchanged.
- Archive the supplied files outside public git and record hashes. Proceed to one
  daily-stock export for the existing 2014-11-04 to 2021-12-28 pilot envelope.
  No actual event labels, fitted models or final-period outcomes are produced.

## 2026-10-10 - Full pilot daily export checked

- Receive and privately archive 36,000 daily rows with all ten requested columns.
  Verify the attachment against the owner's Mac download by exact SHA-256.
  Every candidate security has all 1,800 expected sessions from 2014-11-04 through
  2021-12-28, without duplicate or missing keys. Returns and capitalization pass
  finite-value/domain checks, and benchmark values agree across securities.
- Join every row to exactly one dated Names record; PERMCO agrees. Reproduce the
  five-row Apple access sample. With provisional retrieval associations, verify
  the 60 control sessions, entry-reference date and 20 label sessions for all
  135 events. This verifies data coverage only, not approved historical identities.
- Keep all 36,000 literal `NA` return-quality codes. There are no `Y` delisting
  rows. Request a separate Whole Foods August 2017 cash-merger example using
  public Nasdaq corporate-action evidence, chosen for terminal-return QA rather
  than predictive performance. Do not add it to the model sample or count it as
  an independent human review.
- Record the daily vendor SQL, query ID and exact source release as not supplied.
  No real event labels, controls, fitted models or final-period outcomes are
  generated by this inspection. The frozen protocol and evaluation gate remain.

## 2026-10-10 - CIZ source staging and missing terminal evidence

- Inspect the supplied WFM export: ten ordinary trading rows from 14 to 25 August
  2017, PERMNO 77281, 13 columns and no Y delisting flag. Its ordinary price-change
  arithmetic agrees within delivered rounding and its benchmark matches the pilot.
  Preserve the exact bytes privately and record that terminal-payoff QA is incomplete.
- The cause of the absent terminal row is not established by the CSV. Obtain the
  existing query's SQL or submitted parameters before specifying a corrected
  download. Do not invent a cash-return observation from the public merger amount,
  assume the user entered the dates incorrectly, or assert a ticker-filter cause.
- Add `stage-crsp` for the observed daily and Names schemas. Preserve literal NA
  source codes, leave DlyRet unchanged, convert DlyCap from thousands to USD, and
  join SIC through inclusive historical intervals. Report coverage gaps and invalid
  size snapshots; reject unsupported return codes, ambiguous joins and holdout rows.
- Stage 36,000 pilot return rows, 1,800 benchmark rows and 36,000 dated snapshots
  in private Parquet/DuckDB. Hash raw files, outputs and normalization code.
  Leave query/release metadata and all unverified audit flags explicit. No approved
  CIK links or import-ready manifest are created, and no actual labels or controls
  are calculated. Header CIKs remain separate from historical filing identities.
- Cloud `make reproduce` passes 154 tests, Ruff, the frozen protocol check and both
  synthetic demos. Invented terminal cases test arithmetic; they do not replace
  the missing actual terminal observation or independent human review.

## 2026-10-10 - Historical identity review packet

- Add `review-identities` to assemble source-bound development events, original
  SEC headers, CCM candidate records and dated Names evidence. Verify the audited
  annual pair before using either accession. Read no market returns.
- Check all 155 cached headers against original CIKs, accessions and 10-K forms.
  Assemble 135 event candidates and verify all 10,935 required dated-description
  sessions. Retain seven Exxon header-CIK differences, all literal `E` end markers
  and every pending human verdict. No ticker match, first candidate, header CIK or
  company-name similarity is promoted into an approved mapping.
- Keep source records and the detailed review packet private; publish aggregate
  counts and hashes only. The command cannot approve or import links. Existing
  WFM terminal QA, source release/availability and manual audit requirements remain.
- Cloud `make reproduce` passes 178 tests, Ruff, the frozen protocol check and
  both synthetic demos. No real labels, controls or fitted models are generated.

## 2026-10-10 - Corporate sources and a real identifier-change case

- Locate SEC primary evidence for Exxon's July 2026 holding-company reorganization,
  both registrant CIKs and the old/new common-stock CUSIPs. These identities explain
  the observed historical-filer/current-header pattern, without certifying vendor
  provenance or approving the historical security link. Cache this material apart
  from model filings; preserve original CIKs and the existing review packet.
- Check GE's August 2021 reverse-split CUSIP transition against its SEC 8-K and
  the supplied Names/daily files. Reproduce ten source/staged sessions across two
  contiguous Names intervals, stable permanent IDs, dated snapshots and unchanged
  return values. Five pre-change rows expose a current-header/dated-CUSIP difference.
  This is identifier QA, not an independent split-return or human-review result.
- Record WRDS's official `.E` join predicate as support for an open-ended candidate
  interpretation. Leave extract-specific bounds, release metadata and approvals
  pending. The WFM terminal observation is still absent; diagnose its original
  query before requesting a new export. No labels, fits or holdout results are added.

## 2026-10-10 - WFM terminal observation recovered and checked

- Read the original query screenshots: query 11769187 used the requested
  14 August-8 September 2017 dates and a WFM ticker filter. Preserve displayed
  times without inventing a timezone, and keep absent SQL/release metadata explicit.
- Archive the PERMNO follow-up, matching the Mac download byte for byte. All ten
  original records are unchanged; one 28 August terminal record is added with a
  blank ticker, DA price flag, zero price and missing capitalization. The blank
  ticker is consistent with the retrieval difference; exact SQL internals remain unknown.
- Reconcile delivered DlyRet against the SEC-documented cash consideration within
  CSV rounding. Read CRSP's DA and delisting-date definitions. Use the external
  cash amount only as an independent comparator; never replace the vendor return.
- Verify unchanged normalized returns and missing terminal size. Use existing pilot
  benchmark observations to check two artificial 20-session label windows against
  independent Decimal products, with ten and 19 post-terminal cash sessions. The
  original incomplete file fails both cases for the missing terminal observation.
- Add an invented-data regression for blank ticker/zero DA price/missing size;
  28 CIZ tests pass. Publish aggregate checks and hashes, keeping detailed arithmetic
  private. Preserve the original staging receipt and record follow-up evidence
  separately. Automated terminal-case QA passes; human reviews and historical
  identity/source availability gates remain pending. No real filing labels,
  model results or final-period outcomes are added.

## 2026-10-10 - Complete the candidate label/control arithmetic workflow

- Restore the unchanged source-bound 135-event queue and identity evidence. Stage
  the existing daily/Names exports again with original bytes preserved. No new
  WRDS download or final-period data is needed for the arithmetic review.
- Add `audit-pilot-market`: verify filing, pair, identity, export-plan, raw source
  and staged-table hashes; retain only unambiguous candidate rows for conditional
  calculations. Keep historical CIK approvals, open end markers and source release
  assumptions unresolved. Do not generate approved links or an import manifest.
- Calculate all seven numeric label/control measures for 135 candidate cases and
  reconcile them with independent Decimal arithmetic using the raw CSVs. All 135
  pass, zero cases are blocked, and maximum absolute difference is about 1.43e-15
  against the 1e-12 tolerance. Dated SIC is independently matched too.
- Generate all 20 previously selected arithmetic traces, with 60 control records,
  20 label records, exact-date capitalization/industry and source record references.
  Do not inspect outcomes to change the review sample. Publish aggregate counts
  and hashes; keep licensed rows and all individual calculated values private.
- Add evidence-bound review ingestion that preserves pending records, rejects stale
  or duplicate declarations, and distinguishes human from assistant reviewers. No
  human verdict is supplied by this build. It does not authenticate reviewers or
  approve historical identities, availability, filing boundaries or model inputs.
- `make reproduce` passes 190 tests, Ruff, the frozen protocol and both synthetic
  demos. New tests cover independent arithmetic, reference-day exclusion, changed
  source/plan evidence, holdout-before-market refusal, candidate ambiguity, wrong
  capitalization units, output preservation and stale/assistant review handling.
- Keep Milestone 05 open for historical identity/class and end-bound approval,
  release/availability review, independent filing/trace review and approved import.
  Candidate calculation success is not a research result or final exclusion policy.

## 2026-10-10 - Build the M6–M11 pipeline and preserve empirical boundaries

- Continue under the frozen v1.0.0 primary protocol. The earlier planning PDF
  does not override the later unranked target, 2022–2025 final years or moving
  reference-month bootstrap. No primary protocol or lock change was made.
- Recover the existing private source checkpoint and rebuild the 155-filing
  audit and all 135 candidate arithmetic checks. Preserve 72 timestamp
  differences, 14 reference resolutions, seven header-CIK differences, pending
  source availability and all unresolved historical-link bounds. Human reviews
  remain zero. Reproduced candidate/trace values do not approve identities.
- Publish a source-audit-bound text checkpoint with immutable byte reads,
  per-pair evidence checks and deterministic examples. Report only 59 pairs in
  2019–2021; the 135-pair 2015–2021 parser sample is not equivalent to the
  original plan's 100–150-pair checkpoint or the historical population.
- Implement the full historical selector using information available before
  each year start, one most-liquid eligible class per CIK and the frozen
  60-session/40-valid-session rule. Bind memberships and exclusions to sources.
  Build an outcome-free request from October 7, 2009 liquidity through the
  February 3, 2026 final label tail.
- Assemble explicit one-to-one model inputs with dated controls, reconstructed
  clocks, label arithmetic and actual hashed source/review records. Split final
  features from targets. Pending/failed/stale reviews remain unresolved; an
  assistant or a boolean cannot supply a human pass.
- Reproduce development selections before freezing, bind the exact running
  source and Git commit, and reserve persistent final access before reading the
  target snapshot. Allow exact same-freeze reproduction and automatic annual
  mature-label refits; refuse changed procedures after final access.
- Add six separately selected development-only ablation models and fixed
  diagnostics. Final secondary runners consume only the original completed
  run's verified saved outcomes. Rebuild reference-delay inputs independently;
  preserve unavailable results and declared bootstrap settings.
- Pin a separate retrospective MiniLM comparator by revision, safetensors and
  tokenizer/config hashes. Use all tokens in fixed chunks. Unknown training
  cutoffs remain unknown; actual encoder execution and named human examples
  remain pending. Synthetic semantic tests use a declared toy encoder.
- Use Matplotlib and ReportLab for portable figures/PDFs inside the locked
  Python environment. Publish an eight-page progress report, four-page pilot
  checkpoint and repository overview, without fabricated empirical tables.
- `make reproduce-full` passed Ruff, **361 tests**, protocol verification,
  existing demos and the full 192-membership/144-development/48-final synthetic
  integration. The final score, confidence intervals and research milestone
  sign-offs remain pending for actual data. Independent assistant cross-review
  is not the plan's independent-person reproduction.
