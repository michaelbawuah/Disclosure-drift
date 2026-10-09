"""Read-only SEC ingestion with provenance, caching and bounded retries."""

import hashlib
import json
import re
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import httpx


MAX_DOCUMENT_BYTES = 40 * 1024 * 1024


class SecClient:
    def __init__(self, cache_dir: str | Path, user_agent: str, rate: float = 2.0,
                 timeout: float = 30.0, retries: int = 3, transport=None, sleep=time.sleep):
        if not user_agent or not ("@" in user_agent or "https://" in user_agent):
            raise ValueError("Set SEC_USER_AGENT to identify the research client and contact")
        if not 0 < rate <= 5:
            raise ValueError("Use a conservative request rate between 0 and 5 requests/second")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent, self.interval = user_agent, 1 / rate
        self.timeout, self.retries = timeout, retries
        self.transport = transport
        self.sleep, self.last_request, self.network_requests = sleep, 0.0, 0

    def fetch(self, url: str) -> tuple[bytes, dict]:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {"www.sec.gov", "data.sec.gov"}:
            raise ValueError("SEC client only accepts official HTTPS SEC endpoints")
        key = hashlib.sha256(url.encode()).hexdigest()
        body_path, meta_path = self.cache_dir / f"{key}.bin", self.cache_dir / f"{key}.json"
        if body_path.exists() and meta_path.exists():
            body, meta = body_path.read_bytes(), json.loads(meta_path.read_text())
            if hashlib.sha256(body).hexdigest() != meta["sha256"] or meta["url"] != url:
                raise ValueError("Cached response failed its provenance check")
            return body, {**meta, "cache_hit": True}
        for attempt in range(self.retries + 1):
            self.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            self.network_requests += 1
            headers = {
                "User-Agent": self.user_agent, "Accept-Encoding": "identity",
                "Accept": "application/json,text/html,text/plain,*/*",
            }
            try:
                # Streaming enforces the size limit before the entire document is read.
                # Redirects are not followed: a new destination needs explicit review.
                with httpx.Client(transport=self.transport, timeout=self.timeout,
                                  follow_redirects=False) as client, client.stream(
                                      "GET", url, headers=headers) as response:
                    response.raise_for_status()
                    chunks, size = [], 0
                    for chunk in response.iter_bytes(chunk_size=64 * 1024):
                        size += len(chunk)
                        if size > MAX_DOCUMENT_BYTES:
                            raise ValueError("Response exceeds the 40 MiB per-document limit")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    meta = {"url": url, "sha256": hashlib.sha256(body).hexdigest(),
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                            "bytes": len(body), "status": response.status_code,
                            "body_representation": "http-decoded", "transport": "httpx"}
                # Atomic per-file writes; orphaned partial entries are safe to refetch.
                temp = body_path.with_suffix(".tmp")
                temp.write_bytes(body)
                temp.replace(body_path)
                temp_meta = meta_path.with_suffix(".tmp")
                temp_meta.write_text(json.dumps(meta, indent=2) + "\n")
                temp_meta.replace(meta_path)
                return body, {**meta, "cache_hit": False}
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in {429, 500, 502, 503, 504} or attempt == self.retries:
                    raise
                retry_after = exc.response.headers.get("Retry-After", "")
                wait = min(30, float(retry_after)) if retry_after.isdigit() else min(16, 2 ** attempt)
                self.sleep(wait)
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
                self.sleep(min(16, 2 ** attempt))
        raise RuntimeError("Unreachable retry state")

    def json(self, url: str) -> dict:
        return json.loads(self.fetch(url)[0])


def rows_from_columns(columns: dict) -> list[dict]:
    count = len(columns.get("accessionNumber", []))
    if any(isinstance(v, list) and len(v) != count for v in columns.values()):
        raise ValueError("Submission column lengths differ")
    return [{key: value[i] for key, value in columns.items() if isinstance(value, list)}
            for i in range(count)]


def list_original_filings(client: SecClient, cik: str, start_year: int, end_year: int) -> list[dict]:
    cik = str(int(cik)).zfill(10)
    doc = client.json(f"https://data.sec.gov/submissions/CIK{cik}.json")
    rows = rows_from_columns(doc["filings"]["recent"])
    for part in doc["filings"].get("files", []):
        if part["filingTo"][:4] < str(start_year) or part["filingFrom"][:4] > str(end_year):
            continue
        name = part["name"]
        if not re.fullmatch(r"CIK\d{10}-submissions-\d+\.json", name):
            raise ValueError("Unexpected historical submissions filename")
        rows.extend(rows_from_columns(client.json(f"https://data.sec.gov/submissions/{name}")))
    kept = {}
    for row in rows:
        if row["form"] != "10-K" or not start_year <= int(row["filingDate"][:4]) <= end_year:
            continue
        accession, primary = row["accessionNumber"], row.get("primaryDocument", "")
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
            raise ValueError("Invalid accession number")
        if not primary or Path(primary).name != primary:
            raise ValueError("Unexpected primary-document name")
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"
        kept[accession] = {**row, "cik": cik, "source_url": f"{base}/{primary}",
                           "header_url": f"{base}/{accession}.hdr.sgml"}
    return sorted(kept.values(), key=lambda r: (r["filingDate"], r["accessionNumber"]))
