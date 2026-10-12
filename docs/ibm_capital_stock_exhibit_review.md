# IBM capital stock — source-backed original SEC Exhibit 4.1 review

**12 October 2026.** Original public SEC exhibits clarify the two
`Capital stock, par value $.20 per share` descriptions in the preceding
[16-filing SEC stock-class review](paired_stock_class_review.md). The study
remains **historical-identity and known-at unapproved**, and the frozen
2022–2025 final evaluation remains unopened.

## Findings from two official original filings

| Original IBM SEC evidence | 2019 year-end | 2020 year-end |
| --- | --- | --- |
| SEC original 10-K accession | `0001558370-20-001334` | `0001558370-21-001489` |
| Filing acceptance date | February 25, 2020 | February 23, 2021 |
| Official registered-securities source | [EX-4.1 (2020 filing)](https://www.sec.gov/Archives/edgar/data/51143/000155837020001334/ex-4d1.htm) | [EX-4.1 (2021 filing)](https://www.sec.gov/Archives/edgar/data/51143/000155837021001489/ibm-20201231xex4d1.htm) |
| Registered share class wording | Capital stock, $0.20 par value | Capital stock, $0.20 par value |
| No other issued/outstanding equity class, explicitly stated | **Yes** | **Yes** |
| One vote per share, dividends, residual liquidation rights | **Yes** | **Yes** |
| Public stock symbol and listing | IBM; NYSE / Chicago Stock Exchange | IBM; NYSE / Chicago Stock Exchange |
| Reported year-end outstanding capital stock shares | 887,110,454 | 892,953,271 |
| Historical CIK–PERMNO mapping, known-at and eligible common-stock judgment | **Not approved** | **Not approved** |

This establishes that IBM's original *Capital stock* label represents its
registered **issued/outstanding equity class**, with ordinary voting and
residual shareholder rights. The exhibits explicitly separate equity from
registered notes and debentures. Thus the two “Capital stock” labels are
no longer **unexplained lexical ambiguities**. The original 10-K
`us-gaap:CommonStockMember` context is separately corroborative.
None of this automatically equates issuer equity with an approved CRSP
share class or establishes that a modern security-mapping table was
historically available on the relevant dates.

## Audited evidence and immutable source pin

The six manually retrieved current SEC files—two original EX-4.1
HTML documents, two SEC filing-index HTML documents, and two SEC
directory-index JSON files—remain in ignored
`outputs/ibm-exhibit-discovery-20261012/` on the authorized Mac.
The checked-in [source pin](../configs/ibm_capital_stock_exhibit_source_pin.json)
records the **exact official SEC Archive URL, current raw SHA-256 and byte
length** for each of the six sources, plus original accession, report
year and SEC acceptance clock. It expressly claims **no historical
first-publication date, CIK/security known-at or research approval**.

The [first audit](../src/disclosure_research/ibm_capital_stock_exhibits.py)
requires each input to match that public source pin; identifies the exact
`EX-4.1` in the official filing document index and directory listing;
binds the original filing acceptance clock to the earlier original-SEC-verified
10-K report; and isolates the capital-stock section *before* the separate
debt section. It checks the exact original issuer, par value, authorized
and outstanding share counts, single issued equity class, voting, dividends,
liquidation rights and IBM's stock listing.

An [independent verifier](../src/disclosure_research/ibm_capital_stock_exhibits_verifier.py)
uses Python's standard `HTMLParser`, not the first audit's `lxml`
parser. It independently extracts the two equity sections, recomputes the
original share counts and normalized source-text digests, and verifies all
six raw source hashes against the pinned SEC objects. The
[aggregate audit](../reports/ibm_capital_stock_exhibit_checkpoint.json)
and [independent verification](../reports/ibm_capital_stock_exhibit_independent.json)
exclude licensed CRSP event-level identifiers.

**Source-version caveat:** Both current SEC directory JSON indexes
advertise exhibit file sizes **111 bytes smaller** than the current
downloaded exhibit bytes. The cause is undetermined; we preserve both
values without equating them. Similarly, SEC acceptance timestamps,
current directory `last-modified` values and present-day copies of original
filings are not themselves proof of the original byte-version dissemination
date. We do not infer historical `known_at` from those metadata.

## Reproduce offline

Using the already downloaded source files and a **fresh private output**:

```bash
uv run --locked --python 3.12 python scripts/audit_ibm_capital_stock_exhibits.py \
  --source-pin configs/ibm_capital_stock_exhibit_source_pin.json \
  --source-files outputs/ibm-exhibit-discovery-20261012 \
  --prior-pairs outputs/sec-paired-stock-20261012-final-v2 \
  --original-sec-gzip reports/sec_identity_evidence.json.gz \
  --output outputs/ibm-capital-stock-NEW
```

```bash
uv run --locked --python 3.12 python scripts/verify_ibm_capital_stock_exhibits.py \
  --source-pin configs/ibm_capital_stock_exhibit_source_pin.json \
  --source-files outputs/ibm-exhibit-discovery-20261012 \
  --audit outputs/ibm-capital-stock-NEW \
  --output reports/independent-ibm-NEW.json
```

Synthetic-only tests guard source hashes, wrong SEC filing clocks, forged
approval, altered equity/voting/NYSE/ticker claims, missing exhibit-index
entries, fabricated share counts, and changed source bytes. No licensed
original rows or original SEC document bytes are published to GitHub.

The next substantive decisions remain **human class/issuer eligibility
review**, effective-dated CIK–PERMNO/GVKEY mapping with historical
availability, a predeclared development universe, vendor-market
`available_at`, source benchmark selection and legitimate empirical
model evaluation. These two exhibits are not proof of the full protocol.

## Final independent repeat-run evidence

The [public reproducibility receipt](../reports/ibm_capital_stock_exhibit_reproduction.json)
binds **1,200 passing tests**, Ruff, and the complete invented-data study
software pipeline. The source-pinned IBM original SEC audit was rerun twice
against the same six preserved bytes without additional network requests.
`private_exhibit_review.jsonl` and `public_summary.json` were
**byte-identical**; the separate standard-library HTMLParser verifier
reconstructed both equity sections, source rights, share counts and SEC
exhibit links on each run. Individual receipt hashes differ because they
represent distinct executions. Deterministic source analysis remains
distinct from historical data-version approval or an empirical forecast.
