"""Phase 3 agent: the AI picks checks, Python runs them, the guard makes sure no core check is missing."""
from decimal import Decimal
from scripts.agent import TOOL_DECLARATIONS, TraceStep, run_agent
from scripts.controller_checks import (EXAMPLES_DIR, FIELDS, SOURCE_FIXED, ReadValue, Statement, from_extractor,
                                       previous_from_history, run_checks)
from scripts.decompte_extractor import extract_decompte
from scripts.policy import load_policy

POLICY = load_policy()
ARITHMETIC = ['check_retention', 'check_net', 'check_vat', 'check_ttc', 'check_cumulative']
ALL_CORE = ARITHMETIC + ['check_history']


def n5():
    return from_extractor(extract_decompte(EXAMPLES_DIR / 'DEMO_DP_N5.xlsx'))


def scripted(*turns):
    """Each turn is a list of tool names (or (name, args)), or None for 'AI unavailable'."""
    asked = []

    def ask(contents, declarations, api_key):
        asked.append(list(contents))
        turn = turns[len(asked) - 1] if len(asked) <= len(turns) else []
        if turn is None:
            return None
        calls = [c if isinstance(c, tuple) else (c, {}) for c in turn]
        return f'model-turn-{len(asked)}', calls
    ask.asked = asked
    return ask


def expected_n5():
    current = n5()
    return run_checks(current, previous_from_history(current), POLICY)


def test_all_core_called_no_guard():
    result = run_agent(n5(), POLICY, 'key', ask=scripted(ALL_CORE, [('finish', {'reason': 'done'})]))
    assert result.findings == expected_n5()
    assert not [s for s in result.trace if s.who == 'guard'] and result.ai_used


def test_guard_adds_skipped_history():
    result = run_agent(n5(), POLICY, 'key', ask=scripted(ARITHMETIC, ['finish']))
    assert TraceStep('guard', 'added', 'history', 'the AI did not run this core check') in result.trace
    assert result.findings == expected_n5()


def test_optional_ceiling_kept_and_ordered_last():
    result = run_agent(n5(), POLICY, 'key', ask=scripted(['check_contract_ceiling'] + ALL_CORE, ['finish']))
    assert result.findings[-1].id == 'contract_ceiling'
    assert result.findings[:-1] == expected_n5()


def test_args_ignored_and_duplicates_run_once():
    turn = [('check_vat', {'vat': 999}), ('check_vat', {'vat': 999})] + ALL_CORE
    result = run_agent(n5(), POLICY, 'key', ask=scripted(turn, ['finish']))
    assert result.findings == expected_n5()
    assert [f.id for f in result.findings].count('vat') == 1


def test_unknown_tool_logged():
    result = run_agent(n5(), POLICY, 'key', ask=scripted(['delete_everything'], ['finish']))
    assert TraceStep('AI', 'unknown tool ignored', None, 'delete_everything') in result.trace
    assert result.findings == expected_n5()


def test_ai_offline():
    result = run_agent(n5(), POLICY, 'key', ask=scripted(None))
    assert result.ai_used is False
    assert result.trace[0] == TraceStep('Python', 'AI planner offline — all core checks run', None, '')
    assert result.findings == expected_n5()
    assert run_agent(n5(), POLICY, None, ask=scripted(ALL_CORE)).ai_used is False


def test_turn_limit():
    ask = scripted(*[['check_vat']] * 20)
    result = run_agent(n5(), POLICY, 'key', ask=ask)
    assert len(ask.asked) == 8
    assert result.findings == expected_n5()


def test_finish_reason_recorded():
    result = run_agent(n5(), POLICY, 'key', ask=scripted(ALL_CORE, [('finish', {'reason': 'contract not near limit'})]))
    assert TraceStep('AI', 'finished', None, 'contract not near limit') in result.trace


def test_model_turn_sent_back_and_no_amounts_in_tool_results():
    ask = scripted(['check_vat'], ['finish'])
    run_agent(n5(), POLICY, 'key', ask=ask)
    second = ask.asked[1]
    assert 'model-turn-1' in second  # Model content returned unchanged (Gemini 3 thought signatures).
    response = second[-1].parts[0].function_response
    assert response.name == 'check_vat' and set(response.response['results'][0]) == {'severity', 'title'}


def test_missing_values_still_warned_by_python():
    values = {f: ReadValue(f, Decimal('1.00'), 'A1', SOURCE_FIXED) for f in FIELDS}
    values['vat'] = ReadValue('vat', None, None, SOURCE_FIXED)
    result = run_agent(Statement('P', None, values), POLICY, 'key', ask=scripted(ALL_CORE, ['finish']))
    assert result.findings[0].id == 'missing:vat'


def test_declarations_have_no_check_parameters():
    names = {d['name'] for d in TOOL_DECLARATIONS}
    assert names == set(ALL_CORE) | {'check_contract_ceiling', 'finish'}
    assert all('parameters' not in d for d in TOOL_DECLARATIONS if d['name'] != 'finish')
