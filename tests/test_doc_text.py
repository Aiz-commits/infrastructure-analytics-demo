from decimal import Decimal
import pytest
from scripts.doc_text import AMOUNT_PATTERN, label_matches, parse_amount_text


@pytest.mark.parametrize('text, expected', [
    ('2 750 000,00', '2750000.00'), ('2,750,000.00', '2750000.00'), ('2750000.00', '2750000.00'),
    ('163 000,00 DH', '163000.00'), ('973000 MAD', '973000.00'), ('2 750 000,00', '2750000.00'),
    ('2 750 000,00', '2750000.00'), ('1.000', '1000.00'), ('1,000', '1000.00'), ('90000,5', '90000.50'),
    ('-12 300,00', '-12300.00')])
def test_parse_amount_text(text, expected):
    assert parse_amount_text(text) == Decimal(expected)


@pytest.mark.parametrize('text', ['', 'TVA', '810 000,00 / 820 000,00', '12/03/2026', 'abc 5', None])
def test_parse_amount_text_rejects(text):
    assert parse_amount_text(text) is None


def test_amount_pattern_finds_every_amount_on_a_row():
    found = [m.group() for m in AMOUNT_PATTERN.finditer('3 637 700,00   2 737 700,00   900 000,00')]
    assert found == ['3 637 700,00', '2 737 700,00', '900 000,00']


def test_label_matches():
    assert label_matches('vat', 'TVA 20%')
    assert label_matches('retention', 'Retenue de garantie 10%')
    assert not label_matches('cumulative', 'Cumul précédent HT')
    assert label_matches('previous', 'Cumul précédent HT')


@pytest.mark.parametrize('project, number, expected', [
    ('DEMO PROJECT — DECOMPTE D5', 'D5', ('DEMO PROJECT', 5)),
    ('demo project', 'Décompte n° 5', ('DEMO PROJECT', 5)),
    ('Other site', '12000', ('Other site', None)),
    (None, None, ('', None)),
    ('  Site A  ', 7, ('Site A', 7))])
def test_normalize_identity(project, number, expected):
    from scripts.doc_text import normalize_identity
    assert normalize_identity(project, number, ('DEMO PROJECT',)) == expected


def test_known_projects():
    from scripts.controller_checks import known_projects
    assert known_projects() == ('DEMO PROJECT',)
