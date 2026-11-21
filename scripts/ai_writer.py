"""Audit memo and contractor email. The AI sees findings only; every number it writes is checked."""
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from . import llm

LANGUAGES = {'fr': 'French', 'en': 'English'}
_NUMBER = re.compile(r'\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)*')
_PAIR = re.compile(r'D\d+ → D\d+')
TITLES_FR = {'retention': 'Retenue de garantie', 'net': 'Net HT = travaux − retenue', 'vat': 'TVA',
             'ttc': 'TTC = net HT + TVA', 'cumulative': 'Cumul HT = cumul précédent + travaux du mois',
             'continuity': 'Continuité avec le décompte précédent', 'sequence': 'Suite des numéros de décompte',
             'missing': 'Valeur non trouvée dans le fichier', 'uncertain': 'Libellé incertain pour une valeur lue'}


@dataclass(frozen=True)
class Texts:
    memo: str
    email_subject: str
    email_body: str
    ai_used: bool


def findings_json(findings, project='', number=None):
    rows = [{'id': f.id, 'severity': f.severity, 'title': f.title,
             'amounts': {k: f'{v:.2f}' for k, v in f.amounts.items()},
             'difference': None if f.difference is None else f'{f.difference:.2f}', 'evidence': f.evidence}
            for f in findings]
    return json.dumps({'project': project, 'statement_number': number, 'currency': 'DH', 'findings': rows},
                      ensure_ascii=False, indent=1)


def format_amount(value, language):
    text = f'{value:,.2f}'
    return text.replace(',', ' ').replace('.', ',') if language == 'fr' else text


def _to_decimal(token):
    token = re.sub(r'[   ]', '', token)
    if ',' in token and '.' in token:
        decimal_mark = ',' if token.rfind(',') > token.rfind('.') else '.'
        token = token.replace('.' if decimal_mark == ',' else ',', '').replace(',', '.')
    else:
        for mark in (',', '.'):
            if mark in token:
                parts = token.split(mark)
                decimal = len(parts) == 2 and 1 <= len(parts[1]) <= 2
                token = token.replace(mark, '.') if decimal else token.replace(mark, '')
    try:
        return Decimal(token)
    except InvalidOperation:
        return None


def extract_numbers(text):
    return [value for value in (_to_decimal(m.group()) for m in _NUMBER.finditer(text or '')) if value is not None]


def allowed_numbers(findings, policy, project='', number=None):
    allowed = set(extract_numbers(findings_json(findings, project, number)))
    allowed.update({policy.retention_rate * 100, policy.vat_rate * 100})
    return {value.quantize(Decimal('0.01')) for value in allowed}


def unsupported_numbers(text, allowed, tolerance):
    found = []
    for value in extract_numbers(text):
        value = value.quantize(Decimal('0.01'))
        if not any(abs(value - a) <= tolerance for a in allowed):
            found.append(value)
    return found


def _label(finding, language):
    if language != 'fr':
        return finding.title
    base = TITLES_FR.get(finding.id.split(':')[0], finding.title)
    pair = _PAIR.search(finding.title)
    return f'{base} ({pair.group()})' if pair else base


def _line(finding, language, with_evidence):
    a = lambda key: format_amount(finding.amounts[key], language)
    if 'stated' in finding.amounts and 'expected' in finding.amounts and finding.difference is not None:
        if language == 'fr':
            text = (f'{_label(finding, language)} : montant déclaré {a("stated")} DH, attendu {a("expected")} DH, '
                    f'écart {format_amount(finding.difference, language)} DH')
        else:
            text = (f'{_label(finding, language)}: stated {a("stated")} DH, expected {a("expected")} DH, '
                    f'difference {format_amount(finding.difference, language)} DH')
    else:
        text = _label(finding, language)
    return f'- {text}' + (f' ({finding.evidence})' if with_evidence and language == 'en' and finding.evidence else '')


def template_texts(findings, language, policy=None, project='', number=None):
    fr = language == 'fr'
    groups = {s: [f for f in findings if f.severity == s] for s in ('REVIEW', 'WARNING', 'SKIPPED', 'OK')}
    ref = f'D{number}' if number is not None else ('décompte' if fr else 'statement')
    where = f' — {project}' if project else ''
    heads = (('À justifier', 'Points d’attention', 'Contrôles non effectués', 'Contrôles conformes') if fr else
             ('Requires justification', 'Warnings', 'Checks skipped', 'Checks passed'))
    memo = [f'# {"Note d’audit" if fr else "Audit memo"} — {ref}{where}', '']
    for (severity, items), head in zip(groups.items(), heads):
        if items:
            memo += [f'## {head}'] + [_line(f, language, severity != 'OK') for f in items] + ['']
    memo.append('Les points ci-dessus demandent une justification ; ils ne constituent pas une conclusion définitive.'
                if fr else 'The points above require justification; they are not a final conclusion.')
    reviews = groups['REVIEW']
    subject = (f'Décompte {ref}{where} : demande de justification' if fr else
               f'Statement {ref}{where}: request for justification')
    if fr:
        intro = [f'Madame, Monsieur,', '', f'Nous avons examiné le décompte {ref}{where}.']
        ask = (['Les points suivants demandent une justification :'] + [_line(f, 'fr', False) for f in reviews]
               if reviews else ['Aucun point ne demande de justification à ce stade.'])
        close = ['', 'Merci de nous transmettre les pièces justificatives ou un décompte corrigé.', '',
                 'Cordialement,', 'Le contrôleur de projet']
    else:
        intro = ['Dear Sir or Madam,', '', f'We have reviewed statement {ref}{where}.']
        ask = (['The following points require justification:'] + [_line(f, 'en', False) for f in reviews]
               if reviews else ['No point requires justification at this stage.'])
        close = ['', 'Please send supporting documents or a corrected statement.', '', 'Kind regards,',
                 'Project controller']
    return Texts('\n'.join(memo), subject, '\n'.join(intro + [''] + ask + close), False)


def build_prompt(findings, language, project='', number=None):
    return (f'You are a neutral construction audit assistant. Write in {LANGUAGES.get(language, "English")}.\n'
            'Use only the findings JSON below. Rules:\n'
            '- Never calculate. Use only numbers that appear in the JSON, copied exactly (you may format them).\n'
            '- No cell addresses, no dates, no numbered lists; use "-" bullets.\n'
            '- Neutral tone: say "requires justification". Never say fraud or confirmed error.\n'
            '- One bullet per REVIEW finding. Mention WARNING and SKIPPED items briefly in the memo only.\n'
            'Output exactly this format:\n### MEMO\n<short audit memo>\n### EMAIL\nSubject: <subject>\n'
            '<polite email to the contractor asking for justification of each REVIEW item>\n\n'
            f'Findings JSON:\n{findings_json(findings, project, number)}')


def parse_sections(text):
    match = re.search(r'###\s*MEMO\s*\n(.*?)\n###\s*EMAIL\s*\n\s*Subject:\s*(.+?)\n(.*)', text or '', re.S | re.I)
    if not match:
        return None
    memo, subject, body = (part.strip() for part in match.groups())
    return (memo, subject, body) if memo and subject and body else None


def write_texts(findings, language, policy, api_key, ask=llm.ask_text, *, project='', number=None):
    fallback = template_texts(findings, language, policy, project=project, number=number)
    if not api_key:
        return fallback
    allowed = allowed_numbers(findings, policy, project, number)
    prompt = build_prompt(findings, language, project, number)
    for _ in range(2):
        reply = ask(prompt, api_key)
        if reply is None:
            return fallback
        parts = parse_sections(reply)
        if parts and not unsupported_numbers(' '.join(parts), allowed, policy.tolerance):
            return Texts(*parts, True)
    return fallback
