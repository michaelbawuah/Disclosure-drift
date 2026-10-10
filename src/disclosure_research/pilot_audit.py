"""Source-bound arithmetic evidence for provisional pilot security candidates.

This creates review calculations, never approved links or model-ready observations.
The independent calculation uses literal CSV decimals, not normalized returns.
"""

import csv
import io
import json
import math
import tempfile
from datetime import datetime
from decimal import Decimal, localcontext
from html import escape
from pathlib import Path

import duckdb
import pandas as pd

from .controls import control_sessions, make_controls
from .identity_review import _bound_filings
from .labels import load_development_events
from .market import make_label
from .market_data import development_return_end, fingerprint, iso_dates, sha256
from .protocol import canonical_hash

KIND = "PROVISIONAL_CANDIDATE_ARITHMETIC_QA"
MEASURES = ("stock_return", "market_return", "target", "momentum_20", "momentum_60",
            "volatility_20", "log_market_cap")
TOLERANCE = 1e-12


def require(condition, message):
    if not condition:
        raise ValueError(message)


def csv_rows(raw):
    return [dict(row, source_record=i) for i, row in
            enumerate(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))), 2)]


def product(values):
    value = Decimal(1)
    for item in values:
        value *= 1 + Decimal(item)
    return value - 1


def independent_trace(records, benchmark, names, security, window):
    """Decimal reference arithmetic, retaining exact raw row references."""
    history_dates = control_sessions(window)
    stock = {r["DlyCalDt"]: r for r in records if r["PERMNO"] == security}
    require(window.reference_session in stock, "Missing raw reference-session record")
    history = [stock[s] for s in history_dates if s in stock]
    require(len(history) == 60, "Missing raw control sessions")
    require(all(r["DlyDelFlg"] == "N" for r in history), "Terminal event in raw controls")
    terminals = [s for s, r in stock.items() if r["DlyDelFlg"] == "Y"]
    require(len(terminals) <= 1, "Multiple raw terminal events")
    terminal = terminals[0] if terminals else None
    require(not terminal or terminal > window.reference_session, "Raw terminal precedes entry")
    require(not terminal or not any(s > terminal for s in stock), "Raw rows after terminal")
    label_rows, stock_values, market_values = [], [], []
    for session in window.return_sessions:
        require(session in benchmark, "Missing raw benchmark session")
        cash = bool(terminal and session > terminal)
        require(cash or session in stock, "Missing raw stock label session")
        row = None if cash else stock[session]
        value = "0" if cash else row["DlyRet"]
        stock_values.append(value)
        market_values.append(benchmark[session]["vwretd"])
        label_rows.append({"session": session, "source_record": None if cash else row["source_record"],
                           "stock_return": value, "cash_continuation": cash,
                           "benchmark_return": benchmark[session]["vwretd"],
                           "benchmark_source_record": benchmark[session]["source_record"]})
    snapshot = stock[window.controls_through]
    dated = [r for r in names if r["permno"] == security and
             r["secinfostartdt"] <= window.controls_through <= r["secinfoenddt"]]
    require(len(dated) == 1 and dated[0]["permco"] == snapshot["PERMCO"],
            "Raw snapshot has missing/ambiguous dated Names or PERMCO disagreement")
    with localcontext() as context:
        context.prec = 40
        returns = [Decimal(r["DlyRet"]) for r in history]
        recent = returns[-20:]
        mean = sum(recent) / 20
        values = {"stock_return": product(stock_values), "market_return": product(market_values),
                  "momentum_20": product(recent), "momentum_60": product(returns),
                  "volatility_20": (sum((x - mean) ** 2 for x in recent) / 19).sqrt(),
                  "log_market_cap": (Decimal(snapshot["DlyCap"]) * 1000).ln()}
        values["target"] = values["stock_return"] - values["market_return"]
    return {"independent_values": {key: str(value) for key, value in values.items()},
            "industry": dated[0]["siccd"], "industry_scheme": "SIC",
            "controls": [{"session": r["DlyCalDt"], "source_record": r["source_record"],
                          "return": r["DlyRet"]} for r in history],
            "snapshot": {"source_record": snapshot["source_record"], "session": window.controls_through,
                         "source_cap_thousands": snapshot["DlyCap"], "names_record": dated[0]["source_record"],
                         "names_start": dated[0]["secinfostartdt"], "names_end": dated[0]["secinfoenddt"]},
            "reference_session_excluded_from_label": window.reference_session,
            "label_rows": label_rows}


def read_reviews(path, templates):
    reviews = {r["event_id"]: r.copy() for r in templates}
    if path is None:
        return list(reviews.values())
    seen = set()
    for line in Path(path).read_text().splitlines():
        row = json.loads(line)
        key = row.get("event_id")
        require(key in reviews and key not in seen, "Unknown or duplicate trace review")
        seen.add(key)
        require(row.get("evidence_id") == reviews[key]["evidence_id"], "Stale trace review evidence")
        verdicts = [row.get(c) for c in ["controls_verdict", "label_verdict"]]
        require(all(v in {"pending", "pass", "fail"} for v in verdicts), "Invalid trace verdict")
        if any(v != "pending" for v in verdicts):
            require(row.get("reviewer_type") in {"human", "assistant"}, "Declare review type")
            require(all(isinstance(row.get(k), str) and row[k].strip()
                        for k in ["reviewer", "notes", "reviewed_at"]), "Completed reviews need identity and notes")
            stamp = datetime.fromisoformat(row["reviewed_at"].replace("Z", "+00:00"))
            require(stamp.tzinfo is not None, "Review timestamp needs timezone")
            refs = row.get("source_references")
            require(isinstance(refs, list) and bool(refs) and
                    all(isinstance(x, str) and x.strip() for x in refs), "Record review source references")
        reviews[key].update({k: row[k] for k in reviews[key] if k in row})
    return list(reviews.values())


def html_packet(cases, traces, reviews, summary):
    by_id = {r["event_id"]: r for r in reviews}
    parts = []
    for trace in traces:
        row = cases.loc[trace["event_id"]]
        metrics = pd.DataFrame([{"Measure": k, "Pipeline": row[k],
                                 "Independent decimal": trace["independent_values"][k]}
                                for k in MEASURES]).to_html(index=False, escape=True)
        history = pd.DataFrame(trace["controls"]).to_html(index=False, escape=True)
        labels = pd.DataFrame(trace["label_rows"]).to_html(index=False, escape=True)
        parts.append(f'<details><summary>{escape(row.event_id)} · CIK {escape(row.cik)} · '
                     f'candidate PERMNO {escape(row.candidate_permno)}</summary>'
                     f'<p>Acceptance: {escape(row.acceptance_timestamp)}. '
                     f'Controls through {escape(row.controls_asof)}. Reference close '
                     f'{escape(row.reference_session)}; label ends {escape(row.label_end)}.</p>'
                     f'<p>Identity: pending. Header CIK differs: {bool(row.header_cik_differs)}. '
                     f'Open link end unresolved: {bool(row.open_end_unresolved)}.</p>'
                     f'<p>Snapshot source: {escape(json.dumps(trace["snapshot"]))}</p>{metrics}'
                     f'<details><summary>60 control sessions and CSV record numbers</summary>{history}</details>'
                     f'<details><summary>20 subsequent return sessions</summary>{labels}</details>'
                     f'<p>Review status: {escape(json.dumps(by_id[row.event_id]))}</p></details>')
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Pilot arithmetic review</title><style>body{font:16px system-ui;max-width:1200px;'
            'margin:40px auto;padding:0 20px;color:#162235;background:#f7fafc}details{background:white;'
            'padding:16px;margin:12px 0;border:1px solid #ccd6e0;border-radius:8px;overflow:auto}'
            'summary{cursor:pointer;font-weight:650}table{border-collapse:collapse;font-size:13px}'
            'td,th{padding:7px;border:1px solid #ddd;text-align:left}p{line-height:1.5}</style>'
            '<h1>Pilot arithmetic review</h1>'
            f'<p>{summary["qa_cases_calculated"]} candidate cases calculated; '
            f'{summary["qa_cases_blocked"]} blocked. {len(traces)} fixed review cases.</p>'
            '<p><strong>Provisional security candidates. Historical identity, source availability '
            'and independent human reviews are pending.</strong> These calculations do not approve '
            'an investment universe, a security link or a model input.</p>'
            '<p>Compare the literal source rows with the independent decimal calculation. '
            'The reference-session return is excluded. Volatility uses a sample denominator of 19; '
            'capitalization converts thousands to USD. Record verdicts in the adjacent JSONL '
            'template, retaining its evidence ID. CSV record numbers include the header.</p>'
            + ''.join(parts) + '</html>')


def audit_pilot_market(events_path, filings_path, audit_path, identity_path, staging_path,
                       daily_path, names_path, plan_path, output, config, reviews_path=None):
    output, identity_path, staging_path, plan_path = map(Path, [output, identity_path, staging_path, plan_path])
    require(not output.exists(), "Output already exists; preserve the previous pilot audit")
    event_raw, events, windows = load_development_events(events_path, config)
    require(events.data_kind.eq("REAL_FILING_EVENTS").all(), "Use real source-bound development events")
    _, source_hashes = _bound_filings(events, filings_path, audit_path)
    identity_raw = (identity_path / "identity_summary.json").read_bytes()
    identity = json.loads(identity_raw)
    bindings = identity["source_hashes"]
    for key, value in {**source_hashes, "events": sha256(event_raw), "protocol": canonical_hash(config)}.items():
        require(bindings.get(key) == value, f"Identity inputs changed: {key}")
    for name, digest in identity["files"].items():
        require(Path(name).name == name, "Invalid identity filename")
        require(sha256((identity_path / name).read_bytes()) == digest, f"Identity evidence changed: {name}")
    queue = pd.read_parquet(identity_path / "event_identity_queue.parquet").set_index("event_id", verify_integrity=True)
    candidates = pd.read_parquet(identity_path / "candidate_links.parquet")
    require(set(queue.index) == set(events.event_id), "Identity packet event set differs")
    plan_raw = (plan_path / "export_plan.json").read_bytes()
    plan = json.loads(plan_raw)
    require(plan["events_sha256"] == sha256(event_raw) and plan["protocol_sha256"] == canonical_hash(config),
            "Export plan differs from events or protocol")
    for name, digest in plan["files"].items():
        require(Path(name).name == name and sha256((plan_path / name).read_bytes()) == digest,
                "Export-plan file changed")
    planned = pd.read_csv(plan_path / "event_windows.csv", dtype=str).set_index("event_id", verify_integrity=True)
    selected = pd.read_csv(plan_path / "trace_reviews.template.csv", dtype=str, keep_default_na=False)
    expected = sorted(events.event_id, key=lambda x: fingerprint({"seed": config["seed"], "event": x}))[:20]
    require(selected.event_id.tolist() == expected, "Trace selection changed; outcomes must not select reviews")
    require(set(planned.index) == set(events.event_id), "Export plan event set differs")

    stage_raw = (staging_path / "staging_receipt.json").read_bytes()
    stage = json.loads(stage_raw)
    require(stage["data_kind"] == "CRSP_SOURCE_STAGING_NOT_AUDIT_APPROVED" and
            stage["protocol_sha256"] == canonical_hash(config), "Unexpected source staging")
    source_digests = {r["filename"]: r["sha256"] for r in stage["raw_exports"]}
    daily_raw, names_raw = Path(daily_path).read_bytes(), Path(names_path).read_bytes()
    require(source_digests.get(Path(daily_path).name) == sha256(daily_raw), "Raw daily source changed")
    require(source_digests.get(Path(names_path).name) == sha256(names_raw) == bindings["names"],
            "Raw Names source changed or differs from identity evidence")
    daily, names = csv_rows(daily_raw), csv_rows(names_raw)
    iso_dates(pd.Series([r["DlyCalDt"] for r in daily]), "raw daily dates", sessions=True)
    require(max(r["DlyCalDt"] for r in daily) <= development_return_end(config), "Holdout returns blocked")
    tables = {}
    for name in ["daily_returns", "market_returns", "security_snapshots"]:
        raw = (staging_path / f"{name}.parquet").read_bytes()
        require(sha256(raw) == stage["table_sha256"][name], f"Staged table changed: {name}")
        dates = pd.read_parquet(io.BytesIO(raw), columns=["session"]).session
        iso_dates(dates, name, sessions=True)
        require(dates.max() <= development_return_end(config), "Holdout staged dates blocked")
        tables[name] = pd.read_parquet(io.BytesIO(raw))
    benchmark = {}
    keys = set()
    for row in daily:
        key = row["PERMNO"], row["DlyCalDt"]
        require(key not in keys, "Duplicate raw security/session")
        keys.add(key)
        session = row["DlyCalDt"]
        require(session not in benchmark or benchmark[session]["vwretd"] == row["vwretd"],
                "Conflicting raw benchmarks")
        benchmark.setdefault(session, row)
    sources = {**source_hashes, "events": sha256(event_raw), "identity_receipt": sha256(identity_raw),
               "staging_receipt": sha256(stage_raw), "export_plan": sha256(plan_raw),
               "raw_daily": sha256(daily_raw), "raw_names": sha256(names_raw),
               "protocol": canonical_hash(config), "audit_code": sha256(Path(__file__).read_bytes()),
               "calculation_code": {name: sha256(Path(__file__).with_name(name).read_bytes())
                                    for name in ["controls.py", "market.py", "timing.py"]}}
    rows, traces = [], []
    maximum = 0.0
    stocks = {key: frame for key, frame in tables["daily_returns"].groupby("security_id")}
    for event, window in zip(events.to_dict("records"), windows, strict=True):
        key = event["event_id"]
        timing = {"reference_session": window.reference_session, "controls_asof": window.controls_through,
                  "label_end": window.label_end, "control_history_start": control_sessions(window)[0]}
        require(all(planned.loc[key, k] == v and queue.loc[key, k] == v for k, v in timing.items()),
                "Recorded event timing differs from the frozen clock")
        require(queue.loc[key, "cik"] == event["cik"] and
                queue.loc[key, "previous_accession"] == event["previous_accession"], "Identity event changed")
        item = {**event, **timing, "data_kind": KIND, "candidate_permno": "",
                "identity_approved": False, "model_ready": False, "qa_status": "blocked",
                "qa_issue": "", "header_cik_differs": bool(queue.loc[key, "ccm_header_cik_differs"]),
                "open_end_unresolved": False}
        try:
            links = candidates[candidates.event_id.eq(key)]
            require(len(links) == 1, "Need exactly one candidate row; no arbitrary class selection")
            link = links.iloc[0]
            security = link.candidate_permno
            item.update(candidate_permno=security, open_end_unresolved=bool(link.ccm_end_marker_unresolved))
            require(bool(queue.loc[key, "header_identity_ok"]) and not bool(queue.loc[key, "interval_coverage_issue"]),
                    "Unresolved SEC header or dated candidate coverage")
            require(link.filing_cik == event["cik"] and
                    json.loads(queue.loc[key, "candidate_permnos"]) == [security], "Candidate identity differs")
            require(security in stocks, "Candidate lacks staged returns")
            result = {**make_label(stocks[security], tables["market_returns"], window),
                      **make_controls(stocks[security], tables["security_snapshots"], window)}
            trace = independent_trace(daily, benchmark, names, security, window)
            errors = {k: abs(result[k] - float(trace["independent_values"][k])) for k in MEASURES}
            require(all(math.isfinite(v) and v <= TOLERANCE for v in errors.values()),
                    "Independent source arithmetic disagrees with pipeline")
            require(result["industry"] == trace["industry"] and result["industry_scheme"] == trace["industry_scheme"],
                    "Independent historical industry differs")
            maximum = max(maximum, *errors.values())
            item.update(result, qa_status="calculated_pending_review", independent_max_abs_error=max(errors.values()))
            evidence_id = fingerprint({"sources": sources, "event": event, "identity_evidence": queue.loc[key, "evidence_id"],
                                       "result": result, "independent_trace": trace})
            item["arithmetic_evidence_id"] = evidence_id
            if key in expected:
                traces.append({"event_id": key, "evidence_id": evidence_id, **trace})
        except ValueError as exc:
            item["qa_issue"] = str(exc)
        rows.append(item)
    cases = pd.DataFrame(rows).sort_values(["cik", "reference_session", "event_id"])
    templates = [{"event_id": t["event_id"], "evidence_id": t["evidence_id"],
                  "controls_verdict": "pending", "label_verdict": "pending", "reviewer": "",
                  "reviewer_type": "", "reviewed_at": "", "source_references": [], "notes": ""} for t in traces]
    reviews = read_reviews(reviews_path, templates)
    human = sum(r["reviewer_type"] == "human" and r["controls_verdict"] == r["label_verdict"] == "pass" for r in reviews)
    blocked = cases[cases.qa_status.eq("blocked")]
    summary = {"schema_version": 1, "data_kind": KIND, "events": len(cases),
               "qa_cases_calculated": len(cases) - len(blocked), "qa_cases_blocked": len(blocked),
               "qa_issue_counts": blocked.qa_issue.value_counts().to_dict(),
               "selected_trace_cases": len(expected), "trace_cases_generated": len(traces),
               "independent_arithmetic_max_abs_error": maximum, "arithmetic_tolerance": TOLERANCE,
               "human_trace_reviews_passed": human, "human_trace_reviews_remaining": len(expected) - human,
               "candidate_cases_with_header_cik_difference": int(cases.header_cik_differs.sum()),
               "candidate_cases_with_unresolved_open_end": int(cases.open_end_unresolved.sum()),
               "actual_candidate_calculations_generated": True, "approved_filing_labels_generated": False,
               "historical_cik_mapping_approved": False, "source_release_verified": False,
               "point_in_time_availability_verified": False, "study_exclusions_finalized": False,
               "model_ready": False, "milestone_05_complete": False, "final_period_opened": False,
               "source_hashes": sources, "reviews_sha256": sha256(Path(reviews_path).read_bytes()) if reviews_path else None,
               "remaining": ["historical identity and share-class approval; explicit open-end bounds",
                             "exact source release/query and availability review", "human filing and trace audits"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pilot-arithmetic-", dir=output.parent) as temporary:
        folder = Path(temporary) / "packet"
        folder.mkdir()
        cases.to_parquet(folder / "candidate_calculations.parquet", index=False)
        blocked.to_csv(folder / "qa_issues.csv", index=False)
        for filename, records in [("independent_traces.jsonl", traces), ("trace_reviews.template.jsonl", templates),
                                  ("trace_reviews.recorded.jsonl", reviews)]:
            (folder / filename).write_text(''.join(json.dumps(r, allow_nan=False) + '\n' for r in records))
        (folder / "review.html").write_text(html_packet(cases.set_index("event_id", drop=False), traces, reviews, summary))
        with duckdb.connect(str(folder / "pilot_qa.duckdb")) as con:
            con.register("qa_frame", cases)
            con.execute("CREATE TABLE candidate_calculations AS SELECT * FROM qa_frame")
        summary["files"] = {p.name: sha256(p.read_bytes()) for p in sorted(folder.iterdir())}
        (folder / "audit_summary.json").write_text(json.dumps(summary, indent=2) + '\n')
        folder.rename(output)
    return summary
