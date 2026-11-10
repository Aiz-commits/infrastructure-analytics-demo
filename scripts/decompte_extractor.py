"""Read supported payment summaries and check explicit demonstration rules."""
import hashlib
import re
from decimal import Decimal
from .policy import amount, expected_amounts, load_policy
from .workbooks import open_workbook, workbook_bytes

MAX_STATEMENT_NUMBER = 10000


def statement_number(value):
    if isinstance(value, bool):
        raise ValueError('Invalid statement number.')
    text = str(value).strip()
    if not text.isascii() or not text.isdigit() or len(text) > 5:
        raise ValueError('Statement number must be an integer from 1 to 10000.')
    number = int(text)
    if not 1 <= number <= MAX_STATEMENT_NUMBER:
        raise ValueError('Statement number must be from 1 to 10000.')
    return number


def filename_number(filename):
    if len(filename) > 240:
        raise ValueError('Filename exceeds the 240-character limit.')
    match = re.search(r'(?:DP|DECOMPTE)[^\d]*?(\d+)', filename.upper())
    return statement_number(match.group(1)) if match else None


def identity(sheet):
    header = str(sheet['A1'].value or '').strip()
    match = re.fullmatch(r'(.+?)\s*[—–-]\s*DECOMPTE\s+D?(\d+)', header, re.IGNORECASE)
    header_number = statement_number(match.group(2)) if match else None
    number = statement_number(sheet['B4'].value) if sheet['A4'].value == 'Statement number' else header_number
    if header_number is not None and number != header_number:
        raise ValueError('Statement number conflicts with the source heading.')
    project = str(sheet['B3'].value or '').strip() if sheet['A3'].value == 'Project ID' else (match.group(1).strip() if match else '')
    if len(project) > 120:
        raise ValueError('Project identifier exceeds the supported length.')
    return project, number


def layout_row(sheet):
    if sheet['A39'].value == 'Retenue de Garantie':
        return 37
    if sheet['A41'].value == 'Retenue de Garantie':
        return 39
    return None


def extract_decompte(file, sheet_name=None, policy=None):
    policy = policy or load_policy()
    data = workbook_bytes(file)
    workbook = open_workbook(data)
    try:
        if sheet_name is not None:
            if sheet_name not in workbook.sheetnames:
                raise ValueError('Selected worksheet does not exist.')
            sheet = workbook[sheet_name]
        else:
            candidates = [sheet for sheet in workbook.worksheets
                          if sheet.title.upper().startswith('DP') and layout_row(sheet) is not None]
            if len(candidates) != 1:
                raise ValueError('Select exactly one supported DP summary worksheet; none or several were found.')
            sheet = candidates[0]
        row = layout_row(sheet)
        if row is None:
            raise ValueError('Unsupported statement layout on the selected worksheet.')
        project, number = identity(sheet)
        def cell(address):
            try:
                return amount(sheet[address].value)
            except ValueError as error:
                raise ValueError(f'{sheet.title}!{address}: missing or invalid amount. '
                                 'Formula cells need up-to-date results saved by a spreadsheet application.') from error
        works, cumulative = cell(f'D{row}'), cell(f'B{row}')
        raw_previous = sheet[f'C{row}'].value
        previous = cell(f'C{row}') if raw_previous is not None else (Decimal('0.00') if number == 1 else None)
        if any(value < 0 for value in (works, cumulative, previous) if value is not None):
            raise ValueError('Negative amounts/corrections require a separate policy and are unsupported by this demo.')
        declared = {key: cell(f'D{r}') for key, r in
                    [('Retention', row + 2), ('Net HT', row + 7), ('VAT', row + 8), ('TTC', row + 9)]}
        expected = expected_amounts(works, cumulative, previous, policy)
        differences = {key: abs(declared[key] - expected[key]) for key in declared}
        issues = [f'{key} differs from the configured rule' for key, diff in differences.items() if diff > policy.tolerance]
        if previous is not None and abs(cumulative - previous - works) > policy.tolerance:
            issues.append('Current cumulative HT does not equal previous cumulative HT plus works HT')
        # Check declared relationships as well as their independently expected values.
        if abs(declared['Net HT'] - (works - declared['Retention'])) > policy.tolerance:
            issues.append('Declared net HT does not reconcile with declared retention')
        if abs(declared['TTC'] - declared['Net HT'] - declared['VAT']) > policy.tolerance:
            issues.append('Declared TTC does not equal declared net HT plus VAT')
        if number == 1 and previous not in (None, Decimal('0')):
            issues.append('First statement has a nonzero opening balance')
        status = 'REVIEW REQUIRED' if issues else ('MISSING DATA' if previous is None else 'OK')
        if previous is None:
            issues.append('Previous cumulative HT is missing')
        return {
            'Project': project, 'Statement number': number, 'Source worksheet': sheet.title,
            'Works HT': works, 'Cumulative HT': cumulative, 'Previous cumulative HT': previous,
            **declared, **{f'Expected {key}': value for key, value in expected.items()},
            'Status': status, 'Maximum difference': max(differences.values()),
            'Validation issues': '; '.join(issues), 'Rule version': policy.version,
            'Source SHA256': hashlib.sha256(data).hexdigest(),
            'Source cells': f'{sheet.title}!B{row}:D{row};D{row+2};D{row+7}:D{row+9}',
            'Opening balance note': 'Blank opening balance treated as zero for statement 1' if raw_previous is None and number == 1 else ''
        }
    finally:
        workbook.close()
