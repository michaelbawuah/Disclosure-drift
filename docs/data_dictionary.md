# Filing data dictionary

| Field | Meaning and source |
|---|---|
| `cik` | SEC issuer identifier, zero padded to ten digits |
| `accessionNumber` | SEC accession for the original filing |
| `form` | Exact SEC form, retained only when equal to 10-K |
| `reportDate` | Period of report; used for consecutive annual pairing, not availability |
| `filingDate` | SEC filing date; discovery filter only |
| `acceptanceDateTime` | Raw timestamp from submissions API, preserved unchanged |
| `acceptance_timestamp` | SGML acceptance interpreted in America/New_York; explicit API-offset fallback flagged |
| `acceptance_source` | Header evidence or a flagged fallback |
| `api_header_difference_seconds` | API instant minus interpreted SGML instant; discrepancies require audit |
| `availability_status` | Whether actual public dissemination has been verified; proxy remains marked |
| `source_url`, `header_url` | Official SEC source locations |
| `download_sha256`, `header_sha256` | Content fingerprints |
| `fetched_at` | Retrieval timestamp, not historical public availability |
| `extraction_status` | ok, review or missing; automated, pending human audit |
| `extraction_reason` | Explanation for the current status |
| `risk_text`, `risk_token_count` | Cleaned Item 1A body and alphabetic token count |
| `extraction_version` | Parser version for reproducibility |
| `reference_session` | Second XNYS session after acceptance date |
| `controls_through` | Session before the reference session |
| `prediction_time_utc` | Reference session's open; feature availability must precede it |
| `label_end` | Session 20 trading sessions after the reference session |

The paired table carries current and previous accessions/text/URLs. Extraction
exclusions are separate records with explicit reasons. The parser does not infer
returns, trading signals, risk-theme labels or manually reviewed accuracy.
