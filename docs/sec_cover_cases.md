# Seven original filing covers: identity and security-class evidence

Seven bounded source inspections on October 11, 2026 corroborate observations
in the saved SEC identity report. The checks reread seven original primary HTML
documents and seven SGML headers, verified their source and cache-metadata
hashes, and preserved eight filer observations. A separate process reran the
inspection and produced identical evidence apart from its execution timestamp.

The [case summary](../reports/sec_cover_cases_summary.json) gives original SEC
URLs, hashes, actual execution times, and findings. The
[complete compressed evidence](../reports/sec_cover_case_evidence.json.gz)
retains the selected lexical facts and all inherited context observations,
including entity identifiers, dimensions, periods, element ordinals and source
locations. These public filing observations contain no licensed vendor rows.

| Original filing | Observed distinction | Implication for candidate review |
|---|---|---|
| Exxon 2020 | Original CIK `0000034088`; XOM common stock and NYSE on the cover | Preserve the original registrant in unmatched discovery records. A current company header cannot replace this source identity. |
| Exxon 2021 | XOM common stock and separately listed notes have distinct symbols and contexts | Retain each security occurrence; the first observed ticker is not a general mapping rule. |
| GE 2021 | GE common stock is separate from listed notes | Match the relevant title and context, retaining the other instruments. |
| NIKE 2020 | Listed common security is specifically Class B, NKE | The title carries class information even without an explicit class dimension. |
| Comcast 2020 | Comcast Class A uses CMCSA; debt has other symbols. NBCUniversal is a separate filer with no securities in its printed Section 12(b)/(g) lines | Do not give NBCUniversal the principal registrant's equity merely because both share a filing. |
| Visa 2020 | Class A uses V on NYSE; B/C are separately described and lack an established public trading market | A generic common-stock match cannot assign the listed Class A series to another class. |
| Disney 2019 | The new registrant CIK `0001744489` identifies DIS common stock | This observation does not authorize a predecessor splice or project the new registrant backward. |

## Scope of the evidence

The independent reading aid uses Python's standard HTML parser to inspect a
bounded cover-text prefix and separate regular expressions to inspect the raw
SGML header. It imports no production extraction or identity helper. Its source
checks are reproducible with:

```bash
uv run --locked --python 3.12 python scripts/inspect_saved_cover_cases.py \
  --output outputs/cover-case-rerun.json
```

Choose a new output path. This command requires the original preserved SEC cache;
the Mac currently has the portable evidence, not that complete cache. Copying a
report to another machine does not count as rereading its original sources.

This is assistant source corroboration, not a full visual review or interpreted
XBRL validation. The complete earlier report still contains lexical cover facts
for 79 filings; only these seven receive this additional source inspection. A
context's entity CIK can coexist with a dimension identifying another legal
entity, as in the Comcast co-filing. Context periods are not security-link
validity intervals. Parsed text, namespace/format warnings, and original document
observations remain distinguishable.

The cases support the next comparison with existing dated Names/CCM candidates.
They do not supply a PERMNO link, a continuous historical interval, January 1
knowledge, vendor-release evidence, or an approved share-class decision.
`known_at` and supported link bounds remain null. Source approvals, newly created
human reviews and historical security links remain zero; the final period stays
closed.
