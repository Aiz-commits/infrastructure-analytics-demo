"""Test PDFs. The D5 PDF comes from the same drawing function as the bundled example."""
from io import BytesIO
from pypdf import PdfWriter
from generate_demo_decomptes import controller_example_values, draw_d5_pdf
from scripts.policy import load_policy


def d5_values():
    return controller_example_values(load_policy())


def d5_table_pdf():
    return draw_d5_pdf(d5_values())


def one_bt_row_pdf():
    """A row drawn like office/ERP exports: one BT block per row, cells placed with Td, whole-number amounts."""
    content = (b'BT /F1 10 Tf 50 700 Td (Cumul actuel HT) Tj 150 0 Td (Cumul precedent HT) Tj '
               b'150 0 Td (Travaux du mois HT) Tj ET\n'
               b'BT /F1 10 Tf 50 680 Td (3 637 700) Tj 150 0 Td (2 737 700) Tj 150 0 Td (900 000) Tj ET\n'
               b'BT /F1 10 Tf 50 640 Td (TVA 20%) Tj 300 0 Td (163 000) Tj ET\n')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R '
               b'/Resources << /Font << /F1 5 0 R >> >> >>',
               b'<< /Length %d >>\nstream\n' % len(content) + content + b'endstream',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    out, offsets = b'%PDF-1.4\n', []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b'%d 0 obj\n' % number + body + b'\nendobj\n'
    xref = len(out)
    out += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objects) + 1)
    out += b''.join(b'%010d 00000 n \n' % offset for offset in offsets)
    return out + b'trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objects) + 1, xref)


def blank_pdf(pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(595, 842)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
