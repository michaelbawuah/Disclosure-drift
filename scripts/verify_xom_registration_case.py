"""Inspect the seven flagged Exxon filings without approving a historical link."""

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from disclosure_research.audit import cached_body
from disclosure_research.extraction import clean_html
from disclosure_research.identity_review import _header
from disclosure_research.market_data import sha256
from disclosure_research.pilot_audit import require


def verify(root, output):
    root, output = Path(root), Path(output)
    require(not output.exists(), "Preserve previous identity evidence")
    packet = root / "data/reviews/identity-pilot-v2"
    receipt_raw = (packet / "identity_summary.json").read_bytes()
    receipt = json.loads(receipt_raw)
    for name in ("event_identity_queue.parquet", "candidate_links.parquet"):
        require(sha256((packet / name).read_bytes()) == receipt["files"][name], "Identity evidence changed")
    filings_path = root / "data/processed/pilot-resolved/filings.parquet"
    names_path = root / "data/raw/wrds/2026-10-09/crsp_names_pilot.csv"
    require(sha256(filings_path.read_bytes()) == receipt["source_hashes"]["filings"] and
            sha256(names_path.read_bytes()) == receipt["source_hashes"]["names"], "Source inputs changed")
    filings = pd.read_parquet(filings_path).set_index("accessionNumber", drop=False)
    queue = pd.read_parquet(packet / "event_identity_queue.parquet").set_index("event_id")
    candidates = pd.read_parquet(packet / "candidate_links.parquet")
    flagged = candidates.loc[candidates.header_cik_differs]
    require(len(flagged) == 7 and flagged.filing_cik.eq("0000034088").all(), "Flagged population changed")
    names = pd.read_csv(names_path, dtype=str, keep_default_na=False)
    rows = []
    for candidate in flagged.itertuples():
        filing = filings.loc[candidate.event_id].to_dict()
        require(int(filing["acceptance_date"][:4]) <= 2021, "Only development filings may be inspected")
        header = _header(filing, root / "data/raw/sec_cache")
        require(header["header_identity_ok"], "Original filer header differs")
        source = cached_body(root / "data/raw/sec_cache", filing["source_url"], filing["download_sha256"])
        normalized = " ".join(clean_html(source).split())
        opening = re.search(r"(?i)securities registered pursuant to section 12\s*\(b\)", normalized)
        require(opening is not None, "Original registration table is missing")
        closing = normalized.index("Indicate by check mark", opening.end())
        registration = normalized[opening.start():closing]
        require("Common Stock, without par value" in registration and
                "New York Stock Exchange" in registration, "Registered common-stock description differs")
        date = queue.loc[candidate.event_id, "controls_asof"]
        dated = names.loc[names.permno.eq(candidate.candidate_permno) &
                          names.secinfostartdt.le(date) & names.secinfoenddt.ge(date)]
        require(len(dated) == 1 and dated.iloc[0].permco == candidate.ccm_permco,
                "Prior-close Names description is missing, ambiguous or has a different PERMCO")
        require(dated.iloc[0].issuernm == "EXXON MOBIL CORP" and
                (dated.iloc[0].securitytype, dated.iloc[0].securitysubtype) == ("EQTY", "COM"),
                "Dated issuer/security description differs from the inspected candidate")
        require(candidate.ccm_link_end_raw == "E" and candidate.ccm_end_marker_unresolved,
                "Do not silently normalize the unresolved link end")
        rows.append({"accession": candidate.event_id, "source_url": filing["source_url"],
                     "source_sha256": filing["download_sha256"], "header_url": filing["header_url"],
                     "header_sha256": filing["header_sha256"], "original_filer_cik": filing["cik"],
                     "registration_excerpt_sha256": sha256(registration.encode()),
                     "registered_common_stock_and_nyse_observed": True,
                     "other_registered_notes_present": bool(re.search(r"(?i)notes due", registration)),
                     "one_consistent_dated_names_description": True,
                     "original_identity_evidence_id": queue.loc[candidate.event_id, "evidence_id"],
                     "current_vendor_header_cik_difference_preserved": True,
                     "open_link_end_preserved": True, "mapping_approved": False})
    result = {"status": "supporting_registration_evidence_recorded_mapping_unapproved",
              "reviewer_type": "assistant", "flagged_events_inspected": len(rows),
              "source_registration_checks_passed": len(rows), "human_reviews_added": 0,
              "market_returns_loaded": False, "final_period_opened": False,
              "identity_packet_sha256": sha256(receipt_raw), "names_sha256": receipt["source_hashes"]["names"],
              "script_sha256": sha256(Path(__file__).read_bytes()),
              "remaining": ["Supported historical CIK/security link and validity interval",
                            "Vendor dictionary, source vintage and extract-specific E normalization bound",
                            "Required independent identity/source judgment"], "cases": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = verify(args.root, args.output)
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}, indent=2))
