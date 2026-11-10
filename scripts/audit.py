"""Batch completeness and continuity: never treat excluded inputs as a full pass."""
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from .decompte_extractor import extract_decompte, filename_number
from .policy import load_policy
from .workbooks import MAX_BATCH_BYTES, MAX_FILES, workbook_bytes


@dataclass
class BatchAudit:
    records: list
    comparisons: list
    issues: list
    status: str
    requested: int


def audit_batch(files, policy=None):
    policy = policy or load_policy()
    files = list(files)
    records, comparisons, issues = [], [], []
    if not files or len(files) > MAX_FILES:
        return BatchAudit([], [], [f'Upload between 1 and {MAX_FILES} statements.'], 'INVALID INPUT', len(files))
    total_bytes = 0
    for filename, source in files:
        try:
            declared_number = filename_number(filename)
            data = workbook_bytes(source)
            total_bytes += len(data)
            if total_bytes > MAX_BATCH_BYTES:
                return BatchAudit(records, [], ['Batch exceeds the 50 MiB total limit.'], 'INVALID INPUT', len(files))
            record = extract_decompte(data, policy=policy)
            number = record['Statement number']
            if number is None:
                issues.append(f'{filename}: source statement number is missing; filename alone is not authoritative.')
            elif declared_number is not None and number != declared_number:
                issues.append(f'{filename}: filename number conflicts with the source statement number.')
            if not record['Project']:
                issues.append(f'{filename}: source project identifier is missing.')
            record['File'] = filename
            records.append(record)
        except ValueError as error:
            issues.append(f'{filename}: {error}')
        except Exception:
            issues.append(f'{filename}: cannot process this workbook; verify its structure.')
    projects = {record['Project'].casefold() for record in records if record['Project']}
    if len(projects) > 1:
        issues.append('Statements belong to different projects; continuity cannot be confirmed.')
    numbered = [record for record in records if record['Statement number'] is not None]
    counts = Counter(record['Statement number'] for record in numbered)
    duplicates = {number for number, count in counts.items() if count > 1}
    if duplicates:
        issues.append('Duplicate statement numbers: ' + ', '.join(f'D{n}' for n in sorted(duplicates)))
    # Never pair ambiguous duplicates or mixed projects.
    ordered = sorted((record for record in numbered if record['Statement number'] not in duplicates),
                     key=lambda record: record['Statement number'])
    if len(projects) <= 1:
        for previous, current in zip(ordered, ordered[1:]):
            p, c = previous['Statement number'], current['Statement number']
            if c != p + 1:
                issues.append(f'Missing intermediate statements between D{p} and D{c}.')
                continue
            declared = current['Previous cumulative HT']
            difference = None if declared is None else previous['Cumulative HT'] - declared
            status = 'MISSING DATA' if difference is None else ('OK' if abs(difference) <= policy.tolerance else 'REVIEW REQUIRED')
            comparisons.append({'Comparison': f'D{p} → D{c}', 'Expected previous HT': previous['Cumulative HT'],
                                'Declared previous HT': declared, 'Difference DH': difference, 'Status': status})
    if len(comparisons) == 0:
        issues.append('At least two consecutive, uniquely identified statements are required for continuity.')
    if any(record['Status'] != 'OK' for record in records):
        issues.append('One or more statements have incomplete data or require review.')
    if any(comparison['Status'] != 'OK' for comparison in comparisons):
        issues.append('One or more continuity comparisons have missing data or discrepancies.')
    complete = (len(records) == len(files) and len(comparisons) == len(files) - 1 and len(files) >= 2)
    status = 'OK' if complete and not issues else 'INCOMPLETE / REVIEW REQUIRED'
    return BatchAudit(records, comparisons, issues, status, len(files))


def all_passed(statuses):
    statuses = list(statuses)
    return bool(statuses) and all(isinstance(status, str) and status == 'OK' for status in statuses)


def display_frame(records):
    """Convert Decimal only at the presentation boundary, never during checks."""
    import pandas as pd
    frame = pd.DataFrame(records)
    return frame.map(lambda value: float(value) if isinstance(value, Decimal) else value)
