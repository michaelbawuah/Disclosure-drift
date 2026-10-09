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
