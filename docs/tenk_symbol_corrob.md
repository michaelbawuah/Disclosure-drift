# Original SEC 10-K TradingSymbol / dated CRSP Names corroboration

**11 October 2026 — original-source lexical evidence only. No historical
issuer crosswalk or economic finding approved.**

The previously verified original SEC 215-filing lexical evidence packet
contains parsed cover-page `dei:TradingSymbol` fact occurrences. We matched
their **unaltered parsed-text literals** against complete dated CRSP Names
security descriptors at each original 10-K acceptance date in the fixed
20-issuer 2015–2021 pilot. The source report itself explicitly declares
`xbrl_fact_values_interpreted=false`. No full XBRL processor verified
the context hierarchy, stock class or issuer/company security mapping.

## Observed development-only results

| Observation | Filings |
| --- | ---: |
| Fixed source-bound original SEC/market pilot event records examined | **135** |
| 10-Ks containing one or more original `TradingSymbol` lexical facts | **43** |
| With at least one exact-symbol, globally unique same-day Names record matching the provisional permanent security | **43** |
| With a single distinct symbol, no lexical issues, no hidden fact, and a unique dated Names candidate | **17** |
| Multiple distinct reported symbols requiring share-class/context review | **21** |
| One or more lexical issues | **3** |
| One or more symbols in hidden HTML/style context | **5** |
| No supported `TradingSymbol` lexical facts | **92** |

The 43 symbol-bearing filings occur in **2018 (1), 2019 (2), 2020
(20), and 2021 (20)**. The multiple-symbol, lexical-issue, and hidden-fact
categories can overlap; don't add them as independent totals. A matched
symbol can belong to a different stock class or context, particularly if
another distinct symbol is present, so **even the 17 clean-single-symbol
candidates are not automatically accepted identities**.

For each symbol, the audit scans the full **191,048 original CRSP Names
records**, enforces an exact literal match to `ticker` or
`tradingsymbol`, tests every same-day global symbol candidate for a
unique descriptor, requires the selected PERMNO's simultaneous Names
descriptor to be unique, and checks the security lifetime. No modern ticker
substitution, symbol fuzzy matching, current-header CIK replacement or
look-ahead normalization occurs.

The [offline implementation](../src/disclosure_research/tenk_symbol_corrob.py),
[CLI](../scripts/audit_tenk_symbol_corrob.py), and
[synthetic adversarial tests](../tests/test_tenk_symbol_corrob.py)
verify the saved original SEC report, original M5 market candidate
receipt, complete CRSP Names export and corresponding inventory hashes.
The source-verified report covers earlier original 10-K HTML/SGML byte
checks, but this run **does not reread those original filing bodies**.
Per-filing source values, contexts, CIK and PERMNO remain local in ignored
private files; only the [aggregate checkpoint](../reports/tenk_symbol_corrob_checkpoint.json)
is published.

## Reproduce from authorized local evidence

```bash
uv run --locked --python 3.12 python scripts/audit_tenk_symbol_corrob.py \
  --market-candidates data/reviews/market-pilot-m5-v1 \
  --sec-report-gzip reports/sec_identity_evidence.json.gz \
  --sec-execution reports/sec_identity_evidence_execution.json \
  --names-csv data/private/wrds-intake/names-v2/source.csv \
  --names-inventory data/private/wrds-intake/names-v2/receipt.json \
  --names-sha256 74195ec05a8b392fcef880750aa73e6f7860f927b042e404c0f9a8c28d1858a9 \
  --output outputs/tenk-symbol-corroboration-NEW
```

Use a fresh private output path. The original full Names CSV stays
on the user's authorized Mac. Test fixtures invent company records
and source reports and cannot be mistaken for a real source approval.
No new WRDS authorization, SEC fetch or holdout access is required.

This corroboration supports additional specific 10-K filing dates but
cannot provide the missing continuous 2015–2021 CIK–PERMNO link, valid
share class, source-known date, CRSP release vintage, market availability,
original SEC public dissemination time or selected historical investable
universe. All historical source/identity approvals remain zero; the
conditional exploratory forecasts remain unapproved and the frozen
2022–2025 final evaluation stays closed.

## Verification receipt

The [aggregate reproducibility record](../reports/tenk_symbol_corrob_reproduction.json)
binds **1,086 passing tests**, Ruff, the entire synthetic study pipeline, and
two fresh-directory real-data executions with **byte-identical** public
summaries and private per-filing lexical/context rows. Their run-specific
receipts are not claimed identical. The original sources remain locally
unchanged and their SHA-256 checks succeeded.

The additional matching evidence is useful for the 2018–2021 filing-date
review queue. It is not sufficient to sign off Milestones 5–11 or to claim a
new predictive result in a resume.
