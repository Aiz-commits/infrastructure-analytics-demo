"""Thin Gemini wrapper. Every failure returns None so callers fall back to templates."""
import json

MODEL = 'gemini-2.5-flash'
TIMEOUT_MS = 20_000


def _client(api_key):
    from google import genai
    from google.genai import types
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))


def _generate(prompt, api_key, config, client_factory):
    if not api_key:
        return None
    try:
        client = (client_factory or _client)(api_key)
        response = client.models.generate_content(model=MODEL, contents=prompt, config=config)
        return response.text
    except Exception:  # Network, quota, key, timeout, SDK changes: all mean "AI unavailable".
        return None


def ask_json(prompt, schema, api_key, *, client_factory=None):
    from google.genai import types
    config = types.GenerateContentConfig(response_mime_type='application/json', response_schema=schema or None,
                                         temperature=0)
    text = _generate(prompt, api_key, config, client_factory)
    try:
        value = json.loads(text) if text else None
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def ask_text(prompt, api_key, *, client_factory=None):
    from google.genai import types
    text = _generate(prompt, api_key, types.GenerateContentConfig(temperature=0.2), client_factory)
    text = (text or '').strip()
    return text or None
