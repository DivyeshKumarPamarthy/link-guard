"""Scorer v1 (spec §3 and §9): findings in, an explained outcome out.

A pure function: the same findings always give the same result, with no clock, network or
I/O, so every verdict can be reproduced from a golden file. Weights, severities, wording and
hard rules come from the registry; the thresholds come from config.
"""

import logging
import string
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.contract.models import (
    Confidence,
    DisplayVerdict,
    Reason,
    Scope,
    ScopeMode,
    Severity,
    Status,
    Verdict,
)
from app.core.config import Settings
from app.core.log import safe
from app.engine.fetcher.redirects import Finding
from app.engine.scoring.scope import ReadFacts, build_scope, confidence_for
from app.registry.loader import ReasonCodeSpec, Registry

SEVERITY_RANK = {Severity.info: 0, Severity.low: 1, Severity.medium: 2, Severity.high: 3}
VERDICT_RANK = {Verdict.SAFE: 0, Verdict.SUSPICIOUS: 1, Verdict.UNSAFE: 2}
ENCODING_CODE = "FETCH_UNEXPECTED_ENCODING"
HEADLINE_WHOLE_FILE = "No problems found in the whole file"
HEADLINE_CHECKED_PART = "No issues found in the checked part ({label})"

# A code missing from the registry is a bug (tests fail on it). At runtime it must not crash
# the scan, add risk or make the result look safe, so it counts like an "unable" code.
UNKNOWN_SPEC = ReasonCodeSpec(
    group="unknown",
    weight=0,
    severity=Severity.info,
    outcome="unable",
    message="An internal check returned a result LinkGuard does not recognise ({code}).",
    headline="The check could not be completed",
)


@dataclass(frozen=True)
class Thresholds:
    """Score at or above `suspicious` is SUSPICIOUS, at or above `unsafe` is UNSAFE."""

    suspicious: int
    unsafe: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "Thresholds":
        return cls(suspicious=settings.suspicious_score, unsafe=settings.unsafe_score)


@dataclass(frozen=True)
class ScoreOutcome:
    """The outcome fields of a ScanResult. `unknown_codes` lists codes missing from the
    registry so the caller can log them (see `log_unknown_codes`)."""

    status: Status
    verdict: Verdict | None
    display_verdict: DisplayVerdict
    score: int | None
    confidence: Confidence | None
    scope: Scope
    headline: str
    reasons: list[Reason]
    unknown_codes: tuple[str, ...] = ()


class _KeepMissing(dict[str, object]):
    """Renders a missing evidence key as "unknown" instead of raising mid-scan."""

    def __missing__(self, key: str) -> str:
        return "unknown"


def render(template: str, evidence: Mapping[str, object]) -> str:
    """Fill a registry template. Evidence values are remote data, used only as plain values;
    the template itself always comes from the registry, never from the network."""
    return string.Formatter().vformat(template, (), _KeepMissing(evidence))


def spec_for(code: str, registry: Registry) -> ReasonCodeSpec:
    return registry.codes.get(code, UNKNOWN_SPEC)


def template_evidence(finding: Finding, spec: ReasonCodeSpec) -> Mapping[str, object]:
    """The values a template may use; an unknown code's generic text also names the code."""
    if spec is UNKNOWN_SPEC:
        return {**finding.evidence, "code": finding.code}
    return finding.evidence


def build_reason(finding: Finding, spec: ReasonCodeSpec) -> Reason:
    return Reason(
        code=finding.code,
        severity=spec.severity,
        weight=spec.weight,
        group=spec.group,
        message=render(spec.message, template_evidence(finding, spec)),
        evidence=dict(finding.evidence),
    )


def reason_sort_key(reason: Reason) -> tuple[int, int, str]:
    """Spec §9 order: weight desc, severity desc, code asc. Also the headline tie-break."""
    return (-reason.weight, -SEVERITY_RANK[reason.severity], reason.code)


def compute_score(reasons: Sequence[Reason]) -> int:
    """Spec §9: the highest weight per group, summed, capped at 100. Taking only the
    highest per group stops one fact reported several ways from being counted twice."""
    best_per_group: dict[str, int] = {}
    for reason in reasons:
        best_per_group[reason.group] = max(best_per_group.get(reason.group, 0), reason.weight)
    return min(100, sum(best_per_group.values()))


def status_for(outcomes: set[str]) -> Status:
    """Spec §3: refusing to contact beats "not supported yet"; everything else completed."""
    if "rejected" in outcomes:
        return Status.rejected
    if "unsupported" in outcomes:
        return Status.unsupported
    return Status.completed


def verdict_for(
    score: int, hard_minimums: Sequence[str], outcomes: set[str], thresholds: Thresholds
) -> Verdict:
    """Spec §3 steps 2-4: risk (hard rules and score) always beats missing evidence, and
    missing evidence ("unable" codes) never becomes SAFE."""
    by_score = Verdict.SAFE
    if score >= thresholds.unsafe:
        by_score = Verdict.UNSAFE
    elif score >= thresholds.suspicious:
        by_score = Verdict.SUSPICIOUS
    candidates = [by_score, *(Verdict(v) for v in hard_minimums)]
    verdict = max(candidates, key=VERDICT_RANK.__getitem__)
    if verdict == Verdict.SAFE and "unable" in outcomes:
        return Verdict.UNABLE_TO_VERIFY
    return verdict


def display_verdict_for(
    status: Status, verdict: Verdict | None, scope: Scope, confidence: Confidence | None
) -> DisplayVerdict:
    """Spec §3: plain SAFE only for a whole-file read with confidence medium or better."""
    if status == Status.rejected:
        return DisplayVerdict.REJECTED
    if status == Status.unsupported:
        return DisplayVerdict.UNSUPPORTED
    if verdict == Verdict.SAFE:
        whole_file = scope.mode == ScopeMode.full and confidence != Confidence.low
        return DisplayVerdict.SAFE if whole_file else DisplayVerdict.NO_ISSUES_IN_CHECKED_PART
    return DisplayVerdict(str(verdict))


def headline_for(
    display: DisplayVerdict,
    scope: Scope,
    ranked: Sequence[tuple[Reason, Finding, ReasonCodeSpec]],
) -> str:
    """Spec §3: the top reason's registry headline. A rejected, unsupported or unable result
    takes its headline from the codes that decided it (D49), so a redirect fact never
    headlines a refusal and an info fact never headlines "could not check"."""
    if display == DisplayVerdict.NO_ISSUES_IN_CHECKED_PART:
        return HEADLINE_CHECKED_PART.format(label=scope.label)
    deciding = {
        DisplayVerdict.REJECTED: "rejected",
        DisplayVerdict.UNSUPPORTED: "unsupported",
        DisplayVerdict.UNABLE_TO_VERIFY: "unable",
    }.get(display)
    candidates = [row for row in ranked if deciding is None or row[2].outcome == deciding]
    if not candidates:
        return HEADLINE_WHOLE_FILE
    _, finding, spec = candidates[0]
    return render(spec.headline, template_evidence(finding, spec))


def score_scan(
    findings: Sequence[Finding],
    read: ReadFacts,
    registry: Registry,
    thresholds: Thresholds,
) -> ScoreOutcome:
    """Turn raw findings and read facts into the full explained outcome (spec §3, §9)."""
    rows = [(finding, spec_for(finding.code, registry)) for finding in findings]
    ranked = sorted(
        ((build_reason(finding, spec), finding, spec) for finding, spec in rows),
        key=lambda row: reason_sort_key(row[0]),
    )
    reasons = [reason for reason, _, _ in ranked]
    outcomes: set[str] = {spec.outcome for _, spec in rows}
    unexpected_encoding = any(finding.code == ENCODING_CODE for finding in findings)
    unknown = tuple(sorted({f.code for f, spec in rows if spec is UNKNOWN_SPEC}))

    status = status_for(outcomes)
    scope = build_scope(status, read, unexpected_encoding)
    score: int | None = None
    verdict: Verdict | None = None
    if status == Status.completed:
        score = compute_score(reasons)
        hard = [spec.hard_min_verdict for _, spec in rows if spec.hard_min_verdict]
        verdict = verdict_for(score, hard, outcomes, thresholds)
    confidence = confidence_for(status, verdict, scope, unexpected_encoding)
    display = display_verdict_for(status, verdict, scope, confidence)
    return ScoreOutcome(
        status=status,
        verdict=verdict,
        display_verdict=display,
        score=score,
        confidence=confidence,
        scope=scope,
        headline=headline_for(display, scope, ranked),
        reasons=reasons,
        unknown_codes=unknown,
    )


def log_unknown_codes(outcome: ScoreOutcome, logger: logging.Logger) -> None:
    """Spec §9: a code missing from the registry is logged at ERROR. Kept out of
    `score_scan` so the scorer itself stays free of I/O; the orchestrator calls this."""
    for code in outcome.unknown_codes:
        logger.error("reason code missing from the registry: %s", safe(code))
