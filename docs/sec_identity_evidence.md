# Original SEC filer and lexical cover evidence

This offline reader adds original-source corroboration to the preserved SEC
pilot manifest. It verifies the primary filing and SGML header bytes, checks the
original filer and acceptance clock, and retains contextual cover facts as
**lexical evidence**. It creates no CIK-to-security link, share-class selection,
historical availability timestamp, source approval, or human review.

The existing [filing audit](filing_audit.md) already checks source integrity,
risk-section extraction, acceptance interpretation, and calendar timing. This
reader does not rerun those extraction or review workflows. Its useful addition
is complete SGML co-filer evidence and the unflattened cover-fact/context
observations needed for later identity corroboration.

## Run where the original SEC cache exists

From the repository root:

```bash
uv run --locked --python 3.12 python scripts/verify_sec_identity_evidence.py \
  --manifest reports/pilot_expansion/filing_sources.csv \
  --manifest-sha256 2658b7adfa03ea3c1800afd4107fa74c5348387533abde87cc30c0472b670fb1 \
  --cache data/raw/sec_cache \
  --output reports/sec_identity_evidence.json
```

The manifest hash is mandatory. The output must be a new `.json` file; an
existing report is never overwritten. `--protocol` defaults to
`configs/protocol.json`, and the frozen lock must verify. This command performs
no network request. If a cached source is missing or differs from its declared
hash, it fails rather than fetching a replacement.

The Python API `build_sec_identity_evidence(...)` returns the complete report
without writing it. `write_report(...)` writes deterministic JSON atomically,
with read-only permissions. The report includes source URLs/hashes and selected
public evidence, but no complete filing bodies, local cache paths, execution
timestamp, or licensed market data. The CLI prints only a compact summary and
the written report's hash/size. Parser-library versions and the extractor's
source-code hash are recorded because recovered-tree serialization can depend
on the implementation.

## Original-source checks

The exact supported `filing_sources.csv` schema and SHA-256 pin are checked
first. Every manifest date and identity receives preflight before any filing or
header is opened. Acceptance dates must remain inside **2010–2021**; timestamps
must be timezone-aware and agree with the New York acceptance date. Accessions
must be unique and syntactically valid. Source URLs must be original HTTPS SEC
archive URLs, and both recorded source hashes must be SHA-256 strings.

The existing `audit.cached_body` checker verifies each source URL, cache
metadata hash declaration, and manifest hash declaration. Small read adapters
bound allocation and check file-descriptor identities, including when a file
changes after the initial size check. Final source/cache-metadata/manifest
identity and hash checks run before the report is returned. Current limits are
1,000 filings, 40 MiB per primary document, 1 MiB per header, 64 KiB per cache
metadata file, 4 MiB for the manifest, and 64 MiB for the finished report.

### Co-filers remain separate

Every SGML `<FILER>` occurrence is retained with its source ordinal, raw CIK and
conformed-name values, comparison key, and structural diagnostics. There must
be **exactly one structurally unambiguous filer matching the original manifest
CIK**. Other valid filers remain context. Missing, repeated, or malformed
matching identities cannot satisfy this check. Opening/closing FILER and
COMPANY-DATA counts are checked; a partial extra block is not silently ignored.

SGML tag-boundary whitespace is stripped only for comparisons; the captured
values remain in the report. The CIK comparison requires nonzero ASCII digits
and uses a ten-digit comparison key. The accession prefix is never used to
infer the registrant. The header must separately contain one matching accession
and one original `10-K` form declaration.

The small change to `identity_review._header` uses this same all-filer check.
Its existing display fields come from the unique original-CIK match, and it
retains the complete filer list as JSON. All downstream pending-review,
source-binding, and approval gates remain unchanged. Existing review packets
and completed review records are not rewritten by the change.

### Acceptance is a clock observation

Exactly one complete SGML acceptance value is required. The existing
`timing.acceptance_from_header` interprets it as New York wall time. The reader
compares aware instants and the New York date, while retaining both the original
SGML value and the manifest timestamp representation. An equivalent UTC
encoding is accepted; a different instant is not.

This verifies the recorded acceptance clock only. It does not establish first
public dissemination, create a new timing rule, or modify the permitted filing
availability proxy or completed 20/20 review.

## Lexical cover facts and referenced contexts

The reader retains every inline occurrence with these selected local names:

| Fact family | Retained purpose |
|---|---|
| `EntityCentralIndexKey` | CIK text in its original document context. |
| `EntityRegistrantName` | Registrant-name text in that context. |
| `Security12bTitle` and `Security12gTitle` | Stated security-title text, with all classes/instruments retained. |
| `TradingSymbol` | Symbol text without selecting a common class. |
| `SecurityExchangeName` | Exchange text without turning it into an approved historical listing. |

Matching local names are retained even when their namespaces are missing or
unrecognized. Namespace evidence and unresolved flags distinguish such lexical
observations from recognized declarations. The reader observes inline namespace
declarations and the dated SEC DEI namespace shape; it does not validate a
taxonomy or claim complete XBRL validity. Prefixes shadowed on nearer elements
are resolved there. Prefix-case information that recovered HTML parsing cannot
reliably preserve remains unresolved.

Each fact records its parsed element ordinal/path, fact ID, raw QName and
namespace evidence, `contextRef`, parsed lexical text and serialization, format,
nil and continuation attributes, hidden observations, and unresolved flags.
Every referenced context occurrence is retained separately, including duplicate
IDs. Its payload contains entity identifiers and schemes, period components,
explicit/typed dimensions with QName evidence, and a hash of its parsed
serialization. Missing references, duplicate context IDs, and unrecognized
context namespaces remain explicit. Missing or malformed context components
remain lexical data; the reader does not certify context structure or validity.

**The parsing boundary matters.** Attributes labelled `_raw` are values exposed
by the recovered HTML tree; entity decoding or attribute-name case normalization
may already have occurred. `serialized_parsed_html` is normalized parser
serialization, not an original byte slice. Element ordinals and paths are not
source-byte offsets. The original-document SHA-256 binds these observations to
the source, and the recorded parser versions identify the extraction method.

Facts inside `ix:hidden` are retained. Inline style observations are recorded
without computing CSS visibility or following stylesheets. The existing
`clean_html` helper is deliberately not used because it removes needed hidden
facts and flattens class/context relationships.

Format transformations, nil semantics, exclusions and continuations are
**not interpreted**. An `ix:exclude` descendant remains in the lexical text with
an explicit flag. A `continuedAt` target is recorded but its text is not joined
into a fact value. `interpreted_xbrl_value` remains null for every fact. This
scope avoids quietly introducing a partial XBRL implementation. Selected text
or fragments above 32,768 characters, more than 4,096 selected facts or referenced contexts,
or more than 8 MiB of lexical evidence from one document cause a bounded failure
rather than silent truncation.

No title/ticker/exchange tuple is assembled across different contexts. A legal
entity dimension can distinguish a co-registrant while the context entity
identifier remains the principal registrant. A context duration is not evidence
of when a CIK-to-security link was effective or available. Untagged filings and
HTML parse failures receive explicit coverage statuses and are not converted
into identity exclusions.

## Report and later reconciliation

`records` contains one entry for every manifest filing, in original CSV record
order. Each entry contains `primary_source`, `header_source`, `header_identity`,
`acceptance_clock`, and `cover_evidence`. The latter contains complete `facts`
and `contexts` arrays. The report summary counts source checks, co-filers,
coverage statuses, selected fact families, hidden facts, and lexical issues.

This new report can accurately record `original_sec_bytes_reread=true` for its
own execution. It never changes the earlier
[Names/CCM identity packet](wrds_identity_candidates.md), whose manifest-only
run correctly recorded `original_sec_bytes_reread=false`. A later read-only
reconciliation can bind this report to that packet by manifest SHA, accession,
and original filer CIK. It must retain both discovery matches and unmatched
filings, and must not claim that another machine reread absent original bytes.

The reader keeps `known_at` and `available_at` null, `model_ready=false`,
`source_approvals=0`, `human_reviews_created=0`, and
`historical_security_links_created=0`. No final-period sources or market
outcomes are opened. Source consistency and observed cover text are evidence
for further identity work, not approval of a historical security mapping.

## Technical scope references

The implementation intentionally stops before the transformation, continuation,
and full context/fact semantics described by the official specifications. The
project's source research points to the
[SEC XBRL Guide](https://www.sec.gov/file/xbrl-guide-2024-07-08) and the
[final Inline XBRL 1.1 work-product index](https://specifications.xbrl.org/work-product-index-inline-xbrl-inline-xbrl-1.1.html).
Implementing those semantics would be a separate, explicitly tested change;
this lexical reader does not claim conformance to them.
