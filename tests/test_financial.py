from dataclasses import replace
from decimal import Decimal
from io import BytesIO
import hashlib
import pytest
from openpyxl import load_workbook
from scripts.decompte_extractor import extract_decompte, filename_number
from scripts.policy import amount, load_policy


@pytest.mark.parametrize('layout', [1, 2])
def test_supported_layouts_and_decimal_rounding(make_workbook, layout):
    data = make_workbook(layout=layout, works=100.05, cumulative=100.05,
                         retention=10.01, net=90.04, vat=18.01, ttc=108.05)
    result = extract_decompte(data)
    assert result['Status'] == 'OK'
    assert result['Expected TTC'] == Decimal('108.05')
    assert isinstance(result['Cumulative HT'], Decimal)
    assert amount('1.005') == Decimal('1.01')


@pytest.mark.parametrize('value', [None, True, False, 'NaN', 'Infinity', '-Infinity', 'invalid', '1e30'])
def test_invalid_amounts(value):
    with pytest.raises(ValueError):
        amount(value)


def test_wrong_cumulative_is_not_passed(make_workbook):
    assert extract_decompte(make_workbook(cumulative=999))['Status'] == 'REVIEW REQUIRED'


def test_missing_previous_is_incomplete_for_second_statement(make_workbook):
    result = extract_decompte(make_workbook(number=2, previous=None))
    assert result['Status'] == 'MISSING DATA'


def test_first_blank_opening_is_explicitly_supported(make_workbook):
    result = extract_decompte(make_workbook(previous=None))
    assert result['Status'] == 'OK'
    assert result['Previous cumulative HT'] == 0
    assert result['Opening balance note']


def test_first_nonzero_opening_requires_review(make_workbook):
    assert extract_decompte(make_workbook(previous=10, cumulative=110))['Status'] == 'REVIEW REQUIRED'


def test_cover_sheet_does_not_hide_summary(make_workbook):
    assert extract_decompte(make_workbook(cover=True))['Status'] == 'OK'


def test_selected_sheet_is_authoritative(make_workbook):
    with pytest.raises(ValueError, match='Unsupported statement layout'):
        extract_decompte(make_workbook(cover=True), sheet_name='Cover')


def test_ambiguous_summaries_need_explicit_selection(make_workbook):
    workbook = load_workbook(BytesIO(make_workbook()))
    workbook.copy_worksheet(workbook['DP']).title = 'DP2'
    buffer = BytesIO(); workbook.save(buffer); workbook.close()
    with pytest.raises(ValueError, match='exactly one'):
        extract_decompte(buffer.getvalue())
    assert extract_decompte(buffer.getvalue(), sheet_name='DP2')['Status'] == 'OK'


def test_formula_without_cached_value_has_useful_error(make_workbook):
    with pytest.raises(ValueError, match='Formula cells need up-to-date results'):
        extract_decompte(make_workbook(formula=True))


def test_declared_totals_must_reconcile_even_with_individual_cent_tolerance(make_workbook):
    result = extract_decompte(make_workbook(net=90.01, vat=18.01, ttc=107.99))
    assert result['Status'] == 'REVIEW REQUIRED'
    assert 'Declared TTC' in result['Validation issues']


def test_configured_gross_vat_base(make_workbook):
    policy = replace(load_policy(), vat_base='works_ht')
    assert extract_decompte(make_workbook(vat=20, ttc=110), policy=policy)['Status'] == 'OK'


def test_retention_cap_applies_to_cumulative_amounts(make_workbook):
    policy = replace(load_policy(), retention_cap=Decimal('15'))
    result = extract_decompte(make_workbook(number=2, previous=100, cumulative=200,
                                          retention=5, net=95, vat=19, ttc=114), policy=policy)
    assert result['Status'] == 'OK'


def test_source_bytes_are_unchanged(make_workbook):
    buffer = BytesIO(make_workbook())
    before = hashlib.sha256(buffer.getvalue()).digest()
    extract_decompte(buffer)
    assert before == hashlib.sha256(buffer.getvalue()).digest()


@pytest.mark.parametrize('filename', ['DP_N10001.xlsx', 'DP_N' + '9' * 100 + '.xlsx', 'a' * 241])
def test_filename_numbers_are_bounded(filename):
    with pytest.raises(ValueError):
        filename_number(filename)
