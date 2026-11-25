from decimal import Decimal
import pytest
from scripts.controller_checks import FIELDS, SOURCE_PDF_TEXT
from scripts.pdf_reader import extract_tokens, read_pdf_with_ai, trace_pdf
from tests.pdf_fixtures import blank_pdf, d5_table_pdf, d5_values


@pytest.fixture(scope='module')
def pdf():
    return d5_table_pdf()


def answer_for(data):
    """Map each field to the token holding its known D5 value (what a correct AI would return)."""
    tokens, _ = extract_tokens(data)
    values = d5_values()
    ids = {}
    for field in FIELDS:
        ids[field] = next(t.id for t in tokens if t.value == values[field])
    return {**ids, 'project': 'DEMO PROJECT', 'number': 'D5'}


def test_traces_all_seven(pdf):
    statement = trace_pdf(pdf, answer_for(pdf))
    for field in FIELDS:
        read = statement.values[field]
        assert read.value == d5_values()[field]
        assert read.source == SOURCE_PDF_TEXT
        assert not read.uncertain, field
        assert read.cell.startswith('page 1 · line "')
    assert (statement.project, statement.number) == ('DEMO PROJECT', 5)


def test_table_row_values_pass_column_header_check(pdf):
    tokens, _ = extract_tokens(pdf)
    row = [t for t in tokens if t.value in (Decimal('3637700.00'), Decimal('2737700.00'), Decimal('900000.00'))]
    assert len({t.line for t in row}) == 1
    statement = trace_pdf(pdf, answer_for(pdf))
    assert not any(statement.values[f].uncertain for f in ('cumulative', 'previous', 'works'))


def test_swapped_table_columns_are_uncertain(pdf):
    answer = answer_for(pdf)
    answer['cumulative'], answer['previous'] = answer['previous'], answer['cumulative']
    statement = trace_pdf(pdf, answer)
    assert statement.values['cumulative'].uncertain and statement.values['previous'].uncertain


def test_wrong_token_is_uncertain(pdf):
    answer = {**answer_for(pdf), 'vat': answer_for(pdf)['retention']}
    vat = trace_pdf(pdf, answer).values['vat']
    assert vat.value == Decimal('90000.00') and vat.uncertain


def test_unknown_and_duplicate_ids(pdf):
    statement = trace_pdf(pdf, {'works': 'T999', 'net': 'T1', 'vat': 'T1', 'ttc': 7, 'project': None})
    assert statement.values['works'].value is None
    assert statement.values['ttc'].value is None
    assert statement.values['net'].value == statement.values['vat'].value


def test_blank_pdf_raises_no_text():
    with pytest.raises(ValueError, match='NO_TEXT'):
        read_pdf_with_ai(blank_pdf(), 'k', ask=lambda *a: {})


def test_prompt_lists_tokens_not_bytes(pdf):
    seen = []

    def ask(prompt, schema, key):
        seen.append(prompt)
        return answer_for(pdf)
    statement = read_pdf_with_ai(pdf, 'k', ask=ask)
    assert 'T1 | p1 |' in seen[0] and '%PDF' not in seen[0]
    assert statement.values['vat'].value == Decimal('163000.00')


def test_ai_failure_returns_none(pdf):
    assert read_pdf_with_ai(pdf, 'k', ask=lambda *a: None) is None


def test_unknown_project_not_in_text_is_dropped(pdf):
    statement = trace_pdf(pdf, {**answer_for(pdf), 'project': 'Invented Site'})
    assert statement.project == ''
