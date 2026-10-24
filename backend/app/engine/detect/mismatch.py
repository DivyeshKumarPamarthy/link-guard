"""Mismatch checks: what the file is versus what it claims to be (spec §7, task T2.2).

Each check is one small function that returns a list of findings (empty when it has nothing
to say); `run_mismatch_checks` runs them all. Codes and their evidence keys are declared in
`reason_codes.yaml`; the scorer turns findings into reasons. The claimed name and the
Content-Type are hostile remote data: they are only compared here, never used as paths.

Rules come from decisions D67–D74. Only the LAST extension of the lowercased name is the
claim; an extension in none of the tables below (`.php`, `.81`, none) is an "unknown claim"
that skips the extension checks (the Content-Type check still runs).
"""

import unicodedata

from app.contract.models import DetectionConfidence, Family
from app.engine.detect.names import ClaimedName, extension_chain
from app.engine.detect.signatures import PDF_SEARCH_WINDOW, Detection
from app.engine.fetcher.redirects import Finding

# --- which detected types each claimed extension allows (equivalence classes) ------------

PE_TYPES = frozenset({"pe-executable", "dos-executable"})
ZIP_FAMILY_TYPES = frozenset({"zip", "docx", "xlsx", "jar", "apk"})

# Executable classes (D69): executable content under its own class's extension is consistent.
EXECUTABLE_CLAIMS: dict[str, frozenset[str]] = {
    **dict.fromkeys(("exe", "dll", "sys", "scr", "cpl", "ocx", "com", "pif"), PE_TYPES),
    "so": frozenset({"elf-executable"}),
    "elf": frozenset({"elf-executable"}),
    "dylib": frozenset({"macho-executable", "java-class-or-macho"}),
    "class": frozenset({"java-class-or-macho"}),
}

# Scripts and plain text have no magic bytes: the only thing we can confirm is "text".
TEXT_CLAIMS = frozenset({"txt", "csv", "json", "xml", "js", "ps1", "bat", "cmd", "vbs", "hta"})

# Formats we can detect, each with the detected types its extension allows.
DETECTABLE_CLAIMS: dict[str, frozenset[str]] = {
    **EXECUTABLE_CLAIMS,
    # A DOCX/XLSX is a ZIP, so naming it .zip is honest; a JAR/APK named .zip is not (plan M4).
    "zip": frozenset({"zip", "docx", "xlsx"}),
    "docx": frozenset({"docx"}),
    "xlsx": frozenset({"xlsx"}),
    "jar": frozenset({"jar"}),
    "apk": frozenset({"apk"}),
    "7z": frozenset({"7z"}),
    "rar": frozenset({"rar4", "rar5"}),
    "pdf": frozenset({"pdf"}),
    **dict.fromkeys(("msi", "doc", "xls"), frozenset({"ole"})),
    **dict.fromkeys(("mp4", "m4a", "m4v", "mov"), frozenset({"mp4"})),
    "mp3": frozenset({"mp3"}),
    "png": frozenset({"png"}),
    **dict.fromkeys(("jpg", "jpeg", "jpe"), frozenset({"jpeg"})),
    **dict.fromkeys(TEXT_CLAIMS, frozenset({"text"})),
}

# Common binary formats we cannot detect (D68). They only feed TYPE_MISMATCH_EXEC and
# TYPE_MISMATCH_TEXT, so a program named .gif is still caught, and a real GIF is never flagged.
UNDETECTABLE_BINARY_CLAIMS = frozenset(
    {
        "gif", "bmp", "webp", "ico", "tif", "tiff", "heic",
        "wav", "flac", "ogg", "aac", "avi", "mkv", "webm", "wmv",
        "ppt", "pptx", "odt", "ods", "iso", "gz", "tgz", "tar",
    }
)  # fmt: skip

# Spec §7 risky extensions outside the format list (EXT_RISKY).
RISKY_EXTENSIONS = frozenset({"scr", "lnk", "hta", "vbs", "cmd", "jar", "com", "pif"})

# EXT_DOUBLE (D71, D77): a risky last extension hidden behind a document/media/image/archive
# decoy. Both sets contain every D71 extension; the extra ones only add flags.
DOUBLE_REAL_EXTENSIONS = (
    frozenset(EXECUTABLE_CLAIMS) | RISKY_EXTENSIONS | {"js", "ps1", "bat", "msi"}
)
DOUBLE_DECOY_EXTENSIONS = frozenset(
    {
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "txt", "csv",
        "jpg", "jpeg", "jpe", "png", "gif", "bmp", "webp", "heic",
        "mp3", "mp4", "m4a", "m4v", "mov", "wav", "avi", "mkv", "wmv",
        "zip", "rar", "7z",
    }
)  # fmt: skip

# --- Content-Type rows (D70) -------------------------------------------------------------

ZIP_MEDIA_TYPES = frozenset(
    {"application/zip", "application/x-zip-compressed", "application/x-zip"}
)

# (detected types, media types that fit them). A media type fits a detection when any row
# holding the media type also holds the detected type. A ZIP whose subtype is unconfirmed may
# really be any member, so `check_content_type` lets it match every ZIP-family row.
CONTENT_TYPE_ROWS: list[tuple[frozenset[str], frozenset[str]]] = [
    (
        PE_TYPES,
        frozenset(
            {
                "application/x-msdownload",
                "application/x-dosexec",
                "application/x-msdos-program",
                "application/vnd.microsoft.portable-executable",
            }
        ),
    ),
    (
        frozenset({"elf-executable"}),
        frozenset({"application/x-executable", "application/x-elf", "application/x-sharedlib"}),
    ),
    (
        frozenset({"macho-executable", "java-class-or-macho"}),
        frozenset({"application/x-mach-binary"}),
    ),
    (
        frozenset({"java-class-or-macho"}),
        frozenset({"application/java-vm", "application/x-java-class"}),
    ),
    (ZIP_FAMILY_TYPES, ZIP_MEDIA_TYPES),
    (
        frozenset({"docx"}),
        frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
    ),
    (
        frozenset({"xlsx"}),
        frozenset({"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
    ),
    (
        frozenset({"jar"}),
        frozenset({"application/java-archive", "application/x-java-archive"}),
    ),
    (frozenset({"apk"}), frozenset({"application/vnd.android.package-archive"})),
    (frozenset({"7z"}), frozenset({"application/x-7z-compressed"})),
    (
        frozenset({"rar4", "rar5"}),
        frozenset({"application/vnd.rar", "application/x-rar-compressed", "application/x-rar"}),
    ),
    (frozenset({"pdf"}), frozenset({"application/pdf"})),
    (
        frozenset({"ole"}),
        frozenset(
            {
                "application/x-msi",
                "application/x-ole-storage",
                "application/msword",
                "application/vnd.ms-excel",
            }
        ),
    ),
    (
        frozenset({"mp4"}),
        frozenset({"video/mp4", "video/quicktime", "video/x-m4v", "audio/mp4", "audio/x-m4a"}),
    ),
    (frozenset({"mp3"}), frozenset({"audio/mpeg", "audio/mp3"})),
    (frozenset({"png"}), frozenset({"image/png"})),
    (frozenset({"jpeg"}), frozenset({"image/jpeg", "image/pjpeg"})),
    (
        frozenset({"text"}),
        frozenset(
            {
                "text/plain",
                "text/csv",
                "text/xml",
                "text/javascript",
                "application/javascript",
                "application/json",
                "application/xml",
            }
        ),
    ),
]

# Media types that say nothing about the content (spec §7: "no signal").
NO_SIGNAL_MEDIA_TYPES = frozenset(
    {
        "application/octet-stream",
        "binary/octet-stream",
        "application/download",
        "application/force-download",
        "application/x-download",
        "text/html",  # a web page is the router's LINK_IS_WEB_PAGE (D9), not a mismatch
    }
)

# --- TYPE_POLYGLOT (P1, D73): kept narrow to avoid false alarms ---------------------------

POLYGLOT_ZIP_HOSTS = frozenset({"png", "jpeg", "mp4", "mp3", "pdf"})
POLYGLOT_PDF_HOSTS = frozenset({"png", "jpeg", "mp4", "mp3"})


# --- helpers ------------------------------------------------------------------------------


def claimed_extension(name: str) -> str | None:
    """The last extension, lowercased and stripped of whitespace; None when there is none."""
    chain = extension_chain(name)
    if not chain:
        return None
    return chain[-1].strip() or None


def media_type(content_type: str | None) -> str | None:
    """`Image/PNG; charset=x` → `image/png`. Parameters are never compared."""
    if not content_type:
        return None
    return content_type.split(";", 1)[0].strip().lower() or None


def is_known_claim(ext: str | None) -> bool:
    return ext is not None and (ext in DETECTABLE_CLAIMS or ext in UNDETECTABLE_BINARY_CLAIMS)


# --- the checks ---------------------------------------------------------------------------


def check_exec_mismatch(detection: Detection, ext: str | None) -> list[Finding]:
    """An executable posing as anything else is the headline risk (hard rule: UNSAFE).

    Probable executables count too: risk evidence beats missing evidence.
    """
    if detection.family is not Family.executable or not is_known_claim(ext):
        return []
    if ext in EXECUTABLE_CLAIMS:
        return []  # a wrong executable class is TYPE_MISMATCH_OTHER
    return [
        Finding(
            "TYPE_MISMATCH_EXEC",
            {"claimed_ext": ext, "detected": detection.type, "detected_label": detection.label},
        )
    ]


def check_text_mismatch(
    detection: Detection, ext: str | None, content_media_type: str | None
) -> list[Finding]:
    """Text named like a binary file (a script disguised as a .pdf, an error page saved as .jpg).

    Skipped for `text/html`: HTML is reported as a web page instead (D9). T3.1 adds the HTML
    body sniff, which also stops before this check runs.
    """
    if detection.type != "text" or not is_known_claim(ext) or ext in TEXT_CLAIMS:
        return []
    if content_media_type == "text/html":
        return []
    return [Finding("TYPE_MISMATCH_TEXT", {"claimed_ext": ext})]


def check_other_mismatch(detection: Detection, ext: str | None) -> list[Finding]:
    """Any other wrong format or wrong family member (PNG named .jpg, ELF named .exe).

    Never on an unconfirmed detection (D69): "subtype unconfirmed" is not proof of a mismatch.
    Executable content under a non-executable name and text content are handled by the EXEC
    and TEXT checks, so they are skipped here to avoid two codes for one disguise.
    """
    if ext not in DETECTABLE_CLAIMS or detection.confidence is DetectionConfidence.unconfirmed:
        return []
    if detection.type in ("text", "unknown"):  # D69: unknown bytes never raise a type code
        return []
    if detection.family is Family.executable and ext not in EXECUTABLE_CLAIMS:
        return []
    if detection.type in DETECTABLE_CLAIMS[ext]:
        return []
    return [Finding("TYPE_MISMATCH_OTHER", {"claimed_ext": ext, "detected_label": detection.label})]


def check_double_extension(name: str) -> list[Finding]:
    """`invoice.pdf.exe`: Windows hides the last extension, so the user only sees `.pdf`."""
    chain = [ext.strip() for ext in extension_chain(name)]
    if len(chain) < 2:
        return []
    decoy, real = chain[-2], chain[-1]
    if real not in DOUBLE_REAL_EXTENSIONS or decoy not in DOUBLE_DECOY_EXTENSIONS:
        return []
    return [Finding("EXT_DOUBLE", {"decoy_ext": decoy, "real_ext": real})]


def check_risky_extension(ext: str | None) -> list[Finding]:
    """Extensions that run code but are outside the format list, so bytes cannot prove them."""
    if ext not in RISKY_EXTENSIONS:
        return []
    return [Finding("EXT_RISKY", {"ext": ext})]


def check_spoofed_name(name: str) -> list[Finding]:
    """Invisible control/format characters (U+202E reverses text) can fake an extension (D72).

    Any Unicode category Cc (controls, NUL) or Cf (bidi, zero-width) character counts. The
    evidence lists distinct code points as `U+202E`, never the raw characters.
    """
    found: list[str] = []
    for char in name:
        if unicodedata.category(char) in ("Cc", "Cf"):
            code_point = f"U+{ord(char):04X}"
            if code_point not in found:
                found.append(code_point)
    if not found:
        return []
    return [Finding("EXT_SPOOFED_NAME", {"characters": ", ".join(found)})]


def check_content_type(detection: Detection, content_media_type: str | None) -> list[Finding]:
    """The server's Content-Type contradicts the bytes (magic bytes decide the type).

    No signal when the header is missing or generic, when we do not know the media type, or
    when the content is unknown: we never claim a contradiction we cannot interpret (D70).
    """
    if content_media_type is None or content_media_type in NO_SIGNAL_MEDIA_TYPES:
        return []
    if detection.type == "unknown":
        return []
    rows = [types for types, media_types in CONTENT_TYPE_ROWS if content_media_type in media_types]
    if detection.type == "zip" and detection.confidence is DetectionConfidence.unconfirmed:
        # Subtype unconfirmed: it may be a DOCX/XLSX/JAR/APK, so any ZIP-family row fits.
        # A certain plain ZIP (the listing proved it) only fits the generic ZIP row.
        fitting_types = ZIP_FAMILY_TYPES
    else:
        fitting_types = frozenset({detection.type})
    if not rows or any(fitting_types & types for types in rows):
        return []
    return [
        Finding(
            "TYPE_CONTENT_TYPE_MISMATCH",
            {"content_type": content_media_type, "detected_label": detection.label},
        )
    ]


def check_polyglot(detection: Detection, data: bytes) -> list[Finding]:
    """A file that is also a second format (image + ZIP, PDF + ZIP) can hide a payload (D73).

    Rule 1: an image, media file or PDF that also holds a ZIP local header. Rule 2: an image
    or media file with `%PDF-` in the first 1024 bytes. ZIPs are not searched for `%PDF-`
    because a ZIP that stores a PDF would be a false alarm. The first hit is reported.
    """
    hits: list[tuple[int, str]] = []
    if detection.type in POLYGLOT_ZIP_HOSTS:
        offset = data.find(b"PK\x03\x04", 1)
        if offset != -1:
            hits.append((offset, "ZIP archive"))
    if detection.type in POLYGLOT_PDF_HOSTS:
        offset = data.find(b"%PDF-", 1, PDF_SEARCH_WINDOW)
        if offset != -1:
            hits.append((offset, "PDF document"))
    if not hits:
        return []
    offset, second_label = min(hits)
    return [
        Finding(
            "TYPE_POLYGLOT",
            {"detected_label": detection.label, "second_label": second_label, "offset": offset},
        )
    ]


def check_exec_probable(detection: Detection) -> list[Finding]:
    """`MZ` without a PE header in the buffer: still an executable, but say it is unproven.

    MZ-based detections only (D74): the message talks about MZ, which would be false for
    `CAFEBABE` ("Java class or Mach-O" already says it is uncertain).
    """
    if detection.type in PE_TYPES and detection.confidence is DetectionConfidence.probable:
        return [Finding("TYPE_EXEC_PROBABLE", {})]
    return []


def check_unknown_type(detection: Detection, data: bytes) -> list[Finding]:
    """Bytes we could not identify. An empty body is the fetcher's FETCH_EMPTY instead (D74)."""
    if detection.type == "unknown" and data:
        return [Finding("TYPE_UNKNOWN", {})]
    return []


def run_mismatch_checks(
    detection: Detection, data: bytes, claim: ClaimedName | None, content_type: str | None
) -> list[Finding]:
    """Every spec §7 check, in a fixed order. `detection` should already be refined with
    `refine_zip_subtype` when the whole file was read."""
    ext = claimed_extension(claim.compare) if claim else None
    content_media_type = media_type(content_type)
    findings: list[Finding] = []
    findings += check_exec_mismatch(detection, ext)
    findings += check_text_mismatch(detection, ext, content_media_type)
    findings += check_other_mismatch(detection, ext)
    if claim:
        findings += check_double_extension(claim.compare)
        findings += check_spoofed_name(claim.display)
    findings += check_risky_extension(ext)
    findings += check_content_type(detection, content_media_type)
    findings += check_polyglot(detection, data)
    findings += check_exec_probable(detection)
    findings += check_unknown_type(detection, data)
    return findings
