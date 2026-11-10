"""Executive presentation without changing the machine-readable source tables."""
from datetime import datetime
from zoneinfo import ZoneInfo
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, DoughnutChart, Reference
from openpyxl.chart.series import DataPoint
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.page import PageMargins

NAVY, TEAL, INK, MUTED = '173247', '176B8A', '243B53', '526779'
PALE, LINE = 'F0F5F9', 'D9E5ED'
GREEN, GREEN_BG, AMBER, AMBER_BG = '176747', 'E6F4ED', '8B5600', 'FFF3D6'
MONEY = '#,##0.00;[Red](#,##0.00);"—"'
TITLES = {
    'financial_analysis.xlsx': 'Financial Overview',
    'financial_audit.xlsx': 'Financial Continuity Audit',
    'verification_calculs.xlsx': 'Financial Calculation Verification',
    'verification_retention_tva.xlsx': 'Retention, VAT & TTC Audit',
    'rapport_audit_financier.xlsx': 'Consolidated Financial Audit',
    'audit_technique_valide.xlsx': 'Technical Quantity Audit',
}


def page(sheet, landscape=True):
    sheet.sheet_view.showGridLines = False
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.sheet_properties.tabColor = TEAL
    sheet.page_setup.orientation = 'landscape' if landscape else 'portrait'
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth, sheet.page_setup.fitToHeight = 1, 0
    sheet.page_margins = PageMargins(left=.3, right=.3, top=.5, bottom=.5, header=.2, footer=.2)
    sheet.oddHeader.center.text = 'Infrastructure Analytics | SYNTHETIC DEMO'
    sheet.oddHeader.center.size = 9
    sheet.oddFooter.left.text = 'Preliminary screening — source verification required'
    sheet.oddFooter.left.size = 8
    sheet.oddFooter.right.text = 'Page &P of &N'
    sheet.oddFooter.right.size = 8


def detail(sheet, number):
    page(sheet)
    sheet.freeze_panes = 'B2'
    sheet.print_title_rows, sheet.print_area = '1:1', sheet.dimensions
    sheet.row_dimensions[1].height = 44
    headers = [cell.value for cell in sheet[1]]
    for cell in sheet[1]:
        cell.font = Font(name='Calibri', size=10, bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor=NAVY)
        cell.alignment = Alignment(vertical='center', wrap_text=True)
    for row in sheet.iter_rows(min_row=2):
        sheet.row_dimensions[row[0].row].height = 72 if 'Review reason' in headers else 29
        for cell in row:
            header = str(headers[cell.column-1])
            cell.font = Font(name='Calibri', size=10, color=INK)
            cell.fill = PatternFill('solid', fgColor='FFFFFF' if cell.row % 2 == 0 else PALE)
            cell.border = Border(bottom=Side(style='hair', color=LINE))
            cell.alignment = Alignment(vertical='center', wrap_text=True)
            if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                cell.number_format = MONEY
                cell.alignment = Alignment(horizontal='right', vertical='center')
            if header in {'Status', 'Statut', 'Statut validation'}:
                passed = cell.value == 'OK'
                cell.fill = PatternFill('solid', fgColor=GREEN_BG if passed else AMBER_BG)
                cell.font = Font(name='Calibri', bold=True, size=10, color=GREEN if passed else AMBER)
                cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    for column, header in enumerate(headers, 1):
        text = str(header)
        numeric = all(cell.value is None or isinstance(cell.value, (int, float))
                      for cell in list(sheet.columns)[column-1][1:])
        width = (44 if text in {'Review reason', 'Manual review note'} else 26 if 'Designation' in text
                 else 22 if text in {'Status', 'Statut', 'Statut validation'} else 14 if numeric
                 else 10 if 'Unite' in text else 18)
        sheet.column_dimensions[get_column_letter(column)].width = width
        # Review reason already includes the manual note; retain the duplicate source
        # field for machine readers but avoid printing it twice.
        if text == 'Manual review note':
            sheet.column_dimensions[get_column_letter(column)].hidden = True
    table = Table(displayName=f'AuditDetail{number}', ref=sheet.dimensions)
    table.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
    sheet.add_table(table)
    sheet.auto_filter.ref = sheet.dimensions


def band(sheet, cell_range, text, size=11, color=INK, fill=None, bold=False):
    sheet.merge_cells(cell_range)
    if fill:
        for row in sheet[cell_range]:
            for cell in row:
                cell.fill = PatternFill('solid', fgColor=fill)
    cell = sheet[cell_range.split(':')[0]]
    cell.value = text
    cell.font = Font(name='Calibri', size=size, color=color, bold=bold)
    cell.alignment = Alignment(vertical='center', wrap_text=True, indent=1)
    return cell


def metric(sheet, start, end, label, value, money=False, color=TEAL):
    band(sheet, f'{start}8:{end}8', label.upper(), 9, MUTED, PALE, True)
    cell = band(sheet, f'{start}9:{end}10', value, 22, color, PALE, True)
    cell.alignment = Alignment(horizontal='left', vertical='center', indent=1)
    if money:
        cell.number_format = MONEY


def style_report(workbook, filename, sheets, metadata, policy, records, comparisons, technical):
    title = TITLES[filename]
    for index, name in enumerate(sheets, 1):
        detail(workbook[name], index)
    provenance = workbook['Metadata']
    page(provenance)
    provenance.sheet_properties.tabColor = '94A7B6'
    provenance.freeze_panes = 'B2'
    provenance.column_dimensions['A'].width, provenance.column_dimensions['B'].width = 24, 105
    for row in provenance:
        for cell in row:
            cell.font = Font(name='Calibri', size=10, color=INK)
            cell.alignment = Alignment(vertical='top', wrap_text=True)
        provenance.row_dimensions[row[0].row].height = 32 if row[0].row < 5 else 120
    for cell in provenance[1]:
        cell.fill = PatternFill('solid', fgColor=NAVY)
        cell.font = Font(name='Calibri', bold=True, color='FFFFFF')
    provenance.print_title_rows, provenance.print_area = '1:1', provenance.dimensions
    cover = workbook.create_sheet('Report Overview')
    page(cover, landscape=False)
    cover.sheet_properties.tabColor = NAVY
    for col in range(1, 13):
        cover.column_dimensions[get_column_letter(col)].width = 8.8
    for row in range(1, 42):
        cover.row_dimensions[row].height = 20
    cover.row_dimensions[1].height, cover.row_dimensions[2].height = 28, 24
    cover.row_dimensions[6].height = 25
    band(cover, 'A1:L2', title, 22, 'FFFFFF', NAVY, True)
    band(cover, 'A3:L3', 'INFRASTRUCTURE ANALYTICS  /  CONSTRUCTION MONITORING', 9, TEAL, bold=True)
    band(cover, 'A4:L4', 'Executive overview and supporting audit schedules', 12, MUTED)
    when = datetime.fromisoformat(metadata['generated_at_utc']).astimezone(ZoneInfo('Africa/Casablanca'))
    band(cover, 'A5:L5', f'Issued {when:%d %b %Y · %H:%M} (Africa/Casablanca)  |  {policy.version}', 9, MUTED)
    band(cover, 'A6:L6', 'SYNTHETIC DEMO DATA  •  Preliminary screening, not a certified audit opinion', 9, AMBER, AMBER_BG, True)
    technical_report, continuity_report = filename == 'audit_technique_valide.xlsx', filename == 'financial_audit.xlsx'
    if technical_report or continuity_report:
        statuses = technical['Statut validation'].tolist() if technical_report else [row['Status'] for row in comparisons]
        metric(cover, 'A', 'D', 'Work items' if technical_report else 'Continuity comparisons', len(statuses))
        metric(cover, 'E', 'H', 'Checks passed', statuses.count('OK'), color=GREEN)
        metric(cover, 'I', 'L', 'Requiring review', sum(s != 'OK' for s in statuses), color=AMBER)
    else:
        statuses = [row['Status'] for row in records]
        if filename == 'rapport_audit_financier.xlsx':
            statuses += [row['Status'] for row in comparisons]
        for start, end, label, key in [('A','D','Works HT · DH','Works HT'), ('E','H','VAT · DH','VAT'), ('I','L','TTC · DH','TTC')]:
            metric(cover, start, end, label, float(sum(row[key] for row in records)), money=True)
    passed = bool(statuses) and all(status == 'OK' for status in statuses)
    band(cover, 'A12:L12', '01  /  AUDIT AT A GLANCE', color='FFFFFF', fill=TEAL, bold=True)
    band(cover, 'A14:F15', 'PASS UNDER DEMO RULES' if passed else 'REVIEW REQUIRED', 14,
         GREEN if passed else AMBER, GREEN_BG if passed else AMBER_BG, True)
    band(cover, 'A17:F20',
         'Quantity arithmetic and contract limits are screened. Illustrative manual flags are explained in the detailed schedule.'
         if technical_report else 'Arithmetic uses the stated demo assumptions. Continuity compares consecutive statements within the supplied interval.', 11)
    band(cover, 'A22:F25', 'Green: explicit OK result.\nAmber: missing evidence, discrepancy or review flag.\nReview flags require source verification.', 10, MUTED)
    chart_data = workbook.create_sheet('_ChartData')
    if technical_report or continuity_report:
        chart_data.append(['Result', 'Records'])
        chart_data.append(['Passed', statuses.count('OK')])
        chart_data.append(['Review / incomplete', sum(s != 'OK' for s in statuses)])
        chart = DoughnutChart()
        chart.holeSize, chart.title = 72, 'Check results'
        chart.add_data(Reference(chart_data, min_col=2, min_row=1, max_row=3), titles_from_data=True)
        chart.set_categories(Reference(chart_data, min_col=1, min_row=2, max_row=3))
        for index, color in enumerate([GREEN, 'E4A83A']):
            point = DataPoint(idx=index)
            point.graphicalProperties.solidFill = color
            chart.series[0].data_points.append(point)
    else:
        chart_data.append(['Statement', 'Works HT (DH)'])
        for row in records:
            chart_data.append([f"D{row['Statement number']}", float(row['Works HT'])])
        chart = BarChart()
        chart.title, chart.legend, chart.y_axis.title = 'Works by statement', None, 'DH HT'
        chart.y_axis.numFmt = '#,##0'
        chart.add_data(Reference(chart_data, min_col=2, min_row=1, max_row=len(records)+1), titles_from_data=True)
        chart.set_categories(Reference(chart_data, min_col=1, min_row=2, max_row=len(records)+1))
        chart.series[0].graphicalProperties.solidFill = TEAL
        chart.series[0].graphicalProperties.line.noFill = True
    chart.width, chart.height = 9.2, 6.8
    cover.add_chart(chart, 'G14')
    chart_data.sheet_state = 'hidden'
    band(cover, 'A28:L28', '02  /  REPORT CONTENTS', color='FFFFFF', fill=TEAL, bold=True)
    for row, name in enumerate(sheets, 30):
        label = 'Detailed results — ' + title if name == 'Sheet1' else name.replace('_', ' ')
        cell = band(cover, f'A{row}:L{row}', f'Open schedule  →  {label}', 11, TEAL, PALE)
        cell.hyperlink = f"#'{name}'!A1"
        cell.font = Font(name='Calibri', size=11, underline='single', color=TEAL)
    cell = band(cover, 'A33:L33', 'Open methodology and source provenance → Metadata', 10, TEAL)
    cell.hyperlink = "#'Metadata'!A1"
    band(cover, 'A35:L35', '03  /  BASIS & LIMITATIONS', color='FFFFFF', fill=TEAL, bold=True)
    band(cover, 'A36:L38',
         f'Retention {policy.retention_rate:.0%} · VAT {policy.vat_rate:.0%} · VAT base: {policy.vat_base.replace("_", " ")} · '
         f'Tolerance {policy.tolerance} DH. Half-up rounding to two decimals. '
         'Technical schedules do not certify source measurements. Results use synthetic demonstration data.', 9, MUTED)
    cover.print_area, cover.page_setup.fitToHeight = 'A1:L39', 1
    cover.oddHeader.center.text = ''
    cover.sheet_view.zoomScale = 85
    workbook.active = workbook.index(cover)
    for sheet in workbook:
        sheet.sheet_view.tabSelected = sheet is cover
    workbook.properties.title, workbook.properties.creator = title, 'Infrastructure Analytics Demo'
