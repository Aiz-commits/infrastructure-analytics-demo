"""Phase 3 settings (secrets.toml) and the local SQLite store of pending email runs."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import sqlite3
import pytest
from scripts.agent import TraceStep
from scripts.agent_settings import load_settings, sender_address
from scripts.agent_store import MAX_PIN_ATTEMPTS, RunStore
from scripts.ai_writer import Texts
from scripts.controller_checks import FIELDS, SOURCE_FIXED, Finding, ReadValue, Statement

GOOD_SECRETS = '''GEMINI_API_KEY = "g"
DATABASE_URL = "sqlite:///x.db"
REVIEWER_PIN = "123456"
AGENT_API_KEY = "abcdefghijklmnopqrstuvwxyz012345"
ALLOWED_SENDERS = ["Me@Example.com"]
REVIEW_BASE_URL = "http://192.168.1.5:8000/"
'''
NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def write(tmp_path, text):
    path = tmp_path / 'secrets.toml'
    path.write_text(text, encoding='utf-8')
    return path


def test_settings_happy_path(tmp_path):
    settings = load_settings(write(tmp_path, GOOD_SECRETS), data_dir=tmp_path / 'data')
    assert settings.pin == '123456' and settings.allowed_senders == frozenset({'me@example.com'})
    assert settings.review_base_url == 'http://192.168.1.5:8000' and settings.gemini_key == 'g'


@pytest.mark.parametrize('old,new,message', [
    ('AGENT_API_KEY = "abcdefghijklmnopqrstuvwxyz012345"', 'AGENT_API_KEY = "short"', 'AGENT_API_KEY'),
    ('REVIEWER_PIN = "123456"', 'REVIEWER_PIN = "12a456"', 'REVIEWER_PIN'),
    ('REVIEWER_PIN = "123456"', 'REVIEWER_PIN = "12345"', 'REVIEWER_PIN'),
    ('ALLOWED_SENDERS = ["Me@Example.com"]', 'ALLOWED_SENDERS = []', 'ALLOWED_SENDERS'),
    ('REVIEW_BASE_URL = "http://192.168.1.5:8000/"', 'REVIEW_BASE_URL = "ftp://x"', 'REVIEW_BASE_URL'),
])
def test_settings_refuse_bad_values(tmp_path, old, new, message):
    with pytest.raises(ValueError, match=message):
        load_settings(write(tmp_path, GOOD_SECRETS.replace(old, new)), data_dir=tmp_path)


def test_settings_missing_file(tmp_path):
    with pytest.raises(ValueError, match='secrets.toml'):
        load_settings(tmp_path / 'nope.toml', data_dir=tmp_path)


def test_sender_address_parses_display_names():
    assert sender_address('Ilyass <A@Gmail.com>') == 'a@gmail.com'
    assert sender_address('  b@x.org ') == 'b@x.org'
    assert sender_address('') == ''


def sample():
    values = {f: ReadValue(f, Decimal('10.50'), 'D1', SOURCE_FIXED, f == 'vat') for f in FIELDS}
    values['ttc'] = ReadValue('ttc', None, None, SOURCE_FIXED)
    statement = Statement('DEMO PROJECT', 5, values)
    findings = [Finding('vat', 'REVIEW', 'VAT', {'stated': Decimal('1.00'), 'expected': Decimal('2.00')},
                        Decimal('1.00'), 'cells'), Finding('sequence', 'OK', 'Seq', {}, None, 'ok')]
    trace = [TraceStep('AI', 'ran', 'vat', ''), TraceStep('guard', 'added', 'history', 'why')]
    texts = Texts('memo', 'subject', 'body', True)
    return statement, findings, trace, texts


def create(store, **changes):
    statement, findings, trace, texts = sample()
    fields = dict(file_name='D5.xlsx', data=b'PK\x03\x04data', sender='me@example.com', subject='D5',
                  statement=statement, findings=findings, trace=trace, texts=texts, language='fr',
                  read_method='fixed layout', needs_confirmation=False, ai_used_agent=True, now=NOW)
    return store.create(**{**fields, **changes})


def test_round_trip_and_file_saved(tmp_path):
    store = RunStore(tmp_path / 'runs.sqlite')
    run_id, token = create(store)
    run = store.get(run_id)
    statement, findings, trace, texts = sample()
    assert (run['statement'], run['findings'], run['trace'], run['texts']) == (statement, findings, trace, texts)
    assert run['needs_confirmation'] is False and run['decision'] is None and run['ai_used_agent'] is True
    digest = hashlib.sha256(b'PK\x03\x04data').hexdigest()
    assert run['file_sha256'] == digest and (tmp_path / 'agent_files' / digest).read_bytes() == b'PK\x03\x04data'


def test_token_hash_stored_not_raw(tmp_path):
    store = RunStore(tmp_path / 'runs.sqlite')
    run_id, token = create(store)
    raw = sqlite3.connect(tmp_path / 'runs.sqlite').execute('select * from agent_runs').fetchone()
    assert token not in [str(column) for column in raw]
    run = store.get(run_id)
    assert store.check_token(run, token, NOW) is None
    assert store.check_token(run, token + 'x', NOW) == 'This link is not valid.'
    assert store.check_token(run, token, NOW + timedelta(hours=49)) == 'This link has expired.'
    assert store.get(999) is None


def test_decide_once(tmp_path):
    store = RunStore(tmp_path / 'runs.sqlite')
    run_id, _ = create(store)
    assert store.decide(run_id, 'Approved', NOW) is True
    assert store.decide(run_id, 'Rejected', NOW) is False
    assert store.get(run_id)['decision'] == 'Approved'


def test_five_wrong_pins_lock(tmp_path):
    store = RunStore(tmp_path / 'runs.sqlite')
    run_id, _ = create(store)
    assert [store.record_wrong_pin(run_id) for _ in range(MAX_PIN_ATTEMPTS)] == [1, 2, 3, 4, 5]
    assert store.get(run_id)['locked'] is True
    assert store.decide(run_id, 'Approved', NOW) is False


def test_survives_restart(tmp_path):
    run_id, _ = create(RunStore(tmp_path / 'runs.sqlite'))
    assert RunStore(tmp_path / 'runs.sqlite').get(run_id)['file_name'] == 'D5.xlsx'
