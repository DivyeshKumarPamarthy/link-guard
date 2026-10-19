"""Input checks on the submitted text, before any scan is created (spec §2).

Only the three cheap checks that decide between "400 error" and "start a scan" live here.
Full cleaning (quotes, brackets, adding https://) is the router's job (T3.1).
"""

import re

from app.contract.models import ErrorCode

# Something that starts like a link: a scheme such as https:// or magnet:?, or www.
_LINK_START = re.compile(r"^(?:[a-z][a-z0-9+.-]*:(?://|\?)|www\.)", re.IGNORECASE)


class InputError(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def check_submission(raw: str, max_length: int) -> str:
    """Return the trimmed URL text.

    Raises InputError with URL_EMPTY, URL_TOO_LONG or URL_MULTIPLE (no scan is created).
    """
    text = raw.strip()
    if not text:
        raise InputError(ErrorCode.URL_EMPTY, "Paste a link to check.")
    if len(text) > max_length:
        raise InputError(
            ErrorCode.URL_TOO_LONG, f"This link is longer than {max_length} characters."
        )
    link_like = [token for token in text.split() if _LINK_START.match(token)]
    if len(link_like) > 1:
        raise InputError(ErrorCode.URL_MULTIPLE, "Paste one link at a time.")
    return text
