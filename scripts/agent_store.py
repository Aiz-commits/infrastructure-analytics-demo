"""Phase 3: local SQLite store of runs received by email and waiting for the reviewer (git-ignored data/ folder)."""
import hashlib
import json
import secrets
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from .agent import TraceStep
from .ai_writer import Texts
from .controller_checks import Finding, ReadValue, Statement

TOKEN_HOURS = 48
MAX_PIN_ATTEMPTS = 5
SCHEMA = '''CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, file_name TEXT NOT NULL,
    file_sha256 TEXT NOT NULL, sender TEXT NOT NULL, subject TEXT NOT NULL, statement TEXT NOT NULL,
    findings TEXT NOT NULL, trace TEXT NOT NULL, texts TEXT NOT NULL, language TEXT NOT NULL,
    read_method TEXT NOT NULL, needs_confirmation INTEGER NOT NULL, ai_used_agent INTEGER NOT NULL,
    token_hash TEXT NOT NULL, token_expires_at TEXT NOT NULL, decision TEXT, decided_at TEXT,
    pin_attempts INTEGER NOT NULL DEFAULT 0, locked INTEGER NOT NULL DEFAULT 0)'''


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _decimal(value):
    return None if value is None else str(value)


def _undecimal(value):
    return None if value is None else Decimal(value)


def _dump_statement(statement):
    return json.dumps({'project': statement.project, 'number': statement.number, 'values': {
        f: {**asdict(v), 'value': _decimal(v.value)} for f, v in statement.values.items()}})


def _load_statement(text):
    raw = json.loads(text)
    return Statement(raw['project'], raw['number'], {
        f: ReadValue(**{**v, 'value': _undecimal(v['value'])}) for f, v in raw['values'].items()})


def _dump_findings(findings):
    return json.dumps([{**asdict(f), 'amounts': {k: _decimal(v) for k, v in f.amounts.items()},
                        'difference': _decimal(f.difference)} for f in findings])


def _load_findings(text):
    return [Finding(**{**f, 'amounts': {k: _undecimal(v) for k, v in f['amounts'].items()},
                       'difference': _undecimal(f['difference'])}) for f in json.loads(text)]


class RunStore:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.files_dir = self.db_path.parent / 'agent_files'
        self.files_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(SCHEMA)

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create(self, *, file_name, data, sender, subject, statement, findings, trace, texts, language, read_method,
               needs_confirmation, ai_used_agent, now):
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(data).hexdigest()
        (self.files_dir / digest).write_bytes(data)
        row = (now.isoformat(), file_name[:240], digest, sender[:240], (subject or '')[:240],
               _dump_statement(statement), _dump_findings(findings), json.dumps([asdict(s) for s in trace]),
               json.dumps(asdict(texts)), language, read_method, int(needs_confirmation), int(ai_used_agent),
               _token_hash(token), (now + timedelta(hours=TOKEN_HOURS)).isoformat())
        with self._connect() as conn:
            cursor = conn.execute(
                'INSERT INTO agent_runs (created_at, file_name, file_sha256, sender, subject, statement, findings, '
                'trace, texts, language, read_method, needs_confirmation, ai_used_agent, token_hash, '
                'token_expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', row)
            return cursor.lastrowid, token

    def get(self, run_id):
        with self._connect() as conn:
            row = conn.execute('SELECT * FROM agent_runs WHERE id = ?', (run_id,)).fetchone()
        if row is None:
            return None
        run = dict(row)
        run.update(statement=_load_statement(run['statement']), findings=_load_findings(run['findings']),
                   trace=[TraceStep(**s) for s in json.loads(run['trace'])], texts=Texts(**json.loads(run['texts'])),
                   needs_confirmation=bool(run['needs_confirmation']), ai_used_agent=bool(run['ai_used_agent']),
                   locked=bool(run['locked']), created_at=datetime.fromisoformat(run['created_at']),
                   token_expires_at=datetime.fromisoformat(run['token_expires_at']),
                   decided_at=run['decided_at'] and datetime.fromisoformat(run['decided_at']))
        return run

    def file_path(self, run):
        return self.files_dir / run['file_sha256']

    @staticmethod
    def check_token(run, token, now):
        if not token or not secrets.compare_digest(_token_hash(token), run['token_hash']):
            return 'This link is not valid.'
        if now > run['token_expires_at'] and run['decision'] is None:
            return 'This link has expired.'
        return None

    def record_wrong_pin(self, run_id):
        with self._connect() as conn:
            conn.execute('UPDATE agent_runs SET pin_attempts = pin_attempts + 1, '
                         'locked = CASE WHEN pin_attempts + 1 >= ? THEN 1 ELSE locked END WHERE id = ?',
                         (MAX_PIN_ATTEMPTS, run_id))
            return conn.execute('SELECT pin_attempts FROM agent_runs WHERE id = ?', (run_id,)).fetchone()[0]

    def decide(self, run_id, decision, now):
        with self._connect() as conn:
            cursor = conn.execute('UPDATE agent_runs SET decision = ?, decided_at = ? '
                                  'WHERE id = ? AND decision IS NULL AND locked = 0',
                                  (decision, now.isoformat(), run_id))
            return cursor.rowcount == 1
