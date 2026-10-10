# Development-period delisting check

The 20-security daily pilot has no delisting rows. Obtain one small separate QA
export to test the terminal payoff and prevent double-counting a legacy DLRET.
This security is a data-handling example, not an addition to the research sample.

## Requested export

- WRDS: CRSP / Annual Update / Stock - Version 2 (CIZ) / Daily Stock File.
- Dates: **2017-08-14 through 2017-09-08**, inclusive.
- Identifier type: **Ticker**; enter **WFM** (Whole Foods Market, Inc.).
- Keep the pilot's ten fields: `PERMNO`, `HdrCUSIP`, `Ticker`, `PERMCO`,
  `DlyCalDt`, `DlyDelFlg`, `DlyCap`, `DlyRet`, `DlyRetMissFlg`, `vwretd`.
- Add **`DlyPrc`, `DlyPrevPrc`, `DlyPrcFlg`** for terminal-price arithmetic.
- CSV, uncompressed, YYYY-MM-DD. Save as **`crsp_delisting_check.csv`**.
- Preserve vendor SQL if offered and the query result metadata when available.

If the ticker lookup asks for a company, select Whole Foods Market, Inc.; its
historical CUSIP is 966837106 (eight-character CRSP form: 96683710). Do not guess a
PERMNO. Verify the returned permanent ID and security metadata before testing.

## External event evidence and planned checks

[Nasdaq's corporate-action notice](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2017-10)
records an effective merger on 28 August 2017, trading suspension effective
29 August 2017 and cash consideration of USD 42.00 per share. This establishes
the reason for selecting this window; the actual CRSP terminal row/date must be
read from the export rather than assumed from the public notice.

[WRDS's CIZ transition webinar](https://wrds-www.wharton.upenn.edu/documents/2084/Webinar.pdf),
slide 14, shows that daily CIZ time series contain separate flagged delisting-return
rows. Its worked example uses `DlyDelFlg`, `DlyPrc`, `DlyPrcFlg` and `DlyRet`.
The CRSP [format-2.0 guide](https://www.crsp.org/crsp_pdf/crsp-us-stock-indexes-databases-guide-flat-file-format-2-0/)
defines `DlyPrevPrc` as the prior price used in the return calculation.

After receipt, verify security identity, actual flag codes, terminal-row timing,
prior price and cash proceeds; reconcile the vendor return to independently
calculated arithmetic within the delivered precision. Test the normalized terminal
flag and flat cash proceeds after termination without re-adding legacy DLRET.
Keep null capitalization or missing return codes explicit; never fill them with
zero. If the expected terminal evidence is absent, report the gap rather than
marking the check complete. Source normalization and independent human review
remain separate requirements.

Public sources were checked on 10 October 2026. No WFM export has been received yet.
