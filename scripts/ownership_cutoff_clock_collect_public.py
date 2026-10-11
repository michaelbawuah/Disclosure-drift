"""Collect the exact public cutoff queue through ordinary container HTTPS.

The earlier Mac 403 receipts remain intact. Same SEC URLs and honest User-Agent;
no retries, proxy disguise, alternate archive paths, or historical availability.
"""
import collections
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/cutoff-clock-followup-20261011/container-originals"
QUEUE = ROOT / "outputs/cutoff-clock-followup-20261011/queue.json"
QUEUE_SHA = "03feaeea3e6c23ce2c18e536fd062e63c1b6525fd1957c3624e78d27c6d72226"
UA = "Michael Baffour Awuah Disclosure-drift research https://github.com/michaelbawuah/Disclosure-drift"
MAX_BYTES = 8 * 1024 * 1024
LOCK = threading.Lock()
LAST = 0.0


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(body):
    return hashlib.sha256(body).hexdigest()


def write_new(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(raw)
    path.chmod(0o400)


def main():
    global LAST
    raw = QUEUE.read_bytes()
    if digest(raw) != QUEUE_SHA:
        raise ValueError("Public source queue pin differs")
    rows = json.loads(raw)["source_occurrences"]
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[row["ACCESSION_NUMBER"]].append(row)
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "collection_receipt.json").exists():
        raise FileExistsError("Completed public collection must not be overwritten")
    script = {"path": str(Path(__file__).relative_to(ROOT)), "sha256": digest(Path(__file__).read_bytes())}
    started = now()

    def fetch(accession):
        global LAST
        group = grouped[accession]
        if len({x["ISSUERCIK"] for x in group}) != 1:
            raise ValueError("Conflicting public archive location candidates")
        row = group[0]
        url = f"https://www.sec.gov/Archives/edgar/data/{int(row['ISSUERCIK'])}/{accession.replace('-', '')}/{accession}.txt"
        target = OUT / (accession + ".txt")
        receipt_path = OUT / (accession + ".receipt.json")
        attempt = {"accession": accession, "url": url, "attempt_started_utc": now()}
        try:
            if target.exists() or receipt_path.exists():
                body, receipt = target.read_bytes(), json.loads(receipt_path.read_bytes())
                if receipt["url"] != url or receipt["sha256"] != digest(body) or receipt["bytes"] != len(body):
                    raise ValueError("Existing initial probe source or receipt differs")
                attempt["status"] = "PRESERVED_VERIFIED_FROM_INITIAL_PROBE"
            else:
                with LOCK:
                    delay = 0.6 - (time.monotonic() - LAST)
                    if delay > 0:
                        time.sleep(delay)
                    LAST = time.monotonic()
                request_started = now()
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
                with urllib.request.urlopen(req, timeout=30) as response:
                    body = response.read(MAX_BYTES + 1)
                    if response.status != 200 or response.url != url or len(body) > MAX_BYTES:
                        raise ValueError("SEC response or bounded size differs")
                    if not body.startswith(("<SEC-DOCUMENT>" + accession + ".txt").encode()):
                        raise ValueError("Exact original SEC wrapper differs")
                    receipt = {"accession": accession, "url": url, "final_url": response.url,
                               "http_status": response.status, "sha256": digest(body), "bytes": len(body),
                               "path": str(target.relative_to(ROOT)), "request_started_utc": request_started,
                               "retrieved_at_utc": now(), "collector": script, "user_agent": UA,
                               "response_metadata": {k: response.headers.get(k) for k in
                                                     ("Content-Type", "Last-Modified", "ETag", "Date", "Content-Length", "Content-Encoding")},
                               "request_context": "Ordinary container urllib; unchanged user agent and exact original URL",
                               "historical_availability_inferred": False}
                write_new(target, body)
                write_new(receipt_path, receipt)
                attempt["status"] = "ORIGINAL_PRESERVED"
            target.chmod(0o400)
            receipt_path.chmod(0o400)
            attempt.update(sha256=receipt["sha256"], bytes=receipt["bytes"],
                           receipt_path=str(receipt_path.relative_to(ROOT)))
        except Exception as exc:
            attempt.update(status="SOURCE_NOT_PRESERVED", error_type=type(exc).__name__,
                           error=str(exc), http_status=getattr(exc, "code", None))
        attempt["completed_utc"] = now()
        write_new(OUT / (accession + ".attempt.json"), attempt)
        print(json.dumps({key: attempt[key] for key in ("accession", "status")}), flush=True)
        return attempt

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        attempts = list(executor.map(fetch, sorted(grouped)))
    if QUEUE.read_bytes() != raw or digest(Path(__file__).read_bytes()) != script["sha256"]:
        raise ValueError("Collector or source queue changed during execution")
    result = {"schema_version": 1, "started_utc": started, "completed_utc": now(),
              "queue_sha256": QUEUE_SHA, "collector": script, "accessions": len(grouped), "occurrences": len(rows),
              "attempts": attempts, "status_counts": dict(collections.Counter(x["status"] for x in attempts)),
              "request_policy": {"workers": 2, "minimum_seconds_between_request_starts": 0.6, "timeout_seconds": 30,
                                 "user_agent": UA, "maximum_bytes": MAX_BYTES, "automatic_retries": 0,
                                 "alternate_paths_or_disguised_headers_used": False},
              "mac_failure_receipts_preserved": True, "historical_availability_inferred": False}
    write_new(OUT / "collection_receipt.json", result)
    print(json.dumps({key: result[key] for key in ("accessions", "occurrences", "status_counts")}), flush=True)


if __name__ == "__main__":
    main()

