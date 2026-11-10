from io import BytesIO
import pytest
from openpyxl import Workbook


@pytest.fixture
def make_workbook():
    def make(number=1, previous=0, cumulative=100, works=100, retention=10,
             net=90, vat=18, ttc=108, layout=1, project='DEMO PROJECT',
             cover=False, title='DP', metadata=True, formula=False):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = title
        if metadata:
            sheet['A1'] = f'{project} — DECOMPTE D{number}'
        row = 37 if layout == 1 else 39
        sheet[f'A{row+2}'] = 'Retenue de Garantie'
        for address, value in {f'B{row}': cumulative, f'C{row}': previous, f'D{row}': works,
                               f'D{row+2}': retention, f'D{row+7}': net,
                               f'D{row+8}': vat, f'D{row+9}': ttc}.items():
            sheet[address] = value
        if formula:
            sheet[f'D{row+9}'] = f'=D{row+7}+D{row+8}'
        if cover:
            workbook.create_sheet('Cover', 0)
        buffer = BytesIO()
        workbook.save(buffer)
        workbook.close()
        return buffer.getvalue()
    return make
