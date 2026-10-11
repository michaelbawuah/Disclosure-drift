# Exxon current-header diagnosis and dated CUSIP candidates

**All eight previously unmatched Exxon pilot filings now have complete saved
Names descriptor candidate coverage at their 656 required date points.** Each
point has one original Names record, with the same raw security identifier as
the original annual selection candidate and a recorded security lifetime that
covers the point. The eight January selection checks also have unique matches.
These are candidate observations: the original ledger remains **207 discoveries
and eight unmatched filings, covering all 215 filings**. No historical security
link, class decision, source approval or forecasting observation was created.

The [aggregate execution and provenance report](../reports/exxon_candidate_diagnostic.json)
binds the completed private Mac audit, the original source receipts, the
[eight original SEC issuer/CUSIP observations](exxon_public_identity_evidence.md),
and the separate explanation for the current company-header CIK.

## Why the original CIK discovery did not find Exxon

The problem is present in the preserved CCM source's company-header value.
The full **110,124-row** original CCM CSV contains **zero** rows whose CIK
comparison key is the original pilot issuer, `0000034088`. The security found
through the saved XOM Names observations has two original CCM records. Both
carry company-header CIK `0002115436`.

For each selection year from 2010 through 2021, the original identity builder
retained both relationships. One is before-selection context; the other has an
open date marker and remains an unresolved candidate. All 24 relationships
have exact raw Names-to-CCM security and company identifier comparisons. The
annual evidence has one candidate header CIK in each of the 12 years, and that
CIK differs from the historical pilot filer. The 2020 foundation projection
also retains one rank-eligible Names candidate; a numerical candidate is not an
approved security link.

| Saved evidence | Verified result |
|---|---|
| Full CCM source records with historical pilot CIK `0000034088` | 0 of 110,124 |
| Original CCM records related to the XOM Names identifier | 2, both with comparison CIK `0002115436` |
| Original annual relationships, 2010–2021 | 24: 12 before-selection context and 12 unresolved open-marker candidates |
| Annual candidate evidence rows | 12, each retaining one usable header CIK |
| Original Exxon SEC discovery matches | 0; all eight unmatched records retained |

The original [identity matching code](../src/disclosure_research/manual_wrds_identity_candidates.py)
requires a candidate relationship, the same acceptance year and equal CIK
comparison keys. Those keys preserve this observed issuer distinction. The
audit verified the delivered source CIK against the retained CCM and
relationship records; it found no dropped eligible Exxon relationship or CIK
parsing error in this path.

## The different CIK belongs to a later successor

An original [SEC Form 8-K12B filed July 1, 2026](https://www.sec.gov/Archives/edgar/data/2115436/000119312526291990/d71068d8k12b.htm)
reports completion of Exxon Mobil Corporation's redomiciliation and identifies
ExxonMobil Holdings Corporation as its successor registrant. It describes a
one-for-one common-share exchange and continuation of the XOM trading symbol.
The [original SGML header](https://www.sec.gov/Archives/edgar/data/2115436/000119312526291990/0001193125-26-291990.hdr.sgml)
identifies the filer as CIK `0002115436`, accession
`0001193125-26-291990`, with recorded acceptance
`2026-07-01T12:36:49-04:00`.

This later successor context explains why a current company-header CIK must
not substitute for the original 2014–2021 filing issuer. It does not establish
when or how the vendor updated the saved header, certify the export's vintage,
or provide knowledge that was available during the development years.
The 2026 document was read for this identity explanation only; it supplied no
returns, model features or historical mapping approval.

The exact primary document is **38,031 bytes**, SHA-256
`9ca958ea709ba234a6320b36f0bd78c3f010c658b8dcf783d7ada0a991d499ce`.
Its original header is **850 bytes**, SHA-256
`6315ca044e73e0885efb808a5741171d48ee680112dcb0e425715b6c4a9aa5ed`.
The report preserves retrieval metadata, header byte anchors and primary
paragraph locators. Complete original public bytes remain outside Git.

## How the new descriptor candidates were checked

Each original 2014–2021 Schedule 13G/A observation identifies issuer CIK
`0000034088` and reports Common Stock with CUSIP `30231G102`. The audit independently
verified all 16 original headers and primary documents on the Mac against the
published source ledger, including the subject-company role, cover literals,
acceptance-clock anchors and their association with the original pilot manifest.

For this candidate search, the audit took the **first eight literal characters**
of the reported nine-character CUSIP, giving `30231G10`. This is a declared
string projection. It is not an authoritative identifier conversion, an
approved CCM relation, or evidence of a continuous issuer/security interval.

The full original Names CSV was read before the target queries. All **191,048
records**, all **24 raw fields**, and all **four date fields** were checked.
Every finite descriptor and security-lifetime interval was checked for ordered
bounds. The lookup then searched the complete source for an exact `cusip`
literal and inclusive descriptor-date coverage. It retained every match before
comparing identifiers and security lifetimes; it did not preselect a security
identifier to make the result unique.

For each of the eight original pilot 10-Ks, the existing frozen `event_window`
and `control_sessions` functions supplied the acceptance date, 60 control
sessions, reference session and 20 label sessions. The dates were used only to
query descriptors. No price, return, label value or feature was read or built.
Each year also received a separate January 1 descriptor check.

| Date role | Requested points | Unique original Names matches |
|---|---:|---:|
| Pilot acceptance | 8 | 8 |
| Controls | 480 | 480 |
| Reference | 8 | 8 |
| Label-session descriptors | 160 | 160 |
| **Filing-window total** | **656** | **656** |
| Separate January selections | 8 | 8 |

Across the 656 filing-window points there are **three distinct original Names
records** and 656 point-to-source-record occurrences. There are no missing or
ambiguous matches, no raw security-identifier disagreements with the original
annual candidate, and no recorded lifetime failures. The January checks also
have no identifier disagreements or lifetime failures.

The global exact CUSIP-literal lookup found nine original Names records. The
private audit preserves **13 original Names history records** in total,
including the complete saved history for the selection identifier, plus both
related CCM records and all related original candidate records. Full raw
records, source ordinals and security identifiers remain private.

## What the date coverage does and does not establish

Every paired same-year SEC corroboration precedes its pilot 10-K acceptance.
However, **379 of the 656 requested date points precede that paired SEC
corroboration's acceptance calendar date**. All eight same-year corroborations
also follow their January selection date. Earlier public observations remain
preserved, but repeated CUSIP text and descriptor-date coverage do not determine
historical source availability or a continuous CIK link.

The new result establishes complete saved descriptor candidate coverage at the
requested dates. It leaves `known_at`, `available_at`, historical CIK interval
bounds and class approval unresolved. The acceptance clocks are recorded SEC
timestamps, not verified first-public-dissemination times. Neither the 2026
successor document nor the October 2026 download times are used as earlier
knowledge.

## Preservation and verification

The audit ran on the Mac at commit
`875ace6a39542998bce151895cba9dd447c379c4` and completed successfully. Before
matching, it bound all **98 identity parts** and **135 foundation parts** to
their saved receipts. It independently compared every one of the **86,064
Names candidate rows** to all 24 original raw fields, and every one of the
**110,124 retained CCM rows** to its original 12-field projection and full
delivered-row hash. All 266 consumed files were checked again before completion.

The reproducible audit program and exact input-receipt snapshots are preserved
inside the new private audit. Files have mode `0400` inside `0700` directories;
the audit refused to replace an existing output. Original source files and
the original discovery/coverage tables remain unchanged. The program is an
ignored research audit, not a modification to production matching code.

| Artifact | SHA-256 |
|---|---|
| Private audit receipt | `3fca689b6e66d15e5b7a208544e6f5ca5ea3982bbabd3f5b2f675d11c3a0e514` |
| Exact Mac aggregate | `50ffbe692d6355ecd66af8a9a669cdf739faf0ab6d728ec710c047674585d3d4` |
| Audit program | `b3740d8bd458d5ea1e65751fedd7c69249da6173610d7a7316eb704bcc5fbcea` |
| Original SEC issuer/CUSIP ledger | `9a0b4f64f71eebd8deee4820b59bb89ccde671a46967945d8192706917be4b2d` |

The private output is `data/private/identity-followup/exxon-v1`. The public
report contains aggregate counts and provenance, without licensed vendor rows
or raw security identifiers. This work creates zero source approvals, human
reviews, class decisions, approved exclusions or historical links. The original
arithmetic review and frozen protocol remain unchanged; `model_ready` is false
and the 2022–2025 final-period returns and features remain unopened.
