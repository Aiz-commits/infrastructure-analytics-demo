"""Create synthetic examples only when explicitly invoked, never on import."""
import argparse
from decimal import Decimal
from pathlib import Path
from openpyxl import Workbook
from scripts.policy import amount, expected_amounts, load_policy


def generate_demo_decomptes(folder, policy=None):
    policy = policy or load_policy()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    cumulative = Decimal('0.00')
    paths = []
    for number, monthly in enumerate([480000, 640000, 810000, 820000], start=1):
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parent / 'demo_decomptes')
    args = parser.parse_args()
    for path in generate_demo_decomptes(args.output_dir):
        print(f'Created synthetic statement: {path.name}')
