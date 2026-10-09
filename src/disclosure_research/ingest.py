"""A small live filing pipeline with durable Parquet outputs and an audit queue."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from .edgar import SecClient, list_original_filings
from .extraction import extract_risk_factors, pair_filings
from .timing import acceptance_from_header, event_window


def ingest_smoke(config: dict, client: SecClient, output: str | Path) -> dict:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    records, failures = [], []
    for company in config["companies"]:
        print(f"Reading {company['name']} submission history", flush=True)
        try:
            filings = list_original_filings(client, company["cik"], config["filing_year_start"],
                                            config["filing_year_end"])
        except Exception as exc:
            failures.append({"cik": company["cik"], "stage": "submissions", "error": str(exc)})
            continue
        for filing in filings:
            accession = filing["accessionNumber"]
            try:
                raw, provenance = client.fetch(filing["source_url"])
                extracted = extract_risk_factors(raw)
                header_status = "sgml_header"
                header_hash = None
                try:
                    header, header_meta = client.fetch(filing["header_url"])
                    accepted = acceptance_from_header(header.decode("utf-8", errors="replace"))
                    header_hash = header_meta["sha256"]
                except Exception as exc:
                    encoded = filing.get("acceptanceDateTime", "")
                    accepted = datetime.fromisoformat(encoded.replace("Z", "+00:00"))
                    if accepted.tzinfo is None:
                        raise ValueError("No independently interpretable acceptance timestamp") from exc
                    header_status = "api_encoded_offset_unverified_against_header"
                window = event_window(accepted)
                records.append({**filing, "name": company["name"],
                                "download_sha256": provenance["sha256"],
                                "fetched_at": provenance["fetched_at"], "header_sha256": header_hash,
                                "acceptance_source": header_status,
                                "acceptance_timestamp": accepted.isoformat(),
                                "availability_status": "two_session_proxy; dissemination_not_verified",
                                "extraction_status": extracted.status, "risk_text": extracted.text,
                                "risk_token_count": extracted.token_count, "extraction_reason": extracted.reason,
                                "candidate_count": extracted.candidate_count,
                                "extraction_version": extracted.version,
                                **{k: v for k, v in asdict(window).items() if k != "return_sessions"}})
                print(f"  {accession}: {extracted.status}, {extracted.token_count} tokens", flush=True)
            except Exception as exc:
                failures.append({"cik": company["cik"], "accession": accession,
                                 "stage": "document", "error": str(exc)})
                print(f"  {accession}: failed ({exc})", flush=True)
    pairs, exclusions = pair_filings(records, config["pair_year_start"], config["pair_year_end"])
    frame = pd.DataFrame(records)
    if not frame.empty:
        frame.to_parquet(output / "filings.parquet", index=False)
        audit = frame.drop(columns=["risk_text"])
        audit["manual_boundary_review"] = "pending"
        audit["manual_timing_review"] = "pending"
        audit.to_csv(output / "audit_queue.csv", index=False)
        con = duckdb.connect(str(output / "research.duckdb"))
        con.register("filing_frame", frame)
        con.execute("CREATE OR REPLACE TABLE filings AS SELECT * FROM filing_frame")
        if pairs:
            pair_frame = pd.DataFrame(pairs)
            pair_frame.to_parquet(output / "filing_pairs.parquet", index=False)
            con.register("pair_frame", pair_frame)
            con.execute("CREATE OR REPLACE TABLE filing_pairs AS SELECT * FROM pair_frame")
        con.close()
    summary = {"sample_type": config["purpose"], "companies_requested": len(config["companies"]),
               "filings_downloaded": len(records), "automated_extraction_ok": sum(r["extraction_status"] == "ok" for r in records),
               "pairs_ready_for_manual_review": len(pairs), "excluded_pairs": exclusions,
               "network_requests_this_run": client.network_requests, "failures": failures,
               "manual_audit": "pending", "market_returns": "not_loaded",
               "empirical_predictive_results": "none"}
    (output / "ingestion_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
