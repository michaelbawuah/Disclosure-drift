"""Compare the reference pilot with its baseline and the published source hashes."""

import json
from pathlib import Path

import pandas as pd

from disclosure_research.references import load_reference_rules, sha256


def verify(root: Path = Path(".")) -> dict:
    baseline_dir = root / "data/processed/references-baseline"
    resolved_dir = root / "data/processed/references"
    baseline = pd.read_parquet(baseline_dir / "filings.parquet").set_index("accessionNumber")
    resolved = pd.read_parquet(resolved_dir / "filings.parquet").set_index("accessionNumber")
    manifest = pd.read_csv(root / "reports/pilot_filing_manifest.csv", dtype=str).set_index("accession")
    rules = load_reference_rules(root / "configs/section_resolutions.json")
    if not baseline.index.is_unique or not resolved.index.is_unique or set(baseline.index) != set(resolved.index):
        raise ValueError("Baseline and resolved runs must contain the same unique filings")
    expected_ciks = {row["cik"] for row in json.loads((root / "configs/reference_companies.json").read_text())["companies"]}
    if set(resolved.cik) != expected_ciks or not set(rules).issubset(resolved.index):
        raise ValueError("Reference-pilot issuer or rule coverage is incomplete")
    unchanged = 0
    for accession, current in resolved.iterrows():
        original, published = baseline.loc[accession], manifest.loc[accession]
        for field in ["download_sha256", "header_sha256"]:
            if current[field] != original[field] or current[field] != published[field]:
                raise ValueError(f"Original source changed for {accession}: {field}")
        if sha256(original.risk_text) != published.risk_text_sha256:
            raise ValueError(f"Baseline text differs from milestone 02 for {accession}")
        for field in ["acceptance_timestamp", "reference_session", "label_end", "controls_through"]:
            if current[field] != original[field]:
                raise ValueError(f"Timing changed for {accession}: {field}")
        if accession not in rules:
            if current.risk_text != original.risk_text or current.extraction_status != original.extraction_status:
                raise ValueError(f"Unregistered filing changed: {accession}")
            unchanged += 1
        elif (current.extraction_status != "ok" or sha256(current.risk_text) != rules[accession]["text_sha256"] or
              current.resolution_rule_id != sha256(json.dumps(rules[accession], sort_keys=True))):
            raise ValueError(f"Registered resolution did not reproduce: {accession}")
    audit = json.loads((root / "outputs/audit-references/audit_summary.json").read_text())
    if (audit["source_table_sha256"] != sha256((resolved_dir / "filings.parquet").read_bytes()) or
            audit["filings"] != len(resolved) or audit["filings_with_blocking_issues"]):
        raise ValueError("The resolved filing table needs a fresh passing source audit")
    before = json.loads((baseline_dir / "ingestion_summary.json").read_text())
    after = json.loads((resolved_dir / "ingestion_summary.json").read_text())
    if before["failures"] or after["failures"]:
        raise ValueError("Ingestion failures remain in the reference pilot")
    pairs = pd.read_parquet(resolved_dir / "filing_pairs.parquet")
    transitions = pairs[pairs.resolution_method_changed][
        ["cik", "accession", "previous_accession", "resolution_method", "previous_resolution_method"]]
    result = {"sample": "Targeted 24-filing reference-resolution pilot; not a historical investment universe",
              "filings": len(resolved), "issuers": int(resolved.cik.nunique()),
              "baseline_extraction_ok": before["automated_extraction_ok"],
              "resolved_extraction_ok": after["automated_extraction_ok"],
              "baseline_annual_pairs": before["pairs_ready_for_manual_review"],
              "resolved_annual_pairs": after["pairs_ready_for_manual_review"],
              "registered_resolutions": len(rules), "unchanged_control_filings": unchanged,
              "primary_and_header_hashes_match_milestone_02": True,
              "baseline_text_hashes_match_milestone_02": True, "all_event_dates_unchanged": True,
              "resolution_kind_counts": {k: int(v) for k, v in resolved.resolution_method.value_counts().items()},
              "method_transition_pairs": transitions.to_dict("records"),
              "audit": audit, "baseline_network_requests": before["network_requests_this_run"],
              "resolved_network_requests": after["network_requests_this_run"],
              "resolution_config_sha256": sha256((root / "configs/section_resolutions.json").read_bytes()),
              "source_table_sha256": sha256((resolved_dir / "filings.parquet").read_bytes()),
              "pair_table_sha256": sha256((resolved_dir / "filing_pairs.parquet").read_bytes()),
              "market_returns_used": False, "final_period_opened": False,
              "full_155_filing_pilot_rebuilt": False}
    output = root / "outputs/reference_verification.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
