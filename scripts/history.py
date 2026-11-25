"""Public history store for the AI Controller. Pure Python + SQLAlchemy Core; works on Postgres and SQLite."""
from dataclasses import astuple, dataclass, fields
from datetime import datetime, timedelta, timezone
from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Identity, Integer, MetaData, Numeric, String, Table,
                        Text, and_, create_engine, event, func, insert, inspect, select, text)

MAX_TEXT = 5000
DAILY_CAP = 200
DEDUPE_MINUTES = 10

metadata = MetaData()
runs = Table(
    'controller_runs', metadata,
    Column('id', Integer, Identity(), primary_key=True),
    Column('decided_at', DateTime(timezone=True), nullable=False, index=True),
    Column('decision', String(16), nullable=False),
    Column('file_name', String(240), nullable=False),
    Column('file_sha256', String(64), nullable=False),
    Column('project', String(120), nullable=False),
    Column('statement_number', Integer),
    Column('read_method', String(32), nullable=False),
    Column('language', String(2), nullable=False),
    Column('ai_used_text', Boolean, nullable=False),
    Column('edited', Boolean, nullable=False),
    Column('review_count', Integer, nullable=False),
    Column('warning_count', Integer, nullable=False),
    Column('rule_version', String(40), nullable=False),
    Column('memo', Text, nullable=False),
    Column('email_subject', Text, nullable=False),
    Column('email_body', Text, nullable=False),
    Column('opened_at', DateTime(timezone=True)),  # Phase 2.5: checks first shown; NULL on older rows.
)
values_table = Table(
    'controller_values', metadata,
    Column('run_id', Integer, ForeignKey('controller_runs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('field', String(16), nullable=False),
    Column('value', Numeric(14, 2)),
    Column('cell', String(16)),
    Column('source', String(32), nullable=False),
    Column('uncertain', Boolean, nullable=False),
)
findings_table = Table(
    'controller_findings', metadata,
    Column('run_id', Integer, ForeignKey('controller_runs.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('check_id', String(32), nullable=False),
    Column('severity', String(8), nullable=False),
    Column('title', Text, nullable=False),
    Column('stated', Numeric(14, 2)),
    Column('expected', Numeric(14, 2)),
    Column('difference', Numeric(14, 2)),
    Column('evidence', Text, nullable=False),
)
# Shared by the live and portfolio findings views, so Power BI groups both the same way.
CHECK_GROUP_SQL = ("CASE WHEN {col} LIKE 'missing:%' THEN 'missing value' "
                   "WHEN {col} LIKE 'uncertain:%' THEN 'uncertain label' "
                   "WHEN {col} IN ('continuity', 'sequence') THEN {col} ELSE 'arithmetic' END")
MINUTES_SQL = {'postgresql': 'EXTRACT(EPOCH FROM (decided_at - opened_at)) / 60.0',
               'sqlite': '(julianday(decided_at) - julianday(opened_at)) * 1440.0'}
# Power BI view contract: new columns are only ever appended (Postgres CREATE OR REPLACE VIEW rule).
VIEWS = {
    'v_controller_decisions': (
        'SELECT id, decided_at, decision, file_name, project, statement_number, read_method, language, '
        'ai_used_text, edited, rule_version, review_count, warning_count, opened_at, '
        'CASE WHEN opened_at IS NULL OR opened_at > decided_at THEN NULL ELSE {minutes} END AS minutes_to_decision '
        'FROM controller_runs'),
    'v_controller_findings': (
        'SELECT f.run_id, r.decided_at, r.decision, r.file_name, r.language, f.check_id, '
        + CHECK_GROUP_SQL.format(col='f.check_id') + ' AS check_group, '
        'f.severity, f.title, f.stated, f.expected, f.difference '
        'FROM controller_findings f JOIN controller_runs r ON r.id = f.run_id'),
}


def create_views(conn, views, **values):
    """CREATE OR REPLACE on Postgres keeps Power BI grants; SQLite has no OR REPLACE, so drop and recreate."""
    postgres = conn.dialect.name == 'postgresql'
    for name, body in views.items():
        if not postgres:
            conn.execute(text(f'DROP VIEW IF EXISTS {name}'))
        verb = 'CREATE OR REPLACE VIEW' if postgres else 'CREATE VIEW'
        conn.execute(text(f'{verb} {name} AS {body.format(**values)}'))


@dataclass(frozen=True)
class RunRecord:
    decided_at: datetime
    decision: str
    file_name: str
    file_sha256: str
    project: str
    statement_number: int | None
    read_method: str
    language: str
    ai_used_text: bool
    edited: bool
    rule_version: str
    memo: str
    email_subject: str
    email_body: str
    opened_at: datetime | None = None


def format_utc(moment):
    """Display a stored timestamp in UTC whatever the database session time zone is."""
    return f'{_utc(moment):%Y-%m-%d %H:%M}'


def normalize_url(url):
    url = (url or '').strip()
    if url.startswith('psql '):  # Neon's dialog also offers a "psql '...'" snippet.
        url = url[5:].strip()
    url = url.strip('\'"')
    for prefix in ('postgresql://', 'postgres://'):
        if url.startswith(prefix):
            return 'postgresql+psycopg://' + url[len(prefix):]
    if url.startswith(('postgresql+psycopg://', 'sqlite:///')):
        return url
    raise ValueError('DATABASE_URL must be a postgresql:// or sqlite:/// URL.')


def _statement_timeout(conn):
    """5 s limit per transaction. SET LOCAL works through Neon's pooled (PgBouncer) endpoint,
    which rejects the startup 'options' parameter."""
    conn.exec_driver_sql('SET LOCAL statement_timeout = 5000')


def get_engine(url):
    url = normalize_url(url)
    if url.startswith('postgresql'):
        engine = create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=2,
                               connect_args={'connect_timeout': 5})
        event.listen(engine, 'begin', _statement_timeout)
        return engine
    return create_engine(url)


def ensure_schema(engine):
    metadata.create_all(engine)
    with engine.begin() as conn:
        if engine.dialect.name == 'postgresql':
            conn.execute(text('ALTER TABLE controller_runs ADD COLUMN IF NOT EXISTS opened_at TIMESTAMP WITH TIME ZONE'))
        elif 'opened_at' not in {c['name'] for c in inspect(conn).get_columns('controller_runs')}:
            conn.execute(text('ALTER TABLE controller_runs ADD COLUMN opened_at TIMESTAMP'))
        create_views(conn, VIEWS, minutes=MINUTES_SQL[engine.dialect.name])


def _utc(moment):
    return moment.astimezone(timezone.utc) if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _cap(value):
    return (value or '')[:MAX_TEXT]


def save_run(engine, record, statement, findings):
    """Save one reviewed run. Returns the new id, or None when skipped by the dedupe window or the daily cap."""
    when = _utc(record.decided_at)
    day = when.replace(hour=0, minute=0, second=0, microsecond=0)
    with engine.begin() as conn:
        today = conn.execute(select(func.count()).select_from(runs).where(
            and_(runs.c.decided_at >= day, runs.c.decided_at < day + timedelta(days=1)))).scalar()
        if today >= DAILY_CAP:
            return None
        duplicate = conn.execute(select(func.count()).select_from(runs).where(and_(
            runs.c.file_sha256 == record.file_sha256, runs.c.language == record.language,
            runs.c.decision == record.decision,
            runs.c.decided_at > when - timedelta(minutes=DEDUPE_MINUTES),
            runs.c.decided_at <= when))).scalar()
        if duplicate:
            return None
        row = dict(zip((f.name for f in fields(record)), astuple(record)))
        row.update(decided_at=when, opened_at=record.opened_at and _utc(record.opened_at), memo=_cap(record.memo), email_subject=_cap(record.email_subject),
                   email_body=_cap(record.email_body), project=record.project[:120],
                   review_count=sum(f.severity == 'REVIEW' for f in findings),
                   warning_count=sum(f.severity == 'WARNING' for f in findings))
        run_id = conn.execute(insert(runs).values(**row)).inserted_primary_key[0]
        conn.execute(insert(values_table), [
            {'run_id': run_id, 'field': v.field, 'value': v.value, 'cell': v.cell, 'source': v.source,
             'uncertain': v.uncertain} for v in statement.values.values()])
        conn.execute(insert(findings_table), [
            {'run_id': run_id, 'check_id': f.id, 'severity': f.severity, 'title': _cap(f.title),
             'stated': f.amounts.get('stated'), 'expected': f.amounts.get('expected'), 'difference': f.difference,
             'evidence': _cap(f.evidence)} for f in findings])
    return int(run_id)


def latest_runs(engine, limit=20):
    query = (select(runs.c.decided_at, runs.c.file_name, runs.c.decision, runs.c.ai_used_text, runs.c.review_count)
             .order_by(runs.c.decided_at.desc(), runs.c.id.desc()).limit(limit))
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(query)]


def totals(engine):
    query = select(func.count(), func.coalesce(func.sum(runs.c.review_count), 0),
                   func.count().filter(runs.c.decision == 'Approved'),
                   func.count().filter(runs.c.decision == 'Rejected'))
    with engine.connect() as conn:
        count, problems, approved, rejected = conn.execute(query).one()
    return {'runs': int(count), 'approved': int(approved), 'rejected': int(rejected), 'problems': int(problems)}
