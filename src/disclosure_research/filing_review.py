"""Build a portable SEC filing-review desk without creating reviewer decisions.

This is a display/export bridge to the existing audit contract. It reads only
SEC tables, preserves the frozen sample and fingerprints, and never opens a
market archive or treats a browser declaration as an approved research dataset.
"""

import io
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd
import pyarrow.parquet as pq

from .audit import EVIDENCE_FINGERPRINT_FIELDS, digest, evidence_fingerprint, load_reviews
from .extraction import pair_filings
from .pilot_expansion import SEC_FILING_COLUMNS, SEC_PAIR_COLUMNS
from .protocol import canonical_hash, load_protocol, verify_lock
from .review_followup import frozen_pairs
from .timing import NY

_HASH = re.compile(r"[0-9a-f]{64}")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}")
_MAX_FILE_BYTES = 64 * 1024 * 1024
_MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
_MAX_ROWS = 1000
_REVIEW_FIELDS = {
    "accession", "evidence_id", "reviewer", "reviewer_type", "reviewed_at",
    "boundary_verdict", "timing_verdict", "notes",
}
_FILING_REQUIRED = set("""
accessionNumber cik name filingDate reportDate source_url header_url download_sha256
header_sha256 acceptance_timestamp acceptanceDateTime acceptance_date risk_text risk_token_count
extraction_status extraction_version controls_through reference_session label_end
""".split())
_EVIDENCE_REQUIRED = set(EVIDENCE_FINGERPRINT_FIELDS) | set("""
cik name filing_date report_date risk_token_count extraction_status verified_source
verified_header verified_risk_source start_context section_start section_end end_context
evidence_id blocking_issues cautions automated_evidence_ok
""".split())
_EVIDENCE_ALLOWED = _EVIDENCE_REQUIRED | set("""
api_header_difference_seconds review_status boundary_verdict timing_verdict reviewer_type
human_review_complete assistant_review_complete source_error header_error
""".split())
_DISPLAY_FIELDS = """
accession evidence_id cik name report_date source_url risk_source_url header_url
acceptance_timestamp api_timestamp controls_through reference_session label_end
resolution_method resolution_rule_id start_context section_start section_end end_context
cautions blocking_issues automated_evidence_ok
""".split()


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _unique_object(items):
    result = {}
    for key, value in items:
        _require(key not in result, "Duplicate JSON object key")
        result[key] = value
    return result


def _json(raw):
    return json.loads(raw, object_pairs_hook=_unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          ValueError("Nonfinite JSON value")))


def _identity(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _read_bytes(path, maximum=_MAX_FILE_BYTES):
    path = Path(path)
    with path.open("rb") as source:
        before = os.fstat(source.fileno())
        _require(0 < before.st_size <= maximum, "Source file exceeds bounded size or is empty")
        raw = source.read(maximum + 1)
        _require(len(raw) == before.st_size and len(raw) <= maximum,
                 "Source file changed during bounded read")
        _require(_identity(before) == _identity(os.fstat(source.fileno())),
                 "Source descriptor changed during read")
    _require(_identity(before) == _identity(path.stat()), "Source path changed during read")
    return raw


def _check_hash(raw, expected, label):
    _require(isinstance(expected, str) and _HASH.fullmatch(expected), f"Invalid {label} hash")
    _require(digest(raw) == expected, f"{label} hash differs from pinned evidence")


def _date(value, lower, upper):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value),
             "Development date must be an ISO date")
    parsed = date.fromisoformat(value)
    _require(lower <= parsed.year <= upper,
             "Final-period or pre-protocol observations are blocked from the review desk")
    return parsed


def _timestamp(value, lower, upper):
    _require(isinstance(value, str), "Acceptance timestamp must be text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
             "Acceptance timestamp must include a timezone")
    _require(lower <= parsed.astimezone(NY).year <= upper,
             "Final-period or pre-protocol acceptance clock is blocked")
    return parsed


def _preflight_parquet(raw, allowed, required, date_columns, lower, upper):
    parquet = pq.ParquetFile(io.BytesIO(raw))
    names = parquet.schema_arrow.names
    _require(len(names) == len(set(names)) and not set(names) - allowed,
             "Only SEC source columns are allowed; unexpected data refused")
    _require(required <= set(names), "Required SEC evidence columns are missing")
    _require(0 < parquet.metadata.num_rows <= _MAX_ROWS, "SEC table row count is out of bounds")
    expanded = sum(parquet.metadata.row_group(i).total_byte_size
                   for i in range(parquet.metadata.num_row_groups))
    _require(expanded <= _MAX_UNCOMPRESSED_BYTES, "SEC table expanded size exceeds limit")
    # All tables receive this date-only read before any full text is decoded.
    for row in parquet.read(columns=list(date_columns)).to_pylist():
        for key in date_columns:
            if key.endswith("timestamp"):
                _timestamp(row[key], lower, upper)
            else:
                _date(row[key], lower, upper)


def _sec_url(value):
    _require(isinstance(value, str), "SEC URL must be text")
    parts = urlsplit(value)
    _require(parts.scheme == "https" and parts.hostname in {"www.sec.gov", "data.sec.gov"}
             and not parts.username and not parts.password and parts.port in {None, 443}
             and parts.path.startswith("/"),
             "Source links must be official HTTPS SEC URLs")
    return value


def _indexed(rows, key):
    result = {}
    for row in rows:
        accession = row[key]
        _require(isinstance(accession, str) and _ACCESSION.fullmatch(accession),
                 "Invalid original accession")
        _require(accession not in result, "Duplicate original accession")
        result[accession] = row
    return result


def _check_filing_evidence(filing, evidence, lower, upper):
    _require(evidence["evidence_id"] == evidence_fingerprint(evidence),
             "Audit evidence fingerprint is stale or inconsistent")
    _require(isinstance(filing["risk_text"], str)
             and len(filing["risk_text"]) <= 4 * 1024 * 1024,
             "Invalid or oversized extracted risk text")
    _require(digest(filing["risk_text"]) == evidence["risk_text_sha256"],
             "Extracted risk text differs from audited evidence")
    mapping = {
        "accession": "accessionNumber", "filing_date": "filingDate", "report_date": "reportDate",
        "api_timestamp": "acceptanceDateTime",
    }
    direct = """cik name source_url header_url download_sha256 header_sha256 risk_token_count
    extraction_version extraction_status acceptance_timestamp controls_through reference_session
    label_end""".split()
    for target, source in [*mapping.items(), *((key, key) for key in direct)]:
        _require(filing[source] == evidence[target], "Filing provenance differs from audited evidence")
    defaults = {
        "risk_source_url": filing["source_url"], "risk_source_sha256": filing["download_sha256"],
        "resolution_method": "numbered_item1a", "resolution_rule_id": "",
        "resolution_index_url": "", "resolution_index_sha256": "",
    }
    for key, default in defaults.items():
        _require(filing.get(key, default) == evidence[key],
                 "Resolution provenance differs from audited evidence")
    for key in ("extraction_start", "extraction_end", "normalizer_version"):
        if key in filing:
            _require(filing[key] == evidence[key], "Extraction bounds differ from audited evidence")
    for key in ("source_url", "risk_source_url", "header_url"):
        _sec_url(evidence[key])
    for key in ("download_sha256", "header_sha256", "risk_source_sha256", "evidence_id"):
        _require(isinstance(evidence[key], str) and _HASH.fullmatch(evidence[key]),
                 "Invalid source or evidence fingerprint")
    _require(isinstance(filing["cik"], str) and re.fullmatch(r"[0-9]{10}", filing["cik"])
             and filing["cik"] != "0000000000", "CIK must preserve the original ten-digit identifier")
    accepted = _timestamp(evidence["acceptance_timestamp"], lower, upper)
    _require(accepted.astimezone(NY).date() == _date(filing["acceptance_date"], lower, upper),
             "Recorded acceptance date differs from its New York clock")
    for key in ("cautions", "blocking_issues"):
        _require(isinstance(evidence[key], list)
                 and all(isinstance(x, str) for x in evidence[key]), "Invalid audit issue list")


def packet_fingerprint(packet):
    return digest(json.dumps({k: v for k, v in packet.items() if k != "packet_id"},
                             sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                             allow_nan=False))


def _template_accessions(raw, evidence):
    rows = [_json(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    _require(0 < len(rows) <= _MAX_ROWS, "Reference template is empty or too large")
    known = set()
    for row in rows:
        _require(set(row) == _REVIEW_FIELDS, "Reference template fields differ from review contract")
        accession = row["accession"]
        _require(accession in evidence and accession not in known,
                 "Unknown or duplicate reference-template accession")
        _require(row["evidence_id"] == evidence[accession]["evidence_id"],
                 "Reference template has a stale evidence fingerprint")
        _require(row["boundary_verdict"] == row["timing_verdict"] == "pending"
                 and row["reviewer_type"] in {"", "human", "assistant"},
                 "Reference input must be a pending template, not completed decisions")
        _require(not row["reviewer"] and not row["reviewed_at"],
                 "Reference input cannot carry reviewer decisions")
        known.add(accession)
    return known


def build_filing_review(*, filings_path, pairs_path, audit_dir, audit_summary_sha256,
                        selected_pairs_path, selected_pairs_sha256, output_dir,
                        reference_template_path=None, reference_template_sha256=None,
                        config=None):
    """Create a new pending desk from pinned existing SEC audit inputs.

    Original SEC documents are not reread here. The existing audit reopens those
    sources when a reviewer later supplies a completed JSONL export.
    """
    output = Path(output_dir)
    _require(not output.exists(), "Output exists; preserve previous review work")
    config = load_protocol() if config is None else config
    verify_lock(config, Path("configs/protocol.lock.json"))
    lower, upper = config["initial_train_start"], config["development_end"]
    _require(2010 <= lower <= upper <= 2021, "Review desk is limited to the development envelope")
    audit_dir = Path(audit_dir)
    paths = {
        "filings": Path(filings_path), "pairs": Path(pairs_path),
        "audit_summary": audit_dir / "audit_summary.json",
        "evidence": audit_dir / "filing_evidence.parquet",
        "selected_pairs": Path(selected_pairs_path),
    }
    raws = {key: _read_bytes(path) for key, path in paths.items()}
    _check_hash(raws["audit_summary"], audit_summary_sha256, "Audit summary")
    _check_hash(raws["selected_pairs"], selected_pairs_sha256, "Frozen selection")
    summary = _json(raws["audit_summary"])
    _require(summary.get("market_returns_used") is False, "Audit must explicitly be SEC-only")
    for key, field in (("filings", "source_table_sha256"), ("pairs", "pair_table_sha256"),
                       ("evidence", "evidence_table_sha256")):
        _check_hash(raws[key], summary[field], f"Audited {key}")
    _preflight_parquet(raws["filings"], SEC_FILING_COLUMNS, _FILING_REQUIRED,
                       ("acceptance_date", "acceptance_timestamp"), lower, upper)
    _preflight_parquet(raws["pairs"], SEC_PAIR_COLUMNS,
                       {"accession", "previous_accession", "acceptance_date",
                        "previous_acceptance_date", "cik"},
                       ("acceptance_date", "previous_acceptance_date"), lower, upper)
    _preflight_parquet(raws["evidence"], _EVIDENCE_ALLOWED, _EVIDENCE_REQUIRED,
                       ("acceptance_timestamp",), lower, upper)
    # Bulk reads use these same byte snapshots only after every date preflight.
    filing_rows = pq.read_table(io.BytesIO(raws["filings"])).to_pylist()
    pair_rows = pq.read_table(io.BytesIO(raws["pairs"])).to_pylist()
    evidence_rows = pq.read_table(io.BytesIO(raws["evidence"])).to_pylist()
    filings = _indexed(filing_rows, "accessionNumber")
    evidence = _indexed(evidence_rows, "accession")
    pairs = _indexed(pair_rows, "accession")
    _require(set(filings) == set(evidence) and len(filings) == summary["filings"],
             "Audit and filing accession coverage differ")
    _require(len(pairs) == summary["annual_pairs"], "Audited pair count differs")
    for accession, filing in filings.items():
        _check_filing_evidence(filing, evidence[accession], lower, upper)
    canonical, _ = pair_filings(filing_rows, lower, upper)
    expected = _indexed(canonical, "accession")
    _require(set(pairs) == set(expected), "Annual pair coverage differs from original filings")
    for accession, pair in pairs.items():
        _require(all(value == expected[accession].get(key) for key, value in pair.items()),
                 "Annual pair source, identity, text or timing differs")
    selected = frozen_pairs(pd.DataFrame(pair_rows), raws["selected_pairs"])
    _require(len(selected) == summary["pairs_selected_for_review"], "Frozen sample count differs")
    needed = {row[key] for row in selected.to_dict("records")
              for key in ("accession", "previous_accession")}
    _require(needed <= set(filings), "Frozen sample refers to absent filing evidence")
    references = set()
    if reference_template_path is not None:
        _require(reference_template_sha256 is not None, "Pin the reference template hash")
        paths["reference_template"] = Path(reference_template_path)
        raws["reference_template"] = _read_bytes(reference_template_path, 4 * 1024 * 1024)
        _check_hash(raws["reference_template"], reference_template_sha256, "Reference template")
        references = _template_accessions(raws["reference_template"], evidence)
    else:
        _require(reference_template_sha256 is None, "Reference hash needs its template")
    desk_rows = []
    for accession in sorted(needed | references,
                            key=lambda key: (filings[key]["cik"], filings[key]["acceptance_date"])):
        row = {key: evidence[accession][key] for key in _DISPLAY_FIELDS}
        row.update(acceptance_date=filings[accession]["acceptance_date"],
                   risk_text=filings[accession]["risk_text"],
                   scope_tags=[tag for tag, members in
                               (("fixed_pair", needed), ("reference", references))
                               if accession in members])
        desk_rows.append(row)
    bindings = {key: {"file": paths[key].name, "sha256": digest(raw), "bytes": len(raw)}
                for key, raw in raws.items()}
    packet = {
        "schema_version": 1,
        "title": "Disclosure Drift — filing review",
        "scope_description": (
            "The existing fixed annual-pair sample and explicitly included matching reference "
            "cases. Other flagged filings and later expansion cases remain separate requirements. "
            "Read the full original filing, risk source and SEC header before recording a decision."
        ),
        "summary": {"selected_pairs": len(selected), "selected_filings": len(needed),
                    "reference_filings": len(references), "distinct_filings": len(desk_rows),
                    "source_filings": len(filings)},
        "pairs": [{"number": number, "name": filings[row["accession"]]["name"],
                   **{key: row[key] for key in
                      ("cik", "accession", "previous_accession", "acceptance_date")}}
                  for number, row in enumerate(selected.to_dict("records"), 1)],
        "filings": desk_rows, "source_bindings": bindings,
        "protocol_sha256": canonical_hash(config), "original_sec_bytes_reread": False,
        "full_original_documents_included": False, "market_returns_read": False,
        "model_ready": False, "source_approvals": 0, "human_reviews_created": 0,
        "historical_security_links_created": 0, "final_period_opened": False,
        "prior_arithmetic_review_modified": False,
    }
    packet["packet_id"] = packet_fingerprint(packet)
    from .filing_review_page import render_review_page

    outputs = {"packet.json": (json.dumps(packet, indent=2, ensure_ascii=False,
                                         allow_nan=False) + "\n").encode(),
               "index.html": render_review_page(packet).encode(),
               "selected_pairs.csv": raws["selected_pairs"]}
    _require(sum(len(raw) for raw in outputs.values()) <= _MAX_FILE_BYTES,
             "Finished review desk exceeds size limit")
    # Recheck every input before creating output; no existing file is overwritten.
    for key, path in paths.items():
        _require(_read_bytes(path) == raws[key], "Review source changed during construction")
    receipt = {
        "schema_version": 1, "status": "FILING_REVIEW_DESK_READY_REVIEW_PENDING",
        "packet_id": packet["packet_id"], "summary": packet["summary"],
        "source_bindings": bindings, "protocol_sha256": packet["protocol_sha256"],
        "files": [{"file": name, "sha256": digest(raw), "bytes": len(raw)}
                  for name, raw in outputs.items()],
        "original_sec_bytes_reread": False, "full_original_documents_included": False,
        "market_returns_read": False, "model_ready": False, "source_approvals": 0,
        "human_reviews_created": 0, "historical_security_links_created": 0,
        "final_period_opened": False, "prior_arithmetic_review_modified": False,
        "import_scope": "Exported reviewer declarations still require the existing source audit.",
    }
    output.mkdir(parents=True, exist_ok=False)
    # The receipt is written last. A failed filesystem write leaves no success receipt.
    for name, raw in outputs.items():
        with (output / name).open("xb") as target:
            target.write(raw)
    with (output / "receipt.json").open("x", encoding="utf-8") as target:
        target.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def validate_filing_reviews(packet, reviews_path):
    """Check declarations against a desk; this is not an original-source re-audit."""
    _require(isinstance(packet, dict) and packet.get("schema_version") == 1,
             "Unsupported filing review packet")
    _require(packet.get("packet_id") == packet_fingerprint(packet), "Review packet hash differs")
    _require(packet.get("model_ready") is False and packet.get("final_period_opened") is False,
             "Review desk cannot grant dataset or final-period approval")
    evidence = _indexed(packet["filings"], "accession")
    raw = _read_bytes(reviews_path, 4 * 1024 * 1024)
    rows = [_json(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    _require(0 < len(rows) <= len(evidence), "Export has no recorded reviews or too many rows")
    for row in rows:
        _require(isinstance(row, dict) and set(row) == _REVIEW_FIELDS,
                 "Export fields differ from the filing review contract")
        _require(row["accession"] in evidence, "Export contains an unknown accession")
        _require(row["evidence_id"] == evidence[row["accession"]]["evidence_id"],
                 "Export has a stale evidence fingerprint")
        _require(any(row[key] != "pending" for key in ("boundary_verdict", "timing_verdict")),
                 "Unrecorded pending drafts cannot be exported as reviews")
        _require(all(isinstance(row[key], str) for key in _REVIEW_FIELDS),
                 "Review values must be strings")
        reviewed = datetime.fromisoformat(row["reviewed_at"].replace("Z", "+00:00"))
        _require(reviewed.tzinfo is not None and reviewed.utcoffset() is not None,
                 "Review timestamp must include a timezone")
        _require(reviewed <= datetime.now(timezone.utc), "Review timestamp cannot be in the future")
    # Keep compatibility with the authoritative legacy record validator, using
    # an immutable temporary copy so a path change cannot mix two review reads.
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        frozen = Path(folder) / "reviews.jsonl"
        frozen.write_bytes(raw)
        loaded = load_reviews(frozen)
    _require(_read_bytes(reviews_path, 4 * 1024 * 1024) == raw,
             "Review export changed during validation")
    def complete(row):
        return row["boundary_verdict"] == row["timing_verdict"] == "pass"
    return {
        "status": "DECLARED_FILING_REVIEWS_VALID_PENDING_SOURCE_REAUDIT",
        "packet_id": packet["packet_id"], "reviews_sha256": digest(raw), "records": len(loaded),
        "human_reviews_declared_complete": sum(complete(row) and row["reviewer_type"] == "human"
                                               for row in loaded.values()),
        "assistant_reviews_declared_complete": sum(
            complete(row) and row["reviewer_type"] == "assistant" for row in loaded.values()),
        "partial_reviews": sum("pending" in (row["boundary_verdict"], row["timing_verdict"])
                               for row in loaded.values()),
        "failed_reviews": sum("fail" in (row["boundary_verdict"], row["timing_verdict"])
                              for row in loaded.values()),
        "original_sec_bytes_reread": False, "model_ready": False, "source_approvals": 0,
        "historical_security_links_created": 0, "final_period_opened": False,
        "prior_arithmetic_review_modified": False,
    }
