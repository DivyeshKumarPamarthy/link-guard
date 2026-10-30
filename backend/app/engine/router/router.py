"""Link router (M3, task T3.1, spec §6, decisions D6, D8, D9, D38, D49, D50, D53).

Responsibilities:
1. Clean pasted text (`clean_url`): trim, strip quotes/angle brackets/trailing punctuation,
   normalize backslashes, add `https://` when the scheme is missing, lowercase scheme and host.
2. Classify the link (`classify`, pure function): `http(s)` -> fetch; `magnet:`, `ftp:`,
   `intent:`, or `.torrent` path -> unsupported (`LINK_TYPE_UNSUPPORTED`); any other scheme
   or malformed address -> rejected (`URL_SCHEME_UNSUPPORTED` or `URL_INVALID`).
3. Post-fetch link checks: HTML body sniff (`LINK_IS_WEB_PAGE`, reusing the header check from
   `response_rules.py` without duplicating it), cloud-share page hints (`LINK_CLOUD_SHARE_PAGE`),
   and look-alike / mixed-script domain warnings (`URL_HOMOGRAPH`).
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from urllib.parse import SplitResult, urlsplit, urlunsplit

from app.api.validation import check_submission
from app.contract.models import LinkType, RedirectHop, Status
from app.engine.fetcher.redirects import (
    LINK_KIND_LABELS,
    WEB_SCHEMES,
    Finding,
    unsupported_link_kind,
)
from app.engine.fetcher.response_rules import is_web_page_headers

RouteAction = Literal["fetch", "unsupported", "rejected"]

# Matches an explicit URL scheme at the start of a string, e.g. "https:", "magnet:", "file:".
_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):(.*)$", re.DOTALL)
# Matches "host:port" where there is no scheme (part after ":" starts with digits).
_HOST_PORT_RE = re.compile(r"^[0-9]+(?:[/?#]|$)")
# Trailing sentence punctuation often copied along with a link in prose.
_TRAILING_PUNCT = ".,;!"
# Surrounding wrapper pairs a user may copy around a URL.
_WRAPPERS = (('"', '"'), ("'", "'"), ("<", ">"), ("\u201c", "\u201d"), ("\u2018", "\u2019"))

HTML_SNIFF_BYTES = 1024
_HTML_COMMENT_RE = re.compile(r"^\s*(?:<!--.*?-->\s*|<\?xml[^>]*\?>\s*)*", re.DOTALL)

# Known cloud-sharing hosts (spec §6 P1). Checked only when the response is a web page.
CLOUD_SHARE_HOSTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("drive.google.com", "docs.google.com"), "Google Drive"),
    (("dropbox.com", "www.dropbox.com", "dl.dropbox.com"), "Dropbox"),
    (("onedrive.live.com", "1drv.ms", "sharepoint.com"), "OneDrive"),
    (("mega.nz", "www.mega.nz", "mega.co.nz"), "Mega"),
)

# Cyrillic and Greek letters that look identical or nearly identical to ASCII Latin letters.
_CONFUSABLE_NON_LATIN = frozenset(
    "\u0430\u0441\u0435\u0456\u0458\u043e\u0440\u0455\u0445\u0443\u04cf"
    "\u0410\u0421\u0415\u0406\u0408\u041e\u0420\u0405\u0425\u0423\u04c0"
    "\u03b1\u03bf\u03c1\u03b5\u03b9\u03ba\u03bd\u03c4\u03c5\u03c7"
)


@dataclass(frozen=True)
class Classification:
    """What to do with a cleaned URL (pure decision, no network or DNS)."""

    action: RouteAction
    link_type: LinkType
    finding: Finding | None = None


def _strip_wrappers(text: str) -> str:
    """Peel matching quotes, angle brackets or outer parentheses around the whole link."""
    changed = True
    while changed and len(text) >= 2:
        changed = False
        for left, right in (*_WRAPPERS, ("(", ")")):
            if text.startswith(left) and text.endswith(right):
                text = text[len(left) : len(text) - len(right)].strip()
                changed = True
                break
    return text


def _strip_trailing_punctuation(text: str) -> str:
    """Drop sentence punctuation at the end of a pasted link without breaking valid URLs.

    - Trailing `.`, `,`, `;`, `!` are dropped, except `/.` (such as `http://localhost./`,
      where the `/` is the last character anyway).
    - A trailing `)` or `]` is dropped only when there are more closing than opening
      brackets, so `https://en.wikipedia.org/wiki/Foo_(bar)` and `http://[::1]` stay intact.
    """
    while text:
        if text[-1] in _TRAILING_PUNCT:
            text = text[:-1]
        elif text.endswith(")") and text.count(")") > text.count("("):
            text = text[:-1]
        elif text.endswith("]") and text.count("]") > text.count("["):
            text = text[:-1]
        else:
            break
    return text


def _normalize_slashes(text: str) -> str:
    """Turn `\\` into `/` in the authority and path (before `?` and `#`) for web links."""
    q_pos = text.find("?")
    h_pos = text.find("#")
    cut = min(pos for pos in (q_pos, h_pos, len(text)) if pos != -1)
    head, tail = text[:cut], text[cut:]
    scheme_match = _SCHEME_RE.match(head)
    if (
        scheme_match
        and scheme_match.group(1).lower() not in ("http", "https")
        and not _HOST_PORT_RE.match(scheme_match.group(2))
    ):
        return text
    return head.replace("\\", "/") + tail


def _ensure_scheme(text: str) -> str:
    """Add `https://` when no scheme is present (spec §6).

    `example.com:8080/a` has a colon, but the part after it starts with a port number, so it
    is a host:port without a scheme rather than a `example.com:` scheme.
    """
    if text.startswith("//"):
        return "https:" + text
    match = _SCHEME_RE.match(text)
    if match is None:
        return "https://" + text
    scheme, rest = match.group(1), match.group(2)
    if not rest.startswith("//") and _HOST_PORT_RE.match(rest):
        return "https://" + text
    return f"{scheme.lower()}:{rest}"


def _lowercase_netloc_host(parts: SplitResult) -> str:
    """Lowercase ASCII letters in the host part of `netloc`, keeping userinfo, port and `%XX`."""
    netloc = parts.netloc
    if not netloc:
        return netloc
    userinfo, at, hostport = netloc.rpartition("@")
    if hostport.startswith("["):
        bracket = hostport.find("]")
        if bracket != -1:
            host = hostport[: bracket + 1].lower()
            port = hostport[bracket + 1 :]
            return f"{userinfo}{at}{host}{port}"
    host, colon, port = hostport.partition(":")
    # Keep percent-encoding untouched so `%31` stays `%31` for check_target's `%` check.
    if "%" not in host:
        host = host.lower()
    return f"{userinfo}{at}{host}{colon}{port}"


def clean_url(raw: str, max_length: int | None = None) -> str:
    """Clean raw user input into the normalized URL shown in the report (spec §6).

    Raises `InputError` (`URL_EMPTY`, `URL_TOO_LONG`, `URL_MULTIPLE`) when the input cannot
    start a scan.
    """
    text = check_submission(raw, max_length) if max_length is not None else raw.strip()
    text = _strip_wrappers(text)
    text = _strip_trailing_punctuation(text).strip()
    if max_length is not None or not text:
        check_submission(text, max_length or 2048)
    text = _normalize_slashes(text)
    text = _ensure_scheme(text)
    try:
        parts = urlsplit(text)
    except ValueError:
        return text
    scheme = parts.scheme.lower()
    if parts.netloc:
        return urlunsplit(
            (scheme, _lowercase_netloc_host(parts), parts.path, parts.query, parts.fragment)
        )
    return f"{scheme}:{parts[1]}" if not text.startswith(f"{scheme}://") else text


def classify(url: str) -> Classification:
    """Pure link classifier (spec §6). Decides whether to fetch, reject or report unsupported."""
    kind = unsupported_link_kind(url)
    if kind is not None:
        return Classification(
            action="unsupported",
            link_type=kind,
            finding=Finding("LINK_TYPE_UNSUPPORTED", {"link_kind": LINK_KIND_LABELS[kind]}),
        )
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return Classification(
            action="rejected", link_type=LinkType.http, finding=Finding("URL_INVALID")
        )
    scheme = parts.scheme.lower()
    if not scheme:
        return Classification(
            action="rejected", link_type=LinkType.http, finding=Finding("URL_INVALID")
        )
    if scheme not in WEB_SCHEMES:
        return Classification(
            action="rejected",
            link_type=LinkType.other,
            finding=Finding("URL_SCHEME_UNSUPPORTED", {"scheme": scheme}),
        )
    if not parts.hostname:
        return Classification(
            action="rejected", link_type=LinkType.http, finding=Finding("URL_INVALID")
        )
    return Classification(action="fetch", link_type=LinkType.http, finding=None)


def is_html_body(data: bytes) -> bool:
    """Sniff whether the first 1 KB of the body is an HTML document (spec §6, D9).

    Checks for `<!doctype html` or `<html` after an optional UTF-8/UTF-16 BOM, leading
    whitespace, or leading XML/HTML comments.
    """
    if not data:
        return False
    head = data[:HTML_SNIFF_BYTES]
    encoding = "utf-8"
    if head.startswith(b"\xef\xbb\xbf"):
        head = head[3:]
    elif head.startswith(b"\xff\xfe"):
        head, encoding = head[2:], "utf-16-le"
    elif head.startswith(b"\xfe\xff"):
        head, encoding = head[2:], "utf-16-be"
    text = head.decode(encoding, errors="ignore").lower()
    stripped = _HTML_COMMENT_RE.sub("", text).lstrip()
    if stripped.startswith("<!doctype html"):
        return True
    if stripped.startswith("<html"):
        rest = stripped[5:6]
        return rest in ("", ">", "/", " ", "\t", "\r", "\n")
    return False


def cloud_share_service(host: str | None) -> str | None:
    """Return the cloud-sharing service name if `host` is a known sharing host, else None."""
    if not host:
        return None
    lowered = host.strip().lower().rstrip(".")
    for domains, service in CLOUD_SHARE_HOSTS:
        for domain in domains:
            if lowered == domain or lowered.endswith("." + domain):
                return service
    return None


def _char_script(char: str) -> str | None:
    """The Unicode script family of a letter ('LATIN', 'CYRILLIC', 'GREEK'...), or None."""
    if not char.isalpha():
        return None
    name = unicodedata.name(char, "")
    if not name:
        return "UNKNOWN"
    return name.split(" ", 1)[0]


def is_homograph_host(display_host: str | None, punycode_host: str | None) -> bool:
    """Detect IDN look-alike / mixed-script domain names (`URL_HOMOGRAPH`, spec §8, M3).

    Fires when:
    - an IDN host mixes alphabetic scripts (e.g. Cyrillic `а` + Latin `pple` in `аpple.com`,
      or a Cyrillic label under `.com`), or
    - a non-Latin label uses Cyrillic/Greek characters that are direct visual look-alikes
      of ASCII letters.
    Ordinary single-script Latin IDNs such as `bücher.example` are not flagged as homographs.
    """
    if not display_host or not punycode_host:
        return False
    if display_host.lower() == punycode_host.lower() and display_host.isascii():
        return False
    labels = [label for label in display_host.lower().split(".") if label]
    all_scripts: set[str] = set()
    for label in labels:
        label_scripts = {s for ch in label if (s := _char_script(ch)) is not None}
        if len(label_scripts) > 1:
            return True
        all_scripts |= label_scripts
        if label_scripts - {"LATIN"} and any(ch in _CONFUSABLE_NON_LATIN for ch in label):
            return True
    return len(all_scripts) > 1 and "LATIN" in all_scripts


def redirect_chain_view(hops: Sequence[RedirectHop], status: Status) -> list[RedirectHop]:
    """Build the redirect-chain list for `ScanResult.redirects` (spec §6, D48).

    When the pasted URL itself is rejected at hop 0 (never contacted), `redirects` is empty
    so the Rejected screen does not show a 1-hop chain; when a redirect hop is blocked
    (`SSRF_BLOCKED_AT_HOP`), the chain up to and including the blocked hop is shown.
    """
    if status == Status.rejected and len(hops) <= 1:
        return []
    return list(hops)


__all__ = [
    "Classification",
    "RouteAction",
    "classify",
    "clean_url",
    "cloud_share_service",
    "is_homograph_host",
    "is_html_body",
    "is_web_page_headers",
    "redirect_chain_view",
]
