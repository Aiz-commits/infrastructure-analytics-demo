from io import BytesIO
import pytest
import streamlit as st
from openpyxl import Workbook
from streamlit import config


@pytest.fixture(autouse=True)
def no_real_gemini(monkeypatch, tmp_path):
    """Tests never read a local .streamlit/secrets.toml and never reach the real Gemini API."""
    original = config.get_option('secrets.files')
    config.set_option('secrets.files', [str(tmp_path / 'no-secrets.toml')])
    st.secrets._reset()

    def blocked(api_key):
        raise AssertionError('Real Gemini client built during tests; patch scripts.llm._generate instead.')
    monkeypatch.setattr('scripts.llm._client', blocked)
    yield
    config.set_option('secrets.files', original)
    st.secrets._reset()


@pytest.fixture
def make_workbook():
    def make(number=1, previous=0, cumulative=100, works=100, retention=10,
             net=90, vat=18, ttc=108, layout=1, project='DEMO PROJECT',
             cover=False, title='DP', metadata=True, formula=False):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = title
        if metadata:
            sheet['A1'] = f'{project} — DECOMPTE D{number}'
        row = 37 if layout == 1 else 39
        sheet[f'A{row+2}'] = 'Retenue de Garantie'
        for address, value in {f'B{row}': cumulative, f'C{row}': previous, f'D{row}': works,
                               f'D{row+2}': retention, f'D{row+7}': net,
                               f'D{row+8}': vat, f'D{row+9}': ttc}.items():
            sheet[address] = value
        if formula:
            sheet[f'D{row+9}'] = f'=D{row+7}+D{row+8}'
        if cover:
            workbook.create_sheet('Cover', 0)
        buffer = BytesIO()
        workbook.save(buffer)
        workbook.close()
        return buffer.getvalue()
    return make
