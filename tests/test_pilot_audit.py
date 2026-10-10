"""Real-source-shaped fixtures test evidence binding and independent arithmetic."""

import json
from math import log, sqrt

import pandas as pd
import pytest

import test_identity_review

from disclosure_research import pilot_audit as pa
from disclosure_research.cli import main
from disclosure_research.controls import control_sessions
from disclosure_research.crsp_staging import stage_crsp
from disclosure_research.export_plan import build_export_plan
from disclosure_research.identity_review import build_identity_review
from disclosure_research.labels import load_development_events

identity_inputs = test_identity_review.inputs


@pytest.fixture
def market_inputs(identity_inputs, tmp_path):
    source = identity_inputs
    build_identity_review(**source)
    _, _, windows = load_development_events(source['events_path'], source['config'])
    window = windows[0]
    history = control_sessions(window)
    dates = [*history, window.reference_session, *window.return_sessions]
    returns = ['0.02'] * 40 + ['0.01', '-0.01'] * 10 + ['0.75'] + ['0.003'] * 20
    rows = [{'PERMNO': '12345', 'PERMCO': '99', 'HdrCUSIP': '12345678', 'Ticker': 'SAME',
             'DlyCalDt': date, 'DlyDelFlg': 'N', 'DlyCap': '1000000', 'DlyRet': ret,
             'DlyRetMissFlg': 'NA', 'vwretd': '0.001'} for date, ret in zip(dates, returns, strict=True)]
    daily = tmp_path / 'daily.csv'
    pd.DataFrame(rows).to_csv(daily, index=False)
    stage = tmp_path / 'staging'
    stage_crsp(daily, source['names_path'], stage, source['config'], dates[0], dates[-1])
    plan = tmp_path / 'plan'
    build_export_plan(source['events_path'], plan, source['config'])
    return {'events_path': source['events_path'], 'filings_path': source['filings_path'],
            'audit_path': source['audit_path'], 'identity_path': source['output'],
            'staging_path': stage, 'daily_path': daily, 'names_path': source['names_path'],
            'plan_path': plan, 'output': tmp_path / 'market-audit', 'config': source['config']}


def test_calculations_match_known_arithmetic_without_approving_identity(market_inputs):
    summary = pa.audit_pilot_market(**market_inputs)
    assert summary['qa_cases_calculated'] == summary['trace_cases_generated'] == 1
    assert summary['qa_cases_blocked'] == 0
    assert summary['human_trace_reviews_passed'] == 0
    assert summary['candidate_cases_with_unresolved_open_end'] == 1
    assert not any(summary[k] for k in ['model_ready', 'milestone_05_complete',
                                      'historical_cik_mapping_approved', 'final_period_opened'])
    output = market_inputs['output']
    row = pd.read_parquet(output / 'candidate_calculations.parquet').iloc[0]
    assert row.stock_return == pytest.approx(1.003 ** 20 - 1)
    assert row.target == pytest.approx(1.003 ** 20 - 1.001 ** 20)
    assert row.momentum_20 == pytest.approx(.9999 ** 10 - 1)
    assert row.momentum_60 == pytest.approx(1.02 ** 40 * .9999 ** 10 - 1)
    assert row.volatility_20 == pytest.approx(sqrt(.002 / 19))
    assert row.log_market_cap == pytest.approx(log(1e9))
    assert row.industry == '1234' and not row.identity_approved
    trace = json.loads((output / 'independent_traces.jsonl').read_text())
    assert len(trace['controls']) == 60 and len(trace['label_rows']) == 20
    assert trace['label_rows'][0]['source_record'] == 63
    assert trace['snapshot']['source_record'] == 61
    assert 'current_text' not in row.index and 'observation_id' not in row.index
    assert not (output / 'security_links.parquet').exists()
    assert 'Provisional security candidates' in (output / 'review.html').read_text()


@pytest.mark.parametrize('which', ['raw', 'stage', 'identity', 'plan'])
def test_changed_evidence_is_rejected_before_publishing(market_inputs, which):
    paths = {'raw': market_inputs['daily_path'],
             'stage': market_inputs['staging_path'] / 'security_snapshots.parquet',
             'identity': market_inputs['identity_path'] / 'candidate_links.parquet',
             'plan': market_inputs['plan_path'] / 'trace_reviews.template.csv'}
    with paths[which].open('ab') as file:
        file.write(b'changed')
    with pytest.raises(ValueError, match='changed'):
        pa.audit_pilot_market(**market_inputs)
    assert not market_inputs['output'].exists()


def test_holdout_event_rejected_before_missing_market_paths(market_inputs):
    path = market_inputs['events_path']
    events = pd.read_parquet(path)
    events['acceptance_timestamp'] = '2022-02-03T18:00:00-05:00'
    events.to_parquet(path, index=False)
    market_inputs['staging_path'] = path.parent / 'does-not-exist'
    with pytest.raises(ValueError, match='holdout'):
        pa.audit_pilot_market(**market_inputs)


def test_multiple_candidate_rows_are_not_arbitrarily_selected(market_inputs, identity_inputs):
    path = identity_inputs['ccm_paths'][0]
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    pd.concat([frame, frame.iloc[[0]].assign(LPERMNO='54321', LIID='02')]).to_csv(path, index=False)
    identity_inputs['output'] = path.parent / 'ambiguous-identity'
    build_identity_review(**identity_inputs)
    market_inputs['identity_path'] = identity_inputs['output']
    summary = pa.audit_pilot_market(**market_inputs)
    assert summary['qa_cases_blocked'] == 1 and summary['qa_cases_calculated'] == 0
    assert summary['trace_cases_generated'] == 0
    assert 'Need exactly one candidate row' in next(iter(summary['qa_issue_counts']))


def test_independent_calculation_detects_wrong_pipeline_units(market_inputs, monkeypatch):
    original = pa.make_controls
    def incorrect(*args):
        result = original(*args)
        result['log_market_cap'] += log(1000)
        return result
    monkeypatch.setattr(pa, 'make_controls', incorrect)
    summary = pa.audit_pilot_market(**market_inputs)
    assert summary['qa_cases_blocked'] == 1
    assert summary['qa_issue_counts'] == {'Independent source arithmetic disagrees with pipeline': 1}


def test_existing_outputs_are_preserved(market_inputs):
    market_inputs['output'].mkdir()
    sentinel = market_inputs['output'] / 'keep'
    sentinel.write_text('unchanged')
    with pytest.raises(ValueError, match='already exists'):
        pa.audit_pilot_market(**market_inputs)
    assert sentinel.read_text() == 'unchanged'


def test_review_declarations_are_bound_and_assistant_is_not_human(market_inputs):
    pa.audit_pilot_market(**market_inputs)
    record = json.loads((market_inputs['output'] / 'trace_reviews.template.jsonl').read_text())
    record.update(controls_verdict='pass', label_verdict='pass', reviewer='Example assistant',
                  reviewer_type='assistant', reviewed_at='2026-10-10T12:00:00-04:00',
                  notes='Checked rows and independent arithmetic.', source_references=['daily.csv records 2-82'])
    path = market_inputs['output'].parent / 'reviews.jsonl'
    path.write_text(json.dumps(record) + '\n')
    market_inputs.update(output=market_inputs['output'].parent / 'reviewed', reviews_path=path)
    summary = pa.audit_pilot_market(**market_inputs)
    assert summary['human_trace_reviews_passed'] == 0
    record['evidence_id'] = 'f' * 64
    path.write_text(json.dumps(record) + '\n')
    market_inputs['output'] = path.parent / 'stale'
    with pytest.raises(ValueError, match='Stale'):
        pa.audit_pilot_market(**market_inputs)


def test_cli_publishes_qa_packet(market_inputs, capsys):
    args = ['audit-pilot-market']
    for field in ['events', 'filings', 'audit', 'identity', 'staging', 'daily', 'names', 'plan']:
        args.extend(['--' + field, str(market_inputs[field + '_path'])])
    args.extend(['--output', str(market_inputs['output'])])
    assert main(args) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary['qa_cases_calculated'] == 1 and not summary['milestone_05_complete']
