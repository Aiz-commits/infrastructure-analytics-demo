from dataclasses import replace
from decimal import Decimal
import pytest
from scripts.controller_checks import (EXAMPLES_DIR, FIELDS, SOURCE_AI, SOURCE_EDITED, SOURCE_FIXED, ReadValue,
                                       Statement, apply_edits, from_extractor, previous_from_history,
                                       review_count, run_checks)
from scripts.decompte_extractor import extract_decompte
from scripts.policy import load_policy

POLICY = load_policy()
GOOD = dict(works='100.00', previous='0.00', cumulative='100.00', retention='10.00',
            net='90.00', vat='18.00', ttc='108.00')


def stmt(number=1, project='DEMO PROJECT', source=SOURCE_FIXED, uncertain=(), **changes):
    values = {**GOOD, **changes}
    return Statement(project, number, {
        f: ReadValue(f, None if values[f] is None else Decimal(values[f]), f'X{i}', source, f in uncertain)
        for i, f in enumerate(FIELDS, start=1)})


def by_id(findings):
    return {f.id: f for f in findings}


def severities(findings):
    return {f.id: f.severity for f in findings}


def test_n5_gives_exactly_two_reviews():
    current = from_extractor(extract_decompte(EXAMPLES_DIR / 'DEMO_DP_N5.xlsx'))
    previous = previous_from_history(current)
    assert previous.number == 4
    findings = run_checks(current, previous, POLICY)
    reviews = {f.id: f.difference for f in findings if f.severity == 'REVIEW'}
    assert reviews == {'continuity': Decimal('12300.00'), 'vat': Decimal('1000.00')}
    assert review_count(findings) == 2


def test_fixed_layout_values_keep_cells_and_source():
    current = from_extractor(extract_decompte(EXAMPLES_DIR / 'DEMO_DP_N5.xlsx'))
    assert current.values['works'] == ReadValue('works', Decimal('900000.00'), 'D37', SOURCE_FIXED)
    assert current.values['vat'].cell == 'D45'
    assert (current.project, current.number) == ('DEMO PROJECT', 5)


def test_clean_statement_all_ok():
    found = severities(run_checks(stmt(), None, POLICY))
    assert all(found[k] == 'OK' for k in ('retention', 'net', 'vat', 'ttc', 'cumulative'))


def test_one_wrong_cell_gives_one_finding():
    findings = run_checks(stmt(ttc='113.00'), None, POLICY)
    assert [f.id for f in findings if f.severity == 'REVIEW'] == ['ttc']
    assert by_id(findings)['ttc'].difference == Decimal('5.00')


def test_tolerance_edge():
    assert severities(run_checks(stmt(ttc='108.01'), None, POLICY))['ttc'] == 'OK'
    assert severities(run_checks(stmt(ttc='108.02'), None, POLICY))['ttc'] == 'REVIEW'


def test_no_previous_is_skipped_not_review():
    findings = by_id(run_checks(stmt(number=2), None, POLICY))
    for key in ('continuity', 'sequence'):
        assert findings[key].severity == 'SKIPPED'
        assert findings[key].evidence == 'skipped — no previous décompte'


def test_continuity_ok_with_matching_previous():
    findings = severities(run_checks(stmt(number=2, previous='100.00', cumulative='200.00'), stmt(), POLICY))
    assert (findings['continuity'], findings['sequence']) == ('OK', 'OK')


def test_gap_d3_to_d5_is_sequence_review():
    findings = severities(run_checks(stmt(number=5), stmt(number=3), POLICY))
    assert (findings['sequence'], findings['continuity']) == ('REVIEW', 'SKIPPED')


def test_different_project_is_review():
    findings = by_id(run_checks(stmt(number=2), stmt(project='OTHER'), POLICY))
    assert findings['continuity'].severity == 'REVIEW'
    assert 'different project' in findings['continuity'].title


def test_missing_vat_skips_vat_and_ttc():
    findings = severities(run_checks(stmt(vat=None), None, POLICY))
    assert findings['missing:vat'] == 'WARNING'
    assert (findings['vat'], findings['ttc']) == ('SKIPPED', 'SKIPPED')
    assert findings['net'] == 'OK'


def test_uncertain_value_is_warning():
    findings = severities(run_checks(stmt(source=SOURCE_AI, uncertain=('vat',)), None, POLICY))
    assert findings['uncertain:vat'] == 'WARNING'


def test_vat_base_works_ht_uses_works():
    policy = replace(POLICY, vat_base='works_ht')
    assert severities(run_checks(stmt(vat='20.00', ttc='110.00'), None, policy))['vat'] == 'OK'


def test_apply_edits_marks_source():
    edited = apply_edits(stmt(source=SOURCE_AI, uncertain=('vat',)), {'vat': Decimal('18.50'), 'net': Decimal('90.00')})
    assert edited.values['vat'] == ReadValue('vat', Decimal('18.50'), 'X6', SOURCE_EDITED, False)
    assert edited.values['net'].source == SOURCE_AI
    typed = apply_edits(stmt(number=None, project=''), {}, project='P1', number=3)
    assert (typed.project, typed.number) == ('P1', 3)
