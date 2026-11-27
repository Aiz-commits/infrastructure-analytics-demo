"""Phase 3 intake: one file's bytes -> a Statement, with the same reading paths as the Streamlit app.
No Streamlit here: the local API and the app's cached PDF/photo reader both use it."""
import hashlib
from dataclasses import dataclass
from .ai_reader import read_with_ai
from .controller_checks import (AI_SOURCES, EXAMPLES_DIR, HISTORY_DIR, SAVED_ANSWER_FILES, from_extractor,
                                load_saved_answer)
from .decompte_extractor import extract_decompte
from .documents import MIME, check_limits, detect_kind
from .pdf_reader import read_pdf_with_ai, trace_pdf
from .policy import load_policy
from .vision_reader import parse_vision_answer, read_with_vision
from .workbooks import workbook_bytes

UNAVAILABLE = 'AI reading is unavailable right now. Try again later.'
NO_VALUES = 'No décompte values found in this file.'


class IntakeError(ValueError):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class IntakeRead:
    statement: object
    read_method: str
    needs_confirmation: bool


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def bundled_hashes():
    """SHA-256 of every bundled example file: only these may reach the public history."""
    paths = [*EXAMPLES_DIR.glob('*.xlsx'), *EXAMPLES_DIR.glob('*.pdf'), *EXAMPLES_DIR.glob('*.jpg'),
             *HISTORY_DIR.glob('*.xlsx')]
    return frozenset(_sha256(path.read_bytes()) for path in paths)


def saved_answer_for(data):
    """(bundled file name, saved answer) when these bytes are a bundled PDF/photo example, whatever the file name."""
    digest = _sha256(data)
    for name in SAVED_ANSWER_FILES:
        path = EXAMPLES_DIR / name
        if path.exists() and _sha256(path.read_bytes()) == digest:
            answer = load_saved_answer(name)
            return (name, answer) if answer is not None else None
    return None


def read_document_with_ai(data, kind, api_key):
    """Live PDF/photo read. A PDF without usable text (a scan) goes to vision. -> (statement or None, method)."""
    if kind == 'pdf':
        try:
            return read_pdf_with_ai(data, api_key), 'PDF text'
        except ValueError:  # NO_TEXT
            return read_with_vision(data, MIME['pdf'], api_key), 'AI vision'
    return read_with_vision(data, MIME[kind], api_key), 'AI vision'


def _read_workbook(data, api_key):
    try:
        workbook_bytes(data)
    except ValueError as error:
        raise IntakeError(str(error), 422) from error
    try:
        return from_extractor(extract_decompte(data, policy=load_policy())), 'fixed layout'
    except ValueError:
        pass
    if not api_key:
        raise IntakeError('Layout not supported by the fixed reader, and AI reading is off. ' + UNAVAILABLE, 503)
    try:
        statement = read_with_ai(data, api_key)
    except ValueError as error:
        raise IntakeError(str(error), 422) from error
    if statement is None:
        raise IntakeError(UNAVAILABLE, 503)
    return statement, 'found by AI'


def _read_document(data, kind, api_key):
    if api_key:
        statement, method = read_document_with_ai(data, kind, api_key)
        if statement is not None:
            return statement, method
    saved = saved_answer_for(data)
    if saved is None:
        raise IntakeError(UNAVAILABLE, 503)
    if kind == 'pdf':
        return trace_pdf(data, saved[1]), 'PDF text (saved)'
    return parse_vision_answer(saved[1], 'image'), 'AI vision (saved)'


def read_file(data, api_key):
    try:
        kind = detect_kind(data)
    except ValueError as error:
        raise IntakeError(str(error), 415) from error
    try:
        check_limits(kind, data)
    except ValueError as error:
        raise IntakeError(str(error), 413 if 'larger than' in str(error) else 422) from error
    statement, method = _read_workbook(data, api_key) if kind == 'xlsx' else _read_document(data, kind, api_key)
    if all(value.value is None for value in statement.values.values()):
        raise IntakeError(NO_VALUES, 422)
    needs = any(value.source in AI_SOURCES for value in statement.values.values())
    return IntakeRead(statement, method, needs)
