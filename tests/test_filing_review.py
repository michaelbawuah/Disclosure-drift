"""Synthetic end-to-end review evidence, without creating production approvals."""

import copy
import hashlib
import json
from dataclasses import asdict

import httpx
import pandas as pd
import pyarrow.parquet as pq
import pytest

from disclosure_research.audit import build_audit, load_reviews
from disclosure_research.edgar import SecClient
from disclosure_research.extraction import pair_filings
from disclosure_research.protocol import load_protocol
from disclosure_research.references import resolve_section
from disclosure_research.timing import acceptance_from_header, event_window


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path):
    return json.loads(path.read_text())


def _make_inputs(root):
    """Three original documents produce two pairs sharing the 2018 accession."""
    responses = {}
    cache = root / "cache"
    client = SecClient(cache, "Synthetic tests fixture@example.test", sleep=lambda _: None,
                       transport=httpx.MockTransport(lambda request: httpx.Response(
                           200, content=responses[str(request.url)])))
    records = []
    for year in (2017, 2018, 2019):
        accession = f"0000000123-{year % 100:02d}-000001"
        directory = f"https://www.sec.gov/Archives/edgar/data/123/{accession.replace('-', '')}"
        source, header_url = f"{directory}/annual.htm", f"{directory}/header.sgml"
        raw = ("<h2>Item 1A. Risk Factors</h2><p>" + f"supply competition year{year} " * 120
               + "</p><h2>Item 1B. Unresolved Staff Comments</h2><p>None.</p>").encode()
        header = f"<ACCEPTANCE-DATETIME>{year}0301100000".encode()
        responses.update({source: raw, header_url: header})
        _, body_meta = client.fetch(source)
        _, header_meta = client.fetch(header_url)
        accepted = acceptance_from_header(header.decode())
        window = event_window(accepted)
        resolved = resolve_section(raw, source, accession, {})
        extracted = resolved.extraction
        assert extracted.status == "ok"
        records.append({
            "accessionNumber": accession, "cik": "0000000123",
            "name": "Synthetic <script>company</script>", "form": "10-K",
            "filingDate": f"{year}-03-01", "reportDate": f"{year - 1}-12-31",
            "source_url": source, "header_url": header_url,
            "download_sha256": body_meta["sha256"], "header_sha256": header_meta["sha256"],
            "risk_text": extracted.text, "risk_token_count": extracted.token_count,
            "extraction_version": extracted.version, "extraction_status": extracted.status,
            "acceptance_timestamp": accepted.isoformat(),
            "acceptanceDateTime": f"{year}-03-01T15:00:00Z",
            **resolved.provenance(),
            **{k: v for k, v in asdict(window).items() if k != "return_sessions"},
        })
    filings = root / "filings.parquet"
    pairs_path = root / "filing_pairs.parquet"
    pd.DataFrame(records).to_parquet(filings, index=False)
    pairs, _ = pair_filings(records, 2018, 2021)
    assert len(pairs) == 2
    pd.DataFrame(pairs).to_parquet(pairs_path, index=False)
    audit_dir = root / "audit"
    summary = build_audit(filings, cache, audit_dir, 2021, pairs=pairs_path)
    assert summary["automated_evidence_ok"] == 3
    assert summary["human_reviews_complete"] == 0
    return {
        "cache": cache, "root": root,
        "kwargs": {
            "filings_path": filings, "pairs_path": pairs_path, "audit_dir": audit_dir,
            "audit_summary_sha256": _sha(audit_dir / "audit_summary.json"),
            "selected_pairs_path": audit_dir / "review_pairs.csv",
            "selected_pairs_sha256": _sha(audit_dir / "review_pairs.csv"),
            "output_dir": root / "review-app", "config": load_protocol(),
        },
    }


@pytest.fixture
def review_inputs(tmp_path):
    return _make_inputs(tmp_path)


def _build(inputs, **overrides):
    from disclosure_research.filing_review import build_filing_review

    return build_filing_review(**{**inputs["kwargs"], **overrides})


def _packet(inputs):
    return _json(inputs["kwargs"]["output_dir"] / "packet.json")


def _validate(packet, path):
    from disclosure_research.filing_review import validate_filing_reviews

    return validate_filing_reviews(packet, path)


def _review_rows(packet, reviewer_type="human"):
    return [{
        "accession": row["accession"], "evidence_id": row["evidence_id"],
        "reviewer": "Synthetic fixture reviewer", "reviewer_type": reviewer_type,
        "reviewed_at": "2020-06-01T12:00:00+00:00",
        "boundary_verdict": "pass", "timing_verdict": "pass",
        "notes": "Artificial fixture only; no real filing or production review was approved.",
    } for row in packet["filings"]]


def _export(inputs, rows):
    path = inputs["root"] / "fixture-reviews.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


def _table(inputs, role):
    if role == "evidence":
        return inputs["kwargs"]["audit_dir"] / "filing_evidence.parquet"
    return inputs["kwargs"][f"{role}_path"]


def _rebind_table(inputs, role):
    """Explicitly repin containers, forcing tests to reach semantic checks."""
    summary_path = inputs["kwargs"]["audit_dir"] / "audit_summary.json"
    summary = _json(summary_path)
    key = {"filings": "source_table_sha256", "pairs": "pair_table_sha256",
           "evidence": "evidence_table_sha256"}[role]
    summary[key] = _sha(_table(inputs, role))
    summary_path.write_text(json.dumps(summary) + "\n")
    inputs["kwargs"]["audit_summary_sha256"] = _sha(summary_path)


def _reaudit(inputs, reviews):
    return build_audit(inputs["kwargs"]["filings_path"], inputs["cache"],
                       inputs["root"] / "reviewed-source-audit", 2021,
                       reviews=reviews, pairs=inputs["kwargs"]["pairs_path"])


def _forbid_text_reads(monkeypatch):
    """Observe public Pandas/Arrow reads, not an implementation preflight helper."""
    text_columns = {"risk_text", "current_text", "previous_text", "start_context",
                    "section_start", "section_end", "end_context"}
    reads = []

    def wrap(function, method=False):
        def guarded(*args, **kwargs):
            columns = kwargs.get("columns", args[1] if method and len(args) > 1 else None)
            assert columns is not None and not text_columns.intersection(columns), (
                "Full/text-bearing Parquet data was read before rejecting the input")
            reads.append(tuple(columns))
            return function(*args, **kwargs)
        return guarded

    monkeypatch.setattr(pd, "read_parquet", wrap(pd.read_parquet))
    monkeypatch.setattr(pq, "read_table", wrap(pq.read_table))
    monkeypatch.setattr(pq.ParquetFile, "read", wrap(pq.ParquetFile.read, method=True))
    return reads


def test_packet_preserves_frozen_pairs_text_and_one_record_per_accession(review_inputs):
    receipt = _build(review_inputs)
    out = review_inputs["kwargs"]["output_dir"]
    assert {"index.html", "packet.json", "receipt.json", "selected_pairs.csv"} <= {
        path.name for path in out.iterdir()}
    assert (out / "selected_pairs.csv").read_bytes() == (
        review_inputs["kwargs"]["selected_pairs_path"].read_bytes())
    packet = _packet(review_inputs)
    assert packet["summary"] == {"selected_pairs": 2, "selected_filings": 3,
                                 "reference_filings": 0, "distinct_filings": 3,
                                 "source_filings": 3}
    assert receipt == _json(out / "receipt.json")
    for item in receipt["files"]:
        assert item["sha256"] == _sha(out / item["file"])
        assert item["bytes"] == (out / item["file"]).stat().st_size
    for document in (packet, receipt):
        assert document["model_ready"] is document["final_period_opened"] is False
        assert document["original_sec_bytes_reread"] is False
        assert document["prior_arithmetic_review_modified"] is False
        assert document["source_approvals"] == document["human_reviews_created"] == 0
        assert document["source_bindings"]["audit_summary"]["sha256"] == (
            review_inputs["kwargs"]["audit_summary_sha256"])
        for role in ("filings", "pairs", "evidence"):
            assert document["source_bindings"][role]["sha256"] == _sha(_table(review_inputs, role))
    accessions = [row["accession"] for row in packet["filings"]]
    assert len(accessions) == len(set(accessions)) == 3
    assert {p["previous_accession"] for p in packet["pairs"]} & {
        p["accession"] for p in packet["pairs"]} == {"0000000123-18-000001"}
    original = pd.read_parquet(review_inputs["kwargs"]["filings_path"]).set_index("accessionNumber")
    evidence = pd.read_parquet(_table(review_inputs, "evidence")).set_index("accession")
    for row in packet["filings"]:
        assert row["risk_text"] == original.loc[row["accession"], "risk_text"]
        assert row["evidence_id"] == evidence.loc[row["accession"], "evidence_id"]
        assert row["source_url"] == original.loc[row["accession"], "source_url"]


def test_shared_fingerprints_preserve_the_pre_bridge_audit_contract(review_inputs):
    # Produced from this fixture by audit.py at 3a5b368, before extracting the
    # shared helper. Fixed outputs catch a synchronized change in both consumers.
    expected = {
        "0000000123-17-000001": "86648fef7dd2e125006804b9df2848d0a07a779cc9074db58dc019bd9c46d689",
        "0000000123-18-000001": "cfcefd4d08084e45ebb7ca1a183e671cb7a349e2c191efec2ea2ee1f89a1b811",
        "0000000123-19-000001": "19b4f1e982d1a415263617d93473b020103e273cbe68daab6165abc0772a8f36",
    }
    _build(review_inputs)
    assert {row["accession"]: row["evidence_id"] for row in _packet(review_inputs)["filings"]} == expected


@pytest.mark.parametrize("reviewer_type", ["human", "assistant"])
def test_export_roundtrip_uses_existing_review_loader_and_source_audit(review_inputs, reviewer_type):
    _build(review_inputs)
    packet = _packet(review_inputs)
    rows = _review_rows(packet, reviewer_type)
    reviews = _export(review_inputs, rows)
    validation = _validate(packet, reviews)
    assert validation["records"] == 3
    assert validation["human_reviews_declared_complete"] == (3 if reviewer_type == "human" else 0)
    assert validation["assistant_reviews_declared_complete"] == (3 if reviewer_type == "assistant" else 0)
    assert validation["partial_reviews"] == validation["failed_reviews"] == 0
    assert validation["original_sec_bytes_reread"] is False
    assert validation["model_ready"] is validation["final_period_opened"] is False
    assert validation["source_approvals"] == 0
    assert load_reviews(reviews) == {row["accession"]: row for row in rows}
    audited = _reaudit(review_inputs, reviews)
    assert audited["human_reviews_complete"] == (3 if reviewer_type == "human" else 0)
    assert audited["assistant_reviews_complete"] == (3 if reviewer_type == "assistant" else 0)
    assert audited["manual_audit"] == ("complete" if reviewer_type == "human" else "pending")


def test_valid_declarations_cannot_bypass_a_later_original_source_hash_failure(review_inputs):
    _build(review_inputs)
    packet = _packet(review_inputs)
    reviews = _export(review_inputs, _review_rows(packet))
    url = packet["filings"][0]["source_url"]
    cached = review_inputs["cache"] / (hashlib.sha256(url.encode()).hexdigest() + ".bin")
    cached.write_bytes(b"Changed after the packet was created")
    declaration = _validate(packet, reviews)
    assert declaration["human_reviews_declared_complete"] == 3
    assert declaration["original_sec_bytes_reread"] is False
    assert declaration["source_approvals"] == 0
    audited = _reaudit(review_inputs, reviews)
    assert audited["human_reviews_complete"] == 2
    assert audited["filings_with_blocking_issues"] == 1
    assert audited["manual_audit"] == "pending"


@pytest.mark.parametrize("verdict, partial, failed", [("pending", 1, 0), ("fail", 0, 1)])
def test_partial_and_failed_reviews_never_count_as_complete(review_inputs, verdict, partial, failed):
    _build(review_inputs)
    packet = _packet(review_inputs)
    rows = _review_rows(packet)
    rows[0]["timing_verdict"] = verdict
    reviews = _export(review_inputs, rows)
    validation = _validate(packet, reviews)
    assert validation["human_reviews_declared_complete"] == 2
    assert validation["partial_reviews"] == partial
    assert validation["failed_reviews"] == failed
    audited = _reaudit(review_inputs, reviews)
    assert audited["human_reviews_complete"] == 2
    assert audited["filings_with_blocking_issues"] == failed
    assert audited["manual_audit"] == "pending"


def test_packet_output_cannot_overwrite_an_existing_review_directory(review_inputs):
    _build(review_inputs)
    out = review_inputs["kwargs"]["output_dir"]
    before = {path.name: path.read_bytes() for path in out.iterdir() if path.is_file()}
    with pytest.raises(ValueError):
        _build(review_inputs)
    assert before == {path.name: path.read_bytes() for path in out.iterdir() if path.is_file()}


@pytest.mark.parametrize("role", ["filings", "pairs", "evidence"])
def test_changed_table_bytes_cannot_reuse_the_audit_binding(review_inputs, role):
    path = _table(review_inputs, role)
    path.write_bytes(path.read_bytes() + b"changed bytes")
    with pytest.raises(ValueError):
        _build(review_inputs)
    assert not review_inputs["kwargs"]["output_dir"].exists()


def test_audit_summary_itself_requires_the_supplied_exact_hash(review_inputs):
    path = review_inputs["kwargs"]["audit_dir"] / "audit_summary.json"
    summary = _json(path)
    summary["manual_audit"] = "unjustified replacement"
    path.write_text(json.dumps(summary))
    with pytest.raises(ValueError):
        _build(review_inputs)
    assert not review_inputs["kwargs"]["output_dir"].exists()


@pytest.mark.parametrize("change", ["stale_pin", "reordered_and_repinned"])
def test_frozen_pair_selection_cannot_be_replaced(review_inputs, change):
    path = review_inputs["kwargs"]["selected_pairs_path"]
    if change == "stale_pin":
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        selected = pd.read_csv(path, dtype=str, keep_default_na=False)
        selected.iloc[::-1].to_csv(path, index=False)
        review_inputs["kwargs"]["selected_pairs_sha256"] = _sha(path)
    with pytest.raises(ValueError):
        _build(review_inputs)
    assert not review_inputs["kwargs"]["output_dir"].exists()


@pytest.mark.parametrize("field,value", [
    ("risk_text", "Text that was never present in the independently audited source."),
    ("risk_source_sha256", "0" * 64),
    ("normalizer_version", "unregistered-normalizer"),
    ("extraction_end", 999999),
])
def test_repinned_filing_bytes_still_require_audited_text_and_provenance(review_inputs, field, value):
    path = _table(review_inputs, "filings")
    frame = pd.read_parquet(path)
    frame.loc[0, field] = value
    frame.to_parquet(path, index=False)
    _rebind_table(review_inputs, "filings")
    with pytest.raises(ValueError):
        _build(review_inputs)
    assert not review_inputs["kwargs"]["output_dir"].exists()


def test_repinned_evidence_table_must_recompute_its_legacy_fingerprint(review_inputs):
    path = _table(review_inputs, "evidence")
    frame = pd.read_parquet(path)
    frame.loc[0, "evidence_id"] = "0" * 64
    frame.to_parquet(path, index=False)
    _rebind_table(review_inputs, "evidence")
    with pytest.raises(ValueError):
        _build(review_inputs)
    assert not review_inputs["kwargs"]["output_dir"].exists()


def test_source_mutation_during_construction_cannot_publish_a_stale_packet(review_inputs, monkeypatch):
    source = review_inputs["kwargs"]["filings_path"]
    original = pq.read_table
    mutated = []

    def read(*args, **kwargs):
        result = original(*args, **kwargs)
        if not mutated:
            source.write_bytes(source.read_bytes() + b"changed during construction")
            mutated.append(True)
        return result

    monkeypatch.setattr(pq, "read_table", read)
    with pytest.raises(ValueError):
        _build(review_inputs)
    assert mutated == [True]
    assert not review_inputs["kwargs"]["output_dir"].exists()


@pytest.mark.parametrize("role", ["filings", "pairs", "evidence"])
def test_unexpected_market_column_is_rejected_before_text_materialization(review_inputs, monkeypatch, role):
    path = _table(review_inputs, role)
    frame = pd.read_parquet(path)
    frame["target"] = 0.123456789
    frame.to_parquet(path, index=False)
    _rebind_table(review_inputs, role)
    _forbid_text_reads(monkeypatch)
    with pytest.raises(ValueError):
        _build(review_inputs)
    assert not review_inputs["kwargs"]["output_dir"].exists()


@pytest.mark.parametrize("role,field,value", [
    ("filings", "acceptance_date", "2022-03-01"),
    ("filings", "acceptance_date", "2009-03-01"),
    ("filings", "acceptance_timestamp", "2022-03-01T10:00:00-05:00"),
    ("pairs", "previous_acceptance_date", "2022-03-01"),
    ("evidence", "acceptance_timestamp", "2022-03-01T10:00:00-05:00"),
])
def test_all_source_dates_are_checked_before_any_full_text_read(review_inputs, monkeypatch, role, field, value):
    path = _table(review_inputs, role)
    frame = pd.read_parquet(path)
    frame.loc[len(frame) - 1, field] = value
    frame.to_parquet(path, index=False)
    _rebind_table(review_inputs, role)
    _forbid_text_reads(monkeypatch)
    with pytest.raises(ValueError):
        _build(review_inputs)
    assert not review_inputs["kwargs"]["output_dir"].exists()


@pytest.mark.parametrize("change", ["unknown_accession", "stale_evidence", "pending_only",
                                    "naive_timestamp", "future_timestamp", "extra_field", "duplicate",
                                    "missing_reviewer", "blank_notes"])
def test_review_import_rejects_unbound_or_unauthored_records(review_inputs, change):
    _build(review_inputs)
    packet = _packet(review_inputs)
    rows = _review_rows(packet)
    if change == "unknown_accession":
        rows[0]["accession"] = "0000000456-19-000001"
    elif change == "stale_evidence":
        rows[0]["evidence_id"] = "0" * 64
    elif change == "pending_only":
        rows[0].update(boundary_verdict="pending", timing_verdict="pending")
    elif change == "naive_timestamp":
        rows[0]["reviewed_at"] = "2020-06-01T12:00:00"
    elif change == "future_timestamp":
        rows[0]["reviewed_at"] = "2999-01-01T00:00:00+00:00"
    elif change == "extra_field":
        rows[0]["source_approved"] = True
    elif change == "missing_reviewer":
        rows[0]["reviewer"] = ""
    elif change == "blank_notes":
        rows[0]["notes"] = "  "
    else:
        rows = [rows[0], copy.deepcopy(rows[0])]
    with pytest.raises(ValueError):
        _validate(packet, _export(review_inputs, rows))


def test_review_import_recomputes_packet_id_after_embedded_text_tampering(review_inputs):
    _build(review_inputs)
    packet = _packet(review_inputs)
    reviews = _export(review_inputs, _review_rows(packet))
    packet["filings"][0]["risk_text"] += " changed after the packet was bound"
    with pytest.raises(ValueError):
        _validate(packet, reviews)


def test_pending_reference_template_reuses_shared_accession_without_signoff(review_inputs):
    template = review_inputs["kwargs"]["audit_dir"] / "reviews.template.jsonl"
    rows = [json.loads(line) for line in template.read_text().splitlines()][:2]
    for row in rows:
        row["reviewer_type"] = ""
    path = review_inputs["root"] / "reference.pending.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    _build(review_inputs, reference_template_path=path, reference_template_sha256=_sha(path))
    packet = _packet(review_inputs)
    assert packet["summary"] == {"selected_pairs": 2, "selected_filings": 3,
                                 "reference_filings": 2, "distinct_filings": 3,
                                 "source_filings": 3}
    assert len({row["accession"] for row in packet["filings"]}) == 3
    reference_accessions = {row["accession"] for row in rows}
    for row in packet["filings"]:
        expected = {"fixed_pair", "reference"} if row["accession"] in reference_accessions else {"fixed_pair"}
        assert set(row["scope_tags"]) == expected
    assert packet["source_approvals"] == packet["human_reviews_created"] == 0


@pytest.mark.parametrize("change", ["stale_pin", "stale_evidence", "unknown_accession", "completed", "duplicate"])
def test_reference_templates_cannot_change_evidence_or_supply_approvals(review_inputs, change):
    template = review_inputs["kwargs"]["audit_dir"] / "reviews.template.jsonl"
    rows = [json.loads(line) for line in template.read_text().splitlines()][:1]
    if change == "stale_evidence":
        rows[0]["evidence_id"] = "0" * 64
    elif change == "unknown_accession":
        rows[0]["accession"] = "0000000456-19-000001"
    elif change == "completed":
        rows[0].update(boundary_verdict="pass", timing_verdict="pass", reviewer="Synthetic fixture",
                       reviewed_at="2020-06-01T12:00:00+00:00", notes="Synthetic completed row.")
    elif change == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    path = review_inputs["root"] / "bad-reference.pending.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    pinned = _sha(path)
    if change == "stale_pin":
        path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        _build(review_inputs, reference_template_path=path, reference_template_sha256=pinned)
    assert not review_inputs["kwargs"]["output_dir"].exists()
