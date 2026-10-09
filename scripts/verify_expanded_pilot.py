"""Compare the full resolved pilot to the published milestone-02 source evidence."""

import json
from pathlib import Path

import pandas as pd

from disclosure_research.market_data import sha256
from disclosure_research.references import load_reference_rules


def verify(root: Path = Path(".")) -> dict:
    processed = root / "data/processed/pilot-resolved"
    frame = pd.read_parquet(processed / "filings.parquet").set_index("accessionNumber", verify_integrity=True)
    published = pd.read_csv(root / "reports/pilot_filing_manifest.csv", dtype=str).set_index("accession")
    rules = load_reference_rules(root / "configs/section_resolutions.json")
    audit = json.loads((root / "outputs/audit-pilot-resolved/audit_summary.json").read_text())
    ingestion = json.loads((processed / "ingestion_summary.json").read_text())
    if set(frame.index) != set(published.index) or ingestion["failures"]:
        raise ValueError("The expanded pilot must reproduce every original accession without download failures")
    if (audit["filings_with_blocking_issues"] or audit["source_table_sha256"] !=
            sha256((processed / "filings.parquet").read_bytes())):
        raise ValueError("The expanded pilot needs a fresh passing automated audit")
    unchanged = 0
    for accession, row in frame.iterrows():
        original = published.loc[accession]
        for key in ["cik", "source_url", "header_url", "download_sha256", "header_sha256",
                    "acceptance_timestamp", "reference_session", "label_end"]:
            if row[key] != original[key]:
                raise ValueError(f"Source identity or event timing changed: {accession} {key}")
        if accession in rules:
            if sha256(row.risk_text.encode()) != rules[accession]["text_sha256"]:
                raise ValueError(f"Registered resolution changed: {accession}")
        else:
            if (sha256(row.risk_text.encode()) != original.risk_text_sha256 or
                    row.extraction_status != original.extraction_status):
                raise ValueError(f"Unregistered extraction changed: {accession}")
            unchanged += 1
    pairs_path = processed / "filing_pairs.parquet"
    if audit["pair_table_sha256"] != sha256(pairs_path.read_bytes()):
        raise ValueError("Pair table changed after its audit")
    pairs = pd.read_parquet(pairs_path)
    result = {"filings": len(frame), "issuers": int(frame.cik.nunique()),
              "annual_pairs": len(pairs), "registered_resolutions": len(rules),
              "unchanged_control_filings": unchanged,
              "source_hashes_and_event_dates_match_milestone_02": True,
              "method_transition_pairs": pairs.loc[pairs.resolution_method_changed,
                  ["accession", "previous_accession", "cik"]].to_dict("records"),
              "ingestion": ingestion, "audit": audit,
              "market_returns_used": False, "final_period_opened": False,
              "sample_role": "purposive document-format pilot; not a historical investment universe"}
    (root / "outputs/expanded_pilot_verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
