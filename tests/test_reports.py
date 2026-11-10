import importlib
import shutil
from pathlib import Path
import pandas as pd
import pytest
from scripts.policy import ROOT
from scripts.reports import build_reports, verified_report


@pytest.fixture
def project(tmp_path):
    for filename in ['project_config.json', 'scripts', 'demo_decomptes']:
        source = ROOT / filename
        if source.is_dir(): shutil.copytree(source, tmp_path / filename, ignore=shutil.ignore_patterns('__pycache__'))
        else: shutil.copy(source, tmp_path / filename)
    return tmp_path


def test_generated_reports_reconcile_to_sources(project):
    manifest = build_reports(project)
    assert len(manifest['artifacts']) == 6
    data, _ = verified_report('financial_audit.xlsx', project)
    from io import BytesIO
    continuity = pd.read_excel(BytesIO(data))
    assert (continuity['Status'] == 'OK').all()
    assert (continuity['Difference DH'] == 0).all()
    assert continuity.iloc[1]['Declared previous HT'] == 1120000
    taxes = pd.read_excel(project / 'outputs/verification_retention_tva.xlsx')
    assert taxes['TTC déclaré'].sum() == 2970000
    technical = pd.read_excel(project / 'outputs/audit_technique_valide.xlsx', sheet_name='Controle_D3_D4')
    assert (technical['Statut validation'] != 'OK').sum() == 3
    assert technical.loc[technical['Statut validation'] != 'OK', 'Review reason'].notna().all()


def test_changed_source_invalidates_report(project):
    build_reports(project)
    path = project / 'demo_decomptes/DEMO_DP_N3.xlsx'
    path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='Source data'):
        verified_report('financial_audit.xlsx', project)


def test_changed_report_is_not_served(project):
    build_reports(project)
    path = project / 'outputs/financial_audit.xlsx'
    path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='integrity'):
        verified_report(path.name, project)


def test_missing_report_has_actionable_error(project):
    with pytest.raises(ValueError, match='python -m scripts.reports'):
        verified_report('financial_audit.xlsx', project)


def test_importing_generator_does_not_write_files(monkeypatch):
    def forbidden(*a, **k): raise AssertionError('Import attempted a filesystem mutation')
    monkeypatch.setattr(Path, 'mkdir', forbidden)
    import generate_demo_decomptes
    importlib.reload(generate_demo_decomptes)


def test_reading_view_keeps_machine_readable_tables_and_financial_totals(project):
    from openpyxl import load_workbook
    build_reports(project)
    path = project / 'outputs/rapport_audit_financier.xlsx'
    workbook = load_workbook(path)
    assert workbook.active.title == 'Report Overview'
    assert workbook.worksheets[0].title == 'Continuity_Checks'
    assert workbook['Report Overview']['A9'].value == 2750000
    assert workbook['Report Overview']['E9'].value == 495000
    assert workbook['Report Overview']['I9'].value == 2970000
    assert workbook['_ChartData'].sheet_state == 'hidden'
    assert workbook['Report Overview']['A30'].hyperlink.target == "#'Continuity_Checks'!A1"
    workbook.close()
    assert len(pd.read_excel(path)) == 3


def test_technical_cover_does_not_hide_review_flags(project):
    from openpyxl import load_workbook
    build_reports(project)
    workbook = load_workbook(project / 'outputs/audit_technique_valide.xlsx')
    cover = workbook['Report Overview']
    assert cover['A9'].value == 6
    assert cover['E9'].value == 3
    assert cover['I9'].value == 3
    assert cover['A14'].value == 'REVIEW REQUIRED'
    workbook.close()
