"""Upload type by content (not by name) and the public-site limits for each type."""
from io import BytesIO
from pypdf import PdfReader
from .ai_reader import MAX_UPLOAD_BYTES

MAX_PDF_BYTES = 2 * 1024 * 1024
MAX_PDF_PAGES = 3
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MIME = {'pdf': 'application/pdf', 'jpeg': 'image/jpeg', 'png': 'image/png'}
_MAGIC = (('xlsx', b'PK\x03\x04'), ('pdf', b'%PDF-'), ('jpeg', b'\xff\xd8\xff'), ('png', b'\x89PNG\r\n\x1a\n'))


def detect_kind(data):
    for kind, magic in _MAGIC:
        if data.startswith(magic):
            return kind
    raise ValueError('Unsupported file. Upload an .xlsx, .pdf, .jpg or .png décompte.')


def check_limits(kind, data):
    if kind == 'xlsx' and len(data) > MAX_UPLOAD_BYTES:
        raise ValueError('This file is larger than 2 MB. The AI Controller accepts files up to 2 MB.')
    if kind in ('jpeg', 'png') and len(data) > MAX_IMAGE_BYTES:
        raise ValueError('This photo is larger than 5 MB. The AI Controller accepts photos up to 5 MB.')
    if kind != 'pdf':
        return
    if len(data) > MAX_PDF_BYTES:
        raise ValueError('This PDF is larger than 2 MB. The AI Controller accepts PDFs up to 2 MB.')
    try:
        reader = PdfReader(BytesIO(data))
        encrypted = reader.is_encrypted
        pages = 0 if encrypted else len(reader.pages)
    except Exception as error:  # pypdf raises many types on broken files; all mean "unreadable".
        raise ValueError('This PDF cannot be opened. It may be damaged.') from error
    if encrypted:
        raise ValueError('This PDF is protected by a password. Upload an unprotected copy.')
    if pages > MAX_PDF_PAGES:
        raise ValueError(f'This PDF has {pages} pages. The AI Controller reads PDFs of up to {MAX_PDF_PAGES} pages.')
    if pages == 0:
        raise ValueError('This PDF has no pages.')
