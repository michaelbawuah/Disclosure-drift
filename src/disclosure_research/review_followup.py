"""Supplement a frozen review packet without changing its selection or verdicts.

This is an offline review aid. Real, artificial-clock and synthetic examples are
kept distinct. No output from this module is an approved research observation.
"""

import csv
import io
import json
import tempfile
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd

from .audit import select_review_pairs
from .controls import control_sessions, make_controls
from .identity_review import _bound_filings, _header
from .labels import load_development_events
from .market import make_label
from .market_data import fingerprint, sha256
from .pilot_audit import MEASURES, independent_trace, read_reviews, require
from .protocol import canonical_hash, load_protocol, verify_lock
from .timing import NY, event_window


def records(raw):
    """Use CSV records, counting the header as record 1 (not physical lines)."""
    return [dict(r, source_record=i) for i, r in
            enumerate(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))), 2)]


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def check_trace_sources(trace, security, daily, names, window):
    """Compare every cited value to its literal source, not a staged table."""
    def at(rows, number):
        require(type(number) is int and 2 <= number <= len(rows) + 1, "Invalid CSV record")
        return rows[number - 2]

    require([r["session"] for r in trace["controls"]] == list(control_sessions(window)),
            "Control calendar differs")
    require([r["session"] for r in trace["label_rows"]] == list(window.return_sessions),
            "Label calendar differs")
    require(trace["reference_session_excluded_from_label"] == window.reference_session,
            "Reference session differs")
    for entry in trace["controls"]:
        row = at(daily, entry["source_record"])
        require((row["PERMNO"], row["DlyCalDt"], row["DlyRet"]) ==
                (security, entry["session"], entry["return"]), "Control source row differs")
    for entry in trace["label_rows"]:
        # Fixed sample has no terminal cases. Cash examples are checked separately.
        require(not entry["cash_continuation"], "Use the terminal-source checker for cash")
        row = at(daily, entry["source_record"])
        require((row["PERMNO"], row["DlyCalDt"], row["DlyRet"]) ==
                (security, entry["session"], entry["stock_return"]), "Stock source row differs")
        row = at(daily, entry["benchmark_source_record"])
        require((row["DlyCalDt"], row["vwretd"]) ==
                (entry["session"], entry["benchmark_return"]), "Benchmark source row differs")
    snap = trace["snapshot"]
    row = at(daily, snap["source_record"])
    require((row["PERMNO"], row["DlyCalDt"], row["DlyCap"]) ==
            (security, window.controls_through, snap["source_cap_thousands"]),
            "Capitalization source row differs")
    name = at(names, snap["names_record"])
    require((name["permno"], name["permco"], name["siccd"], name["secinfostartdt"],
             name["secinfoenddt"]) ==
            (security, row["PERMCO"], trace["industry"], snap["names_start"], snap["names_end"]),
            "Names source row differs")
    require(snap["session"] == window.controls_through and
            name["secinfostartdt"] <= snap["session"] <= name["secinfoenddt"],
            "Names interval does not cover snapshot")
    return {"control_rows": 60, "stock_label_rows": 20, "benchmark_rows": 20,
            "capitalization_rows": 1, "names_rows": 1}


def frozen_pairs(pair_frame, selected_raw):
    """Check the existing 30-pair list; never replace it with another selection."""
    expected = select_review_pairs(pair_frame)
    selected = pd.read_csv(io.BytesIO(selected_raw), dtype=str, keep_default_na=False)
    require(selected.to_dict("records") == expected.astype(str).to_dict("records"),
            "Frozen filing-pair selection differs")
    return selected


def page(title, body):
    return ("<!doctype html><html lang='en'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{escape(title)}</title><style>"
            "body{font:16px system-ui;line-height:1.55;max-width:1450px;margin:32px auto;"
            "padding:0 20px;color:#172b40;background:#f5f7fa}details,article{background:white;"
            "padding:18px;margin:14px 0;border:1px solid #ccd6e0;border-radius:8px}"
            "summary{cursor:pointer;font-weight:650}table{border-collapse:collapse;font-size:13px}"
            "td,th{padding:7px;border:1px solid #ccd6e0;text-align:left}pre{white-space:pre-wrap;"
            "overflow-wrap:anywhere;font-size:13px}a{color:#1556a2}code{overflow-wrap:anywhere}"
            ".pair{display:grid;grid-template-columns:1fr 1fr;gap:18px}.scroll{overflow:auto}"
            "@media(max-width:850px){.pair{grid-template-columns:1fr}}"
            f"</style><h1>{escape(title)}</h1>{body}</html>")


def table(rows):
    return '<div class="scroll">' + pd.DataFrame(rows).to_html(index=False, escape=True) + '</div>'


def filing_packet(filings, evidence, selected):
    cards, needed = [], set()
    for number, pair in enumerate(selected.to_dict("records"), 1):
        sides = []
        for side, accession in [("Previous", pair["previous_accession"]),
                                ("Current", pair["accession"])]:
            needed.add(accession)
            f, e = filings.loc[accession], evidence.loc[accession]
            require(f.cik == e.cik == pair["cik"], "Pair issuer differs")
            require(sha256(f.risk_text.encode()) == e.risk_text_sha256,
                    "Extracted risk text differs from audited evidence")
            links = ' · '.join(f'<a href="{escape(str(e[key]), quote=True)}">{label}</a>'
                               for key, label in [("source_url", "Complete 10-K"),
                                                  ("risk_source_url", "Risk source"),
                                                  ("header_url", "SEC header")])
            timing = {key: str(e[key]) for key in ["acceptance_timestamp", "api_timestamp",
                       "api_header_difference_seconds", "controls_through", "reference_session",
                       "label_end", "resolution_method", "resolution_rule_id"]}
            context = {key: str(e[key]) for key in ["start_context", "section_start",
                                                  "section_end", "end_context"]}
            sides.append(f'<article><h3>{side}: {escape(accession)}</h3><p>{links}</p>'
                         f'<p>Evidence: <code>{escape(e.evidence_id)}</code></p>'
                         f'<pre>{escape(json.dumps(timing, indent=2))}</pre>'
                         f'<h4>Boundary context</h4><pre>{escape(json.dumps(context, indent=2))}</pre>'
                         '<details><summary>Complete extracted risk section</summary>'
                         f'<pre>{escape(f.risk_text)}</pre></details>'
                         f'<p>Cautions: {escape(", ".join(e.cautions))}. Review: pending.</p></article>')
        cards.append(f'<details data-pair="{number}"><summary>{number:02d} · '
                     f'{escape(filings.loc[pair["accession"], "name"])} · '
                     f'{escape(pair["previous_accession"])} → {escape(pair["accession"])}</summary>'
                     '<div class="pair">' + ''.join(sides) + '</div></details>')
    intro = (f'<p><strong>{len(selected)} frozen pairs; {len(needed)} distinct filings.</strong> '
             'Same selection and evidence IDs as the expanded filing audit. No new sample.</p>'
             '<p>Read both original SEC documents. Check Item 1A boundaries and completeness, '
             'reference/exhibit resolution, the SEC acceptance header and exchange dates. '
             'The excerpts and extracted text aid review; they do not replace the original sources.</p>'
             '<p>Record one boundary/timing review per distinct accession in '
             '<code>filing_reviews.template.jsonl</code>. Repeated filings need one review. '
             'The registered reference-resolution packet remains a separate review requirement.</p>')
    templates = [{"accession": key, "evidence_id": evidence.loc[key, "evidence_id"],
                  "reviewer": "", "reviewer_type": "", "reviewed_at": "",
                  "boundary_verdict": "pending", "timing_verdict": "pending", "notes": ""}
                 for key in sorted(needed)]
    return page("30-pair filing review", intro + ''.join(cards)), templates


def short_history_case():
    window = event_window(datetime(2018, 1, 10, 12, tzinfo=NY))
    dates = control_sessions(window)
    stock = pd.DataFrame({"security_id": "SYNTHETIC", "session": dates[1:],
                          "total_return": 0.001, "terminal_event": False})
    snapshots = pd.DataFrame([{"security_id": "SYNTHETIC", "session": window.controls_through,
                               "market_cap_usd": 250_000_000.0, "industry": "invented",
                               "industry_scheme": "invented"}])
    try:
        make_controls(stock, snapshots, window)
    except ValueError as exc:
        require(str(exc).startswith("Missing control return sessions:"), "Unexpected rejection")
        return {"case_id": "synthetic-59-control-sessions", "kind": "SYNTHETIC_FAULT_INJECTION",
                "control_sessions_supplied": 59, "control_sessions_required": 60,
                "missing_session": dates[0], "expected_rejection": str(exc),
                "automated_check_passed": True, "real_small_cap_coverage": False}
    raise ValueError("Incomplete control history was accepted")


def build_followup(root, output, recheck_results=None, draft=None):
    root, output = Path(root), Path(output)
    require(not output.exists(), "Output exists; preserve previous reviews")
    config = load_protocol(root / "configs/protocol.json")
    verify_lock(config, root / "configs/protocol.lock.json")
    original = root / "data/reviews/market-pilot-m5-v1"
    receipt = json.loads((original / "audit_summary.json").read_text())
    sources = receipt["source_hashes"]
    require(sources["protocol"] == canonical_hash(config), "Protocol changed")
    for name, digest in receipt["files"].items():
        require(Path(name).name == name and sha256((original / name).read_bytes()) == digest,
                f"Original packet changed: {name}")
    for name, digest in {"pilot_audit.py": sources["audit_code"],
                         **sources["calculation_code"]}.items():
        require(sha256(Path(__file__).with_name(name).read_bytes()) == digest,
                f"Original calculation code changed: {name}")
    paths = {"raw_daily": root / "data/raw/wrds/2026-10-10/crsp_daily_pilot.csv",
             "raw_names": root / "data/raw/wrds/2026-10-09/crsp_names_pilot.csv",
             "events": root / "data/processed/pilot-resolved/label_events.parquet"}
    for key, path in paths.items():
        require(sha256(path.read_bytes()) == sources[key], f"Source changed: {key}")
    _, events, windows = load_development_events(paths["events"], config)
    clocks = dict(zip(events.event_id, windows, strict=True))
    filings, bindings = _bound_filings(events, root / "data/processed/pilot-resolved/filings.parquet",
                                       root / "outputs/audit-pilot-resolved")
    require(all(sources[key] == value for key, value in bindings.items()), "Filing audit changed")
    filings = pd.read_parquet(root / "data/processed/pilot-resolved/filings.parquet").set_index(
        "accessionNumber", drop=False, verify_integrity=True)
    evidence = pd.read_parquet(root / "outputs/audit-pilot-resolved/filing_evidence.parquet").set_index("accession")
    cases = pd.read_parquet(original / "candidate_calculations.parquet").set_index("event_id", drop=False)
    traces = jsonl(original / "independent_traces.jsonl")
    daily, names = (records(paths[key].read_bytes()) for key in ["raw_daily", "raw_names"])
    checks = []
    for trace in traces:
        row = cases.loc[trace["event_id"]]
        require(trace["evidence_id"] == row.arithmetic_evidence_id, "Trace evidence differs")
        checks.append({"event_id": trace["event_id"], "evidence_id": trace["evidence_id"],
                       "source_rows_match": True,
                       **check_trace_sources(trace, row.candidate_permno, daily, names, clocks[row.event_id])})
    submitted = read_reviews(draft, jsonl(original / "trace_reviews.template.jsonl"))
    # This helper never ingests a completed verdict or changes original review counts.
    require(all(r["controls_verdict"] == r["label_verdict"] == "pending" for r in submitted),
            "Use audit-pilot-market to ingest completed reviews")
    recheck = None
    if recheck_results:
        result = json.loads(Path(recheck_results).read_text())
        require(len(result) == len(traces) and
                {(r["event_id"], r["evidence_id"]) for r in result} ==
                {(r["event_id"], r["evidence_id"]) for r in traces}, "Recheck set differs")
        require(all(not r["issues"] and 0 <= r["max_diff"] <= 1e-12 for r in result),
                "Recheck has failures or exceeds strict tolerance")
        recheck = {"traces_passed": len(result), "observed_max_abs_error": max(r["max_diff"] for r in result),
                   "results_sha256": sha256(Path(recheck_results).read_bytes()),
                   "submitted_draft_sha256": sha256(Path(draft).read_bytes()) if draft else None}

    benchmark = {}
    for row in daily:
        require(row["DlyCalDt"] not in benchmark or
                benchmark[row["DlyCalDt"]]["vwretd"] == row["vwretd"], "Conflicting benchmarks")
        benchmark.setdefault(row["DlyCalDt"], row)
    # Earliest flagged event; selection does not use returns or model outcomes.
    mismatch = cases[cases.header_cik_differs].reset_index(drop=True).sort_values(
        ["reference_session", "event_id"])
    require(not mismatch.empty, "Expected header-CIK case absent")
    xom = mismatch.iloc[0]
    xtrace = independent_trace(daily, benchmark, names, xom.candidate_permno, clocks[xom.event_id])
    check_trace_sources(xtrace, xom.candidate_permno, daily, names, clocks[xom.event_id])
    require(all(abs(xom[k] - float(xtrace["independent_values"][k])) <= 1e-12 for k in MEASURES),
            "Supplemental arithmetic differs")
    identity = root / "data/reviews/identity-pilot-v2"
    identity_raw = (identity / "identity_summary.json").read_bytes()
    require(sha256(identity_raw) == sources["identity_receipt"], "Identity receipt changed")
    links_raw = (identity / "candidate_links.parquet").read_bytes()
    require(sha256(links_raw) == json.loads(identity_raw)["files"]["candidate_links.parquet"],
            "Candidate links changed")
    links = pd.read_parquet(io.BytesIO(links_raw))
    matching = links[links.event_id.eq(xom.event_id)]
    require(len(matching) == 1 and matching.iloc[0].candidate_permno == xom.candidate_permno,
            "Supplemental candidate identity differs")
    supplement = [{"case_id": "vendor-header-cik-difference", "kind": "REAL_PROVISIONAL_FILING_EVENT",
                   "event_id": xom.event_id, "filing_cik": xom.cik, "candidate_permno": xom.candidate_permno,
                   "ccm_header_cik": matching.iloc[0].ccm_header_cik,
                   "ccm_link_end_raw": matching.iloc[0].ccm_link_end_raw,
                   "original_arithmetic_evidence_id": xom.arithmetic_evidence_id,
                   "selection": "earliest flagged event by reference session and accession",
                   "automated_check_passed": True, "identity_approved": False, **xtrace}]
    agents = []
    for trace in traces:
        row = cases.loc[trace["event_id"]]
        if row.event_id[:10] != row.cik:
            header = _header(filings.loc[row.event_id].to_dict(), root / "data/raw/sec_cache")
            require(header["header_identity_ok"], "Original SEC filer identity failed")
            agents.append({"event_id": row.event_id, "accession_prefix": row.event_id[:10],
                           "issuer_cik": row.cik, "header_cik": header["header_cik"],
                           "header_url": header["header_url"], "header_sha256": header["header_sha256"]})
    wfm_dir = root / "data/reviews/wfm-terminal-v1"
    wreceipt = json.loads((wfm_dir / "qa_summary.json").read_text())
    require(sha256((wfm_dir / "qa_trace.json").read_bytes()) == wreceipt["private_trace_sha256"],
            "WFM trace changed")
    for filename, item in wreceipt["inputs"].items():
        require(sha256((paths["raw_daily"].parent / filename).read_bytes()) == item["sha256"],
                "WFM source changed")
    wfm = records((paths["raw_daily"].parent / "crsp_delisting_check_permno.csv").read_bytes())
    stock = pd.DataFrame({"security_id": [r["PERMNO"] for r in wfm],
                          "session": [r["DlyCalDt"] for r in wfm],
                          "total_return": [float(r["DlyRet"]) for r in wfm],
                          "terminal_event": [r["DlyDelFlg"] == "Y" for r in wfm]})
    market = pd.DataFrame({"session": list(benchmark),
                           "total_return": [float(r["vwretd"]) for r in benchmark.values()]})
    terminal = wfm[-1]
    require(terminal["DlyDelFlg"] == "Y", "WFM terminal row absent")
    by_date = {r["DlyCalDt"]: r for r in wfm}
    for case in json.loads((wfm_dir / "qa_trace.json").read_text())["traces"]:
        window = event_window(datetime.fromisoformat(case["acceptance_timestamp"]))
        result = make_label(stock, market, window)
        require(all(abs(result[k] - case["result"][k]) <= 1e-12
                    for k in ["stock_return", "market_return", "target"]), "WFM labels differ")
        rows = []
        for session in window.return_sessions:
            cash = session > terminal["DlyCalDt"]
            source = None if cash else by_date[session]
            rows.append({"session": session, "source_record": None if cash else source["source_record"],
                         "stock_return": "0" if cash else source["DlyRet"], "cash_continuation": cash,
                         "benchmark_return": benchmark[session]["vwretd"],
                         "benchmark_source_record": benchmark[session]["source_record"]})
        require(sum(r["cash_continuation"] for r in rows) == case["cash_continuation_sessions"],
                "Cash continuation count differs")
        supplement.append({"case_id": "wfm-" + case["case"], "kind": "REAL_RETURNS_ARTIFICIAL_EVENT_CLOCK",
                           "automated_check_passed": True, "controls_reviewable": False,
                           "stock_source": "crsp_delisting_check_permno.csv", "benchmark_source": "crsp_daily_pilot.csv",
                           "reference_session": window.reference_session, "label_rows": rows,
                           "terminal_row": terminal, "terminal_source_record": terminal["source_record"],
                           "cash_payoff_usd": "42.00", "source_references": wreceipt["source_references"], **case})
    supplement.append(short_history_case())
    supplemental_reviews = []
    for case in supplement:
        case["evidence_id"] = fingerprint({"original_receipt": sha256((original / "audit_summary.json").read_bytes()),
                                           "wfm_receipt": sha256((wfm_dir / "qa_summary.json").read_bytes()),
                                           "case": case, "code": sha256(Path(__file__).read_bytes())})
        supplemental_reviews.append({"case_id": case["case_id"], "evidence_id": case["evidence_id"],
                                     "verdict": "pending", "reviewer": "", "reviewer_type": "",
                                     "reviewed_at": "", "source_references": [], "notes": ""})
    raw_pairs = (root / "reports/expanded_review_pairs.csv").read_bytes()
    selected = frozen_pairs(pd.read_parquet(root / "data/processed/pilot-resolved/filing_pairs.parquet"), raw_pairs)
    filing_html, filing_reviews = filing_packet(filings, evidence, selected)
    cards = []
    for case in supplement:
        detail = {k: v for k, v in case.items() if k not in {"controls", "label_rows"}}
        cards.append(f'<details><summary>{escape(case["case_id"])} · {escape(case["kind"])}</summary>'
                     f'<pre>{escape(json.dumps(detail, indent=2))}</pre>' +
                     (table(case["controls"]) if "controls" in case else '') +
                     (table(case["label_rows"]) if "label_rows" in case else '') + '</details>')
    edge_html = page("Supplemental edge-case review", '<p><strong>Four directed cases, separate from '
                     'the unchanged 20 fixed traces.</strong> All human verdicts and identities remain pending. '
                     'The two WFM clocks are label-only QA with actual returns; the 59-session case is synthetic. '
                     'No actual small-cap market history is available in this pilot.</p>'
                     '<p>Cash rows have no stock CSV record: zero is an explicit post-termination convention. '
                     'Benchmark observations continue on every session; they are never filled. '
                     'Record pending reviews in <code>edge_reviews.template.jsonl</code>; these do not '
                     'count toward the fixed 20-event gate.</p>' + ''.join(cards) +
                     '<h2>Already in the fixed sample: accession-prefix differences</h2>' + table(agents) +
                     '<p>Accession prefixes identify the submitting login CIK, which can be a filing agent. '
                     'The SEC FILER company CIK above matches the issuer. This is distinct from a CCM '
                     'current-header CIK differing from the historical issuer.</p>')
    summary = {"status": "review_followup_delivered_M5_still_pending", "fixed_traces_unchanged": len(traces),
               "fixed_permnos": int(cases.loc[[t["event_id"] for t in traces]].candidate_permno.nunique()),
               "source_row_checks_passed": len(checks),
               "source_record_references_checked": {k: sum(c[k] for c in checks)
                                                     for k in checks[0] if k.endswith("_rows")},
               "source_checks_reviewer_type": "assistant", "submitted_recheck": recheck,
               "filing_pairs": len(selected), "distinct_pair_filings": len(filing_reviews),
               "filing_pair_selection_sha256": sha256(raw_pairs),
               "supplemental_cases": [{k: c[k] for k in ["case_id", "kind", "automated_check_passed"]}
                                      for c in supplement],
               "existing_accession_prefix_cases": len(agents), "actual_small_cap_coverage_added": False,
               "draft_reviews_promoted": False, "human_review_counts_changed": False,
               "milestone_05_complete": False, "model_ready": False, "final_period_opened": False,
               "original_arithmetic_receipt_sha256": sha256((original / "audit_summary.json").read_bytes()),
               "original_trace_sha256": receipt["files"]["independent_traces.jsonl"],
               "source_hashes": {k: sources[k] for k in ["raw_daily", "raw_names", "protocol"]},
               "generator_sha256": sha256(Path(__file__).read_bytes())}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        folder = Path(temporary) / "packet"
        folder.mkdir()
        (folder / "filing_pairs_30.html").write_text(filing_html)
        (folder / "edge_cases.html").write_text(edge_html)
        (folder / "filing_pairs_30.csv").write_bytes(raw_pairs)
        for name, rows in [("filing_reviews.template.jsonl", filing_reviews),
                           ("edge_reviews.template.jsonl", supplemental_reviews),
                           ("edge_traces.jsonl", supplement), ("source_row_checks.jsonl", checks)]:
            (folder / name).write_text(''.join(json.dumps(r, allow_nan=False) + '\n' for r in rows))
        summary["files"] = {p.name: sha256(p.read_bytes()) for p in sorted(folder.iterdir())}
        (folder / "followup_summary.json").write_text(json.dumps(summary, indent=2) + '\n')
        require(not output.exists(), "Output appeared during build")
        folder.rename(output)
    return summary
