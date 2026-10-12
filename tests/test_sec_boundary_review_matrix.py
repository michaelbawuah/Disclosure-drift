"""Invented SEC original HTML only; no network or licensed source in unit tests."""

import csv
import gzip
import hashlib
import json

import pytest

import disclosure_research.sec_boundary_review_matrix as builder
from disclosure_research.extraction import TOKEN, clean_html, extract_risk_factors
from disclosure_research.protocol import canonical_hash, load_protocol
from disclosure_research.sec_boundary_review_verifier import independent_boundary_source_recheck


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _html(kind, idx):
    if kind == "ge":
        return (
            "<html><body><h1>Table of Contents</h1>"
            "<p>Item 1A. Risk Factors</p><p>Pages 50-57</p>"
            "<p>Item 1B. Unresolved Staff Comments</p><p>None</p>"
            "<h1>Actual unnumbered risk disclosure follows</h1>"
            "<p>Substantive risk paragraph " +
            " ".join(("invented business risk exposure and operating condition "
                      "market activity potential disruption") for _ in range(45)) +
            "</p><h1>Item 2. Properties</h1><p>End of reference text.</p></body></html>"
        ).encode()
    return (
        "<html><body><p>Table of Contents</p>"
        "<p>Item 1A. Risk Factors</p><p>" +
        " ".join(("Original annual corporate risk explanation "
                  "of conditions financial strategic exposure and business "
                  f"market {idx} ") for _ in range(38)) +
        "</p><p>Item 1B. Unresolved Staff Comments</p>"
        "<p>None this year</p><p>Item 2. Properties</p></body></html>"
    ).encode()


def _json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n")


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    inputs = root / "reports" / "pilot_expansion"
    sources = root / "outputs"
    inputs.mkdir(parents=True)
    sources.mkdir()
    config = load_protocol()
    special = sorted(builder.ALTERNATE)
    stock_acc = special + [
        f"{1000000000+i:010d}-20-{i+1:06d}" for i in range(14)
    ]
    diag_acc = stock_acc[2:4] + [
        f"{1100000000+i:010d}-21-{i+1:06d}" for i in range(14)
    ]
    assert len(set(stock_acc + diag_acc)) == 30
    diagnostic_path = sources / "diag"
    stock_path = sources / "class"
    d_html = diagnostic_path / "original_html"
    c_html = stock_path / "original_sec_bytes"
    d_html.mkdir(parents=True)
    c_html.mkdir(parents=True)
    metadata, manifest, old_records, rules = {}, [], [], []
    selected = sorted(set(stock_acc + diag_acc))
    for ordinal, accession in enumerate(selected):
        cik = accession[:10]
        year = 2020 if accession in stock_acc else 2021
        stamp = f"{year}-02-12T12:32:14-05:00"
        kind = "ge" if accession in builder.ALTERNATE else "normal"
        raw = _html(kind, ordinal)
        old_sha = _sha(raw + b"\n \n")  # prior byte version differs
        current = _sha(raw)
        norm = clean_html(raw)
        result = extract_risk_factors(raw)
        if kind == "ge":
            assert result.status == "review"
            first = norm.index("Substantive risk paragraph")
            last = norm.index("Item 2. Properties")
            text = norm[first:last].strip(" .:-\n")
            method = "same_document_range"
            saved_version = "reference-range-v1"
        else:
            assert result.status == "ok"
            first, last = result.start_offset, result.end_offset
            text = result.text
            method = "numbered_item1a"
            saved_version = result.version
        count = len(TOKEN.findall(text))
        assert count >= 200
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/invented-report.html"
        )
        manifest.append({
            "accessionNumber": accession, "cik": cik, "source_url": url,
            "acceptance_timestamp": stamp, "acceptance_date": stamp[:10],
            "download_sha256": old_sha, "risk_token_count": count,
            "resolution_method": method, "extraction_version": saved_version,
            "extraction_status": "ok", "extraction_start": first, "extraction_end": last,
            "risk_source_url": url,
        })
        old_records.append({
            "accession": accession, "manifest_cik_raw": cik,
            "recorded_acceptance_timestamp": stamp, "acceptance_date": stamp[:10],
            "header_identity": {"header_identity_consistent": True},
            "known_at": None, "available_at": None, "security_link_created": False,
            "primary_source": {"sha256": old_sha},
        })
        metadata[accession] = {
            "cik": cik, "year": year, "url": url, "new_sha": current, "old_sha": old_sha,
            "bytes": raw,
        }
        if accession in stock_acc:
            (c_html / (accession + ".original.html")).write_bytes(raw)
        if accession in diag_acc:
            (d_html / (accession + ".html")).write_bytes(raw)
        if kind == "ge":
            rules.append({
                "accession": accession,
                "kind": "same_document_range",
                "curation": "assistant-proposed; human boundary review pending",
                "source_url": url, "primary_url": url,
                "primary_sha256": old_sha, "source_sha256": old_sha,
                "start_offset": first, "end_offset": last,
                "token_count": count, "text_sha256": _sha(text.encode()),
            })
    for ordinal in range(185):
        cik = f"{8000000000+ordinal:010d}"
        acc = f"{cik}-18-{ordinal+1:06d}"
        url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
               f"{acc.replace('-', '')}/synthetic.htm")
        manifest.append({
            "accessionNumber": acc, "cik": cik, "source_url": url,
            "acceptance_timestamp": "2018-02-12T12:32:14-05:00",
            "acceptance_date": "2018-02-12", "download_sha256": "0"*64,
            "risk_token_count": 400, "resolution_method": "numbered_item1a",
            "extraction_version": "item1a-v1", "extraction_status": "ok",
            "extraction_start": 0, "extraction_end": 0, "risk_source_url": url,
        })
        old_records.append({"accession": acc})
    assert len(old_records) == len(manifest) == 215
    manifest_path = inputs / "filing_sources.csv"
    with manifest_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)
    monkeypatch.setattr(builder, "PINNED_MANIFEST_SHA", _sha(manifest_path.read_bytes()))
    _json(inputs / "pilot_checkpoint.json", {
        "data_kind": "REAL_SEC_TEXT_DESCRIPTIVE_PILOT",
        "files": {"text_features.csv": "synthetic-reference-sha"},
        "filings": 215, "pairs": 180, "protocol_sha256": canonical_hash(config),
        "human_filing_reviews": 0, "returns_read": False,
        "milestone_06_complete": False,
    })
    rules_path = root / "configs" / "source_ranges.json"
    rules_path.parent.mkdir(parents=True)
    _json(rules_path, {
        "schema_version": 1, "normalizer_version": "item1a-v1",
        "rules": rules,
    })
    original_report = root / "reports" / "prior_origins.gz"
    all_source = {
        "status": builder.SOURCE_REPORT,
        "original_sec_bytes_reread": True,
        "source_approvals": 0, "final_period_opened": False,
        "xbrl_fact_values_interpreted": False,
        "protocol_sha256": canonical_hash(config),
        "records": old_records,
    }
    uncompressed = json.dumps(all_source).encode()
    zipped = gzip.compress(uncompressed, mtime=0)
    original_report.write_bytes(zipped)
    original_execution = root / "reports" / "prior_execution.json"
    _json(original_execution, {
        "publication": {"sha256": _sha(zipped), "bytes": len(zipped),
                        "uncompressed_sha256": _sha(uncompressed)}
    })
    diag_rows = []
    for acc in diag_acc:
        meta = metadata[acc]
        diag_rows.append({
            "accession": acc, "cik": meta["cik"],
            "year": meta["year"], "original_SEC_url": meta["url"],
            "earlier_original_HTML_sha256": meta["old_sha"],
            "current_HTML_sha256": meta["new_sha"],
            "current_HTML_bytes": len(meta["bytes"]),
            "retrieval_status": "HTTP_200_VALID_SIZE",
            "extraction_status": "ok", "manual_Item1A_boundary_approved": False,
            "original_SEC_first_publication_at": None,
            "original_source_expected_Item1A_tokens":
                next(x["risk_token_count"] for x in manifest if x["accessionNumber"] == acc),
        })
    diag_raw = "".join(json.dumps(row) + "\n" for row in diag_rows).encode()
    diag_public = {
        "status": builder.ORIGINAL_DIAGNOSTIC,
        "counts": {"HTTP_200_original_documents": 16},
        "manual_original_item1a_boundary_reviews_approved": False,
        "first_publication_known_at_verified": False,
        "model_ready": False, "final_period_opened": False,
    }
    diag_public_bytes = json.dumps(diag_public).encode()
    (diagnostic_path / "private_original_source_rows.jsonl").write_bytes(diag_raw)
    (diagnostic_path / "public_summary.json").write_bytes(diag_public_bytes)
    _json(diagnostic_path / "receipt.json", {
        "status": builder.ORIGINAL_DIAGNOSTIC,
        "human_approvals": 0, "model_ready": False, "final_period_opened": False,
        "files": {
            "public_summary.json": {"sha256": _sha(diag_public_bytes)},
            "private_original_source_rows.jsonl": {"sha256": _sha(diag_raw)},
        },
    })
    class_rows = []
    for acc in stock_acc:
        meta = metadata[acc]
        class_rows.append({
            "accession": acc, "issuer_CIK": meta["cik"],
            "acceptance_year": meta["year"],
            "source_files": {"primary": {
                "status": "HTTP_200_VALID_SIZE",
                "current_source_availability_as_of_filing": False,
                "source_publication_time_verified": False,
                "saved_relative_path": f"original_sec_bytes/{acc}.original.html",
                "current_sha256": meta["new_sha"],
                "current_bytes": len(meta["bytes"]),
                "earlier_verified_sha256": meta["old_sha"],
                "source_url": meta["url"],
            }},
        })
    class_raw = json.dumps(class_rows).encode()
    class_public = {
        "status": builder.ORIGINAL_CLASS,
        "retrieved_HTTP_200_source_objects": 32,
        "new_source_approvals": 0, "model_ready": False, "final_period_opened": False,
    }
    class_public_bytes = json.dumps(class_public).encode()
    (stock_path / "private_source_fetch_receipts.json").write_bytes(class_raw)
    (stock_path / "public_summary.json").write_bytes(class_public_bytes)
    _json(stock_path / "receipt.json", {
        "status": builder.ORIGINAL_CLASS,
        "new_approved_historical_links": 0,
        "model_ready": False, "final_period_opened": False,
        "files": {
            "public_summary.json": {"sha256": _sha(class_public_bytes)},
            "private_source_fetch_receipts.json": {"sha256": _sha(class_raw)},
        },
    })
    return {
        "root": root, "features": inputs, "diag": diagnostic_path,
        "class": stock_path, "rules": rules_path,
        "gz": original_report, "execution": original_execution,
        "output": sources / "boundaries",
        "verification": root / "reports" / "independent_boundaries.json",
        "config": config, "metadata": metadata,
    }


def build(x):
    return builder.build_original_sec_boundary_matrix(
        x["diag"], x["class"], x["features"], x["rules"],
        x["gz"], x["execution"], x["output"],
        config=x["config"], repo_root=x["root"],
    )


def verify(x):
    return independent_boundary_source_recheck(
        x["diag"], x["class"], x["features"], x["rules"],
        x["gz"], x["output"], x["verification"],
        config=x["config"], repo_root=x["root"],
    )


def alter_private_rehash(x, filename, update):
    p = x["output"] / filename
    before = p.read_text()
    after = update(before)
    p.chmod(0o600)
    p.write_text(after)
    receipt_path = x["output"] / "receipt.json"
    receipt_path.chmod(0o600)
    receipt = json.loads(receipt_path.read_text())
    payload = p.read_bytes()
    receipt["files"][filename] = {
        "sha256": _sha(payload), "bytes": len(payload),
    }
    receipt_path.write_text(json.dumps(receipt))


def test_30_original_sec_source_boundaries_reproduce_with_no_approvals(prepared):
    info = build(prepared)
    assert info["source_cache_record_count"] == 32
    assert info["identical_duplicate_current_SEC_source_files_in_both_caches"] == 2
    assert info["counts"]["unique_original_SEC_filing_bodies"] == 30
    assert info["counts"]["direct_substantive_item1a_source_boundaries"] == 28
    assert info["counts"]["registered_alternate_source_boundaries"] == 2
    assert info["counts"]["source_risk_text_token_count_matches_original_manifest"] == 30
    assert info["counts"]["current_original_HTML_bytes_same_as_earlier_source"] == 0
    assert info["new_source_or_human_approvals"] == 0
    assert not info["model_ready"] and not info["final_period_opened"]
    assert not info["historical_SEC_first_publication_available_at_established"]
    folder = prepared["output"]
    assert folder.stat().st_mode & 0o077 == 0
    receipt = json.loads((folder / "receipt.json").read_text())
    for name, declaration in receipt["files"].items():
        p = folder / name
        assert _sha(p.read_bytes()) == declaration["sha256"]
        assert p.stat().st_mode & 0o222 == 0
    assert "<script" not in (folder / "private_review.html").read_text().lower()


def test_source_verifier_rebuilds_original_30_from_both_caches(prepared):
    build(prepared)
    result = verify(prepared)
    assert result["independent_current_original_SEC_body_files_checked"] == 30
    assert result["independent_direct_bounded_Item1A_texts_reproduced"] == 28
    assert result["independent_registered_GE_Item1A_text_digests_reproduced"] == 2
    assert result["all_source_risk_text_counts_and_surrounding_boundaries_reproduced"]
    assert result["duplicate_current_source_bytes_verified_across_both_caches"] == 2
    assert not result["source_first_public_dissemination_time_certified"]
    assert result["manual_section_boundary_reviews_completed_here"] == 0
    assert not result["model_ready"]


def test_invented_registered_GE_range_rejects_forged_section_hash(prepared):
    settings = json.loads(prepared["rules"].read_text())
    settings["rules"][0]["text_sha256"] = "f"*64
    _json(prepared["rules"], settings)
    with pytest.raises(ValueError, match="registered risk-section text"):
        build(prepared)


def test_fake_original_html_current_source_bytes_refused(prepared):
    accession = next(iter(prepared["metadata"]))
    cache = prepared["class"] / "original_sec_bytes" / (accession + ".original.html")
    if cache.exists():
        cache.write_bytes(cache.read_bytes() + b"source mutation")
    else:
        cache = prepared["diag"] / "original_html" / (accession + ".html")
        cache.write_bytes(cache.read_bytes() + b"source mutation")
    with pytest.raises(ValueError, match="HTML changed|SEC diagnostic HTML bytes"):
        build(prepared)


def test_current_file_duplicate_disagreement_fails(prepared):
    dup = sorted(
        set(p.stem for p in (prepared["diag"] / "original_html").glob("*.html"))
        & set(p.name[:20] for p in (prepared["class"] / "original_sec_bytes").glob("*.html"))
    )
    assert len(dup) == 2
    original = prepared["diag"] / "original_html" / (dup[0] + ".html")
    original.write_bytes(original.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="diagnostic HTML bytes disagree"):
        build(prepared)


def test_source_verifier_refuses_forged_approval_even_if_public_rehashed(prepared):
    build(prepared)
    def change(raw):
        result = json.loads(raw)
        result["model_ready"] = True
        return json.dumps(result)
    alter_private_rehash(prepared, "public_summary.json", change)
    with pytest.raises(ValueError, match="falsely signals approval"):
        verify(prepared)


def test_source_verifier_refuses_forged_GE_section_even_with_matching_receipt(prepared):
    build(prepared)
    def change(raw):
        rows = [json.loads(line) for line in raw.splitlines()]
        selected = next(row for row in rows if row["accession"] in builder.ALTERNATE)
        selected["risk_text_sha256"] = "0" * 64
        return "".join(json.dumps(line, sort_keys=True) + "\n" for line in rows)
    alter_private_rehash(prepared, "private_filing_boundaries.jsonl", change)
    with pytest.raises(ValueError, match="risk text boundary preview, count or SHA"):
        verify(prepared)


def test_source_verifier_refuses_spurious_manual_signoff(prepared):
    build(prepared)
    def change(raw):
        rows = [json.loads(line) for line in raw.splitlines()]
        rows[0]["manual_boundary_and_pair_review_approved"] = True
        return "".join(json.dumps(line, sort_keys=True) + "\n" for line in rows)
    alter_private_rehash(prepared, "private_filing_boundaries.jsonl", change)
    with pytest.raises(ValueError, match="unapproved research gates changed"):
        verify(prepared)


def test_source_html_escapes_malicious_original_text():
    example = {
        "accession": "0000012345-20-000012",
        "acceptance_year": 2020,
        "source_boundary_method": "DIRECT_NUMBERED_ITEM1A_AUTOMATED",
        "risk_token_count": 220,
        "original_sec_url": "https://www.sec.gov/Archives/edgar/data/12345/000001234520000012/file.htm",
        "issuer_CIK": "0000012345",
        "surrounding_start_private": "<script>alert(1)</script>",
        "section_start_preview_private": '<img src=x onerror=alert(1)>',
        "section_end_preview_private": "<svg onload=alert(1)>",
        "surrounding_end_private": "<script>alert(9)</script>",
    }
    rendered = builder._render_review([example])
    assert "<script" not in rendered.lower()
    assert "<img " not in rendered.lower()
    assert "<svg " not in rendered.lower()
    assert "&lt;script&gt;" in rendered
    assert "read-only" in rendered.lower()


def test_source_refuses_mutation_to_future_year_even_with_correct_sha(prepared, monkeypatch):
    path = prepared["features"] / "filing_sources.csv"
    entries = list(csv.DictReader(path.open()))
    entries[0]["acceptance_timestamp"] = "2025-02-12T12:32:14-05:00"
    with path.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(entries[0]))
        writer.writeheader()
        writer.writerows(entries)
    monkeypatch.setattr(builder, "PINNED_MANIFEST_SHA", _sha(path.read_bytes()))
    with pytest.raises(ValueError, match="verified original SEC issuer CIK/acceptance clock"):
        build(prepared)


def test_existing_source_review_bundle_not_overwritten(prepared):
    build(prepared)
    with pytest.raises(ValueError, match="new private outputs"):
        build(prepared)


def test_safe_source_locator_refuses_foreign_host_and_query():
    acc = "0000012345-20-000012"
    expected = "https://www.sec.gov/Archives/edgar/data/12345/000001234520000012/file.htm"
    assert builder._sec_url(expected, acc, "0000012345")
    assert not builder._sec_url(expected + "?tamper=1", acc, "0000012345")
    assert not builder._sec_url(expected.replace("www.sec.gov", "evil.example"), acc, "0000012345")
