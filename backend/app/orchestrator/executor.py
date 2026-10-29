"""In-process scan executor and JSON-serializable seam (task T2.4, D59, D66, D67, D75).

The executor runs Router -> Fetcher -> Detectors and returns plain JSON-compatible data
(`RawScanReport.model_dump(mode="json")`). It never scores findings and never touches the
database: the orchestrator validates the returned data, runs the pure scorer (`score_scan`),
and persists the final `ScanResult`. Phase 2 can swap this executor for a container runner
without changing the API, contract, orchestrator or scorer.
"""

import time
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.contract.models import FileInfo, LinkType, RedirectHop, ScopeMode, Status
from app.core.config import Settings
from app.engine.detect.mismatch import media_type, run_mismatch_checks
from app.engine.detect.names import claimed_name
from app.engine.detect.signatures import detect_type, refine_zip_subtype
from app.engine.fetcher.fetch import Ended, FetchResult, fetch
from app.engine.fetcher.redirects import LINK_KIND_LABELS, Finding
from app.engine.fetcher.resolver import Resolver, StaticHostsResolver, SystemResolver
from app.engine.fetcher.targets import TargetRejected, normalize_host
from app.engine.router.router import (
    classify,
    clean_url,
    cloud_share_service,
    is_homograph_host,
    is_html_body,
    redirect_chain_view,
)
from app.engine.scoring.scope import ReadFacts, build_scope
from app.orchestrator.mock_executor import ExecutorOutput

REJECTED_CODES = frozenset(
    {
        "URL_PRIVATE_ADDRESS",
        "URL_USERINFO",
        "URL_PORT_BLOCKED",
        "URL_SCHEME_UNSUPPORTED",
        "URL_INVALID",
        "SSRF_BLOCKED_AT_HOP",
        "REDIR_BAD_TARGET",
    }
)
UNSUPPORTED_CODES = frozenset({"LINK_TYPE_UNSUPPORTED"})
KIND_BY_LABEL = {label: kind for kind, label in LINK_KIND_LABELS.items()}


class FindingRecord(BaseModel):
    """JSON-serializable representation of a `Finding` across the executor seam."""

    model_config = ConfigDict(extra="forbid")

    code: str
    evidence: dict[str, JsonValue] = Field(default_factory=dict)

    def to_finding(self) -> Finding:
        return Finding(code=self.code, evidence=dict(self.evidence))


class ReadFactsRecord(BaseModel):
    """JSON-serializable representation of `ReadFacts` across the executor seam (D66)."""

    model_config = ConfigDict(extra="forbid")

    bytes_read: int = Field(default=0, ge=0)
    total_size: int | None = Field(default=None, ge=0)
    range_supported: bool = False
    ended: Ended = "error"
    headers_only: bool = False

    def to_read_facts(self) -> ReadFacts:
        return ReadFacts(
            bytes_read=self.bytes_read,
            total_size=self.total_size,
            range_supported=self.range_supported,
            ended=self.ended,
            headers_only=self.headers_only,
        )


class RawScanReport(BaseModel):
    """Validated JSON-serializable output of a real executor before scoring."""

    model_config = ConfigDict(extra="forbid")

    normalized_url: str
    final_url: str | None = None
    display_host: str | None = None
    punycode_host: str | None = None
    link_type: LinkType = LinkType.http
    findings: list[FindingRecord] = Field(default_factory=list)
    read: ReadFactsRecord = Field(default_factory=ReadFactsRecord)
    file: FileInfo | None = None
    redirects: list[RedirectHop] = Field(default_factory=list)
    unavailable_signals: list[str] = Field(default_factory=list)
    timings_ms: dict[str, int] = Field(default_factory=dict)


def make_resolver(settings: Settings) -> Resolver:
    """System DNS, wrapped with `LG_STATIC_HOSTS` when configured in test/demo."""
    system = SystemResolver()
    if settings.static_hosts:
        return StaticHostsResolver(settings.static_hosts, fallback=system)
    return system


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _try_extract_hosts(url: str) -> tuple[str | None, str | None]:
    """Best-effort host extraction for URLs that stopped before `Target` creation."""
    try:
        raw_host = urlsplit(url).hostname
        if not raw_host:
            return None, None
        host = normalize_host(raw_host)
        return host.display, host.punycode
    except (TargetRejected, ValueError):
        return None, None


def _collect_fetch_findings(fetched: FetchResult, settings: Settings) -> list[Finding]:
    """Gather findings from `FetchResult`, dropping `FETCH_INTERRUPTED` only when the
    partial bytes already identify a file type (spec §8 note, decision D59)."""
    findings = list(fetched.findings)
    if fetched.failure is None:
        return findings
    if fetched.failure.code == "FETCH_INTERRUPTED" and fetched.body_head:
        if detect_type(fetched.body_head, settings).type != "unknown":
            return findings
    findings.append(fetched.failure)
    return findings


def _unsupported_link_type(findings: list[Finding], changed_host: bool) -> LinkType:
    for finding in findings:
        if finding.code == "LINK_TYPE_UNSUPPORTED":
            label = str(finding.evidence.get("link_kind", ""))
            if label in KIND_BY_LABEL:
                return KIND_BY_LABEL[label]
    return LinkType.shortened if changed_host else LinkType.http


class InProcessExecutor:
    """Phase 1 executor: runs Router -> Fetcher -> Detectors in-process."""

    def __init__(self, settings: Settings, resolver: Resolver | None = None) -> None:
        self.settings = settings
        self.resolver = resolver or make_resolver(settings)

    async def run(self, url: str) -> ExecutorOutput:
        started = time.monotonic()
        normalized = clean_url(url)
        route = classify(normalized)

        if route.action == "unsupported":
            assert route.finding is not None
            report = RawScanReport(
                normalized_url=normalized,
                link_type=route.link_type,
                findings=[
                    FindingRecord(code=route.finding.code, evidence=dict(route.finding.evidence))
                ],
                read=ReadFactsRecord(),
                timings_ms={"total": _elapsed_ms(started)},
            )
            return report.model_dump(mode="json")

        if route.action == "rejected":
            assert route.finding is not None
            display_host, punycode_host = _try_extract_hosts(normalized)
            report = RawScanReport(
                normalized_url=normalized,
                display_host=display_host,
                punycode_host=punycode_host,
                link_type=route.link_type,
                findings=[
                    FindingRecord(code=route.finding.code, evidence=dict(route.finding.evidence))
                ],
                read=ReadFactsRecord(),
                timings_ms={"total": _elapsed_ms(started)},
            )
            return report.model_dump(mode="json")

        fetched = await fetch(normalized, self.settings, self.resolver)
        findings = _collect_fetch_findings(fetched, self.settings)

        display_host = fetched.display_host
        punycode_host = fetched.punycode_host
        if display_host is None:
            last_url = fetched.hops[-1].url if fetched.hops else normalized
            display_host, punycode_host = _try_extract_hosts(last_url)

        is_rejected = any(f.code in REJECTED_CODES for f in findings)
        is_unsupported = not is_rejected and any(f.code in UNSUPPORTED_CODES for f in findings)

        if is_rejected or is_unsupported:
            status_hint = Status.rejected if is_rejected else Status.unsupported
            link_type = (
                _unsupported_link_type(findings, fetched.changed_host)
                if is_unsupported
                else (LinkType.shortened if fetched.changed_host else LinkType.http)
            )
            total_ms = max(_elapsed_ms(started), fetched.timings.get("fetch", 0))
            report = RawScanReport(
                normalized_url=normalized,
                final_url=None,
                display_host=display_host,
                punycode_host=punycode_host,
                link_type=link_type,
                findings=[FindingRecord(code=f.code, evidence=dict(f.evidence)) for f in findings],
                read=ReadFactsRecord(),
                file=None,
                redirects=redirect_chain_view(fetched.hops, status_hint),
                timings_ms={"total": total_ms, **fetched.timings},
            )
            return report.model_dump(mode="json")

        link_type = LinkType.shortened if fetched.changed_host else LinkType.http

        if is_homograph_host(display_host, punycode_host):
            findings.append(
                Finding(
                    "URL_HOMOGRAPH",
                    {
                        "display_host": display_host or "",
                        "punycode_host": punycode_host or "",
                    },
                )
            )

        if (
            not fetched.metadata_only
            and not any(f.code == "LINK_IS_WEB_PAGE" for f in findings)
            and is_html_body(fetched.body_head)
        ):
            findings.append(Finding("LINK_IS_WEB_PAGE", {}))

        is_web_page = any(f.code == "LINK_IS_WEB_PAGE" for f in findings)
        if is_web_page:
            service = cloud_share_service(punycode_host or display_host)
            if service is not None:
                findings.append(Finding("LINK_CLOUD_SHARE_PAGE", {"service": service}))

        file_info: FileInfo | None = None
        if fetched.body_head and not is_web_page:
            detection = detect_type(fetched.body_head, self.settings)
            detection = refine_zip_subtype(
                detection, fetched.body_head, fetched.whole_file, self.settings
            )
            claim = claimed_name(
                fetched.headers.get("content-disposition"), fetched.final_url, normalized
            )
            findings.extend(
                run_mismatch_checks(
                    detection,
                    fetched.body_head,
                    claim,
                    fetched.headers.get("content-type"),
                )
            )
            file_info = FileInfo(
                claimed_name=claim.display if claim else None,
                name_source=claim.source if claim else None,
                content_type=media_type(fetched.headers.get("content-type")),
                detected_type=detection.type,
                detected_label=detection.label,
                family=detection.family,
                detection_confidence=detection.confidence,
                first_bytes_hex=fetched.body_head[:16].hex(),
                signature=detection.signature,
            )

        read_record = ReadFactsRecord(
            bytes_read=fetched.bytes_read,
            total_size=fetched.total_size,
            range_supported=fetched.range_supported,
            ended=fetched.ended,
            headers_only=fetched.metadata_only,
        )
        read_facts = read_record.to_read_facts()
        unexpected_encoding = any(f.code == "FETCH_UNEXPECTED_ENCODING" for f in findings)
        scope = build_scope(Status.completed, read_facts, unexpected_encoding)
        if (
            scope.mode == ScopeMode.partial
            and not unexpected_encoding
            and not any(
                f.code in ("FETCH_TIMEOUT", "FETCH_INTERRUPTED", "SCAN_PARTIAL") for f in findings
            )
        ):
            findings.append(Finding("SCAN_PARTIAL", {"scope_label": scope.label}))

        total_ms = max(_elapsed_ms(started), fetched.timings.get("fetch", 0))
        report = RawScanReport(
            normalized_url=normalized,
            final_url=fetched.final_url,
            display_host=display_host,
            punycode_host=punycode_host,
            link_type=link_type,
            findings=[FindingRecord(code=f.code, evidence=dict(f.evidence)) for f in findings],
            read=read_record,
            file=file_info,
            redirects=redirect_chain_view(fetched.hops, Status.completed),
            timings_ms={"total": total_ms, **fetched.timings},
        )
        return report.model_dump(mode="json")
