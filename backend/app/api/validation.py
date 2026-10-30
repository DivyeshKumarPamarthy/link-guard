"""Input checks on the submitted text, before any scan is created (spec §2).

Only the three cheap checks that decide between "400 error" and "start a scan" live here.
Full cleaning (quotes, brackets, adding https://) is the router's job (T3.1).
"""

import re

from app.contract.models import ErrorCode

# Something that starts like a link: a scheme such as https:// or magnet:?, or www.
_LINK_START = re.compile(r"^(?:[a-z][a-z0-9+.-]*:(?://|\?)|www\.)", re.IGNORECASE)
# A bare host/path token such as example.com/file.pdf when two bare links are pasted together.
_BARE_LINK = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+/\S*$", re.IGNORECASE)
_WRAP_CHARS = "\"'<>()\u201c\u201d\u2018\u2019"


class InputError(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def has_multiple_urls(text: str) -> bool:
    """True when `text` contains two or more distinct link tokens."""
    tokens = [tok.strip(_WRAP_CHARS) for tok in text.split()]
    tokens = [tok for tok in tokens if tok]
    explicit = [tok for tok in tokens if _LINK_START.match(tok)]
    if len(explicit) > 1:
        return True
    if not explicit:
        bare = [tok for tok in tokens if _BARE_LINK.match(tok)]
        if len(bare) > 1:
            return True
    return False


def check_submission(raw: str, max_length: int) -> str:
    """Return the trimmed URL text.

    Raises InputError with URL_EMPTY, URL_TOO_LONG or URL_MULTIPLE (no scan is created).
    """
    text = raw.strip()
    if not text or not text.strip(_WRAP_CHARS).strip():
        raise InputError(ErrorCode.URL_EMPTY, "Paste a link to check.")
    if len(text) > max_length:
        raise InputError(
            ErrorCode.URL_TOO_LONG, f"This link is longer than {max_length} characters."
        )
    if has_multiple_urls(text):
        raise InputError(ErrorCode.URL_MULTIPLE, "Paste one link at a time.")
    return text
