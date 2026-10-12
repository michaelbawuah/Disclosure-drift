# Direct original SEC Risk Factors boundary diagnostics

**12 October 2026.** This intentionally **post-hoc diagnostic source review**
tests whether the biggest observed lexical changes from the earlier
[SEC-only descriptive study](sec_only_descriptive_study.md) are reproducible
from the *current original SEC 10-K HTML*, rather than merely copied
from the saved feature table.

The predeclared diagnostic selection algorithm uses only the balanced
34-issuer 2019→2021 Jaccard change: choose the **largest positive**
(PepsiCo), **largest negative** (Amazon), **closest to zero** (Nike), and
**closest to the median** (Bank of America). It does not use stock-return
outcomes or the sealed final test. The selection is deliberately sensitive
to the observed descriptive result and **is not a random or representative
sample**.

## Direct SEC source results

| Source diagnostic | Verified count |
| --- | ---: |
| Distinct purposively selected issuers | **4** |
| Original SEC annual 10-K HTMLs from 2018–2021 | **16 / 16 retrieved** |
| Current original HTML has the same SHA-256 as the previously verified historical source record | **0 / 16** |
| Original Item 1A extracted token count reproduced | **16 / 16** |
| Original extraction version/status reproduced | **16 / 16** |
| Annual Item 1A token-set Jaccard values reproduced | **12 / 12** |
| Original annual log-length change reproduced | **12 / 12** |
| 2019→2021 four-filing issuer Jaccard contrasts reproduced | **4 / 4** |

The live source HTMLs were retrieved from exact, original SEC manifest URLs
using a contact-bearing research User-Agent and a conservative request
interval, no redirects, size limits, an archive-only domain/issuer/accession
check and a stop-on-error policy. All originals and CIK-level comparisons
remain under `outputs/sec-original-extremes-20261012-v1/`. The historical
source SHA-256 and newly fetched SHA-256 are **both retained**. No current
copy was silently represented as byte-identical to an earlier archived one.

The source extractor reproduced these four original issuer contrasts:

| Original SEC issuer | Post-hoc reason for review | 2019→2021 within-issuer annual Jaccard contrast |
| --- | --- | ---: |
| PepsiCo | largest positive | +0.31909 |
| Amazon | largest negative | −0.05806 |
| Nike | closest to zero | +0.00248 |
| Bank of America | closest to panel median | +0.04385 |

For PepsiCo, the original 2020 and 2021 Item 1A sections have
**14,493** and **6,964** extracted tokens respectively. Both figures
were reproduced directly from the current original SEC documents. This
supports a large descriptive document change, but **does not identify
its cause** or establish that a first-publication time is known.

The archive-byte differences persist in each downloaded HTML. The
earlier original filing source record contains SHA-256 but the precise
older body bytes were not present for direct byte-diff review. Matching
extractor output and counts cannot prove identical historical versions.

These checks are **automated source extraction and arithmetic**.
Source-section boundary *human review*, historically effective CRSP
security classifications, the first public filing dissemination time and
the original market source `known_at` remain unapproved. No one has
adjudicated risk-factor scope changes from these data alone.

## Independent original-source review

The [direct source verifier](../src/disclosure_research/sec_sample_original_verifier.py)
reopens all 16 saved current SEC HTML files, validates their individual
source byte hashes and their exact original 215-record SEC manifest
accessions, years and URLs, then independently rebuilds the year-level
token counts and lexical-set arithmetic using `re.findall`.
It uses the **same previously audited conservative Item 1A boundary
extractor**—so the Jaccard arithmetic is independently implemented but
the parsing boundary is *not* independently human-adjudicated.
It recomputes the original 34-issuer diagnostic selection and all four
signed 2019→2021 issuer differences before comparing the private
case evidence and aggregate public result.

The [publication-safe source checkpoint](../reports/sec_original_extremes_checkpoint.json)
and [independent source verification](../reports/sec_original_extremes_independent.json)
contain no individual CRSP security identity or licensed market rows.
Private source HTML, filing CIKs, source-level review flags and the exact
issuer comparison packet are gitignored.

## Reproduce without refetching SEC

To reverify the preserved **current original HTML** without any network call:

```bash
uv run --locked --python 3.12 python scripts/verify_sec_original_extremes.py \
  --intake outputs/sec-original-extremes-20261012-v1 \
  --sources reports/pilot_expansion \
  --output reports/independent-original-risk-NEW.json
```

The initial fetch is implemented in
[`scripts/review_sec_original_extremes.py`](../scripts/review_sec_original_extremes.py).
It requires an authorized Mac, a legitimate SEC contact-bearing
`SEC_USER_AGENT` and a **fresh private output path**; rerunning downloads
unnecessarily is not required.

The audited **35-issuer purposive SEC pilot** is not the frozen investable
U.S. stock universe. A source-reviewed small diagnostic subset cannot
turn the exploratory text statistic into a causal finding, a
historically available investment signal or a validated out-of-sample
return forecast. Original research milestones and the sealed 2022–2025
holdout remain closed.

## Reproducibility checkpoint

The [source-only reproducibility receipt](../reports/sec_sensitivity_reproduction.json)
records successful full-repository Ruff checks, **1,245 tests** and the
end-to-end *invented input* software pipeline. A separate independent
source verifier was run twice on the *same* 16 previously downloaded
original SEC HTML files, without another SEC network request; the
two aggregate original-source verification reports were byte-identical.
Both verifications reconstructed **16 source token counts**, **12 annual
token-set Jaccard and length features** and **four signed issuer changes**.
All live SEC source hashes continue to differ from the earlier
manifest and remain explicit source-version warnings, not silently
approved historical equivalents.
