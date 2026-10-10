import httpx
import pytest
import pandas as pd

from disclosure_research.edgar import SecClient, list_original_filings, rows_from_columns
from disclosure_research.extraction import clean_html, extract_risk_factors, pair_filings
from disclosure_research.ingest import ingest_smoke


def test_cache_avoids_second_network_request_and_detects_corruption(tmp_path):
    calls = []
    def transport(request):
        calls.append(str(request.url))
        assert request.headers["User-Agent"] == "Research contact test@example.org"
        assert request.headers["Accept-Encoding"] == "identity"
        return httpx.Response(200, content=b'{"ok":true}')
    client = SecClient(tmp_path, "Research contact test@example.org", transport=httpx.MockTransport(transport), sleep=lambda _: None)
    url = "https://data.sec.gov/submissions/CIK0000000001.json"
    body, first = client.fetch(url)
    assert first["cache_hit"] is False
    assert client.fetch(url)[1]["cache_hit"] is True
    assert len(calls) == 1
    next(tmp_path.glob("*.bin")).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="provenance"):
        client.fetch(url)


def test_429_retries_with_bounded_backoff(tmp_path):
    calls, sleeps = [], []
    def transport(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, content=b"ok")
    client = SecClient(tmp_path, "Research test@example.org", transport=httpx.MockTransport(transport), sleep=sleeps.append)
    assert client.fetch("https://www.sec.gov/test")[0] == b"ok"
    assert len(calls) == 2 and 2 in sleeps


def test_forbidden_response_is_not_retried(tmp_path):
    calls = []
    def transport(request):
        calls.append(1)
        return httpx.Response(403)
    client = SecClient(tmp_path, "Research test@example.org", transport=httpx.MockTransport(transport), sleep=lambda _: None)
    with pytest.raises(httpx.HTTPStatusError):
        client.fetch("https://www.sec.gov/test")
    assert len(calls) == 1


@pytest.mark.parametrize("recover", [True, False])
def test_transport_timeout_has_a_finite_retry_budget(tmp_path, recover):
    calls = []
    def transport(request):
        calls.append(str(request.url))
        if not recover or len(calls) == 1:
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        return httpx.Response(200, content=b"complete")
    client = SecClient(tmp_path, "Research test@example.org", retries=1,
                       transport=httpx.MockTransport(transport), sleep=lambda _: None)
    if recover:
        assert client.fetch("https://www.sec.gov/test")[0] == b"complete"
    else:
        with pytest.raises(httpx.ReadTimeout):
            client.fetch("https://www.sec.gov/test")
        assert not list(tmp_path.glob("*.bin"))
    assert len(calls) == 2


def test_oversized_response_never_enters_the_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("disclosure_research.edgar.MAX_DOCUMENT_BYTES", 8)
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=b"123456789"))
    client = SecClient(tmp_path, "Research test@example.org", transport=transport,
                       sleep=lambda _: None)
    with pytest.raises(ValueError, match="per-document limit"):
        client.fetch("https://www.sec.gov/test")
    assert not list(tmp_path.glob("*.bin"))
    assert not list(tmp_path.glob("*.json"))


def test_redirect_is_not_followed_or_cached(tmp_path):
    calls = []
    def transport(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://example.org/document"})
    client = SecClient(tmp_path, "Research test@example.org", transport=httpx.MockTransport(transport),
                       sleep=lambda _: None)
    with pytest.raises(httpx.HTTPStatusError):
        client.fetch("https://www.sec.gov/test")
    assert calls == ["https://www.sec.gov/test"]
    assert not list(tmp_path.glob("*.bin"))


def test_client_rejects_unrelated_hosts_and_missing_contact(tmp_path):
    with pytest.raises(ValueError, match="contact"):
        SecClient(tmp_path, "anonymous")
    client = SecClient(tmp_path, "Research test@example.org")
    with pytest.raises(ValueError, match="official"):
        client.fetch("https://example.org/document")


def test_historical_submission_pages_and_amendment_filter(tmp_path):
    pages = {
        "https://data.sec.gov/submissions/CIK0000000123.json": {
            "filings": {"recent": {"accessionNumber": [], "filingDate": [], "form": []},
                        "files": [{"name": "CIK0000000123-submissions-001.json",
                                   "filingFrom": "2010-01-01", "filingTo": "2020-12-31"}]}},
        "https://data.sec.gov/submissions/CIK0000000123-submissions-001.json": {
            "accessionNumber": ["0000000123-19-000001", "0000000123-19-000002"],
            "filingDate": ["2019-03-01", "2019-03-10"], "form": ["10-K", "10-K/A"],
            "primaryDocument": ["annual.htm", "amend.htm"]},
    }
    def transport(request):
        return httpx.Response(200, json=pages[str(request.url)])
    client = SecClient(tmp_path, "Research test@example.org", transport=httpx.MockTransport(transport), sleep=lambda _: None)
    rows = list_original_filings(client, "123", 2019, 2019)
    assert len(rows) == 1 and rows[0]["form"] == "10-K"
    assert rows[0]["source_url"].endswith("/123/000000012319000001/annual.htm")


def test_submission_columns_must_align():
    with pytest.raises(ValueError, match="lengths"):
        rows_from_columns({"accessionNumber": ["a"], "form": []})


def body(word, count=250):
    return " ".join([word] * count)


def test_extract_ignores_contents_entry_and_preserves_inline_heading():
    raw = f"""<html><body><div>Item 1A. Risk Factors</div><div>Item 1B. Unresolved Staff Comments</div>
    <h2><span>Item </span><b>1A.</b> <span>Risk Factors</span></h2><p>{body('competition')}</p>
    <h2>Item 1B. Unresolved Staff Comments</h2><p>none</p></body></html>"""
    result = extract_risk_factors(raw)
    assert result.status == "ok" and result.token_count == 250
    assert result.candidate_count == 2
    assert "Unresolved" not in result.text


def test_missing_end_is_flagged_instead_of_swallowing_entire_report():
    result = extract_risk_factors(f"<h2>Item 1A. Risk Factors</h2><p>{body('risk')}</p>")
    assert result.status == "missing"


def test_hidden_text_does_not_pollute_section():
    raw = f"<h2>Item 1A. Risk Factors</h2><div style='display: none'>secret</div><p>{body('risk')}</p><h2>Item 2. Properties</h2>"
    assert "secret" not in clean_html(raw)
    assert extract_risk_factors(raw).status == "ok"


def test_duplicate_substantive_sections_require_review():
    section = f"<h2>Item 1A. Risk Factors</h2><p>{body('risk')}</p><h2>Item 1B. Unresolved Staff Comments</h2>"
    assert extract_risk_factors(section + section).status == "review"


@pytest.mark.parametrize("continuation", [" (Continued)", " — Continued", " Continued"])
def test_continuation_page_headings_preserve_the_entire_risk_section(continuation):
    raw = (f"<h2>Item 1A. Risk Factors</h2><p>{body('opening', 250)}</p>"
           f"<h2>Item 1A. Risk Factors{continuation}</h2><p>{body('middle', 250)}</p>"
           f"<h2>Item 1A. Risk Factors{continuation}</h2><p>{body('ending', 40)}</p>"
           "<h2>Item 1B. Unresolved Staff Comments</h2><p>outside the section</p>")
    result = extract_risk_factors(raw)
    assert result.status == "ok"
    assert result.text.count("opening") == result.text.count("middle") == 250
    assert result.text.count("ending") == 40
    assert "outside" not in result.text
    assert result.version == "item1a-v2-continued-headings"


def test_continuation_without_an_original_heading_remains_missing():
    raw = (f"<h2>Item 1A. Risk Factors (Continued)</h2><p>{body('truncated')}</p>"
           "<h2>Item 1B. Unresolved Staff Comments</h2>")
    assert extract_risk_factors(raw).status == "missing"


def test_normal_heading_with_continued_as_first_body_word_stays_eligible():
    raw = (f"<h2>Item 1A. Risk Factors</h2><p>Continued {body('competition')}</p>"
           "<h2>Item 1B. Unresolved Staff Comments</h2>")
    result = extract_risk_factors(raw)
    assert result.status == "ok" and result.text.startswith("Continued competition")
    assert result.version == "item1a-v1"


def record(year, status="ok"):
    return {"cik": "0000000123", "acceptance_date": f"{year}-03-01", "accessionNumber": str(year),
            "reportDate": f"{year - 1}-12-31", "extraction_status": status, "risk_text": "risk supply",
            "source_url": "https://www.sec.gov/example", "reference_session": f"{year}-03-04",
            "label_end": f"{year}-04-01"}


def test_pairing_never_skips_failed_previous_year():
    pairs, exclusions = pair_filings([record(2018), record(2019, "review"), record(2020)], 2019, 2020)
    assert pairs == []
    assert len(exclusions) == 2


def test_pairing_preserves_issuer_and_consecutive_report_period():
    pairs, exclusions = pair_filings([record(2018), record(2019), record(2021)], 2019, 2021)
    assert len(pairs) == 1 and pairs[0]["previous_accession"] == "2018"
    assert exclusions[0]["reason"] == "nonannual_or_missing_report_period"


def test_header_evidence_wins_over_disagreeing_api_and_empty_run_clears_stale_data(tmp_path, monkeypatch):
    import hashlib
    rows = [{"cik": "0000000123", "accessionNumber": str(year), "filingDate": f"{year}-03-01",
             "reportDate": f"{year-1}-12-31", "form": "10-K",
             "acceptanceDateTime": f"{year}-03-02T05:00:00Z",
             "source_url": f"https://www.sec.gov/{year}.htm", "header_url": f"https://www.sec.gov/{year}.sgml"}
            for year in [2018, 2019]]
    monkeypatch.setattr("disclosure_research.ingest.list_original_filings", lambda *args: rows)
    class Client:
        network_requests = 0
        def fetch(self, url):
            year = url.rsplit('/', 1)[-1][:4]
            raw = (f"<ACCEPTANCE-DATETIME>{year}0301100000" if url.endswith("sgml") else
                   f"<h2>Item 1A. Risk Factors</h2><p>{body('risk')}</p><h2>Item 2. Properties</h2>").encode()
            return raw, {"sha256": hashlib.sha256(raw).hexdigest(), "fetched_at": "2026-10-09T00:00:00Z"}
    config = {"companies": [{"cik": "123", "name": "Synthetic"}], "purpose": "test",
              "filing_year_start": 2018, "filing_year_end": 2019, "pair_year_start": 2019, "pair_year_end": 2019}
    summary = ingest_smoke(config, Client(), tmp_path)
    frame = pd.read_parquet(tmp_path / "filings.parquet")
    assert set(frame.acceptance_source) == {"sgml_header"}
    assert frame.acceptance_date.tolist() == ["2018-03-01", "2019-03-01"]
    assert (frame.api_header_difference_seconds == 14 * 3600).all()
    assert summary["pairs_ready_for_manual_review"] == 1
    monkeypatch.setattr("disclosure_research.ingest.list_original_filings", lambda *args: [])
    empty = ingest_smoke(config, Client(), tmp_path)
    assert empty["failures"]
    assert not (tmp_path / "filings.parquet").exists()
    assert not (tmp_path / "filing_pairs.parquet").exists()
