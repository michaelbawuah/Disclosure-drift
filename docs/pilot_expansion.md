# Expanded 2019–2021 SEC text pilot

The initial pilot has 59 annual pairs accepted in 2019–2021. The expansion
configuration selects 15 additional issuers before reading their new filing
text or any market outcomes. It requests original annual filings accepted in
2018–2021 so that each 2019 observation can have its immediate annual predecessor.
All failures and exclusions are retained. This is a purposive document-format
sample; historical investment-universe selection remains a separate task.

The completed combined checkpoint has **215 filings, 180 pairs and 35 issuers**.
Its **104 pairs accepted in 2019–2021** meet the planned count criterion. All 215
automated source checks pass; see the [actual checkpoint](../reports/pilot_expansion/pilot_checkpoint.json).

The companies are Adobe, Comcast, Tesla, Ford, Visa, Mastercard, McDonald's,
Nike, Costco, AbbVie, Amgen, Goldman Sachs, Honeywell, Chevron and AT&T. Their
CIKs are sourced from the recorded SEC discovery file. Current ticker discovery
does not establish historical eligibility or a market-data identity link.

## Reproduce collection and the combined checkpoint

Run from the repository root with the original pilot source cache restored:

```bash
export SEC_USER_AGENT='DisclosureDriftResearch https://github.com/michaelbawuah/Disclosure-drift'
uv run --locked disclosure ingest \
  --companies configs/pilot_expansion_2019_2021.json \
  --resolutions configs/pilot_expansion_resolutions.json \
  --output data/processed/pilot-expansion-2019-2021-resolved

uv run --locked python scripts/build_pilot_expansion.py \
  --sources data/processed/pilot-resolved data/processed/pilot-expansion-2019-2021-resolved \
  --output outputs/pilot-expanded-checkpoint
```

The collector uses the existing conservative SEC request rate and checks cached
source hashes. The combination command reads only source dates before accepting
development files, rejects overlapping accessions, and verifies that every
original pair's identity, text, dates and extraction provenance survive unchanged.
It recomputes pairs from consecutive original annual reports and runs a fresh
offline source audit before producing descriptive features. A failed source
audit is saved for investigation and cannot produce a successful checkpoint.
Use a new combined output directory on subsequent runs.

The original 155-filing source table, 135-pair table, market arithmetic packet,
and their recorded reviews are preserved. No return table is loaded by these
commands. Successful text extraction does not approve historical security links,
vendor vintages, filing judgments, or the controls-only market-data pilot.

## Layout problems found in the new sample

### Ford: explicit continuation headings

Ford repeats `Item 1A. Risk Factors (Continued)` on successive pages. The old
candidate selection treated each repeated heading as a new section and retained
only the last page. The parser now recognizes explicit continuation headings as
part of the existing section, through its substantive Item 1B/2 boundary.

This path records `item1a-v2-continued-headings`. The HTML normalizer remains
unchanged, and sources without these markers keep their existing extraction
version and output. A fresh comparison against all 155 original sources found
no changed extracted text, token counts, status or parser version. Tests include
multiple continued pages, an isolated continuation without an opening section,
and an ordinary paragraph whose first word is “Continued.”

### Mastercard: unmarked running headers

The 2020 and 2021 filings repeat an unmarked `ITEM 1A. RISK FACTORS` running
header on each page. The generic parser flags its short, incomplete result.
Two source-specific rules select the actual opening before `RISK HIGHLIGHTS`
and include the whole continuous risk discussion up to the substantive Item 1B.
The rule validator requires a numbered opening, repeated headings inside the
range, and the first real Item 1B/2 boundary. It refuses ranges that cross an
intervening Item 1B/2. Unknown layouts remain unresolved.

### McDonald's: an annual-report cross-reference

The 2020 and 2021 filings place a labeled `RISK FACTORS` block in the annual
report and an Item 1A cross-reference in the form index. The index also points
to a separate, general forward-looking-statement caution on page 3.

The recorded scope selects the **labeled Risk Factors block**, ending before
`LEGAL PROCEEDINGS`. It excludes the separately located, general cautionary
statement and does not claim to concatenate every page referenced by Item 1A.
This scope is visible in the rule notes and assistant source review so that the
remaining human filing review can assess it. No intervening business or MD&A
content is included merely to bridge the distant cross-references.

### Honeywell: a single-page index pointer

The 2021 filing's numbered Item 1A entry is a cross-reference index pointing to
page 24. The substantive `RISK FACTORS` section begins there and continues through
page 32. A fifth rule selects that complete section and ends immediately before
`QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISKS`. The validator
requires a numeric single-page Item 1A pointer and exact standalone section
boundaries. The unrelated contents and form index are excluded.

## Source evidence and research limits

[The expansion rules](../configs/pilot_expansion_resolutions.json) preserve all
14 earlier reference rules exactly and add five explicit layout cases. Each new
rule binds the original SEC URL, source hash, initial flagged extraction,
normalized offsets, resulting text hash and token count. These are reproducible
extraction instructions with assistant source inspection; they are not human
research sign-off.

The combined checkpoint reports actual filings, issuers, annual pairs, exclusions
and 2019–2021 coverage. Its length, Jaccard and TF-IDF distributions describe
the text. TF-IDF uses strictly earlier acceptance years. A sufficiently large
text pilot still needs reviewed market inputs before the fixed controls-only
smoke test can run.
