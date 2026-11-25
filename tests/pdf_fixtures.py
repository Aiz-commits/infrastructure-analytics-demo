"""Test PDFs. The D5 PDF comes from the same drawing function as the bundled example."""
from io import BytesIO
from pypdf import PdfWriter
from generate_demo_decomptes import controller_example_values, draw_d5_pdf
from scripts.policy import load_policy


def d5_values():
    return controller_example_values(load_policy())


def d5_table_pdf():
    return draw_d5_pdf(d5_values())


def blank_pdf(pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(595, 842)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
