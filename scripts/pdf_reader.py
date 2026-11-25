"""Digital PDF reading. Python extracts and numbers every amount; the AI only says which token is which field."""
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
OVERLAP_PT = 10         # fallback column match tolerance, in PDF points.
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


@dataclass(frozen=True)
class Line:
    page: int
    y: float
    text: str
    chunks: tuple  # ((text, x0, x1), ...) left to right


def _page_lines(page, number):
    chunks = []

    def visit(text, cm, tm, font_dict, font_size):
        text = clean_spaces(text).strip()
        if text:
            x, y = tm[4] * cm[0] + cm[4], tm[5] * cm[3] + cm[5]
            width = len(text) * (font_size or 10) * abs(tm[0] or 1) * 0.5
            chunks.append((round(y, 1), x, x + width, text))
    page.extract_text(visitor_text=visit)
    rows = {}
    for y, x0, x1, text in chunks:
        rows.setdefault(y, []).append((text, x0, x1))
    return [Line(number, y, ' '.join(c[0] for c in sorted(parts, key=lambda c: c[1])),
                 tuple(sorted(parts, key=lambda c: c[1]))) for y, parts in sorted(rows.items(), reverse=True)]


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
                    tokens.append(Token(f'T{len(tokens) + 1}', value, line.page, line.text, x0, x1, line.y))
    return tokens, lines


def _row_position(token, tokens):
    row = [t for t in tokens if t.page == token.page and t.y == token.y]
    return row.index(token), len(row)


def _header_ok(field, token, tokens, lines):
    if label_matches(field, token.line):
        return True
    above = [line for line in lines if line.page == token.page and line.y > token.y]
    above.sort(key=lambda line: line.y)
    index, count = _row_position(token, tokens)
    if count > 1:
        header = next((line for line in above if len(line.chunks) == count), None)
        if header is not None:
            return label_matches(field, header.chunks[index][0])
    for line in above:
        for text, x0, x1 in line.chunks:
            if x0 - OVERLAP_PT <= token.x1 and token.x0 <= x1 + OVERLAP_PT and label_matches(field, text):
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


def build_prompt(tokens):
    fields = '\n'.join(f'- {field}: {hint}' for field, hint in FIELD_HINTS.items())
    listing = '\n'.join(f'{t.id} | p{t.page} | "{t.line[:120]}"' for t in tokens)
    return ('You locate values in a construction payment statement (décompte) PDF.\n'
            'Below, every amount printed in the PDF has an id, with its page and the full line it is on.\n'
            'For each field return the id of the amount that holds its value (for example "T7"), or null if you '
            'are not sure. Return ids only. Do not compute, add, or change any number. '
            'For project and number, return the project name and the statement number as printed, or null.\n'
            f'Fields:\n{fields}\n\nAmounts:\n{listing}')


def read_pdf_with_ai(data, api_key, ask=llm.ask_json):
    tokens, _ = extract_tokens(data)
    if len(tokens) < MIN_TOKENS:
        raise ValueError('NO_TEXT')
    answer = ask(build_prompt(tokens), SCHEMA, api_key)
    if not isinstance(answer, dict):
        return None
    return trace_pdf(data, answer)
