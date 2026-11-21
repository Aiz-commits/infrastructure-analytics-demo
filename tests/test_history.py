from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from sqlalchemy import text
from scripts import history
from scripts.controller_checks import EXAMPLES_DIR, from_extractor, previous_from_history, run_checks
from scripts.decompte_extractor import extract_decompte
from scripts.history import (RunRecord, ensure_schema, get_engine, latest_runs, normalize_url, save_run, totals)
from scripts.policy import load_policy

T0 = datetime(2026, 11, 22, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def engine(tmp_path):
    engine = get_engine(f'sqlite:///{tmp_path / "h.sqlite"}')
    ensure_schema(engine)
    return engine


@pytest.fixture(scope='module')
def n5():
    statement = from_extractor(extract_decompte(EXAMPLES_DIR / 'DEMO_DP_N5.xlsx'))
    return statement, run_checks(statement, previous_from_history(statement), load_policy())


def record(when=T0, decision='Approved', memo='Note', language='fr', sha='a' * 64):
    return RunRecord(when, decision, 'DEMO_DP_N5.xlsx', sha, 'DEMO PROJECT', 5, 'fixed layout', language,
                     True, False, 'demo-finance-v1', memo, 'Sujet', 'Corps')


def test_normalize_url():
    neon = 'postgresql://u:p@h/db?sslmode=require&channel_binding=require'
    assert normalize_url(neon) == 'postgresql+psycopg://u:p@h/db?sslmode=require&channel_binding=require'
    assert normalize_url('postgres://u:p@h/db') == 'postgresql+psycopg://u:p@h/db'
    assert normalize_url('sqlite:///x.db') == 'sqlite:///x.db'
    with pytest.raises(ValueError):
        normalize_url('mysql://u:p@h/db')
    snippet = "psql 'postgresql://u:p@h/db?sslmode=require&channel_binding=require'"
    assert normalize_url(snippet) == 'postgresql+psycopg://u:p@h/db?sslmode=require&channel_binding=require'


def test_format_utc_converts_other_timezones():
    from datetime import timezone as tz
    casablanca = timezone(timedelta(hours=1))
    assert history.format_utc(datetime(2026, 11, 22, 10, 30, tzinfo=casablanca)) == '2026-11-22 09:30'
    assert history.format_utc(datetime(2026, 11, 22, 9, 30)) == '2026-11-22 09:30'  # naive = already UTC
    assert history.format_utc(datetime(2026, 11, 22, 9, 30, tzinfo=tz.utc)) == '2026-11-22 09:30'


def test_postgres_engine_works_with_neon_pooler():
    """Neon's pooled endpoint rejects startup 'options'; the timeout is set per transaction instead."""
    from sqlalchemy import event
    pg = get_engine('postgresql://u:p@host.neon.tech/db?sslmode=require')
    assert 'options' not in pg.dialect.create_connect_args(pg.url)[1]
    assert event.contains(pg, 'begin', history._statement_timeout)


def test_schema_idempotent(engine):
    ensure_schema(engine)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM v_controller_decisions')).scalar() == 0


def test_save_and_read_back(engine, n5):
    statement, findings = n5
    run_id = save_run(engine, record(), statement, findings)
    assert isinstance(run_id, int)
    with engine.connect() as conn:
        values = conn.execute(text('SELECT field, value, cell FROM controller_values WHERE run_id = :r'),
                              {'r': run_id}).all()
        continuity = conn.execute(text("SELECT severity, difference, stated, expected FROM controller_findings "
                                       "WHERE run_id = :r AND check_id = 'continuity'"), {'r': run_id}).one()
        view = conn.execute(text('SELECT review_count, warning_count FROM v_controller_decisions')).one()
    assert len(values) == 7
    assert ('vat', Decimal('163000.00'), 'D45') in [(f, Decimal(str(v)), c) for f, v, c in values]
    assert continuity[0] == 'REVIEW' and Decimal(str(continuity[1])) == Decimal('12300.00')
    assert Decimal(str(continuity[3])) == Decimal('2750000.00')
    assert tuple(view) == (2, 0)
    assert totals(engine) == {'runs': 1, 'approved': 1, 'rejected': 0, 'problems': 2}


def test_dedupe_within_10_minutes(engine, n5):
    statement, findings = n5
    assert isinstance(save_run(engine, record(), statement, findings), int)
    assert save_run(engine, record(T0 + timedelta(minutes=5)), statement, findings) is None
    assert isinstance(save_run(engine, record(T0 + timedelta(minutes=5), decision='Rejected'), statement, findings), int)
    assert isinstance(save_run(engine, record(T0 + timedelta(minutes=5), language='en'), statement, findings), int)
    assert isinstance(save_run(engine, record(T0 + timedelta(minutes=11)), statement, findings), int)


def test_daily_cap(engine, n5, monkeypatch):
    statement, findings = n5
    monkeypatch.setattr(history, 'DAILY_CAP', 2)
    assert save_run(engine, record(sha='1' * 64), statement, findings)
    assert save_run(engine, record(sha='2' * 64), statement, findings)
    assert save_run(engine, record(sha='3' * 64), statement, findings) is None
    assert save_run(engine, record(T0 + timedelta(days=1), sha='3' * 64), statement, findings)


def test_text_capped(engine, n5):
    statement, findings = n5
    run_id = save_run(engine, record(memo='x' * 6000), statement, findings)
    with engine.connect() as conn:
        memo = conn.execute(text('SELECT memo FROM controller_runs WHERE id = :r'), {'r': run_id}).scalar()
    assert len(memo) == 5000


def test_latest_runs_newest_first_and_limited(engine, n5):
    statement, findings = n5
    for minutes in (0, 20, 40):
        save_run(engine, record(T0 + timedelta(minutes=minutes)), statement, findings)
    rows = latest_runs(engine, limit=2)
    assert len(rows) == 2
    assert rows[0]['decided_at'] > rows[1]['decided_at']
    assert set(rows[0]) == {'decided_at', 'file_name', 'decision', 'ai_used_text', 'review_count'}
    assert rows[0]['review_count'] == 2
