"""Auditable, development-only event identity evidence matrix.

This is a retrospective source-candidate analysis, not a historical CIK-PERMNO
crosswalk, XBRL share-class resolution, source vintage, or investment-universe
approval. No model target is read beyond the unchanged M5 candidate receipts.
"""

import csv
import gzip
import hashlib
import json
import os
import re
import tempfile
from html import escape
from urllib.parse import urlsplit
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .controls import control_sessions
from .protocol import canonical_hash
from .timing import event_window

STATUS = "DEVELOPMENT_EVENT_IDENTITY_MATRIX_DESCRIPTORS_NOT_APPROVED"
MARKET_KIND = "PROVISIONAL_CANDIDATE_ARITHMETIC_QA"
ANCHOR_KIND = "SEC_2019Q4_PILOT_ISSUER_ANCHORS_NOT_HISTORICAL_LINK_APPROVAL"
TENK_KIND = "ORIGINAL_SEC_10K_LEXICAL_TRADING_SYMBOL_NAMES_CORROBORATION_UNAPPROVED"
SEC_KIND = "SEC_ORIGINAL_IDENTITY_EVIDENCE_NOT_SECURITY_APPROVED"
_NAMES_FIELDS = (
    "permno", "hdrprimaryexch", "nasdissuno", "hdrsiccd", "permco",
    "secinfostartdt", "secinfoenddt", "securitybegdt", "securityenddt",
    "cusip", "ticker", "issuernm", "shareclass", "usincflg", "issuertype",
    "securitytype", "securitysubtype", "sharetype", "securityactiveflg",
    "siccd", "primaryexch", "tradingsymbol", "naics", "tradingstatusflg",
)
_CCM_FIELDS = (
    "gvkey", "conm", "tic", "cusip", "cik", "sic", "naics", "LINKPRIM",
    "LIID", "LINKTYPE", "LPERMNO", "LPERMCO", "LINKDT", "LINKENDDT",
    "EIN", "COSTAT", "DLRSN", "PRIUSA", "PRICAN", "PRIROW", "IDBFLAG",
    "FIC", "LOC", "INCORP", "STATE", "COUNTY", "CITY", "CONML", "WEBURL",
    "PHONE", "FAX", "ADD1", "ADD2", "ADD3", "ADD4", "ADDZIP", "BUSDESC",
    "ipodate", "dldte", "STKO", "FYRC", "GSECTOR", "GGROUP", "GIND",
    "GSUBIND", "SPCINDCD", "SPCSECCD",
)
_MARKET_FIELDS = (
    "event_id", "cik", "candidate_permno", "acceptance_timestamp",
    "reference_session", "controls_asof", "label_end", "control_history_start",
    "identity_approved", "model_ready", "human_pair_review_complete",
    "qa_status", "data_kind", "header_cik_differs", "open_end_unresolved",
)
_SOURCE_HASH = re.compile(r"[0-9a-f]{64}")
_CIK = re.compile(r"[0-9]{10}")
_SEC_SOURCE_FILE_CAP = 16 * 1024 * 1024


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _sha(content):
    return hashlib.sha256(content).hexdigest()


def _read_source(path, limit):
    given = Path(path)
    _require(not given.is_symlink(), "Symlinked original input is not permitted")
    p = given.resolve(strict=True)
    _require(p.is_file() and p.stat().st_size <= limit, "Original source missing or oversized")
    return p, p.read_bytes()


def _verified_private(root, expected_status, *, config, restrictions):
    root = Path(root).resolve(strict=True)
    _, receipt_raw = _read_source(root / "receipt.json", 128 * 1024)
    receipt = json.loads(receipt_raw)
    _require(receipt.get("status") == expected_status,
             "Private research evidence has an unexpected status")
    for key, value in restrictions.items():
        _require(receipt.get(key) is value, f"Private evidence restriction changed: {key}")
    output = {}
    for name in ("private_issuer_rows.jsonl", "private_filing_symbol_contexts.jsonl"):
        if name not in receipt.get("files", {}):
            continue
        path, data = _read_source(root / name, 1024 * 1024)
        declaration = receipt["files"][name]
        _require(_sha(data) == declaration["sha256"] and len(data) == declaration["bytes"],
                 f"Private evidence SHA-256 mismatch: {name}")
        output[name] = [json.loads(x) for x in data.decode("utf-8").splitlines() if x]
    _require(output, "No private issuer/symbol rows in evidence")
    return receipt, output, _sha(receipt_raw)


def _load_fixed_market(market_dir, config):
    market_dir = Path(market_dir).resolve(strict=True)
    receipt_path, receipt_raw = _read_source(market_dir / "audit_summary.json", 250 * 1024)
    data_path, data_raw = _read_source(market_dir / "candidate_calculations.parquet", 32 * 1024 * 1024)
    meta = json.loads(receipt_raw)
    _require(meta["data_kind"] == MARKET_KIND
             and meta["model_ready"] is False
             and meta["historical_cik_mapping_approved"] is False
             and meta["final_period_opened"] is False
             and meta["source_hashes"]["protocol"] == canonical_hash(config),
             "Market source is not the unapproved locked development candidate")
    _require(meta["files"]["candidate_calculations.parquet"] == _sha(data_raw),
             "M5 candidate table differs from its preserved source receipt")
    frame = pd.read_parquet(data_path)
    _require(len(frame) == meta["qa_cases_calculated"] == 135
             and set(_MARKET_FIELDS).issubset(frame.columns)
             and frame["event_id"].is_unique
             and frame["data_kind"].eq(MARKET_KIND).all()
             and frame["qa_status"].eq("calculated_pending_review").all(),
             "Unexpected market candidate cohort or duplicated SEC filing IDs")
    for field in ("identity_approved", "model_ready", "human_pair_review_complete"):
        _require(frame[field].eq(False).all(), f"Candidate input already claims approval: {field}")
    _require(frame["open_end_unresolved"].eq(True).all(),
             "Original pilot CCM open-end evidence unexpectedly changed")
    _require(frame["cik"].map(lambda c: isinstance(c, str) and bool(_CIK.fullmatch(c))).all()
             and frame["candidate_permno"].map(
                 lambda s: isinstance(s, str) and bool(re.fullmatch(r"[1-9][0-9]{0,19}", s))).all(),
             "Malformed permanent security or ten-digit CIK in original pilot")
    for raw in frame["acceptance_timestamp"]:
        _require(isinstance(raw, str), "Missing original SEC acceptance timestamp")
        try:
            accepted = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Malformed original SEC acceptance timestamp") from exc
        _require(accepted.utcoffset() is not None, "Original SEC acceptance lacks timezone")
        _require(2015 <= accepted.year <= config["development_end"]
                 and accepted.year < config["holdout_start"],
                 "Holdout or outside-year filing forbidden before opening issuer sources")
    issuer_pairs = frame[["cik", "candidate_permno"]].drop_duplicates()
    _require(len(issuer_pairs) == 20
             and issuer_pairs["cik"].is_unique and issuer_pairs["candidate_permno"].is_unique,
             "Fixed issuer cohort must retain exactly one candidate PERMNO per CIK")
    return frame, issuer_pairs, {"candidate_table": _sha(data_raw),
                                 "candidate_receipt": _sha(receipt_raw)}, (receipt_path, data_path)


def _read_names(names_csv, names_inventory, identifiers, config):
    source, raw = _read_source(names_csv, 256 * 1024 * 1024)
    _, inventory_raw = _read_source(names_inventory, 1024 * 1024)
    receipt = json.loads(inventory_raw)
    _require(receipt["status"] == "RAW_MANUAL_WRDS_METADATA_INVENTORY_NOT_SOURCE_APPROVED"
             and receipt["model_ready"] is False and receipt["source_approvals"] == 0
             and receipt["protocol_sha256"] == canonical_hash(config),
             "Unexpected CRSP Names inventory state")
    _require(receipt["source"]["sha256"] == _sha(raw)
             and receipt["source"]["bytes"] == len(raw)
             and receipt["source"]["observed_header"] == list(_NAMES_FIELDS),
             "Source Names CSV or inventory field list differs from the preserved export")
    n = 0
    by_permno = defaultdict(list)
    with source.open(encoding="utf-8-sig", newline="") as file:
        rdr = csv.DictReader(file, strict=True, restkey="extra")
        _require(rdr.fieldnames == list(_NAMES_FIELDS), "Original CRSP Names header changed")
        for ordinal, row in enumerate(rdr, start=2):
            _require("extra" not in row and None not in row.values(),
                     "Malformed source CRSP Names CSV record")
            n += 1
            if row["permno"] in identifiers:
                by_permno[row["permno"]].append({**row, "_source_record": ordinal})
    _require(n == receipt["all_rows"]["rows"] and n >= len(identifiers)
             and len(by_permno) == len(identifiers),
             "Complete original Names source coverage changed")
    selected_company_ids = {row["permco"] for records in by_permno.values() for row in records}
    _require(len(selected_company_ids) == len(identifiers) and "" not in selected_company_ids,
             "Selected original Names company IDs must be unambiguous and nonempty")
    by_company_id = defaultdict(list)
    verification_rows = 0
    with source.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, strict=True, restkey="extra")
        _require(reader.fieldnames == list(_NAMES_FIELDS),
                 "Second complete CRSP Names source pass differs in header")
        for ordinal, record in enumerate(reader, start=2):
            _require("extra" not in record and None not in record.values(),
                     "Malformed full-company collateral Names source record")
            verification_rows += 1
            if record["permco"] in selected_company_ids:
                by_company_id[record["permco"]].append({**record, "_source_record": ordinal})
    _require(verification_rows == n
             and len(by_company_id) == len(selected_company_ids),
             "Same-company security cohort failed complete original Names second pass")
    return by_permno, by_company_id, {"names_source": _sha(raw), "names_receipt": _sha(inventory_raw)}, (
        source, Path(names_inventory).resolve()
    )


def _read_ccm(ccm_files, identity_public, security_ids):
    _, report_raw = _read_source(identity_public, 256 * 1024)
    report = json.loads(report_raw)
    expected = report["source_hashes"]["ccm"]
    _require(len(ccm_files) == len(expected) == 2
             and {Path(f).name for f in ccm_files} == set(expected),
             "Original two CCM pilot source files must both be provided")
    by_permno = defaultdict(list)
    originals = []
    for supplied in sorted(ccm_files, key=lambda p: Path(p).name):
        p, raw = _read_source(supplied, 64 * 1024 * 1024)
        _require(_sha(raw) == expected[p.name], "Original pilot CCM source SHA changed")
        originals.append(p)
        with p.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, strict=True, restkey="extra")
            _require(reader.fieldnames == list(_CCM_FIELDS), "Original pilot CCM field list changed")
            for ordinal, row in enumerate(reader, start=2):
                _require("extra" not in row and None not in row.values(),
                         "Malformed original CCM source record")
                if row["LPERMNO"] in security_ids:
                    by_permno[row["LPERMNO"]].append({
                        **row, "_source_record": ordinal, "_source_file": p.name,
                    })
    _require(len(by_permno) == len(security_ids), "Missing original CCM relationship candidate")
    return by_permno, {"ccm_public_summary": _sha(report_raw),
                       **{f"ccm_source:{p.name}": expected[p.name] for p in originals}}, originals


def _read_original_sec(sec_gzip, sec_execution, config):
    path, compressed = _read_source(sec_gzip, 8 * 1024 * 1024)
    execution_path, execution_blob = _read_source(sec_execution, 2 * 1024 * 1024)
    execution = json.loads(execution_blob)
    published = execution["publication"]
    _require(_sha(compressed) == published["sha256"]
             and len(compressed) == published["bytes"],
             "Published original SEC report gzip fingerprint changed")
    plain = gzip.decompress(compressed)
    _require(len(plain) <= _SEC_SOURCE_FILE_CAP
             and _sha(plain) == published["uncompressed_sha256"]
             and len(plain) == published["uncompressed_bytes"],
             "Original SEC report gzip roundtrip or source byte hash differs")
    report = json.loads(plain)
    _require(report["status"] == SEC_KIND
             and report["original_sec_bytes_reread"] is True
             and report["source_approvals"] == 0
             and report["historical_security_links_created"] == 0
             and report["final_period_opened"] is False
             and report["protocol_sha256"] == canonical_hash(config)
             and len(report["records"]) == 215,
             "Original SEC report not a verified unapproved source record")
    by_accession = {r["accession"]: r for r in report["records"]}
    _require(len(by_accession) == 215, "Repeated original SEC accession")
    return by_accession, {
        "sec_identity_gzip": _sha(compressed),
        "sec_identity_original_json": _sha(plain),
        "sec_identity_execution": _sha(execution_blob),
    }, (path, execution_path)


def _facts_by_event(tenk_dir, market_receipt_sha, sec_gzip_sha, names_source_sha, config):
    receipt, data, receipt_sha = _verified_private(
        tenk_dir, TENK_KIND, config=config,
        restrictions={"model_ready": False, "source_approvals": 0,
                      "security_links_approved": 0, "actual_final_2022_2025_opened": False},
    )
    prior = receipt["provenance"]
    _require(prior["candidate_receipt_sha256"] == market_receipt_sha
             and prior["original_SEC_report_gzip_sha256"] == sec_gzip_sha
             and prior["original_CRSP_Names_csv_sha256"] == names_source_sha
             and prior["protocol_sha256"] == canonical_hash(config),
             "Previous 10-K symbol audit source bindings differ")
    rows = data["private_filing_symbol_contexts.jsonl"]
    events = {item["accession"]: item for item in rows}
    _require(len(events) == len(rows), "Repeated previous 10-K symbol audit record")
    return events, {"tenk_receipt": receipt_sha,
                    "tenk_private_rows": receipt["files"]["private_filing_symbol_contexts.jsonl"]["sha256"]}


def _anchors_by_issuer(anchor_dir, market_receipt_sha, sec_gzip_sha, names_source_sha, config):
    receipt, data, receipt_sha = _verified_private(
        anchor_dir, ANCHOR_KIND, config=config,
        restrictions={"model_ready": False, "source_approvals": 0,
                      "security_links_approved": 0, "final_period_opened": False},
    )
    bound = receipt["provenance"]
    _require(bound["market_candidate_receipt_sha256"] == market_receipt_sha
             and bound["sec_original_evidence_gzip_sha256"] == sec_gzip_sha
             and bound["original_CRSP_Names_CSV_sha256"] == names_source_sha
             and bound["frozen_protocol_sha256"] == canonical_hash(config),
             "Prior 2019Q4 anchor evidence is not source-compatible")
    rows = data["private_issuer_rows.jsonl"]
    issuer = {x["original_sec_filer_cik"]: x for x in rows}
    _require(len(issuer) == len(rows) == 20, "Expected 20 distinct 2019Q4 issuer anchors")
    _require(all(x["source_identity_approval"] is False and x["known_at"] is None
                 and x["available_at"] is None and x["historical_link_validity_established"] is False
                 for x in rows), "Historical anchor file cannot assert approved identity")
    return issuer, {"anchor_receipt": receipt_sha,
                    "anchor_private_rows": receipt["files"]["private_issuer_rows.jsonl"]["sha256"]}


def _event_symbols(sec_source):
    return [f for f in sec_source["cover_evidence"]["facts"]
            if f["concept_qname_raw"] == "dei:TradingSymbol"]


def _symbol_relation(facts, source_names, acceptance_day):
    """Return only facts visible in parsed lexical report, not validated XBRL classes."""
    if not facts:
        return False, False, False, False
    values = {x["text_from_parsed_html"] for x in facts}
    has_multi = len(values) > 1
    issue = any(bool(x["lexical_issues"]) for x in facts)
    hidden = any(bool(x["inside_hidden_element"])
                 or bool(x["hidden_by_inline_style_observed"]) for x in facts)
    matched = any(
        symbol != "" and symbol in
        {r["ticker"], r["tradingsymbol"]}
        for symbol in values for r in source_names
        if r["secinfostartdt"] <= acceptance_day <= r["secinfoenddt"]
    )
    return matched, has_multi, issue, hidden




def _inspect_window_names(source_rows, required_sessions, expected_permco):
    """Require one lifetime-valid descriptor for every XNYS session.

    Return every source-record ordinal rather than collapsing distinct
    source records that happen to share a ticker/CUSIP.
    """
    covered = []
    for day in required_sessions:
        descriptions = [row for row in source_rows
                        if row["secinfostartdt"] <= day <= row["secinfoenddt"]]
        _require(len(descriptions) == 1,
                 "Dated original Names interval missing or ambiguous in 81-session window")
        record = descriptions[0]
        _require(record["securitybegdt"] <= day <= record["securityenddt"]
                 and record["permco"] == expected_permco,
                 "Dated Names security lifetime or CCM PERMCO conflict")
        covered.append(record)
    return {
        "source_records": sorted({r["_source_record"] for r in covered}),
        "cusip8_raw": sorted({r["cusip"] for r in covered}),
        "trading_symbols_raw": sorted({r["tradingsymbol"] for r in covered}),
        "descriptors": covered,
    }



def _same_company_security_context(company_descriptors, selected_permno, acceptance_day):
    """Other PERMNOs linked to the same raw PERMCO, not validated share classes."""
    active = [row for row in company_descriptors
              if row["secinfostartdt"] <= acceptance_day <= row["secinfoenddt"]]
    return sorted({row["permno"] for row in active if row["permno"] != selected_permno})

def _verified_sec_url(source):
    """Display only the immutable previously recorded official SEC source URL."""
    if not isinstance(source, dict):
        return ""
    value = source.get("url")
    if not isinstance(value, str):
        return ""
    parsed = urlsplit(value)
    return value if parsed.scheme == "https" and parsed.netloc == "www.sec.gov" and (
        parsed.path.startswith("/Archives/edgar/data/")
    ) and not parsed.username and not parsed.password else ""


def _render_private_review(events, original_sec):
    """Human-readable, private *read-only* evidence queue. No verdict controls."""
    by_year = defaultdict(list)
    for item in events:
        by_year[item["year"]].append(item)
    blocks = []
    for year, group in sorted(by_year.items()):
        cards = []
        for row in group:
            reference = original_sec[row["observation_id"]]
            sources = []
            for caption, key in (("Original SEC filing", "primary_source"),
                                 ("Original SEC header", "header_source")):
                url = _verified_sec_url(reference.get(key))
                if url:
                    sources.append(
                        f'<a href="{escape(url, quote=True)}" rel="noreferrer noopener" '
                        f'target="_blank">{escape(caption)}</a>'
                    )
            flags = "".join(f"<li>{escape(flag)}</li>" for flag in row["review_flags"])
            cards.append(
                f'<details><summary><strong>{escape(row["observation_id"])}</strong>'
                f' · {escape(row["acceptance_timestamp"][:10])}'
                f' · {len(row["review_flags"])} unresolved checks</summary>'
                f'<p>Original SEC CIK: <code>{escape(row["original_SEC_CIK"])}</code>'
                f' · provisional CRSP PERMNO: <code>{escape(row["candidate_CRSP_PERMNO"])}</code>'
                f' · CCM source row: <code>{escape(row["original_CCM_source_file"])}:'
                f'{int(row["original_CCM_source_record"])}</code></p>'
                f'<p>Original Names source records: '
                f'<code>{escape(", ".join(str(i) for i in row["source_names_record_ordinals"]))}</code>'
                f' · CUSIP8 literals: <code>{escape(", ".join(row["observed_names_CUSIP8_raw"]))}</code>'
                f' · same-PERMCO alternative PERMNOs: '
                f'<code>{escape(", ".join(row["alternative_active_same_PERMCO_security_ids_raw"]) or "none observed")}</code></p>'
                f'<p>Original Names shareclass literal: '
                f'<code>{escape(row["selected_original_names_shareclass_raw"] or "(blank)")}</code>'
                f' · sharetype literal: <code>{escape(row["selected_original_names_sharetype_raw"])}</code>'
                f' · original 10-K TradingSymbol lexical facts: {row["original_10k_symbol_fact_count"]}</p>'
                f'<p>2019Q4 SEC issuer-anchor filing date was earlier: '
                f'{"yes (not proof of publication)" if row["2019q4_issuer_anchor_reported_before_10k"] else "not established"}'
                f' · source URLs: {" · ".join(sources) if sources else "not retained in this source bundle"}</p>'
                f'<h4>Open source and reviewer issues</h4><ul>{flags}</ul>'
                f'<p><strong>Decision:</strong> pending. Historical CIK-to-PERMNO known_at,'
                f' source release, security class, and data availability not approved.</p></details>'
            )
        blocks.append(
            f'<section><h2>Acceptance year {year} · {len(group)} events</h2>'
            + "".join(cards) + "</section>"
        )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Disclosure Drift — Private Historical Identity Review Queue</title>'
        '<style>body{font:15px system-ui;line-height:1.5;max-width:1100px;'
        'margin:36px auto;padding:0 20px;color:#1b2939;background:#f5f7fa}'
        'details{background:#fff;border:1px solid #d3dbe3;border-radius:10px;'
        'padding:15px;margin:12px 0;overflow-wrap:anywhere}'
        'summary{cursor:pointer;color:#143653}h1,h2{line-height:1.25}'
        'code{font-size:13px}li{padding:2px 0}'
        'a{color:#1651a2}p{margin:10px 0}</style>'
        '<main><h1>Disclosure Drift — Historical Identity Review Queue</h1>'
        '<p><strong>Source evidence only — not a historical approval.</strong>'
        ' SEC filing CIKs, CRSP security IDs and source row numbers are private.'
        ' A matching dated descriptor does not establish known_at, available_at,'
        ' continuous issuer identity or common-stock eligibility.</p>'
        '<p>All 135 original filing events retain pending source/human review.'
        ' This page is read-only and does not record or submit verdicts.</p>'
        + "".join(blocks) + '</main></html>'
    )


def run_development_identity_matrix(market_candidates, names_csv, names_inventory,
                                    ccm_sources, identity_summary, sec_gzip, sec_execution,
                                    tenk_audit, ownership_anchor, output, *,
                                    config, repo_root):
    """Produce a private per-event review queue and a no-approval public aggregate."""
    root = Path(repo_root).resolve(strict=True)
    destination = Path(output).resolve()
    _require(not destination.exists() and any(
        destination.is_relative_to(root / folder) and destination != root / folder
        for folder in ("data", "outputs")
    ), "Use a new private output directory under data/ or outputs/")
    market, issuers, proof, bound_paths = _load_fixed_market(market_candidates, config)
    selected = set(issuers["candidate_permno"])
    names, names_by_company, names_proof, names_paths = _read_names(
        names_csv, names_inventory, selected, config
    )
    ccm, ccm_proof, ccm_paths = _read_ccm(ccm_sources, identity_summary, selected)
    original_sec, sec_proof, sec_paths = _read_original_sec(sec_gzip, sec_execution, config)
    tenk, tenk_proof = _facts_by_event(
        tenk_audit, proof["candidate_receipt"], sec_proof["sec_identity_gzip"],
        names_proof["names_source"], config
    )
    anchors, anchor_proof = _anchors_by_issuer(
        ownership_anchor, proof["candidate_receipt"], sec_proof["sec_identity_gzip"],
        names_proof["names_source"], config
    )
    by_pair = dict(zip(issuers["cik"], issuers["candidate_permno"], strict=True))
    _require(set(anchors) == set(by_pair)
             and all(x["pilot_candidate_permno"] == by_pair[k] and x["pilot_cik_matched_earlier_issuer"]
                     for k, x in anchors.items()),
             "2019Q4 source anchors do not cover these exact pilot CIK/PERMNO pairs")
    _require(set(tenk).issubset(set(market["event_id"])),
             "Prior 10-K evidence references an unknown filing")
    counts = Counter()
    year_counts = defaultdict(Counter)
    events_private = []
    for event in sorted(market.itertuples(index=False), key=lambda x: x.event_id):
        parsed = datetime.fromisoformat(event.acceptance_timestamp.replace("Z", "+00:00"))
        _require(parsed.utcoffset() is not None, "Original SEC acceptance lacks offset")
        year = parsed.year
        _require(2015 <= year <= config["development_end"]
                 and year < config["holdout_start"], "Holdout or outside-year filing forbidden")
        window = event_window(parsed, config["reference_session_offset"],
                              config["horizon_sessions"])
        controls = control_sessions(window)
        _require((event.reference_session, event.controls_asof, event.label_end,
                  event.control_history_start) ==
                 (window.reference_session, window.controls_through, window.label_end, controls[0]),
                 "Original M5 acceptance-window timing disagrees with XNYS")
        required_sessions = [*controls, window.reference_session, *window.return_sessions]
        _require(len(required_sessions) == 81 and len(set(required_sessions)) == 81,
                 "Expected 60+1+20 distinct XNYS dates")
        acceptance_day = parsed.date().isoformat()
        original = original_sec.get(event.event_id)
        _require(original is not None
                 and original["recorded_acceptance_timestamp"] == event.acceptance_timestamp
                 and original["manifest_cik_raw"] == event.cik
                 and original["header_identity"]["header_identity_consistent"] is True
                 and original["header_identity"]["matching_filer_count"] == 1,
                 "Original SEC filing identity or acceptance clock differs")
        original_filers = original["header_identity"]["filers"]
        _require(any(f["matches_manifest_cik"] and f["cik_comparison_key"] == event.cik
                     for f in original_filers),
                 "Original header fails filer CIK match")
        source_ccm = [
            link for link in ccm[event.candidate_permno]
            if link["LINKDT"] <= acceptance_day
            and (link["LINKENDDT"] == "E" or acceptance_day <= link["LINKENDDT"])
        ]
        _require(len(source_ccm) == 1, "Zero/multiple dated CCM link candidates at the filing date")
        relationship = source_ccm[0]
        _require(relationship["LPERMNO"] == event.candidate_permno
                 and bool(event.open_end_unresolved) is (relationship["LINKENDDT"] == "E")
                 and bool(event.header_cik_differs) is (relationship["cik"] != event.cik),
                 "Original CCM header/open-end flags conflict with M5 evidence")
        window_names = _inspect_window_names(
            names[event.candidate_permno], required_sessions, relationship["LPERMCO"]
        )
        at_acceptance = [row for row in names[event.candidate_permno]
                         if row["secinfostartdt"] <= acceptance_day <= row["secinfoenddt"]]
        _require(len(at_acceptance) == 1,
                 "Filing acceptance has zero/multiple original CRSP Names descriptors")
        selected_names = at_acceptance[0]
        other_company_permnos = _same_company_security_context(
            names_by_company[selected_names["permco"]],
            event.candidate_permno, acceptance_day,
        )
        raw_facts = _event_symbols(original)
        matched, has_multi, has_issue, has_hidden = _symbol_relation(
            raw_facts, at_acceptance, acceptance_day
        )
        previous = tenk.get(event.event_id)
        _require(bool(raw_facts) is (previous is not None),
                 "Original SEC facts do not match prior source-pinned 10-K audit coverage")
        if previous:
            _require(previous["original_issuer_cik"] == event.cik
                     and previous["candidate_permno"] == event.candidate_permno
                     and previous["original_10k_acceptance_day"] == acceptance_day
                     and previous["multiple_symbols_require_class_review"] == has_multi
                     and previous["lexical_issues_require_review"] == has_issue
                     and previous["hidden_facts_require_review"] == has_hidden
                     and bool(previous["dated_names_matching_symbol_and_source_record"]) == matched
                     and previous["SEC_XBRL_semantics_validated"] is False,
                     "Source-pinned 10-K symbol review flags or exact match disagree")
        clean_single = bool(raw_facts) and matched and not has_multi and not has_issue and not has_hidden
        descriptors = window_names["source_records"]
        cusips = window_names["cusip8_raw"]
        trading_symbols = window_names["trading_symbols_raw"]
        anchor = anchors[event.cik]
        prior_q4_reported_date = anchor["quarter_source_date_min"] < acceptance_day
        _require(anchor["quarter_source_date_min"] <= anchor["quarter_source_date_max"]
                 and anchor["quarter_source_date_max"] < "2020-01-01"
                 and anchor["known_at"] is None and anchor["available_at"] is None,
                 "Original 2019Q4 quarterly issuer anchor bounds or availability changed")
        flags = []
        if event.header_cik_differs:
            flags.append("CURRENT_COMPANY_HEADER_CIK_CONFLICT")
        if relationship["LINKENDDT"] == "E":
            flags.append("CCM_OPEN_LINK_END_UNRESOLVED")
        if len(descriptors) > 1:
            flags.append("DATED_NAMES_DESCRIPTOR_TRANSITION_WITHIN_81_SESSIONS")
        if other_company_permnos:
            flags.append("CONTEMPORANEOUS_OTHER_CRSP_PERMNO_SAME_PERMCO_REVIEW")
        if not selected_names["shareclass"]:
            flags.append("BLANK_NAMES_SHARECLASS_LITERAL_NOT_ELIGIBILITY_APPROVAL")
        if len(cusips) > 1:
            flags.append("DATED_EIGHT_CHAR_CUSIP_CHANGE_WITHIN_WINDOW")
        if len(trading_symbols) > 1:
            flags.append("DATED_TRADING_SYMBOL_CHANGE_WITHIN_WINDOW")
        if not raw_facts:
            flags.append("NO_ORIGINAL_10K_LEXICAL_TRADING_SYMBOL_FACT")
        if has_multi:
            flags.append("MULTIPLE_DISTINCT_10K_TRADING_SYMBOLS_CLASS_REVIEW")
        if has_issue:
            flags.append("ORIGINAL_10K_SYMBOL_LEXICAL_ISSUE")
        if has_hidden:
            flags.append("ORIGINAL_10K_HIDDEN_SYMBOL_CONTEXT")
        if not prior_q4_reported_date:
            flags.append("2019Q4_ISSUER_ANCHOR_NOT_EARLIER_THAN_THIS_10K")
        flags.extend(["HISTORICAL_CIK_TO_SECURITY_KNOWN_AT_UNKNOWN",
                      "MARKET_SOURCE_AVAILABLE_AT_UNKNOWN",
                      "SOURCE_RELEASE_AND_VERSION_UNVERIFIED"])
        counts.update({
            "events": 1, "required_session_checks": len(required_sessions),
            "unique_names_descriptors_at_81_required_sessions": 1,
            "unique_ccm_link_candidate_at_acceptance": 1,
            "permanent_company_ID_consistent_for_all_81_sessions": 1,
            "original_filing_CIK_and_clock_validated_by_prior_SEC_source_report": 1,
            "dated_names_descriptor_transition_windows": int(len(descriptors) > 1),
            "eight_char_cusip_change_windows": int(len(cusips) > 1),
            "dated_trading_symbol_change_windows": int(len(trading_symbols) > 1),
            "current_ccm_company_header_CIK_differences": int(event.header_cik_differs),
            "open_ended_CCM_links": int(relationship["LINKENDDT"] == "E"),
            "events_with_alternative_active_CRSP_PERMNO_same_company": int(bool(other_company_permnos)),
            "events_with_blank_original_names_shareclass": int(not selected_names["shareclass"]),
            "original_10k_trading_symbol_fact_events": int(bool(raw_facts)),
            "original_10k_exact_date_symbol_candidate_matches": int(matched),
            "original_10k_single_clean_nonhidden_symbol_candidate_matches": int(clean_single),
            "original_10k_multiple_distinct_symbols": int(has_multi),
            "original_10k_lexical_symbol_issues": int(has_issue),
            "original_10k_hidden_symbol_facts": int(has_hidden),
            "original_2019q4_issuer_anchor_filing_date_before_this_event": int(prior_q4_reported_date),
            "events_with_both_prior_Q4_filing_date_anchor_and_10K_cover_symbol":
                int(prior_q4_reported_date and bool(raw_facts)),
            "events_with_only_10K_cover_symbol_no_prior_Q4_anchor":
                int(not prior_q4_reported_date and bool(raw_facts)),
            "events_with_only_prior_Q4_filing_date_anchor_no_10K_cover_symbol":
                int(prior_q4_reported_date and not raw_facts),
            "events_with_neither_prior_Q4_anchor_nor_direct_10K_cover_symbol":
                int(not prior_q4_reported_date and not raw_facts),
        })
        year_counts[year].update({
            "events": 1, "required_session_checks": len(required_sessions),
            "descriptor_transition_windows": int(len(descriptors) > 1),
            "cusip_change_windows": int(len(cusips) > 1),
            "CCM_header_disagreement_events": int(event.header_cik_differs),
            "alternative_active_same_PERMCO_security_events": int(bool(other_company_permnos)),
            "blank_original_names_shareclass_events": int(not selected_names["shareclass"]),
            "original_10k_symbol_fact_events": int(bool(raw_facts)),
            "clean_single_symbol_candidate_matches": int(clean_single),
            "prior_2019q4_issuer_anchor_date_events": int(prior_q4_reported_date),
            "both_prior_Q4_anchor_and_cover_symbol_events":
                int(prior_q4_reported_date and bool(raw_facts)),
            "neither_prior_Q4_anchor_nor_cover_symbol_events":
                int(not prior_q4_reported_date and not raw_facts),
        })
        events_private.append({
            "observation_id": event.event_id,
            "original_SEC_CIK": event.cik,
            "candidate_CRSP_PERMNO": event.candidate_permno,
            "acceptance_timestamp": event.acceptance_timestamp,
            "year": year,
            "reference_session": window.reference_session,
            "control_session_count": len(controls),
            "return_session_count": len(window.return_sessions),
            "source_names_record_ordinals": descriptors,
            "original_CCM_source_file": relationship["_source_file"],
            "original_CCM_source_record": relationship["_source_record"],
            "original_CCM_GVKEY": relationship["gvkey"],
            "original_CCM_link_end_literal": relationship["LINKENDDT"],
            "original_CCM_company_header_CIK": relationship["cik"],
            "observed_names_CUSIP8_raw": cusips,
            "observed_names_trading_symbols_raw": trading_symbols,
            "selected_original_names_sharetype_raw": selected_names["sharetype"],
            "selected_original_names_shareclass_raw": selected_names["shareclass"],
            "selected_original_names_issuertype_raw": selected_names["issuertype"],
            "selected_original_names_securitytype_raw": selected_names["securitytype"],
            "alternative_active_same_PERMCO_security_ids_raw": other_company_permnos,
            "original_10k_symbol_fact_count": len(raw_facts),
            "strict_clean_single_cover_symbol_candidate": clean_single,
            "2019q4_issuer_anchor_reported_before_10k": prior_q4_reported_date,
            "review_flags": flags,
            "historical_CIK_to_PERMNO_approved": False,
            "historical_known_at": None, "market_available_at": None,
            "source_release_verified": False, "model_ready": False,
        })
    _require(counts["events"] == 135 and counts["required_session_checks"] == 10935
             and len(events_private) == 135
             and set(year_counts) == set(range(2015, 2022)),
             "Full original pilot development year/window accounting failed")
    _require(counts["original_10k_trading_symbol_fact_events"] == len(tenk),
             "Source-bound original 10-K symbol filing count inconsistent")
    for source, hash_expected in [
        (bound_paths[0], proof["candidate_receipt"]),
        (bound_paths[1], proof["candidate_table"]),
        (names_paths[0], names_proof["names_source"]),
        (names_paths[1], names_proof["names_receipt"]),
        (sec_paths[0], sec_proof["sec_identity_gzip"]),
        (sec_paths[1], sec_proof["sec_identity_execution"]),
    ]:
        _require(_sha(source.read_bytes()) == hash_expected,
                 "Consumed original historical source changed before finalizing audit")
    for source in ccm_paths:
        _require(_sha(source.read_bytes()) == ccm_proof[f"ccm_source:{source.name}"],
                 "Original pilot CCM source mutated")
    provenance = {**proof, **names_proof, **ccm_proof, **sec_proof, **tenk_proof, **anchor_proof,
                  "protocol": canonical_hash(config)}
    summary = {
        "schema_version": 1, "status": STATUS, "scope": "fixed_sec_parser_pilot_only",
        "years": list(range(2015, 2022)), "issuer_count": len(issuers),
        "counts": dict(sorted(counts.items())),
        "year_counts": {str(year): dict(sorted(x.items()))
                        for year, x in sorted(year_counts.items())},
        "provenance": provenance,
        "observed_2019q4_issuer_anchor_covers_all_20_candidate_pairs": True,
        "source_version_and_historical_revisions_approved": False,
        "historical_security_link_effective_interval_approved": False,
        "historical_known_at_established": False, "market_available_at_established": False,
        "original_10k_XBRL_class_contexts_validated": False,
        "historical_top_500_investable_universe_approved": False,
        "human_review_or_source_approvals_created": 0,
        "model_ready": False, "final_period_opened": False,
        "primary_empirical_milestones_completed": [],
        "interpretation": (
            "Full dated CRSP descriptor coverage and single CCM relationship candidate at each "
            "development filing, with explicit conflicting/later issuer facts. No continuous "
            "historical CIK-PERMNO known-at, vendor availability or original 10-K XBRL class approval."
        ),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".development-identity-matrix-", dir=destination.parent) as scratch:
        stage = Path(scratch) / "result"
        stage.mkdir(mode=0o700)
        (stage / "review_queue_private.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in events_private)
        )
        (stage / "private_review.html").write_text(
            _render_private_review(events_private, original_sec)
        )
        (stage / "public_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        receipt = {
            "schema_version": 1, "status": STATUS,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_bindings": provenance,
            "files": {name: {"sha256": _sha((stage / name).read_bytes()),
                             "bytes": (stage / name).stat().st_size}
                      for name in ("review_queue_private.jsonl", "private_review.html",
                                   "public_summary.json")},
            "historical_links_approved": 0, "source_approvals": 0,
            "model_ready": False, "final_period_opened": False,
        }
        (stage / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        for path in stage.iterdir():
            os.chmod(path, 0o400)
        stage.rename(destination)
    return summary
