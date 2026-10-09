# Milestone 03: resolving referenced risk disclosures

Completed 9 October 2026. Fourteen previously flagged cases now produce bounded,
source-verified text under explicit registered rules. Human review remains pending.

## Measured comparison

| Check | Numbered-section baseline | With reference rules |
|---|---:|---:|
| Original filings in the targeted sample | 24 | 24 |
| Issuers: J&J, Intel and GE | 3 | 3 |
| Automatically usable extractions | 10 | 24 |
| Annual pairs ready for review | 7 | 21 |
| Unresolved extraction cases | 14 | 0 |

All 24 primary documents and original acceptance headers match the byte hashes
published in milestone 02. The baseline text hashes also match that earlier
manifest. The ten unregistered control texts and every event date are unchanged.
The cached baseline/resolved rebuild required zero network requests.

The 11 GE/Intel page-reference cases use explicit ranges in the main document.
The three J&J cases use incorporated Exhibit 99 bodies, after verifying a unique
EX-99 entry in the original accession's document index. Rules pin the primary
reference, source bytes, normalized range, resulting text hash and token count.
They are assistant-proposed instructions for known cases, not a general parser
or proof of human approval. See the [boundary policy](../docs/reference_resolution.md).

## Review evidence

- [HTML audit packet](reference_audit.html): 24 expandable source cards, short
  boundary excerpts, original filing/header links and actual risk-source links.
- [Filing evidence manifest](reference_filing_manifest.csv): source and rule hashes,
  normalized ranges, dates, extraction methods and review status; no full texts.
- [Annual pairs](reference_review_pairs.csv): all 21 pairs selected for review.
- [Pending review template](reference_reviews.template.jsonl): copy to an ignored
  output file before recording named reviews; the published template contains no approvals.
- [Machine-readable verification](milestone_03.json): counts, hashes and execution evidence.

Three annual pairs change extraction method: J&J's 2017 filing, Intel's 2018 filing
and GE's 2015 filing. These are highlighted for review. A source-format transition
must not automatically be interpreted as an economic change in risk.

No human reviews have been signed off. The targeted sample has no API/header
timestamp disagreements; this does not resolve the 72 disagreements recorded
across the broader milestone 02 sample. Exact public dissemination remains
unverified, and the original second-session timing proxy remains explicit.

## Implementation and verification

Tested code: `2abbc37042cb86f74f2cfd8d4d1b3764a9291e44`.
The full reproduction passed 70 tests, Ruff, protocol verification and the
synthetic demo in the cloud, on the owner's Mac, and in
[GitHub Actions](https://github.com/michaelbawuah/Disclosure-drift/actions/runs/37999382935).
Cloud checks used Python 3.12.14; CI used Python 3.12.3. Four upstream calendar/NumPy
deprecation warnings remain. The actual SEC source comparison ran in the cloud;
Mac verification ran the code tests and synthetic demo.

The new checks cover altered primary/index/exhibit bytes, incorrect exhibit types,
duplicate index entries, source paths outside the original accession, invalid
ranges, stale review rules, altered pair texts and skipped annual predecessors.
An original filing's acceptance header still supplies timing for its exhibit.

With an identifying `SEC_USER_AGENT`, reproduce the source comparison with:

```bash
make reference-reproduce
```

This rebuilds both extraction variants, the offline audit packet and the comparison
record. Changed registered source bytes stop reproduction for investigation.

## Scope and next gates

This is a targeted 24-filing regression sample. The full 155-filing pilot was not
rerun with this revision, so no revised aggregate count for that larger sample is
claimed. Internal page furniture remains under the unchanged normalizer.

Next, review the 21 annual pairs and source-method transitions, rerun the broader
pilot, and obtain verified historical market data. Cornell's current WRDS entry
page lists student day-pass access; actual CRSP/table entitlements still need to be
checked through the user's authorized access. See the
[access checklist](../docs/data_access_checklist.md).

No real return labels or forecast scores were produced. The 2022-2025 final test
remains closed, and the frozen primary model and inference protocol are unchanged.
