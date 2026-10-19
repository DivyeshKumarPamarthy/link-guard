"""API contract v1 (spec §2): the request, the scan result and the error body.

These models are the single source of truth. FastAPI turns them into OpenAPI
(`backend/openapi.json`) and `openapi-typescript` turns that into the web app's types,
so the backend and the web app can never silently disagree about a field.

Readers are tolerant (`extra="ignore"`): a client built against 1.0 keeps working when
a later 1.x adds optional fields. Breaking changes bump the major `schema_version`.
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

SchemaVersion = Literal["1.0"]
SCHEMA_VERSION: SchemaVersion = "1.0"


class ContractModel(BaseModel):
    """Base for every contract model: unknown fields are ignored, not rejected.

    In responses every field is always sent (null when empty), so the generated web types
    mark them required instead of optional.
    """

    model_config = ConfigDict(extra="ignore", json_schema_serialization_defaults_required=True)


# --- enums -----------------------------------------------------------------------------


class State(StrEnum):
    """Where the scan is in its lifecycle. Outcome fields are null until `done`."""

    queued = "queued"
    running = "running"
    done = "done"


class Status(StrEnum):
    """How a finished scan ended (spec §3)."""

    completed = "completed"  # fetched (or tried to): has a verdict
    rejected = "rejected"  # unsafe to contact (SSRF, blocked scheme/port, userinfo)
    unsupported = "unsupported"  # link type not handled yet (magnet, ftp, .torrent)


class Verdict(StrEnum):
    SAFE = "SAFE"
    SUSPICIOUS = "SUSPICIOUS"
    UNSAFE = "UNSAFE"
    UNABLE_TO_VERIFY = "UNABLE_TO_VERIFY"


class DisplayVerdict(StrEnum):
    """What clients show. Computed by the backend only (decision D4)."""

    SAFE = "SAFE"
    NO_ISSUES_IN_CHECKED_PART = "NO_ISSUES_IN_CHECKED_PART"
    SUSPICIOUS = "SUSPICIOUS"
    UNSAFE = "UNSAFE"
    UNABLE_TO_VERIFY = "UNABLE_TO_VERIFY"
    REJECTED = "REJECTED"
    UNSUPPORTED = "UNSUPPORTED"


class Confidence(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class ScopeMode(StrEnum):
    """How much of the file was actually read (decision D7 added `none`)."""

    full = "full"
    partial = "partial"
    metadata_only = "metadata-only"
    none = "none"


class LinkType(StrEnum):
    http = "http"
    shortened = "shortened"
    # The next four appear only with status=unsupported in Phase 1.
    torrent = "torrent"
    magnet = "magnet"
    ftp = "ftp"
    other = "other"


class Severity(StrEnum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"


class AddressClass(StrEnum):
    public = "public"
    private = "private"
    blocked = "blocked"


class NameSource(StrEnum):
    """Where the claimed filename came from, in priority order (spec §7)."""

    content_disposition = "content-disposition"
    final_url = "final-url"
    original_url = "original-url"


class Family(StrEnum):
    """File family (spec §7). `text` and `unknown` added by decision D24."""

    executable = "executable"
    archive = "archive"
    document = "document"
    script = "script"
    media = "media"
    image = "image"
    text = "text"
    unknown = "unknown"


class DetectionConfidence(StrEnum):
    certain = "certain"
    probable = "probable"
    unconfirmed = "unconfirmed"


class ErrorCode(StrEnum):
    """Error codes returned instead of a scan (spec §2; decision D25 for the last four)."""

    URL_EMPTY = "URL_EMPTY"
    URL_TOO_LONG = "URL_TOO_LONG"
    URL_MULTIPLE = "URL_MULTIPLE"
    SERVER_BUSY = "SERVER_BUSY"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"
    REQUEST_TOO_LARGE = "REQUEST_TOO_LARGE"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"


# --- request and small responses -------------------------------------------------------


class ScanRequest(ContractModel):
    """Body of POST /api/scans. `url` is raw user text; the router cleans it."""

    url: str = ""


class ScanAccepted(ContractModel):
    """202 response: the scan exists; poll GET /api/scans/{scan_id} for the result."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    scan_id: UUID
    state: State
    poll_after_ms: int = Field(gt=0)


class ErrorDetail(ContractModel):
    code: ErrorCode
    message: str


class ErrorBody(ContractModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    error: ErrorDetail


# --- scan result -----------------------------------------------------------------------


class Scope(ContractModel):
    """What was actually read. Every result states it (honesty rule)."""

    mode: ScopeMode
    bytes_analyzed: int = Field(ge=0)
    total_bytes: int | None = Field(default=None, ge=0)
    range_supported: bool
    label: str


class Signature(ContractModel):
    """Which of the first 16 bytes identified the type (drives the hex-strip highlight)."""

    offset: int = Field(ge=0, le=15)
    length: int = Field(ge=1, le=16)
    name: str


class FileInfo(ContractModel):
    """The claimed-vs-actual evidence for the file."""

    claimed_name: str | None = None
    name_source: NameSource | None = None
    content_type: str | None = None
    detected_type: str | None = None
    detected_label: str | None = None
    family: Family | None = None
    detection_confidence: DetectionConfidence | None = None
    first_bytes_hex: str = Field(default="", pattern=r"^([0-9a-f]{2}){0,16}$")
    signature: Signature | None = None


class RedirectHop(ContractModel):
    url: str
    status: int | None = None
    address_class: AddressClass


class Reason(ContractModel):
    """One finding. Unknown codes must be rendered as a generic card by clients."""

    code: str
    severity: Severity
    weight: int = Field(ge=0)  # no negative weights, ever
    group: str
    message: str
    evidence: dict[str, JsonValue] = {}


class ScanResult(ContractModel):
    """Body of GET /api/scans/{scan_id}. Outcome fields are null until state is `done`."""

    schema_version: SchemaVersion = SCHEMA_VERSION
    scan_id: UUID
    state: State
    status: Status | None = None
    input_url: str
    normalized_url: str | None = None
    final_url: str | None = None
    display_host: str | None = None
    punycode_host: str | None = None
    link_type: LinkType | None = None
    verdict: Verdict | None = None
    display_verdict: DisplayVerdict | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    confidence: Confidence | None = None
    scope: Scope | None = None
    headline: str | None = None
    file: FileInfo | None = None
    redirects: list[RedirectHop] = []
    reasons: list[Reason] | None = None
    unavailable_signals: list[str] = []
    timings_ms: dict[str, int] | None = None
    engine_version: str
    rules_version: str
    created_at: datetime
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def _check_outcome_rules(self) -> "ScanResult":
        """Enforce spec §2/§3 so no code path can return a contradictory or dishonest result."""
        outcome = {
            "status": self.status,
            "verdict": self.verdict,
            "display_verdict": self.display_verdict,
            "score": self.score,
            "confidence": self.confidence,
            "headline": self.headline,
            "reasons": self.reasons,
            "file": self.file,
        }
        if self.state != State.done:
            filled = [name for name, value in outcome.items() if value is not None]
            if filled:
                raise ValueError(f"outcome fields must be null until done: {filled}")
            return self

        if self.status is None or self.display_verdict is None:
            raise ValueError("a done scan needs status and display_verdict")
        if self.status == Status.completed:
            if self.verdict is None or self.confidence is None:
                raise ValueError("a completed scan needs verdict and confidence")
            if self.display_verdict in (DisplayVerdict.REJECTED, DisplayVerdict.UNSUPPORTED):
                raise ValueError("a completed scan cannot display REJECTED or UNSUPPORTED")
        else:
            if self.verdict is not None or self.confidence is not None:
                raise ValueError("verdict and confidence exist only when status is completed")
            expected = (
                DisplayVerdict.REJECTED
                if self.status == Status.rejected
                else DisplayVerdict.UNSUPPORTED
            )
            if self.display_verdict != expected:
                raise ValueError(f"status {self.status} must display {expected}")

        if self.display_verdict == DisplayVerdict.SAFE:
            # Plain "Safe" only for a whole-file read with confidence medium or better.
            if (
                self.verdict != Verdict.SAFE
                or self.scope is None
                or self.scope.mode != ScopeMode.full
                or self.confidence == Confidence.low
            ):
                raise ValueError(
                    "display SAFE needs verdict SAFE, full scope, confidence >= medium"
                )
        return self
