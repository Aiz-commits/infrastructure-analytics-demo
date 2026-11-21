from decimal import Decimal
from io import BytesIO
import pytest
from openpyxl import Workbook
from scripts.ai_reader import MAX_AI_CELLS, cell_text, read_with_ai, trace
from scripts.controller_checks import EXAMPLES_DIR, FIELDS, SOURCE_AI, ReadValue

GOOD_CELLS = {'works': 'H10', 'previous': 'H11', 'cumulative': 'H12', 'retention': 'H13',
              'net': 'H14', 'vat': 'H15', 'ttc': 'H16', 'project': 'B3', 'number': 'B4'}


@pytest.fixture
def new_layout_bytes():
    return (EXAMPLES_DIR / 'DEMO_DP_N5_NEW_LAYOUT.xlsx').read_bytes()


def workbook_bytes_from(cells):
    workbook = Workbook()
    sheet = workbook.active
    for address, value in cells.items():
        sheet[address] = value
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_new_layout_traced(new_layout_bytes):
    statement = read_with_ai(new_layout_bytes, 'k', ask=lambda *a, **k: GOOD_CELLS)
    assert statement.values['vat'] == ReadValue('vat', Decimal('163000.00'), 'H15', SOURCE_AI, False)
    assert statement.values['previous'].value == Decimal('2737700.00')
    assert not any(statement.values[f].uncertain for f in FIELDS)
    assert (statement.project, statement.number) == ('DEMO PROJECT', 5)


def test_cell_text_lists_non_empty_cells(new_layout_bytes):
    text = cell_text(new_layout_bytes)
    assert 'F15: TVA 20%' in text
    assert 'H15: 163000' in text


def test_junk_addresses_are_not_found(new_layout_bytes):
    junk = {'works': 'Sheet2!A1', 'previous': 'Z99999', 'cumulative': 'hello', 'retention': None,
            'net': 'Q1', 'vat': 'F15', 'ttc': 42}
    statement = trace(new_layout_bytes, junk)
    assert all(statement.values[f].value is None for f in FIELDS)


def test_text_amount_is_not_found():
    data = workbook_bytes_from({'A1': 'Travaux du mois HT', 'B1': '900 000,00', 'A2': 'TVA', 'B2': '1000'})
    statement = trace(data, {'works': 'B1', 'vat': 'B2'})
    assert statement.values['works'].value is None
    assert statement.values['vat'].value is None


def test_wrong_label_is_uncertain(new_layout_bytes):
    statement = trace(new_layout_bytes, {**GOOD_CELLS, 'vat': 'H13'})
    assert statement.values['vat'] == ReadValue('vat', Decimal('90000.00'), 'H13', SOURCE_AI, True)


def test_cumul_precedent_not_accepted_for_cumulative(new_layout_bytes):
    assert trace(new_layout_bytes, {'cumulative': 'H11'}).values['cumulative'].uncertain is True


def test_column_header_label_counts():
    data = workbook_bytes_from({'C1': 'TVA', 'C5': 18})
    assert trace(data, {'vat': 'C5'}).values['vat'].uncertain is False


def test_identity_from_ai_cells_when_heading_missing():
    data = workbook_bytes_from({'A1': 'Projet', 'B1': 'SITE NORD', 'A2': 'N°', 'B2': 7})
    statement = trace(data, {'project': 'B1', 'number': 'B2'})
    assert (statement.project, statement.number) == ('SITE NORD', 7)
    assert trace(data, {'number': 'A1'}).number is None


def test_ai_down_returns_none(new_layout_bytes):
    assert read_with_ai(new_layout_bytes, 'k', ask=lambda *a, **k: None) is None


def test_prompt_contains_cells_and_no_math_instruction(new_layout_bytes):
    seen = {}
    read_with_ai(new_layout_bytes, 'k', ask=lambda prompt, schema, key: seen.update(prompt=prompt) or GOOD_CELLS)
    assert 'H15: 163000' in seen['prompt'] and 'do not compute' in seen['prompt'].lower()


@pytest.mark.parametrize('cells', [{}, {'A1': 'Projet', 'B2': 'texte seulement'}])
def test_sheet_without_numbers_raises_before_any_ai_call(cells):
    calls = []
    with pytest.raises(ValueError, match='does not look like a décompte'):
        read_with_ai(workbook_bytes_from(cells), 'k', ask=lambda *a: calls.append(a) or GOOD_CELLS)
    assert calls == []


def test_too_many_cells_raises():
    data = workbook_bytes_from({f'A{row}': row for row in range(1, MAX_AI_CELLS + 2)})
    with pytest.raises(ValueError):
        cell_text(data)
