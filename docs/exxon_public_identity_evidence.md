# Original Exxon issuer and common-stock CUSIP observations

Eight original SEC Schedule 13G/A filings, accepted during **2014–2021**,
independently corroborate the original issuer CIK behind all eight unmatched
Exxon pilot filings. Each original header identifies **EXXON MOBIL CORP,
CIK `0000034088`, as SUBJECT-COMPANY**. The primary document in that same
accession reports **Common Stock, CUSIP `30231G102`**. These are dated documentary
observations; no vendor security link or historical availability is approved.

The [source ledger](../reports/exxon_public_identity_evidence.json) records all
16 exact source URLs, SHA-256 hashes, byte counts, download clocks, selected HTTP
metadata, raw field locations, and the binding to the eight previously verified
10-K records. Original headers and primary documents total **236,183 bytes** and
were downloaded on **October 11, 2026, 15:28:57–15:30:46 UTC**. The complete
original bytes and individual receipts remain in the ignored directory
`outputs/public-identity-followup-20261011/`.

## What the original records say

Each accession below links to its preserved primary source on SEC.gov. Acceptance
times are the original SGML clock interpreted in `America/New_York`; all these
January/February observations have UTC offset `−05:00`.

| Reported event date | SEC acceptance, Eastern | Reporting party | Original accession |
|---|---|---|---|
| December 31, 2013 | January 29, 2014, 07:26:07 | BlackRock | [0001086364-14-000843](https://www.sec.gov/Archives/edgar/data/34088/000108636414000843/exxon.mobil.corp..txt) |
| December 31, 2014 | February 11, 2015, 11:52:05 | Vanguard | [0000932471-15-005142](https://www.sec.gov/Archives/edgar/data/102909/000093247115005142/exxonmobilcorp.htm) |
| December 31, 2015 | February 10, 2016, 09:36:50 | Vanguard | [0000932471-16-010846](https://www.sec.gov/Archives/edgar/data/102909/000093247116010846/exxonmobilecorp.htm) |
| December 31, 2016 | February 10, 2017, 15:01:42 | Vanguard | [0000932471-17-002034](https://www.sec.gov/Archives/edgar/data/102909/000093247117002034/exxonmobilcorp.htm) |
| December 31, 2017 | February 9, 2018, 10:46:23 | Vanguard | [0000932471-18-003753](https://www.sec.gov/Archives/edgar/data/102909/000093247118003753/exxonmobilcorp.htm) |
| December 31, 2018 | February 11, 2019, 11:59:52 | Vanguard | [0000932471-19-004963](https://www.sec.gov/Archives/edgar/data/102909/000093247119004963/exxonmobilcorp.htm) |
| December 31, 2019 | February 12, 2020, 09:24:04 | Vanguard | [0001104659-20-018249](https://www.sec.gov/Archives/edgar/data/102909/000110465920018249/tv01546-exxonmobilcorp.htm) |
| December 31, 2020 | February 10, 2021, 10:02:30 | Vanguard | [0001104659-21-017224](https://www.sec.gov/Archives/edgar/data/102909/000110465921017224/tv0035-exxonmobilcorp.htm) |

All eight acceptance clocks precede their respective same-year unmatched pilot
10-K acceptance. The ledger binds those contextual pairings to the pinned
[discovery report](../reports/sec_identity_discovery_context.json), SEC manifest,
and [original SEC evidence](sec_identity_evidence.md). This task reread the new
13G/A originals; it did not reread the large 10-K source files or modify their
earlier verification claims.

### Subject company and reporting party remain separate

The [2014 original header](https://www.sec.gov/Archives/edgar/data/34088/000108636414000843/0001086364-14-000843.hdr.sgml)
puts Exxon CIK `0000034088` in `SUBJECT-COMPANY` and BlackRock CIK `0001364742`
in `FILED-BY`. The seven later headers put the same Exxon CIK in
`SUBJECT-COMPANY` and Vanguard CIK `0000102909` in `FILED-BY`; the
[2019 header](https://www.sec.gov/Archives/edgar/data/102909/000093247119004963/0000932471-19-004963.hdr.sgml)
is one example. The archive-directory CIK and accession prefix are not used to
identify the issuer. This distinction matters because a search for a CIK can
return filings in which that entity is the reporting investor.

The reader checks the header accession against the archive directory, the
primary document's original `FILENAME`, `TYPE` and `SEQUENCE` wrapper, and the
saved SEC discovery document ID. It checks each front cover's issuer, class,
CUSIP and event labels in order. Raw byte offsets point to the unchanged source
values. A standard HTML parser provides a text-reading aid for the seven HTML
covers; its decoded, whitespace-collapsed text is not treated as original bytes.
The 2016 filename's `exxonmobilecorp` spelling and the primary issuer-name
punctuation differences remain preserved.

## Time and coverage limits

**Six acceptance observations precede January 1, 2020.** The February 2020 source
reports a December 2019 event, but its acceptance cannot be moved back to the
January 2020 selection cutoff. The February 2021 source remains separate too.
All eight are after January 1 of their own filing year. Matching repeated class
and CUSIP text does not establish continuous validity between the observations,
or coverage of every selection, control, reference and label date.

The [SEC timestamp explanation](https://www.sec.gov/about/webmaster-frequently-asked-questions)
distinguishes acceptance, filing and change dates and does not supply a timestamp
for first website availability. The original `FILING-DATE` and
`DATE-OF-FILING-DATE-CHANGE` values are retained separately. HTTP modification
dates and the 2026 download clock describe the retrieved copy. Neither becomes
historical `known_at` or `available_at`. The preserved SEC guidance and related
source limits are documented in the [public-source note](public_historical_identity_sources.md).

The 23-hit SEC search, limited to 2010–2021 and the two requested 13G form types,
served only to find documents. This eight-accession sample is not an exhaustive
history of ownership filings, identifier changes or security classes. Original
headers and labeled primary content supply the observed facts.

## Consequence for the remaining identity work

The evidence provides a specific reported common-stock CUSIP to compare with
the authorized, dated Names/CCM records. Such a comparison must preserve competing
CIKs, descriptor intervals, raw identifiers and source occurrences. It still
needs evidence for historical security-link bounds, source availability and
the eventual class decision.

The frozen accounting remains **207 existing discoveries plus eight unmatched
filings, covering all 215 original filings**. This note adds no approved mapping,
exclusion, review, historical availability timestamp or forecasting row. No
vendor rows, market returns or final-period outcomes were analyzed; original
filings opened for this task end in 2021. `known_at`, `available_at` and effective
link bounds remain null, and `model_ready` remains false.
