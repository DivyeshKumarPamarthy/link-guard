"""Tests for safe() and logging setup (task T0.3, spec §13, CLAUDE.md safety rules)."""

import logging

import pytest

from app.core.log import REDACTED, safe, setup_logging


def test_plain_text_is_unchanged() -> None:
    assert safe("movie.mp4") == "movie.mp4"


def test_non_string_values_are_converted() -> None:
    assert safe(404) == "404"
    assert safe(None) == "None"


# --- signed URLs: query values are secrets, keys stay readable -------------------------


def test_signed_url_query_values_are_redacted() -> None:
    url = (
        "https://bucket.s3.amazonaws.com/file.zip"
        "?X-Amz-Credential=AKIAEXAMPLE&X-Amz-Signature=abc123&X-Amz-Expires=3600"
    )
    assert safe(url) == (
        "https://bucket.s3.amazonaws.com/file.zip"
        f"?X-Amz-Credential={REDACTED}&X-Amz-Signature={REDACTED}&X-Amz-Expires={REDACTED}"
    )


def test_token_parameter_is_redacted() -> None:
    assert safe("http://files.example/a.pdf?token=s3cr3t") == (
        f"http://files.example/a.pdf?token={REDACTED}"
    )


def test_bare_query_value_without_key_is_redacted() -> None:
    assert safe("https://files.example/a.pdf?s3cr3t") == f"https://files.example/a.pdf?{REDACTED}"


def test_empty_value_and_semicolon_separators() -> None:
    assert safe("https://x.example/?a=&b=2;c=3") == (
        f"https://x.example/?a={REDACTED}&b={REDACTED};c={REDACTED}"
    )


def test_fragment_is_kept_after_redacted_query() -> None:
    assert safe("https://x.example/p?k=v#part") == f"https://x.example/p?k={REDACTED}#part"


def test_url_without_query_is_unchanged() -> None:
    assert safe("https://files.example/movie.mp4") == "https://files.example/movie.mp4"


def test_userinfo_password_is_redacted() -> None:
    assert safe("http://bob:hunter2@files.example/a") == (f"http://bob:{REDACTED}@files.example/a")


def test_redirect_location_value_is_redacted_too() -> None:
    # Location headers are URLs as well; they go through the same function.
    assert REDACTED in safe("https://cdn.example/x?sig=abc")
    assert "abc" not in safe("https://cdn.example/x?sig=abc")


def test_question_mark_in_non_url_text_is_not_touched() -> None:
    assert safe("why? because") == "why? because"


# --- control characters: logs must not be forgeable or hide tricks --------------------


def test_ansi_escape_sequences_are_stripped() -> None:
    # A filename that would turn the terminal red and clear the line
    assert safe("evil\x1b[31mRED\x1b[0m\x1b[2K.exe") == "evilRED.exe"


def test_ansi_osc_sequence_is_stripped() -> None:
    # OSC 8 hyperlink sequence ends with BEL or ESC \
    assert safe("a\x1b]8;;http://x\x07b\x1b]8;;\x1b\\c") == "abc"


def test_newlines_cannot_forge_a_log_line() -> None:
    assert safe("ok.pdf\nINFO fake: scan SAFE") == "ok.pdfINFO fake: scan SAFE"
    assert "\r" not in safe("a\rb")


def test_rtl_override_is_stripped() -> None:
    # "invoice\u202efdp.exe" displays as "invoiceexe.pdf" in many terminals
    assert safe("invoice\u202efdp.exe") == "invoicefdp.exe"


@pytest.mark.parametrize(
    "char",
    ["\u200b", "\u200e", "\u200f", "\u202a", "\u202d", "\u2066", "\u2069", "\ufeff", "\u2028"],
)
def test_zero_width_and_bidi_characters_are_stripped(char: str) -> None:
    assert safe(f"a{char}b") == "ab"


def test_nul_and_c1_controls_are_stripped() -> None:
    assert safe("a\x00b\x85c\x9bd") == "abcd"


def test_tab_is_stripped_too() -> None:
    assert safe("a\tb") == "ab"


def test_control_characters_inside_url_query_are_stripped_and_redacted() -> None:
    result = safe("https://x.example/?t=ab\x1b[31mc")
    assert result == f"https://x.example/?t={REDACTED}"


def test_unicode_letters_are_kept() -> None:
    assert safe("фильм.mp4 — 映画") == "фильм.mp4 — 映画"


# --- logging setup --------------------------------------------------------------------


def test_magnet_link_query_is_redacted() -> None:
    # Tracker URLs inside a magnet link can carry private passkeys
    assert safe("magnet:?xt=urn:btih:abc&tr=http://t.example/passkey") == (
        f"magnet:?xt={REDACTED}&tr={REDACTED}"
    )


def test_setup_logging_is_plain_text_and_idempotent(capsys: pytest.CaptureFixture[str]) -> None:
    try:
        setup_logging("INFO")
        setup_logging("INFO")  # calling twice must not duplicate handlers
        logging.getLogger("linkguard.test").info("hello %s", safe("https://h.example/?k=v"))
        err = capsys.readouterr().err
    finally:
        for handler in list(logging.getLogger().handlers):
            if handler.get_name() == "linkguard":
                logging.getLogger().removeHandler(handler)
    assert err.count("hello") == 1
    assert "INFO linkguard.test: hello" in err
    assert f"k={REDACTED}" in err
    assert "k=v" not in err
