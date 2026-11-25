import json
from decimal import Decimal
import pytest
from scripts.controller_checks import EXAMPLES_DIR, FIELDS, SOURCE_VISION
from scripts.vision_reader import parse_vision_answer, read_with_vision
from tests.pdf_fixtures import d5_values


@pytest.fixture
def answer():
    return json.loads((EXAMPLES_DIR / 'DEMO_DP_N5_PHOTO.jpg.answer.json').read_text(encoding='utf-8'))


def test_saved_photo_answer_parses(answer):
    statement = parse_vision_answer(answer, 'image')
    for field in FIELDS:
        read = statement.values[field]
        assert read.value == d5_values()[field]
        assert (read.source, read.cell, read.uncertain) == (SOURCE_VISION, 'image', False)
    assert (statement.project, statement.number) == ('DEMO PROJECT', 5)


def test_two_numbers_in_value_not_found(answer):
    answer['net'] = {'value': '810 000,00 / 820 000,00', 'label': 'Net HT'}
    assert parse_vision_answer(answer, 'image').values['net'].value is None


def test_wrong_label_uncertain(answer):
    answer['vat'] = {'value': '163 000,00', 'label': 'Net HT'}
    vat = parse_vision_answer(answer, 'image').values['vat']
    assert vat.value == Decimal('163000.00') and vat.uncertain


@pytest.mark.parametrize('junk', ['abc', {'value': None}, 5, {'value': 7}, {'label': 'TVA'}, None, []])
def test_junk_answer_shapes(answer, junk):
    answer['vat'] = junk
    assert parse_vision_answer(answer, 'scanned PDF').values['vat'].value is None


def test_none_from_ai_returns_none():
    assert read_with_vision(b'\xff\xd8\xff', 'image/jpeg', 'k', ask=lambda *a: None) is None


def test_read_with_vision_sends_file_and_mime(answer):
    seen = []

    def ask(prompt, data, mime_type, schema, key):
        seen.append((data, mime_type, prompt))
        return answer
    statement = read_with_vision(b'\x89PNG...', 'image/png', 'k', ask=ask)
    assert seen[0][:2] == (b'\x89PNG...', 'image/png')
    assert 'never compute' in seen[0][2].lower() or 'do not compute' in seen[0][2].lower()
    assert statement.values['ttc'].value == Decimal('973000.00')
    assert statement.values['ttc'].cell == 'image'


def test_scanned_pdf_cell_text(answer):
    statement = read_with_vision(b'%PDF-', 'application/pdf', 'k', ask=lambda *a: answer)
    assert statement.values['vat'].cell == 'scanned PDF'
