from io import BytesIO
from zipfile import ZipFile
import pytest
from openpyxl import load_workbook
from scripts import workbooks


def test_invalid_archive_rejected():
    with pytest.raises(ValueError, match='valid XLSX'):
        workbooks.workbook_bytes(b'not zip')


def test_expanded_size_limit(make_workbook, monkeypatch):
    monkeypatch.setattr(workbooks, 'MAX_EXPANDED_BYTES', 100)
    with pytest.raises(ValueError, match='Expanded workbook'):
        workbooks.workbook_bytes(make_workbook())


def test_compressed_size_limit(make_workbook, monkeypatch):
    monkeypatch.setattr(workbooks, 'MAX_FILE_BYTES', 100)
    with pytest.raises(ValueError, match='10 MiB'):
        workbooks.workbook_bytes(make_workbook())


def test_row_limit(make_workbook):
    workbook = load_workbook(BytesIO(make_workbook()))
    workbook.active['A10001'] = 'too far'
    buffer = BytesIO(); workbook.save(buffer); workbook.close()
    with pytest.raises(ValueError, match='10,000-row'):
        workbooks.open_workbook(buffer.getvalue())


def test_sheet_count_limit(make_workbook):
    workbook = load_workbook(BytesIO(make_workbook()))
    for i in range(20): workbook.create_sheet(f'Cover{i}')
    buffer = BytesIO(); workbook.save(buffer); workbook.close()
    with pytest.raises(ValueError, match='20-worksheet'):
        workbooks.open_workbook(buffer.getvalue())


def test_preview_is_bounded(make_workbook):
    _, rows = workbooks.preview_workbook(make_workbook())
    assert len(rows) == 30
    assert all(len(row) <= 200 for row in rows)
