"""Thin Gemini wrapper. Every failure returns None so callers fall back to templates."""
import json

MODEL = 'gemini-3.1-flash-lite'  # 2.5-flash is closed to new keys; 3.x flash timed out (504) on 2026-11-21.
TIMEOUT_MS = 20_000


def _client(api_key):
    from google import genai
    from google.genai import types
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))


def _generate(contents, api_key, config, client_factory):
    """contents: the prompt string, or [file Part, prompt] for PDF/photo reading."""
    if not api_key:
        return None
    try:
        client = (client_factory or _client)(api_key)
        response = client.models.generate_content(model=MODEL, contents=contents, config=config)
        return response.text
    except Exception:  # Network, quota, key, timeout, SDK changes: all mean "AI unavailable".
        return None


def _json_answer(contents, schema, api_key, client_factory):
    from google.genai import types
    config = types.GenerateContentConfig(response_mime_type='application/json', response_schema=schema or None,
                                         temperature=0)
    text = _generate(contents, api_key, config, client_factory)
    try:
        value = json.loads(text) if text else None
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def ask_json(prompt, schema, api_key, *, client_factory=None):
    return _json_answer(prompt, schema, api_key, client_factory)


def ask_json_file(prompt, data, mime_type, schema, api_key, *, client_factory=None):
    """Send one PDF or image with the prompt; same JSON rules and failure handling as ask_json."""
    if not api_key:
        return None
    try:
        from google.genai import types
        part = types.Part.from_bytes(data=data, mime_type=mime_type)
    except Exception:
        return None
    return _json_answer([part, prompt], schema, api_key, client_factory)


def ask_with_tools(contents, declarations, api_key, *, client_factory=None):
    """One agent turn with function calling (Phase 3). -> (model content to send back unchanged, [(name, args)])
    or None when the AI is unavailable. Python runs every tool; the SDK never calls functions itself."""
    if not api_key:
        return None
    try:
        from google.genai import types
        config = types.GenerateContentConfig(
            tools=[types.Tool(function_declarations=declarations)], temperature=0,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        client = (client_factory or _client)(api_key)
        response = client.models.generate_content(model=MODEL, contents=contents, config=config)
        if not response.candidates:
            return None
        calls = [(call.name, dict(call.args or {})) for call in (response.function_calls or [])]
        return response.candidates[0].content, calls
    except Exception:  # Same rule as _generate: any failure means "AI unavailable".
        return None


def function_response(name, payload):
    from google.genai import types
    return types.Part.from_function_response(name=name, response=payload)


def ask_text(prompt, api_key, *, client_factory=None):
    from google.genai import types
    text = _generate(prompt, api_key, types.GenerateContentConfig(temperature=0.2), client_factory)
    text = (text or '').strip()
    return text or None
