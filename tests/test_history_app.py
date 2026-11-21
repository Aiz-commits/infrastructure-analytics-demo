import hashlib
import json
from unittest.mock import patch
import pytest
import streamlit as st
from sqlalchemy import create_engine, text
from streamlit.testing.v1 import AppTest
from scripts.controller_checks import EXAMPLES_DIR
from scripts.policy import ROOT
from tests.test_app import upload
from tests.test_controller_app import CELLS, all_text

PAGE = '🤖 AI Controller'
N5 = EXAMPLES_DIR / 'DEMO_DP_N5.xlsx'
TAG = hashlib.sha256(N5.read_bytes()).hexdigest()[:12] + '_fr'


@pytest.fixture(autouse=True)
def clear_caches():
    st.cache_data.clear()
    st.cache_resource.clear()


@pytest.fixture
def db_url(tmp_path):
    return f'sqlite:///{tmp_path / "history.sqlite"}'


def rows(url, table='controller_runs'):
    with create_engine(url).connect() as conn:
        try:
            return conn.execute(text(f'SELECT * FROM {table}')).mappings().all()
        except Exception:
            return []


def uploader_for(single):
    return lambda *a, **k: single if k.get('key') == 'ctrl_upload' else None


def open_page(db_url, single=None, gemini=None):
    with patch('streamlit.file_uploader', side_effect=uploader_for(single)):
        app = AppTest.from_file(str(ROOT / 'app.py'))
        if db_url:
            app.secrets['DATABASE_URL'] = db_url
        if gemini:
            app.secrets['GEMINI_API_KEY'] = gemini
        app.run(timeout=30)
        app.sidebar.radio[0].set_value(PAGE).run(timeout=30)
    return app


def click(app, key, single=None):
    with patch('streamlit.file_uploader', side_effect=uploader_for(single)):
        return app.button(key=key).click().run(timeout=30)


def test_approve_example_saves_one_row(db_url):
    app = click(click(open_page(db_url), 'ctrl_example'), 'ctrl_approve')
    assert not app.exception
    assert 'Added to the public history' in all_text(app)
    app.run(timeout=30)
    app.run(timeout=30)
    saved = rows(db_url)
    assert len(saved) == 1
    assert saved[0]['decision'] == 'Approved' and saved[0]['file_name'] == 'DEMO_DP_N5.xlsx'
    assert saved[0]['read_method'] == 'fixed layout' and saved[0]['edited'] in (0, False)
    assert len(rows(db_url, 'controller_values')) == 7


def test_reject_then_approve_saves_first_only(db_url):
    app = click(click(click(open_page(db_url), 'ctrl_example'), 'ctrl_reject'), 'ctrl_approve')
    assert not app.exception
    assert [r['decision'] for r in rows(db_url)] == ['Rejected']


def test_upload_never_saved(db_url):
    single = upload('DEMO_DP_N5.xlsx', N5.read_bytes())
    app = click(open_page(db_url, single=single), 'ctrl_approve', single=single)
    assert not app.exception
    assert 'Uploads are never saved to the public history' in all_text(app)
    assert rows(db_url) == []


def test_edited_values_not_saved(db_url):
    from scripts.controller_checks import parse_edits as real_parse

    def edit_works(raw):
        edits, bad = real_parse(raw)
        edits['works'] = edits['works'] + 1
        return edits, bad

    def fake_generate(prompt, api_key, config, client_factory):
        return json.dumps(CELLS) if 'locate values' in prompt else None
    with patch('scripts.llm._generate', side_effect=fake_generate), \
            patch('scripts.controller_checks.parse_edits', side_effect=edit_works):
        app = click(open_page(db_url, gemini='test-key'), 'ctrl_example_new')
        app = click(app, 'ctrl_confirm')
        app = click(app, 'ctrl_approve')
    assert not app.exception
    assert 'Edited values are not added to the public history' in all_text(app)
    assert rows(db_url) == []


def test_unedited_ai_read_example_is_saved(db_url):
    def fake_generate(prompt, api_key, config, client_factory):
        return json.dumps(CELLS) if 'locate values' in prompt else None
    with patch('scripts.llm._generate', side_effect=fake_generate):
        app = click(open_page(db_url, gemini='test-key'), 'ctrl_example_new')
        app = click(app, 'ctrl_confirm')
        app = click(app, 'ctrl_approve')
    assert not app.exception
    saved = rows(db_url)
    assert len(saved) == 1
    assert saved[0]['read_method'] == 'found by AI'
    assert saved[0]['file_name'] == 'DEMO_DP_N5_NEW_LAYOUT.xlsx'


def test_db_failure_keeps_page_working():
    bad = 'postgresql://user:secret@127.0.0.1:1/none'
    app = click(click(open_page(bad), 'ctrl_example'), 'ctrl_approve')
    assert not app.exception
    text_on_page = all_text(app)
    assert 'click again' in text_on_page
    assert 'Approved by reviewer' in text_on_page
    assert 'secret' not in text_on_page and 'postgresql://' not in text_on_page


def test_edited_memo_stores_app_text(db_url):
    app = click(open_page(db_url), 'ctrl_example')
    original = app.text_area(key=f'ctrl_memo_{TAG}').value
    app.text_area(key=f'ctrl_memo_{TAG}').input('Texte libre du visiteur').run(timeout=30)
    app = click(app, 'ctrl_approve')
    saved = rows(db_url)
    assert len(saved) == 1
    assert saved[0]['memo'] == original
    assert saved[0]['edited'] in (1, True)
    assert 'Texte libre du visiteur' not in str(saved[0])


def test_history_shows_saved_run(db_url):
    app = click(click(open_page(db_url), 'ctrl_example'), 'ctrl_approve')
    assert any('Public history' in h.value for h in app.subheader)
    assert any(m.label == 'Runs saved' and str(m.value) == '1' for m in app.metric)
    assert 'DEMO_DP_N5.xlsx' in ''.join(d.value.to_string() for d in app.dataframe)


def test_history_unavailable_notice():
    app = open_page('postgresql://user:secret@127.0.0.1:1/none')
    assert not app.exception
    assert any('temporarily unavailable' in i.value for i in app.info)


def test_unreachable_db_is_not_retried_on_every_rerun():
    from scripts import history as store
    calls = []
    real = store.get_engine

    def counting(url):
        calls.append(url)
        return real(url)
    import ui.history_section  # noqa: F401  (bind the module before patching its imported name)
    with patch('ui.history_section.get_engine', side_effect=counting):
        app = open_page('postgresql://user:secret@127.0.0.1:1/none')
        first = len(calls)
        app.run(timeout=30)
        app.run(timeout=30)
    assert first >= 1
    assert len(calls) == first
    assert any('temporarily unavailable' in i.value for i in app.info)


def test_history_not_configured():
    app = open_page(None)
    assert not app.exception
    assert 'Public history not configured' in all_text(app)
