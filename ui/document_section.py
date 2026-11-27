"""Streamlit side of PDF/photo reading: upload checks, live AI reads, the session AI limit, saved-answer fallback."""
import streamlit as st
from scripts.ai_reader import MAX_UPLOAD_BYTES
from scripts.controller_checks import load_saved_answer
from scripts.documents import check_limits, detect_kind
from scripts.intake import read_document_with_ai
from scripts.pdf_reader import trace_pdf
from scripts.vision_reader import parse_vision_answer

AI_CALL_LIMIT = 10
SAVED_BADGE = 'Saved example answer (AI offline)'
NO_TICK_DOC = 'PDF and photo reading uses Gemini. Tick the privacy box above to allow it.'
OFFLINE_DOC = 'AI is offline (template mode). PDF and photo reading needs AI; upload an .xlsx instead.'
UNAVAILABLE = 'AI reading is unavailable right now (quota or network). Try again in a new session.'


class NotCached(Exception):
    """Raised inside cached functions so a failed AI result is never cached."""


def ai_call_allowed(cache_key):
    """Max AI_CALL_LIMIT distinct AI requests per browser session. A repeat of a successful request is a
    cache hit (no call). Callers skip requests listed in ctrl_ai_failed, so failures never retry on reruns."""
    seen = st.session_state.setdefault('ctrl_ai_seen', set())
    if cache_key in seen:
        return True
    if st.session_state.get('ctrl_ai_calls', 0) >= AI_CALL_LIMIT:
        return False
    seen.add(cache_key)
    st.session_state['ctrl_ai_calls'] = st.session_state.get('ctrl_ai_calls', 0) + 1
    return True


@st.cache_data(show_spinner=False, max_entries=100)
def cached_document_read(digest, kind, _data, _key):
    """Live PDF/photo read. A PDF without usable text (a scan) goes to vision. Returns (statement, read_method)."""
    statement, method = read_document_with_ai(_data, kind, _key)
    if statement is None:
        raise NotCached()
    return statement, method


def upload_problem(data):
    """Plain message for an upload that is the wrong type or over a limit, else None."""
    try:
        kind = detect_kind(data)
    except ValueError as error:
        too_big = len(data) > MAX_UPLOAD_BYTES
        return 'This file is larger than 2 MB. The AI Controller accepts files up to 2 MB.' if too_big else str(error)
    try:
        check_limits(kind, data)
    except ValueError as error:
        return str(error)
    return None


def live_document_read(source, kind, key):
    cache_key = (source['digest'], 'read')
    failed = st.session_state.setdefault('ctrl_ai_failed', set())
    if cache_key in failed:
        return None, None, UNAVAILABLE
    if not ai_call_allowed(cache_key):
        return None, None, f'AI limit reached for this session ({AI_CALL_LIMIT} calls). Use an .xlsx décompte.'
    try:
        with st.spinner('Gemini is reading the document…'):
            statement, method = cached_document_read(source['digest'], kind, source['data'], key)
    except NotCached:
        failed.add(cache_key)
        return None, None, UNAVAILABLE
    return statement, method, None


def saved_document_read(source, kind):
    answer = load_saved_answer(source['name'])
    if answer is None:
        return None
    if kind == 'pdf':
        return trace_pdf(source['data'], answer), 'PDF text (saved)'
    return parse_vision_answer(answer, 'image'), 'AI vision (saved)'


def read_document(source, kind, key, allow_ai):
    """PDF or photo: live AI when allowed; bundled examples fall back to their saved answer."""
    if not allow_ai:
        return None, NO_TICK_DOC, None
    if not key and not source['example']:
        return None, OFFLINE_DOC, None
    problem = None
    if key:
        statement, method, problem = live_document_read(source, kind, key)
        if statement is not None:
            return statement, None, method
    saved = saved_document_read(source, kind) if source['example'] else None
    if saved is None:
        return None, problem or UNAVAILABLE, None
    st.info(SAVED_BADGE)
    return saved[0], None, saved[1]
