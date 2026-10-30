"""Mismatch checks on inline byte fixtures (task T2.2, spec §7, decisions D67–D75).

Every check has at least one positive and one negative test. Rows from the M4 edge-case table
of the original plan are marked "edge:". No network, no generated samples.
"""

import io
import struct
import zipfile

import pytest

from app.contract.models import DetectionConfidence, Family, NameSource
from app.core.config import Settings
from app.engine.detect.mismatch import (
    DOUBLE_DECOY_EXTENSIONS,
    DOUBLE_REAL_EXTENSIONS,
    check_content_type,
    check_double_extension,
    check_exec_mismatch,
    check_exec_probable,
    check_other_mismatch,
    check_polyglot,
    check_risky_extension,
    check_spoofed_name,
    check_text_mismatch,
    check_unknown_type,
    claimed_extension,
    media_type,
    run_mismatch_checks,
)
from app.engine.detect.names import ClaimedName
from app.engine.detect.signatures import Detection, detect_type, refine_zip_subtype
from app.engine.fetcher.redirects import Finding
from app.registry.loader import load_registry

SETTINGS = Settings()

# --- fixture builders --------------------------------------------------------------------


def pe_file(e_lfanew: int = 0x80, size: int = 0x100, pe_header: bool = True) -> bytes:
    """A minimal PE head: MZ, e_lfanew at 0x3C, PE\\0\\0 at e_lfanew."""
    data = bytearray(size)
    data[0:2] = b"MZ"
    data[0x3C:0x40] = struct.pack("<I", e_lfanew)
    if pe_header:
        data[e_lfanew : e_lfanew + 4] = b"PE\0\0"
    return bytes(data)


def zip_file(*entries: str | tuple[str, bytes]) -> bytes:
    """A real ZIP built in memory with the stdlib (stored entries; content b"x" by default)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for entry in entries:
            name, content = entry if isinstance(entry, tuple) else (entry, b"x")
            archive.writestr(name, content)
    return buffer.getvalue()


def png_file(extra: bytes = b"") -> bytes:
    return b"\x89PNG\r\n\x1a\n" + bytes(24) + extra


def jpeg_file(extra: bytes = b"") -> bytes:
    return b"\xff\xd8\xff\xe0" + bytes(28) + extra


DOCX = zip_file("[Content_Types].xml", "word/document.xml")
XLSX = zip_file("[Content_Types].xml", "xl/workbook.xml")
JAR = zip_file("META-INF/MANIFEST.MF", "Main.class")
APK = zip_file("AndroidManifest.xml", "classes.dex")
PLAIN_ZIP = zip_file("readme.txt", "photo.png")
ELF = b"\x7fELF\x02\x01\x01" + bytes(57)
MACHO = b"\xfe\xed\xfa\xcf" + bytes(28)
CAFEBABE = b"\xca\xfe\xba\xbe" + bytes(28)
SEVEN_Z = b"7z\xbc\xaf\x27\x1c" + bytes(26)
RAR4 = b"Rar!\x1a\x07\x00" + bytes(25)
RAR5 = b"Rar!\x1a\x07\x01\x00" + bytes(24)
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n"
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(24)
MP4 = b"\x00\x00\x00\x18ftypisom" + bytes(20)
MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + bytes(22)
TEXT = b"Write-Host 'hello'\r\n"
UNKNOWN_BYTES = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b"


def detect(data: bytes, full_scope: bool = False, settings: Settings = SETTINGS) -> Detection:
    """What the executor will do: detect from the head, then refine full-scope ZIPs."""
    return refine_zip_subtype(detect_type(data, settings), data, full_scope, settings)


def claim(name: str) -> ClaimedName:
    return ClaimedName(display=name, compare=name.lower(), source=NameSource.content_disposition)


def run(
    data: bytes,
    name: str | None = None,
    content_type: str | None = None,
    full_scope: bool = False,
) -> list[Finding]:
    detection = detect(data, full_scope)
    return run_mismatch_checks(detection, data, claim(name) if name else None, content_type)


def codes(findings: list[Finding]) -> list[str]:
    return [finding.code for finding in findings]


# --- clean samples of every format: no mismatch codes ------------------------------------

CLEAN = [
    ("pe", pe_file(), "setup.exe", "application/x-msdownload", False),
    ("pe-dll", pe_file(), "library.dll", "application/octet-stream", False),
    ("elf", ELF, "libtool.so", "application/x-executable", False),
    ("macho", MACHO, "libthing.dylib", "application/x-mach-binary", False),
    ("java-class", CAFEBABE, "Main.class", "application/java-vm", False),
    ("zip", PLAIN_ZIP, "photos.zip", "application/zip", True),
    ("zip-head-only", PLAIN_ZIP, "photos.zip", "application/zip", False),
    ("docx", DOCX, "Report.docx", "application/zip", True),
    (
        "docx-own-type",
        DOCX,
        "report.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        False,
    ),
    ("xlsx", XLSX, "budget.xlsx", None, True),
    ("jar", JAR, "tool.jar", "application/java-archive", True),
    ("apk", APK, "app.apk", "application/vnd.android.package-archive", True),
    ("7z", SEVEN_Z, "backup.7z", "application/x-7z-compressed", True),
    ("rar4", RAR4, "old.rar", "application/x-rar-compressed", True),
    ("rar5", RAR5, "new.rar", "application/vnd.rar", True),
    ("pdf", PDF, "paper.pdf", "application/pdf", True),
    ("ole-msi", OLE, "installer.msi", "application/x-msi", True),
    ("ole-doc", OLE, "letter.doc", "application/msword", True),
    ("ole-xls", OLE, "sheet.xls", "application/vnd.ms-excel", True),
    ("mp4", MP4, "movie.mp4", "video/mp4", True),
    ("mov", MP4, "clip.mov", "video/quicktime", True),
    ("m4a", MP4, "song.m4a", "audio/mp4", True),
    ("mp3", MP3, "song.mp3", "audio/mpeg", True),
    ("png", png_file(), "photo.png", "image/png", True),
    ("jpeg", jpeg_file(), "photo.jpg", "image/jpeg", True),
    ("jpe", jpeg_file(), "photo.jpe", "image/jpeg; charset=binary", True),
    ("text-ps1", TEXT, "setup.ps1", "text/plain", True),
    ("text-txt", b"just some notes\n", "notes.txt", "text/plain; charset=utf-8", True),
]


@pytest.mark.parametrize(
    ("data", "name", "content_type", "full_scope"),
    [case[1:] for case in CLEAN],
    ids=[case[0] for case in CLEAN],
)
def test_clean_files_of_every_format_produce_no_codes(
    data: bytes, name: str, content_type: str | None, full_scope: bool
) -> None:
    findings = run(data, name, content_type, full_scope)
    if name.endswith(".jar"):
        # A genuine JAR is consistent, but .jar is on the spec's risky-name list: that
        # name-based reason is expected, and no mismatch code is.
        assert findings == [Finding("EXT_RISKY", {"ext": "jar"})]
    else:
        assert findings == []


def test_no_name_and_no_content_type_is_no_signal() -> None:
    assert run(png_file()) == []


# --- helpers ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("movie.MP4", "mp4"),
        ("invoice.pdf.exe", "exe"),
        ("README", None),
        (".bashrc", None),
        ("invoice.pdf .exe", "exe"),
    ],
)
def test_claimed_extension_is_the_last_one_lowercased(name: str, expected: str | None) -> None:
    assert claimed_extension(name) == expected


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("image/PNG", "image/png"),
        ("text/plain; charset=utf-8", "text/plain"),
        ("  application/zip  ", "application/zip"),
        ("", None),
        (None, None),
    ],
)
def test_media_type_drops_parameters(header: str | None, expected: str | None) -> None:
    assert media_type(header) == expected


# --- TYPE_MISMATCH_EXEC -------------------------------------------------------------------


@pytest.mark.parametrize(
    "ext",
    # edge: an executable served as .zip, .pdf, .jpg, .mp4 or .docx; D68 additions
    ["mp4", "pdf", "jpg", "zip", "docx", "gif", "iso", "js", "ps1", "msi", "jar", "txt"],
)
def test_exec_mismatch_for_any_known_non_executable_claim(ext: str) -> None:
    detection = detect(pe_file())
    assert check_exec_mismatch(detection, ext) == [
        Finding(
            "TYPE_MISMATCH_EXEC",
            {
                "claimed_ext": ext,
                "detected": "pe-executable",
                "detected_label": "Windows executable",
            },
        )
    ]


def test_exec_mismatch_counts_probable_executables() -> None:
    detection = detect(b"MZ" + bytes(10))
    assert detection.confidence is DetectionConfidence.probable
    assert codes(check_exec_mismatch(detection, "jpg")) == ["TYPE_MISMATCH_EXEC"]


def test_exec_mismatch_for_elf_and_macho_too() -> None:
    assert codes(check_exec_mismatch(detect(ELF), "mp4")) == ["TYPE_MISMATCH_EXEC"]
    assert codes(check_exec_mismatch(detect(MACHO), "png")) == ["TYPE_MISMATCH_EXEC"]


@pytest.mark.parametrize("ext", ["exe", "dll", "scr", "so", "dylib", None, "php", "aspx", "81"])
def test_no_exec_mismatch_for_executable_or_unknown_claims(ext: str | None) -> None:
    # edge: no extension or a download-script extension → the extension comparison is skipped
    assert check_exec_mismatch(detect(pe_file()), ext) == []


def test_no_exec_mismatch_for_non_executable_content() -> None:
    assert check_exec_mismatch(detect(png_file()), "mp4") == []


def test_full_run_disguised_executable() -> None:
    findings = run(pe_file(), "movie.mp4", "video/mp4", full_scope=True)
    assert codes(findings) == ["TYPE_MISMATCH_EXEC", "TYPE_CONTENT_TYPE_MISMATCH"]


# --- TYPE_MISMATCH_TEXT -------------------------------------------------------------------


@pytest.mark.parametrize("ext", ["pdf", "jpg", "exe", "zip", "gif", "mp3"])
def test_text_mismatch_for_binary_claims(ext: str) -> None:
    # edge: a text file named .pdf or .jpg
    assert check_text_mismatch(detect(TEXT), ext, None) == [
        Finding("TYPE_MISMATCH_TEXT", {"claimed_ext": ext})
    ]


@pytest.mark.parametrize("ext", ["txt", "js", "ps1", "bat", "csv", None, "php"])
def test_no_text_mismatch_for_text_or_unknown_claims(ext: str | None) -> None:
    assert check_text_mismatch(detect(TEXT), ext, "text/plain") == []


def test_no_text_mismatch_when_served_as_html() -> None:
    # D9: HTML is the router's job (LINK_IS_WEB_PAGE), never TYPE_MISMATCH_TEXT.
    assert check_text_mismatch(detect(TEXT), "pdf", "text/html") == []


def test_no_text_mismatch_for_binary_content() -> None:
    assert check_text_mismatch(detect(PDF), "pdf", None) == []


# --- TYPE_MISMATCH_OTHER ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "ext", "label"),
    [
        (png_file(), "jpg", "PNG image"),  # wrong member of the image family
        (ELF, "exe", "Linux executable (ELF)"),  # D69: wrong executable class
        (pe_file(), "so", "Windows executable"),
        (pe_file(), "class", "Windows executable"),
        (JAR, "zip", "Java archive (JAR)"),  # edge: .zip that is really a .jar
        (APK, "zip", "packaged Android app (APK)"),  # edge: .zip that is really an .apk
        (APK, "jar", "packaged Android app (APK)"),
        (DOCX, "xlsx", "Word document (DOCX)"),
        (PDF, "docx", "PDF document"),
        (png_file(), "js", "PNG image"),
        (OLE, "pdf", "Windows Installer or legacy Office file"),
        (MP3, "mp4", "sound file (MP3)"),
    ],
)
def test_other_mismatch(data: bytes, ext: str, label: str) -> None:
    assert check_other_mismatch(detect(data), ext) == [
        Finding("TYPE_MISMATCH_OTHER", {"claimed_ext": ext, "detected_label": label})
    ]


def test_other_mismatch_plain_zip_named_docx_when_listing_proves_it() -> None:
    # edge: a .docx that is really a plain ZIP (full scope: the listing proves no subtype)
    assert check_other_mismatch(detect(PLAIN_ZIP, full_scope=True), "docx") == [
        Finding("TYPE_MISMATCH_OTHER", {"claimed_ext": "docx", "detected_label": "ZIP archive"})
    ]


@pytest.mark.parametrize(
    ("data", "ext"),
    [
        (jpeg_file(), "jpeg"),  # equivalence class {jpg, jpeg, jpe}
        (jpeg_file(), "jpe"),
        (MP4, "mov"),  # edge: equivalence class {mp4, m4a, m4v, mov}
        (MP4, "m4v"),
        (OLE, "msi"),  # equivalence class {msi, doc, xls}
        (OLE, "xls"),
        (DOCX, "zip"),  # a DOCX is a ZIP
        (RAR5, "rar"),
        (png_file(), "gif"),  # D68: formats we cannot detect never feed OTHER
        (png_file(), "php"),  # unknown claim
        (png_file(), None),
        (pe_file(), "zip"),  # executable content → TYPE_MISMATCH_EXEC, not OTHER
        (TEXT, "pdf"),  # text content → TYPE_MISMATCH_TEXT, not OTHER
        (UNKNOWN_BYTES, "pdf"),  # unknown content → no type codes
        (pe_file(), "dll"),  # edge: the whole PE family is one class
        (b"MZ" + bytes(10), "com"),
        (CAFEBABE, "dylib"),
    ],
)
def test_no_other_mismatch(data: bytes, ext: str | None) -> None:
    assert check_other_mismatch(detect(data), ext) == []


def test_no_other_mismatch_on_unconfirmed_zip_subtype() -> None:
    # edge: OOXML whose [Content_Types].xml is not in the head → "subtype unconfirmed", no code
    detection = detect(PLAIN_ZIP, full_scope=False)
    assert detection.confidence is DetectionConfidence.unconfirmed
    assert check_other_mismatch(detection, "docx") == []


# --- EXT_DOUBLE ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "decoy", "real"),
    [
        ("invoice.pdf.exe", "pdf", "exe"),  # edge: deceptive double extension
        ("Invoice.PDF.EXE", "pdf", "exe"),
        ("invoice.pdf .exe", "pdf", "exe"),  # D71: whitespace stripped from the decoy
        ("holiday.jpg.scr", "jpg", "scr"),
        ("song.mp3.vbs", "mp3", "vbs"),
        ("report.docx.js", "docx", "js"),
        ("invoice.pdf.msi", "pdf", "msi"),  # D71 lists msi as a risky real extension
        ("archive.zip.exe", "zip", "exe"),  # D71 lists zip, rar and 7z as decoys
        ("backup.rar.scr", "rar", "scr"),
        ("photos.7z.bat", "7z", "bat"),
    ],
)
def test_double_extension(name: str, decoy: str, real: str) -> None:
    assert check_double_extension(name) == [
        Finding("EXT_DOUBLE", {"decoy_ext": decoy, "real_ext": real})
    ]


@pytest.mark.parametrize(
    "name",
    [
        "setup.1.2.exe",  # D71: a version number is not a decoy
        "archive.tar.gz",
        "report.pdf",
        "report.final.pdf",
        "invoice.exe.pdf",  # the last extension is not risky
        "setup.exe",
        "README",
    ],
)
def test_no_double_extension(name: str) -> None:
    assert check_double_extension(name) == []


# --- EXT_RISKY ----------------------------------------------------------------------------


@pytest.mark.parametrize("ext", ["scr", "lnk", "hta", "vbs", "cmd", "jar", "com", "pif"])
def test_risky_extension(ext: str) -> None:
    # edge: formats outside the list still get a name-based reason
    assert check_risky_extension(ext) == [Finding("EXT_RISKY", {"ext": ext})]


@pytest.mark.parametrize("ext", ["exe", "pdf", "iso", None])
def test_no_risky_extension(ext: str | None) -> None:
    assert check_risky_extension(ext) == []


# --- EXT_SPOOFED_NAME ---------------------------------------------------------------------

# Built with chr() so no invisible character appears in this source file (Trojan Source rule).
RLO = chr(0x202E)  # right-to-left override
ZWSP = chr(0x200B)  # zero-width space
LRI = chr(0x2066)  # left-to-right isolate
BOM = chr(0xFEFF)  # byte-order mark / zero-width no-break space
SPOOFED = f"photo{RLO}gpj.exe"  # shows as "photoexe.jpg"


@pytest.mark.parametrize(
    ("name", "characters"),
    [
        (SPOOFED, "U+202E"),  # edge: right-to-left override
        (f"a{ZWSP}b{RLO}c{ZWSP}.exe", "U+200B, U+202E"),  # distinct, in order of first use
        ("file\x00.pdf", "U+0000"),  # NUL (category Cc)
        (f"bad{LRI}name.pdf", "U+2066"),  # bidi isolate (category Cf)
        (f"x{BOM}.txt", "U+FEFF"),
    ],
)
def test_spoofed_name(name: str, characters: str) -> None:
    assert check_spoofed_name(name) == [Finding("EXT_SPOOFED_NAME", {"characters": characters})]


@pytest.mark.parametrize("name", ["résumé.pdf", "日本語の資料.pdf", "my file (1).zip", "a.b.c"])
def test_no_spoofed_name(name: str) -> None:
    assert check_spoofed_name(name) == []


def test_spoofed_name_runs_on_the_display_form() -> None:
    findings = run(pe_file(), SPOOFED)
    assert codes(findings) == ["EXT_SPOOFED_NAME"]


# --- TYPE_CONTENT_TYPE_MISMATCH -----------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "content_type", "expected_type", "label"),
    [
        (pe_file(), "image/jpeg", "image/jpeg", "Windows executable"),
        (pe_file(), "Video/MP4; codecs=avc1", "video/mp4", "Windows executable"),
        # edge: magic bytes say MP4, Content-Type says executable
        (MP4, "application/x-msdownload", "application/x-msdownload", "video file (MP4 family)"),
        (png_file(), "image/jpeg", "image/jpeg", "PNG image"),
        (PDF, "application/zip", "application/zip", "PDF document"),
        (ELF, "application/x-msdownload", "application/x-msdownload", "Linux executable (ELF)"),
    ],
)
def test_content_type_mismatch(
    data: bytes, content_type: str, expected_type: str, label: str
) -> None:
    assert check_content_type(detect(data), media_type(content_type)) == [
        Finding(
            "TYPE_CONTENT_TYPE_MISMATCH", {"content_type": expected_type, "detected_label": label}
        )
    ]


@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        (pe_file(), None),  # edge: missing → no signal
        (pe_file(), "application/octet-stream"),  # edge: generic → no signal
        (pe_file(), "binary/octet-stream"),
        (pe_file(), "application/force-download"),
        (pe_file(), "application/x-unheard-of"),  # D70: a type in no row → no signal
        (pe_file(), "text/html"),  # D9: the router's job
        (DOCX, "application/zip"),  # edge: application/zip for a .docx is very common
        (JAR, "application/zip"),
        (PLAIN_ZIP, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        (jpeg_file(), "image/pjpeg"),
        (MP4, "video/quicktime"),
        (UNKNOWN_BYTES, "image/png"),  # D70: unknown detection → no signal
        (TEXT, "application/json"),
    ],
)
def test_no_content_type_mismatch(data: bytes, content_type: str | None) -> None:
    assert check_content_type(detect(data), media_type(content_type)) == []


@pytest.mark.parametrize(
    "content_type",
    [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/java-archive",
        "application/vnd.android.package-archive",
    ],
)
def test_content_type_mismatch_for_a_proven_plain_zip(content_type: str) -> None:
    # Full scope: the listing proves a plain ZIP, so a member's media type contradicts it.
    # (The same header on a head-only, unconfirmed ZIP is no signal: see the test above.)
    detection = detect(PLAIN_ZIP, full_scope=True)
    assert check_content_type(detection, content_type) == [
        Finding(
            "TYPE_CONTENT_TYPE_MISMATCH",
            {"content_type": content_type, "detected_label": "ZIP archive"},
        )
    ]


def test_proven_plain_zip_still_fits_the_generic_zip_type() -> None:
    assert check_content_type(detect(PLAIN_ZIP, full_scope=True), "application/zip") == []


# --- TYPE_POLYGLOT (P1, D73) --------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "label", "second_label", "offset"),
    [
        (png_file(b"PK\x03\x04"), "PNG image", "ZIP archive", 32),  # edge: image plus ZIP
        (jpeg_file(b"%PDF-1.4"), "JPEG image", "PDF document", 32),
        (PDF + b"PK\x03\x04", "PDF document", "ZIP archive", len(PDF)),  # edge: PDF plus ZIP
        (MP4 + b"PK\x03\x04", "video file (MP4 family)", "ZIP archive", len(MP4)),
        (MP3 + b"%PDF-1.4", "sound file (MP3)", "PDF document", len(MP3)),
        # Both signatures: the first one in the file is reported.
        (png_file(b"%PDF-1.4" + bytes(8) + b"PK\x03\x04"), "PNG image", "PDF document", 32),
    ],
)
def test_polyglot(data: bytes, label: str, second_label: str, offset: int) -> None:
    assert check_polyglot(detect(data), data) == [
        Finding(
            "TYPE_POLYGLOT",
            {"detected_label": label, "second_label": second_label, "offset": offset},
        )
    ]


@pytest.mark.parametrize(
    "data",
    [
        png_file(),
        PDF,
        zip_file(("paper.pdf", PDF)),  # D73: a ZIP storing a PDF is not a polyglot
        DOCX,
        pe_file() + b"PK\x03\x04%PDF-",  # executables are excluded
        OLE + b"PK\x03\x04",  # OLE is excluded
        TEXT * 10 + b"PK\x03\x04",  # text is excluded
        png_file(bytes(1100) + b"%PDF-"),  # %PDF- only counts in the first 1024 bytes
        PDF + b"%PDF-1.4",  # a PDF never matches its own signature
    ],
)
def test_no_polyglot(data: bytes) -> None:
    assert check_polyglot(detect(data), data) == []


# --- TYPE_EXEC_PROBABLE and TYPE_UNKNOWN (info) ------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        b"MZ" + bytes(10),  # edge: too short to read e_lfanew → probable PE
        pe_file(e_lfanew=0x400, pe_header=False),  # edge: e_lfanew points past the buffer
        pe_file(pe_header=False),  # edge: DOS stub, no PE\0\0 → dos-executable
    ],
)
def test_exec_probable(data: bytes) -> None:
    assert check_exec_probable(detect(data)) == [Finding("TYPE_EXEC_PROBABLE", {})]


@pytest.mark.parametrize("data", [pe_file(), CAFEBABE, ELF, png_file()])
def test_no_exec_probable(data: bytes) -> None:
    # D74: CAFEBABE is probable too, but it is not MZ, so the message would be false.
    assert check_exec_probable(detect(data)) == []


@pytest.mark.parametrize("data", [UNKNOWN_BYTES, b"PK", b"\x89P"])
def test_unknown_type(data: bytes) -> None:
    # edge: shorter than the signature → informational reason
    assert check_unknown_type(detect(data), data) == [Finding("TYPE_UNKNOWN", {})]


@pytest.mark.parametrize("data", [b"", png_file(), TEXT])
def test_no_unknown_type(data: bytes) -> None:
    # An empty body is FETCH_EMPTY (fetcher), not TYPE_UNKNOWN (D74).
    assert check_unknown_type(detect(data), data) == []


# --- full-scope ZIP subtype (D75) ---------------------------------------------------------

UNCONFIRMED_ZIP = Detection(
    "zip",
    "ZIP-based file (subtype unconfirmed)",
    Family.archive,
    DetectionConfidence.unconfirmed,
    None,
)


def test_refine_proves_docx_from_the_listing() -> None:
    refined = refine_zip_subtype(UNCONFIRMED_ZIP, DOCX, True, SETTINGS)
    assert (refined.type, refined.family, refined.confidence) == (
        "docx",
        Family.document,
        DetectionConfidence.certain,
    )


def test_refine_proves_a_plain_zip_and_keeps_the_signature() -> None:
    head = detect_type(PLAIN_ZIP, SETTINGS)
    refined = refine_zip_subtype(head, PLAIN_ZIP, True, SETTINGS)
    assert (refined.type, refined.label, refined.confidence) == (
        "zip",
        "ZIP archive",
        DetectionConfidence.certain,
    )
    assert refined.signature == head.signature


def test_refine_does_nothing_for_partial_scope() -> None:
    assert refine_zip_subtype(UNCONFIRMED_ZIP, DOCX, False, SETTINGS) is UNCONFIRMED_ZIP


@pytest.mark.parametrize("data", [PLAIN_ZIP[:-10], PLAIN_ZIP[:40], b"PK\x03\x04" + bytes(60)])
def test_refine_keeps_the_head_result_for_corrupt_or_truncated_zips(data: bytes) -> None:
    assert refine_zip_subtype(UNCONFIRMED_ZIP, data, True, SETTINGS) is UNCONFIRMED_ZIP


def test_refine_keeps_the_head_result_above_the_entry_cap() -> None:
    data = zip_file("a.txt", "b.txt", "c.txt")
    settings = Settings(zip_max_entries=2)
    assert refine_zip_subtype(UNCONFIRMED_ZIP, data, True, settings) is UNCONFIRMED_ZIP


def test_refine_leaves_other_detections_alone() -> None:
    certain_docx = detect_type(DOCX, SETTINGS)
    assert refine_zip_subtype(certain_docx, PLAIN_ZIP, True, SETTINGS) is certain_docx
    png = detect_type(png_file(), SETTINGS)
    assert refine_zip_subtype(png, png_file(), True, SETTINGS) is png


# --- every emitted code is registered with exactly its declared evidence keys (D67) -------


def every_kind_of_finding() -> list[Finding]:
    return [
        *check_exec_mismatch(detect(pe_file()), "mp4"),
        *check_text_mismatch(detect(TEXT), "pdf", None),
        *check_other_mismatch(detect(png_file()), "jpg"),
        *check_double_extension("invoice.pdf.exe"),
        *check_risky_extension("scr"),
        *check_spoofed_name(SPOOFED),
        *check_content_type(detect(pe_file()), "image/jpeg"),
        *check_polyglot(detect(png_file(b"PK\x03\x04")), png_file(b"PK\x03\x04")),
        *check_exec_probable(detect(b"MZ" + bytes(10))),
        *check_unknown_type(detect(UNKNOWN_BYTES), UNKNOWN_BYTES),
    ]


def test_every_check_emits_a_registered_code_with_its_declared_evidence() -> None:
    registry = load_registry().codes
    findings = every_kind_of_finding()
    assert len({finding.code for finding in findings}) == 10
    for finding in findings:
        assert finding.code in registry
        assert set(finding.evidence) == set(registry[finding.code].evidence), finding.code
        assert all(isinstance(value, str | int) for value in finding.evidence.values())


def test_every_d71_extension_is_in_the_double_extension_sets() -> None:
    """D71's lists are the minimum; the implementation may add more (D77), never fewer."""
    d71_real = {"exe", "dll", "scr", "com", "pif", "cpl", "msi", "js", "ps1", "bat", "cmd", "vbs",
                "hta", "lnk", "jar"}  # fmt: skip
    d71_decoys = {"pdf", "doc", "docx", "xls", "xlsx", "txt", "mp4", "m4a", "m4v", "mov", "mp3",
                  "png", "jpg", "jpeg", "jpe", "zip", "rar", "7z"}  # fmt: skip
    assert d71_real <= DOUBLE_REAL_EXTENSIONS
    assert d71_decoys <= DOUBLE_DECOY_EXTENSIONS


def test_unknown_bytes_never_raise_other_even_if_marked_certain() -> None:
    """D69: unknown content raises no type mismatch code, whatever its confidence says."""
    unknown = Detection("unknown", "unknown", Family.unknown, DetectionConfidence.certain, None)
    assert check_other_mismatch(unknown, "pdf") == []
