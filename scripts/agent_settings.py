"""Phase 3 settings, read from the git-ignored .streamlit/secrets.toml. The API refuses to start without them."""
import re
import tomllib
from dataclasses import dataclass
from email.utils import parseaddr
from pathlib import Path
from .policy import ROOT

SECRETS = ROOT / '.streamlit' / 'secrets.toml'


@dataclass(frozen=True)
class Settings:
    api_key: str
    pin: str
    allowed_senders: frozenset
    review_base_url: str
    gemini_key: str | None
    database_url: str | None
    data_dir: Path


def sender_address(raw):
    """'Name <A@Gmail.com>' -> 'a@gmail.com'."""
    return parseaddr(raw or '')[1].strip().lower()


def load_settings(path=SECRETS, data_dir=ROOT / 'data'):
    try:
        values = tomllib.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f'Cannot read {Path(path).name} (.streamlit/secrets.toml). See the Phase 3 guide.') from error
    api_key = str(values.get('AGENT_API_KEY') or '')
    if len(api_key) < 24:
        raise ValueError('AGENT_API_KEY is missing or shorter than 24 characters.')
    pin = str(values.get('REVIEWER_PIN') or '')
    if not re.fullmatch(r'\d{6}', pin):
        raise ValueError('REVIEWER_PIN must be exactly 6 digits.')
    senders = frozenset(sender_address(s) for s in values.get('ALLOWED_SENDERS') or [] if sender_address(s))
    if not senders:
        raise ValueError('ALLOWED_SENDERS must list at least one email address.')
    base = str(values.get('REVIEW_BASE_URL') or '').rstrip('/')
    if not re.match(r'^https?://[^/\s]+', base):
        raise ValueError('REVIEW_BASE_URL must start with http:// or https:// (e.g. http://192.168.1.5:8000).')
    return Settings(api_key, pin, senders, base, values.get('GEMINI_API_KEY') or None,
                    values.get('DATABASE_URL') or None, Path(data_dir))
