# Development-period delisting check

Status on 10 October 2026: **the automated WFM terminal-return case passes**.
The PERMNO export recovered the terminal observation missing from the original
ticker export. Both files remain unchanged in the private archive. This is a
data-handling example, not an addition to the research sample or a human review.

## Original request and observed query

The request used WRDS CRSP / Annual Update / Stock - Version 2 (CIZ) / Daily Stock
File, dates **2017-08-14 through 2017-09-08**, ticker **WFM**, and these 13 fields:
`PERMNO`, `HdrCUSIP`, `Ticker`, `PERMCO`, `DlyCalDt`, `DlyDelFlg`, `DlyPrc`,
`DlyPrcFlg`, `DlyCap`, `DlyPrevPrc`, `DlyRet`, `DlyRetMissFlg`, `vwretd`.

The supplied result-page screenshots confirm query **11769187**, product
`crsp_a_stock`, Success, ten rows and the requested dates. Expanded parameters show
`file=wrds_dsfv2_query`, `qvar=ticker`, `query=WFM`, `datevar=dlycaldt`,
`library=crspa`, `format=csv`, `datef=YYMMDD10.` and `wrdsVersion=3`. The displayed
submission time is `2026-10-10 00:57`; its timezone is not shown. The variable list
is collapsed at 13 entries; field names are verified from the CSV separately.
No vendor SQL is available. These parameters do not by themselves certify a
fully qualified SQL namespace or exact CRSP release.

The original `crsp_delisting_check.csv` has **ten ordinary rows**, 14-25 August
2017, PERMNO **77281**, PERMCO **11310** and historical CUSIP **96683710**. Its
delisting flags are all N. It remains a negative control: the label engine rejects
the missing 28 August return instead of inventing a payoff.

## PERMNO follow-up and primary evidence

`crsp_delisting_check_permno.csv` has **11 rows and 13 columns**. All ten original
records match exactly. The added row is dated **28 August 2017**, with the same
permanent identifiers, `DlyDelFlg=Y`, a blank ticker, `DlyPrcFlg=DA`, zero `DlyPrc`
and missing capitalization. Both CSVs match their original Mac downloads.

The blank terminal ticker is consistent with the original ticker request missing
that row. The export comparison establishes the retrieval difference; the actual
SQL predicate is not available. The follow-up query ID, submitted parameters and
exact vendor release remain unverified. Use the observed permanent ID for future
retrievals of this security rather than relying on its ticker.

- Whole Foods' [SEC 8-K, Item 2.01](https://www.sec.gov/Archives/edgar/data/865436/000114420417045261/v474128_8k.htm)
  records completion of the merger on 28 August 2017 and USD 42.00 cash per eligible
  share. Item 3.01 describes a requested trading suspension before that day's open.
- CRSP's [price-flag dictionary](https://www.crsp.org/wp-content/uploads/appendix/FlagType_PC.html)
  defines DA as a delisting amount with no delisting price. The zero price is
  therefore not interpreted as a zero cash payoff or a minus-100% return.
- CRSP's [convention dictionary](https://www.crsp.org/wp-content/uploads/appendix/FlagType_MU.html)
  describes daily delisting fields on the next trading day after the delisting
  date, which need not be the payment date. The observed terminal session is used;
  no settlement/payment date is inferred from it.

These primary pages are cached privately with URL, retrieval time and byte hashes
in the [source receipt](../reports/market_access_samples.json). The earlier
[Nasdaq notice](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2017-10) selected
the example; the SEC filing and delivered observation support the completed check.

## Completed automated checks

The externally documented cash consideration divided by the delivered prior price,
minus one, matches DlyRet within its six-decimal rounding tolerance of 0.0000005.
All ten ordinary price-change calculations meet that tolerance too. The external
cash amount is only an independent comparator; it never replaces a source return.

The normalizer preserves all 11 DlyRet values unchanged, retains the terminal flag
and keeps missing capitalization invalid for size controls. It neither uses the
zero price to calculate a return nor adds a legacy DLRET. Stock coverage has no
missing sessions through the observed terminal event. All 11 benchmark rows match
the existing daily pilot; later benchmark sessions come from that same pilot,
without forward filling. The WFM-only export lacks those eight remaining benchmark
sessions in the original request window, as expected after termination.

Two artificial QA clocks exercise the frozen 20-session label horizon. One spans
ordinary returns plus the terminal return and ten subsequent cash sessions; the
other starts with the terminal return and has 19 cash sessions. Stock, benchmark
and excess-return arithmetic agree with independent Decimal products to 1e-12.
Both reject the original incomplete file. These clocks are not real SEC events.

Reproduce from the repository root with the three private input CSVs present:

```bash
uv run --locked python scripts/verify_wfm_terminal_case.py
```

The command pins input and protocol hashes and refuses to overwrite an existing
`data/reviews/wfm-terminal-v1` run; use `--output` with a new directory to repeat it.
Detailed arithmetic stays private. The [public aggregate result](../reports/wfm_terminal_check.json)
contains counts, checks and hashes only. An invented-data regression test covers
the blank-ticker, zero-DA-price and missing-capitalization combination.

No further WFM CSV is needed for this automated case. Historical CIK approvals,
exact release/query metadata, point-in-time availability and independent human
filing/label reviews remain separate Milestone 05 requirements. No real filing
labels, fitted models or final-period outcomes were produced.
