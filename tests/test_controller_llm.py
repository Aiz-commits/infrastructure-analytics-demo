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
