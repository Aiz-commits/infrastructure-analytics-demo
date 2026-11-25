"""Printed amounts and labels shared by the PDF and photo readers. Python parses every number itself."""
import re
import unicodedata
from .policy import amount

LABEL_KEYWORDS = {'works': ('travaux', 'works'), 'previous': ('precedent', 'anterieur', 'previous'),
                  'cumulative': ('cumul', 'cumulative'), 'retention': ('retenue', 'retention'),
                  'net': ('net',), 'vat': ('tva', 'vat'), 'ttc': ('ttc',)}
# Thousands groups use ONE separator (space, dot or comma); two or more spaces end the amount.
_NUMBER = r'-?(?:\d{1,3}(?:[ .,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)'
AMOUNT_PATTERN = re.compile(rf'(?<![\d.,]){_NUMBER}(?![\d])')
_WHOLE = re.compile(rf'({_NUMBER})(?:\s*(?:DH|MAD))?', re.IGNORECASE)
_SPACES = str.maketrans({' ': ' ', ' ': ' ', ' ': ' '})


def clean_spaces(text):
    return str(text).translate(_SPACES)


def parse_amount_text(text):
    """One printed amount -> Decimal, or None. The final separator is decimal only with 1-2 digits after it."""
    if not isinstance(text, str):
        return None
    match = _WHOLE.fullmatch(clean_spaces(text).strip())
    if not match:
        return None
    number = match.group(1)
    decimal = re.search(r'[.,](\d{1,2})$', number)
    whole = number[:decimal.start()] if decimal else number
    digits = re.sub(r'[ .,]', '', whole) + ('.' + decimal.group(1) if decimal else '')
    try:
        return amount(digits)
    except ValueError:
        return None


def normalize(text):
    text = unicodedata.normalize('NFKD', str(text))
    return ''.join(ch for ch in text if not unicodedata.combining(ch)).casefold()


def label_matches(field, text):
    text = normalize(text)
    if field == 'cumulative' and any(re.search(rf'\b{w}', text) for w in LABEL_KEYWORDS['previous']):
        return False
    return any(re.search(rf'\b{word}', text) for word in LABEL_KEYWORDS[field])
