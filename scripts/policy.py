"""Explicit financial assumptions for the public synthetic demonstration."""
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_AMOUNT = Decimal('1000000000000')


def amount(value):
    if value is None or isinstance(value, bool):
        raise ValueError('Missing or invalid financial amount.')
    try:
        result = Decimal(str(value))
        if not result.is_finite() or abs(result) > MAX_AMOUNT:
            raise ValueError('Financial amount is non-finite or outside the supported range.')
        return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError) as error:
        raise ValueError('Invalid financial amount; use a numeric cell.') from error


@dataclass(frozen=True)
class Policy:
    version: str
    name: str
    retention_rate: Decimal
    vat_rate: Decimal
    vat_base: str
    tolerance: Decimal
    contract_ttc: Decimal
    retention_cap: Decimal | None = None


def _load_policy(path=ROOT / 'project_config.json'):
    values = json.loads(Path(path).read_text(encoding='utf-8'))
    rate = Decimal(values['retention_rate'])
    vat = Decimal(values['vat_rate'])
    if not all(x.is_finite() and 0 <= x <= 1 for x in (rate, vat)):
        raise ValueError('Rates must be finite values between zero and one.')
    base = values['vat_base']
    if base not in {'net_after_retention', 'works_ht'}:
        raise ValueError('Unsupported VAT base.')
    tolerance = amount(values['tolerance'])
    contract = amount(values['contract_ttc'])
    cap = None if values.get('retention_cap') is None else amount(values['retention_cap'])
    if tolerance < 0 or tolerance > Decimal('0.01') or contract <= 0 or (cap is not None and cap < 0):
        raise ValueError('Invalid tolerance, contract total, or retention cap.')
    return Policy(values['rule_version'], values['policy_name'], rate, vat, base, tolerance, contract, cap)


def load_policy(path=ROOT / 'project_config.json'):
    try:
        return _load_policy(path)
    except (KeyError, TypeError, InvalidOperation, OverflowError) as error:
        raise ValueError('Invalid financial policy configuration; check required numeric fields.') from error


def expected_amounts(works, cumulative, previous, policy):
    retention = amount(works * policy.retention_rate)
    if policy.retention_cap is not None:
        if previous is None:
            raise ValueError('Previous cumulative amount is required for capped retention.')
        retention = amount(min(amount(cumulative * policy.retention_rate), policy.retention_cap)
                           - min(amount(previous * policy.retention_rate), policy.retention_cap))
    net = amount(works - retention)
    vat = amount((net if policy.vat_base == 'net_after_retention' else works) * policy.vat_rate)
    return {'Retention': retention, 'Net HT': net, 'VAT': vat, 'TTC': amount(net + vat)}
