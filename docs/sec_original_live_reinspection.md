# Direct SEC 10-K original-byte reinspection on the authorized Mac

**12 October 2026; historical identity/source approvals still pending.** This
checkpoint reopens the 16 highest-priority annual filings from the preceding
[paired-year registered-security class review](paired_stock_class_review.md),
using **the exact SEC URLs in the locked 215-filing source manifest**. Earlier
checks relied on a source-verified report from a different research workspace;
this is the first targeted reinspection of current *primary SEC HTML bytes
and SGML filing headers* directly on the user's connected Mac.

Nothing in this checkpoint requires the user's WRDS login or opens the
2022–2025 final evaluation.

## Verified live SEC retrieval

All **32** official SEC Archive URLs were retrieved with HTTP 200, from an
explicitly version-bound source manifest, with a real research contact
User-Agent and at least one second between requests. The command has no
redirections, does not retry or bypass HTTP 403 denials, caps download sizes,
and stops if an access or rate-limit error is encountered. The research
contact email is not stored in the output receipts or GitHub.

| Source-level check | Observed evidence |
| --- | ---: |
| Original shortlisted 10-K filing events | **16** |
| Direct primary HTML documents fetched | **16 / 16** |
| Original filing header SGML documents fetched | **16 / 16** |
| Header SHA-256 identical to earlier verified originals | **16 / 16** |
| Primary HTML SHA-256 identical to earlier verified originals | **0 / 16** |
| Primary HTML byte-length difference | **–4 bytes in all 16** |
| Directly reparsed *entire* original SEC lexical evidence packet identical | **16 / 16** |
| Directly reparsed selected inline-XBRL facts identical | **16 / 16** |
| Directly reparsed XBRL contexts identical | **16 / 16** |
| SEC header identity and accepted clock identical | **16 / 16 each** |
| Independently extracted current SEC HTML symbol/context/member/title/exchange | **16 / 16** |

### What the four-byte difference means

A current primary SEC document is **not byte-identical** to the earlier
original-SEC-verified version. Every current primary is four bytes shorter,
yet the returned original SGML header is byte-identical and the
entire resulting lexical SEC fact/context/diagnostic report reproduces
exactly. The reason for the uniform four-byte difference has **not been
established**; it might reflect different source versions or how bytes
were acquired. We do **not** silently append four bytes, update a historical
receipt to the new hash, assert version equivalence or infer historical
publication dates. Both distinct hashes and lengths are preserved separately
in the local source-intake evidence.

The previous original HTML copy is **not locally available for a byte-level
diff on this Mac**. This result is a current-source original reinspection and
reproducibility check, not proof that the 2020 source bytes were historically
unchanged from the 2020 dissemination date. A matching original accepted
filing clock alone likewise does not prove first public dissemination.

## Three source-bound processing stages

**1. Fetch and preserve exact present-day SEC source bytes.**
The [controlled original source-intake module](../src/disclosure_research/sec_original_revisit.py)
uses only the previously approved-to-fetch **public SEC Archive URLs**
from `reports/pilot_expansion/filing_sources.csv`, whose fixed source SHA is
`2658b7adfa03ea3c1800afd4107fa74c5348387533abde87cc30c0472b670fb1`.
The 16 accessions are taken from the earlier original class-review receipt;
each must match the original SEC issuer CIK, primary URL, header URL and
previously recorded raw-byte SHA. Requests are restricted to SEC Archive
HTTPS paths with the correct issuer CIK/accession directory. The script
writes **new private** original byte files and a receipt with both prior and
current SHA/byte counts. It doesn't fetch unexpected issuers or future years.

The retrieval record is in the gitignored directory
`outputs/sec-original-revisit-20261012-v1/`. Its raw HTML and SGML source
documents are not published as part of the repository.

**2. Reparse the full selected SEC lexical report from the current original
HTML.** The [reparser](../src/disclosure_research/sec_original_revisit_verifier.py)
reprocesses every current original primary through the previously locked
lexical SEC extractor and every current filing header through the original
header and acceptance-clock functions. It compares all previously published
selected facts, original context records, parser diagnostic counts and
header fields. The comparison reproduced all 16 full lexical reports
*exactly*. This is a **literal/HTML-parser projection check**, not SEC
XBRL schema validation or a registered-share-class approval. Its private
source fingerprints and per-document results live at
`outputs/sec-original-reparse-20261012-v1/`.

**3. Independently inspect the live original HTML DOM.**
A [separate source walker](../src/disclosure_research/sec_original_dom_crosscheck.py)
does not use the earlier `cover_evidence` projection for its fact extraction.
It parses each freshly saved source HTML directly, locates the appropriate
`dei:TradingSymbol` with original `contextRef`, and checks the
`xbrli:context` issuer CIK, period, actual
`us-gaap:StatementClassOfStockAxis` /
`us-gaap:CommonStockMember` declarations, and the **same-context**
`dei:Security12bTitle` and `dei:SecurityExchangeName` text.
All **16/16** match the previously preserved reviewed class candidate rows.
This also uses a nonvalidating HTML DOM parser; it is independent code
verification of original text/context, not full XBRL taxonomy semantics.

The three published aggregate verification reports are
[original SEC fetch comparison](../reports/sec_original_live_fetch_checkpoint.json),
[lexical original-byte reparse](../reports/sec_original_live_reparse_checkpoint.json),
and [independent current-source DOM cross-check](../reports/sec_original_dom_independent.json).

## Reproduce carefully, without public account credentials

The fetch requires a valid **contact-bearing SEC research User-Agent** supplied
in an environment variable, not in a tracked source file. The assistant
used a locally configured research identity on the authorized Mac; no SEC
login, WRDS credentials or user secrets are required.

The original fetch need not be repeated to reproduce the source checks.
Use these commands against the **existing locally preserved private source
bundle**:

```bash
uv run --locked --python 3.12 python scripts/verify_original_sec_revisit.py \
  --source-intake outputs/sec-original-revisit-20261012-v1 \
  --prior-gzip reports/sec_identity_evidence.json.gz \
  --prior-execution reports/sec_identity_evidence_execution.json \
  --output outputs/original-SEC-reparse-NEW
```

```bash
uv run --locked --python 3.12 python scripts/verify_sec_original_dom.py \
  --intake outputs/sec-original-revisit-20261012-v1 \
  --paired outputs/sec-paired-stock-20261012-final-v2 \
  --reparse outputs/original-SEC-reparse-NEW \
  --output reports/independent-original-DOM-NEW.json
```

Optional **new** SEC network fetching is separately implemented in
[`scripts/fetch_original_sec_paired.py`](../scripts/fetch_original_sec_paired.py).
It verifies the manifest, source receipt and SEC fair-access rules, requires
`SEC_USER_AGENT` with a legitimate contact email, and a fresh private output
path. Avoid unnecessary repeat downloads or invalid contact information.

Synthetic unit/integration tests never make SEC network requests; they use
invented original SEC HTML/SGML documents, a full invented 215-filing
manifest/report and a mocked retrieval function. They verify access-error
stops, contact/pacing requirements, changed primary bytes, exact original
header identity/clock matching, report hash integrity, unapproved research
flags, direct DOM source forgery rejection, and preservation of closed
2022–2025 gates.

## Research gates remain locked

Directly re-fetching and reparsing current official SEC files resolves the
**original HTML reinspection gap for the 16 shortlisted documents only**.
It cannot establish historical first-publication or website dissemination
timestamps, a continuous CIK–PERMNO effective mapping, WRDS source vintage,
event-level original market-data `available_at`, a common-stock eligibility
judgment, or human-reviewed model readiness.

The 2015–2021 sample is still the intentionally small 20-issuer SEC parser
pilot, and the measured expanding-year provisional model comparison still
**must not** be reported as validated economic forecast performance.
The frozen final evaluation remains sealed.

## Full-suite and independent-repeat verification

The [aggregate, publication-safe reproducibility receipt](../reports/sec_original_live_reproduction.json)
records a full **1,181 passing-test** local software reproduction, Ruff,
and the complete *invented-data* study pipeline. Reprocessing the **same
already-fetched original 16 SEC primary/header files** twice produced
**byte-identical** `private_reparse_per_filing.jsonl` and
`public_summary.json` files. Independently walking the raw SEC HTML
stock contexts a second time again verified all **16/16** source
TradingSymbol/common-stock-member/title/exchange relationships. Receipt
hashes naturally differ between fresh output executions. There was **no
second network download** for this reproducibility check.

The direct-current-HTML result is a meaningful improvement in original
source scrutiny but remains **retrospective 2026 retrieval of older 10-Ks**.
Neither the unexplained uniform four-byte primary difference nor the
semantic limitations of the lexical parser have been hidden or resolved.
