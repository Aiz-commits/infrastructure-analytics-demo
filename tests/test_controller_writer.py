from decimal import Decimal
import pytest
from scripts.ai_writer import (Texts, allowed_numbers, extract_numbers, findings_json, format_amount,
                               template_texts, unsupported_numbers, write_texts)
from scripts.controller_checks import EXAMPLES_DIR, from_extractor, previous_from_history, run_checks
from scripts.decompte_extractor import extract_decompte
from scripts.policy import load_policy

POLICY = load_policy()


@pytest.fixture(scope='module')
def n5_findings():
    current = from_extractor(extract_decompte(EXAMPLES_DIR / 'DEMO_DP_N5.xlsx'))
    return run_checks(current, previous_from_history(current), POLICY)


def answer(memo_extra='', email_extra=''):
    return ('### MEMO\nAudit memo D5. Continuity D4 → D5 differs by 12,300.00 DH. '
            f'VAT 20% differs by 1 000,00 DH.{memo_extra}\n'
            '### EMAIL\nSubject: Statement D5 — request for justification\n'
            f'Dear Sir or Madam,\n- Continuity: difference 12 300,00 DH requires justification.{email_extra}\n')


class FakeAsk:
    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def __call__(self, prompt, api_key):
        self.prompts.append(prompt)
        return self.replies.pop(0) if self.replies else None


@pytest.mark.parametrize('text,expected', [
    ('12 300,00 DH', [Decimal('12300.00')]),
    ('12 300,00 DH', [Decimal('12300.00')]),
    ('12 300,00 DH', [Decimal('12300.00')]),
    ('12,300.00', [Decimal('12300.00')]),
    ('1.000,00', [Decimal('1000.00')]),
    ('162 000', [Decimal('162000')]),
    ('TVA 20%', [Decimal('20')]),
    ('D4 → D5', [Decimal('4'), Decimal('5')]),
    ('total 2025, then 10.', [Decimal('2025'), Decimal('10')]),
])
def test_extract_numbers(text, expected):
    assert extract_numbers(text) == expected


def test_format_amount():
    assert format_amount(Decimal('12300'), 'en') == '12,300.00'
    assert format_amount(Decimal('12300'), 'fr') == '12 300,00'


def test_guard_accepts_finding_numbers_and_rejects_invented(n5_findings):
    allowed = allowed_numbers(n5_findings, POLICY, number=5)
    assert unsupported_numbers(answer(), allowed, POLICY.tolerance) == []
    assert unsupported_numbers('gap of 99,999.00 DH', allowed, POLICY.tolerance) == [Decimal('99999.00')]


def test_good_text_first_try(n5_findings):
    ask = FakeAsk(answer())
    texts = write_texts(n5_findings, 'en', POLICY, 'k', ask=ask, project='DEMO PROJECT', number=5)
    assert texts.ai_used is True and len(ask.prompts) == 1
    assert texts.email_subject == 'Statement D5 — request for justification'
    assert texts.email_body.startswith('Dear Sir or Madam')


def test_invented_number_triggers_retry_then_template(n5_findings):
    bad = answer(memo_extra=' Total 99,999.00 DH.')
    ask = FakeAsk(bad, bad)
    texts = write_texts(n5_findings, 'en', POLICY, 'k', ask=ask, project='DEMO PROJECT', number=5)
    assert texts.ai_used is False and len(ask.prompts) == 2
    assert texts == template_texts(n5_findings, 'en', POLICY, project='DEMO PROJECT', number=5)


def test_bad_then_good_uses_second(n5_findings):
    ask = FakeAsk('no sections at all', answer())
    texts = write_texts(n5_findings, 'en', POLICY, 'k', ask=ask, project='DEMO PROJECT', number=5)
    assert texts.ai_used is True and len(ask.prompts) == 2


def test_ai_down_uses_template_no_retry(n5_findings):
    ask = FakeAsk()
    texts = write_texts(n5_findings, 'fr', POLICY, 'k', ask=ask, project='DEMO PROJECT', number=5)
    assert texts.ai_used is False and len(ask.prompts) == 1


def test_no_key_never_calls_ai(n5_findings):
    ask = FakeAsk(answer())
    assert write_texts(n5_findings, 'en', POLICY, None, ask=ask).ai_used is False
    assert ask.prompts == []


@pytest.mark.parametrize('language', ['fr', 'en'])
def test_templates_pass_their_own_guard(n5_findings, language):
    texts = template_texts(n5_findings, language, POLICY, project='DEMO PROJECT', number=5)
    allowed = allowed_numbers(n5_findings, POLICY, number=5)
    for part in (texts.memo, texts.email_subject, texts.email_body):
        assert unsupported_numbers(part, allowed, POLICY.tolerance) == []
    assert format_amount(Decimal('12300.00'), language) in texts.memo
    assert format_amount(Decimal('1000.00'), language) in texts.email_body


@pytest.mark.parametrize('language', ['fr', 'en'])
def test_template_never_says_fraud(n5_findings, language):
    texts = template_texts(n5_findings, language, POLICY, project='DEMO PROJECT', number=5)
    text = f'{texts.memo} {texts.email_subject} {texts.email_body}'.lower()
    assert not any(word in text for word in ('fraud', 'fraude', 'error confirmed', 'erreur confirmée'))


def test_prompt_contains_findings_json_only(n5_findings):
    ask = FakeAsk(answer())
    write_texts(n5_findings, 'fr', POLICY, 'k', ask=ask, project='DEMO PROJECT', number=5)
    assert findings_json(n5_findings, project='DEMO PROJECT', number=5) in ask.prompts[0]
    assert 'French' in ask.prompts[0]
    assert '163000' not in ask.prompts[0].replace('163000.00', '')  # only JSON strings, no raw cells


def test_texts_dataclass_fields():
    assert Texts('m', 's', 'b', True).ai_used is True
