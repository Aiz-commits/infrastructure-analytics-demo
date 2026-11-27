"""The phone review page: plain mobile HTML, no JavaScript. Every value is HTML-escaped."""
from html import escape
from scripts.ai_writer import FIELDS_FR, _evidence, _label, format_amount
from scripts.controller_checks import FIELDS, LABELS

TEXT = {
    'fr': {'title': 'Contrôle du décompte', 'happened': 'Ce qui s’est passé', 'values': 'Valeurs lues',
           'checks': 'Contrôles', 'memo': 'Note d’audit (brouillon)', 'email': 'E-mail à l’entreprise (brouillon, non envoyé)',
           'file': 'Ouvrir le fichier reçu', 'pin': 'Code PIN', 'approve': 'Approuver', 'reject': 'Rejeter',
           'confirm': 'J’ai comparé ces valeurs avec le document joint.',
           'no_edit': 'Une valeur est fausse ? Rejetez, corrigez le fichier et renvoyez l’e-mail.',
           'summary': '{review} à vérifier · {warnings} alertes', 'received': 'E-mail reçu de {sender} le {when} UTC',
           'read': 'Valeurs lues ({method})', 'ai_ran': 'L’IA a choisi : {checks}',
           'guard': '{check} — ajouté par le garde-fou (l’IA ne l’avait pas lancé)',
           'offline': 'IA indisponible — Python a lancé tous les contrôles de base', 'python_ran': 'Python a lancé : {checks}',
           'stopped': 'L’IA a cessé de répondre — le garde-fou a complété les contrôles',
           'unknown': 'Outil inconnu demandé par l’IA, ignoré : {name}', 'reason': 'Raison de l’IA : {reason}',
           'texts_ai': 'Note et e-mail rédigés par l’IA (chiffres vérifiés par Python)',
           'texts_template': 'Note et e-mail : modèle standard (sans IA)',
           'Approved': 'Approuvé', 'Rejected': 'Rejeté', 'decided': '{decision} par le contrôleur le {when} UTC. Aucun e-mail n’a été envoyé.',
           'field': 'Valeur', 'amount': 'Montant DH', 'cell': 'Emplacement', 'source': 'Source', 'status': 'Statut',
           'check': 'Contrôle', 'difference': 'Écart DH', 'evidence': 'Preuve', 'uncertain': ' (incertain)',
           'not_found': 'non trouvée'},
    'en': {'title': 'Décompte review', 'happened': 'What happened', 'values': 'Values read', 'checks': 'Checks',
           'memo': 'Audit memo (draft)', 'email': 'Email to the contractor (draft, not sent)',
           'file': 'Open the file received', 'pin': 'PIN', 'approve': 'Approve', 'reject': 'Reject',
           'confirm': 'I compared these values with the attached document.',
           'no_edit': 'A value is wrong? Reject, fix the file and email it again.',
           'summary': '{review} to review · {warnings} warnings', 'received': 'Email received from {sender} on {when} UTC',
           'read': 'Values read ({method})', 'ai_ran': 'The AI chose: {checks}',
           'guard': '{check} — added by the guard (the AI did not run it)',
           'offline': 'AI unavailable — Python ran every core check', 'python_ran': 'Python ran: {checks}',
           'stopped': 'The AI stopped answering — the guard completed the checks',
           'unknown': 'Unknown tool asked by the AI, ignored: {name}', 'reason': 'AI reason: {reason}',
           'texts_ai': 'Memo and email drafted by the AI (numbers checked by Python)',
           'texts_template': 'Memo and email: standard template (no AI)',
           'Approved': 'Approved', 'Rejected': 'Rejected', 'decided': '{decision} by the reviewer on {when} UTC. No email was sent.',
           'field': 'Field', 'amount': 'Amount DH', 'cell': 'Where', 'source': 'Source', 'status': 'Status',
           'check': 'Check', 'difference': 'Difference DH', 'evidence': 'Evidence', 'uncertain': ' (uncertain)',
           'not_found': 'not found'},
}
CHECK_NAMES = {'fr': {'retention': 'retenue de garantie', 'net': 'net HT', 'vat': 'TVA', 'ttc': 'TTC',
                      'cumulative': 'cumul', 'history': 'historique (continuité + numéros)',
                      'contract_ceiling': 'plafond du marché'},
               'en': {'retention': 'retention', 'net': 'net HT', 'vat': 'VAT', 'ttc': 'TTC', 'cumulative': 'cumulative',
                      'history': 'history (continuity + numbers)', 'contract_ceiling': 'contract ceiling'}}
STATUS = {'fr': {'OK': '✅ Conforme', 'REVIEW': '⚠️ À vérifier', 'WARNING': '⚠️ Attention', 'SKIPPED': '⏭️ Non vérifié'},
          'en': {'OK': '✅ OK', 'REVIEW': '⚠️ Review', 'WARNING': '⚠️ Warning', 'SKIPPED': '⏭️ Skipped'}}
STYLE = ('body{font-family:system-ui,sans-serif;margin:0 auto;max-width:720px;padding:12px;line-height:1.4;color:#1a1a1a}'
         'h1{font-size:1.3em}h2{font-size:1.05em;margin-top:1.4em}table{border-collapse:collapse;width:100%;font-size:.9em}'
         'td,th{border-bottom:1px solid #ddd;padding:4px;text-align:left;vertical-align:top}'
         'pre{white-space:pre-wrap;background:#f6f6f6;padding:8px;font-family:inherit}'
         '.msg{padding:10px;border-radius:6px;background:#fff4d6;margin:10px 0}.ok{background:#e3f6e3}'
         'input[type=password]{font-size:1.4em;width:8em;letter-spacing:.2em}'
         'button{font-size:1.1em;padding:10px 18px;margin:8px 8px 0 0}ol{padding-left:1.2em}')


def _lang(run):
    return 'fr' if run['language'] == 'fr' else 'en'


def page(title, body):
    return (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">'
            f'<title>{escape(title)}</title><style>{STYLE}</style></head><body>{body}</body></html>')


def message_page(text):
    return page('AI Controller', f'<h1>AI Controller</h1><div class="msg">{escape(text)}</div>')


def timeline(run):
    t, lang = TEXT[_lang(run)], _lang(run)
    name = lambda check: CHECK_NAMES[lang].get(check, check)
    steps = [t['received'].format(sender=run['sender'], when=f'{run["created_at"]:%Y-%m-%d %H:%M}'),
             t['read'].format(method=run['read_method'])]
    ai_ran = [name(s.check_id) for s in run['trace'] if s.who == 'AI' and s.action == 'ran']
    python_ran = [name(s.check_id) for s in run['trace'] if s.who == 'Python' and s.action == 'ran']
    if ai_ran:
        steps.append(t['ai_ran'].format(checks=', '.join(ai_ran)))
    for step in run['trace']:
        if step.who == 'guard':
            steps.append(t['guard'].format(check=name(step.check_id)))
        elif step.who == 'Python' and step.action.startswith('AI planner offline'):
            steps.append(t['offline'])
        elif step.who == 'Python' and step.action.startswith('AI stopped'):
            steps.append(t['stopped'])
        elif step.action == 'unknown tool ignored':
            steps.append(t['unknown'].format(name=step.reason))
        elif step.action == 'finished' and step.reason:
            steps.append(t['reason'].format(reason=step.reason))
    if python_ran:
        steps.append(t['python_ran'].format(checks=', '.join(python_ran)))
    steps.append(t['texts_ai'] if run['texts'].ai_used else t['texts_template'])
    return '<ol>' + ''.join(f'<li>{escape(s)}</li>' for s in steps) + '</ol>'


def _values_table(run):
    t, lang = TEXT[_lang(run)], _lang(run)
    rows = []
    for field in FIELDS:
        v = run['statement'].values[field]
        label = (FIELDS_FR if lang == 'fr' else LABELS)[field] + (t['uncertain'] if v.uncertain else '')
        value = t['not_found'] if v.value is None else format_amount(v.value, lang)
        rows.append(f'<tr><td>{escape(label)}</td><td>{escape(value)}</td><td>{escape(v.cell or "")}</td>'
                    f'<td>{escape(v.source)}</td></tr>')
    return (f'<table><tr><th>{t["field"]}</th><th>{t["amount"]}</th><th>{t["cell"]}</th><th>{t["source"]}</th></tr>'
            + ''.join(rows) + '</table>')


def _findings_table(run):
    t, lang = TEXT[_lang(run)], _lang(run)
    rows = ''.join(
        f'<tr><td>{escape(_label(f, lang))}</td><td>{escape(STATUS[lang].get(f.severity, f.severity))}</td>'
        f'<td>{"" if f.difference is None else escape(format_amount(f.difference, lang))}</td>'
        f'<td>{escape(_evidence(f, lang))}</td></tr>' for f in run['findings'])
    return (f'<table><tr><th>{t["check"]}</th><th>{t["status"]}</th><th>{t["difference"]}</th>'
            f'<th>{t["evidence"]}</th></tr>{rows}</table>')


def _form(run, token):
    t = TEXT[_lang(run)]
    confirm = (f'<p><label><input type="checkbox" name="confirmed_values"> {escape(t["confirm"])}</label><br>'
               f'<small>{escape(t["no_edit"])}</small></p>' if run['needs_confirmation'] else '')
    return (f'<form method="post" action="/review/{run["id"]}/decision">'
            f'<input type="hidden" name="t" value="{escape(token)}">{confirm}'
            f'<p><label>{t["pin"]} <input type="password" name="pin" inputmode="numeric" autocomplete="off" '
            f'maxlength="12" required></label></p>'
            f'<button type="submit" name="decision" value="Approved">✅ {t["approve"]}</button>'
            f'<button type="submit" name="decision" value="Rejected">❌ {t["reject"]}</button></form>')


def decision_text(run):
    t = TEXT[_lang(run)]
    return t['decided'].format(decision=t[run['decision']], when=f'{run["decided_at"]:%Y-%m-%d %H:%M}')


def render_review(run, *, token, message=None, ok=False):
    t = TEXT[_lang(run)]
    s = run['statement']
    review = sum(f.severity == 'REVIEW' for f in run['findings'])
    warnings = sum(f.severity == 'WARNING' for f in run['findings'])
    head = f'{s.project or "?"} — D{s.number if s.number is not None else "?"}'
    notice = f'<div class="msg{" ok" if ok else ""}">{escape(message)}</div>' if message else ''
    if run['decision']:
        action = f'<div class="msg ok">{escape(decision_text(run))}</div>'
    elif run['locked']:
        action = ''
    else:
        action = _form(run, token)
    body = (f'<h1>{escape(t["title"])} : {escape(head)}</h1>'
            f'<p><b>{escape(t["summary"].format(review=review, warnings=warnings))}</b></p>{notice}'
            f'<h2>{t["happened"]}</h2>{timeline(run)}<h2>{t["values"]}</h2>{_values_table(run)}'
            f'<h2>{t["checks"]}</h2>{_findings_table(run)}'
            f'<p><a href="/review/{run["id"]}/file?t={escape(token)}">{t["file"]}</a></p>'
            f'<h2>{t["memo"]}</h2><pre>{escape(run["texts"].memo)}</pre>'
            f'<h2>{t["email"]}</h2><pre>{escape(run["texts"].email_subject)}\n\n{escape(run["texts"].email_body)}</pre>'
            f'{action}')
    return page(f'{t["title"]} {head}', body)
