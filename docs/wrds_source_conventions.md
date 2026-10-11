# WRDS source conventions and proposed normalization

**Status: evidence review and candidate policy; zero new source approvals.**
This document connects vendor definitions to proposed normalization of the
received development exports. It does not declare those exports model-ready,
approve historical identities, or change the
[frozen protocol](../configs/protocol.json). The user's completed
[20/20 arithmetic and printed-timing review](../reports/review_progress/user_arithmetic_receipt.json)
remains complete and is not extended to these separate source judgments.

## 1. Verified inputs and remaining evidence

The [execution update](../reports/RESEARCH_EXECUTION_UPDATE.md) records four daily
batches covering the requested development dates **2009-10-07–2022-02-02**, plus
locally preserved Names, combined CCM/company metadata and the independent
market file. The early-2022 tail serves late-2021 labels; it does not authorize
evaluation of 2022 filings. Raw date coverage does not certify the historical
security universe. No licensed rows were read to prepare this document.

| Evidence layer | What it establishes | What remains unresolved |
|---|---|---|
| Private raw files and inventory receipts | Preserved bytes, hashes, observed fields, date coverage and declared check scope | Vendor universe completeness, source vintage and historical availability |
| Vendor dictionaries and examples below | Meanings of documented fields and codes | Whether the delivered product/release follows every documented convention |
| Candidate policies in this document | Explicit proposed inclusion, conversion and unresolved-record rules | Source-bound review and empirical execution |
| Historical identity evidence | Candidates and documented corporate events | Approved security/issuer links at each research date |

The [manual inventory guide](wrds_daypass_export.md) describes the implemented
checks. Normalization must retain source-file hashes and row references, produce
an explicit exclusion/unresolved ledger, and preserve original files unchanged.

The [benchmark source decision proposal](benchmark_source_decision.md) requires
a source-backed, reviewed choice of value-weighted total returns on the protocol's
identical sessions; it does not require equality between the two export views.
The saved independent series is proposed for review, with all 52 differences
still unresolved. Their size alone cannot establish or exclude a precision
explanation: a smaller difference can cross a rounding boundary. No source
selection, tolerance or approval is enacted by that proposal.

## 2. Returns: preserve `NA`; keep `MV` unresolved

**Vendor evidence.** The official CIZ guide defines `DlyRet` as the daily total
investment return and states that `DlyRetMissFlg` is `NA` when a return is
available. The [CRSP return-missing dictionary](https://www.crsp.org/wp-content/uploads/appendix/FlagType_RM.html)
defines `MV` as a missing corporate-action value. It does not establish that a
numeric value carrying `MV` is a complete usable total return. See the
[official guide reference and access note](#9-official-guide-reference-and-release-evidence).

**Candidate policy:**

| Source condition | Proposed treatment |
|---|---|
| Literal `NA` and finite `DlyRet >= -1` | Retain the delivered return unchanged as an arithmetic candidate, subject to dates, uniqueness and source review |
| `MV`, including a finite numeric return | Preserve the value and flag; mark the return unresolved and unavailable to an approved return window until supported by further evidence |
| Other missing-return codes, blank/nonfinite values or returns below `-1` | Preserve the source and record the reason; do not substitute zero or a price-only return |

Generic CSV null inference must not erase literal `NA`. A return flag and its
numeric value must be checked together. A window requiring an unresolved return
must be reported explicitly rather than silently shortened. The proposed
NA-only admission rule is a conservative project choice, not a claim that CRSP
requires every study to discard the same observations. Meanings from a different
monthly or delisting flag family cannot be assigned to daily `MV`.

## 3. Delisting payoffs must enter once

**Vendor evidence.** The [WRDS CIZ webinar, daily delisting example](https://wrds-www.wharton.upenn.edu/documents/2084/Webinar.pdf#page=13)
shows delisting returns in the main CIZ daily time series. The
[CRSP convention dictionary, `DelistConvDaily`](https://www.crsp.org/wp-content/uploads/appendix/FlagType_MU.html)
places the daily delisting fields on the trading day following the delisting
date by convention; that date need not be the payment date.

**Candidate policy:** preserve CIZ `DlyRet` and its source date. Do not append
legacy `DLRET`, recompute a payoff from a placeholder price, or shift the
observation to an inferred settlement date. `DlyDelFlg = Y` identifies a
delisting candidate; it alone does not establish a fully paid terminal event.
The [frozen return contract](market_data_contract.md) permits cash continuation
only after a defensible terminal payoff, counted exactly once. Continue the
independent market series over the remaining horizon; do not forward-fill it.

The [existing WFM case](wrds_delisting_check.md) tests this behavior with separate
corporate evidence. It is an automated case check, not blanket approval of every
delisting. The [price dictionary](https://www.crsp.org/wp-content/uploads/appendix/FlagType_PC.html)
distinguishes `DA` (delisting amount without a delisting price) and `DP`
(delisting price); these are not ordinary trading-price eligibility flags.

## 4. Capitalization and the price-volume proxy

**Vendor evidence.** The CIZ guide describes `DlyCap` as daily capitalization in
thousands, based on price and shares outstanding. `DlyVol` counts raw daily
shares without an adjustment for splits during the month. `DlyPrcVol` is the
product of daily price and volume, rather than a sum over individual trades.
The [guide reference](#9-official-guide-reference-and-release-evidence) supports
these field definitions; delivered-source currency and convention evidence must
still be attached to the normalization record.

**Candidate capitalization conversion:** for the documented USD source, use
`market_cap_usd = DlyCap * 1000`, consistent with the existing
[staging contract](crsp_staging.md). Use the natural log only when this result is
finite and strictly positive. Missing/zero values remain invalid for size
controls; negative or nonfinite values require an explicit failure or unresolved
record. Do not replace missing capitalization with a reconstructed estimate or
apply the thousands multiplier to price or volume.

**Candidate liquidity proxy:** use `DlyPrc * DlyVol` when price is finite and
strictly positive, volume is finite and nonnegative, and `DlyPrcFlg` is `TR` or
`BA`. Preserve the flag and report both categories. The
[CRSP price dictionary](https://www.crsp.org/wp-content/uploads/appendix/FlagType_PC.html)
identifies `TR` as a closing trade and `BA` as a bid/ask average. Accepting both
for this proxy is a proposed project policy; a bid/ask average is not an executed
closing trade. Other flags remain excluded or unresolved for liquidity.

The [CIZ price-convention entry](https://www.crsp.org/wp-content/uploads/appendix/FlagType_MU.html)
explains that the legacy negative-price encoding has been replaced by separate
price and flag fields. **Do not apply `abs()` to a negative CIZ `DlyPrc`** to make
it eligible. The proposed product measures approximate dollars traded, not
transaction-level dollar volume. Do not introduce split adjustments or legacy
volume corrections without source evidence. The frozen selector still requires
at least 40 valid observations within the preceding 60 XNYS sessions, as
specified in the [historical dataset contract](historical_dataset.md).

## 5. Projected duplicates are not full-row duplicates

The daily inventory accepts additional columns only with explicit
`--allow-extra-columns`. It retains every source byte, but statistics and
duplicate/conflict checks use the canonical 13-field projection. For the
96-column download, equal projected rows can differ in the other columns;
the receipt therefore records `full_delivered_row_duplicates_checked: false`.
See the [implemented inventory](../src/disclosure_research/manual_wrds_intake.py).

**Candidate policy:** a derived table using only the reviewed projection may
collapse exact projected repetitions with recorded source references and counts.
Never describe this as equality across all delivered fields. Conflicting values
for a security/date remain unresolved; do not choose the first row or average
them. Bringing an extra field into normalization requires rechecking equality
and conflicts over that expanded projection. Reconcile overlaps between files
as well as repetitions within each file. The raw files remain unchanged.

## 6. CCM `E`: candidate matching is not an evidence bound

**Vendor example.** The official [WRDS CIZ industry-ratios macro](https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/wrds-macro-indratios-ciz/)
uses inclusive dates and permits a link when the start is `.B` or the end is
`.E`. This supports investigating an open-bound interpretation of the CSV's
literal `B`/`E` markers. It does not itself certify their representation in the
received extract or supply a finite end date.

**Candidate policy:** preserve original bounds. After documenting the CSV/SAS
marker correspondence, open-marker comparisons may generate candidate matches
inside the requested development window. A clipped analysis interval is merely
the intersection being examined; it is not a vendor-certified validity bound.
Do not replace `E` with today, the download date or an invented extract end.
Blank bounds remain separately unresolved. Do not inherit the macro's link-type,
primary-link or domestic-company screens as approved research filters.

The [identity review](identity_source_evidence.md) and normalized contract still
require defensible effective bounds and identity evidence before an accepted
historical link can enter the universe.

## 7. Current company headers cannot establish historical CIKs

The combined CCM export carries link history and company-header identifiers in
one file, but those roles have different meanings. An interval linking a GVKEY
to a security does not date the accompanying current header CIK. Preserve the
original filing CIK, dated Names evidence and header identifiers separately.

The [SEC-filed Exxon reorganization document](https://www.sec.gov/Archives/edgar/data/34088/000119312526292453/d54886dposasr.htm)
describes the July 2026 creation of the parent/subsidiary relationship. The
project's [corporate-identity evidence](identity_source_evidence.md) explains why
the received modern header can differ from the original filing identity. That
retrospective explanation does not approve a historical CIK/security mapping or
justify splicing predecessor filings into another CIK's annual pair.

**Additional source lead:** the official
[WRDS SEC Suite presentation, slide 22](https://wrds-www.wharton.upenn.edu/documents/1439/WRDS_SEC_Suite_PowerPoint_for_Video_Learning.pdf#page=22)
describes `WCIKLINK_GVKEY` as a GVKEY-to-historical-CIK map useful around
restructurings. The full historical CIK form was subsequently observed for
product `wrdssec_common`, but displayed **Submit Form (Not Subscribed)** under
the selected institution/session (user screenshots labeled 7.31.33 and 7.32.20,
October 10, 2026). This is evidence of the observed access denial only; it does
not establish that the day pass expired or a permanent institution-wide
entitlement decision. No full historical CIK export was secured from that form.
The images and `observation.json` are preserved locally under
`data/private/wrds-intake/historical-cik-access-denied-v1`, with the observation
recorded at `2026-10-10T23:49:57.814374Z`. That recording time is evidence of this
access observation, not historical information availability.
The actual table namespace, delivered schema, coverage, date semantics and
provenance remain unverified. Do not invent SQL or treat the presentation as
proof of an available historical observation. Any later retrieved map would
still need reconciliation against original SEC filings and security-level
evidence.

**Company History alternative:** CRSP's
[Company History dictionary](https://www.crsp.org/wp-content/uploads/ccm_files/CompanyHistory.html)
documents `HCIK` with `HCHGDT`/`HCHGENDDT`, alongside `GVKEY`, `LPERMNO`,
`LPERMCO` and `LINKRANGETYPECD`. This is a documented historical-CIK source to
investigate through authorized CCM access. The dictionary does not establish
the currently exposed WRDS table, this account's entitlement, delivered coverage,
revision vintage or historical `known_at`. See the
[access evidence and unsent request](historical_identity_access_evidence.md)
for the precise source request and the distinction between effective bounds and
historical availability. No new source export or approval is claimed.

## 8. Historical `known_at` remains unresolved

The [normalized universe contract](historical_dataset.md) requires timezone-aware
`known_at` for classifications and identity links, and `available_at` for daily
liquidity. The [selector](../src/disclosure_research/universe.py) applies the
prior-year information cutoff before selecting issuers. This is a project
requirement; the vendor definitions above do not satisfy it.

An observation's effective date, an open link marker, an SEC event date and a
modern retrieval timestamp answer different questions. None can automatically
fill the historical availability field. The actual source-bound availability
evidence is still unresolved. Candidate normalization should retain that
uncertainty and stay outside the approved universe path; it must not fabricate
timestamps to satisfy the strict schema. Later corporate documents can explain
an identity without making the explanation contemporaneously available.

## 9. Official guide reference and release evidence

Field definitions above were checked in indexed text of the official
[CRSP U.S. Stock and Indexes CIZ guide](https://www.crsp.org/wp-content/uploads/guides/CRSP_US_Stock_%26_Indexes_Database_Guide_Flat_File_Format_2.0.pdf),
including the daily-data entries around pages 16–17. That PDF URL now redirects
to the [current official guide page](https://indexes.morningstar.com/docs/guide/crsp-us-stock-databases-guide-for-flat-file-format-2-0?isRdp=true),
which displays **07/31/26** as its effective date. The legacy
`crsp_pdf/crsp-us-stock-indexes-databases-guide-flat-file-format-2-0/` endpoint
returned 404, and the replacement PDF body was not independently retrieved in
this review. This access limitation is recorded rather than hidden.

**A guide effective date is not the release date of the downloaded data.**
Preserve the actual product/view, query evidence, retrieval time, byte hash and
any supplied vendor release evidence separately. Missing release/vintage and
historical availability remain unknown. Documentation, candidate calculations
and automated checks create no new human approvals; the completed 20/20
arithmetic review and the final-period access gate remain unchanged.
