"""All issuer-anchor inputs in these tests are invented, never vendor observations."""

import csv
import gzip
import hashlib
import json

import pandas as pd
import pytest

from disclosure_research.pilot_issuer_anchor import run_pilot_anchor
from disclosure_research.pilot_issuer_anchor_verifier import independently_verify_anchor
from disclosure_research.protocol import canonical_hash, load_protocol

NAMES = [
    "permno", "hdrprimaryexch", "nasdissuno", "hdrsiccd", "permco",
    "secinfostartdt", "secinfoenddt", "securitybegdt", "securityenddt",
    "cusip", "ticker", "issuernm", "shareclass", "usincflg", "issuertype",
    "securitytype", "securitysubtype", "sharetype", "securityactiveflg",
    "siccd", "primaryexch", "tradingsymbol", "naics", "tradingstatusflg",
]
OWNERSHIP = [
    "ACCESSION_NUMBER", "FILING_DATE", "PERIOD_OF_REPORT", "DATE_OF_ORIG_SUB",
    "NO_SECURITIES_OWNED", "NOT_SUBJECT_SEC16", "FORM3_HOLDINGS_REPORTED",
    "FORM4_TRANS_REPORTED", "DOCUMENT_TYPE", "ISSUERCIK", "ISSUERNAME",
    "ISSUERTRADINGSYMBOL", "REMARKS",
]


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _save(root, folder, rows):
    """One-part synthetic counterpart of the original immutable table manifest."""
    part = root / folder / "part-000001.parquet"
    part.parent.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(part, index=False)
    return {
        "parts": [{"file": f"{folder}/part-000001.parquet", "bytes": part.stat().st_size,
                   "rows": len(rows), "sha256": _sha(part)}],
        "fields": pd.read_parquet(part).columns.tolist(),
        "rows": len(rows),
    }


def _write_csv(path, columns, rows, delimiter=","):
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out, delimiter=delimiter)
        writer.writerow(columns)
        writer.writerows(rows)


@pytest.fixture
def example(tmp_path):
    repo = tmp_path / "repo"
    market, own, outside, report = (
        repo / "data" / "market",
        repo / "data" / "ownership",
        repo / "data" / "originals",
        repo / "reports",
    )
    for folder in [market, own, outside, report]:
        folder.mkdir(parents=True, exist_ok=True)
    config = load_protocol()
    digest = canonical_hash(config)
    nrows = []
    sec_rows = []
    cohort, summaries, observations, names, sec_events, comparisons, market_rows = (
        [] for _ in range(7)
    )
    issuer = []
    for i in range(20):
        cik = f"{1200000000 + i:010d}"
        sec = str(5000 + i)
        symbol = f"Q{i:02d}"
        issuer.append((cik, sec, symbol))
        values = [
            sec, "N", "", "3000", str(8000 + i),
            "2011-01-01", "2024-12-31", "1999-01-01", "2025-12-31",
            f"{i:08d}", symbol, f"SYNTHETIC CORP {i}", "", "Y", "CORP",
            "EQTY", "", "NS", "Y", "3000", "N", symbol, "123456", "A",
        ]
        nrows.append(values)
        names.append({
            **dict(zip(NAMES, values, strict=True)),
            "source_csv_record": i + 2, "source_sha256": "", "source_inventory_sha256": "",
            "retention_roles_json": "[]",
            "known_at": None, "available_at": None, "identity_approved": False,
        })
        sec_values = [
            f"9999999999-19-{i + 1:06d}", "01-NOV-2019", "", "", "", "", "", "",
            "4", cik, f"SYNTHETIC CORP {i}", symbol, "",
        ]
        sec_rows.append(sec_values)
        sec_events.append({
            "source_tsv_record": i + 2,
            "accession": sec_values[0],
            "identity_approved": False,
        })
        cohort.append({
            "security_id": sec, "selection_asof": "2020-01-01",
            "information_cutoff": "2019-12-31T21:00:00+00:00",
            "rank_eligible_by_candidate_policy": True,
            "identity_approved": False, "known_at": None,
        })
        summaries.append({
            "security_id": sec,
            "observation_status": "EARLIER_DATE_UNAMBIGUOUS_LITERAL_OBSERVATIONS",
            "observation_rows": 1,
            "unambiguous_earlier_date_sec_occurrences": 1,
            "earlier_issuer_cik_comparison_keys_json": json.dumps([cik]),
            "earlier_candidate_header_agreement": i != 0,
            "earlier_candidate_header_disagreement": i == 0,
            "identity_approved": False, "known_at": None, "available_at": None,
        })
        observations.append({
            "observation_id": f"observed-{i}",
            "security_id": sec,
            "names_source_csv_record": i + 2,
            "source_tsv_record": i + 2,
            "filing_date": "2019-11-01",
            "accession": sec_values[0],
            "sec_issuer_cik_raw": cik,
            "sec_issuer_cik_comparison_key": cik,
            "sec_symbol_raw": symbol,
            "cutoff_date_relation": "BEFORE_CUTOFF_DATE",
            "unambiguous_exact_literal_observation": True,
            "global_symbol_record_count": 1, "security_date_record_count": 1,
            "names_record_covers_selection": True, "securitylife_covers_filing_date": True,
            "sec_source_sha256": "", "names_source_sha256": "",
            "known_at": None, "available_at": None, "identity_approved": False,
        })
        comparisons.append({
            "security_id": sec, "cik_comparison": "DIFFERENT_VALID_COMPARISON_KEYS"
            if i == 0 else "EXACT_RAW_TEXT",
        })
    # Include cutoff-day evidence for one security. It is retained but cannot
    # establish a strictly earlier historical filing.
    sec_rows.append([
        "9999999999-19-999999", "31-DEC-2019", "", "", "", "", "", "", "4",
        issuer[0][0], "SYNTHETIC CORP 0", issuer[0][2], "",
    ])
    observations.append({
        **observations[0], "observation_id": "cutoff-observation",
        "source_tsv_record": len(sec_rows) + 1,
        "filing_date": "2019-12-31", "accession": sec_rows[-1][0],
        "cutoff_date_relation": "CUTOFF_DAY_TIME_UNRESOLVED",
    })
    sec_events.append({
        "source_tsv_record": len(sec_rows) + 1, "accession": sec_rows[-1][0],
        "identity_approved": False,
    })
    summaries[0]["observation_rows"] = 2
    originals = []
    for n in range(135):
        cik = issuer[n % 20][0]
        year = 2015 + n // 20
        acc = f"{cik}-{year % 100:02d}-{n + 1:06d}"
        stamp = f"{year}-10-09T14:01:00-04:00"
        market_rows.append({
            "event_id": acc, "cik": cik, "candidate_permno": issuer[n % 20][1],
            "acceptance_timestamp": stamp,
            "model_ready": False, "identity_approved": False,
            "open_end_unresolved": True, "human_pair_review_complete": False,
            "qa_status": "calculated_pending_review",
            "data_kind": "PROVISIONAL_CANDIDATE_ARITHMETIC_QA",
        })
        originals.append({
            "accession": acc, "manifest_cik_raw": cik,
            "recorded_acceptance_timestamp": stamp,
            "header_identity": {
                "header_identity_consistent": True, "matching_filer_count": 1,
                "filers": [{"cik_comparison_key": cik, "matches_manifest_cik": True}],
            },
            "security_link_created": False, "known_at": None, "available_at": None,
        })
    for i in range(80):
        originals.append({
            "accession": f"9999999999-14-{i+1:06d}",
            "manifest_cik_raw": "9999999999",
            "recorded_acceptance_timestamp": "2014-01-03T09:00:00-05:00",
            "header_identity": {
                "header_identity_consistent": True, "matching_filer_count": 1,
                "filers": [{"cik_comparison_key": "9999999999", "matches_manifest_cik": True}],
            },
            "security_link_created": False, "known_at": None, "available_at": None,
        })
    names_source = outside / "source.csv"
    ownership_tsv = own / "original_SUBMISSION.tsv"
    _write_csv(names_source, NAMES, nrows)
    _write_csv(ownership_tsv, OWNERSHIP, sec_rows, delimiter="\t")
    for obj in names:
        obj["source_sha256"] = _sha(names_source)
    for obj in observations:
        obj["sec_source_sha256"] = _sha(ownership_tsv)
        obj["names_source_sha256"] = _sha(names_source)
    tables = {}
    for folder, values in [
        ("cohort", cohort), ("cohort_summary", summaries),
        ("observations", observations), ("names_records", names),
        ("sec_occurrences", sec_events), ("header_comparisons", comparisons),
    ]:
        tables[folder] = _save(own, folder, values)
    owner_receipt = {
        "status": "SEC_OWNERSHIP_ISSUER_OBSERVATIONS_NOT_APPROVED_LINKS",
        "source_quarter": "2019Q4", "cohort_year": 2020,
        "information_cutoff": "2019-12-31T21:00:00+00:00",
        "selection_asof": "2020-01-01",
        "protocol_sha256": digest, "model_ready": False,
        "final_period_opened": False, "source_approvals": 0,
        "historical_cik_links_created": 0, "known_at_inferred": False,
        "available_at_inferred": False,
        "counts": {"cohort_rows": 20, "original_sec_occurrences": len(sec_rows),
                   "original_names_source_rows_checked": len(nrows)},
        "inputs": {"sec_submission_sha256": _sha(ownership_tsv),
                   "names_source_sha256": _sha(names_source)},
        "tables": tables,
    }
    (own / "receipt.json").write_text(json.dumps(owner_receipt))
    candidate_file = market / "candidate_calculations.parquet"
    pd.DataFrame(market_rows).to_parquet(candidate_file, index=False)
    market_receipt = {
        "data_kind": "PROVISIONAL_CANDIDATE_ARITHMETIC_QA",
        "source_hashes": {"protocol": digest}, "model_ready": False,
        "final_period_opened": False,
        "historical_cik_mapping_approved": False, "qa_cases_calculated": 135,
        "files": {"candidate_calculations.parquet": _sha(candidate_file)},
    }
    (market / "audit_summary.json").write_text(json.dumps(market_receipt))
    raw_report = json.dumps({
        "status": "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED",
        "original_sec_bytes_reread": True,
        "protocol_sha256": digest, "source_approvals": 0,
        "final_period_opened": False,
        "historical_security_links_created": 0, "records": originals,
    }).encode()
    pub_gzip = report / "sec_identity_evidence.json.gz"
    pub_gzip.write_bytes(gzip.compress(raw_report, mtime=0))
    publication = {
        "publication": {
            "sha256": _sha(pub_gzip), "bytes": pub_gzip.stat().st_size,
            "uncompressed_sha256": hashlib.sha256(raw_report).hexdigest(),
            "uncompressed_bytes": len(raw_report),
        },
        "source_approvals": 0, "final_period_opened": False,
    }
    execution = report / "sec_identity_evidence_execution.json"
    execution.write_text(json.dumps(publication))
    return {
        "repo": repo,
        "market": market, "ownership": own,
        "names": names_source, "sec_gzip": pub_gzip, "sec_execution": execution,
        "output": repo / "outputs" / "first",
        "config": config,
    }


def _run(x):
    return run_pilot_anchor(
        x["market"], x["ownership"], x["names"], x["sec_gzip"], x["sec_execution"],
        x["output"], config=x["config"], repo_root=x["repo"],
        ownership_receipt_sha256=_sha(x["ownership"] / "receipt.json"),
        candidate_receipt_sha256=_sha(x["market"] / "audit_summary.json"),
    )


def _refresh_table(x, table, transform):
    own = x["ownership"]
    file = own / table / "part-000001.parquet"
    frame = pd.read_parquet(file)
    transform(frame)
    frame.to_parquet(file, index=False)
    receipt_path = own / "receipt.json"
    obj = json.loads(receipt_path.read_text())
    obj["tables"][table]["parts"][0]["sha256"] = _sha(file)
    obj["tables"][table]["parts"][0]["bytes"] = file.stat().st_size
    receipt_path.write_text(json.dumps(obj))


def test_anchored_issuers_and_gates_and_hashbound_private_output(example):
    out = _run(example)
    assert out["pilot_issuers"] == out["securities_with_strictly_earlier_unambiguous_matching_issuer_cik"] == 20
    assert out["strictly_earlier_dated_SEC_ownership_name_observations"] == 20
    assert out["cutoff_day_observations_retained_but_not_used_as_earlier"] == 1
    assert out["pilot_development_event_count"] == out["original_10k_event_headers_matching_original_cik_and_acceptance"] == 135
    assert out["original_SEC_quarterly_rows_reread"] == 21
    assert out["original_CRSP_Names_rows_reread"] == 20
    assert out["candidate_header_agreement_issuers"] == 19
    assert out["candidate_header_disagreement_issuers"] == 1
    assert out["security_links_approved"] == 0
    assert not out["historical_known_at_established"]
    assert not out["final_period_opened"]
    receipt = json.loads((example["output"] / "receipt.json").read_text())
    assert receipt["source_approvals"] == 0
    for filename, binding in receipt["files"].items():
        assert _sha(example["output"] / filename) == binding["sha256"]
        assert example["output"].stat().st_mode & 0o077 == 0
        assert (example["output"] / filename).stat().st_mode & 0o222 == 0
    rows = [json.loads(x) for x in (example["output"] / "private_issuer_rows.jsonl").read_text().splitlines()]
    assert len(rows) == 20
    assert sum(x["strictly_earlier_2019q4_source_observations"] for x in rows) == 20
    assert all(x["known_at"] is None and not x["source_identity_approval"] for x in rows)


def test_original_source_hash_tamper_is_detected(example):
    example["names"].write_text(example["names"].read_text() + "\n")
    with pytest.raises(ValueError, match="Original CRSP Names CSV SHA"):
        _run(example)


def test_original_quarterly_source_tamper_is_detected(example):
    raw = example["ownership"] / "original_SUBMISSION.tsv"
    raw.write_text(raw.read_text().replace("SYNTHETIC CORP 4", "CORRUPTED CORP 4"))
    with pytest.raises(ValueError, match="Original SEC ownership TSV SHA"):
        _run(example)


def test_original_sec_publication_hash_tamper_is_detected(example):
    example["sec_gzip"].write_bytes(example["sec_gzip"].read_bytes() + b"garbage")
    with pytest.raises(ValueError, match="publication checksum"):
        _run(example)


def test_mutated_ownership_part_requires_new_receipt_and_is_refused(example):
    file = example["ownership"] / "observations" / "part-000001.parquet"
    file.write_bytes(file.read_bytes() + b"mutation")
    with pytest.raises(ValueError, match="Parquet changed"):
        _run(example)


def test_per_security_conflicting_issuer_cik_cannot_be_reported_as_match(example):
    def change(frame):
        frame.loc[0, "sec_issuer_cik_comparison_key"] = "0000000099"
    _refresh_table(example, "observations", change)
    with pytest.raises(ValueError, match="[Oo]riginal SEC"):
        _run(example)


def test_cutoff_day_observation_cannot_be_reclassified_as_earlier(example):
    def change(frame):
        frame.loc[frame["filing_date"].eq("2019-12-31"), "cutoff_date_relation"] = "BEFORE_CUTOFF_DATE"
    _refresh_table(example, "observations", change)
    with pytest.raises(ValueError, match="misclassified"):
        _run(example)


def test_changed_candidate_cik_does_not_pass_original_10k_check(example):
    path = example["market"] / "candidate_calculations.parquet"
    frame = pd.read_parquet(path)
    original_cik = frame.loc[0, "cik"]
    frame.loc[frame["cik"].eq(original_cik), "cik"] = "0000000009"
    frame.to_parquet(path, index=False)
    receipt = json.loads((example["market"] / "audit_summary.json").read_text())
    receipt["files"]["candidate_calculations.parquet"] = _sha(path)
    (example["market"] / "audit_summary.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="[Oo]riginal SEC"):
        _run(example)


def test_future_holdout_filing_rejected_before_ownership_sources(example):
    path = example["market"] / "candidate_calculations.parquet"
    frame = pd.read_parquet(path)
    frame.loc[0, "acceptance_timestamp"] = "2023-11-01T10:01:00-04:00"
    frame.to_parquet(path, index=False)
    receipt = json.loads((example["market"] / "audit_summary.json").read_text())
    receipt["files"]["candidate_calculations.parquet"] = _sha(path)
    (example["market"] / "audit_summary.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="forbidden later-period"):
        _run(example)


def test_false_approval_flag_is_rejected(example):
    def change(frame):
        frame.loc[0, "identity_approved"] = True
    _refresh_table(example, "cohort_summary", change)
    with pytest.raises(ValueError, match="historical-unapproved"):
        _run(example)


def test_reuse_existing_evidence_path_is_refused(example):
    _run(example)
    with pytest.raises(ValueError, match="overwrite"):
        _run(example)


def test_source_date_name_interval_mismatch_rejected(example):
    def change(frame):
        frame.loc[0, "secinfostartdt"] = "2020-04-01"
    _refresh_table(example, "names_records", change)
    with pytest.raises(ValueError, match="Original CRSP Names row differs"):
        _run(example)


def test_unsupported_symlinked_source_file_rejected(example):
    link = example["repo"] / "data" / "names-link.csv"
    link.symlink_to(example["names"])
    example["names"] = link
    with pytest.raises(ValueError, match="Symbolic links"):
        _run(example)


def test_report_has_no_licensed_identifiers_or_raw_symbol_listing(example):
    _run(example)
    report = (example["output"] / "public_summary.json").read_text()
    assert "pilot_candidate_permno" not in report
    assert "original_sec_filer_cik" not in report
    assert "sec_symbol_raw" not in report
    assert "source_tsv_record" not in report
    assert "conditional_development_event_count" not in report
    assert "20" in report


def test_missing_original_header_reread_is_not_claimed(example):
    result = _run(example)
    assert result["original_SEC_headers_reread_this_run"] is False
    assert result["original_quarterly_SEC_TSV_reread_this_run"] is True
    assert result["original_CRSP_Names_CSV_reread_this_run"] is True


def _independent(example):
    return independently_verify_anchor(
        example["output"], example["ownership"] / "receipt.json",
        example["ownership"] / "original_SUBMISSION.tsv",
        example["names"], example["repo"] / "reports" / "independent.json",
        repo_root=example["repo"],
    )


def test_independent_direct_raw_sec_names_reproduces_all_quarter_anchors(example):
    first = _run(example)
    second = _independent(example)
    assert second["original_sec_submissions_reexamined"] == 21
    assert second["original_names_descriptors_reexamined"] == 20
    assert second["original_sec_submissions_from_20_pilot_ciks"] == 21
    assert second["securities_with_independently_matched_strictly_earlier_anchors"] == 20
    assert second["strictly_earlier_unambiguous_issuer_security_observations"] == 20
    assert second["cutoff_day_unresolved_observations"] == 1
    assert second["ambiguous_or_mismatched_source_observations"] == 0
    assert second["per_issuer_earlier_and_cutoff_counts_identical_to_first_audit"]
    assert not second["historical_effective_interval_established"]
    assert not second["historical_known_at_established"]
    assert not second["actual_final_2022_2025_opened"]
    assert first["securities_with_strictly_earlier_unambiguous_matching_issuer_cik"] == 20
    public = (example["repo"] / "reports" / "independent.json").read_text()
    assert "pilot_candidate_permno" not in public
    assert "original_sec_filer_cik" not in public


def test_independent_verifier_rejects_original_names_tamper(example):
    _run(example)
    example["names"].write_text(example["names"].read_text().replace("SYNTHETIC CORP 2", "OTHER CORP 2"))
    with pytest.raises(ValueError, match="Independent source bytes"):
        _independent(example)


def test_independent_verifier_rejects_modified_private_rows(example):
    _run(example)
    path = example["output"] / "private_issuer_rows.jsonl"
    path.chmod(0o600)
    path.write_text(path.read_text().replace('"source_identity_approval": false',
                                             '"source_identity_approval": true', 1))
    with pytest.raises(ValueError, match="output hash mismatch"):
        _independent(example)


def test_independent_verifier_does_not_allow_reusing_same_public_report_path(example):
    _run(example)
    _independent(example)
    with pytest.raises(ValueError, match="new aggregate"):
        _independent(example)


def test_independent_verifier_cannot_rewrite_an_original_receipt(example):
    _run(example)
    receipt = example["ownership"] / "receipt.json"
    receipt.write_text(receipt.read_text() + chr(10))
    with pytest.raises(ValueError, match="Original pilot anchor|Independent source bytes"):
        _independent(example)


def test_independent_verifier_rejects_fake_earlier_count_even_when_fully_rehashed(example):
    _run(example)
    detail = example["output"] / "private_issuer_rows.jsonl"
    original = [json.loads(x) for x in detail.read_text().splitlines()]
    original[0]["strictly_earlier_2019q4_source_observations"] += 1
    detail.chmod(0o600)
    detail.write_text("".join(json.dumps(x) + chr(10) for x in original))
    receipt_path = example["output"] / "receipt.json"
    receipt_path.chmod(0o600)
    receipt = json.loads(receipt_path.read_text())
    receipt["files"]["private_issuer_rows.jsonl"]["sha256"] = _sha(detail)
    receipt["files"]["private_issuer_rows.jsonl"]["bytes"] = detail.stat().st_size
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="per-issuer"):
        _independent(example)
