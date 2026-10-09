"""Stage event labels for data QA; this does not authorize empirical model selection."""

import io
import json
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd

from .market import make_label, resolve_security
from .market_data import SYNTHETIC, load_market, sha256, strings
from .timing import event_window


def export_label_events(filings: str | Path, pairs: str | Path, audit: str | Path,
                        output: str | Path, config: dict) -> dict:
    """Create a public event queue from an unchanged offline source audit."""
    output, audit = Path(output), Path(audit)
    if output.exists():
        raise ValueError("Event output already exists; preserve the prior audit-bound queue")
    summary = json.loads((audit / "audit_summary.json").read_text())
    paths = {"source_table_sha256": Path(filings), "pair_table_sha256": Path(pairs),
             "evidence_table_sha256": audit / "filing_evidence.parquet"}
    for key, path in paths.items():
        if summary.get(key) != sha256(path.read_bytes()):
            raise ValueError(f"A fresh matching filing audit is required: {key}")
    frame = pd.read_parquet(filings).set_index("accessionNumber", verify_integrity=True)
    paired = pd.read_parquet(pairs)
    evidence = pd.read_parquet(paths["evidence_table_sha256"]).set_index("accession", verify_integrity=True)
    if paired.empty or paired.accession.duplicated().any():
        raise ValueError("Event export requires nonempty unique annual pairs")
    rows = []
    for pair in paired.itertuples():
        current, previous = evidence.loc[pair.accession], evidence.loc[pair.previous_accession]
        if not current.automated_evidence_ok or not previous.automated_evidence_ok:
            raise ValueError("An annual pair still has blocking source-audit issues")
        filing = frame.loc[pair.accession]
        accepted = datetime.fromisoformat(filing.acceptance_timestamp)
        window = event_window(accepted, config["reference_session_offset"], config["horizon_sessions"])
        if not config["initial_train_start"] <= int(window.acceptance_date[:4]) <= config["development_end"]:
            raise ValueError("Holdout event export is blocked")
        rows.append({"event_id": pair.accession, "cik": pair.cik,
                     "acceptance_timestamp": filing.acceptance_timestamp, "data_kind": "REAL_FILING_EVENTS",
                     "previous_accession": pair.previous_accession,
                     "current_evidence_id": current.evidence_id, "previous_evidence_id": previous.evidence_id,
                     "human_pair_review_complete": bool(current.human_review_complete and previous.human_review_complete),
                     "filing_source_table_sha256": summary["source_table_sha256"]})
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".event-queue-", dir=output.parent) as temp:
        staged = Path(temp) / "events.parquet"
        pd.DataFrame(rows).to_parquet(staged, index=False)
        staged.rename(output)
    return {"events": len(rows), "human_pairs_reviewed": sum(x["human_pair_review_complete"] for x in rows),
            "events_sha256": sha256(output.read_bytes()), "market_returns_used": False,
            "research_status": "event queue only; human and market-data audits remain required"}


def load_development_events(events_path: str | Path, config: dict):
    """Validate event identities and dates before any market outcomes are read."""
    raw = Path(events_path).read_bytes()
    events = pd.read_parquet(io.BytesIO(raw))
    required = {"event_id", "cik", "acceptance_timestamp", "data_kind"}
    if events.empty or required - set(events.columns) or events[list(required)].isna().any().any():
        raise ValueError("Events require nonempty event_id, cik, acceptance_timestamp and data_kind")
    for column in required:
        strings(events[column], f"events.{column}")
    if (events.event_id.duplicated().any() or not events.cik.str.fullmatch(r"\d{10}").all() or
            (events.cik == "0000000000").any()):
        raise ValueError("Events need unique IDs and canonical 10-digit CIK strings")
    windows = []
    for row in events.itertuples():
        accepted = datetime.fromisoformat(row.acceptance_timestamp.replace("Z", "+00:00"))
        window = event_window(accepted, config["reference_session_offset"], config["horizon_sessions"])
        if not config["initial_train_start"] <= int(window.acceptance_date[:4]) <= config["development_end"]:
            raise ValueError("Event outside training/development years; holdout events are blocked")
        windows.append(window)
    return raw, events, windows


def prepare_labels(events_path: str | Path, bundle: str | Path,
                   output: str | Path, config: dict) -> dict:
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new label staging directory")
    raw, events, windows = load_development_events(events_path, config)
    # Validate event dates before loading any market returns.
    tables, receipt = load_market(bundle, config)
    expected_kind = SYNTHETIC if receipt["data_kind"] == SYNTHETIC else "REAL_FILING_EVENTS"
    if not (events.data_kind == expected_kind).all():
        raise ValueError("Synthetic and real events/market data must never be mixed")
    stocks = {key: frame for key, frame in tables["daily_returns"].groupby("security_id", sort=False)}
    rows = []
    for event, window in zip(events.to_dict("records"), windows, strict=True):
        item = {"event_id": event["event_id"], "cik": event["cik"],
                "acceptance_timestamp": event["acceptance_timestamp"],
                "acceptance_date": window.acceptance_date, "reference_session": window.reference_session,
                "controls_asof": window.controls_through, "label_end": window.label_end,
                "market_bundle_id": receipt["bundle_id"], "data_kind": receipt["data_kind"],
                "research_status": "engineering_staging_only", "security_id": "",
                "label_status": "excluded", "exclusion_reason": "",
                "stock_return": None, "market_return": None, "target": None,
                "horizon_sessions": None}
        for key in ["previous_accession", "current_evidence_id", "previous_evidence_id",
                    "human_pair_review_complete", "filing_source_table_sha256"]:
            if key in event:
                item[key] = event[key]
        try:
            security_id = resolve_security(tables["security_links"], event["cik"], window.reference_session)
            item["security_id"] = security_id
            if security_id not in stocks:
                raise ValueError("Mapped security has no returns")
            label = make_label(stocks[security_id], tables["market_returns"], window)
            item.update(label, label_status="ready_for_label_audit")
        except ValueError as exc:
            item["exclusion_reason"] = str(exc)
        rows.append(item)
    result = pd.DataFrame(rows)
    excluded = result[result.label_status == "excluded"]
    summary = {"data_kind": receipt["data_kind"], "research_status": "engineering_staging_only",
               "events": len(result), "labels_prepared": len(result) - len(excluded),
               "events_excluded": len(excluded), "market_bundle_id": receipt["bundle_id"],
               "events_sha256": sha256(raw),
               "exclusion_reasons": excluded.exclusion_reason.value_counts().to_dict(),
               "remaining_gates": ["human filing boundary/timing audit", "verified vendor mapping",
                                   "historical universe and share-class audit", "label and controls audit"],
               "model_ready": False, "final_period_opened": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".label-staging-", dir=output.parent) as temp:
        stage = Path(temp) / "labels"
        stage.mkdir()
        result.to_parquet(stage / "event_labels.parquet", index=False)
        excluded.to_csv(stage / "exclusions.csv", index=False)
        summary["labels_sha256"] = sha256((stage / "event_labels.parquet").read_bytes())
        (stage / "label_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        stage.rename(output)
    return summary
