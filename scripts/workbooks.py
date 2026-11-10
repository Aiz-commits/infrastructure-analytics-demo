"""Bounded, in-memory XLSX input handling. Never extracts ZIP members to disk."""
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile
from openpyxl import load_workbook

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_EXPANDED_BYTES = 50 * 1024 * 1024
MAX_BATCH_BYTES = 50 * 1024 * 1024
MAX_FILES = 20
MAX_ROWS = 10000
MAX_COLUMNS = 200
MAX_SHEETS = 20


def workbook_bytes(source):
    if isinstance(source, (str, Path)):
        with open(source, 'rb') as handle:
            data = handle.read(MAX_FILE_BYTES + 1)
    elif isinstance(source, bytes):
        data = source
    elif hasattr(source, 'getvalue'):
        data = source.getvalue()
    else:
        data = source.read(MAX_FILE_BYTES + 1)
    if not data or len(data) > MAX_FILE_BYTES:
        raise ValueError('Workbook must be nonempty and no larger than 10 MiB.')
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(entries) > 1024 or len(names) != len(set(names)):
                raise ValueError('Workbook contains too many or duplicate ZIP entries.')
            if sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES:
                raise ValueError('Expanded workbook exceeds the 50 MiB limit.')
            if any(entry.flag_bits & 1 for entry in entries):
                raise ValueError('Encrypted workbooks are unsupported.')
            if any('vbaproject' in name.lower() for name in names):
                raise ValueError('Macro-enabled workbooks are unsupported.')
            if not {'[Content_Types].xml', 'xl/workbook.xml'}.issubset(names):
                raise ValueError('File is not a supported XLSX workbook.')
    except BadZipFile as error:
        raise ValueError('File is not a valid XLSX workbook.') from error
    return data


def open_workbook(source, *, data_only=True):
    data = workbook_bytes(source)
    try:
        workbook = load_workbook(BytesIO(data), read_only=True, data_only=data_only, keep_links=False)
    except Exception as error:
        raise ValueError('Cannot parse workbook. Check its format and XML content.') from error
    if len(workbook.worksheets) > MAX_SHEETS:
        workbook.close()
        raise ValueError('Workbook exceeds the 20-worksheet limit.')
    for sheet in workbook.worksheets:
        if (sheet.max_row or 0) > MAX_ROWS or (sheet.max_column or 0) > MAX_COLUMNS:
            workbook.close()
            raise ValueError('Worksheet exceeds the 10,000-row or 200-column limit.')
    return workbook


def preview_workbook(data, sheet_name=None):
    workbook = open_workbook(data)
    try:
        names = workbook.sheetnames
        selected = sheet_name or names[0]
        if selected not in names:
            raise ValueError('Selected worksheet does not exist.')
        # Bound the iteration, including for workbooks with misleading dimensions.
        rows = list(workbook[selected].iter_rows(min_row=1, max_row=30, max_col=MAX_COLUMNS, values_only=True))
        return names, rows
    finally:
        workbook.close()
