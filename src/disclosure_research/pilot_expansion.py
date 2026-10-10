"""Combine independently collected SEC pilot sources without replacing earlier evidence."""

import io
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from .audit import build_audit
from .extraction import pair_filings
from .market_data import sha256
from .pilot_checkpoint import build_pilot_checkpoint
from .protocol import canonical_hash, guard_development

SEC_FILING_COLUMNS = set("""
accessionNumber filingDate reportDate acceptanceDateTime act form fileNumber filmNumber items core_type
size isXBRL isInlineXBRL isXBRLNumeric primaryDocument primaryDocDescription cik source_url header_url name
download_sha256 fetched_at header_sha256 acceptance_source api_header_difference_seconds acceptance_timestamp
availability_status extraction_status risk_text risk_token_count extraction_reason candidate_count
extraction_version risk_source_url risk_source_sha256 resolution_method resolution_rule_id
resolution_index_url resolution_index_sha256 extraction_start extraction_end normalizer_version
acceptance_date reference_session prediction_time_utc controls_through label_end
""".split())
SEC_PAIR_COLUMNS = set("""
cik accession previous_accession acceptance_date previous_acceptance_date current_text previous_text
reference_session label_end source_url previous_source_url risk_source_url previous_risk_source_url
resolution_method previous_resolution_method resolution_method_changed
""".split())


def combine_pilot_sources(source_directories, output, cache, resolutions, config) -> dict:
    """Build and audit a source union; no market table or historical universe is accepted.

    The original pair identities, text and dates must survive the union exactly.
    New sources cannot overwrite an original accession or silently change its
    predecessor. Read dates before text so a final-period input is refused early.
    """
    sources = [Path(value).resolve() for value in source_directories]
    out = Path(output)
    if len(sources) < 2 or len(set(sources)) != len(sources):
        raise ValueError("Supply at least two distinct SEC pilot source directories")
    if out.exists():
        raise ValueError("Output exists; preserve earlier pilot evidence")
    filings, original_pairs, bindings = [], [], []
    for source in sources:
        filing_path, pair_path = source / "filings.parquet", source / "filing_pairs.parquet"
        snapshots = {}
        for path, allowed in [(filing_path, SEC_FILING_COLUMNS), (pair_path, SEC_PAIR_COLUMNS)]:
            raw = path.read_bytes()
            columns = set(pq.ParquetFile(io.BytesIO(raw)).schema_arrow.names)
            if columns - allowed:
                raise ValueError("Pilot combination accepts only SEC source columns; unexpected data refused")
            dates = pd.read_parquet(io.BytesIO(raw), columns=["acceptance_date"])
            guard_development(dates, config)
            if dates.empty or dates.acceptance_date.isna().any():
                raise ValueError("Pilot sources need nonempty, dated filing and pair tables")
            snapshots[path] = raw
        filings.append(pd.read_parquet(io.BytesIO(snapshots[filing_path])))
        original_pairs.append(pd.read_parquet(io.BytesIO(snapshots[pair_path])))
        bindings.append({"source_directory": str(source),
                         "filings_sha256": sha256(snapshots[filing_path]),
                         "pairs_sha256": sha256(snapshots[pair_path])})
    combined = pd.concat(filings, ignore_index=True)
    if combined.accessionNumber.duplicated().any():
        raise ValueError("Pilot sources overlap; an original accession cannot be replaced")
    original = pd.concat(original_pairs, ignore_index=True)
    start_year = int(pd.to_datetime(original.acceptance_date).dt.year.min())
    pairs, exclusions = pair_filings(combined.to_dict("records"), start_year,
                                    config["development_end"])
    canonical = {row["accession"]: row for row in pairs}
    for row in original.to_dict("records"):
        match = canonical.get(row["accession"])
        if match is None or any(row[key] != match.get(key) for key in row):
            raise ValueError("Combined sources would change an existing pair or its provenance")
    pair_frame = pd.DataFrame(pairs)
    out.mkdir(parents=True)
    combined.sort_values(["cik", "acceptance_date", "accessionNumber"]).to_parquet(
        out / "filings.parquet", index=False)
    pair_frame.sort_values(["cik", "acceptance_date", "accession"]).to_parquet(
        out / "filing_pairs.parquet", index=False)
    audit = build_audit(out / "filings.parquet", cache, out / "audit",
                        config["development_end"], resolutions=resolutions)
    receipt = {"schema_version": 1, "data_kind": "REAL_SEC_TEXT_DESCRIPTIVE_PILOT",
               "protocol_sha256": canonical_hash(config), "input_sources": bindings,
               "original_pairs_preserved": len(original), "filings": len(combined),
               "pairs": len(pair_frame), "issuers": int(combined.cik.nunique()),
               "excluded_pairs": exclusions, "source_audit": audit,
               "returns_read": False, "historical_universe_claim": False,
               "predictive_performance_claim": False,
               "status": "blocked_source_audit" if audit["filings_with_blocking_issues"]
                         else "source_verified_descriptive_pilot"}
    (out / "combination_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if audit["filings_with_blocking_issues"]:
        raise ValueError("Combined source audit has blocking findings; inspect the saved audit")
    checkpoint = build_pilot_checkpoint(out / "filing_pairs.parquet", out / "filings.parquet",
                                        out / "audit", out / "checkpoint", config)
    receipt["pilot_2019_2021_pairs"] = checkpoint["pilot_2019_2021_pairs"]
    receipt["planned_pilot_pair_count_met"] = 100 <= receipt["pilot_2019_2021_pairs"] <= 150
    receipt["checkpoint_sha256"] = sha256((out / "checkpoint/pilot_checkpoint.json").read_bytes())
    (out / "combination_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt
