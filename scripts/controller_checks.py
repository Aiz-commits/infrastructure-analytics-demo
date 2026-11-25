"""AI Controller checks: pure Python, stated values, one step per check. No Streamlit, no AI."""
import re
from dataclasses import dataclass, replace
from decimal import Decimal
from .decompte_extractor import extract_decompte
from .policy import ROOT, amount, expected_amounts

FIELDS = ('works', 'previous', 'cumulative', 'retention', 'net', 'vat', 'ttc')
LABELS = {'works': 'works of month HT', 'previous': 'previous cumulative HT', 'cumulative': 'cumulative HT',
          'retention': 'retention', 'net': 'net HT', 'vat': 'VAT', 'ttc': 'total TTC'}
SOURCE_FIXED = 'fixed layout'
SOURCE_AI = 'found by AI'
SOURCE_EDITED = 'edited by reviewer'
SOURCE_PDF_TEXT = 'PDF text (AI located)'
SOURCE_VISION = 'read by AI from image'
SEVERITIES = ('OK', 'WARNING', 'REVIEW', 'SKIPPED')
EXAMPLES_DIR = ROOT / 'controller_examples'
HISTORY_DIR = ROOT / 'demo_decomptes'
NO_PREVIOUS = 'skipped — no previous décompte'
_EXTRACTOR_KEYS = {'works': 'Works HT', 'previous': 'Previous cumulative HT', 'cumulative': 'Cumulative HT',
                   'retention': 'Retention', 'net': 'Net HT', 'vat': 'VAT', 'ttc': 'TTC'}


@dataclass(frozen=True)
class ReadValue:
    field: str
    value: Decimal | None
    cell: str | None
    source: str
    uncertain: bool = False


@dataclass(frozen=True)
class Statement:
    project: str
    number: int | None
    values: dict


@dataclass(frozen=True)
class Finding:
    id: str
    severity: str
    title: str
    amounts: dict
    difference: Decimal | None
    evidence: str


def from_extractor(record):
    match = re.search(r'!B(\d+)', record['Source cells'])
    if not match:
        raise ValueError('Fixed-layout source cells are missing.')
    row = int(match.group(1))
    cells = {'cumulative': f'B{row}', 'previous': f'C{row}', 'works': f'D{row}', 'retention': f'D{row + 2}',
             'net': f'D{row + 7}', 'vat': f'D{row + 8}', 'ttc': f'D{row + 9}'}
    values = {field: ReadValue(field, record[_EXTRACTOR_KEYS[field]], cells[field], SOURCE_FIXED) for field in FIELDS}
    return Statement(record['Project'], record['Statement number'], values)


def apply_edits(statement, edits, *, project=None, number=None):
    values = dict(statement.values)
    for field, value in edits.items():
        old = values[field]
        value = None if value is None else amount(value)
        if value != old.value:
            values[field] = ReadValue(field, value, old.cell, SOURCE_EDITED, False)
    return Statement(statement.project if project is None else project,
                     statement.number if number is None else number, values)


def parse_edits(raw_values):
    """Reviewer-typed values -> (edits, fields that are not valid amounts). Blank/NaN means 'not found'."""
    edits, bad = {}, []
    for field, raw in raw_values.items():
        if raw is None or (isinstance(raw, float) and raw != raw):
            edits[field] = None
            continue
        try:
            edits[field] = amount(raw)
        except ValueError:
            bad.append(field)
    return edits, bad


def known_projects(folder=HISTORY_DIR):
    """Project names found in the bundled history, used to normalise AI-read project names."""
    names = []
    for path in sorted(folder.glob('*.xlsx')):
        try:
            project = extract_decompte(path)['Project']
        except ValueError:
            continue
        if project and project not in names:
            names.append(project)
    return tuple(names)


def previous_from_history(current, folder=HISTORY_DIR):
    if current.number is None or not current.project:
        return None
    for path in sorted(folder.glob('*.xlsx')):
        try:
            record = extract_decompte(path)
        except ValueError:
            continue
        if record['Statement number'] == current.number - 1 and record['Project'].casefold() == current.project.casefold():
            return from_extractor(record)
    return None


def review_count(findings):
    return sum(finding.severity == 'REVIEW' for finding in findings)


def _cells(statement, *fields):
    return ', '.join(f'{LABELS[f]} {statement.values[f].cell or "?"}' for f in fields)


def _compare(check_id, title, stated, expected, evidence, policy):
    difference = abs(stated - expected)
    severity = 'REVIEW' if difference > policy.tolerance else 'OK'
    return Finding(check_id, severity, title, {'stated': stated, 'expected': expected}, difference, evidence)


def _skipped(check_id, title, missing):
    return Finding(check_id, 'SKIPPED', f'{title} — skipped, missing {", ".join(LABELS[f] for f in missing)}',
                   {}, None, 'missing input value')


def _arithmetic(current, policy):
    v = {field: current.values[field].value for field in FIELDS}
    rate, vat_rate = f'{policy.retention_rate:.0%}', f'{policy.vat_rate:.0%}'
    vat_field = 'net' if policy.vat_base == 'net_after_retention' else 'works'
    retention_inputs = ('works', 'retention') + (('cumulative', 'previous') if policy.retention_cap is not None else ())
    checks = [
        ('retention', f'Retention {rate} of works', retention_inputs,
         lambda: expected_amounts(v['works'], v['cumulative'], v['previous'], policy)['Retention'], 'retention'),
        ('net', 'Net HT = works − retention', ('works', 'retention', 'net'),
         lambda: amount(v['works'] - v['retention']), 'net'),
        ('vat', f'VAT {vat_rate} of {LABELS[vat_field]}', (vat_field, 'vat'),
         lambda: amount(v[vat_field] * policy.vat_rate), 'vat'),
        ('ttc', 'TTC = net HT + VAT', ('net', 'vat', 'ttc'), lambda: amount(v['net'] + v['vat']), 'ttc'),
        ('cumulative', 'Cumulative HT = previous cumulative + works', ('previous', 'works', 'cumulative'),
         lambda: amount(v['previous'] + v['works']), 'cumulative'),
    ]
    findings = []
    for check_id, title, inputs, expected, stated_field in checks:
        missing = [field for field in inputs if v[field] is None]
        if missing:
            findings.append(_skipped(check_id, title, missing))
        else:
            findings.append(_compare(check_id, title, v[stated_field], expected(), _cells(current, *inputs), policy))
    return findings


def _history(current, previous, policy):
    if previous is None:
        return [Finding('continuity', 'SKIPPED', 'Continuity with previous décompte', {}, None, NO_PREVIOUS),
                Finding('sequence', 'SKIPPED', 'Statement sequence', {}, None, NO_PREVIOUS)]
    label = f'D{previous.number} → D{current.number}'
    if current.project and previous.project and current.project.casefold() != previous.project.casefold():
        return [Finding('continuity', 'REVIEW', f'Continuity {label} — different project', {}, None,
                        f'projects "{previous.project}" and "{current.project}"'),
                Finding('sequence', 'SKIPPED', f'Statement sequence {label}', {}, None, 'different project')]
    if current.number is None or previous.number is None:
        return [Finding(i, 'SKIPPED', t, {}, None, 'statement number missing')
                for i, t in (('continuity', 'Continuity with previous décompte'), ('sequence', 'Statement sequence'))]
    if previous.number != current.number - 1:
        missing = ', '.join(f'D{n}' for n in range(previous.number + 1, current.number)) or f'D{current.number - 1}'
        return [Finding('continuity', 'SKIPPED', f'Continuity {label}', {}, None, 'sequence gap'),
                Finding('sequence', 'REVIEW', f'Statement sequence {label} — missing {missing}', {}, None,
                        f'previous available: D{previous.number}')]
    sequence = Finding('sequence', 'OK', f'Statement sequence {label}', {}, None, 'consecutive numbers')
    stated, expected = current.values['previous'].value, previous.values['cumulative'].value
    if stated is None or expected is None:
        return [_skipped('continuity', f'Continuity {label}',
                         ['previous'] if stated is None else ['cumulative']), sequence]
    evidence = f'D{previous.number} {_cells(previous, "cumulative")}; D{current.number} {_cells(current, "previous")}'
    return [_compare('continuity', f'Continuity {label}', stated, expected, evidence, policy), sequence]


def run_checks(current, previous, policy):
    findings = []
    for field in FIELDS:
        read = current.values.get(field)
        if read is None or read.value is None:
            findings.append(Finding(f'missing:{field}', 'WARNING', f'Value not found: {LABELS[field]}', {}, None,
                                    'not found in the file; never invented'))
        elif read.uncertain:
            findings.append(Finding(f'uncertain:{field}', 'WARNING', f'Uncertain label: {LABELS[field]}',
                                    {'stated': read.value}, None, f'cell {read.cell} has no matching label'))
    values = {field: current.values.get(field) or ReadValue(field, None, None, SOURCE_AI) for field in FIELDS}
    current = replace(current, values=values)
    return findings + _arithmetic(current, policy) + _history(current, previous, policy)
