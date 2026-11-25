from io import BytesIO
import pytest
from pypdf import PdfWriter
from scripts.controller_checks import EXAMPLES_DIR
from scripts.documents import MAX_IMAGE_BYTES, MAX_PDF_BYTES, check_limits, detect_kind

JPEG = b'\xff\xd8\xff\xe0' + b'\0' * 20
PNG = b'\x89PNG\r\n\x1a\n' + b'\0' * 20


def blank_pdf(pages=1, password=None):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(595, 842)
    if password:
        writer.encrypt(password)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_detects_each_kind():
    assert detect_kind((EXAMPLES_DIR / 'DEMO_DP_N5.xlsx').read_bytes()) == 'xlsx'
    assert detect_kind(blank_pdf()) == 'pdf'
    assert detect_kind(JPEG) == 'jpeg'
    assert detect_kind(PNG) == 'png'


def test_unknown_bytes_rejected():
    with pytest.raises(ValueError, match=r'\.xlsx, \.pdf, \.jpg or \.png'):
        detect_kind(b'hello')


def test_fake_pdf_rejected_plainly():
    with pytest.raises(ValueError):
        check_limits('pdf', b'%PDF-1.7 garbage')


def test_encrypted_pdf_rejected():
    with pytest.raises(ValueError, match='password'):
        check_limits('pdf', blank_pdf(password='x'))


def test_pdf_page_limit():
    check_limits('pdf', blank_pdf(3))
    with pytest.raises(ValueError, match='3 pages'):
        check_limits('pdf', blank_pdf(4))


def test_size_limits():
    with pytest.raises(ValueError, match='2 MB'):
        check_limits('pdf', b'%PDF-' + b'0' * MAX_PDF_BYTES)
    with pytest.raises(ValueError, match='5 MB'):
        check_limits('jpeg', JPEG + b'0' * MAX_IMAGE_BYTES)
    with pytest.raises(ValueError, match='2 MB'):
        check_limits('xlsx', b'PK\x03\x04' + b'0' * (2 * 1024 * 1024))
    check_limits('png', PNG)
