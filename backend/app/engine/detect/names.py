"""The name the file claims to have, and its extension chain (spec §7, task T1.5).

All of this is remote, hostile data. The name is only ever compared and displayed (escaped by
the web app); it is never used as a path. Control and bidi characters are kept on purpose so
the `EXT_SPOOFED_NAME` check (T2.2) can see them.
"""

from dataclasses import dataclass
from urllib.parse import unquote, unquote_to_bytes, urlsplit

from app.contract.models import NameSource

# Charsets RFC 5987 requires recipients to support; anything else is ignored.
RFC5987_CHARSETS = {"utf-8": "utf-8", "iso-8859-1": "latin-1"}


@dataclass(frozen=True)
class ClaimedName:
    """`display` keeps the original case for the report; `compare` is lowercased for checks."""

    display: str
    compare: str
    source: NameSource


def split_parameters(header: str) -> list[tuple[str, str]]:
    """Split `type; a=1; b="x;y"` into lowercase names and raw values, respecting quotes."""
    parameters: list[tuple[str, str]] = []
    parts: list[str] = []
    current: list[str] = []
    in_quotes = False
    escaped = False
    for char in header:
        if escaped:
            escaped = False
        elif char == "\\" and in_quotes:
            escaped = True
        elif char == '"':
            in_quotes = not in_quotes
        elif char == ";" and not in_quotes:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    for part in parts[1:]:  # parts[0] is the disposition type (attachment / inline)
        name, sep, value = part.partition("=")
        if sep:
            parameters.append((name.strip().lower(), value.strip()))
    return parameters


def unquote_header_value(value: str) -> str:
    """RFC 6266 quoted-string: drop quotes and backslash escapes; tolerate a missing end quote."""
    if not value.startswith('"'):
        return value
    result: list[str] = []
    escaped = False
    for char in value[1:]:
        if escaped:
            result.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            break
        else:
            result.append(char)
    return "".join(result)


def decode_rfc5987(value: str) -> str | None:
    """`UTF-8'lang'%E2%82%AC.txt` → "€.txt". Unknown charset or bad bytes → None."""
    charset, sep1, rest = value.partition("'")
    _language, sep2, encoded = rest.partition("'")
    encoding = RFC5987_CHARSETS.get(charset.strip().lower())
    if not (sep1 and sep2 and encoding):
        return None
    try:
        return unquote_to_bytes(encoded).decode(encoding)
    except UnicodeDecodeError:
        return None


def filename_from_content_disposition(header: str | None) -> str | None:
    """The filename a Content-Disposition header gives; `filename*` wins (RFC 6266 §4.3).

    The plain `filename` is percent-decoded later like a URL path; the `filename*` value is
    already decoded here, so callers must not decode it again.
    """
    return _content_disposition_name(header)[0]


def _content_disposition_name(header: str | None) -> tuple[str | None, bool]:
    """(name, already_decoded). Never raises: malformed parts are skipped."""
    if not header:
        return None, False
    parameters = split_parameters(header)
    for name, value in parameters:
        if name == "filename*":
            decoded = decode_rfc5987(value)
            if decoded:
                return decoded, True
    for name, value in parameters:
        if name == "filename":
            plain = unquote_header_value(value)
            if plain:
                return plain, False
    return None, False


def normalize_name(raw: str, decode_percent: bool) -> str | None:
    """Last path segment, without trailing dots/spaces (Windows ignores them). None if empty.

    Both `/` and `\\` count as separators, so `..\\..\\evil.exe` becomes `evil.exe`.
    """
    name = unquote(raw, errors="replace") if decode_percent else raw
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = name.rstrip(". ")
    return name or None


def url_path_name(url: str | None) -> str | None:
    """The last segment of a URL's path; query and fragment are ignored."""
    if not url:
        return None
    try:
        path = urlsplit(url).path
    except ValueError:
        return None
    return normalize_name(path, decode_percent=True)


def claimed_name(
    content_disposition: str | None, final_url: str | None, original_url: str | None
) -> ClaimedName | None:
    """Pick the claimed name in the spec §7 order: header, final URL, original URL."""
    header_name, already_decoded = _content_disposition_name(content_disposition)
    candidates = [
        (
            normalize_name(header_name, decode_percent=not already_decoded)
            if header_name
            else None,
            NameSource.content_disposition,
        ),
        (url_path_name(final_url), NameSource.final_url),
        (url_path_name(original_url), NameSource.original_url),
    ]
    for name, source in candidates:
        if name:
            return ClaimedName(display=name, compare=name.lower(), source=source)
    return None


def extension_chain(name: str) -> tuple[str, ...]:
    """All extensions in order, lowercased: `Invoice.PDF.exe` → ("pdf", "exe").

    The last item is the claimed extension; earlier ones feed the double-extension check.
    Leading dots mark hidden files (`.bashrc`), not extensions.
    """
    parts = [part for part in name.lower().lstrip(".").split(".") if part]
    return tuple(parts[1:])
