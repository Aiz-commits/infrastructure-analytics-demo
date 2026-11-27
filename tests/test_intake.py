"""Phase 3 intake: file bytes -> statement, without Streamlit (used by the local API)."""
from decimal import Decimal
import pytest
from scripts import intake
from scripts.controller_checks import EXAMPLES_DIR, FIELDS, SOURCE_VISION, ReadValue, Statement
from scripts.intake import IntakeError, bundled_hashes, read_file, saved_answer_for


def test_fixed_layout_xlsx_needs_no_confirmation(make_workbook):
    read = read_file(make_workbook(number=3), None)
    assert read.read_method == 'fixed layout' and read.needs_confirmation is False
    assert read.statement.values['works'].value == Decimal('100.00')


def test_bundled_photo_offline_uses_saved_answer():
    read = read_file((EXAMPLES_DIR / 'DEMO_DP_N5_PHOTO.jpg').read_bytes(), None)
    assert read.read_method == 'AI vision (saved)' and read.needs_confirmation is True
    assert read.statement.values['works'].value is not None


def test_saved_answer_matched_by_content_not_name():
    data = (EXAMPLES_DIR / 'DEMO_DP_N5.pdf').read_bytes()
    assert saved_answer_for(data)[0] == 'DEMO_DP_N5.pdf'
    assert saved_answer_for(data + b'\n') is None
    assert read_file(data, None).read_method == 'PDF text (saved)'


def test_image_with_no_values_is_rejected(monkeypatch):
    empty = Statement('', None, {f: ReadValue(f, None, None, SOURCE_VISION) for f in FIELDS})
    monkeypatch.setattr(intake, 'read_with_vision', lambda data, mime, key: empty)
    with pytest.raises(IntakeError) as error:
        read_file(b'\x89PNG\r\n\x1a\n' + b'0' * 30000, 'key')
    assert error.value.status == 422 and str(error.value) == 'No décompte values found in this file.'


def test_unsupported_type_is_415():
    with pytest.raises(IntakeError) as error:
        read_file(b'hello, this is a text file', None)
    assert error.value.status == 415


def test_oversize_pdf_is_413():
    with pytest.raises(IntakeError) as error:
        read_file(b'%PDF-' + b'0' * (3 * 1024 * 1024), None)
    assert error.value.status == 413


def test_unknown_layout_without_ai_is_503(make_workbook):
    with pytest.raises(IntakeError) as error:
        read_file((EXAMPLES_DIR / 'DEMO_DP_N5_NEW_LAYOUT.xlsx').read_bytes(), None)
    assert error.value.status == 503


def test_ai_reader_failure_falls_back_or_503(monkeypatch):
    monkeypatch.setattr(intake, 'read_pdf_with_ai', lambda data, key: None)
    pdf = (EXAMPLES_DIR / 'DEMO_DP_N5.pdf').read_bytes()
    assert read_file(pdf, 'key').read_method == 'PDF text (saved)'  # bundled: saved answer
    monkeypatch.setattr(intake, 'read_with_vision', lambda data, mime, key: None)
    with pytest.raises(IntakeError) as error:
        read_file(b'\x89PNG\r\n\x1a\n' + b'1' * 30000, 'key')
    assert error.value.status == 503


def test_bundled_hashes_cover_examples_and_history():
    hashes = bundled_hashes()
    assert len(hashes) == 8  # 4 controller examples + DEMO_DP_N1..N4
    from hashlib import sha256
    assert sha256((EXAMPLES_DIR / 'DEMO_DP_N5.xlsx').read_bytes()).hexdigest() in hashes


def test_tiny_image_rejected_without_ai_call(monkeypatch):
    def never(*args):
        raise AssertionError('AI called for a logo-sized image')
    monkeypatch.setattr(intake, 'read_with_vision', never)
    with pytest.raises(IntakeError) as error:
        read_file(b'\x89PNG\r\n\x1a\n' + b'0' * 5000, 'key')
    assert error.value.status == 422 and 'too small' in str(error.value)
