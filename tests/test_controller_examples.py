import json
from decimal import Decimal
import pytest
from openpyxl import load_workbook
from generate_demo_decomptes import generate_controller_examples
from scripts.decompte_extractor import extract_decompte
from scripts.policy import ROOT


def test_standard_example_reads_with_fixed_extractor(tmp_path):
    standard, _ = generate_controller_examples(tmp_path)
    record = extract_decompte(standard)
    assert record['Statement number'] == 5
    assert record['Project'] == 'DEMO PROJECT'
    assert record['Works HT'] == Decimal('900000.00')
    assert record['Previous cumulative HT'] == Decimal('2737700.00')
    assert record['Cumulative HT'] == Decimal('3637700.00')
    assert record['Retention'] == Decimal('90000.00')
    assert record['Net HT'] == Decimal('810000.00')
    assert record['VAT'] == Decimal('163000.00')
    assert record['TTC'] == Decimal('973000.00')


def test_new_layout_is_rejected_by_fixed_extractor(tmp_path):
    _, new_layout = generate_controller_examples(tmp_path)
    with pytest.raises(ValueError):
        extract_decompte(new_layout)
    sheet = load_workbook(new_layout).active
    assert sheet.title == 'Situation'
    assert (sheet['F15'].value, sheet['H15'].value) == ('TVA 20%', 163000)


def test_committed_examples_match_generator(tmp_path):
    for generated in generate_controller_examples(tmp_path):
        committed = ROOT / 'controller_examples' / generated.name
        values = lambda path: [[c.value for c in row] for row in load_workbook(path).active.iter_rows()]
        assert values(committed) == values(generated)


def test_document_examples_generated(tmp_path):
    from generate_demo_decomptes import generate_document_examples
    paths = {p.name: p for p in generate_document_examples(tmp_path)}
    assert set(paths) == {'DEMO_DP_N5.pdf', 'DEMO_DP_N5_PHOTO.jpg', 'DEMO_DP_N5.pdf.answer.json',
                          'DEMO_DP_N5_PHOTO.jpg.answer.json'}
    assert paths['DEMO_DP_N5.pdf'].read_bytes().startswith(b'%PDF')
    assert paths['DEMO_DP_N5_PHOTO.jpg'].read_bytes().startswith(b'\xff\xd8\xff')
    photo = json.loads(paths['DEMO_DP_N5_PHOTO.jpg.answer.json'].read_text(encoding='utf-8'))
    assert photo['vat'] == {'value': '163 000,00', 'label': 'TVA 20%'}
    assert (photo['project'], photo['number']) == ('DEMO PROJECT', '5')


def test_committed_document_examples_match_generator(tmp_path):
    from generate_demo_decomptes import generate_document_examples
    from pypdf import PdfReader
    for generated in generate_document_examples(tmp_path):
        committed = ROOT / 'controller_examples' / generated.name
        if generated.suffix == '.json':
            assert json.loads(committed.read_text(encoding='utf-8')) == json.loads(generated.read_text(encoding='utf-8'))
        elif generated.suffix == '.pdf':
            text = lambda path: PdfReader(path).pages[0].extract_text()
            assert text(committed) == text(generated)
        else:
            assert committed.read_bytes()[:3] == b'\xff\xd8\xff'
