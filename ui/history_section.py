"""Streamlit side of the public history: save reviewed example runs, show totals and the latest decisions."""
import time
import pandas as pd
import streamlit as st
from scripts.history import RunRecord, ensure_schema, format_utc, get_engine, latest_runs, save_run, totals

SESSION_SAVE_LIMIT = 5
RETRY_AFTER_SECONDS = 60
BUSY = 'Not saved to the public history (database busy) — click again in a minute.'


def _database_down():
    return time.monotonic() < st.session_state.get('ctrl_history_down_until', 0)


def _mark_down():
    """After a failure, skip the database for a minute so each rerun does not wait on a timeout."""
    st.session_state['ctrl_history_down_until'] = time.monotonic() + RETRY_AFTER_SECONDS


def database_url():
    try:
        return st.secrets.get('DATABASE_URL') or None
    except Exception:  # No secrets file: history not configured.
        return None


@st.cache_resource(show_spinner=False)
def history_engine(_url):
    """One engine per app process. Failures raise and are not cached, so a later rerun retries."""
    engine = get_engine(_url)
    ensure_schema(engine)
    return engine


@st.cache_data(ttl=60, show_spinner=False)
def public_history(_url):
    engine = history_engine(_url)
    return totals(engine), latest_runs(engine)


def mark_values_edited(digest):
    st.session_state.setdefault('ctrl_values_edited', set()).add(digest)


def save_decision(*, source, statement, findings, app_texts, final_texts, decision, decided_at, language,
                  read_method, rule_version):
    """Called once per Approve/Reject click. Shows one caption; never raises."""
    if not source['example']:
        st.caption('Uploads are never saved to the public history.')
        return
    if source['digest'] in st.session_state.setdefault('ctrl_values_edited', set()):
        st.caption('Edited values are not added to the public history.')
        return
    url = database_url()
    if not url:
        return
    saved = st.session_state.setdefault('ctrl_saved', set())
    key = (source['digest'], language)
    if key in saved:
        st.caption('Not added to the public history: this file and language were already saved in this session.')
        return
    if len(saved) >= SESSION_SAVE_LIMIT:
        st.caption('Not added to the public history (session limit).')
        return
    edited = (final_texts.memo, final_texts.email_subject, final_texts.email_body) != \
             (app_texts.memo, app_texts.email_subject, app_texts.email_body)
    record = RunRecord(decided_at, decision, source['name'], source['digest'], statement.project or '',
                       statement.number, read_method, language, app_texts.ai_used, edited, rule_version,
                       app_texts.memo, app_texts.email_subject, app_texts.email_body)
    if _database_down():
        st.caption(BUSY)
        return
    try:
        run_id = save_run(history_engine(url), record, statement, findings)
    except Exception:  # Database asleep, down or misconfigured: the decision itself still stands.
        _mark_down()
        st.caption(BUSY)
        return
    saved.add(key)
    if run_id is None:
        st.caption('Not added to the public history (duplicate or daily limit).')
        return
    public_history.clear()
    st.caption('Added to the public history.')


def render_public_history():
    st.subheader('📚 Public history (synthetic examples only)')
    url = database_url()
    if not url:
        st.caption('Public history not configured.')
        return
    if _database_down():
        st.info('Public history is temporarily unavailable.')
        return
    try:
        counts, latest = public_history(url)
    except Exception:
        _mark_down()
        st.info('Public history is temporarily unavailable.')
        return
    a, b, c, d = st.columns(4)
    a.metric('Runs saved', counts['runs'])
    b.metric('Approved', counts['approved'])
    c.metric('Rejected', counts['rejected'])
    d.metric('Problems flagged', counts['problems'])
    if latest:
        st.dataframe(pd.DataFrame([{
            'Date/time (UTC)': format_utc(row['decided_at']), 'File': row['file_name'],
            'Decision': row['decision'], 'AI text': 'yes' if row['ai_used_text'] else 'no',
            'Problems': row['review_count']} for row in latest]), hide_index=True, width='stretch')
    st.caption('Only Approve/Reject decisions on the bundled synthetic examples are saved. '
               'Uploads and visitor-typed text are never stored.')
