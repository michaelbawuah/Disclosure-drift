"""Assemble dated identity evidence without selecting or approving security links."""

import io
import json
import re
import tempfile
from html import escape
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from .audit import cached_body
from .controls import control_sessions
from .crsp_staging import _csv, _ids
from .labels import load_development_events
from .market_data import fingerprint, iso_dates, sha256
from .protocol import canonical_hash

CCM_FIELDS = """gvkey conm tic cusip cik LINKPRIM LIID LINKTYPE
LPERMNO LPERMCO LINKDT LINKENDDT""".split()
NAMES_FIELDS = """permno permco secinfostartdt secinfoenddt
cusip ticker issuernm shareclass securitytype securitysubtype sharetype siccd""".split()
FILING_FIELDS = """accessionNumber cik acceptance_timestamp source_url header_url
header_sha256""".split()
CANDIDATE_FIELDS = """event_id filing_cik candidate_permno ccm_header_cik ccm_header_name
header_cik_differs ccm_gvkey ccm_permco ccm_link_start ccm_link_end_raw
ccm_end_marker_unresolved ccm_link_type ccm_link_primary ccm_issue_id ccm_source_file
ccm_source_record ccm_source_sha256 required_sessions sessions_outside_explicit_link_bounds
names_missing_sessions names_ambiguous_sessions names_permco_mismatch_sessions
names_source_records identity_approved""".split()


def _ciks(values: pd.Series, label: str) -> None:
    if not values.str.fullmatch(r"\d{10}").all() or values.eq("0000000000").any():
        raise ValueError(f"{label} requires nonzero, ten-digit CIK strings")


def _source_csv(path, fields):
    frame, raw = _csv(path, fields)
    frame = frame[fields].copy()
    frame["source_file"] = Path(path).name
    frame["source_sha256"] = sha256(raw)
    # One-based CSV record numbers, including the header; not physical text lines.
    frame["source_record"] = range(2, len(frame) + 2)
    return frame, sha256(raw)


def _ccm_sources(paths):
    if not paths or len({Path(p).name for p in paths}) != len(paths):
        raise ValueError("Supply CCM sources with distinct filenames")
    frames, hashes = [], {}
    for path in sorted(paths, key=lambda p: Path(p).name):
        frame, digest = _source_csv(path, CCM_FIELDS)
        _ciks(frame.cik, "CCM.cik")
        if not frame.gvkey.str.fullmatch(r"\d{6}").all():
            raise ValueError("CCM GVKEY must remain a six-digit source string")
        for key in ["LPERMNO", "LPERMCO"]:
            _ids(frame.loc[frame[key].ne(""), key], key)
        if frame.LPERMNO.eq("").ne(frame.LPERMCO.eq("")).any():
            raise ValueError("CCM permanent security/company IDs must both be present or absent")
        iso_dates(frame.LINKDT, "CCM.LINKDT")
        explicit = frame.LINKENDDT.ne("E")
        iso_dates(frame.loc[explicit, "LINKENDDT"], "CCM.LINKENDDT")
        if (frame.loc[explicit, "LINKDT"] > frame.loc[explicit, "LINKENDDT"]).any():
            raise ValueError("Reversed CCM interval")
        frames.append(frame)
        hashes[Path(path).name] = digest
    combined = pd.concat(frames, ignore_index=True)
    if combined.duplicated(CCM_FIELDS).any():
        raise ValueError("Duplicate CCM evidence rows; reconcile the supplied exports")
    return combined, hashes


def _header(filing, cache):
    item = {"accession": filing["accessionNumber"], "filing_cik": filing["cik"],
            "source_url": filing["source_url"], "header_url": filing["header_url"],
            "header_sha256": filing["header_sha256"], "header_cik": "",
            "header_name": "", "header_identity_ok": False, "issue": ""}
    try:
        text = cached_body(Path(cache), filing["header_url"], filing["header_sha256"]).decode("utf-8")

        def one(pattern, source):
            values = re.findall(pattern, source, flags=re.I | re.S)
            if len(values) != 1:
                raise ValueError("Header needs one unambiguous filer and company identity")
            return values[0].strip()

        filer = one(r"<FILER>(.*?)</FILER>", text)
        company = one(r"<COMPANY-DATA>(.*?)</COMPANY-DATA>", filer)
        item["header_cik"] = one(r"<CIK>([^<\r\n]+)", company)
        item["header_name"] = one(r"<CONFORMED-NAME>([^<\r\n]+)", company)
        accession = one(r"<ACCESSION-NUMBER>([^<\r\n]+)", text)
        form = one(r"<TYPE>([^<\r\n]+)", text)
        if item["header_cik"] != filing["cik"] or accession != filing["accessionNumber"] or form != "10-K":
            raise ValueError("Header CIK, accession or form differs from the original 10-K record")
        item["header_identity_ok"] = True
    except (ValueError, OSError, KeyError, UnicodeError) as exc:
        item["issue"] = str(exc)
    return item


def _bound_filings(events, filings_path, audit_path):
    raw = Path(filings_path).read_bytes()
    digest = sha256(raw)
    if "filing_source_table_sha256" not in events or not events.filing_source_table_sha256.eq(digest).all():
        raise ValueError("Event queue is not bound to this filing table")
    audit_path = Path(audit_path)
    summary_raw = (audit_path / "audit_summary.json").read_bytes()
    summary = json.loads(summary_raw)
    evidence_raw = (audit_path / "filing_evidence.parquet").read_bytes()
    if summary.get("source_table_sha256") != digest or summary.get("evidence_table_sha256") != sha256(evidence_raw):
        raise ValueError("A matching source audit is required")
    pairs_raw = Path(filings_path).with_name("filing_pairs.parquet").read_bytes()
    if summary.get("pair_table_sha256") != sha256(pairs_raw):
        raise ValueError("A matching audited annual-pair table is required")
    pairs = pd.read_parquet(io.BytesIO(pairs_raw)).set_index("accession", verify_integrity=True)
    filings = pd.read_parquet(io.BytesIO(raw), columns=FILING_FIELDS).set_index("accessionNumber", drop=False, verify_integrity=True)
    evidence = pd.read_parquet(io.BytesIO(evidence_raw)).set_index("accession", verify_integrity=True)
    needed = ["previous_accession", "current_evidence_id", "previous_evidence_id"]
    if set(needed) - set(events):
        raise ValueError("Use the audit-bound event queue with current and previous evidence")
    for event in events.to_dict("records"):
        if (event["event_id"] not in pairs.index or
                pairs.loc[event["event_id"], "previous_accession"] != event["previous_accession"] or
                pairs.loc[event["event_id"], "cik"] != event["cik"]):
            raise ValueError("Event differs from the audited annual pair")
        for accession, key in [(event["event_id"], "current_evidence_id"), (event["previous_accession"], "previous_evidence_id")]:
            if accession not in filings.index or accession not in evidence.index:
                raise ValueError("Event references a filing outside the source audit")
            filing, record = filings.loc[accession], evidence.loc[accession]
            if filing.cik != event["cik"] or record.cik != event["cik"]:
                raise ValueError("Current and previous filings must retain the same original CIK")
            if (not re.fullmatch(r"[0-9a-f]{64}", str(event[key])) or
                    record.evidence_id != event[key] or record.automated_evidence_ok != True):  # noqa: E712
                raise ValueError("Event evidence is stale or has unresolved source-audit issues")
        if filings.loc[event["event_id"], "acceptance_timestamp"] != event["acceptance_timestamp"]:
            raise ValueError("Event acceptance timestamp differs from its source filing")
    return filings, {"filings": digest, "filing_pairs": sha256(pairs_raw), "audit_summary": sha256(summary_raw),
                     "filing_evidence": sha256(evidence_raw)}


def _candidate(link, event, sessions, names):
    history = names[names.permno.eq(link["LPERMNO"])]
    touched = history[(history.secinfostartdt <= sessions[-1]) & (history.secinfoenddt >= sessions[0])]
    missing, ambiguous, mismatch = 0, 0, 0
    for session in sessions:
        matches = touched[(touched.secinfostartdt <= session) & (touched.secinfoenddt >= session)]
        missing += int(matches.empty)
        ambiguous += int(len(matches) > 1)
        mismatch += int(len(matches) == 1 and matches.iloc[0].permco != link["LPERMCO"])
    outside = sum(s < link["LINKDT"] or (link["LINKENDDT"] != "E" and s > link["LINKENDDT"]) for s in sessions)
    return {"event_id": event["event_id"], "filing_cik": event["cik"],
            "candidate_permno": link["LPERMNO"], "ccm_header_cik": link["cik"],
            "ccm_header_name": link["conm"], "header_cik_differs": link["cik"] != event["cik"],
            "ccm_gvkey": link["gvkey"], "ccm_permco": link["LPERMCO"],
            "ccm_link_start": link["LINKDT"], "ccm_link_end_raw": link["LINKENDDT"],
            "ccm_end_marker_unresolved": link["LINKENDDT"] == "E",
            "ccm_link_type": link["LINKTYPE"], "ccm_link_primary": link["LINKPRIM"],
            "ccm_issue_id": link["LIID"], "ccm_source_file": link["source_file"],
            "ccm_source_record": link["source_record"], "ccm_source_sha256": link["source_sha256"],
            "required_sessions": len(sessions), "sessions_outside_explicit_link_bounds": outside,
            "names_missing_sessions": missing, "names_ambiguous_sessions": ambiguous,
            "names_permco_mismatch_sessions": mismatch,
            "names_source_records": json.dumps(touched.source_record.tolist()),
            "identity_approved": False}


def _html(queue, candidates, names, headers, summary):
    def link(url, label):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc not in {"www.sec.gov", "data.sec.gov"}:
            return escape(label) + " (unverified URL)"
        return f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'

    cards = []
    header_index = headers.set_index("accession")
    for row in queue.to_dict("records"):
        h = header_index.loc[row["event_id"]]
        p = header_index.loc[row["previous_accession"]]
        candidate_rows = candidates[candidates.event_id.eq(row["event_id"])]
        columns = ["candidate_permno", "ccm_header_cik", "ccm_header_name", "ccm_link_start",
                   "ccm_link_end_raw", "ccm_link_type", "ccm_link_primary",
                   "names_missing_sessions", "names_ambiguous_sessions", "names_permco_mismatch_sessions"]
        table = candidate_rows[columns].to_html(index=False, escape=True) if len(candidate_rows) else "<p>No candidate security.</p>"
        refs = set()
        for value in candidate_rows.names_source_records:
            refs.update(json.loads(value))
        dated = names[names.source_record.isin(refs)]
        historical = dated[["source_record", "permno", "secinfostartdt", "secinfoenddt", "issuernm",
                            "ticker", "cusip", "shareclass", "siccd"]].to_html(index=False, escape=True)
        cards.append(f'''<details><summary>{escape(h.header_name or row['cik'])}
 {escape(row['reference_session'])} — {escape(row['review_priority'].replace('_', ' '))}</summary>
<p>Event: {escape(row['event_id'])}. Original filing CIK: {escape(row['cik'])}.
 Required sessions: {row['required_sessions']}, {escape(row['control_history_start'])} through {escape(row['label_end'])}.</p>
<p>{link(h.source_url, 'Current filing')} · {link(h.header_url, 'Current SEC header')} ·
 {link(p.source_url, 'Previous filing')} · {link(p.header_url, 'Previous SEC header')}</p>
<p>SEC filer: {escape(h.header_name)} ({escape(h.header_cik)}).
 Previous filer: {escape(p.header_name)} ({escape(p.header_cik)}).
 Header issues: {escape(h.issue or p.issue or 'none detected')}.</p>
<h3>Candidate CCM records</h3><div class="table">{table}</div>
<h3>Dated security descriptions</h3><div class="table">{historical}</div>
<p>Review fingerprint: <code>{row['evidence_id']}</code></p></details>''')
    return f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Historical identity review</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;max-width:1200px;margin:40px auto;padding:0 22px;color:#17283b;background:#fafcff}}
h1{{line-height:1.2}}details{{background:white;border:1px solid #ccd5df;border-radius:8px;padding:16px;margin:12px 0}}
summary{{cursor:pointer;font-weight:650}}.table{{overflow-x:auto}}table{{border-collapse:collapse;font-size:13px}}
th,td{{padding:7px 10px;border:1px solid #ccd5df;text-align:left}}th{{background:#edf2f8}}a{{color:#1554a0}}
code{{overflow-wrap:anywhere}}.note{{padding:16px;background:#fff4da;border-left:4px solid #936000}}</style>
<h1>Historical identity review</h1><p>{summary['events']} filing events across {summary['issuers']} issuers.
 {summary['filing_headers_checked']} cached SEC headers checked. Human approvals: 0.</p>
<p class="note">Candidate records only. CCM dates describe its company/security link; header CIKs are not established historical CIK intervals.
 Literal E end markers remain unresolved. No security class or CIK link is approved here.</p>
<p>Open both SEC filings and compare the registered security with the dated Names records.
 Resolve multiple candidates, identifier changes and interval gaps. Record the source, date range,
 share-class rationale and reviewer in <code>identity_reviews.template.jsonl</code>.
 This packet contains no market returns and does not replace the separate filing or arithmetic audits.</p>
{''.join(cards)}</html>'''


def build_identity_review(events_path, filings_path, audit_path, companies_path,
                          ccm_paths, names_path, cache, output, config):
    """Build an immutable private review packet using source-bound development events."""
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; preserve the prior identity review")
    # Holdout refusal precedes all vendor and cached-header reads.
    events_raw, events, windows = load_development_events(events_path, config)
    if not events.data_kind.eq("REAL_FILING_EVENTS").all():
        raise ValueError("Identity review requires real development event metadata")
    filings, source_hashes = _bound_filings(events, filings_path, audit_path)
    companies_raw = Path(companies_path).read_bytes()
    companies = pd.DataFrame(json.loads(companies_raw)["companies"])
    _ciks(companies.cik, "Company configuration")
    if companies.cik.duplicated().any() or set(events.cik) - set(companies.cik):
        raise ValueError("Every event requires one configured original issuer CIK")
    companies = companies.set_index("cik")
    ccm, ccm_hashes = _ccm_sources(ccm_paths)
    names, names_hash = _source_csv(names_path, NAMES_FIELDS)
    for field in ["permno", "permco"]:
        _ids(names[field], f"Names.{field}")
    for field in ["secinfostartdt", "secinfoenddt"]:
        iso_dates(names[field], f"Names.{field}")
    if (names.secinfostartdt > names.secinfoenddt).any():
        raise ValueError("Reversed Names interval")
    accessions = sorted(set(events.event_id) | set(events.previous_accession))
    headers = pd.DataFrame([_header(filings.loc[a].to_dict(), cache) for a in accessions])
    header_index = headers.set_index("accession")
    bindings = {**source_hashes, "events": sha256(events_raw), "companies": sha256(companies_raw),
                "ccm": ccm_hashes, "names": names_hash, "protocol": canonical_hash(config),
                "review_code": sha256(Path(__file__).read_bytes())}
    rows, candidate_rows = [], []
    for event, window in zip(events.to_dict("records"), windows, strict=True):
        sessions = list(control_sessions(window)) + [window.reference_session] + list(window.return_sessions)
        search_ciks = [event["cik"]]
        discovery = companies.loc[event["cik"]].get("discovery_cik")
        if isinstance(discovery, str) and discovery != event["cik"]:
            _ciks(pd.Series([discovery]), "Configured discovery CIK")
            search_ciks.append(discovery)
        # This is a candidate search, never a ticker join or a share-class selection.
        matches = ccm[ccm.cik.isin(search_ciks) & ccm.LPERMNO.ne("") &
                      (ccm.LINKDT <= sessions[-1]) &
                      (ccm.LINKENDDT.eq("E") | (ccm.LINKENDDT >= sessions[0]))]
        candidates = [_candidate(link, event, sessions, names) for link in matches.to_dict("records")]
        candidate_rows.extend(candidates)
        ids = sorted({r["candidate_permno"] for r in candidates})
        current, previous = header_index.loc[event["event_id"]], header_index.loc[event["previous_accession"]]
        header_ok = bool(current.header_identity_ok and previous.header_identity_ok)
        coverage_issue = any(r[k] for r in candidates for k in ["names_missing_sessions",
                             "names_ambiguous_sessions", "names_permco_mismatch_sessions",
                             "sessions_outside_explicit_link_bounds"])
        differs = any(r["header_cik_differs"] for r in candidates)
        priority = ("resolve_sec_header" if not header_ok else "resolve_missing_candidate" if not ids else
                    "resolve_multiple_candidates" if len(candidates) > 1 else "resolve_header_cik" if differs else
                    "resolve_interval_coverage" if coverage_issue else "review_historical_identity")
        row = {"event_id": event["event_id"], "cik": event["cik"],
               "previous_accession": event["previous_accession"],
               "reference_session": window.reference_session, "control_history_start": sessions[0],
               "controls_asof": window.controls_through, "label_end": window.label_end,
               "required_sessions": len(sessions), "candidate_link_rows": len(candidates),
               "candidate_security_count": len(ids), "candidate_permnos": json.dumps(ids),
               "header_identity_ok": header_ok, "ccm_header_cik_differs": differs,
               "interval_coverage_issue": bool(coverage_issue), "review_priority": priority,
               "identity_review": "pending", "identity_approved": False}
        row["evidence_id"] = fingerprint({"bindings": bindings, "event": event, "review": row,
                                         "candidates": candidates,
                                         "headers": [current.to_dict(), previous.to_dict()]})
        rows.append(row)
    queue = pd.DataFrame(rows).sort_values(["review_priority", "cik", "reference_session", "event_id"])
    candidates = pd.DataFrame(candidate_rows, columns=CANDIDATE_FIELDS)
    summary = {"schema_version": 1, "data_kind": "HISTORICAL_IDENTITY_REVIEW_NOT_APPROVED",
               "events": len(queue), "issuers": int(queue.cik.nunique()),
               "filing_headers_checked": len(headers),
               "filing_headers_identity_consistent": int(headers.header_identity_ok.sum()),
               "ccm_source_rows": len(ccm), "ccm_rows_without_security_id": int(ccm.LPERMNO.eq("").sum()),
               "names_source_rows": len(names), "candidate_rows": len(candidates),
               "events_with_one_candidate_security": int(queue.candidate_security_count.eq(1).sum()),
               "events_without_candidate_security": int(queue.candidate_security_count.eq(0).sum()),
               "events_with_multiple_candidate_rows": int(queue.candidate_link_rows.gt(1).sum()),
               "events_with_header_cik_difference": int(queue.ccm_header_cik_differs.sum()),
               "events_with_interval_coverage_issues": int(queue.interval_coverage_issue.sum()),
               "candidate_rows_with_unresolved_end_marker": int(candidates.ccm_end_marker_unresolved.sum()),
               "review_priority_counts": queue.review_priority.value_counts().to_dict(),
               "source_hashes": bindings, "market_returns_loaded": False,
               "human_reviews_completed": 0, "approved_security_links_created": 0,
               "model_ready": False, "final_period_opened": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".identity-review-", dir=output.parent) as temp:
        stage = Path(temp) / "packet"
        stage.mkdir()
        tables = {"event_identity_queue": queue, "candidate_links": candidates,
                  "filing_headers": headers, "ccm_evidence": ccm, "names_evidence": names}
        for name, frame in tables.items():
            frame.to_parquet(stage / f"{name}.parquet", index=False)
        reviews = [{"event_id": r["event_id"], "evidence_id": r["evidence_id"],
                    "identity_verdict": "pending", "selected_permno": "", "historical_cik_evidence": "",
                    "valid_from": "", "valid_to": "", "share_class_rationale": "",
                    "source_references": [], "reviewer": "", "reviewer_type": "",
                    "reviewed_at": "", "notes": ""} for r in queue.to_dict("records")]
        (stage / "identity_reviews.template.jsonl").write_text("".join(json.dumps(r) + "\n" for r in reviews))
        (stage / "identity_review.html").write_text(_html(queue, candidates, names, headers, summary))
        summary["files"] = {p.name: sha256(p.read_bytes()) for p in sorted(stage.iterdir())}
        (stage / "identity_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        stage.rename(output)
    return summary
