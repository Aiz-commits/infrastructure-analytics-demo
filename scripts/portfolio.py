"""Synthetic portfolio for the Power BI management dashboard (Phase 2.5). No Streamlit, no AI.

Every statement is generated, then checked by the real `run_checks` with the real policy, so every finding comes
from Python. Decisions and timings are simulated with a fixed seed. Nothing here is real data.

    python -m scripts.portfolio --load            # replace the portfolio_* rows in DATABASE_URL
    python -m scripts.portfolio --csv powerbi/data --expected powerbi/expected_totals.json
"""
import argparse
import csv
import json
import os
import random
import statistics
import tomllib
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from sqlalchemy import (Column, Date, DateTime, ForeignKey, Integer, MetaData, Numeric, String, Table, Text,
                        delete, insert, text)
from .controller_checks import FIELDS, SOURCE_FIXED, ReadValue, Statement, review_count, run_checks
from .history import CHECK_GROUP_SQL, create_views, get_engine
from .policy import ROOT, amount, expected_amounts, load_policy

SEED = 2025
LABEL = 'Synthetic portfolio — generated, not real'
TARGET_DAYS = Decimal('5')  # Demo assumption for "decided within target".


@dataclass(frozen=True)
class Project:
    project: str
    contractor: str
    contract_ttc: Decimal
    start_date: date
    statements: int
    speed_days: float  # Typical days from opening to decision for this contractor (simulation input).


PROJECTS = (
    Project('DEMO ROAD R1', 'Alpha Works (fictional)', Decimal('5400000.00'), date(2025, 9, 1), 9, 2.0),
    Project('DEMO BRIDGE B2', 'Beta Build (fictional)', Decimal('3600000.00'), date(2025, 11, 1), 7, 4.5),
    Project('DEMO WATER W3', 'Alpha Works (fictional)', Decimal('7200000.00'), date(2025, 10, 1), 10, 2.5),
    Project('DEMO SCHOOL S4', 'Gamma Infra (fictional)', Decimal('2400000.00'), date(2026, 1, 1), 6, 6.0),
)
# Planted problems: (project, statement number) -> kind. Fixed, so the answer key is readable in one place.
PLANTED = {
    ('DEMO ROAD R1', 3): 'vat', ('DEMO ROAD R1', 7): 'continuity',
    ('DEMO BRIDGE B2', 2): 'retention', ('DEMO BRIDGE B2', 5): 'missing statement',
    ('DEMO BRIDGE B2', 6): 'ttc',
    ('DEMO WATER W3', 4): 'continuity', ('DEMO WATER W3', 8): 'vat',
    ('DEMO SCHOOL S4', 2): 'cumulative', ('DEMO SCHOOL S4', 4): 'vat', ('DEMO SCHOOL S4', 5): 'retention',
}
PENDING = {('DEMO WATER W3', 10), ('DEMO SCHOOL S4', 6)}  # Latest statements not decided yet.
ERROR_AMOUNTS = (Decimal('4500.00'), Decimal('12300.00'), Decimal('27800.00'), Decimal('61250.00'))

metadata = MetaData()
projects_table = Table(
    'portfolio_projects', metadata,
    Column('project', String(120), primary_key=True),
    Column('contractor', String(120), nullable=False),
    Column('contract_ttc', Numeric(14, 2), nullable=False),
    Column('start_date', Date, nullable=False),
)
statements_table = Table(
    'portfolio_statements', metadata,
    Column('statement_id', Integer, primary_key=True, autoincrement=False),
    Column('project', String(120), ForeignKey('portfolio_projects.project'), nullable=False),
    Column('statement_number', Integer, nullable=False),
    *(Column(field, Numeric(14, 2), nullable=False) for field in FIELDS),
    Column('cumulative_ttc_billed', Numeric(14, 2), nullable=False),
    Column('submitted_at', DateTime(timezone=True), nullable=False),
    Column('opened_at', DateTime(timezone=True), nullable=False),
    Column('decided_at', DateTime(timezone=True)),
    Column('decision', String(16), nullable=False),
    Column('days_to_decision', Numeric(8, 2)),
    Column('review_count', Integer, nullable=False),
    Column('warning_count', Integer, nullable=False),
    Column('planted_problem', String(40)),
)
findings_table = Table(
    'portfolio_findings', metadata,
    Column('statement_id', Integer, ForeignKey('portfolio_statements.statement_id'), nullable=False, index=True),
    Column('check_id', String(32), nullable=False),
    Column('severity', String(8), nullable=False),
    Column('title', Text, nullable=False),
    Column('stated', Numeric(14, 2)),
    Column('expected', Numeric(14, 2)),
    Column('difference', Numeric(14, 2)),
    Column('evidence', Text, nullable=False),
)
# Power BI view contract (see powerbi/README.md). Columns are only ever appended.
VIEWS = {
    'v_portfolio_projects': (
        'SELECT p.project, p.contractor, p.contract_ttc, p.start_date, '
        'COALESCE(SUM(s.ttc), 0) AS billed_ttc, COUNT(s.statement_id) AS statements '
        'FROM portfolio_projects p LEFT JOIN portfolio_statements s ON s.project = p.project '
        'GROUP BY p.project, p.contractor, p.contract_ttc, p.start_date'),
    'v_portfolio_statements': (
        'SELECT s.statement_id, s.project, p.contractor, s.statement_number, s.works, s.previous, s.cumulative, '
        's.retention, s.net, s.vat, s.ttc, s.cumulative_ttc_billed, p.contract_ttc, s.submitted_at, s.opened_at, '
        's.decided_at, s.decision, s.days_to_decision, s.review_count, s.warning_count '
        'FROM portfolio_statements s JOIN portfolio_projects p ON p.project = s.project'),
    'v_portfolio_findings': (
        'SELECT f.statement_id, s.project, p.contractor, s.statement_number, s.decision, f.check_id, '
        + CHECK_GROUP_SQL.format(col='f.check_id') + ' AS check_group, '
        'f.severity, f.title, f.stated, f.expected, f.difference, f.evidence '
        'FROM portfolio_findings f JOIN portfolio_statements s ON s.statement_id = f.statement_id '
        'JOIN portfolio_projects p ON p.project = s.project'),
}
VIEW_COLUMNS = {
    'v_portfolio_projects': ('project', 'contractor', 'contract_ttc', 'start_date', 'billed_ttc', 'statements'),
    'v_portfolio_statements': ('statement_id', 'project', 'contractor', 'statement_number', *FIELDS,
                               'cumulative_ttc_billed', 'contract_ttc', 'submitted_at', 'opened_at', 'decided_at',
                               'decision', 'days_to_decision', 'review_count', 'warning_count'),
    'v_portfolio_findings': ('statement_id', 'project', 'contractor', 'statement_number', 'decision', 'check_id',
                             'check_group', 'severity', 'title', 'stated', 'expected', 'difference', 'evidence'),
}


# Cells of the standard décompte template (same as controller_checks.from_extractor with the totals on row 37).
CELLS = {'cumulative': 'B37', 'previous': 'C37', 'works': 'D37', 'retention': 'D39', 'net': 'D44', 'vat': 'D45',
         'ttc': 'D46'}


def _statement(project, number, values):
    return Statement(project, number, {f: ReadValue(f, values[f], CELLS[f], SOURCE_FIXED) for f in FIELDS})


def _plant(kind, values, error):
    """Return stated values with one deliberate mistake. Correct values are kept for the next statement."""
    stated = dict(values)
    if kind == 'vat':
        stated['vat'] = values['vat'] + error
        stated['ttc'] = stated['net'] + stated['vat']
    elif kind == 'retention':
        stated['retention'] = values['retention'] - error
    elif kind == 'continuity':
        stated['previous'] = values['previous'] - error
    elif kind == 'cumulative':
        stated['cumulative'] = values['cumulative'] + error
    elif kind == 'ttc':
        stated['ttc'] = values['ttc'] + error
    return stated


def _timings(rng, project, submitted, findings, pending):
    opened = submitted + timedelta(hours=rng.uniform(2, 48))
    if pending:
        return opened, None, 'Pending', None
    problems = review_count(findings)
    days = rng.uniform(0.5, 1.5) * project.speed_days * (1.8 if problems else 1.0)
    decided = opened + timedelta(days=days)
    rejected = bool(problems) or rng.random() < 0.05  # A REVIEW finding is never approved in this simulation.
    return opened, decided, 'Rejected' if rejected else 'Approved', amount((decided - submitted).total_seconds() / 86400)


def generate(policy=None, seed=SEED):
    """-> (projects, statements, findings) as lists of row dicts, ready to insert."""
    policy = policy or load_policy()
    rng = random.Random(seed)
    projects, statements, findings = [], [], []
    for project in PROJECTS:
        projects.append({'project': project.project, 'contractor': project.contractor,
                         'contract_ttc': project.contract_ttc, 'start_date': project.start_date})
        contract_ht = amount(project.contract_ttc / ((1 - policy.retention_rate) * (1 + policy.vat_rate)))
        target = rng.uniform(0.55, 0.92)
        previous_statement, cumulative, billed = None, Decimal('0.00'), Decimal('0.00')
        for number in range(1, project.statements + 1):
            share = Decimal(str(round(target / project.statements * rng.uniform(0.6, 1.4), 4)))
            works = amount(contract_ht * share)
            parts = expected_amounts(works, cumulative + works, cumulative, policy)
            values = {'works': works, 'previous': cumulative, 'cumulative': cumulative + works,
                      'retention': parts['Retention'], 'net': parts['Net HT'], 'vat': parts['VAT'],
                      'ttc': parts['TTC']}
            cumulative = values['cumulative']
            kind = PLANTED.get((project.project, number))
            if kind == 'missing statement':  # The contractor never sends it: the next one shows the gap.
                continue
            stated = _plant(kind, values, rng.choice(ERROR_AMOUNTS)) if kind else values
            current = _statement(project.project, number, stated)
            checked = run_checks(current, previous_statement, policy)
            previous_statement = current
            billed += stated['ttc']
            month_end = project.start_date + timedelta(days=30 * number + rng.randint(0, 4))
            submitted = datetime.combine(month_end, time(9), timezone.utc) + timedelta(hours=rng.randint(0, 8))
            opened, decided, decision, days = _timings(rng, project, submitted, checked,
                                                       (project.project, number) in PENDING)
            statement_id = len(statements) + 1
            statements.append({
                'statement_id': statement_id, 'project': project.project, 'statement_number': number, **stated,
                'cumulative_ttc_billed': billed, 'submitted_at': submitted, 'opened_at': opened,
                'decided_at': decided, 'decision': decision, 'days_to_decision': days,
                'review_count': review_count(checked),
                'warning_count': sum(f.severity == 'WARNING' for f in checked), 'planted_problem': kind})
            findings += [{'statement_id': statement_id, 'check_id': f.id, 'severity': f.severity, 'title': f.title,
                          'stated': f.amounts.get('stated'), 'expected': f.amounts.get('expected'),
                          'difference': f.difference, 'evidence': f.evidence} for f in checked]
    return projects, statements, findings


def ensure_schema(engine):
    metadata.create_all(engine)
    with engine.begin() as conn:
        create_views(conn, VIEWS)


def load(engine, policy=None):
    """Replace the portfolio rows. Rows are deleted, not tables dropped, so views and Power BI grants survive."""
    projects, statements, findings = generate(policy)
    ensure_schema(engine)
    with engine.begin() as conn:
        for table in (findings_table, statements_table, projects_table):
            conn.execute(delete(table))
        conn.execute(insert(projects_table), projects)
        conn.execute(insert(statements_table), statements)
        conn.execute(insert(findings_table), findings)
    return len(statements), len(findings)


def _median(values):
    values = sorted(v for v in values if v is not None)
    return amount(statistics.median(values)) if values else None


def view_rows(generated):
    """Rows of the three portfolio views, built in Python with exact Decimals (tested equal to the SQL views)."""
    projects, statements, findings = generated
    project_of = {p['project']: p for p in projects}
    by_id = {s['statement_id']: s for s in statements}
    return {
        'v_portfolio_projects': [
            {**p, 'billed_ttc': sum((s['ttc'] for s in statements if s['project'] == p['project']), Decimal('0.00')),
             'statements': sum(s['project'] == p['project'] for s in statements)} for p in projects],
        'v_portfolio_statements': [
            {**s, 'contractor': project_of[s['project']]['contractor'],
             'contract_ttc': project_of[s['project']]['contract_ttc']} for s in statements],
        'v_portfolio_findings': [
            {**f, 'project': by_id[f['statement_id']]['project'],
             'contractor': project_of[by_id[f['statement_id']]['project']]['contractor'],
             'statement_number': by_id[f['statement_id']]['statement_number'],
             'decision': by_id[f['statement_id']]['decision'], 'check_group': check_group(f['check_id'])}
            for f in findings],
    }


def expected_totals(generated):
    """Headline numbers Power BI must show (spec section 8), computed in Python from the generated rows."""
    rows = view_rows(generated)
    projects, statements, findings = rows['v_portfolio_projects'], rows['v_portfolio_statements'], \
        rows['v_portfolio_findings']
    reviews = [f for f in findings if f['severity'] == 'REVIEW']
    decided = [s for s in statements if s['days_to_decision'] is not None]
    contract = sum(p['contract_ttc'] for p in projects)
    billed = sum(p['billed_ttc'] for p in projects)
    contractors = sorted({p['contractor'] for p in projects})
    return {
        'label': LABEL, 'seed': SEED,
        'portfolio': {
            'contract_ttc': str(contract), 'billed_ttc': str(billed),
            'pct_contract_billed': str(amount(billed / contract * 100)),
            'statements': len(statements), 'pending_statements': len(statements) - len(decided),
            'review_findings': len(reviews),
            'rejected_statements': sum(s['decision'] == 'Rejected' for s in statements),
            'median_days_to_decision': str(_median(s['days_to_decision'] for s in decided)),
            'target_days': str(TARGET_DAYS),
            'pct_decided_within_target': str(amount(
                Decimal(sum(s['days_to_decision'] <= TARGET_DAYS for s in decided)) / len(decided) * 100))},
        'projects': {p['project']: {'contractor': p['contractor'], 'contract_ttc': str(p['contract_ttc']),
                                    'billed_ttc': str(p['billed_ttc']),
                                    'pct_contract_billed': str(amount(p['billed_ttc'] / p['contract_ttc'] * 100))}
                     for p in projects},
        'contractors': {name: {
            'review_findings': sum(f['contractor'] == name for f in reviews),
            'median_days_to_decision': str(_median(s['days_to_decision'] for s in decided
                                                   if s['contractor'] == name))} for name in contractors},
    }


def _csv_value(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    return '' if value is None else str(value)


def export_csv(folder, generated):
    """Write the three portfolio views as CSV (UTF-8, comma, UTC times) so Power BI can be built without Neon."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for view, rows in view_rows(generated).items():
        with open(folder / f'{view}.csv', 'w', newline='', encoding='utf-8') as handle:
            writer = csv.writer(handle, lineterminator='\n')
            writer.writerow(VIEW_COLUMNS[view])
            writer.writerows([_csv_value(row[c]) for c in VIEW_COLUMNS[view]] for row in rows)


def check_group(check_id):
    """Python twin of CHECK_GROUP_SQL (tested to agree)."""
    if check_id.startswith('missing:'):
        return 'missing value'
    if check_id.startswith('uncertain:'):
        return 'uncertain label'
    return check_id if check_id in ('continuity', 'sequence') else 'arithmetic'


def database_url():
    if os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    secrets = ROOT / '.streamlit' / 'secrets.toml'
    if secrets.exists():
        return tomllib.loads(secrets.read_text(encoding='utf-8')).get('DATABASE_URL')
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--load', action='store_true', help='replace portfolio rows in DATABASE_URL')
    parser.add_argument('--csv', type=Path, help='write the portfolio views as CSV files into this folder')
    parser.add_argument('--expected', type=Path, help='write the headline totals JSON to this path')
    args = parser.parse_args(argv)
    if not (args.load or args.csv or args.expected):
        parser.error('choose at least one of --load, --csv, --expected')
    if args.load:
        url = database_url()
        if not url:
            parser.error('DATABASE_URL not set (environment or .streamlit/secrets.toml)')
        engine = get_engine(url)
        count, found = load(engine)
        print(f'Loaded {count} synthetic statements and {found} findings.')
    if args.csv:
        export_csv(args.csv, generate())
        print(f'Wrote CSV files to {args.csv}')
    if args.expected:
        args.expected.write_text(json.dumps(expected_totals(generate()), indent=2,
                                            ensure_ascii=False) + '\n', encoding='utf-8')
        print(f'Wrote {args.expected}')


if __name__ == '__main__':
    main()
