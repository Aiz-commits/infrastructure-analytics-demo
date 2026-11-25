"""Digital PDF reading. Python extracts and numbers every amount; the AI only says which token is which field."""
import re
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from pypdf import PdfReader
from . import llm
from .ai_reader import FIELD_HINTS
from .controller_checks import FIELDS, SOURCE_PDF_TEXT, ReadValue, Statement, known_projects
from .doc_text import AMOUNT_PATTERN, clean_spaces, label_matches, normalize, normalize_identity, parse_amount_text
from .documents import MAX_PDF_PAGES

MIN_TOKENS = 3          # fewer printed amounts than this = no usable text (a scan): switch to vision.
OVERLAP_CHARS = 2       # fallback column match tolerance, in layout-text characters.
SCHEMA = {'type': 'object', 'properties': {f: {'type': 'string', 'nullable': True}
                                           for f in FIELDS + ('project', 'number')}}


@dataclass(frozen=True)
class Token:
    id: str
    value: Decimal
    page: int
    line: str
    x0: float
    x1: float
    y: float
    text: str = ''  # the amount exactly as printed


@dataclass(frozen=True)
class Line:
    page: int
    y: float
    text: str
    chunks: tuple  # ((text, x0, x1), ...) left to right


_CELL = re.compile(r'\S+(?: \S+)*')  # 2+ spaces end a cell, so table cells never merge into one number.


def _page_lines(page, number):
    """Lines from pypdf's layout mode, which keeps the page's horizontal spacing. Positions are character
    columns; y is minus the line index, so a line above has a larger y."""
    text = clean_spaces(page.extract_text(extraction_mode='layout'))
    lines = []
    for index, raw in enumerate(row for row in text.splitlines() if row.strip()):
        chunks = tuple((m.group(), float(m.start()), float(m.end())) for m in _CELL.finditer(raw))
        lines.append(Line(number, float(-index), ' '.join(c[0] for c in chunks), chunks))
    return lines


def extract_tokens(data):
    """Every amount on the first MAX_PDF_PAGES pages, ids T1.. in reading order, plus the text lines."""
    reader = PdfReader(BytesIO(data))
    lines, tokens = [], []
    for number, page in enumerate(reader.pages[:MAX_PDF_PAGES], start=1):
        lines += _page_lines(page, number)
    for line in lines:
        for text, x0, x1 in line.chunks:
            for match in AMOUNT_PATTERN.finditer(text):
                value = parse_amount_text(match.group())
                if value is not None:
                    tokens.append(Token(f'T{len(tokens) + 1}', value, line.page, line.text, x0, x1, line.y,
                                        match.group()))
    return tokens, lines


def _row_position(token, tokens):
    row = [t for t in tokens if t.page == token.page and t.y == token.y]
    return row.index(token), len(row)


def _lines_above(token, lines):
    return sorted((line for line in lines if line.page == token.page and line.y > token.y), key=lambda line: line.y)


def _all_amounts(line):
    return all(parse_amount_text(text) is not None for text, _, _ in line.chunks)


def column_header(token, tokens, lines):
    """Table row (every piece on the line is an amount, 2+ of them): the k-th label of the nearest text-only
    line above with the same number of pieces. Any other line has no column header."""
    index, count = _row_position(token, tokens)
    row = next((line for line in lines if line.page == token.page and line.y == token.y), None)
    if count < 2 or row is None or len(row.chunks) != count or not _all_amounts(row):
        return None
    header = next((line for line in _lines_above(token, lines) if len(line.chunks) == count
                   and not any(parse_amount_text(text) is not None for text, _, _ in line.chunks)), None)
    return header.chunks[index][0] if header is not None else None


def _header_ok(field, token, tokens, lines):
    if label_matches(field, token.line):
        return True
    header = column_header(token, tokens, lines)
    if header is not None:
        return label_matches(field, header)
    for line in _lines_above(token, lines):
        for text, x0, x1 in line.chunks:
            if x0 - OVERLAP_CHARS <= token.x1 and token.x0 <= x1 + OVERLAP_CHARS and label_matches(field, text):
                return True
    return False


def _cell(token):
    return f'page {token.page} · line "{token.line[:40]}"'


def trace_pdf(data, answer):
    """Trace rule, PDF version: only values Python parsed from its own tokens are used."""
    tokens, lines = extract_tokens(data)
    by_id = {t.id: t for t in tokens}
    values = {}
    for field in FIELDS:
        token_id = answer.get(field)
        token = by_id.get(token_id.strip().upper()) if isinstance(token_id, str) else None
        if token is None:
            values[field] = ReadValue(field, None, None, SOURCE_PDF_TEXT)
        else:
            values[field] = ReadValue(field, token.value, _cell(token), SOURCE_PDF_TEXT,
                                      not _header_ok(field, token, tokens, lines))
    project, number = normalize_identity(_text(answer.get('project')), _text(answer.get('number')), known_projects())
    full_text = normalize(' '.join(line.text for line in lines))
    if project and project not in known_projects() and normalize(project) not in full_text:
        project = ''
    return Statement(project, number, values)


def _text(value):
    return value if isinstance(value, (str, int)) and not isinstance(value, bool) else None


def _listing(token, tokens, lines):
    header = column_header(token, tokens, lines)
    column = f' | column "{header}"' if header else ''
    return f'{token.id} | p{token.page} | amount "{token.text}"{column} | line "{token.line[:120]}"'


def build_prompt(tokens, lines):
    fields = '\n'.join(f'- {field}: {hint}' for field, hint in FIELD_HINTS.items())
    listing = '\n'.join(_listing(t, tokens, lines) for t in tokens)
    return ('You locate values in a construction payment statement (décompte) PDF.\n'
            'Below, every number printed in the PDF has an id, with its page, the number as printed, its table '
            'column header when it sits in a table row, and the full line it is on. Small numbers such as rates '
            '(20 in "TVA 20%") are listed too; pick the money amount, not the rate.\n'
            'For each field return the id of the amount that holds its value (for example "T7"), or null if you '
            'are not sure. Return ids only. Do not compute, add, or change any number. '
            'For project and number, return the project name and the statement number as printed, or null.\n'
            f'Fields:\n{fields}\n\nAmounts:\n{listing}')


def read_pdf_with_ai(data, api_key, ask=llm.ask_json):
    tokens, lines = extract_tokens(data)
    if len(tokens) < MIN_TOKENS:
        raise ValueError('NO_TEXT')
    answer = ask(build_prompt(tokens, lines), SCHEMA, api_key)
    if not isinstance(answer, dict):
        return None
    return trace_pdf(data, answer)
