import json
from unittest.mock import patch
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest
from scripts.policy import ROOT
from tests.test_app import upload

PAGE = '🤖 AI Controller'
CELLS = {'works': 'H10', 'previous': 'H11', 'cumulative': 'H12', 'retention': 'H13',
         'net': 'H14', 'vat': 'H15', 'ttc': 'H16', 'project': 'B3', 'number': 'B4'}


@pytest.fixture(autouse=True)
def clear_cache():
    st.cache_data.clear()


def open_page(single=None, secret=None):
    def uploader(*args, **kwargs):
        return single if kwargs.get('key') == 'ctrl_upload' else None
    with patch('streamlit.file_uploader', side_effect=uploader):
        app = AppTest.from_file(str(ROOT / 'app.py'))
        if secret:
            app.secrets['GEMINI_API_KEY'] = secret
        app.run(timeout=30)
        app.sidebar.radio[0].set_value(PAGE).run(timeout=30)
    return app


def click(app, key, single=None):
    def uploader(*args, **kwargs):
        return single if kwargs.get('key') == 'ctrl_upload' else None
    with patch('streamlit.file_uploader', side_effect=uploader):
        return app.button(key=key).click().run(timeout=30)


def all_text(app):
    parts = []
    for kind in ('markdown', 'info', 'warning', 'error', 'success', 'caption', 'header', 'subheader'):
        parts += [str(element.value) for element in getattr(app, kind)]
    parts += [element.value.to_string() for element in app.dataframe]
    return '\n'.join(parts)


def test_try_example_template_mode():
    app = click(open_page(), 'ctrl_example')
    assert not app.exception
    text = all_text(app)
    assert 'AI offline — template mode' in text
    assert text.count('REVIEW') >= 2
    assert '12,300.00' in text or '12 300,00' in text
    assert any('demande de justification' in area.value or 'request for justification' in area.value
               for area in app.text_input) or app.text_area


def test_new_layout_without_ai_explains_why():
    app = click(open_page(), 'ctrl_example_new')
    assert not app.exception
    assert 'AI is offline' in all_text(app)


def test_approve_adds_trail_row():
    app = click(click(open_page(), 'ctrl_example'), 'ctrl_approve')
    assert not app.exception
    assert 'Approved' in all_text(app)
    assert 'Approved by reviewer' in all_text(app)


def test_fake_ai_reader_needs_confirm():
    def fake_generate(prompt, api_key, config, client_factory):
        return json.dumps(CELLS) if 'locate values' in prompt else None
    with patch('scripts.llm._generate', side_effect=fake_generate):
        app = click(open_page(secret='test-key'), 'ctrl_example_new')
        assert not app.exception
        assert app.button(key='ctrl_confirm') is not None
        assert 'REVIEW' not in all_text(app)
        assert 'found by AI' in all_text(app)
        app = click(app, 'ctrl_confirm')
    assert not app.exception
    assert all_text(app).count('REVIEW') >= 2


def test_failed_ai_text_is_not_retried_on_every_rerun():
    calls = []

    def invented_numbers(prompt, api_key, config, client_factory):
        calls.append(prompt)
        return '### MEMO\nGap 99,999.00 DH.\n### EMAIL\nSubject: x\nBody 99,999.00 DH.'
    with patch('scripts.llm._generate', side_effect=invented_numbers):
        app = click(open_page(secret='test-key'), 'ctrl_example')
        after_click = len(calls)
        for _ in range(3):
            app.run(timeout=30)
    assert after_click == 2  # one try + one retry, then template
    assert len(calls) == after_click
    assert not app.exception


def test_upload_too_big_is_rejected():
    app = open_page(single=upload('DP_N5.xlsx', b'0' * (2 * 1024 * 1024 + 1)))
    assert not app.exception
    assert any('2 MB' in message.value for message in app.error)


def test_unexpected_error_shows_message():
    with patch('scripts.controller_checks.run_checks', side_effect=RuntimeError('boom')):
        app = click(open_page(), 'ctrl_example')
    assert not app.exception
    assert any('Cannot analyze this workbook' in message.value for message in app.error)
    assert 'boom' not in all_text(app)
