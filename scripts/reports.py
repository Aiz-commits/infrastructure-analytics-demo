"""Reproducible report generation and integrity checks for synthetic demo data."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import pandas as pd
from .audit import audit_batch, display_frame
from .policy import ROOT, amount, load_policy
from .report_styles import style_report

REPORT_NAMES = {
    'Consolidated Financial Audit': 'rapport_audit_financier.xlsx',
    'Financial Calculation Verification': 'verification_calculs.xlsx',
    'Retention, VAT and TTC Audit': 'verification_retention_tva.xlsx',
    'Technical Quantity Audit': 'audit_technique_valide.xlsx',
}
RULE_FILES = ['project_config.json', 'scripts/policy.py', 'scripts/decompte_extractor.py',
              'scripts/workbooks.py', 'scripts/audit.py', 'scripts/reports.py', 'scripts/report_styles.py']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def technical_audit(path):
    frame = pd.read_csv(path, keep_default_na=False)
    statuses, reasons = [], []
    for _, row in frame.iterrows():
        issues = []
        previous, current, cumulative, limit = [amount(row[col]) for col in
            ['Precedent D4', 'Actuel D4', 'Cumul D4', 'Quantite marche D4']]
        if min(previous, current, cumulative, limit) < 0:
            issues.append('Negative quantity')
        if cumulative != previous + current:
            issues.append('Cumulative quantity does not equal previous plus current')
        if cumulative > limit:
            issues.append('Cumulative quantity exceeds contract quantity')
        if row['Manual review note']:
            issues.append(row['Manual review note'])
        statuses.append('REVIEW REQUIRED' if issues else 'OK')
        reasons.append('; '.join(issues))
    frame['Statut validation'] = statuses
    frame['Review reason'] = reasons
    return frame


def build_reports(root=ROOT):
    root = Path(root)
    policy = load_policy(root / 'project_config.json')
    paths = sorted((root / 'demo_decomptes').glob('*.xlsx'))
    batch = audit_batch([(path.name, path) for path in paths], policy)
    if batch.status != 'OK':
        raise ValueError('Cannot publish demo reports from incomplete/invalid statements: ' + '; '.join(batch.issues))
    records = sorted(batch.records, key=lambda record: record['Statement number'])
    financial = display_frame([{'Decompte': f"D{r['Statement number']}",
                               'Cumul actuel HT': r['Cumulative HT'],
                               'Cumul precedent HT': r['Previous cumulative HT'],
                               'Travaux du mois HT': r['Works HT']} for r in records])
    taxes = []
    for record in records:
        row = {'Décompte': f"D{record['Statement number']} - Demo", 'Travaux HT': record['Works HT']}
        for key, label, suffix in [('Retention', 'Retenue', 'ée'), ('Net HT', 'HT net', 'é'),
                                   ('VAT', 'TVA', 'ée'), ('TTC', 'TTC', 'é')]:
            row[f'{label} calcul{suffix}'] = record[f'Expected {key}']
            row[f'{label} déclar{suffix}'] = record[key]
        row.update({'Écart maximum DH': record['Maximum difference'], 'Statut': record['Status']})
        taxes.append(row)
    tax_frame = display_frame(taxes)
    continuity = display_frame(batch.comparisons)
    technical = technical_audit(root / 'scripts/demo_technical.csv')
    inputs = paths + [root / 'scripts/demo_technical.csv']
    manifest = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'rule_version': policy.version,
        'policy_name': policy.name,
        'inputs': {str(path.relative_to(root)): digest(path) for path in inputs},
        'rules': {name: digest(root / name) for name in RULE_FILES},
        'artifacts': {},
    }
    metadata = pd.DataFrame([{'Property': key, 'Value': value if isinstance(value, str) else json.dumps(value, sort_keys=True)}
                             for key, value in manifest.items() if key != 'artifacts'])
    definitions = {
        'financial_analysis.xlsx': {'Sheet1': financial},
        'financial_audit.xlsx': {'Sheet1': continuity},
        'verification_calculs.xlsx': {'Sheet1': tax_frame},
        'verification_retention_tva.xlsx': {'Sheet1': tax_frame},
        'rapport_audit_financier.xlsx': {'Continuity_Checks': continuity, 'VAT_Verification': tax_frame},
        'audit_technique_valide.xlsx': {'Controle_D3_D4': technical},
    }
    output = root / 'outputs'
    output.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=output) as temporary:
        for filename, sheets in definitions.items():
            path = Path(temporary) / filename
            with pd.ExcelWriter(path, engine='openpyxl') as writer:
                for name, frame in sheets.items():
                    frame.to_excel(writer, sheet_name=name, index=False)
                metadata.to_excel(writer, sheet_name='Metadata', index=False)
                style_report(writer.book, filename, sheets, manifest, policy, records, batch.comparisons, technical)
            manifest['artifacts'][filename] = digest(path)
        for filename in definitions:
            (Path(temporary) / filename).replace(output / filename)
        path = Path(temporary) / 'manifest.json'
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        path.replace(output / 'manifest.json')
    return manifest


def verified_report(filename, root=ROOT):
    """Reject stale, tampered, or untraceable reports instead of displaying a pass."""
    root = Path(root)
    if filename not in set(REPORT_NAMES.values()) | {'financial_analysis.xlsx', 'financial_audit.xlsx'}:
        raise ValueError('Unknown demo report.')
    try:
        manifest = json.loads((root / 'outputs/manifest.json').read_text(encoding='utf-8'))
        for group in ['inputs', 'rules']:
            if not isinstance(manifest[group], dict) or not manifest[group]:
                raise ValueError('Missing report provenance.')
            for name, expected in manifest[group].items():
                path = (root / name).resolve()
                if not path.is_relative_to(root.resolve()) or digest(path) != expected:
                    raise ValueError('Source data or financial rules changed; regenerate the demo reports.')
        for required in RULE_FILES + ['scripts/demo_technical.csv']:
            if required not in manifest['inputs'] and required not in manifest['rules']:
                raise ValueError('Report provenance is incomplete.')
        declared_sources = {name for name in manifest['inputs'] if name.startswith('demo_decomptes/')}
        actual_sources = {str(path.relative_to(root)) for path in (root / 'demo_decomptes').glob('*.xlsx')}
        if actual_sources != declared_sources:
            raise ValueError('Demo statement collection changed; regenerate reports.')
        path = root / 'outputs' / filename
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest['artifacts'][filename]:
            raise ValueError('Report integrity check failed; regenerate the demo reports.')
        return data, manifest
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError('Demo report or provenance is missing/invalid. Run python -m scripts.reports.') from error


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    result = build_reports(args.root)
    print(f"Generated {len(result['artifacts'])} traceable synthetic demo reports.")
