from datetime import datetime, timezone
from email import message_from_bytes, policy as email_policy
from scripts.ai_writer import Texts
from scripts.controller_review import email_eml, memo_markdown, trail_row

WHEN = datetime(2026, 11, 21, 14, 30, tzinfo=timezone.utc)
TEXTS = Texts('# Note d’audit\n- TVA : écart 1 000,00 DH', 'Décompte D5 : demande de justification',
              'Madame, Monsieur,\n- Continuité : écart 12 300,00 DH', True)


def test_memo_starts_with_decision_line():
    memo = memo_markdown(TEXTS, 'DEMO PROJECT', 5, 'Approved', WHEN).decode('utf-8')
    assert memo.splitlines()[0] == 'Approved by reviewer — 2026-11-21T14:30:00+00:00'
    assert 'DEMO PROJECT' in memo and 'D5' in memo and 'Note d’audit' in memo
    assert 'AI-drafted' in memo
    assert memo_markdown(TEXTS, '', None, 'Rejected', WHEN).decode().startswith('Rejected by reviewer')


def test_eml_parses_back_with_accents_and_no_recipient():
    message = message_from_bytes(email_eml(TEXTS, WHEN), policy=email_policy.default)
    assert message['Subject'] == 'Décompte D5 : demande de justification'
    assert message['To'] is None
    assert message['Date'] is not None
    assert 'Continuité' in message.get_content()


def test_trail_row_keys():
    row = trail_row('DEMO_DP_N5.xlsx', WHEN, True, 'Approved')
    assert row == {'File': 'DEMO_DP_N5.xlsx', 'Date/time': '2026-11-21 14:30 UTC', 'AI used': 'yes',
                   'Decision': 'Approved'}
    assert trail_row('x.xlsx', WHEN, False, 'Rejected')['AI used'] == 'no'
