"""Photo and scanned-PDF reading. Gemini transcribes printed values; Python parses them; a human must confirm."""
from . import llm
from .ai_reader import FIELD_HINTS
from .controller_checks import FIELDS, SOURCE_VISION, ReadValue, Statement, known_projects
from .doc_text import label_matches, normalize_identity, parse_amount_text

_VALUE = {'type': 'object', 'nullable': True,
          'properties': {'value': {'type': 'string'}, 'label': {'type': 'string'}}}
SCHEMA = {'type': 'object', 'properties': {**{f: _VALUE for f in FIELDS},
                                           'project': {'type': 'string', 'nullable': True},
                                           'number': {'type': 'string', 'nullable': True}}}


def _text(value):
    return value if isinstance(value, str) else None


def parse_vision_answer(answer, cell_text):
    """Each value must parse as exactly one printed amount; anything else is 'not found', never guessed."""
    values = {}
    for field in FIELDS:
        item = answer.get(field) if isinstance(answer, dict) else None
        item = item if isinstance(item, dict) else {}
        value = parse_amount_text(_text(item.get('value')))
        label = _text(item.get('label')) or ''
        if value is None:
            values[field] = ReadValue(field, None, None, SOURCE_VISION)
        else:
            values[field] = ReadValue(field, value, cell_text, SOURCE_VISION, not label_matches(field, label))
    project, number = normalize_identity(_text(answer.get('project')), _text(answer.get('number')), known_projects())
    return Statement(project, number, values)


def build_prompt():
    fields = '\n'.join(f'- {field}: {hint}' for field, hint in FIELD_HINTS.items() if field in FIELDS)
    return ('This is a photo or scan of a construction payment statement (décompte).\n'
            'For each field, transcribe the amount exactly as printed (same digits, spaces and separators) and '
            'the printed label next to it. Do not compute, add, round, or correct any number. '
            'If you are not sure, return null for that field.\n'
            'Also return the project name and the statement number exactly as printed, or null.\n'
            f'Fields:\n{fields}')


def read_with_vision(data, mime_type, api_key, ask=llm.ask_json_file):
    answer = ask(build_prompt(), data, mime_type, SCHEMA, api_key)
    if not isinstance(answer, dict):
        return None
    return parse_vision_answer(answer, 'scanned PDF' if mime_type == 'application/pdf' else 'image')
