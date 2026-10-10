"""Record recovered research reviews without enlarging their declared scope.

An explicit prior user verdict is evidence, even when its exact message time is
unavailable. This module preserves that uncertainty instead of manufacturing a
timestamp or promoting a packet-arithmetic check into source/identity approval.
"""

import io
import json
import math
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

from .audit import cached_body, load_reviews, select_review_pairs
from .extraction import clean_html
from .market_data import sha256
from .pilot_audit import MEASURES, require

ARCHIVE_PREFIX = "M5-Review-Followup/"
USER_REVIEW_SCOPE = ["controls_arithmetic", "label_arithmetic", "packet_timing_and_structure"]


def _jsonl(raw):
    return [json.loads(line) for line in raw.decode().splitlines() if line.strip()]


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def _stamp(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(stamp.tzinfo is not None, "A known review timestamp must include a timezone")
    require(stamp <= datetime.now(timezone.utc), "Review timestamp is in the future")
    return stamp


def verify_recheck_results(results, traces):
    """Bind every reported pass to one exact selected trace and seven measures."""
    expected = {(row["event_id"], row["evidence_id"]) for row in traces}
    observed = [(row["event_id"], row["evidence_id"]) for row in results]
    require(len(expected) == len(traces) == 20, "Expected the original fixed 20 traces")
    require(len(observed) == len(set(observed)) == 20 and set(observed) == expected,
            "Recheck event/evidence set differs or contains duplicate traces")
    for row in results:
        require(row.get("issues") == [], "A submitted trace has issues")
        diffs = row.get("diffs", {})
        require(set(diffs) == set(MEASURES), "Recheck measures differ")
        require(all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) and 0 <= v <= 1e-12 for v in diffs.values()),
                "Recheck difference is invalid or exceeds the observed strict tolerance")
        require(row.get("max_diff") == max(diffs.values()), "Reported maximum difference is inconsistent")
    return max(row["max_diff"] for row in results)


def record_user_arithmetic_review(archive, packet, statement, output, reproduced_results=None):
    """Record a supplied explicit USER verdict against an unchanged old packet.

    ``statement`` is a JSON path containing the actual prior user message and
    its provenance. Unknown original review time stays null. Outputs deliberately
    use scoped verdict fields and cannot be mistaken for the broader legacy
    source-trace review import. This function never executes the supplied script.
    """
    archive, packet, statement, output = map(Path, (archive, packet, statement, output))
    require(not output.exists(), "Preserve the previous review record; use a new output")
    statement_raw = statement.read_bytes()
    declared = json.loads(statement_raw)
    require(declared.get("reviewer_type") == "human" and declared.get("verdict") == "pass",
            "An explicit prior human pass declaration is required")
    require(declared.get("scope") == USER_REVIEW_SCOPE, "User review scope must remain packet arithmetic/timing")
    require(all(isinstance(declared.get(k), str) and declared[k].strip()
                for k in ("reviewer", "statement", "source_kind", "source_reference")),
            "Preserve the user statement, reviewer and message provenance")
    require(declared["source_kind"] == "prior_user_message", "Use the actual user message as the verdict source")
    known_time = declared.get("original_reviewed_at")
    if known_time is not None:
        _stamp(known_time)
    required = ["followup_summary.json", "original_fixed20/audit_summary.json",
                "original_fixed20/review.html", "original_fixed20/independent_traces.jsonl",
                "original_fixed20/trace_reviews.template.jsonl", "user_recheck_results.json",
                "user_submission/pilot-recheck.py", "user_submission/review-verdicts-DRAFT.jsonl"]
    with ZipFile(archive) as z:
        require(len(z.namelist()) == len(set(z.namelist())), "Duplicate archive members")
        manifest_raw = z.read(ARCHIVE_PREFIX + "delivery_manifest.json")
        manifest = json.loads(manifest_raw)
        payloads = {}
        for name in required:
            raw = z.read(ARCHIVE_PREFIX + name)
            require(manifest.get(name) == {"bytes": len(raw), "sha256": sha256(raw)},
                    f"Submitted archive member changed: {name}")
            payloads[name] = raw
    receipt_raw = (packet / "audit_summary.json").read_bytes()
    require(receipt_raw == payloads["original_fixed20/audit_summary.json"],
            "Local packet is not the user's reviewed packet")
    receipt = json.loads(receipt_raw)
    for name, digest in receipt["files"].items():
        require(Path(name).name == name and sha256((packet / name).read_bytes()) == digest,
                f"Original packet changed: {name}")
    for name in ("review.html", "independent_traces.jsonl", "trace_reviews.template.jsonl"):
        require(payloads[f"original_fixed20/{name}"] == (packet / name).read_bytes(),
                f"Submitted and local packet evidence differ: {name}")
    traces = _jsonl(payloads["original_fixed20/independent_traces.jsonl"])
    results = json.loads(payloads["user_recheck_results.json"])
    maximum = verify_recheck_results(results, traces)
    followup = json.loads(payloads["followup_summary.json"])
    require(followup["original_arithmetic_receipt_sha256"] == sha256(receipt_raw),
            "Follow-up receipt is bound to a different original packet")
    require(followup["submitted_recheck"]["results_sha256"] == sha256(payloads["user_recheck_results.json"]),
            "Saved review result differs from its earlier follow-up receipt")
    require(followup["submitted_recheck"]["submitted_draft_sha256"] ==
            sha256(payloads["user_submission/review-verdicts-DRAFT.jsonl"]), "Submitted draft changed")
    draft = _jsonl(payloads["user_submission/review-verdicts-DRAFT.jsonl"])
    require([(r["event_id"], r["evidence_id"]) for r in draft] ==
            [(r["event_id"], r["evidence_id"]) for r in results], "Draft and reported result order differs")
    require(all(r["controls_verdict"] == r["label_verdict"] == "pending" for r in draft),
            "The original draft must be preserved as originally pending")
    if reproduced_results is not None:
        repeated = json.loads(Path(reproduced_results).read_bytes())
        verify_recheck_results(repeated, traces)
        require(repeated == results, "Reproduced script output differs from the saved user result")
    recorded_at = datetime.now(timezone.utc).isoformat()
    statement_hash = sha256(statement_raw)
    reviews = []
    for result in results:
        reviews.append({"event_id": result["event_id"], "evidence_id": result["evidence_id"],
                        "reviewer": declared["reviewer"], "reviewer_type": "human",
                        "scope": USER_REVIEW_SCOPE, "controls_arithmetic_verdict": "pass",
                        "label_arithmetic_verdict": "pass", "packet_structure_verdict": "pass",
                        "original_reviewed_at": known_time, "original_review_time_unknown": known_time is None,
                        "recorded_at": recorded_at, "recorded_by": "assistant",
                        "user_statement_sha256": statement_hash,
                        "source_references": [declared["source_reference"],
                                              "sha256:" + sha256(payloads["original_fixed20/review.html"]),
                                              "sha256:" + sha256(payloads["user_submission/pilot-recheck.py"])],
                        "observed_max_abs_difference": result["max_diff"],
                        "raw_csv_review_verdict": "not_declared",
                        "historical_identity_verdict": "not_declared",
                        "vendor_release_availability_verdict": "not_declared",
                        "filing_boundary_verdict": "not_declared"})
    summary = {"schema_version": 1, "status": "prior_user_packet_review_recorded",
               "user_arithmetic_and_packet_timing_passes": len(reviews),
               "observed_max_abs_error": maximum, "reviewer_type": "human",
               "original_reviewed_at": known_time, "original_review_time_unknown": known_time is None,
               "recorded_at": recorded_at, "recorded_by": "assistant",
               "assistant_reproduction_matches_saved_results": reproduced_results is not None,
               "original_pending_draft_preserved": True,
               "legacy_full_source_trace_review_imported": False,
               "new_human_raw_source_reviews": 0, "new_human_identity_reviews": 0,
               "new_human_filing_reviews": 0, "source_release_approved": False,
               "model_ready": False, "final_period_opened": False,
               "bindings": {"archive_sha256": sha256(archive.read_bytes()),
                            "delivery_manifest_sha256": sha256(manifest_raw),
                            "original_packet_sha256": sha256(receipt_raw),
                            "user_statement_sha256": statement_hash,
                            **{name: sha256(raw) for name, raw in payloads.items()}},
               "review_code_sha256": sha256(Path(__file__).read_bytes())}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".review-record-", dir=output.parent) as temporary:
        stage = Path(temporary) / "record"
        stage.mkdir()
        (stage / "user_statement.json").write_bytes(statement_raw)
        for name in ("user_recheck_results.json", "user_submission/pilot-recheck.py",
                     "user_submission/review-verdicts-DRAFT.jsonl"):
            (stage / Path(name).name).write_bytes(payloads[name])
        (stage / "user_arithmetic_reviews.recorded.jsonl").write_text(
            "".join(json.dumps(row, allow_nan=False) + "\n" for row in reviews))
        summary["files"] = {p.name: sha256(p.read_bytes()) for p in sorted(stage.iterdir())}
        _write_json(stage / "review_receipt.json", summary)
        require(not output.exists(), "Output appeared while recording review")
        stage.rename(output)
    return summary


def independent_header_clock(row, cache):
    """Read original SGML and derive sessions without the project's clock helper."""
    raw = cached_body(Path(cache), row["header_url"], row["header_sha256"])
    matches = re.findall(rb"<ACCEPTANCE-DATETIME>\s*(\d{14})", raw)
    require(len(matches) == 1, "Original header acceptance timestamp is ambiguous")
    accepted = datetime.strptime(matches[0].decode(), "%Y%m%d%H%M%S").replace(
        tzinfo=ZoneInfo("America/New_York"))
    require(accepted.year <= 2021, "This review must not open final-period events")
    calendar = xcals.get_calendar("XNYS", start="2000-01-01", end="2027-12-31")
    sessions = calendar.sessions_in_range(accepted.date(), accepted.date() + timedelta(days=70))
    after = [s for s in sessions if s.date() > accepted.date()]
    reference = after[1]
    controls = calendar.previous_session(reference)
    end = calendar.session_offset(reference, 20)
    expected = {"acceptance_timestamp": accepted.isoformat(),
                "reference_session": reference.date().isoformat(),
                "controls_through": controls.date().isoformat(), "label_end": end.date().isoformat()}
    require(all(str(row[key]) == value for key, value in expected.items()),
            "Stored event clock differs from independent original-header calculation")
    api = datetime.fromisoformat(str(row["api_timestamp"]).replace("Z", "+00:00"))
    require(api.tzinfo is not None, "API timestamp is naive")
    delta = (api - accepted).total_seconds()
    return {"accession": row["accession"], "evidence_id": row["evidence_id"], **expected,
            "header_url": row["header_url"], "header_sha256": row["header_sha256"],
            "api_timestamp": row["api_timestamp"], "api_minus_header_seconds": delta,
            "api_difference_equals_local_utc_offset": delta == -accepted.utcoffset().total_seconds(),
            "source_clock_pass": True, "reviewer_type": "assistant",
            "public_dissemination_verified": False}


def inspect_names_query(query_path, names_path):
    """Document a supplied query and reconcile its selector with its supplied CSV."""
    query_raw, names_raw = Path(query_path).read_bytes(), Path(names_path).read_bytes()
    query = query_raw.decode()
    require("crsp_a_stock.wrds_names_query" in query, "Unexpected supplied Names source")
    selected = set(re.findall(r"'([0-9]+)'", query))
    names = pd.read_csv(io.BytesIO(names_raw), dtype=str, keep_default_na=False)
    require(selected and selected == set(names.permno), "Query identifiers differ from supplied Names rows")
    projected = re.findall(r"crsp_a_stock\.wrds_names_query\.([a-z]+)", query.split("FROM", 1)[0])
    require(projected == names.columns.tolist(), "Query projection differs from supplied Names columns")
    return {"source_table": "crsp_a_stock.wrds_names_query", "query_sha256": sha256(query_raw),
            "names_sha256": sha256(names_raw), "query_security_ids": len(selected),
            "source_rows": len(names), "columns": projected, "query_csv_selector_and_columns_match": True,
            "query_execution_independently_verified": False, "source_release_verified": False,
            "point_in_time_availability_verified": False, "reviewer_type": "assistant"}


def build_assistant_source_progress(root, reviews_path, output):
    """Revalidate explicitly recorded assistant boundary decisions and all clocks.

    The deterministic 30-pair selection and all registered reference resolutions
    are retained. This is additional source investigation, not human sign-off.
    """
    root, reviews_path, output = map(Path, (root, reviews_path, output))
    require(not output.exists(), "Preserve the previous source-review output")
    original = root / "outputs/audit-pilot-resolved"
    receipt_raw = (original / "audit_summary.json").read_bytes()
    receipt = json.loads(receipt_raw)
    evidence_raw = (original / "filing_evidence.parquet").read_bytes()
    filings_raw = (root / "data/processed/pilot-resolved/filings.parquet").read_bytes()
    pairs_raw = (root / "data/processed/pilot-resolved/filing_pairs.parquet").read_bytes()
    require(sha256(evidence_raw) == receipt["evidence_table_sha256"] and
            sha256(filings_raw) == receipt["source_table_sha256"] and
            sha256(pairs_raw) == receipt["pair_table_sha256"], "Original source audit changed")
    dates = pd.read_parquet(io.BytesIO(filings_raw), columns=["acceptance_date"]).acceptance_date
    require(dates.str[:4].astype(int).le(2021).all(), "Review accepts development filings only")
    evidence = pd.read_parquet(io.BytesIO(evidence_raw)).set_index("accession", drop=False)
    filings = pd.read_parquet(io.BytesIO(filings_raw)).set_index("accessionNumber")
    selected_raw = (root / "reports/expanded_review_pairs.csv").read_bytes()
    selected = pd.read_csv(io.BytesIO(selected_raw), dtype=str)
    expected = select_review_pairs(pd.read_parquet(io.BytesIO(pairs_raw)))
    selection_keys = ["cik", "accession", "previous_accession", "acceptance_date", "source_url", "previous_source_url"]
    require(selected[selection_keys].reset_index(drop=True).equals(
        expected[selection_keys].reset_index(drop=True)), "Fixed filing-pair selection changed")
    sample_ids = set(selected.accession) | set(selected.previous_accession)
    reference_ids = set(evidence.loc[evidence.resolution_method.ne("numbered_item1a")].index)
    reviews = load_reviews(reviews_path)
    require(set(reviews) == sample_ids | reference_ids,
            "Review set must retain the fixed sample and all registered reference cases")
    require(all(r["reviewer_type"] == "assistant" for r in reviews.values()),
            "This investigation must be attributed to the assistant")
    clocks, boundaries, continued = [], [], []
    cache = root / "data/raw/sec_cache"
    for row in evidence.to_dict("records"):
        clocks.append(independent_header_clock(row, cache))
        raw = cached_body(cache, row["risk_source_url"], row["risk_source_sha256"])
        normalized = clean_html(raw)
        occurrences = list(re.finditer(
            r"(?i)\bitem\s*1\s*a\s*[.\-:–—]*\s*risk\s+factors\s*\(\s*continued\s*\)", normalized))
        if occurrences:
            continued.append({"accession": row["accession"], "evidence_id": row["evidence_id"],
                              "source_url": row["risk_source_url"],
                              "offsets": [match.start() for match in occurrences]})
        if row["accession"] not in reviews:
            continue
        review = reviews[row["accession"]]
        _stamp(review["reviewed_at"])
        require(review["evidence_id"] == row["evidence_id"], "Assistant review evidence is stale")
        require(review["boundary_verdict"] == review["timing_verdict"] == "pass",
                "This record of completed inspections cannot discard a failed or pending review")
        require(set(review.get("source_references", [])) >= {row["source_url"], row["header_url"], row["risk_source_url"]},
                "Assistant review must cite the inspected original sources")
        cached_body(cache, row["source_url"], row["download_sha256"])
        if row["resolution_index_url"]:
            cached_body(cache, row["resolution_index_url"], row["resolution_index_sha256"])
        start, end = int(row["extraction_start"]), int(row["extraction_end"])
        require(0 <= start < end <= len(normalized), "Invalid source boundaries")
        # Both frozen extractors trim this boundary punctuation after slicing.
        # Preserve that declared operation; do not alter internal source text.
        inspected_text = normalized[start:end].strip(" .:-\n")
        require(" ".join(inspected_text.split()) ==
                " ".join(filings.loc[row["accession"], "risk_text"].split()),
                "Stored risk text differs from the inspected source span")
        boundaries.append({**review, "resolution_method": row["resolution_method"],
                           "source_sha256": row["risk_source_sha256"],
                           "start_offset": start, "end_offset": end,
                           "source_start_context": normalized[max(0, start - 160):start + 260],
                           "source_end_context": normalized[max(start, end - 260):end + 160],
                           "source_span_matches_stored_text": True,
                           "declared_boundary_trim_characters": " .:-\n",
                           "table_of_contents_phrases_retained": len(re.findall(
                               r"(?i)\btable of contents\b", normalized[start:end])),
                           "human_review": False})
    differences = pd.Series([c["api_minus_header_seconds"] for c in clocks]).value_counts()
    summary = {"schema_version": 1, "status": "assistant_source_review_completed_human_gates_unchanged",
               "original_filings_checked": len(clocks), "original_header_clocks_passed": len(clocks),
               "api_header_difference_seconds_counts": {str(int(k)): int(v) for k, v in differences.items()},
               "nonzero_api_differences_match_local_utc_offset": all(
                   c["api_difference_equals_local_utc_offset"] for c in clocks if c["api_minus_header_seconds"]),
               "fixed_review_pairs": len(selected), "fixed_sample_distinct_filings": len(sample_ids),
               "registered_reference_filings_reviewed": len(reference_ids),
               "assistant_filing_reviews_completed": len(boundaries),
               "explicit_continued_heading_filings": len(continued),
               "human_filing_reviews_added": 0, "public_dissemination_verified": False,
               "historical_identity_approved": False, "source_release_approved": False,
               "full_universe_representativeness_established": False,
               "model_ready": False, "final_period_opened": False,
               "bindings": {"original_audit_receipt": sha256(receipt_raw),
                            "original_filing_evidence": sha256(evidence_raw),
                            "filing_table": sha256(filings_raw), "pair_table": sha256(pairs_raw),
                            "fixed_pair_selection": sha256(selected_raw),
                            "assistant_review_decisions": sha256(reviews_path.read_bytes()),
                            "generator": sha256(Path(__file__).read_bytes())}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".source-review-", dir=output.parent) as temporary:
        stage = Path(temporary) / "review"
        stage.mkdir()
        for name, records in (("header_clock_checks.jsonl", clocks),
                              ("assistant_filing_reviews.jsonl", boundaries),
                              ("continued_heading_cases.jsonl", continued)):
            (stage / name).write_text("".join(json.dumps(row, allow_nan=False) + "\n" for row in records))
        summary["files"] = {p.name: sha256(p.read_bytes()) for p in sorted(stage.iterdir())}
        _write_json(stage / "source_review_receipt.json", summary)
        require(not output.exists(), "Output appeared while recording source review")
        stage.rename(output)
    return summary
