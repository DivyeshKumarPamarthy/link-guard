"""Plain-text logging and the safe() helper for hostile values.

URLs, filenames and headers come from strangers. Before any of them reaches a log line,
safe() removes characters that could forge log lines, recolour the terminal or hide text
(ANSI escapes, newlines, bidi overrides), and replaces URL secrets with REDACTED
(signed-URL query values, userinfo passwords).
"""

import logging
import re
import unicodedata
from urllib.parse import urlsplit

REDACTED = "REDACTED"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_HANDLER_NAME = "linkguard"

# ESC [ ... final byte (CSI), and ESC ] ... BEL or ESC \ (OSC, e.g. terminal hyperlinks)
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b")

# Invisible characters that change how text is displayed: zero-width, bidi marks,
# embeddings/overrides/isolates, byte-order mark, line/paragraph separators.
_INVISIBLE = set(
    "\u200b\u200c\u200d\u200e\u200f"  # zero-width, LRM, RLM
    "\u202a\u202b\u202c\u202d\u202e"  # bidi embeddings and overrides
    "\u2066\u2067\u2068\u2069"  # bidi isolates
    "\ufeff\u2028\u2029"  # byte-order mark, line and paragraph separators
)


def _strip_unsafe_characters(text: str) -> str:
    text = _ANSI_ESCAPE.sub("", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cc" and ch not in _INVISIBLE)


def _looks_like_url(text: str) -> bool:
    try:
        parts = urlsplit(text)
    except ValueError:
        return False
    return bool(parts.scheme) and (bool(parts.netloc) or parts.scheme == "magnet")


def _redact_query(query: str) -> str:
    """Keep each key, replace each value: '?token=abc&x' -> '?token=REDACTED&REDACTED'."""
    redacted = []
    for pair in re.split(r"([&;])", query):
        if pair in ("&", ";"):
            redacted.append(pair)
        elif "=" in pair:
            redacted.append(pair.split("=", 1)[0] + "=" + REDACTED)
        else:
            redacted.append(REDACTED)
    return "".join(redacted)


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    netloc = parts.netloc
    if "@" in netloc:
        userinfo, host = netloc.rsplit("@", 1)
        user, has_password, _ = userinfo.partition(":")
        netloc = f"{user}:{REDACTED}@{host}" if has_password else netloc
    result = f"{parts.scheme}:"
    if parts.netloc:
        result += f"//{netloc}"
    result += parts.path
    if parts.query:
        result += "?" + _redact_query(parts.query)
    if parts.fragment:
        result += "#" + parts.fragment
    return result


def safe(value: object) -> str:
    """Return `value` as text that is safe to write to a log line."""
    text = _strip_unsafe_characters(str(value))
    if _looks_like_url(text):
        return _redact_url(text)
    return text


def setup_logging(level: str = "INFO") -> None:
    """Send LinkGuard logs to the terminal as plain text. Safe to call more than once."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if handler.get_name() == _HANDLER_NAME:
            root.removeHandler(handler)
    handler = logging.StreamHandler()
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
    logging.getLogger("linkguard").setLevel(level)
