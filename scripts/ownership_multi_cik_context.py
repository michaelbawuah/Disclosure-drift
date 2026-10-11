"""Preserve the eight fixed original corporate-context sources for seven cases.

Only source identity, listed symbol/class and reported corporate transitions
are interpreted. No vendor relationship or historical availability is approved.
"""
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from lxml import html

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/multi-cik-followup-20261011/corporate-context"
REPORT = ROOT / "reports/ownership_multi_cik_context.json"
UA = "Michael Baffour Awuah Disclosure-drift research https://github.com/michaelbawuah/Disclosure-drift"
SOURCES = [
    ("ecol_merger", "multi-cik-01", "https://www.sec.gov/Archives/edgar/data/1783400/000110465919058632/a19-21013_128k.htm",
     ["completion at 12:01 a.m.", "Predecessor US Ecology", "wholly-owned subsidiary", "November 1, 2019"]),
    ("bcow_cover", "multi-cik-02", "https://www.sec.gov/Archives/edgar/data/1751692/000094337419000425/form8k_092419.htm",
     ["1895 Bancorp of Wisconsin, Inc.", "BCOW"]),
    ("goldman_cover", "multi-cik-03", "https://www.sec.gov/Archives/edgar/data/886982/000119312519293432/d831594d8k.htm",
     ["The Goldman Sachs Group, Inc.", "Common stock, par value $.01 per share", "GS"]),
    ("provident_conversion", "multi-cik-04", "https://www.sec.gov/Archives/edgar/data/1778784/000094337419000460/form8k_101119.htm",
     ["Old Provident", "New Provident", "close of business on October 16, 2019"]),
    ("provident_closing_release", "multi-cik-04", "https://www.sec.gov/Archives/edgar/data/1778784/000094337419000460/ex99-2_8k101119.htm",
     ["ceased to exist", "October 17, 2019", "PVBC"]),
    ("tidewater_cover", "multi-cik-05", "https://www.sec.gov/Archives/edgar/data/98222/000119312519279310/d827369d8k.htm",
     ["TIDEWATER INC.", "Common stock, $0.001 par value per share", "TDW"]),
    ("valeritas_merger", "multi-cik-06", "https://www.sec.gov/Archives/edgar/data/1619250/000119312516583971/d180550d8k.htm",
     ["May 3, 2016", "Valeritas Holdings, Inc.", "surviving entity and as a wholly owned subsidiary"]),
    ("westlake_partners_cover", "multi-cik-07", "https://www.sec.gov/Archives/edgar/data/1604665/000160466519000033/a2019093010qwlkp.htm",
     ["Westlake Chemical Partners LP", "Common units representing limited partnership interests", "WLKP"]),
]

def main():
    from datetime import datetime, timezone
    def now():
        return datetime.now(timezone.utc).isoformat()
    def sha(body):
        return hashlib.sha256(body).hexdigest()
    def write(path, body):
        with path.open("xb") as stream:
            stream.write(body)
    assert not OUT.exists() and not REPORT.exists()
    OUT.mkdir(mode=0o700)
    records, stopped = [], False
    for key, case, url, needles in SOURCES:
        assert re.search(r"/\d{10}(?:16|19)\d{6}/", url)
        record = {"source_id": key, "case_id": case, "url": url, "started_at_utc": now()}
        if stopped:
            record["status"] = "NOT_ATTEMPTED_AFTER_ACCESS_DENIAL"
            records.append(record)
            continue
        try:
            request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read(8 * 1024 * 1024 + 1)
                assert response.status == 200 and response.url == url and len(body) <= 8 * 1024 * 1024
                record.update(http_status=response.status, final_url=response.url,
                              response_metadata={k: response.headers.get(k) for k in ("Content-Type", "Last-Modified", "Date", "ETag")})
            path = OUT / (key + ".html")
            write(path, body)
            document = html.fromstring(body)
            text = re.sub(r"\s+", " ", " ".join(document.itertext())).strip()
            text_path = OUT / (key + ".normalized.txt")
            text_bytes = text.encode()
            write(text_path, text_bytes)
            anchors = []
            for needle in needles:
                starts = [m.start() for m in re.finditer(re.escape(needle), text)]
                anchors.append({"literal": needle, "normalized_character_starts": starts,
                                "normalization": "lxml itertext joined with spaces; Unicode whitespace collapsed"})
            cover_rows = []
            if key.endswith("_cover"):
                target = {"bcow_cover": "BCOW", "goldman_cover": "GS",
                          "tidewater_cover": "TDW", "westlake_partners_cover": "WLKP"}[key]
                candidates = [re.sub(r"\s+", " ", " ".join(tr.itertext())).strip() for tr in document.xpath("//tr")]
                candidates = [s for s in candidates if re.search(r"\b" + target + r"\b", s)
                              and ("Common stock" in s or "Common Stock" in s or "Common units" in s)]
                if candidates:
                    cover_rows = [min(candidates, key=len)]
            record.update(status="ORIGINAL_CONTEXT_SOURCE_PRESERVED",
                          source={"path": str(path.relative_to(ROOT)), "bytes": len(body), "sha256": sha(body)},
                          normalized_text={"path": str(text_path.relative_to(ROOT)), "bytes": len(text_bytes), "sha256": sha(text_bytes)},
                          evidence_anchors=anchors, all_anchors_present=all(a["normalized_character_starts"] for a in anchors),
                          shortest_matching_cover_rows=cover_rows)
        except urllib.error.HTTPError as exc:
            record.update(status="HTTP_ERROR", http_status=exc.code)
            stopped = exc.code == 403
        except Exception as exc:
            record.update(status="SOURCE_OR_INSPECTION_ERROR", error_type=type(exc).__name__, message=str(exc))
        record["completed_at_utc"] = now()
        records.append(record)
        print(json.dumps({k: record.get(k) for k in ("source_id", "status", "all_anchors_present", "shortest_matching_cover_rows")}), flush=True)
        time.sleep(0.6)
    report = {"schema_version": 1, "status": "SEPARATE_CORPORATE_CONTEXT_SOURCE_EVIDENCE",
              "recorded_at_utc": now(), "sources": records,
              "script": {"path": str(Path(__file__).resolve().relative_to(ROOT)), "sha256": sha(Path(__file__).read_bytes()), "bytes": Path(__file__).stat().st_size},
              "request_policy": {"workers": 1, "minimum_delay_after_each_source_seconds": 0.6,
                                 "user_agent": UA, "automatic_retries": 0, "stop_after_403": True},
              "scope": "Eight pre-2020 original SEC HTML filings/exhibits, source byte preservation, reported corporate identities/events and listed symbol/class context. These are separate from ownership metadata validation.",
              "historical_security_links_created": 0, "historical_availability_inferred": False,
              "known_at_inferred": False, "source_approvals_created": 0, "human_reviews_created": 0,
              "market_outcomes_read": False, "final_period_sources_requested": False, "model_ready": False}
    write(REPORT, (json.dumps(report, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({"report": str(REPORT.relative_to(ROOT)), "sha256": sha(REPORT.read_bytes()),
                      "preserved_sources": sum(r["status"] == "ORIGINAL_CONTEXT_SOURCE_PRESERVED" for r in records),
                      "all_sources": len(records)}), flush=True)
    if any(r.get("status") != "ORIGINAL_CONTEXT_SOURCE_PRESERVED" for r in records):
        sys.exit(2)

if __name__ == "__main__":
    main()

