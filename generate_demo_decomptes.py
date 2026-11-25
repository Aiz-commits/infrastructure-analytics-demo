"""Create synthetic examples only when explicitly invoked, never on import."""
import argparse
import io
import json
import random
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from openpyxl import Workbook
from scripts.controller_checks import FIELDS
from scripts.policy import amount, expected_amounts, load_policy

MONTHLY_WORKS = [480000, 640000, 810000, 820000]


def generate_demo_decomptes(folder, policy=None):
    policy = policy or load_policy()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    cumulative = Decimal('0.00')
    paths = []
    for number, monthly in enumerate(MONTHLY_WORKS, start=1):
        works, previous = amount(monthly), cumulative
        cumulative = amount(cumulative + works)
        expected = expected_amounts(works, cumulative, previous, policy)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'DP'
        sheet['A1'] = f'DEMO PROJECT — DECOMPTE D{number}'
        sheet['A2'] = 'SYNTHETIC DATA — FOR DEMONSTRATION ONLY'
        sheet['A3'], sheet['B3'] = 'Project ID', 'DEMO PROJECT'
        sheet['A4'], sheet['B4'] = 'Statement number', number
        sheet['A39'] = 'Retenue de Garantie'
        for cell, value in {'B37': cumulative, 'C37': previous, 'D37': works,
                            'D39': expected['Retention'], 'D44': expected['Net HT'],
                            'D45': expected['VAT'], 'D46': expected['TTC']}.items():
            sheet[cell] = float(value)
        path = folder / f'DEMO_DP_N{number}.xlsx'
        workbook.save(path)
        workbook.close()
        paths.append(path)
    return paths


NEW_LAYOUT_ROWS = [('works', 'Travaux du mois HT'), ('previous', 'Cumul précédent HT'),
                   ('cumulative', 'Cumul actuel HT'), ('retention', 'Retenue de garantie 10%'),
                   ('net', 'Net HT'), ('vat', 'TVA 20%'), ('ttc', 'Total TTC')]


def controller_example_values(policy):
    """D5 with exactly two planted problems: a 12,300 DH continuity gap and +1,000 DH VAT."""
    d4_cumulative = amount(sum(MONTHLY_WORKS))
    works = amount(900000)
    previous = amount(d4_cumulative - Decimal('12300.00'))
    cumulative = amount(previous + works)
    expected = expected_amounts(works, cumulative, previous, policy)
    vat = amount(expected['VAT'] + Decimal('1000.00'))
    return {'works': works, 'previous': previous, 'cumulative': cumulative,
            'retention': expected['Retention'], 'net': expected['Net HT'], 'vat': vat,
            'ttc': amount(expected['Net HT'] + vat)}


TABLE_HEADERS = (('cumulative', 'Cumul actuel HT'), ('previous', 'Cumul précédent HT'), ('works', 'Travaux du mois HT'))
SUMMARY_LINES = (('retention', 'Retenue de garantie 10%'), ('net', 'Net HT'), ('vat', 'TVA 20%'), ('ttc', 'Total TTC'))
DOCUMENT_HEADER = ('DEMO PROJECT - DECOMPTE D5', 'SYNTHETIC DATA - FOR DEMONSTRATION ONLY',
                   'Projet : DEMO PROJECT     Décompte n° 5')


def french_amount(value):
    return f'{value:,.2f}'.replace(',', ' ').replace('.', ',')


def draw_d5_pdf(values):
    """The D5 statement as a one-page French PDF: a 3-column table row, then one labelled line per amount."""
    from fpdf import FPDF
    pdf = FPDF(format='A4')
    pdf.set_creation_date(datetime(2026, 11, 25, tzinfo=timezone.utc))
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_xy(15, 20)
    pdf.cell(180, 8, DOCUMENT_HEADER[0])
    pdf.set_font('Helvetica', size=10)
    for row, text in enumerate(DOCUMENT_HEADER[1:], start=1):
        pdf.set_xy(15, 20 + 8 * row)
        pdf.cell(180, 8, text)
    pdf.set_xy(15, 60)
    for _, label in TABLE_HEADERS:
        pdf.cell(60, 8, label)
    pdf.set_xy(15, 68)
    for field, _ in TABLE_HEADERS:
        pdf.cell(60, 8, french_amount(values[field]), align='R')
    for row, (field, label) in enumerate(SUMMARY_LINES):
        pdf.set_xy(15, 84 + 9 * row)
        pdf.cell(120, 8, label)
        pdf.cell(60, 8, french_amount(values[field]), align='R')
    return bytes(pdf.output())


def draw_d5_photo(values):
    """The same page as a phone photo: paper tint, a slight tilt and a soft shadow. Seeded, so reproducible."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    rng = random.Random(5)
    page = Image.new('RGB', (1240, 900), (250, 247, 238))
    draw = ImageDraw.Draw(page)
    font, bold = ImageFont.load_default(size=30), ImageFont.load_default(size=40)
    # Pillow's built-in font has no accented letters, so the photo text is drawn without accents.
    plain = lambda text: unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    draw.text((90, 110), DOCUMENT_HEADER[0], fill=(25, 25, 30), font=bold)
    for row, text in enumerate(DOCUMENT_HEADER[1:], start=1):
        draw.text((90, 110 + 55 * row), plain(text), fill=(40, 40, 45), font=font)
    for column, (field, label) in enumerate(TABLE_HEADERS):
        x = 90 + 360 * column
        draw.text((x, 360), plain(label), fill=(30, 30, 35), font=font)
        draw.text((x + 330, 410), french_amount(values[field]), fill=(20, 20, 25), font=font, anchor='ra')
    for row, (field, label) in enumerate(SUMMARY_LINES):
        y = 520 + 60 * row
        draw.text((90, y), plain(label), fill=(30, 30, 35), font=font)
        draw.text((1150, y), french_amount(values[field]), fill=(20, 20, 25), font=font, anchor='ra')
    for _ in range(4000):
        x, y = rng.randrange(page.width), rng.randrange(page.height)
        shade = rng.randrange(225, 250)
        page.putpixel((x, y), (shade, shade - 3, shade - 10))
    photo = Image.new('RGB', (1400, 1060), (92, 84, 74))
    shadow = Image.new('L', page.size, 110).filter(ImageFilter.GaussianBlur(4))
    photo.paste((40, 36, 30), (98, 92), shadow)
    photo.paste(page, (80, 70))
    photo = photo.rotate(1.2, resample=Image.Resampling.BICUBIC, fillcolor=(92, 84, 74))
    buffer = io.BytesIO()
    photo.save(buffer, 'JPEG', quality=85)
    return buffer.getvalue()


def generate_document_examples(folder, policy=None):
    """The D5 statement as a digital PDF and a phone photo, each with its saved example answer."""
    from scripts.pdf_reader import extract_tokens
    values = controller_example_values(policy or load_policy())
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    pdf_data = draw_d5_pdf(values)
    tokens, _ = extract_tokens(pdf_data)
    pdf_answer = {field: next(t.id for t in tokens if t.value == values[field]) for field in FIELDS}
    labels = dict(TABLE_HEADERS + SUMMARY_LINES)
    photo_answer = {field: {'value': french_amount(values[field]), 'label': labels[field]} for field in FIELDS}
    identity = {'project': 'DEMO PROJECT', 'number': '5'}
    files = {'DEMO_DP_N5.pdf': pdf_data, 'DEMO_DP_N5_PHOTO.jpg': draw_d5_photo(values),
             'DEMO_DP_N5.pdf.answer.json': _json_bytes({**pdf_answer, **identity}),
             'DEMO_DP_N5_PHOTO.jpg.answer.json': _json_bytes({**photo_answer, **identity})}
    paths = []
    for name, data in files.items():
        paths.append(folder / name)
        paths[-1].write_bytes(data)
    return paths


def _json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def _identity_sheet(workbook, title):
    sheet = workbook.active
    sheet.title = title
    sheet['A1'] = 'DEMO PROJECT — DECOMPTE D5'
    sheet['A2'] = 'SYNTHETIC DATA — FOR DEMONSTRATION ONLY'
    sheet['A3'], sheet['B3'] = 'Project ID', 'DEMO PROJECT'
    sheet['A4'], sheet['B4'] = 'Statement number', 5
    return sheet


def generate_controller_examples(folder, policy=None):
    values = controller_example_values(policy or load_policy())
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    workbook = Workbook()
    sheet = _identity_sheet(workbook, 'DP')
    sheet['A39'] = 'Retenue de Garantie'
    for cell, field in {'B37': 'cumulative', 'C37': 'previous', 'D37': 'works', 'D39': 'retention',
                        'D44': 'net', 'D45': 'vat', 'D46': 'ttc'}.items():
        sheet[cell] = float(values[field])
    paths.append(folder / 'DEMO_DP_N5.xlsx')
    workbook.save(paths[-1])
    workbook.close()
    workbook = Workbook()
    sheet = _identity_sheet(workbook, 'Situation')
    sheet['F8'], sheet['H8'] = 'Désignation', 'Montant (DH)'
    for row, (field, label) in enumerate(NEW_LAYOUT_ROWS, start=10):
        sheet[f'F{row}'], sheet[f'H{row}'] = label, float(values[field])
    paths.append(folder / 'DEMO_DP_N5_NEW_LAYOUT.xlsx')
    workbook.save(paths[-1])
    workbook.close()
    return paths


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=root / 'demo_decomptes')
    parser.add_argument('--controller-dir', type=Path, nargs='?', const=root / 'controller_examples', default=None,
                        help='Write only the AI Controller examples (never into demo_decomptes).')
    args = parser.parse_args()
    if args.controller_dir is not None:
        created = generate_controller_examples(args.controller_dir) + generate_document_examples(args.controller_dir)
    else:
        created = generate_demo_decomptes(args.output_dir)
    for path in created:
        print(f'Created synthetic statement: {path.name}')
