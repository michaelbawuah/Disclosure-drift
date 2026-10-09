"""Offline filing evidence and fingerprinted review records, separate from sign-off."""

import hashlib
import json
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import urlparse

import duckdb
import pandas as pd
from lxml.etree import ParserError

from .extraction import VERSION, clean_html, extract_risk_factors
from .timing import acceptance_from_header, event_window


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def cached_body(cache: Path, url: str, expected_hash: str) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"www.sec.gov", "data.sec.gov"}:
        raise ValueError("Evidence must refer to an official HTTPS SEC URL")
    key = digest(url)
    body = (cache / f"{key}.bin").read_bytes()
    meta = json.loads((cache / f"{key}.json").read_text())
    if meta["url"] != url or digest(body) != meta["sha256"] or digest(body) != expected_hash:
        raise ValueError("Source hash or cached provenance differs from the filing record")
    return body


def excerpt(text: str, tail: bool = False, words: int = 6) -> str:
    tokens = text.split()
    return " ".join(tokens[-words:] if tail else tokens[:words])


def load_reviews(path: str | Path | None) -> dict:
    if path is None:
        return {}
    reviews = {}
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        accession = row["accession"]
        if accession in reviews:
            raise ValueError(f"Duplicate review for {accession}")
        if row.get("reviewer_type") not in {"human", "assistant"}:
            raise ValueError(f"Invalid reviewer type on review line {number}")
        for field in ("boundary_verdict", "timing_verdict"):
            if row.get(field) not in {"pending", "pass", "fail"}:
                raise ValueError(f"Invalid {field} on review line {number}")
        if any(row[field] != "pending" for field in ("boundary_verdict", "timing_verdict")):
            if not row.get("reviewer", "").strip() or not row.get("notes", "").strip():
                raise ValueError("A completed review needs a named reviewer and notes")
            reviewed_at = datetime.fromisoformat(row.get("reviewed_at", ""))
            if reviewed_at.tzinfo is None:
                raise ValueError("Review timestamp must include a timezone")
        reviews[accession] = row
    return reviews


def filing_evidence(row: dict, cache: Path, review: dict | None = None) -> dict:
    issues, cautions = [], ["public_dissemination_unverified"]
    item = {"accession": row["accessionNumber"], "cik": row["cik"], "name": row["name"],
            "filing_date": row["filingDate"], "report_date": row["reportDate"],
            "source_url": row["source_url"], "header_url": row["header_url"],
            "download_sha256": row["download_sha256"],
            "extraction_version": row["extraction_version"],
            "risk_text_sha256": digest(row["risk_text"]),
            "risk_token_count": int(row["risk_token_count"]),
            "acceptance_timestamp": row["acceptance_timestamp"],
            "api_timestamp": str(row.get("acceptanceDateTime", "")),
            "reference_session": row["reference_session"], "label_end": row["label_end"],
            "extraction_status": row["extraction_status"],
            "api_header_difference_seconds": None,
            "verified_source": False, "verified_header": False,
            "start_context": "", "section_start": "", "section_end": "", "end_context": ""}
    header_hash = row.get("header_sha256")
    item["header_sha256"] = header_hash if isinstance(header_hash, str) else ""
    try:
        raw = cached_body(cache, row["source_url"], row["download_sha256"])
        item["verified_source"] = True
        extracted = extract_risk_factors(raw)
        normalized = clean_html(raw)
        if row["extraction_version"] != VERSION:
            issues.append("parser_version_changed")
        if extracted.text != row["risk_text"] or extracted.token_count != row["risk_token_count"]:
            issues.append("stored_extraction_differs_from_source")
        if extracted.status != "ok" or row["extraction_status"] != "ok":
            issues.append("extraction_requires_review")
        if extracted.start_offset is not None:
            item.update(start_context=excerpt(normalized[:extracted.start_offset], tail=True),
                        section_start=excerpt(extracted.text), section_end=excerpt(extracted.text, tail=True),
                        end_context=excerpt(normalized[extracted.end_offset:]))
    except (OSError, ValueError, KeyError, ParserError) as exc:
        issues.append("source_evidence_unavailable_or_changed")
        item["source_error"] = str(exc)
    try:
        header = cached_body(cache, row["header_url"], item["header_sha256"])
        accepted = acceptance_from_header(header.decode("utf-8", errors="replace"))
        item["verified_header"] = True
        if accepted.isoformat() != row["acceptance_timestamp"]:
            issues.append("stored_acceptance_differs_from_header")
        window = event_window(accepted)
        if (window.reference_session != row["reference_session"] or
                window.label_end != row["label_end"] or
                window.controls_through != row["controls_through"]):
            issues.append("stored_event_window_differs_from_calendar")
        try:
            api = datetime.fromisoformat(item["api_timestamp"].replace("Z", "+00:00"))
            if api.tzinfo is None:
                raise ValueError("Naive API timestamp")
            item["api_header_difference_seconds"] = (api - accepted).total_seconds()
            if item["api_header_difference_seconds"] != 0:
                cautions.append("api_header_timestamp_disagreement")
        except ValueError:
            item["api_header_difference_seconds"] = None
            cautions.append("api_timestamp_not_interpretable")
    except (OSError, ValueError, KeyError) as exc:
        issues.append("header_evidence_unavailable_or_changed")
        item["header_error"] = str(exc)
    fingerprint_fields = ["accession", "source_url", "header_url", "download_sha256", "header_sha256",
                          "extraction_version", "risk_text_sha256", "acceptance_timestamp",
                          "api_timestamp", "reference_session", "label_end"]
    item["evidence_id"] = digest(json.dumps({k: item[k] for k in fingerprint_fields}, sort_keys=True))
    item.update(review_status="pending", boundary_verdict="pending", timing_verdict="pending",
                reviewer_type="", human_review_complete=False, assistant_review_complete=False)
    if review:
        if review.get("evidence_id") != item["evidence_id"]:
            issues.append("stale_review_fingerprint")
            item["review_status"] = "stale"
        else:
            item.update(boundary_verdict=review["boundary_verdict"], timing_verdict=review["timing_verdict"],
                        reviewer_type=review["reviewer_type"])
            verdicts = [review["boundary_verdict"], review["timing_verdict"]]
            if "fail" in verdicts:
                item["review_status"] = "failed"
                issues.append("review_failed")
            elif verdicts == ["pass", "pass"] and not issues:
                item["review_status"] = "complete"
                item[f"{review['reviewer_type']}_review_complete"] = True
    item["blocking_issues"], item["cautions"] = issues, cautions
    item["automated_evidence_ok"] = not issues
    return item


def render_html(records: list[dict], summary: dict) -> str:
    cards = []
    for row in records:
        checks = ", ".join(row["blocking_issues"] + row["cautions"])
        snippets = "".join(f"<h4>{title}</h4><p>{escape(row[key])}</p>" for key, title in [
            ("start_context", "Before the extracted section"), ("section_start", "Section beginning"),
            ("section_end", "Section ending"), ("end_context", "After the extracted section")])
        cards.append(f'''<details><summary>{escape(row['name'])} · {escape(row['filing_date'])}
            · {row['risk_token_count']:,} tokens · review {escape(row['review_status'])}</summary>
            <p><a href="{escape(row['source_url'], quote=True)}">Full SEC filing</a> ·
            <a href="{escape(row['header_url'], quote=True)}">SGML header</a></p>
            <dl><dt>Accession</dt><dd>{escape(row['accession'])}</dd>
            <dt>Header interpretation</dt><dd>{escape(row['acceptance_timestamp'])}</dd>
            <dt>Raw API timestamp</dt><dd>{escape(row['api_timestamp'])}</dd>
            <dt>Reference / label-end sessions</dt><dd>{escape(row['reference_session'])} / {escape(row['label_end'])}</dd>
            <dt>Review notes required</dt><dd>{escape(checks)}</dd>
            <dt>Evidence fingerprint</dt><dd><code>{row['evidence_id']}</code></dd></dl>{snippets}</details>''')
    return '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Disclosure Drift — filing audit</title><style>
body{font:16px/1.6 system-ui,sans-serif;max-width:1050px;margin:40px auto;padding:0 22px;color:#172b3a;background:#f8fafb}
h1,h2{line-height:1.2}a{color:#07569c}details{background:white;border:1px solid #cbd6df;border-radius:8px;margin:12px 0;padding:16px}
summary{cursor:pointer;font-weight:650}dt{font-weight:650}dd{margin:0 0 10px;overflow-wrap:anywhere}h4{margin:14px 0 2px}
code{font-size:12px}pre{white-space:pre-wrap;background:#eaf0f5;padding:18px;border-radius:8px}
</style><h1>Disclosure Drift: filing audit</h1>
<p>Source integrity and boundary evidence for the extraction pilot. Automated consistency checks are not human sign-off.
Open each complete SEC filing and its header before reviewing. The excerpts show boundaries only.</p>
<p>Public dissemination remains unverified; the study uses its declared two-session timing proxy.
This report contains no market-return findings.</p><h2>Coverage</h2><pre>''' + escape(
        json.dumps(summary, indent=2)) + "</pre><h2>Filing evidence</h2>" + "".join(cards) + "</html>"


def select_review_pairs(pairs: pd.DataFrame, count: int = 30, seed: int = 20261009) -> pd.DataFrame:
    """Cover issuers first, then fill by a stable hash; no returns enter selection."""
    columns = ["cik", "accession", "previous_accession", "acceptance_date",
               "source_url", "previous_source_url"]
    if count < 1 or pairs["accession"].duplicated().any():
        raise ValueError("Review selection needs a positive count and unique pair accessions")
    ranked = pairs[columns].copy()
    ranked["selection_key"] = ranked.apply(
        lambda r: digest(f"{seed}|{r['cik']}|{r['accession']}"), axis=1)
    ranked = ranked.sort_values("selection_key")
    first = ranked.drop_duplicates("cik").head(count)
    remaining = ranked[~ranked["accession"].isin(first["accession"])].head(count - len(first))
    return pd.concat([first, remaining]).sort_values(["cik", "acceptance_date"])


def build_audit(filings: str | Path, cache: str | Path, output: str | Path,
                development_end: int, reviews: str | Path | None = None,
                pairs: str | Path | None = None) -> dict:
    frame = pd.read_parquet(filings)
    if frame.empty or frame["accessionNumber"].duplicated().any():
        raise ValueError("Audit requires nonempty filings with unique accessions")
    if frame["acceptance_date"].map(lambda x: int(x[:4])).max() > development_end:
        raise ValueError("This audit command accepts development-year filings only")
    review_map = load_reviews(reviews)
    if set(review_map) - set(frame["accessionNumber"]):
        raise ValueError("Review file includes accessions outside the supplied filing table")
    rows = [filing_evidence(row, Path(cache), review_map.get(row["accessionNumber"]))
            for row in frame.sort_values(["cik", "acceptance_date"]).to_dict("records")]
    pairs_path = Path(pairs) if pairs is not None else Path(filings).with_name("filing_pairs.parquet")
    pair_count, selected = 0, None
    if pairs_path.exists():
        pair_frame = pd.read_parquet(pairs_path)
        known = frame.set_index("accessionNumber")
        for pair in pair_frame.to_dict("records"):
            if pair["accession"] not in known.index or pair["previous_accession"] not in known.index:
                raise ValueError("Pair references a filing outside the audited source table")
            current, previous = known.loc[pair["accession"]], known.loc[pair["previous_accession"]]
            if (current["cik"] != pair["cik"] or previous["cik"] != pair["cik"] or
                    current["acceptance_date"] != pair["acceptance_date"]):
                raise ValueError("Pair identity or timing differs from the audited filing table")
        pair_count = len(pair_frame)
        selected = select_review_pairs(pair_frame)
    elif pairs is not None:
        raise FileNotFoundError(pairs_path)
    evidence = pd.DataFrame(rows)
    with duckdb.connect() as con:
        con.register("evidence", evidence)
        coverage = con.execute('''SELECT cik, name, count(*) AS filings,
            min(filing_date) AS first_filing, max(filing_date) AS last_filing,
            count(*) FILTER (WHERE automated_evidence_ok) AS automated_consistency_ok,
            count(*) FILTER (WHERE human_review_complete) AS human_reviews_complete,
            count(*) FILTER (WHERE assistant_review_complete) AS assistant_reviews_complete,
            count(*) FILTER (WHERE api_header_difference_seconds != 0) AS timestamp_disagreements
            FROM evidence GROUP BY cik, name ORDER BY cik''').df()
    summary = {"filings": len(rows), "issuers": len(coverage),
               "annual_pairs": pair_count, "pairs_selected_for_review": len(selected) if selected is not None else 0,
               "automated_evidence_ok": sum(r["automated_evidence_ok"] for r in rows),
               "filings_with_blocking_issues": sum(bool(r["blocking_issues"]) for r in rows),
               "timestamp_disagreements": sum("api_header_timestamp_disagreement" in r["cautions"] for r in rows),
               "human_reviews_complete": sum(r["human_review_complete"] for r in rows),
               "assistant_reviews_complete": sum(r["assistant_review_complete"] for r in rows),
               "source_table_sha256": digest(Path(filings).read_bytes()),
               "manual_audit": "complete" if all(r["human_review_complete"] for r in rows) else "pending",
               "dissemination_verification": "pending; second-session proxy remains explicit",
               "market_returns_used": False}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    evidence.to_parquet(output / "filing_evidence.parquet", index=False)
    coverage.to_parquet(output / "coverage.parquet", index=False)
    coverage.to_csv(output / "coverage.csv", index=False)
    if selected is not None:
        selected.to_csv(output / "review_pairs.csv", index=False)
    else:
        (output / "review_pairs.csv").unlink(missing_ok=True)
    (output / "audit_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "audit.html").write_text(render_html(rows, summary))
    template = [{"accession": r["accession"], "evidence_id": r["evidence_id"],
                 "reviewer": "", "reviewer_type": "human", "reviewed_at": "",
                 "boundary_verdict": "pending", "timing_verdict": "pending", "notes": ""} for r in rows]
    (output / "reviews.template.jsonl").write_text("".join(json.dumps(r) + "\n" for r in template))
    return summary
