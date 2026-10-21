"""Unit tests for scorer v1 (spec §3, §9). Golden cases live in tests/golden/."""

import logging
import uuid
from datetime import UTC, datetime

import pytest

from app.contract.models import (
    Confidence,
    DisplayVerdict,
    ScanResult,
    ScopeMode,
    State,
    Status,
    Verdict,
)
from app.core.config import Settings
from app.engine.fetcher.redirects import Finding
from app.engine.scoring.scope import ReadFacts, format_size
from app.engine.scoring.scorer import Thresholds, log_unknown_codes, score_scan
from app.registry.loader import get_registry, parse_registry

THRESHOLDS = Thresholds(suspicious=30, unsafe=60)
FULL = ReadFacts(bytes_read=100, total_size=100, range_supported=True, ended="complete")

TEST_REGISTRY = parse_registry(
    """
rules_version: "0.0.1"
codes:
  TYPE_A: {group: type, weight: 29, severity: low, outcome: risk, message: "a", headline: "A"}
  TYPE_B: {group: type, weight: 30, severity: low, outcome: risk, message: "b", headline: "B"}
  TYPE_C: {group: type, weight: 59, severity: medium, outcome: risk, message: "c", headline: "C"}
  TYPE_D: {group: type, weight: 60, severity: high, outcome: risk, message: "d", headline: "D"}
"""
)


def score(codes: list[str], read: ReadFacts = FULL, registry=None):  # type: ignore[no-untyped-def]
    findings = [Finding(code) for code in codes]
    return score_scan(findings, read, registry or get_registry(), THRESHOLDS)


@pytest.mark.parametrize(
    ("code", "expected_score", "expected_verdict"),
    [
        ("TYPE_A", 29, Verdict.SAFE),
        ("TYPE_B", 30, Verdict.SUSPICIOUS),
        ("TYPE_C", 59, Verdict.SUSPICIOUS),
        ("TYPE_D", 60, Verdict.UNSAFE),
    ],
)
def test_threshold_edges_are_inclusive(
    code: str, expected_score: int, expected_verdict: Verdict
) -> None:
    outcome = score([code], registry=TEST_REGISTRY)
    assert (outcome.score, outcome.verdict) == (expected_score, expected_verdict)


def test_thresholds_come_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LG_SUSPICIOUS_SCORE", "20")
    monkeypatch.setenv("LG_UNSAFE_SCORE", "50")
    assert Thresholds.from_settings(Settings()) == Thresholds(suspicious=20, unsafe=50)


def test_thresholds_must_be_ordered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LG_SUSPICIOUS_SCORE", "60")
    monkeypatch.setenv("LG_UNSAFE_SCORE", "60")
    with pytest.raises(ValueError):
        Settings()


def test_score_takes_the_highest_weight_per_group_and_keeps_every_reason() -> None:
    outcome = score(["EXT_DOUBLE", "EXT_RISKY", "TYPE_CONTENT_TYPE_MISMATCH"])
    assert outcome.score == 40 + 10
    assert [r.code for r in outcome.reasons] == [
        "EXT_DOUBLE",
        "EXT_RISKY",
        "TYPE_CONTENT_TYPE_MISMATCH",
    ]


def test_score_is_capped_at_100() -> None:
    registry = parse_registry(
        """
rules_version: "0.0.1"
codes:
  TYPE_X: {group: type, weight: 80, severity: high, outcome: risk, message: "x", headline: "X"}
  REDIR_Y: {group: redirect, weight: 80, severity: high, outcome: risk, message: "y", headline: "Y"}
"""
    )
    assert score(["TYPE_X", "REDIR_Y"], registry=registry).score == 100


def test_hard_rule_raises_the_verdict_even_with_a_low_score() -> None:
    registry = parse_registry(
        """
rules_version: "0.0.1"
codes:
  TYPE_H: {group: type, weight: 1, severity: high, outcome: risk, hard_min_verdict: SUSPICIOUS,
           message: "h", headline: "H"}
  FETCH_U: {group: fetch, weight: 0, severity: info, outcome: unable, message: "u", headline: "U"}
"""
    )
    outcome = score(["TYPE_H", "FETCH_U"], registry=registry)
    assert (outcome.score, outcome.verdict) == (1, Verdict.SUSPICIOUS)


def test_unable_never_becomes_safe_and_risk_beats_unable() -> None:
    assert score(["FETCH_HTTP_ERROR"]).verdict == Verdict.UNABLE_TO_VERIFY
    assert score(["FETCH_HTTP_ERROR", "EXT_DOUBLE"]).verdict == Verdict.SUSPICIOUS


def test_info_codes_do_not_change_a_safe_verdict() -> None:
    outcome = score(["REDIR_CROSS_DOMAIN", "TYPE_UNKNOWN"])
    assert (outcome.verdict, outcome.display_verdict) == (Verdict.SAFE, DisplayVerdict.SAFE)


def test_reason_order_is_weight_then_severity_then_code() -> None:
    codes = [
        "REDIR_CROSS_DOMAIN",
        "TYPE_CONTENT_TYPE_MISMATCH",
        "REDIR_DOWNGRADE",
        "TYPE_MISMATCH_EXEC",
    ]
    ordered = [r.code for r in score(codes).reasons]
    assert ordered == [
        "TYPE_MISMATCH_EXEC",
        "REDIR_DOWNGRADE",
        "TYPE_CONTENT_TYPE_MISMATCH",
        "REDIR_CROSS_DOMAIN",
    ]


@pytest.mark.parametrize(
    "read",
    [
        ReadFacts(bytes_read=50, total_size=100, range_supported=True, ended="cap"),
        ReadFacts(bytes_read=50, total_size=None, range_supported=False, ended="interrupted"),
        ReadFacts(bytes_read=100, total_size=200, range_supported=False, ended="complete"),
        ReadFacts(headers_only=True),
        ReadFacts(bytes_read=0, ended="complete"),
    ],
)
def test_anything_but_a_full_read_never_displays_safe(read: ReadFacts) -> None:
    outcome = score([], read)
    assert outcome.verdict == Verdict.SAFE
    assert outcome.display_verdict == DisplayVerdict.NO_ISSUES_IN_CHECKED_PART
    assert outcome.headline.startswith("No issues found in the checked part (")


def test_unexpected_encoding_forces_partial_scope_and_low_confidence() -> None:
    outcome = score_scan(
        [Finding("FETCH_UNEXPECTED_ENCODING", {"encoding": "gzip"})],
        FULL,
        get_registry(),
        THRESHOLDS,
    )
    assert outcome.scope.mode == ScopeMode.partial
    assert outcome.confidence == Confidence.low
    assert outcome.display_verdict == DisplayVerdict.NO_ISSUES_IN_CHECKED_PART


@pytest.mark.parametrize(
    ("read", "confidence"),
    [
        (FULL, Confidence.high),
        (
            ReadFacts(bytes_read=50, total_size=100, range_supported=True, ended="cap"),
            Confidence.medium,
        ),
        (
            ReadFacts(bytes_read=50, total_size=None, range_supported=True, ended="cap"),
            Confidence.low,
        ),
        (
            ReadFacts(bytes_read=50, total_size=100, range_supported=False, ended="cap"),
            Confidence.low,
        ),
    ],
)
def test_confidence_rules(read: ReadFacts, confidence: Confidence) -> None:
    assert score([], read).confidence == confidence


def test_unable_with_a_full_read_is_low_confidence() -> None:
    assert score(["LINK_IS_WEB_PAGE"]).confidence == Confidence.low


def test_rejected_beats_everything_and_has_no_verdict_score_or_confidence() -> None:
    outcome = score(["TYPE_MISMATCH_EXEC", "URL_PRIVATE_ADDRESS"])
    assert outcome.status == Status.rejected
    assert (outcome.verdict, outcome.score, outcome.confidence) == (None, None, None)
    assert outcome.scope.mode == ScopeMode.none
    assert outcome.headline == "Not scanned: this address points inside a private network"


def test_messages_and_headlines_are_rendered_from_the_registry() -> None:
    finding = Finding("FETCH_HTTP_ERROR", {"status": 404})
    outcome = score_scan([finding], ReadFacts(), get_registry(), THRESHOLDS)
    assert (
        outcome.reasons[0].message == "The server answered 404, so the file could not be fetched."
    )
    assert outcome.reasons[0].evidence == {"status": 404}
    assert outcome.headline == "The server answered 404, so the file could not be checked"


def test_missing_evidence_does_not_crash() -> None:
    outcome = score(["FETCH_HTTP_ERROR"])
    assert (
        outcome.reasons[0].message
        == "The server answered unknown, so the file could not be fetched."
    )


def test_evidence_braces_are_not_reinterpreted_as_templates() -> None:
    finding = Finding("FETCH_DNS_ERROR", {"host": "{status}.example"})
    outcome = score_scan([finding], ReadFacts(), get_registry(), THRESHOLDS)
    assert outcome.reasons[0].message == "The address {status}.example could not be found."


def test_unknown_code_weighs_nothing_never_looks_safe_and_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    outcome = score(["TYPE_NOT_IN_REGISTRY"])
    assert outcome.unknown_codes == ("TYPE_NOT_IN_REGISTRY",)
    assert outcome.reasons[0].weight == 0
    assert outcome.verdict == Verdict.UNABLE_TO_VERIFY
    assert "TYPE_NOT_IN_REGISTRY" in outcome.reasons[0].message
    with caplog.at_level(logging.ERROR):
        log_unknown_codes(outcome, logging.getLogger("linkguard.test"))
    assert "TYPE_NOT_IN_REGISTRY" in caplog.text


def test_scorer_is_pure_same_input_same_output() -> None:
    findings = [
        Finding("EXT_DOUBLE", {"decoy_ext": "pdf", "real_ext": "exe"}),
        Finding("FETCH_TIMEOUT"),
    ]
    first = score_scan(findings, FULL, get_registry(), THRESHOLDS)
    second = score_scan(list(reversed(findings)), FULL, get_registry(), THRESHOLDS)
    assert first == second
    assert findings[0].evidence == {"decoy_ext": "pdf", "real_ext": "exe"}


@pytest.mark.parametrize("code", sorted(get_registry().codes))
@pytest.mark.parametrize(
    "read",
    [
        FULL,
        ReadFacts(bytes_read=50, total_size=100, ended="cap"),
        ReadFacts(headers_only=True),
        ReadFacts(),
    ],
)
def test_every_registry_code_gives_a_result_the_contract_accepts(
    code: str, read: ReadFacts
) -> None:
    """The ScanResult validator (D29) is the last guard against dishonest results."""
    spec = get_registry().codes[code]
    finding = Finding(code, {key: "x" for key in spec.evidence})
    outcome = score_scan([finding], read, get_registry(), THRESHOLDS)
    ScanResult(
        scan_id=uuid.uuid4(),
        state=State.done,
        status=outcome.status,
        input_url="https://example.com/f",
        verdict=outcome.verdict,
        display_verdict=outcome.display_verdict,
        score=outcome.score,
        confidence=outcome.confidence,
        scope=outcome.scope,
        headline=outcome.headline,
        reasons=outcome.reasons,
        engine_version="1.0.0",
        rules_version="1.0.0",
        created_at=datetime(2026, 10, 21, tzinfo=UTC),
    )
    if outcome.display_verdict == DisplayVerdict.SAFE:
        assert outcome.scope.mode == ScopeMode.full


@pytest.mark.parametrize(
    ("n", "text"),
    [
        (0, "0 bytes"),
        (1, "1 byte"),
        (1023, "1023 bytes"),
        (48213, "47 KB"),
        (5_242_880, "5 MB"),
        (209_715_200, "200 MB"),
        (1_610_612_736, "1.5 GB"),
    ],
)
def test_format_size(n: int, text: str) -> None:
    assert format_size(n) == text


# --- D54: full scope needs a KNOWN length ------------------------------------------------------


def test_body_read_until_close_with_no_length_is_partial() -> None:
    """D54: without a Content-Length, a Content-Range total or a terminating chunk, nothing
    proves the whole file arrived, so a clean result must not show plain Safe."""
    read = ReadFacts(bytes_read=4096, total_size=None, range_supported=False, ended="complete")
    outcome = score([], read)
    assert outcome.scope.mode == ScopeMode.partial
    assert outcome.scope.label == "First 4 KB (total size unknown)"
    assert outcome.display_verdict == DisplayVerdict.NO_ISSUES_IN_CHECKED_PART
    assert outcome.confidence == Confidence.low


def test_chunked_body_that_ended_cleanly_is_full() -> None:
    """The fetcher sets total_size = bytes read when a chunked body ends with its terminating
    chunk (D54), so such a file is a whole-file read."""
    read = ReadFacts(bytes_read=4096, total_size=4096, range_supported=False, ended="complete")
    outcome = score([], read)
    assert outcome.scope.mode == ScopeMode.full
    assert outcome.display_verdict == DisplayVerdict.SAFE
    assert outcome.confidence == Confidence.high
