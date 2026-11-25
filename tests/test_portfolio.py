import json
from datetime import datetime
from decimal import Decimal
import pytest
from sqlalchemy import text
from scripts import portfolio
from scripts.history import get_engine
from scripts.policy import ROOT

POWERBI = ROOT / 'powerbi'


@pytest.fixture(scope='module')
def generated():
    return portfolio.generate()


@pytest.fixture
def engine(tmp_path):
    return get_engine(f'sqlite:///{tmp_path / "p.sqlite"}')


def test_deterministic(generated):
    assert portfolio.generate() == generated


def test_planted_problems_are_found_by_the_real_checks(generated):
    _, statements, findings = generated
    by_key = {(s['project'], s['statement_number']): s for s in statements}
    for (project, number), kind in portfolio.PLANTED.items():
        if kind == 'missing statement':
            assert (project, number) not in by_key
            after = by_key[(project, number + 1)]
            assert any(f['check_id'] == 'sequence' and f['severity'] == 'REVIEW'
                       for f in findings if f['statement_id'] == after['statement_id'])
        else:
            assert by_key[(project, number)]['review_count'] >= 1, (project, number, kind)
    clean = [s for s in statements if s['planted_problem'] is None]
    assert sum(s['review_count'] == 0 for s in clean) >= len(clean) - 3  # Only knock-on continuity findings.


def test_decisions_follow_findings(generated):
    _, statements, _ = generated
    for s in statements:
        if (s['project'], s['statement_number']) in portfolio.PENDING:
            assert s['decision'] == 'Pending' and s['decided_at'] is None and s['days_to_decision'] is None
        else:
            assert s['submitted_at'] < s['opened_at'] < s['decided_at']
            if s['review_count']:
                assert s['decision'] == 'Rejected'


def test_amounts_are_consistent(generated):
    projects, statements, _ = generated
    for p in projects:
        rows = [s for s in statements if s['project'] == p['project']]
        assert rows[-1]['cumulative_ttc_billed'] == sum(s['ttc'] for s in rows)
        assert rows[-1]['cumulative_ttc_billed'] < p['contract_ttc']
    assert all(isinstance(s[f], Decimal) for s in statements for f in portfolio.FIELDS)


def _norm(value):
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return Decimal(str(value)).quantize(Decimal('0.01'))
    text_value = str(value)
    try:
        return Decimal(text_value).quantize(Decimal('0.01'))
    except ArithmeticError:
        return text_value[:19]


def test_sql_views_match_python_rows_and_contract(engine, generated):
    portfolio.load(engine)
    expected = portfolio.view_rows(generated)
    with engine.connect() as conn:
        for view, columns in portfolio.VIEW_COLUMNS.items():
            result = conn.execute(text(f'SELECT * FROM {view}'))
            assert tuple(result.keys()) == columns, view
            key = columns[0]
            got = sorted((dict(r._mapping) for r in result), key=lambda r: (str(r[key]), r.get('check_id', '')))
            want = sorted(expected[view], key=lambda r: (str(r[key]), r.get('check_id', '')))
            assert len(got) == len(want)
            for g, w in zip(got, want):
                assert {c: _norm(g[c]) for c in columns} == {c: _norm(w[c]) for c in columns}, view


def test_load_replaces_rows(engine):
    first = portfolio.load(engine)
    assert portfolio.load(engine) == first
    with engine.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM portfolio_statements')).scalar() == first[0]


def test_check_group_python_matches_sql(engine):
    portfolio.load(engine)
    with engine.connect() as conn:
        pairs = conn.execute(text('SELECT DISTINCT check_id, check_group FROM v_portfolio_findings')).all()
    assert pairs and all(portfolio.check_group(i) == g for i, g in pairs)
    assert portfolio.check_group('missing:vat') == 'missing value'
    assert portfolio.check_group('uncertain:ttc') == 'uncertain label'


def test_committed_power_bi_files_are_current(tmp_path, generated):
    portfolio.export_csv(tmp_path, generated)
    for view in portfolio.VIEW_COLUMNS:
        assert (tmp_path / f'{view}.csv').read_text(encoding='utf-8') == \
            (POWERBI / 'data' / f'{view}.csv').read_text(encoding='utf-8'), \
            'Run: python -m scripts.portfolio --csv powerbi/data --expected powerbi/expected_totals.json'
    assert json.loads((POWERBI / 'expected_totals.json').read_text(encoding='utf-8')) == \
        json.loads(json.dumps(portfolio.expected_totals(generated)))


def test_expected_totals_are_reconciled(generated):
    totals = portfolio.expected_totals(generated)
    assert sum(Decimal(p['billed_ttc']) for p in totals['projects'].values()) == \
        Decimal(totals['portfolio']['billed_ttc'])
    assert sum(c['review_findings'] for c in totals['contractors'].values()) == totals['portfolio']['review_findings']
    assert totals['label'] == portfolio.LABEL


def test_cli_requires_an_action():
    with pytest.raises(SystemExit):
        portfolio.main([])
