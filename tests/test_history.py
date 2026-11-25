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


def test_opened_at_and_minutes_to_decision(engine, n5):
    statement, findings = n5
    run = record()
    from dataclasses import replace
    save_run(engine, replace(run, opened_at=T0 - timedelta(minutes=30)), statement, findings)
    save_run(engine, record(T0 + timedelta(hours=1), language='en'), statement, findings)  # older row: no opened_at
    with engine.connect() as conn:
        minutes = conn.execute(text('SELECT language, minutes_to_decision FROM v_controller_decisions '
                                    'ORDER BY language')).all()
    assert minutes[0][0] == 'en' and minutes[0][1] is None
    assert minutes[1][1] == pytest.approx(30, abs=0.01)


def test_findings_view_groups_checks(engine, n5):
    statement, findings = n5
    save_run(engine, record(), statement, findings)
    with engine.connect() as conn:
        groups = dict(conn.execute(text('SELECT check_id, check_group FROM v_controller_findings')).all())
    assert groups['continuity'] == 'continuity' and groups['vat'] == 'arithmetic'


def test_power_bi_view_contract(engine):
    expected = {
        'v_controller_decisions': ('id', 'decided_at', 'decision', 'file_name', 'project', 'statement_number',
                                   'read_method', 'language', 'ai_used_text', 'edited', 'rule_version',
                                   'review_count', 'warning_count', 'opened_at', 'minutes_to_decision'),
        'v_controller_findings': ('run_id', 'decided_at', 'decision', 'file_name', 'language', 'check_id',
                                  'check_group', 'severity', 'title', 'stated', 'expected', 'difference'),
    }
    with engine.connect() as conn:
        for view, columns in expected.items():
            assert tuple(conn.execute(text(f'SELECT * FROM {view}')).keys()) == columns


def test_old_database_gets_opened_at(tmp_path):
    """A Phase 1.5 database (no opened_at, old view) is upgraded in place by ensure_schema."""
    from sqlalchemy import create_engine
    url = f'sqlite:///{tmp_path / "old.sqlite"}'
    old = create_engine(url)
    with old.begin() as conn:
        conn.execute(text('CREATE TABLE controller_runs (id INTEGER PRIMARY KEY, decided_at TIMESTAMP NOT NULL, '
                          'decision VARCHAR(16) NOT NULL, file_name VARCHAR(240) NOT NULL, file_sha256 VARCHAR(64) '
                          'NOT NULL, project VARCHAR(120) NOT NULL, statement_number INTEGER, read_method VARCHAR(32) '
                          'NOT NULL, language VARCHAR(2) NOT NULL, ai_used_text BOOLEAN NOT NULL, edited BOOLEAN NOT '
                          'NULL, review_count INTEGER NOT NULL, warning_count INTEGER NOT NULL, rule_version '
                          'VARCHAR(40) NOT NULL, memo TEXT NOT NULL, email_subject TEXT NOT NULL, email_body TEXT '
                          'NOT NULL)'))
        conn.execute(text('CREATE VIEW v_controller_decisions AS SELECT id, decision FROM controller_runs'))
    engine = get_engine(url)
    ensure_schema(engine)
    ensure_schema(engine)
    with engine.connect() as conn:
        assert 'minutes_to_decision' in conn.execute(text('SELECT * FROM v_controller_decisions')).keys()
