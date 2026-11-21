"""AI-assisted reading of unknown layouts. The AI names cells; Python reads every value itself."""
import re
import unicodedata
from decimal import Decimal
from . import llm
from .controller_checks import FIELDS, SOURCE_AI, ReadValue, Statement
from .decompte_extractor import identity, statement_number
from .policy import amount
from .workbooks import MAX_COLUMNS, open_workbook

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_AI_CELLS = 2000
AI_FIELDS = FIELDS + ('project', 'number')
LABEL_KEYWORDS = {'works': ('travaux', 'works'), 'previous': ('precedent', 'anterieur', 'previous'),
                  'cumulative': ('cumul', 'cumulative'), 'retention': ('retenue', 'retention'),
                  'net': ('net',), 'vat': ('tva', 'vat'), 'ttc': ('ttc',)}
_ADDRESS = re.compile(r'^([A-Z]{1,3})([1-9][0-9]{0,4})$')
SCHEMA = {'type': 'object', 'properties': {f: {'type': 'string', 'nullable': True} for f in AI_FIELDS}}
FIELD_HINTS = {'works': 'works executed this month, excluding tax (HT)',
               'previous': 'previous cumulative works HT (from the last statement)',
               'cumulative': 'current cumulative works HT', 'retention': 'retention / guarantee holdback amount',
               'net': 'net amount HT after retention', 'vat': 'VAT (TVA) amount', 'ttc': 'total including tax (TTC)',
               'project': 'project name or identifier', 'number': 'statement (décompte) number'}


def _sheet_cells(data):
    """Non-empty cells of the first sheet as {address: value}, bounded."""
    workbook = open_workbook(data)
    try:
        sheet = workbook.worksheets[0]
        cells = {}
        for row in sheet.iter_rows(max_col=MAX_COLUMNS):
            for cell in row:
                if cell.value is None or (isinstance(cell.value, str) and not cell.value.strip()):
                    continue
                cells[cell.coordinate] = cell.value
                if len(cells) > MAX_AI_CELLS:
                    raise ValueError(f'Worksheet has more than {MAX_AI_CELLS} non-empty cells; AI reading is limited.')
        try:
            project, number = identity(sheet)
        except ValueError:
            project, number = '', None
        return cells, project, number
    finally:
        workbook.close()


def cell_text(data):
    cells, _, _ = _sheet_cells(data)
    return '\n'.join(f'{address}: {value}' for address, value in cells.items())


def _normalize(text):
    text = unicodedata.normalize('NFKD', str(text))
    return ''.join(ch for ch in text if not unicodedata.combining(ch)).casefold()


def _split(address):
    match = _ADDRESS.match(address) if isinstance(address, str) else None
    return (match.group(1), int(match.group(2))) if match else None


def _label_ok(field, address, cells):
    column, row = _split(address)
    labels = [value for key, value in cells.items() if isinstance(value, str)
              and ((_split(key)[1] == row) or (_split(key)[0] == column and _split(key)[1] < row))]
    for label in labels:
        text = _normalize(label)
        hit = any(re.search(rf'\b{word}', text) for word in LABEL_KEYWORDS[field])
        if field == 'cumulative' and any(re.search(rf'\b{w}', text) for w in LABEL_KEYWORDS['previous']):
            hit = False
        if hit:
            return True
    return False


def _number_value(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        return amount(value)
    except ValueError:
        return None


def trace(data, cells_by_field):
    """Trace rule: only values Python reads from the named cells are used. Bad cells become 'not found'."""
    cells, project, number = _sheet_cells(data)
    values = {}
    for field in FIELDS:
        address = cells_by_field.get(field)
        address = address.strip().upper() if isinstance(address, str) else None
        value = _number_value(cells.get(address)) if address and _split(address) else None
        if value is None:
            values[field] = ReadValue(field, None, None, SOURCE_AI)
        else:
            values[field] = ReadValue(field, value, address, SOURCE_AI, not _label_ok(field, address, cells))
    if not project:
        raw = cells.get(str(cells_by_field.get('project') or '').strip().upper())
        project = raw.strip()[:120] if isinstance(raw, str) else ''
    if number is None:
        raw = cells.get(str(cells_by_field.get('number') or '').strip().upper())
        if isinstance(raw, float) and raw.is_integer():
            raw = int(raw)
        try:
            number = None if raw is None or isinstance(raw, bool) else statement_number(raw)
        except ValueError:
            number = None
    return Statement(project, number, values)


def build_prompt(text):
    fields = '\n'.join(f'- {field}: {hint}' for field, hint in FIELD_HINTS.items())
    return ('You locate values in a construction payment statement (décompte) spreadsheet.\n'
            'Below are the non-empty cells of the first sheet as "ADDRESS: value".\n'
            'For each field, return the address of the cell that holds its value (for example "H15"), '
            'or null if you cannot find it. Return addresses only. Do not compute, add, or change any number.\n'
            f'Fields:\n{fields}\n\nCells:\n{text}')


def read_with_ai(data, api_key, ask=llm.ask_json):
    answer = ask(build_prompt(cell_text(data)), SCHEMA, api_key)
    if not isinstance(answer, dict):
        return None
    return trace(data, answer)
