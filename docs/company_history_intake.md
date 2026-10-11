# Company History: pending WRDS export, offline intake ready

**11 October 2026.** The Cornell WRDS proxy session displayed the `HCIK`
(Historical CIK Number) variable in the **CRSP `companyhistory`** table for
`crsp_m_ccm`, and also in `comphist` under `crsp_q_ccm`,
`crsp_m_ccm` and `crsp_a_ccm`. These are **variable-catalog entries**, not
verified dataset access. Opening the query form redirected to the separate WRDS
account login. An individual account request was submitted and is **pending
institutional approval**, not activated. No new Company History export,
live vendor data, historical release, or human research approval was obtained.

These observations refine the [historical-source lead](historical_identity_access_evidence.md).
The [official CRSP dictionary](https://www.crsp.org/wp-content/uploads/ccm_files/CompanyHistory.html)
describes `HCIK` and effective description bounds `HCHGDT` and
`HCHGENDDT`. The actual delivered field names, interval conventions,
product table and release semantics must be checked against the approved
export. **Do not infer `known_at` from the effective date, the day of
download, the registration request or the dictionary page.**

## Offline source-preservation workflow (not yet run on licensed history)

A new, isolated importer is available in
[`company_history_intake.py`](../src/disclosure_research/company_history_intake.py),
with a [CLI wrapper](../scripts/wrds_company_history_intake.py). This is
preparation for the authorized source, not evidence that the source exists
in the repository. It **does not login, query or scrape WRDS**, does not
submit a vendor form, and never opens SEC or holdout return labels.

After an authorized manual CSV export, inspect the *actual* downloaded header
and save the original unmodified bytes privately. Record its SHA-256 and the
specific source product/table. An explicit metadata document must accompany the
CSV. For example, this is **only a schema example**, not an observed export:

```json
{
  "schema_version": 1,
  "data_kind": "AUTHORIZED_VENDOR_EXPORT",
  "product": "crsp_m_ccm",
  "table": "companyhistory",
  "protocol_sha256": "<actual locked protocol SHA-256>",
  "source_sha256": "<actual source CSV SHA-256>",
  "columns": {
    "gvkey": "GVKEY",
    "hcik": "HCIK",
    "valid_from": "HCHGDT",
    "valid_to": "HCHGENDDT",
    "permno": "LPERMNO"
  },
  "date_format": "YYYYMMDD",
  "open_start_values": [],
  "open_end_values": [],
  "claimed_known_at": null,
  "source_approved": false,
  "source_release": null,
  "exported_at": null
}
```

For invented tests, use `data_kind: SYNTHETIC_ENGINEERING_FIXTURE` rather
than `AUTHORIZED_VENDOR_EXPORT`. This is a declared classification, not
independent verification that a CSV truly came from WRDS.

The column names, date format and open-bound sentinels above **must be changed
to match observed source fields and supported vendor conventions**. An empty
sentinel list means *none declared*; values such as `99999999` may be listed
only when actually observed and documented. Set `permno` to `null` if no
permanent security identifier exists in the delivered table. If the source
offers `KYGVKEY` instead of `GVKEY`, use an explicit mapping to that
actual column; do not rename the unmodified raw CSV. Do not fabricate an
`exported_at` or `source_release` value.

Example command, **after** the approved export exists:

```bash
uv run --locked --python 3.12 python scripts/wrds_company_history_intake.py \
  --source data/private/wrds-company-history/incoming/history.csv \
  --manifest data/private/wrds-company-history/incoming/manifest.json \
  --output data/private/wrds-company-history/staged-v1
```

The output must be a **new path** beneath local `data/` or `outputs/`; an
existing output is never overwritten. The script rechecks the manifest
protocol fingerprint against the actual frozen protocol, verifies the input
SHA-256 before and after processing, preserves original CSV bytes, and emits:

| Private output | Description |
| --- | --- |
| `original.csv`, `input_manifest.json` | Original copied data and its source-specific field declarations |
| `candidate_intervals.csv` | Dated issuer candidates with raw IDs/intervals and explicit empty `known_at` |
| `review_issues.csv` | Every source record requiring closer inspection; rows are not silently discarded |
| `overlap_examples.csv` | Bounded examples of overlapping, competing CIK observations by GVKEY or PERMNO |
| `public_summary.json`, `receipt.json` | Aggregate counts, SHA-256 provenance and unchanged closed research gates |

A record beginning after **2022-02-02** is not admitted to the
development-candidate stage; it remains in the original saved source and is
counted in the out-of-scope audit. Rows ending before **2009-10-07** are
similarly retained as raw history but not promoted to development candidates.
These limits are for **this development intake only**, not the final universe
or the eventual holdout source plan.

All comparison intervals are **provisional inclusive candidate intervals**
only; this choice highlights overlap for review and does not certify the
vendor's endpoint semantics. Coincident effective-interval **comparison projections** remain counted and
flagged by source-record number, never merged; their original raw spellings may
differ in leading zeroes, so a flagged projection is not necessarily an exact
raw duplicate. GVKEY comparison itself retains exact raw spelling. These are
review leads, not identity decisions. A missing/zero/invalid PERMNO remains unlinked, not replaced
with a current security. No result is accepted as an approved security-to-issuer
mapping; every row has `mapping_approved=false` and empty `known_at`.

If the actual Company History export is not available under the approved WRDS
account, stop here and seek an authorized source or institutional guidance.
Do not use an unrelated current-header CIK as a substitute. Even a successful
history intake will still require independent effective-bound/source-vintage
review, known-at evidence, original SEC/CCM corroboration, selection-population
coverage, market normalization and named human review before the empirical
pilot. The [research completion gates](research_completion_gates.md) and frozen
protocol remain unchanged.

## Synthetic verification

`tests/test_company_history_intake.py` tests the importer with synthetic-only
cases. They check competing overlapping CIKs, inclusive boundary conditions,
open-ended markers, missing link identifiers, corrupt headers or rows, unsafe
metadata, changed source hashes, output collisions and preservation of closed
gates. Passing those tests demonstrates the software's behavior, **not** access
to or correctness of any real Company History records.

## Verified engineering checkpoint

The [11 October checkpoint](../reports/company_history_intake_checkpoint.json)
records a **synthetic-only** CLI smoke: three invented history records, two
effective-interval candidates, one GVKEY conflict pair, one PERMNO conflict
pair, and explicit out-of-scope and unlinked-PERMNO issues. The original
fixture CSV and complete private receipt remain ignored in local
`outputs/`; the published report contains only aggregate counts and the
private receipt's digest. A separate seeded brute-force check confirmed
the overlap sweep over 30 synthetic sets of 90 records each. The final
`make reproduce-full` completed Ruff, **1,019 passing tests**, and the
synthetic study pipeline.

This does not show that real `companyhistory` access was granted or that
historical identity/availability is defensible. Milestones 5–11 remain
empirically unapproved; the final evaluation remains unopened.
