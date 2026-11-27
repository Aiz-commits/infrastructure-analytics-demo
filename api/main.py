"""Phase 3 local API. n8n posts emailed décomptes to /intake; the reviewer approves on the phone with a PIN.
Run: .venv\\Scripts\\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000 (see automation/start_api.ps1)."""
import hmac
from datetime import datetime, timezone
from fastapi import FastAPI, File, Form, Header, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from scripts.agent import run_agent
from scripts.agent_settings import load_settings, sender_address
from scripts.agent_store import MAX_PIN_ATTEMPTS, RunStore
from scripts.ai_writer import write_texts
from scripts.controller_checks import OPTIONAL_CHECKS
from scripts.history import RunRecord, ensure_schema, get_engine, save_run
from scripts.intake import IntakeError, bundled_hashes, read_file
from scripts.policy import load_policy
from .review_page import message_page, render_review

MAX_BODY_BYTES = 10 * 1024 * 1024
LANGUAGE = 'fr'
MESSAGES = {
    'fr': {'already': 'Ce décompte a déjà été traité.', 'wrong_pin': 'Code PIN incorrect ({n} / {max}).',
           'locked': 'Verrouillé — trop de codes PIN incorrects. Renvoyez l’e-mail pour une nouvelle vérification.',
           'confirm': 'Cochez « J’ai comparé ces valeurs avec le document joint » avant d’approuver.',
           'bad_decision': 'Choisissez Approuver ou Rejeter.'},
    'en': {'already': 'This décompte was already decided.', 'wrong_pin': 'Wrong PIN ({n} / {max}).',
           'locked': 'Locked — too many wrong PINs. Email the décompte again for a new review.',
           'confirm': 'Tick "I compared these values with the attached document" before approving.',
           'bad_decision': 'Choose Approve or Reject.'},
}
SUMMARY = {'fr': '{project} D{number} : {review} à vérifier, {warnings} alertes',
           'en': '{project} D{number}: {review} to review, {warnings} warnings'}


def save_public(settings, run):
    """Public Neon history: bundled examples only, optional findings removed (same rows as a Streamlit approval)."""
    if run['file_sha256'] not in bundled_hashes():
        return 'Kept on this PC (not a bundled example).'
    if not settings.database_url:
        return 'Kept on this PC (no public history database configured).'
    texts, statement = run['texts'], run['statement']
    findings = [f for f in run['findings'] if f.id not in OPTIONAL_CHECKS]
    record = RunRecord(run['decided_at'], run['decision'], run['file_name'], run['file_sha256'],
                       statement.project or '', statement.number, f'{run["read_method"]} via email', run['language'],
                       texts.ai_used, False, load_policy().version, texts.memo, texts.email_subject, texts.email_body,
                       run['created_at'])
    try:
        engine = get_engine(settings.database_url)
        ensure_schema(engine)
        saved = save_run(engine, record, statement, findings)
    except Exception:  # Database asleep, down or misconfigured: the decision itself stands.
        return 'Public history not updated (database unavailable).'
    return 'Added to the public history.' if saved else 'Not added to the public history (duplicate or daily limit).'


def _error(status, message):
    return JSONResponse({'error': message}, status_code=status)


def _key_ok(settings, given):
    return bool(given) and hmac.compare_digest(given.encode(), settings.api_key.encode())


def _run_json(run):
    s = run['statement']
    text = lambda v: None if v is None else str(v)
    return {'id': run['id'], 'created_at': run['created_at'].isoformat(), 'file_name': run['file_name'],
            'sender': run['sender'], 'project': s.project, 'number': s.number, 'read_method': run['read_method'],
            'needs_confirmation': run['needs_confirmation'], 'decision': run['decision'],
            'decided_at': run['decided_at'] and run['decided_at'].isoformat(), 'locked': run['locked'],
            'values': {f: text(v.value) for f, v in s.values.items()},
            'findings': [{'id': f.id, 'severity': f.severity, 'title': f.title, 'difference': text(f.difference)}
                         for f in run['findings']],
            'trace': [{'who': t.who, 'action': t.action, 'check_id': t.check_id, 'reason': t.reason}
                      for t in run['trace']]}


def create_app(settings, *, agent=run_agent, reader=read_file, writer=write_texts, history_saver=save_public,
               policy=None, now=None):
    policy = policy or load_policy()
    now = now or (lambda: datetime.now(timezone.utc))
    store = RunStore(settings.data_dir / 'agent_runs.sqlite')
    app = FastAPI(title='AI Controller API', docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(Exception)
    async def unexpected(request, error):
        return _error(500, 'Something went wrong on the server. Nothing was approved.')

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.post('/intake')
    async def intake(request: Request, file: UploadFile = File(...), sender: str = Form(''), subject: str = Form(''),
                     x_api_key: str = Header('')):
        if not _key_ok(settings, x_api_key):
            return _error(401, 'Missing or wrong X-API-Key.')
        if int(request.headers.get('content-length') or 0) > MAX_BODY_BYTES + 64 * 1024:
            return _error(413, 'This email attachment is larger than 10 MB.')
        address = sender_address(sender)
        if address not in settings.allowed_senders:
            return _error(403, 'This sender is not on the allowed list. Nothing was processed.')
        data = await file.read(MAX_BODY_BYTES + 1)
        if len(data) > MAX_BODY_BYTES:
            return _error(413, 'This email attachment is larger than 10 MB.')
        try:
            read = reader(data, settings.gemini_key)
        except IntakeError as error:
            return _error(error.status, str(error))
        statement = read.statement
        result = agent(statement, policy, settings.gemini_key)
        texts = writer(result.findings, LANGUAGE, policy, settings.gemini_key, project=statement.project,
                       number=statement.number)
        run_id, token = store.create(
            file_name=file.filename or 'attachment', data=data, sender=address, subject=subject, statement=statement,
            findings=result.findings, trace=result.trace, texts=texts, language=LANGUAGE,
            read_method=read.read_method, needs_confirmation=read.needs_confirmation, ai_used_agent=result.ai_used,
            now=now())
        review = sum(f.severity == 'REVIEW' for f in result.findings)
        warnings = sum(f.severity == 'WARNING' for f in result.findings)
        number = statement.number if statement.number is not None else '?'
        return {'run_id': run_id, 'project': statement.project, 'number': statement.number, 'review_count': review,
                'warning_count': warnings, 'needs_confirmation': read.needs_confirmation,
                'summary': SUMMARY[LANGUAGE].format(project=statement.project or '?', number=number, review=review,
                                                    warnings=warnings),
                'review_url': f'{settings.review_base_url}/review/{run_id}?t={token}'}

    @app.get('/runs/{run_id}')
    def run_details(run_id: int, x_api_key: str = Header('')):
        if not _key_ok(settings, x_api_key):
            return _error(401, 'Missing or wrong X-API-Key.')
        run = store.get(run_id)
        return _run_json(run) if run else _error(404, 'This run does not exist.')

    def _checked_run(run_id, token):
        run = store.get(run_id)
        if run is None:
            return None, HTMLResponse(message_page('This review does not exist.'), status_code=404)
        problem = store.check_token(run, token, now())
        if problem:
            return None, HTMLResponse(message_page(problem), status_code=403)
        return run, None

    @app.get('/review/{run_id}', response_class=HTMLResponse)
    def review(run_id: int, t: str = ''):
        run, refused = _checked_run(run_id, t)
        if refused:
            return refused
        locked = MESSAGES[run['language']]['locked'] if run['locked'] and not run['decision'] else None
        return HTMLResponse(render_review(run, token=t, message=locked))

    @app.get('/review/{run_id}/file')
    def original_file(run_id: int, t: str = ''):
        run, refused = _checked_run(run_id, t)
        if refused:
            return refused
        return Response(store.file_path(run).read_bytes(), media_type='application/octet-stream',
                        headers={'Content-Disposition': 'attachment; filename="decompte"'})

    @app.post('/review/{run_id}/decision', response_class=HTMLResponse)
    def decision(run_id: int, t: str = Form(''), decision: str = Form(''), pin: str = Form(''),
                 confirmed_values: str = Form('')):
        run, refused = _checked_run(run_id, t)
        if refused:
            return refused
        text = MESSAGES[run['language']]
        show = lambda message, ok=False: HTMLResponse(render_review(store.get(run_id), token=t, message=message, ok=ok))
        if run['decision']:
            return show(text['already'])
        if run['locked']:
            return show(text['locked'])
        if decision not in ('Approved', 'Rejected'):
            return show(text['bad_decision'])
        if not hmac.compare_digest(''.join(pin.split()).encode(), settings.pin.encode()):
            attempts = store.record_wrong_pin(run_id)
            message = text['wrong_pin'].format(n=attempts, max=MAX_PIN_ATTEMPTS)
            return show(message + (' ' + text['locked'] if attempts >= MAX_PIN_ATTEMPTS else ''))
        if decision == 'Approved' and run['needs_confirmation'] and confirmed_values != 'on':
            return show(text['confirm'])
        if not store.decide(run_id, decision, now()):
            return show(text['already'])
        try:
            note = history_saver(settings, store.get(run_id))
        except Exception:
            note = 'Public history not updated (database unavailable).'
        return show(note, ok=True)

    return app


def __getattr__(name):
    """`uvicorn api.main:app` builds the app from secrets.toml; importing create_app in tests needs no secrets."""
    if name == 'app':
        return create_app(load_settings())
    raise AttributeError(name)
