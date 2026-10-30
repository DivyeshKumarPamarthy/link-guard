"""What the file really is, worked out from its first bytes (spec §7, task T1.5).

The project's own signature table is authoritative. Each format has a small check function;
`detect_type` tries them riskiest family first, so an executable that also contains another
format's marker is reported as an executable. Nothing here executes, decompresses or writes
the bytes: it only compares them with known signatures.
"""

import io
import struct
import zipfile
from collections.abc import Callable
from dataclasses import dataclass

from app.contract.models import DetectionConfidence, Family, Signature
from app.core.config import Settings, get_settings

CERTAIN = DetectionConfidence.certain
PROBABLE = DetectionConfidence.probable
UNCONFIRMED = DetectionConfidence.unconfirmed

# Format facts from spec §7 (not tunables): where a signature may appear.
PE_E_LFANEW_OFFSET = 0x3C
PDF_SEARCH_WINDOW = 1024
HEX_STRIP_BYTES = 16

# Fixed signatures at offset 0. Also used to recognise a buffer that is too short to tell.
PREFIX_SIGNATURES = [
    b"MZ",
    b"\x7fELF",
    b"\xfe\xed\xfa\xce",
    b"\xfe\xed\xfa\xcf",
    b"\xce\xfa\xed\xfe",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
    b"PK\x03\x04",
    b"PK\x05\x06",
    b"PK\x07\x08",
    b"7z\xbc\xaf\x27\x1c",
    b"Rar!\x1a\x07\x00",
    b"Rar!\x1a\x07\x01\x00",
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"ID3",
    b"%PDF-",
]


@dataclass(frozen=True)
class Detection:
    """The detector's answer. `label` must read correctly after "a" (decision D27)."""

    type: str
    label: str
    family: Family
    confidence: DetectionConfidence
    signature: Signature | None = None


UNKNOWN = Detection("unknown", "file of unknown type", Family.unknown, UNCONFIRMED)


def marked(offset: int, length: int, name: str) -> Signature | None:
    """The hex-strip highlight, only when the signature lies inside the first 16 bytes."""
    if offset + length > HEX_STRIP_BYTES:
        return None
    return Signature(offset=offset, length=length, name=name)


# --- executable family -------------------------------------------------------------------


def detect_pe(data: bytes, settings: Settings) -> Detection | None:
    """PE needs `MZ` and `PE\\0\\0` at e_lfanew; a bare MZ is still treated as executable."""
    if not data.startswith(b"MZ"):
        return None
    signature = marked(0, 2, "MZ (Windows executable)")
    if len(data) < PE_E_LFANEW_OFFSET + 4:
        # Too short to read e_lfanew: risk evidence, but unproven (TYPE_EXEC_PROBABLE).
        return Detection(
            "pe-executable", "Windows executable", Family.executable, PROBABLE, signature
        )
    (e_lfanew,) = struct.unpack_from("<I", data, PE_E_LFANEW_OFFSET)
    if e_lfanew + 4 > len(data):
        # The PE header lies beyond what was read.
        return Detection(
            "pe-executable", "Windows executable", Family.executable, PROBABLE, signature
        )
    if data[e_lfanew : e_lfanew + 4] == b"PE\0\0":
        return Detection(
            "pe-executable", "Windows executable", Family.executable, CERTAIN, signature
        )
    return Detection(
        "dos-executable", "DOS or other MZ executable", Family.executable, PROBABLE, signature
    )


def detect_elf(data: bytes, settings: Settings) -> Detection | None:
    """Linux and most Unix executables and libraries."""
    if not data.startswith(b"\x7fELF"):
        return None
    return Detection(
        "elf-executable",
        "Linux executable (ELF)",
        Family.executable,
        CERTAIN,
        marked(0, 4, "ELF (Linux executable)"),
    )


def detect_macho(data: bytes, settings: Settings) -> Detection | None:
    """Mach-O in both byte orders; CAFEBABE is shared by Java class files and fat binaries."""
    if data[:4] in (
        b"\xfe\xed\xfa\xce",
        b"\xfe\xed\xfa\xcf",
        b"\xce\xfa\xed\xfe",
        b"\xcf\xfa\xed\xfe",
    ):
        return Detection(
            "macho-executable",
            "macOS executable (Mach-O)",
            Family.executable,
            CERTAIN,
            marked(0, 4, "Mach-O (macOS executable)"),
        )
    if data.startswith(b"\xca\xfe\xba\xbe"):
        return Detection(
            "java-class-or-macho",
            "Java class or Mach-O file",
            Family.executable,
            PROBABLE,
            marked(0, 4, "CAFEBABE (Java class or Mach-O)"),
        )
    return None


# --- ZIP and the formats built on it -----------------------------------------------------


def zip_entry_names(data: bytes, max_entries: int) -> list[str]:
    """Names from ZIP local file headers found in the buffer (listing only, no extraction).

    Searching for every `PK\\x03\\x04` instead of walking sizes still works when sizes are
    deferred to a data descriptor. The cap stops a crafted head from causing endless work.
    """
    names: list[str] = []
    position = data.find(b"PK\x03\x04")
    while position != -1 and len(names) < max_entries:
        name_start = position + 30
        if name_start > len(data):
            break
        (name_length,) = struct.unpack_from("<H", data, position + 26)
        names.append(data[name_start : name_start + name_length].decode("utf-8", "replace"))
        position = data.find(b"PK\x03\x04", position + 4)
    return names


def zip_subtype(names: list[str]) -> tuple[str, str, Family] | None:
    """Which ZIP-based format the entry names prove, if any (spec §7 DOCX/XLSX rule)."""
    if "AndroidManifest.xml" in names:
        return "apk", "packaged Android app (APK)", Family.archive
    if "[Content_Types].xml" in names:
        if any(name.startswith("word/") for name in names):
            return "docx", "Word document (DOCX)", Family.document
        if any(name.startswith("xl/") for name in names):
            return "xlsx", "spreadsheet (XLSX)", Family.document
    if "META-INF/MANIFEST.MF" in names:
        return "jar", "Java archive (JAR)", Family.archive
    return None


def detect_zip(data: bytes, settings: Settings) -> Detection | None:
    """ZIP and its variants. Without proof of a subtype the result is "subtype unconfirmed"."""
    if data[:4] not in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        return None
    signature = marked(0, 4, "PK (ZIP container)")
    if data[:4] == b"PK\x05\x06":
        # The end-of-archive record first: an empty ZIP, nothing inside to be anything else.
        return Detection("zip", "ZIP archive", Family.archive, CERTAIN, signature)
    subtype = zip_subtype(zip_entry_names(data, settings.zip_max_entries))
    if subtype is None:
        return Detection(
            "zip", "ZIP-based file (subtype unconfirmed)", Family.archive, UNCONFIRMED, signature
        )
    type_, label, family = subtype
    return Detection(type_, label, family, CERTAIN, signature)


def refine_zip_subtype(
    detection: Detection, data: bytes, full_scope: bool, settings: Settings | None = None
) -> Detection:
    """Prove a ZIP's subtype from its central directory when the whole file was read (D75).

    Spec §7: full scope only, listing only (`namelist()` never opens, reads or extracts an
    entry), an entry cap, and every exception caught. A crafted or truncated archive simply
    keeps the head result. Called by the executor after `detect_type`.
    """
    settings = settings or get_settings()
    if not full_scope or detection.type != "zip" or detection.confidence is not UNCONFIRMED:
        return detection
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
    except Exception:  # any parsing failure means "not proven", never a crash
        return detection
    if len(names) > settings.zip_max_entries:
        return detection
    subtype = zip_subtype(names)
    if subtype is None:
        # The listing proves there is nothing more specific inside: a plain ZIP.
        return Detection("zip", "ZIP archive", Family.archive, CERTAIN, detection.signature)
    type_, label, family = subtype
    return Detection(type_, label, family, CERTAIN, detection.signature)


def detect_7z(data: bytes, settings: Settings) -> Detection | None:
    """7-Zip archives can carry an executable, so a .7z must really be one."""
    if not data.startswith(b"7z\xbc\xaf\x27\x1c"):
        return None
    return Detection("7z", "7-Zip archive", Family.archive, CERTAIN, marked(0, 6, "7z archive"))


def detect_rar(data: bytes, settings: Settings) -> Detection | None:
    """RAR4 and RAR5 share `Rar!\\x1a\\x07` and differ in the next byte."""
    if data.startswith(b"Rar!\x1a\x07\x01\x00"):
        return Detection(
            "rar5", "RAR archive (version 5)", Family.archive, CERTAIN, marked(0, 8, "RAR5 archive")
        )
    if data.startswith(b"Rar!\x1a\x07\x00"):
        return Detection(
            "rar4", "RAR archive (version 4)", Family.archive, CERTAIN, marked(0, 7, "RAR4 archive")
        )
    return None


# --- documents ---------------------------------------------------------------------------


def detect_ole(data: bytes, settings: Settings) -> Detection | None:
    """OLE container: .msi and legacy .doc/.xls share it, so Phase 1 does not tell them apart."""
    if not data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return None
    return Detection(
        "ole",
        "Windows Installer or legacy Office file",
        Family.document,
        CERTAIN,
        marked(0, 8, "OLE container"),
    )


def detect_pdf(data: bytes, settings: Settings) -> Detection | None:
    """Readers accept `%PDF-` anywhere in the first 1024 bytes, so we search that window."""
    offset = data.find(b"%PDF-", 0, PDF_SEARCH_WINDOW)
    if offset == -1 or offset + 5 > PDF_SEARCH_WINDOW:
        return None
    return Detection("pdf", "PDF document", Family.document, CERTAIN, marked(offset, 5, "%PDF-"))


# --- images and media --------------------------------------------------------------------


def detect_png(data: bytes, settings: Settings) -> Detection | None:
    """Images are a common disguise for executables; the 8-byte PNG header proves a real PNG."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    return Detection("png", "PNG image", Family.image, CERTAIN, marked(0, 8, "PNG image"))


def detect_jpeg(data: bytes, settings: Settings) -> Detection | None:
    """A file named .jpg should start with the JPEG start-of-image marker `FF D8 FF`."""
    if not data.startswith(b"\xff\xd8\xff"):
        return None
    return Detection("jpeg", "JPEG image", Family.image, CERTAIN, marked(0, 3, "JPEG image"))


def detect_mp4(data: bytes, settings: Settings) -> Detection | None:
    """MP4, MOV and M4A all have `ftyp` at offset 4; the brand after it is not compared."""
    if data[4:8] != b"ftyp":
        return None
    return Detection(
        "mp4", "video file (MP4 family)", Family.media, CERTAIN, marked(4, 4, "ftyp (MP4 family)")
    )


# MPEG audio Layer III tables, in kbit/s and Hz, indexed by the header fields.
MP3_BITRATES_V1 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
MP3_BITRATES_V2 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]
MP3_SAMPLE_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def mp3_frame_length(header: bytes) -> int | None:
    """Length of the MP3 frame starting with these 4 bytes, or None if it is not a valid header.

    Only MPEG Layer III counts (that is what MP3 means), which also keeps a UTF-16 BOM
    (`FF FE`, a Layer I pattern) from being mistaken for audio.
    """
    if len(header) < 4 or header[0] != 0xFF or header[1] & 0xE0 != 0xE0:
        return None
    version = (header[1] >> 3) & 0b11  # 3 = MPEG-1, 2 = MPEG-2, 0 = MPEG-2.5, 1 = reserved
    layer = (header[1] >> 1) & 0b11  # 1 = Layer III
    bitrate_index = header[2] >> 4
    rate_index = (header[2] >> 2) & 0b11
    padding = (header[2] >> 1) & 0b1
    if version == 1 or layer != 1 or bitrate_index in (0, 15) or rate_index == 3:
        return None
    sample_rate = MP3_SAMPLE_RATES[version][rate_index]
    if version == 3:
        return 144_000 * MP3_BITRATES_V1[bitrate_index] // sample_rate + padding
    return 72_000 * MP3_BITRATES_V2[bitrate_index] // sample_rate + padding


def detect_mp3(data: bytes, settings: Settings) -> Detection | None:
    """`ID3` tag, or a frame sync that is only certain when a second frame header follows."""
    if data.startswith(b"ID3"):
        return Detection("mp3", "sound file (MP3)", Family.media, CERTAIN, marked(0, 3, "ID3 tag"))
    frame_length = mp3_frame_length(data[:4])
    if frame_length is None:
        return None
    second_frame = mp3_frame_length(data[frame_length : frame_length + 4])
    confidence = CERTAIN if second_frame is not None else PROBABLE
    return Detection(
        "mp3", "sound file (MP3)", Family.media, confidence, marked(0, 2, "MP3 frame sync")
    )


# --- text --------------------------------------------------------------------------------

BYTE_ORDER_MARKS = [
    (b"\xef\xbb\xbf", "utf-8", "UTF-8 byte-order mark"),
    (b"\xff\xfe", "utf-16-le", "UTF-16 byte-order mark"),
    (b"\xfe\xff", "utf-16-be", "UTF-16 byte-order mark"),
]


def printable_ratio(text: str) -> float:
    """Share of characters a text file would contain: printable ones plus common whitespace."""
    if not text:
        return 0.0
    printable = sum(1 for char in text if char.isprintable() or char in "\t\n\r\f")
    return printable / len(text)


def detect_text(data: bytes, settings: Settings) -> Detection | None:
    """Scripts (.js, .ps1, .bat) have no magic bytes, so we can only say "this is text"."""
    sample = data[: settings.text_sample_bytes]
    encoding, signature = "utf-8", None
    for bom, bom_encoding, name in BYTE_ORDER_MARKS:
        if sample.startswith(bom):
            encoding, signature = bom_encoding, marked(0, len(bom), name)
            sample = sample[len(bom) :]
            break
    if signature is None and b"\x00" in sample:
        return None  # NUL bytes without a UTF-16 BOM mean binary
    # A sample cut mid-character costs at most one replacement character.
    text = sample.decode(encoding, "replace")
    if printable_ratio(text) < settings.text_min_printable_ratio:
        return None
    return Detection("text", "plain text file", Family.text, PROBABLE, signature)


# Riskiest family first: if two signatures match, the executable one wins (plan M4 edge case).
DETECTORS: list[Callable[[bytes, Settings], Detection | None]] = [
    detect_pe,
    detect_elf,
    detect_macho,
    detect_zip,
    detect_7z,
    detect_rar,
    detect_ole,
    detect_png,
    detect_jpeg,
    detect_mp4,
    detect_mp3,
    detect_pdf,
    detect_text,
]


def is_signature_prefix(data: bytes) -> bool:
    """True when the buffer is only the start of a signature: too short to tell what it is."""
    return any(len(data) < len(sig) and sig.startswith(data) for sig in PREFIX_SIGNATURES)


def detect_type(data: bytes, settings: Settings | None = None) -> Detection:
    """Identify the file from its first bytes using the spec §7 table."""
    settings = settings or get_settings()
    if not data or is_signature_prefix(data):
        return UNKNOWN
    for detector in DETECTORS:
        result = detector(data, settings)
        if result is not None:
            return result
    return UNKNOWN
