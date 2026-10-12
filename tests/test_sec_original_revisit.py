"""Invented original SEC files only; mock HTTP to avoid any network call."""

import csv
import gzip
import hashlib
import json

import pytest

import disclosure_research.sec_original_revisit as revisit
from disclosure_research.protocol import canonical_hash, load_protocol
from disclosure_research.sec_identity_evidence import (
    _clock, cover_evidence, header_identity,
)
from disclosure_research.sec_original_revisit_verifier import reparse_16_sec_originals


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _fake_original(cik, accession, stamp):
    dt = stamp[:4] + stamp[5:7] + stamp[8:10] + stamp[11:13] + stamp[14:16] + stamp[17:19]
    head = (
        f'<SEC-HEADER>\n<ACCESSION-NUMBER>{accession}\n'
        '<TYPE>10-K\n'
        f'<ACCEPTANCE-DATETIME>{dt}\n'
        '<FILER>\n<COMPANY-DATA>\n'
        f'<CIK>{cik}\n<CONFORMED-NAME>SYNTHETIC RESEARCH ISSUER\n'
        '</COMPANY-DATA>\n</FILER>\n</SEC-HEADER>\n'
    ).encode()
    body = (
        '<html xmlns:dei="http://xbrl.sec.gov/dei/2019-01-31">'
        '<body><p>Invented original report</p></body></html>\n'
    ).encode()
    old_body = body + b' \n  '
    assert len(old_body) == len(body) + 4
    assert cover_evidence(body) == cover_evidence(old_body)
    return body, old_body, head


@pytest.fixture
def sources(tmp_path, monkeypatch):
    repo = tmp_path / "disclosure"
    inputs = repo / "data" / "inputs"
    outputs = repo / "outputs"
    inputs.mkdir(parents=True)
    outputs.mkdir()
    cfg = load_protocol()
    report = repo / "reports"
    report.mkdir()
    index, allreports, pairs, lookup = [], [], [], {}
    for i in range(8):
        cik = f'{1000000000 + i:010d}'
        rows = []
        for year in (2020, 2021):
            accession = f'{cik}-{year % 100:02d}-{i*2+year-2019:06d}'
            stamp = f'{year}-02-19T14:12:34-05:00'
            body, old, hdr = _fake_original(cik, accession, stamp)
            base = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/'
            primary_url, header_url = base + 'annual.htm', base + accession + '.hdr.sgml'
            lookup[primary_url] = body
            lookup[header_url] = hdr
            index.append({
                'accessionNumber': accession, 'cik': cik,
                'source_url': primary_url, 'header_url': header_url,
                'download_sha256': _hash(old), 'header_sha256': _hash(hdr),
            })
            allreports.append({
                'accession': accession, 'manifest_cik_raw': cik,
                'recorded_acceptance_timestamp': stamp,
                'acceptance_date': stamp[:10],
                'header_identity': header_identity(
                    hdr, expected_cik=cik, expected_accession=accession
                ),
                'acceptance_clock': _clock(hdr, stamp, stamp[:10]),
                'primary_source': {
                    'sha256': _hash(old), 'bytes': len(old), 'url': primary_url,
                },
                'header_source': {
                    'sha256': _hash(hdr), 'bytes': len(hdr), 'url': header_url,
                },
                'cover_evidence': cover_evidence(old),
                'known_at': None, 'available_at': None,
                'security_link_created': False,
            })
            rows.append({
                'accession': accession,
                'historical_security_class_approved': False,
                'historical_security_link_known_at': None,
            })
        pairs.append({
            'issuer_CIK': cik,
            'candidate_PERMNO': str(5000 + i),
            'human_approved_historical_class': False,
            'historical_security_identity_known_at': None,
            'filings': rows,
        })
    for i in range(199):
        allreports.append({'accession': f'9999999999-14-{i+1:06d}'})
        index.append({
            'accessionNumber': f'9999999999-14-{i+1:06d}',
            'cik': '9999999999', 'source_url': '',
            'header_url': '', 'download_sha256': '0'*64, 'header_sha256': '0'*64,
        })
    assert len(index) == len(allreports) == 215
    manifest = inputs / 'source_manifest.csv'
    with manifest.open('w', newline='') as file:
        wr = csv.DictWriter(file, fieldnames=list(index[0]))
        wr.writeheader()
        wr.writerows(index)
    monkeypatch.setattr(revisit, 'MANIFEST_HASH', _hash(manifest.read_bytes()))
    previous = {
        'status': revisit.SEC_PRIOR_STATUS,
        'original_sec_bytes_reread': True,
        'xbrl_fact_values_interpreted': False,
        'source_approvals': 0, 'final_period_opened': False,
        'historical_security_links_created': 0,
        'protocol_sha256': canonical_hash(cfg),
        'records': allreports,
    }
    prior_raw = json.dumps(previous).encode()
    gz_blob = gzip.compress(prior_raw, mtime=0)
    earlier = report / 'earlier_source.gz'
    earlier.write_bytes(gz_blob)
    execution = report / 'earlier_execution.json'
    execution.write_text(json.dumps({
        'publication': {
            'sha256': _hash(gz_blob), 'bytes': len(gz_blob),
            'uncompressed_sha256': _hash(prior_raw),
            'uncompressed_bytes': len(prior_raw),
        }
    }))
    p = outputs / 'paired'
    p.mkdir()
    selection = {
        'status': revisit.CLASS_SOURCE_STATUS,
        'issuer_pairs_in_first_review': 8,
        'counts': {'filings_with_standard_member_without_structural_warning': 16},
        'source_fingerprints': {
            'locked_protocol': canonical_hash(cfg),
            'original_sec_gzip': _hash(gz_blob),
        },
        'source_approvals_created': 0, 'model_ready': False,
        'final_period_opened': False,
    }
    items = ''.join(json.dumps(row) + '\n' for row in pairs).encode()
    public_blob = json.dumps(selection).encode()
    (p / 'private_issuer_pairs.jsonl').write_bytes(items)
    (p / 'public_summary.json').write_bytes(public_blob)
    (p / 'receipt.json').write_text(json.dumps({
        'status': revisit.CLASS_SOURCE_STATUS,
        'source_approvals': 0, 'class_approvals': 0,
        'files': {
            'private_issuer_pairs.jsonl': {'sha256': _hash(items)},
            'public_summary.json': {'sha256': _hash(public_blob)},
        },
    }))
    request_log = []

    def fake_curl(url, target, agent, cap, **_):
        assert url in lookup
        assert '@' in agent
        request_log.append(url)
        data = lookup[url]
        target.write_bytes(data)
        return {
            'status': 'HTTP_200_VALID_SIZE', 'http': '200',
            'bytes': len(data), 'curl_returncode': 0,
        }, data

    monkeypatch.setattr(revisit, '_curl', fake_curl)
    monkeypatch.setattr(revisit.time, 'sleep', lambda seconds: None)
    return {
        'repo': repo, 'cfg': cfg,
        'manifest': manifest, 'earlier': earlier, 'execution': execution,
        'paired': p, 'lookup': lookup,
        'request_log': request_log,
        'fetch_output': outputs / 'retrieved',
        'verify_output': outputs / 'verified',
    }


def download(x):
    return revisit.fetch_original_sec_16(
        x['paired'], x['manifest'], x['earlier'], x['execution'],
        x['fetch_output'],
        user_agent='DisclosureDriftResearch (researcher@university.edu)',
        config=x['cfg'], repo_root=x['repo'], delay=1.2,
    )


def verify(x):
    return reparse_16_sec_originals(
        x['fetch_output'], x['earlier'], x['execution'],
        x['verify_output'], config=x['cfg'], repo_root=x['repo'],
    )


def test_source_fetch_mismatch_is_never_relabelled_as_prior_exact(sources):
    report = download(sources)
    assert len(sources['request_log']) == 32
    assert report['original_filings_requested'] == 16
    assert report['retrieved_HTTP_200_source_objects'] == 32
    assert report['retrieved_exact_prior_verified_sha256'] == 16
    assert report['retrieved_different_from_prior_verified_sha256'] == 16
    assert not report['original_source_bytes_all_exactly_match_prior_verified_16_filing_cache']
    assert report['source_verification_pending_if_any_bytes_differ']
    assert not report['historical_issuer_identity_approved']
    assert not report['source_publication_at_filing_established']
    assert not report['model_ready'] and not report['final_period_opened']
    receipt = json.loads((sources['fetch_output'] / 'receipt.json').read_text())
    assert receipt['model_ready'] is False
    assert sources['fetch_output'].stat().st_mode & 0o077 == 0
    assert 'researcher@university.edu' not in json.dumps(report)
    assert 'researcher@university.edu' not in (
        sources['fetch_output'] / 'receipt.json').read_text()


def test_direct_bytes_reparse_preserves_original_selected_source_evidence(sources):
    download(sources)
    report = verify(sources)
    x = report['source_object_counts']
    assert x['primary_retrieved_HTTP_200'] == x['header_retrieved_HTTP_200'] == 16
    assert x['original_primary_full_lexical_report_exact_reproductions'] == 16
    assert x['original_primary_selected_lexical_facts_exact_reproductions'] == 16
    assert x['original_primary_contexts_exact_reproductions'] == 16
    assert x['original_header_identity_exact_reproductions'] == 16
    assert x['original_header_clock_exact_reproductions'] == 16
    assert x['primary_bytes_delta_-4'] == 16
    assert x['header_bytes_delta_+0'] == 16
    assert report['all_current_source_lexical_evidence_matches_earlier_verified_packet']
    assert report['source_sha256_mismatch_is_not_accepted_as_exact_historical_bytes']
    assert not report['historical_link_or_common_stock_class_approved']
    assert not report['final_period_opened']
    receipt = json.loads((sources['verify_output'] / 'receipt.json').read_text())
    assert all(_hash((sources['verify_output'] / n).read_bytes()) == declaration['sha256']
               for n, declaration in receipt['files'].items())


def test_sec_archive_url_rejects_offhost_query_or_wrong_accession():
    accession = '1000000000-20-000001'
    p = 'https://www.sec.gov/Archives/edgar/data/1000000000/100000000020000001/file.htm'
    assert revisit._allowed_sec_url(p, accession, '1000000000')
    for url in (
        p + '?download=1',
        p + '#bad',
        p.replace('https://', 'http://'),
        p.replace('www.sec.gov', 'www.sec.gov.evil.example'),
        p.replace('www.sec.gov/', 'someone@www.sec.gov/'),
        p.replace('100000000020000001', '100000000020000002'),
    ):
        assert not revisit._allowed_sec_url(url, accession, '1000000000')


def test_failed_sec_access_stops_future_requests(sources, monkeypatch):
    first = sources['request_log']

    def deny(url, dst, agent, cap):
        first.append(url)
        return {'status': 'HTTP_STATUS', 'http': '403', 'curl_returncode': 0}, None

    monkeypatch.setattr(revisit, '_curl', deny)
    result = download(sources)
    assert result['SEC_access_error_stop_triggered']
    assert result['retrieved_HTTP_200_source_objects'] == 0
    assert result['retrieved_missing_or_error'] == 32
    assert len(first) == 1
    assert result['new_source_approvals'] == 0


def test_forged_previous_manifest_hash_is_rejected(sources, monkeypatch):
    monkeypatch.setattr(revisit, 'MANIFEST_HASH', '0'*64)
    with pytest.raises(ValueError, match="inventory SHA changed"):
        download(sources)
    assert not sources['fetch_output'].exists()


def test_incorrect_original_report_hash_is_rejected(sources):
    sources['earlier'].write_bytes(sources['earlier'].read_bytes() + b'ATTACK')
    with pytest.raises(ValueError, match="Original SEC previously verified publication"):
        download(sources)


def test_forged_saved_primary_evidence_fails_even_with_valid_fetch_receipt(sources):
    download(sources)
    location = sources['fetch_output'] / 'original_sec_bytes'
    file = sorted(location.glob('*.original.html'))[0]
    file.chmod(0o600)
    file.write_bytes(file.read_bytes() + b'attack')
    with pytest.raises(ValueError, match="Downloaded original SEC bytes"):
        verify(sources)


def test_forged_historical_approval_gates_rejected_when_receipt_rehashed(sources):
    download(sources)
    src = sources['fetch_output'] / 'public_summary.json'
    summary = json.loads(src.read_text())
    summary['historical_issuer_identity_approved'] = True
    modified = (json.dumps(summary) + '\n').encode()
    src.chmod(0o600)
    src.write_bytes(modified)
    receipt_path = sources['fetch_output'] / 'receipt.json'
    receipt_path.chmod(0o600)
    receipt = json.loads(receipt_path.read_text())
    receipt['files']['public_summary.json'] = {
        'sha256': _hash(modified), 'bytes': len(modified),
    }
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="Unapproved SEC original fetch"):
        verify(sources)


def test_output_overwrite_is_rejected(sources):
    download(sources)
    with pytest.raises(ValueError, match="fresh private"):
        download(sources)



def test_sec_contact_research_agent_is_required(sources):
    with pytest.raises(ValueError, match="legitimate SEC academic"):
        revisit.fetch_original_sec_16(
            sources["paired"], sources["manifest"], sources["earlier"],
            sources["execution"], sources["fetch_output"],
            user_agent="FakeClient (not-an-email)",
            config=sources["cfg"], repo_root=sources["repo"], delay=1.3,
        )
    assert not sources["fetch_output"].exists()


def test_fair_access_pacing_is_mandatory(sources):
    with pytest.raises(ValueError, match="more than one file per second"):
        revisit.fetch_original_sec_16(
            sources["paired"], sources["manifest"], sources["earlier"],
            sources["execution"], sources["fetch_output"],
            user_agent="DisclosureDriftAcademic (research@university.edu)",
            config=sources["cfg"], repo_root=sources["repo"], delay=0.1,
        )
    assert not sources["fetch_output"].exists()
