# Corporate-identity source evidence

Checked on 10 October 2026. These checks supplement the existing
[identity review packet](identity_review.md); its source tables, flags and pending
verdicts remain unchanged. Public SEC sources are cached separately in
`data/raw/identity_source_cache`. The [source receipt](../reports/identity_source_receipts.json)
records their URLs, retrieval times and byte hashes.

## Exxon: the two CIKs have a documented corporate explanation

Exxon's [1 July 2026 POSASR](https://www.sec.gov/Archives/edgar/data/34088/000119312526292453/d54886dposasr.htm)
describes a holding-company reorganization effective that day. The existing
New Jersey corporation became a subsidiary of the Texas parent, which succeeded
to the common-stock registration. The
[SEC index](https://www.sec.gov/Archives/edgar/data/34088/000119312526292453/0001193125-26-292453-index.htm)
identifies both registrants. The
[NYSE notice filed with the SEC](https://www.sec.gov/Archives/edgar/data/34088/000087666126000593/ruleprovisionnotice.htm)
also distinguishes their common-stock CUSIPs:

| Identity | SEC CIK | Common-stock CUSIP |
|---|---|---|
| Original Exxon Mobil Corporation | `0000034088` | `30231G102` |
| ExxonMobil Holdings Corporation | `0002115436` | `30233Q108` |

The older pilot filings use the original CIK. The received CCM supplement carries
the parent's CIK, name and CUSIP. **Inference:** a current corporate header is
consistent with the observed mismatch; a historical CCM link interval does not
make that header a historical CIK observation. This evidence explains the two
identities but does not independently certify the vendor's update process or
approve the original CIK-to-PERMNO link.

Keep original filing CIKs, the separate discovery CIK and the seven flagged events.
The 2026 documents are retrospective identity evidence only. They are excluded
from research text, features, labels and any point-in-time availability claim.
No final-period filing event or return is evaluated by this check.

## GE: a development-period identifier change in the existing export

GE's [30 July 2021 8-K, Item 3.03](https://www.sec.gov/Archives/edgar/data/40545/000120677421001925/ge3936671-8k.htm)
reports a one-for-eight reverse split and split-adjusted NYSE trading from
**2 August 2021**, under unchanged ticker GE and new CUSIP **369604301**.
The supplied dated Names records change from eight-character CUSIP `36960410`
to `36960430` on that date. Their intervals are contiguous, and the same PERMNO
and PERMCO remain present on both sides.

The [reproducible case check](../scripts/verify_ge_identifier_case.py) inspects
**26 July through 6 August 2021**, selected around the identifier change rather
than model performance. It verifies all ten expected exchange sessions, one
dated Names match per session, unchanged staged daily-return values and source-row
references, and the staged snapshot's dated SIC and interval. The current daily
header CUSIP differs from the dated CUSIP on five pre-change sessions. This is
direct evidence that a header identifier cannot replace the dated record.

The [aggregate result](../reports/ge_identifier_check.json) records checks and input
hashes without distributing vendor rows. With the private pilot exports and staged
Parquet files present, reproduce it from the repository root:

```bash
uv run --locked python scripts/verify_ge_identifier_case.py
```

This passes automated identifier/staging QA only. The ten-column daily pilot
lacks prices and distribution factors, so the check does not independently
recompute split-adjusted returns. It neither approves historical CIK links nor
counts as an independent human review or terminal-payoff check.

## CCM open end markers: interpretation supported, bounds still pending

The official [WRDS CIZ industry-ratios macro](https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/wrds-macro-indratios-ciz/),
updated in November 2024, permits a CCM observation when its date is before
`LINKENDDT` **or** that end marker is `.E`. This supports an open-ended candidate
interpretation. It does not establish the received CSV's exact dictionary version,
extract date, release vintage or a certified normalization bound.

Preserve the literal CSV `E` values and pending approvals. Do not substitute today's
date, infer a source vintage from the 2026 corporate event, or silently inherit
the macro's other link/class filters. The original WFM submitted parameters are
now documented, and the PERMNO follow-up passes the
[automated terminal check](wrds_delisting_check.md). The pilot's exact release/query
metadata, point-in-time availability and historical identity approvals remain pending.
