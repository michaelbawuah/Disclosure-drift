# Recorded review progress: original pilot evidence

## The user's completed numerical review is now recorded

The researcher previously supplied an explicit verdict: **20 of 20 fixed traces
passed an independent arithmetic and packet-structure re-check**. That statement
is a completed user review. It is not merely a script submission, and the user
does not need to repeat it.

The recovered follow-up archive contains the original HTML packet, the submitted
`pilot-recheck.py`, its saved results, the earlier pending draft, and the exact
20 event/evidence identifiers. These match the unchanged private source packet.
The script was run unchanged again: every returned result matches the saved
result, with maximum absolute difference **1.27675647831893e-15**. The statement
and each event-specific pass are recorded in the private
`data/reviews/user-arithmetic-recorded-v2` directory; public hashes and counts are
in [user_arithmetic_receipt.json](../reports/review_progress/user_arithmetic_receipt.json).

The original message's precise timestamp was not recovered. Its review time
therefore remains `null`, with `original_review_time_unknown: true`. A separate
`recorded_at` describes when the assistant recorded the existing user verdict.
No earlier timestamp or new human action is invented.

| Review component | Established status |
|---|---|
| Stock/benchmark compounding, target difference, momentum, sample volatility and log capitalization | User pass on all 20 fixed traces |
| The printed 60-control/20-label structure, dates, excluded reference row and snapshot position | User pass on all 20 fixed traces |
| Reproduction of the submitted script against the exact old packet | Assistant rerun matches the saved output on all 20 |
| A return changed by 0.0001 in the first trace | Assistant rerun catches the changed trace, reproducing the user's reported mutation test |
| Matching the packet's quoted rows to original CSV bytes | The separately recorded assistant source-row reconciliation covers all 2,040 references |
| Historical security identity, share-class choice, vendor release/availability and filing boundaries | Not judgments supplied in the user's numerical-review statement |

The mutation receipt is [mutation_check.json](../reports/review_progress/mutation_check.json).
The original script exits successfully even when it prints failed checks, so the
reproduction inspected the returned `issues` fields. It did not treat process
exit status as a passed review. The original script and draft were preserved.

The earlier draft and M5 receipts remain historical records. Their pending fields
must not be read as saying the user never completed the numerical check. The new
record uses explicit arithmetic/packet-structure verdicts: it does not silently
insert a broader full-source trace approval into the legacy importer, or attribute
the assistant's original-CSV inspection to the user.

## Additional assistant source inspection

The source investigation retains the fixed 30-pair sample: **58 distinct
filings**. It also includes all **14 registered reference resolutions**. Nine
filings overlap those groups, giving **63 distinct inspected filings**.

For the ordinary cases, the inspected textual boundaries start at substantive
Item 1A Risk Factors and end before Item 1B Unresolved Staff Comments. GE's
same-document ranges end before Legal Proceedings. Intel's ranges end before
Non-GAAP Financial Measures or Properties. Johnson & Johnson's original Item 1A
directs readers to Exhibit 99; the inspected exhibit belongs to the same accession.
Every stored risk section is checked against the exact inspected span of its
hash-bound original source. Existing page-navigation and footer text remains
visible under the unchanged normalizer; boundary inspection is not a claim of
complete visual inspection or perfect text normalization.

All **155 original SGML acceptance clocks** were independently derived without
the project's event-clock helper. The stored reference, control-end and label-end
sessions agree. There are 83 equal API/header timestamps, 49 differences of five
hours and 23 differences of four hours. Each nonzero difference equals the
corresponding New York/UTC offset. This describes the discrepancy; it does not
establish the API's cause or prove when the filing was publicly disseminated.
The original SGML header remains the study's clock.

The source scan also checks explicit “Item 1A Risk Factors (Continued)” headings
in every original pilot source. No such case occurs among the original 155
filings. This finding does not establish that newly collected issuers are free
of repeated-heading parser problems.

The [source review receipt](../reports/review_progress/source_review_receipt.json)
binds the original tables, source audit, fixed selection, recorded decisions and
generated checks. All new filing inspections are explicitly assistant-authored.
They add useful source evidence and leave the existing independent-human gates
unchanged. No market return was used to choose these cases, and no final-period
event or outcome was examined.

## Supplied Names query recovered

The user's original [Names SQL](source_queries/crsp_names_pilot.sql) is now
preserved unchanged. It selects 24 fields from
`crsp_a_stock.wrds_names_query` for the 20 pilot PERMNOs, without a date restriction.
The field order and selected security set match the supplied 237-row Names CSV.
The [query receipt](../reports/review_progress/names_query_receipt.json) records
the query hash and the existing CSV hash.

This resolves the missing **Names query text**. It does not establish that the
query was actually executed as supplied, its vendor release vintage or the
point-in-time availability of retrospective metadata. The daily-return and CCM
export queries/release metadata remain separate needs. Literal CCM `E` link-end
values and the historical Exxon CIK discrepancy remain visible; these have not
been converted into approved mappings.

## Source-specific expansion and identity checks

Five new expansion filings received separate assistant scope inspection against
their original SEC bytes. The [five-case scope receipt](../reports/review_progress/expansion_scope_review_v2.json)
records exact normalized offsets, source and text hashes, and the scope chosen:

| Source case | Inspected scope and limitation |
|---|---|
| Mastercard 2020 and 2021 filings | Risk Highlights and all following risk pages through the true Item 1B heading; unmarked running Item 1A headings remain inside the section |
| McDonald's 2020 and 2021 filings | The continuous labeled Risk Factors block through Legal Proceedings; the separately cross-referenced general cautionary statement on page 3 is excluded explicitly |
| Honeywell 2021 filing | The substantive Risk Factors block pointed to by page 24 of the Item 1A index, through its last paragraph on page 32 and before Quantitative and Qualitative Disclosures About Market Risks |

These are source-specific extraction judgments. In particular, the McDonald's
comparison covers the labeled risk block and does not claim to include every
piece of material cross-referenced under Item 1A. The earlier four-case receipt
remains a historical record. Neither receipt adds a human review.

The [Exxon registration receipt](../reports/review_progress/exxon_registration_review.json)
adds direct supporting evidence for the seven flagged 2015–2021 filings. Each
original cover registers common stock without par value on the New York Stock
Exchange. At each prior-close date, the supplied Names file has one consistent
Exxon Mobil common-equity description for the candidate PERMNO and PERMCO.
This corroborates the candidate's description; it does not establish a historical
CIK-to-security link or its release vintage. The current vendor-header CIK
discrepancy, literal `E` end marker and unapproved mapping remain explicit.

## Reproduce the evidence recording

The recorder never executes a submitted program. With the original private
archive, packet and recorded user statement available, use a new output directory:

```bash
uv run --locked python scripts/record_review_progress.py user-arithmetic \
  --archive /path/to/Disclosure-Drift-M5-Review-Followup.zip \
  --packet data/reviews/market-pilot-m5-v1 \
  --statement data/reviews/user_arithmetic_statement_v1.json \
  --reproduced-results outputs/user-recheck-reproduction-20261010/results.json \
  --output data/reviews/user-arithmetic-reproduction

uv run --locked python scripts/record_review_progress.py assistant-sources \
  --reviews reports/review_progress/assistant_filing_decisions.jsonl \
  --output outputs/assistant-source-review-reproduction

uv run --locked python scripts/verify_expansion_scope_review.py \
  --output outputs/expansion-scope-reproduction.json

uv run --locked python scripts/verify_xom_registration_case.py \
  --output outputs/exxon-registration-reproduction.json
```

The second command verifies recorded assistant decisions against original sources;
it does not create an independent person's review. Prior output directories are
never overwritten. Private arithmetic packets and licensed source rows stay out
of public Git.

## What still needs external evidence or another person's judgment

The researcher's authorization permits assistant investigation and honest
assistant-authored review records. The primary protocol requires audited
provenance, timing, links, labels and extraction, and manual semantic validation.
Its completion section also requires that another person can rebuild permitted
public examples. Existing trace, dataset and freeze contracts separately enforce
human-authored reviews for particular gates; authorization to work is not a
substitute for those scientific judgments, and none of these contracts was changed.

Remaining evidence includes full historical source exports, exact vendor
release/query metadata, supported historical link intervals and share-class
resolution, and the specifically required independent source/filing reviews.
The user has already completed the 20-case numerical and printed-timing check.
