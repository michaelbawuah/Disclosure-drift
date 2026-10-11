# Seven multiple-earlier-CIK cases: original-source findings

**2026-10-11 — source evidence only; no historical security links approved.**

All seven multiple-earlier-CIK cases in the fixed 2020 ownership cohort were reproduced in original SEC filings. Four have an original ownership-symbol inconsistency when compared with the same issuer's separate pre-2020 official filing cover; three have documented corporate transition or parent/subsidiary context. These findings explain why a literal ticker match can be unique in the supplied security universe and still fail to establish issuer identity. They do not supply a continuous historical security-to-issuer mapping.

The [original-source validation report](../reports/ownership_multi_cik_source_validation.json) records **14/14 complete originals preserved**, **154,250 original bytes**, **129 contributing observation rows and 129 unique original SEC TSV occurrences**, and **zero overlap with the previously completed 47 cases**. The separate [corporate-context report](../reports/ownership_multi_cik_context.json) preserves **eight original SEC pages, totaling 3,066,354 bytes**, together with exact source hashes, normalized text, and evidence locations. The [execution receipt](../reports/ownership_multi_cik_execution.json) binds the artifacts and executed code versions.

## What the seven cases show

The symbols below are literal ownership-filing values. The CIKs and issuer names are public SEC facts; private security associations remain on the Mac.

| Case / symbol | Original issuer CIKs and identities | Contributing occurrences | Bounded interpretation |
| --- | --- | ---: | --- |
| 01 / ECOL | 0000742126 US Ecology Holdings; 0001783400 US Ecology | 42 | A documented November 1, 2019 holding-company transition explains related issuers sharing the symbol. |
| 02 / FSFG | 0001435508 First Savings Financial Group; 0001751692 1895 Bancorp of Wisconsin | 24 | The 1895 original ownership filing says FSFG, while its separate 2019 cover says BCOW. |
| 03 / PROS | 0000886982 Goldman Sachs Group; 0001634038 ProSight Global | 11 | The Goldman original ownership filing says PROS, while its separate 2019 common-stock cover says GS. |
| 04 / PVBC | 0001635840 Provident Bancorp; 0001778784 Provident Bancorp | 22 | A documented October 16, 2019 conversion explains old and new entities; the selected old-CIK filing itself is later than the conversion. |
| 05 / TW | 0000098222 Tidewater; 0001758730 Tradeweb Markets | 19 | The Tidewater original ownership filing says TW, while its separate 2019 common-stock cover says TDW. |
| 06 / VLRX | 0001445274 Valeritas; 0001619250 Valeritas Holdings | 3 | A documented May 3, 2016 merger left Valeritas as a wholly owned subsidiary. The two issuer IDs are not interchangeable. |
| 07 / WLK | 0001262823 Westlake Chemical; 0001604665 Westlake Chemical Partners LP | 8 | The partnership original ownership filing says WLK, while its separate 2019 cover lists partnership units under WLKP. |

### Corporate transition and relationship evidence

**ECOL:** The [original November 1, 2019 8-K](https://www.sec.gov/Archives/edgar/data/1783400/000110465919058632/a19-21013_128k.htm) reports the merger effective at 12:01 a.m. Boise time that day. The predecessor became a subsidiary of the new parent; the parent took the US Ecology name and the ECOL symbol. Selected old-CIK accession `0001437749-19-021150` and new-CIK accession `0001437749-19-021175` were both accepted later that morning. The source supports a corporate relationship and transition, without independently establishing vendor security continuity or effective linking intervals.

**PVBC:** The [original conversion 8-K](https://www.sec.gov/Archives/edgar/data/1778784/000094337419000460/form8k_101119.htm) reports completion at the close of business on October 16, 2019. Its [closing release](https://www.sec.gov/Archives/edgar/data/1778784/000094337419000460/ex99-2_8k101119.htm) identifies the new Maryland holding company, says the former holding entities ceased to exist, and states that new shares were **expected** to begin trading as PVBC on October 17. The selected old-CIK Form 4, accession `0001567619-19-021835`, reports October 28 and was accepted November 19; both dates follow the reported conversion. The transition alone therefore cannot validate that later old-CIK usage. Expected trading commencement is not treated as independently verified exchange evidence.

**VLRX:** The [original 2016 merger 8-K](https://www.sec.gov/Archives/edgar/data/1619250/000119312516583971/d180550d8k.htm) describes the May 3, 2016 transaction with Valeritas surviving as a wholly owned subsidiary of Valeritas Holdings. Both selected ownership originals were accepted October 2, 2019. This is a parent/subsidiary relationship established in 2016, not evidence of a 2019 ticker transition or permission to combine the issuers.

### Four original symbol inconsistencies

Each comparison below uses a separate original filing by the issuer named in the anomalous ownership source. The disagreement is present in the SEC source itself; this audit does not decide which original field caused it, silently repair symbols, or treat repeated filings as votes.

| Ownership original | Literal issuer and symbol | Separate original cover evidence |
| --- | --- | --- |
| `0001567619-19-022217` | 1895 Bancorp / FSFG | [September 24, 2019 8-K](https://www.sec.gov/Archives/edgar/data/1751692/000094337419000425/form8k_092419.htm): common stock, BCOW. |
| `0000769993-19-000566` | Goldman Sachs / PROS | [November 2019 8-K](https://www.sec.gov/Archives/edgar/data/886982/000119312519293432/d831594d8k.htm): common stock, GS. |
| `0001567619-19-021775` | Tidewater / TW | [October 2019 8-K](https://www.sec.gov/Archives/edgar/data/98222/000119312519279310/d827369d8k.htm): common stock, TDW. |
| `0001567619-19-021001` | Westlake Chemical Partners / WLK | [2019 third-quarter 10-Q](https://www.sec.gov/Archives/edgar/data/1604665/000160466519000033/a2019093010qwlkp.htm): limited partnership common units, WLKP. |

The Goldman original is particularly useful: its header and ownership XML both identify Goldman as issuer, and one reporting-owner role separately has that same CIK. Both roles are retained. The result is not an accidental parser substitution of a reporting owner for the issuer. Its unusual `periodOfReport` literal, `2019-11-21-05:00`, is preserved verbatim and is not used as an acceptance or availability clock.

## Selection and verification boundary

The Mac selector verified the pinned ownership receipt `85358e4f928687ed9fc3da3813e87980321bbd155b24c952f7a955c5c92a8442`, relevant table-part hashes and exact schemas, all 4,122 stored cohort summaries, all 31,466 stored observations, and all 38,145 original SEC TSV occurrences. It independently regrouped earlier issuer CIKs across that full stored cohort. Exactly seven groups had multiple earlier CIKs, each with two. All 129 contributing observations were retained with their source occurrences and original ambiguity accounting. The upstream Names/CCM population and matching process was not rerun.

For each distinct earlier CIK in each case, selection uses earliest filing date, then accession, then original TSV record as deterministic tie-breakers. It does not use acceptance time to revise selection after seeing the originals, count repeated filings as independent identity votes, or choose the CIK with the most observations.

All 14 original headers and issuer XML prefixes agree with the selected accession, form, filing date, issuer CIK, issuer name, and literal symbol. All 14 original acceptance timestamps precede the stored 2019 year-end information cutoff. Twenty-five header reporting-owner role occurrences are retained separately. XML parsing stops at the direct issuer; holdings, transactions, remarks, and signatures are outside this audit's parsed scope. Source byte spans and decoded text are retained for independent checking. The separate [independent follow-up verifier](../reports/ownership_followup_verification.json) rederived the full cohort selection and checked the 14 original-source results on the Mac; its ownership-source scope does not include the eight context pages.

An original acceptance timestamp establishes that source's reported filing clock. Retrieval in 2026, an HTTP date, and the first selected filing do not establish historical vendor availability, a continuous issuer interval, or `known_at`. All such inferred fields remain unset; historical links, source approvals, and human reviews created by this audit remain zero. Market outcomes and the 2022–2025 held-out evaluation were not opened, and the completed arithmetic and 47-case reviews were not repeated.

## Execution provenance and preservation

The first Mac collection returned HTTP 403 for all 14 fixed URLs. [The failure report](../reports/ownership_multi_cik_originals.json) and its per-attempt receipts are preserved unchanged. A separately authorized ordinary container request using the same public URL and honest research User-Agent returned the first original; that exact response was reused and the remaining 13 originals were fetched once. Container collection used one worker, at least 0.6 seconds between request starts, no automatic retries, and a stop-on-403 rule. Context collection used the same identity and one worker. These are separate observed access results, not a claim that the Mac requests succeeded.

The Mac selector/failure run used a 34,581-byte script, SHA-256 `35eac10f578b226bd286148765e5f169e3e59b44bdf05cc1b295e06ddb9e36a2`. The container used the 34,582-byte canonical script, SHA-256 `0fed56a92283fb6f52301d2a6d98ef4830a7a4deb5d14be4272bf45a00e9383c`. The only byte difference is one final newline. Both exact executed versions are preserved under `outputs/multi-cik-followup-20261011`, together with the source-wrapper and context-script execution snapshots. Existing reports were not rewritten to conceal that difference.

All public originals, context pages, reports, and code snapshots were copied to the Mac and checked byte-for-byte. Licensed associations stay in the existing private Mac file. Seven protected protocol/review/source-report files match their before hashes. The three new scripts pass Ruff; an independent verifier checks actual source and selection evidence rather than adding implementation-mirroring tests.

The acquisition scripts intentionally require fresh output paths and refuse to overwrite this evidence. Preserve this run and verify it from the bound receipts and originals; do not rerun acquisition into the completed directory. The next identity step requires dated authoritative issuer/security evidence for unresolved mappings, while retaining these original anomalies and the existing source gates.
