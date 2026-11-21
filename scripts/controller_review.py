"""Human review outputs: downloadable memo and email draft, plus audit-trail rows. Nothing is sent."""
from datetime import timezone
from email.message import EmailMessage
from email.utils import format_datetime


def memo_markdown(texts, project, number, decision, decided_at):
    reference = ' — '.join(part for part in (project, f'D{number}' if number is not None else '') if part)
    source = 'AI-drafted, reviewed by a human' if texts.ai_used else 'Template text (no AI)'
    lines = [f'{decision} by reviewer — {decided_at.isoformat()}', '',
             f'Statement: {reference or "unidentified"}', f'Source: {source}', '', texts.memo, '']
    return '\n'.join(lines).encode('utf-8')


def email_eml(texts, decided_at):
    message = EmailMessage()
    message['Subject'] = texts.email_subject
    message['Date'] = format_datetime(decided_at)
    message['X-Draft-Status'] = 'Draft approved by reviewer; not sent'
    message.set_content(texts.email_body)
    return message.as_bytes()


def trail_row(filename, decided_at, ai_used, decision):
    return {'File': filename, 'Date/time': decided_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
            'AI used': 'yes' if ai_used else 'no', 'Decision': decision}
