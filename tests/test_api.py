"""Phase 3 local API: intake from n8n, PIN-protected review page on the phone."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
import pytest
from fastapi.testclient import TestClient
from api.main import create_app
from scripts.agent import AgentResult, TraceStep
from scripts.agent_settings import Settings
from scripts.ai_writer import Texts
from scripts.controller_checks import FIELDS, SOURCE_FIXED, Finding, ReadValue, Statement
from scripts.intake import IntakeError, IntakeRead

KEY = 'k' * 32
PIN = '123456'
HEADERS = {'X-API-Key': KEY}


def statement():
    return Statement('DEMO PROJECT', 5, {f: ReadValue(f, Decimal('100.00'), 'D1', SOURCE_FIXED) for f in FIELDS})


FINDINGS = [Finding('vat', 'REVIEW', 'VAT 20% of net HT', {'stated': Decimal('1.00'), 'expected': Decimal('2.00')},
                    Decimal('1.00'), 'VAT D45'),
            Finding('missing:ttc', 'WARNING', 'Value not found: total TTC', {}, None, 'not found'),
            Finding('contract_ceiling', 'OK', 'Contract ceiling', {}, None, '80.80 % of contract TTC')]


class Fakes:
    def __init__(self, needs_confirmation=False, read_error=None):
        self.reads, self.saved, self.needs, self.read_error = [], [], needs_confirmation, read_error
        self.clock = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)

    def reader(self, data, key):
        self.reads.append(data)
        if self.read_error:
            raise self.read_error
        return IntakeRead(statement(), 'fixed layout', self.needs)

    def agent(self, stmt, policy, key):
        return AgentResult(FINDINGS, [TraceStep('AI', 'ran', 'vat', ''),
                                      TraceStep('guard', 'added', 'history', 'the AI did not run this core check')],
                           True)

    def writer(self, findings, language, policy, key, project='', number=None):
        return Texts('memo <b>text</b>', 'subject', 'body', True)

    def history(self, settings, run):
        self.saved.append(run['id'])
        return 'Added to the public history.'


@pytest.fixture
def fakes():
    return Fakes()


def make_client(tmp_path, fakes):
    settings = Settings(KEY, PIN, frozenset({'me@example.com'}), 'http://pc:8000', None, None, tmp_path)
    app = create_app(settings, agent=fakes.agent, reader=fakes.reader, writer=fakes.writer,
                     history_saver=fakes.history, now=lambda: fakes.clock)
    return TestClient(app, raise_server_exceptions=False)


def intake(client, sender='me@example.com', headers=HEADERS, data=b'PK\x03\x04file'):
    return client.post('/intake', headers=headers, files={'file': ('D5.xlsx', data)},
                       data={'sender': sender, 'subject': 'Décompte D5'})


def review_link(response):
    url = response.json()['review_url']
    run_id, token = re.match(r'http://pc:8000/review/(\d+)\?t=(.+)$', url).groups()
    return int(run_id), token


def test_health(tmp_path, fakes):
    assert make_client(tmp_path, fakes).get('/health').json() == {'status': 'ok'}


def test_intake_needs_api_key(tmp_path, fakes):
    client = make_client(tmp_path, fakes)
    assert intake(client, headers={}).status_code == 401
    assert intake(client, headers={'X-API-Key': 'wrong'}).status_code == 401
    assert fakes.reads == []


def test_sender_not_allowed_is_403_and_nothing_read(tmp_path, fakes):
    response = intake(make_client(tmp_path, fakes), sender='stranger@spam.com')
    assert response.status_code == 403 and 'error' in response.json() and fakes.reads == []


def test_display_name_sender_accepted(tmp_path, fakes):
    assert intake(make_client(tmp_path, fakes), sender='Me <ME@Example.com>').status_code == 200


def test_reader_error_passed_through(tmp_path):
    fakes = Fakes(read_error=IntakeError('No décompte values found in this file.', 422))
    response = intake(make_client(tmp_path, fakes))
    assert response.status_code == 422 and response.json() == {'error': 'No décompte values found in this file.'}


def test_unexpected_error_is_plain_500(tmp_path):
    fakes = Fakes(read_error=RuntimeError('secret internals /path/to/file.py'))
    response = intake(make_client(tmp_path, fakes))
    assert response.status_code == 500 and 'internals' not in response.text and 'Traceback' not in response.text


def test_too_big_is_413(tmp_path, fakes):
    response = intake(make_client(tmp_path, fakes), data=b'0' * (10 * 1024 * 1024 + 1))
    assert response.status_code == 413 and fakes.reads == []


def test_happy_intake_summary(tmp_path, fakes):
    body = intake(make_client(tmp_path, fakes)).json()
    assert body['project'] == 'DEMO PROJECT' and body['number'] == 5
    assert (body['review_count'], body['warning_count'], body['needs_confirmation']) == (1, 1, False)
    assert body['summary'] == 'DEMO PROJECT D5 : 1 à vérifier, 1 alertes'
    assert body['review_url'].startswith('http://pc:8000/review/')


def test_review_page_shows_timeline_and_never_changes_state(tmp_path, fakes):
    client = make_client(tmp_path, fakes)
    run_id, token = review_link(intake(client))
    for _ in range(2):
        page = client.get(f'/review/{run_id}', params={'t': token})
        assert page.status_code == 200
    assert 'ajouté par le garde-fou' in page.text and 'memo &lt;b&gt;text&lt;/b&gt;' in page.text
    assert 'name="pin"' in page.text and fakes.saved == []


def test_wrong_token(tmp_path, fakes):
    client = make_client(tmp_path, fakes)
    run_id, token = review_link(intake(client))
    assert 'This link is not valid.' in client.get(f'/review/{run_id}', params={'t': 'x'}).text
    assert client.get('/review/999', params={'t': token}).status_code == 404


def decide(client, run_id, token, decision='Approved', pin=PIN, **extra):
    return client.post(f'/review/{run_id}/decision', data={'t': token, 'decision': decision, 'pin': pin, **extra})


def test_spaced_pin_approves_once(tmp_path, fakes):
    client = make_client(tmp_path, fakes)
    run_id, token = review_link(intake(client))
    first = decide(client, run_id, token, pin=' 123 456 ')
    assert 'Approuvé' in first.text and fakes.saved == [run_id]
    second = decide(client, run_id, token, decision='Rejected')
    assert 'déjà' in second.text and fakes.saved == [run_id]
    assert 'name="pin"' not in client.get(f'/review/{run_id}', params={'t': token}).text


def test_five_wrong_pins_lock(tmp_path, fakes):
    client = make_client(tmp_path, fakes)
    run_id, token = review_link(intake(client))
    for attempt in range(1, 6):
        assert f'({attempt} / 5)' in decide(client, run_id, token, pin='000000').text
    assert 'Verrouillé' in decide(client, run_id, token).text and fakes.saved == []


def test_ai_read_values_need_confirmation(tmp_path):
    fakes = Fakes(needs_confirmation=True)
    client = make_client(tmp_path, fakes)
    run_id, token = review_link(intake(client))
    assert 'Cochez' in decide(client, run_id, token).text and fakes.saved == []
    assert 'Rejeté' in decide(client, run_id, token, decision='Rejected').text


def test_ai_read_values_confirmed_approves(tmp_path):
    fakes = Fakes(needs_confirmation=True)
    client = make_client(tmp_path, fakes)
    run_id, token = review_link(intake(client))
    assert 'Approuvé' in decide(client, run_id, token, confirmed_values='on').text


def test_expired_link(tmp_path, fakes):
    client = make_client(tmp_path, fakes)
    run_id, token = review_link(intake(client))
    fakes.clock += timedelta(hours=49)
    assert 'This link has expired.' in client.get(f'/review/{run_id}', params={'t': token}).text
    assert 'This link has expired.' in decide(client, run_id, token).text and fakes.saved == []


def test_decision_survives_restart(tmp_path, fakes):
    client = make_client(tmp_path, fakes)
    run_id, token = review_link(intake(client))
    decide(client, run_id, token)
    page = make_client(tmp_path, fakes).get(f'/review/{run_id}', params={'t': token})
    assert 'Approuvé' in page.text and 'name="pin"' not in page.text


def test_runs_endpoint_needs_key(tmp_path, fakes):
    client = make_client(tmp_path, fakes)
    run_id, _ = review_link(intake(client))
    assert client.get(f'/runs/{run_id}').status_code == 401
    body = client.get(f'/runs/{run_id}', headers=HEADERS).json()
    assert body['decision'] is None and 'token_hash' not in body and body['findings'][0]['id'] == 'vat'


def test_original_file_download_needs_token(tmp_path, fakes):
    client = make_client(tmp_path, fakes)
    run_id, token = review_link(intake(client))
    assert client.get(f'/review/{run_id}/file', params={'t': 'x'}).status_code == 403
    assert client.get(f'/review/{run_id}/file', params={'t': token}).content == b'PK\x03\x04file'


def test_save_public_only_bundled_and_strips_optional(tmp_path, fakes):
    from sqlalchemy import select
    from api.main import save_public
    from scripts.controller_checks import EXAMPLES_DIR
    from scripts.history import findings_table, get_engine, runs
    url = f'sqlite:///{(tmp_path / "public.sqlite").as_posix()}'
    settings = Settings(KEY, PIN, frozenset({'me@example.com'}), 'http://pc:8000', None, url, tmp_path)
    client = TestClient(create_app(settings, agent=fakes.agent, reader=fakes.reader, writer=fakes.writer,
                                   history_saver=lambda s, r: 'skip', now=lambda: fakes.clock))
    own_id, own_token = review_link(intake(client))
    bundled_id, token = review_link(intake(client, data=(EXAMPLES_DIR / 'DEMO_DP_N5.xlsx').read_bytes()))
    for run_id, run_token in ((own_id, own_token), (bundled_id, token)):
        decide(client, run_id, run_token)
    from scripts.agent_store import RunStore
    store = RunStore(tmp_path / 'agent_runs.sqlite')
    assert save_public(settings, store.get(own_id)) == 'Kept on this PC (not a bundled example).'
    assert save_public(settings, store.get(bundled_id)) == 'Added to the public history.'
    with get_engine(url).connect() as conn:
        row = conn.execute(select(runs.c.read_method, runs.c.decision)).one()
        ids = [r[0] for r in conn.execute(select(findings_table.c.check_id))]
    assert tuple(row) == ('fixed layout via email', 'Approved') and 'contract_ceiling' not in ids and 'vat' in ids
    broken = Settings(KEY, PIN, frozenset({'x@y.z'}), 'http://pc', None, 'postgresql://u:p@127.0.0.1:1/db', tmp_path)
    assert save_public(broken, store.get(bundled_id)) == 'Public history not updated (database unavailable).'


def test_intake_runs_in_worker_thread_not_event_loop(tmp_path, fakes):
    import inspect
    app = make_client(tmp_path, fakes).app
    route = next(r for r in app.routes if getattr(r, 'path', '') == '/intake')
    assert not inspect.iscoroutinefunction(route.endpoint)  # Slow Gemini calls must not freeze the review page.


def test_original_file_opens_on_phone(tmp_path, fakes):
    client = make_client(tmp_path, fakes)
    run_id, token = review_link(intake(client))
    response = client.get(f'/review/{run_id}/file', params={'t': token})
    assert response.headers['content-type'].startswith('application/vnd.openxmlformats-officedocument.spreadsheetml')
    assert response.headers['content-disposition'] == 'inline; filename="decompte.xlsx"'
    assert response.headers['cache-control'] == 'no-store'
