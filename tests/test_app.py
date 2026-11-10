from unittest.mock import patch
import pytest
from streamlit.testing.v1 import AppTest
from streamlit.runtime.uploaded_file_manager import UploadedFile, UploadedFileRec
from scripts.policy import ROOT


def run_page(page, files=None, single=None):
    def uploader(*args, **kwargs):
        return files if kwargs.get('key') == 'multi_decompte_upload' else single
    with patch('streamlit.file_uploader', side_effect=uploader):
        app = AppTest.from_file(str(ROOT / 'app.py')).run(timeout=20)
        app.sidebar.radio[0].set_value(page).run(timeout=20)
    return app


def upload(name, data):
    return UploadedFile(UploadedFileRec(name, name, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', data), None)


@pytest.mark.parametrize('page', ['Overview', 'Financial Audit', 'Technical Monitoring', 'Document Analysis', 'Report Center'])
def test_pages_load(page):
    app = run_page(page)
    assert not app.exception
    assert not app.error


def test_missing_data_has_no_green_summary(make_workbook):
    app = run_page('Document Analysis', files=[upload('DP_N1.xlsx', make_workbook()),
        upload('DP_N2.xlsx', make_workbook(number=2, previous=None, cumulative=200))])
    assert not app.exception
    assert app.warning
    assert not app.success


def test_valid_upload_pair_has_green_summary(make_workbook):
    app = run_page('Document Analysis', files=[upload('DP_N1.xlsx', make_workbook()),
        upload('DP_N2.xlsx', make_workbook(number=2, previous=100, cumulative=200))])
    assert not app.exception
    assert any('All uploaded statements' in message.value for message in app.success)


def test_upload_page_independent_of_saved_reports():
    with patch('scripts.reports.verified_report', side_effect=ValueError('missing')):
        app = run_page('Document Analysis')
    assert not app.exception
    assert not app.error
    assert any('Excel Document Import' in heading.value for heading in app.header)


def test_missing_overview_report_does_not_crash():
    with patch('scripts.reports.verified_report', side_effect=ValueError('missing report')):
        app = run_page('Overview')
    assert not app.exception
    assert any('missing report' in message.value for message in app.error)
