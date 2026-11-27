from types import SimpleNamespace
from scripts.llm import ask_json, ask_text


def fake_client(text=None, error=None):
    calls = []

    def generate_content(**kwargs):
        calls.append(kwargs)
        if error:
            raise error
        return SimpleNamespace(text=text)
    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    client.calls = calls
    return client


def test_no_key_returns_none_without_building_a_client():
    def never(key):
        raise AssertionError('client must not be built without a key')
    assert ask_text('hi', None, client_factory=never) is None
    assert ask_json('hi', {}, '', client_factory=never) is None


def test_any_exception_returns_none():
    def boom(key):
        raise RuntimeError('quota')
    assert ask_text('hi', 'k', client_factory=boom) is None
    client = fake_client(error=TimeoutError('slow'))
    assert ask_json('hi', {}, 'k', client_factory=lambda key: client) is None


def test_json_parsed_and_requested_as_json():
    client = fake_client(text='{"vat": "H15"}')
    assert ask_json('p', {'type': 'object'}, 'k', client_factory=lambda key: client) == {'vat': 'H15'}
    assert client.calls[0]['config'].response_mime_type == 'application/json'


def test_bad_or_non_object_json_returns_none():
    for text in ['not json', '["H15"]', None]:
        client = fake_client(text=text)
        assert ask_json('p', {}, 'k', client_factory=lambda key: client) is None


def test_text_is_stripped_and_empty_is_none():
    assert ask_text('p', 'k', client_factory=lambda key: fake_client(text='  memo \n')) == 'memo'
    assert ask_text('p', 'k', client_factory=lambda key: fake_client(text='   ')) is None


def test_ask_json_file_sends_file_part():
    from scripts.llm import ask_json_file
    client = fake_client(text='{"vat": {"value": "1", "label": "TVA"}}')
    answer = ask_json_file('read it', b'\x89PNG', 'image/png', {'type': 'object'}, 'k', client_factory=lambda key: client)
    assert answer == {'vat': {'value': '1', 'label': 'TVA'}}
    contents = client.calls[0]['contents']
    assert contents[0].inline_data.mime_type == 'image/png'
    assert contents[0].inline_data.data == b'\x89PNG'
    assert contents[1] == 'read it'


def test_ask_json_file_failure_returns_none():
    from scripts.llm import ask_json_file
    client = fake_client(error=RuntimeError('quota'))
    assert ask_json_file('p', b'x', 'image/png', {}, 'k', client_factory=lambda key: client) is None
    assert ask_json_file('p', b'x', 'image/png', {}, None) is None


# Phase 3: one tool-calling turn for the agent.
from types import SimpleNamespace  # noqa: E402
from scripts.llm import ask_with_tools, function_response  # noqa: E402

DECLARATIONS = [{'name': 'check_vat', 'description': 'VAT check'}]


def tool_client(calls=(), candidates=True, error=None):
    seen = {}

    def generate_content(**kwargs):
        seen.update(kwargs)
        if error:
            raise error
        content = SimpleNamespace(role='model', parts=['call'])
        return SimpleNamespace(candidates=[SimpleNamespace(content=content)] if candidates else [],
                               function_calls=[SimpleNamespace(name=n, args=a) for n, a in calls] or None)
    return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)), seen


def test_ask_with_tools_returns_content_and_calls_with_tools_config():
    client, seen = tool_client(calls=[('check_vat', {})])
    content, calls = ask_with_tools(['prompt'], DECLARATIONS, 'k', client_factory=lambda key: client)
    assert calls == [('check_vat', {})] and content.role == 'model'
    config = seen['config']
    assert config.tools[0].function_declarations[0].name == 'check_vat'
    assert config.automatic_function_calling.disable is True and config.temperature == 0


def test_ask_with_tools_text_answer_gives_no_calls():
    client, _ = tool_client(calls=[])
    assert ask_with_tools(['p'], DECLARATIONS, 'k', client_factory=lambda key: client)[1] == []


def test_ask_with_tools_failures_return_none():
    def never(key):
        raise AssertionError('client built without key')
    assert ask_with_tools(['p'], DECLARATIONS, None, client_factory=never) is None
    client, _ = tool_client(error=RuntimeError('quota'))
    assert ask_with_tools(['p'], DECLARATIONS, 'k', client_factory=lambda key: client) is None
    client, _ = tool_client(candidates=False)
    assert ask_with_tools(['p'], DECLARATIONS, 'k', client_factory=lambda key: client) is None


def test_function_response_part():
    part = function_response('check_vat', {'severity': 'OK'})
    assert part.function_response.name == 'check_vat' and part.function_response.response == {'severity': 'OK'}
