"""Build a date-bounded market-data request without loading market outcomes."""

import json
import re
import tempfile
from pathlib import Path

import pandas as pd

from .controls import control_sessions
from .labels import load_development_events
from .market_data import fingerprint, sha256
from .protocol import canonical_hash


def build_export_plan(events_path: str | Path, output: str | Path, config: dict) -> dict:
    output = Path(output)
    if output.exists():
        raise ValueError("Export plan already exists; preserve the prior request")
    raw, events, windows = load_development_events(events_path, config)
    if not (events.data_kind == "REAL_FILING_EVENTS").all():
        raise ValueError("Export requests require real development filing events")
    provenance = ["current_evidence_id", "previous_evidence_id", "filing_source_table_sha256"]
    if set(provenance + ["previous_accession"]) - set(events.columns):
        raise ValueError("Use the audit-bound export-label-events queue")
    for name in provenance:
        if not events[name].map(lambda x: isinstance(x, str) and
                               bool(re.fullmatch(r"[0-9a-f]{64}", x))).all():
            raise ValueError(f"Invalid event provenance: {name}")
    if events.previous_accession.isna().any() or not events.previous_accession.map(
        lambda x: isinstance(x, str) and bool(x.strip())
    ).all():
        raise ValueError("Missing previous accession in the event queue")
    rows = []
    for event, window in zip(events.to_dict("records"), windows, strict=True):
        sessions = control_sessions(window)
        rows.append({"event_id": event["event_id"], "cik": event["cik"],
                     "previous_accession": event["previous_accession"],
                     "acceptance_timestamp": event["acceptance_timestamp"],
                     "prediction_time_utc": window.prediction_time_utc,
                     "control_history_start": sessions[0], "momentum_20_start": sessions[-20],
                     "controls_asof": window.controls_through,
                     "reference_session": window.reference_session,
                     "label_start": window.return_sessions[0], "label_end": window.label_end,
                     **{key: event[key] for key in provenance}})
    frame = pd.DataFrame(rows).sort_values(["cik", "reference_session", "event_id"])
    issuers = frame.groupby("cik", as_index=False).agg(
        request_start=("control_history_start", "min"), request_end=("label_end", "max"),
        events=("event_id", "size"))
    # A deterministic random-priority trace sample, chosen without market outcomes.
    keys = frame.event_id.map(lambda event: fingerprint({"seed": config["seed"], "event": event}))
    traces = frame.assign(selection_key=keys).sort_values("selection_key").head(20).copy()
    for column in ["identity_review", "controls_review", "label_review"]:
        traces[column] = "pending"
    for column in ["reviewer", "reviewed_at", "notes"]:
        traces[column] = ""
    summary = {"events": len(frame), "issuers": len(issuers), "trace_reviews_requested": len(traces),
               "request_start": str(issuers.request_start.min()),
               "request_end": str(issuers.request_end.max()), "events_sha256": sha256(raw),
               "protocol_sha256": canonical_hash(config), "market_returns_loaded": False,
               "human_reviews_completed_by_this_command": 0, "final_period_opened": False,
               "status": "export request only; entitlement, normalization and human review pending"}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".export-plan-", dir=output.parent) as temp:
        stage = Path(temp) / "plan"
        stage.mkdir()
        files = {"event_windows.csv": frame, "issuer_requests.csv": issuers,
                 "trace_reviews.template.csv": traces}
        for filename, table in files.items():
            table.to_csv(stage / filename, index=False)
        summary["files"] = {name: sha256((stage / name).read_bytes()) for name in files}
        (stage / "export_plan.json").write_text(json.dumps(summary, indent=2) + "\n")
        stage.rename(output)
    return summary
