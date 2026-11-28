"""Phase 3 agent: Gemini chooses which checks to run (tool calls), Python runs them, and a guard runs any core
check the AI skipped. The AI never computes or passes an amount: tools take no arguments and return no numbers."""
import time
from dataclasses import dataclass
from . import llm
from .ai_writer import LANGUAGES
from .controller_checks import (CHECK_ORDER, CORE_CHECKS, FIELDS, LABELS, previous_from_history, run_one_check,
                                value_warnings)

TOOLS = {
    'check_retention': ('retention', 'Retention withheld = retention rate × works of the month.'),
    'check_net': ('net', 'Net HT = works of the month − retention.'),
    'check_vat': ('vat', 'VAT = VAT rate × its base (net HT in this project).'),
    'check_ttc': ('ttc', 'Total TTC = net HT + VAT.'),
    'check_cumulative': ('cumulative', 'Cumulative HT = previous cumulative + works of the month.'),
    'check_history': ('history', 'Compare with the previous décompte of the same project: continuity of the '
                                 'cumulative and no missing statement numbers.'),
    'check_contract_ceiling': ('contract_ceiling', 'Optional: is the billed total (cumulative TTC) above the '
                                                   'contract value? Useful when the project is far along.'),
}
TOOL_DECLARATIONS = [{'name': name, 'description': description} for name, (_, description) in TOOLS.items()] + [
    {'name': 'finish', 'description': 'Call when you have run every check this décompte needs.',
     'parameters': {'type': 'object', 'properties': {
         'reason': {'type': 'string', 'description': 'One sentence: which checks you skipped and why.'}}}}]
MAX_TEXT = 300


@dataclass(frozen=True)
class TraceStep:
    who: str          # 'AI', 'guard' or 'Python'
    action: str
    check_id: str | None
    reason: str


@dataclass(frozen=True)
class AgentResult:
    findings: list
    trace: list
    ai_used: bool


def build_prompt(statement, language='fr'):
    values = '\n'.join(f'- {LABELS[f]}: {"missing" if statement.values[f].value is None else statement.values[f].value}'
                       for f in FIELDS)
    return (f'You are a junior auditor checking a construction progress statement (décompte).\n'
            f'Project: {statement.project or "unknown"}; statement number: {statement.number or "unknown"}.\n'
            f'Values read from the document (DH):\n{values}\n\n'
            'Python already knows the contract value, the rates and the previous décomptes; the tools use them. '
            'Choose the checks this décompte needs and call them. Python runs each check and tells you the result. '
            'Never compute amounts yourself. When you are done, call finish with one sentence explaining any check '
            f'you chose not to run, written in {LANGUAGES.get(language, "English")}.')


def _tool_results(parts):
    from google.genai import types
    return types.Content(role='user', parts=parts)


def run_agent(statement, policy, api_key, *, ask=llm.ask_with_tools, previous_lookup=previous_from_history,
              max_turns=8, language='fr', time_budget=60, clock=time.monotonic):
    """time_budget (seconds): past it the AI is stopped and the guard finishes, so n8n gets an answer in time."""
    warnings, filled = value_warnings(statement)
    started = clock()
    results, trace = {}, []

    def run(check):
        if check not in results:
            previous = previous_lookup(filled) if check == 'history' else None
            results[check] = run_one_check(check, filled, policy, previous)

    ai_used = False
    contents = [build_prompt(filled, language)]
    for _ in range(max_turns if api_key else 0):
        if clock() - started > time_budget:
            trace.append(TraceStep('Python', 'AI took too long — the guard completes the checks', None, ''))
            break
        answer = ask(contents, TOOL_DECLARATIONS, api_key)
        if answer is None:
            if ai_used:
                trace.append(TraceStep('Python', 'AI stopped answering — the guard completes the checks', None, ''))
            break
        ai_used = True
        content, calls = answer
        contents.append(content)
        parts, finished = [], not calls
        for name, args in calls:
            if name == 'finish':
                finished = True
                trace.append(TraceStep('AI', 'finished', None, str((args or {}).get('reason', ''))[:MAX_TEXT]))
            elif name not in TOOLS:
                trace.append(TraceStep('AI', 'unknown tool ignored', None, str(name)[:80]))
                parts.append(llm.function_response(str(name), {'error': 'unknown tool'}))
            else:
                check = TOOLS[name][0]
                if check not in results:
                    run(check)
                    trace.append(TraceStep('AI', 'ran', check, ''))
                parts.append(llm.function_response(name, {'results': [
                    {'severity': f.severity, 'title': f.title} for f in results[check]]}))
        if finished:
            break
        contents.append(_tool_results(parts))
    if not ai_used:
        trace.insert(0, TraceStep('Python', 'AI planner offline — all core checks run', None, ''))
    for check in CORE_CHECKS:
        if check not in results:
            run(check)
            trace.append(TraceStep('guard', 'added', check, 'the AI did not run this core check') if ai_used
                         else TraceStep('Python', 'ran', check, ''))
    checked = sorted(sum(results.values(), []), key=lambda f: CHECK_ORDER.index(f.id))
    return AgentResult(warnings + checked, trace, ai_used)
