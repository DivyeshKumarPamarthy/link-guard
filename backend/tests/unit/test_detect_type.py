"""Detection on inline byte fixtures (task T1.5, spec §7). No network, no generated samples.

Rows from the M4 edge-case table of the original plan are marked "edge:".
"""

import struct

import pytest

from app.contract.models import DetectionConfidence, Family, Signature
from app.core.config import Settings
from app.engine.detect.names import (
    claimed_name,
    extension_chain,
    filename_from_content_disposition,
    normalize_name,
)
from app.engine.detect.signatures import detect_type

CERTAIN = DetectionConfidence.certain
PROBABLE = DetectionConfidence.probable
UNCONFIRMED = DetectionConfidence.unconfirmed


# --- fixture builders --------------------------------------------------------------------


def pe_file(e_lfanew: int = 0x80, size: int = 0x100) -> bytes:
    """A minimal PE head: MZ, e_lfanew at 0x3C, PE\\0\\0 at e_lfanew."""
    data = bytearray(size)
    data[0:2] = b"MZ"
    data[0x3C:0x40] = struct.pack("<I", e_lfanew)
    if e_lfanew + 4 <= size:
        data[e_lfanew : e_lfanew + 4] = b"PE\0\0"
    return bytes(data)


def zip_local_header(name: str) -> bytes:
    """One stored ZIP local file header with no data."""
    encoded = name.encode()
    return b"PK\x03\x04" + bytes(22) + struct.pack("<HH", len(encoded), 0) + encoded


def mp3_frame() -> bytes:
    """One MPEG-1 Layer III frame: 128 kbit/s, 44.1 kHz, no padding → 417 bytes."""
    return b"\xff\xfb\x90\x00" + bytes(413)


# --- every format in the spec §7 table ----------------------------------------------------

FORMATS = [
    ("pe", pe_file(), "pe-executable", Family.executable, CERTAIN),
    ("elf", b"\x7fELF\x02\x01\x01" + bytes(57), "elf-executable", Family.executable, CERTAIN),
    ("macho-32", b"\xfe\xed\xfa\xce" + bytes(28), "macho-executable", Family.executable, CERTAIN),
    ("macho-64", b"\xfe\xed\xfa\xcf" + bytes(28), "macho-executable", Family.executable, CERTAIN),
    (
        "macho-32-le",
        b"\xce\xfa\xed\xfe" + bytes(28),
        "macho-executable",
        Family.executable,
        CERTAIN,
    ),
    (
        "macho-64-le",
        b"\xcf\xfa\xed\xfe" + bytes(28),
        "macho-executable",
        Family.executable,
        CERTAIN,
    ),
    (
        "cafebabe",
        b"\xca\xfe\xba\xbe" + bytes(28),
        "java-class-or-macho",
        Family.executable,
        PROBABLE,
    ),
    ("zip-empty", b"PK\x05\x06" + bytes(18), "zip", Family.archive, CERTAIN),
    ("7z", b"7z\xbc\xaf\x27\x1c" + bytes(26), "7z", Family.archive, CERTAIN),
    ("rar4", b"Rar!\x1a\x07\x00" + bytes(25), "rar4", Family.archive, CERTAIN),
    ("rar5", b"Rar!\x1a\x07\x01\x00" + bytes(24), "rar5", Family.archive, CERTAIN),
    ("pdf", b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n", "pdf", Family.document, CERTAIN),
    (
        "docx",
        zip_local_header("[Content_Types].xml") + zip_local_header("word/document.xml"),
        "docx",
        Family.document,
        CERTAIN,
    ),
    (
        "xlsx",
        zip_local_header("[Content_Types].xml") + zip_local_header("xl/workbook.xml"),
        "xlsx",
        Family.document,
        CERTAIN,
    ),
    ("ole", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(24), "ole", Family.document, CERTAIN),
    ("text", b"Write-Host 'hello'\r\nexit 0\r\n", "text", Family.text, PROBABLE),
    ("mp4", b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00", "mp4", Family.media, CERTAIN),
    ("mp3-id3", b"ID3\x04\x00\x00\x00\x00\x00\x00" + mp3_frame(), "mp3", Family.media, CERTAIN),
    ("mp3-two-frames", mp3_frame() + mp3_frame(), "mp3", Family.media, CERTAIN),
    ("png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "png", Family.image, CERTAIN),
    ("jpeg", b"\xff\xd8\xff\xe0\x00\x10JFIF\x00", "jpeg", Family.image, CERTAIN),
]


@pytest.mark.parametrize(
    ("data", "type_", "family", "confidence"),
    [row[1:] for row in FORMATS],
    ids=[row[0] for row in FORMATS],
)
def test_every_format_is_detected(
    data: bytes, type_: str, family: Family, confidence: DetectionConfidence
) -> None:
    result = detect_type(data)
    assert (result.type, result.family, result.confidence) == (type_, family, confidence)


@pytest.mark.parametrize("row", FORMATS, ids=[row[0] for row in FORMATS])
def test_labels_read_correctly_after_a(row: tuple[object, ...]) -> None:
    """D27: templates say "a {detected_label}", so no label may start with a vowel sound."""
    label = detect_type(row[1]).label  # type: ignore[arg-type]
    assert label and label[0].lower() not in "aeiou"
    assert not label.upper().startswith(("MP", "MPEG", "ELF", "OLE", "XLSX", "MSI"))


# --- PE edge cases -----------------------------------------------------------------------


def test_pe_signature_marks_mz_for_the_hex_strip() -> None:
    result = detect_type(pe_file())
    assert result.signature == Signature(offset=0, length=2, name="MZ (Windows executable)")
    assert result.label == "Windows executable"


def test_mz_with_e_lfanew_past_the_buffer_is_probable_pe() -> None:
    """edge: e_lfanew points past the buffer → treat as probable PE."""
    result = detect_type(pe_file(e_lfanew=0x10000, size=0x100))
    assert (result.type, result.family, result.confidence) == (
        "pe-executable",
        Family.executable,
        PROBABLE,
    )


def test_mz_too_short_to_read_e_lfanew_is_probable_pe() -> None:
    result = detect_type(b"MZ\x90\x00")
    assert (result.type, result.confidence) == ("pe-executable", PROBABLE)


def test_mz_without_pe_header_inside_buffer_is_dos_executable() -> None:
    """edge: MZ but no PE\\0\\0 where e_lfanew points (DOS stub) → "DOS/other executable"."""
    data = bytearray(pe_file())
    data[0x80:0x84] = b"XXXX"
    result = detect_type(bytes(data))
    assert (result.type, result.family, result.confidence) == (
        "dos-executable",
        Family.executable,
        PROBABLE,
    )


def test_huge_e_lfanew_does_not_crash() -> None:
    result = detect_type(pe_file(e_lfanew=0xFFFFFFFF))
    assert result.confidence == PROBABLE


# --- ZIP edge cases ----------------------------------------------------------------------


def test_spanned_zip_marker_is_a_zip_variant() -> None:
    """edge: PK\\x07\\x08 (spanned archive) is recognised as ZIP."""
    result = detect_type(b"PK\x07\x08" + zip_local_header("a.txt"))
    assert (result.type, result.family) == ("zip", Family.archive)


def test_zip_without_known_entries_in_head_is_subtype_unconfirmed() -> None:
    """edge: OOXML whose [Content_Types].xml is not in the head → ZIP-based, unconfirmed."""
    result = detect_type(zip_local_header("readme.txt") + bytes(100))
    assert (result.type, result.confidence) == ("zip", UNCONFIRMED)
    assert result.label == "ZIP-based file (subtype unconfirmed)"


def test_content_types_without_word_or_xl_is_unconfirmed() -> None:
    data = zip_local_header("[Content_Types].xml") + zip_local_header("_rels/.rels")
    assert detect_type(data).confidence == UNCONFIRMED


def test_word_entry_without_content_types_is_unconfirmed() -> None:
    data = zip_local_header("word/document.xml")
    assert detect_type(data).confidence == UNCONFIRMED


@pytest.mark.parametrize(
    ("entries", "type_"),
    [
        (["META-INF/MANIFEST.MF", "com/example/Main.class"], "jar"),
        (["AndroidManifest.xml", "META-INF/MANIFEST.MF", "classes.dex"], "apk"),
    ],
)
def test_jar_and_apk_are_recognised_from_entry_names(entries: list[str], type_: str) -> None:
    data = b"".join(zip_local_header(name) for name in entries)
    result = detect_type(data)
    assert (result.type, result.family, result.confidence) == (type_, Family.archive, CERTAIN)


def test_zip_entry_scan_respects_entry_cap() -> None:
    """A head full of fake local headers stops at the configured cap (no unbounded work)."""
    filler = b"".join(zip_local_header(f"f{i}") for i in range(20))
    data = filler + zip_local_header("[Content_Types].xml") + zip_local_header("word/x.xml")
    assert detect_type(data, Settings(zip_max_entries=5)).type == "zip"
    assert detect_type(data, Settings(zip_max_entries=100)).type == "docx"


def test_truncated_zip_local_header_does_not_crash() -> None:
    result = detect_type(b"PK\x03\x04\x14\x00")
    assert (result.type, result.confidence) == ("zip", UNCONFIRMED)


def test_zip_signature_is_marked() -> None:
    result = detect_type(zip_local_header("[Content_Types].xml") + zip_local_header("xl/a"))
    assert result.signature == Signature(offset=0, length=4, name="PK (ZIP container)")


# --- PDF, MP4, MP3 -----------------------------------------------------------------------


def test_pdf_header_may_start_within_first_1024_bytes() -> None:
    result = detect_type(b"\x00" * 500 + b"%PDF-1.4\n")
    assert (result.type, result.confidence) == ("pdf", CERTAIN)
    assert result.signature is None  # beyond the 16-byte hex strip


def test_pdf_header_after_1024_bytes_is_not_pdf() -> None:
    assert detect_type(b"\x00" * 1024 + b"%PDF-1.4\n").type != "pdf"


@pytest.mark.parametrize("brand", [b"qt  ", b"M4A ", b"isom", b"M4V "])
def test_mp4_family_brands_are_one_type(brand: bytes) -> None:
    """edge: .mp4/.mov/.m4a share ftyp and differ only by brand."""
    result = detect_type(b"\x00\x00\x00\x20ftyp" + brand + bytes(8))
    assert result.type == "mp4"
    assert result.signature == Signature(offset=4, length=4, name="ftyp (MP4 family)")


def test_single_mp3_frame_sync_is_only_probable() -> None:
    """edge: frame sync alone is probable; a second valid header makes it certain."""
    result = detect_type(mp3_frame())
    assert (result.type, result.confidence) == ("mp3", PROBABLE)


def test_mp3_frame_followed_by_garbage_is_probable() -> None:
    assert detect_type(mp3_frame() + b"\x00" * 10).confidence == PROBABLE


@pytest.mark.parametrize(
    "header",
    [
        b"\xff\xfb\xf0\x00",  # bitrate index 15 (invalid)
        b"\xff\xfb\x9c\x00",  # sample-rate index 3 (reserved)
        b"\xff\xeb\x90\x00",  # MPEG version "01" (reserved)
        b"\xff\xff\x90\x00",  # Layer I, not MP3
    ],
)
def test_invalid_frame_headers_are_not_mp3(header: bytes) -> None:
    assert detect_type(header + bytes(60)).type != "mp3"


def test_mpeg2_layer3_frames_are_mp3() -> None:
    # MPEG-2 Layer III, 64 kbit/s, 22.05 kHz → 72000 * 64 // 22050 = 208 bytes
    frame = b"\xff\xf3\x80\x00" + bytes(204)
    assert detect_type(frame + frame).confidence == CERTAIN


# --- text --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "bom_length"),
    [
        (b"\xef\xbb\xbfconsole.log('hi');\n", 3),
        (b"\xff\xfe" + "Write-Host 'hi'\r\n".encode("utf-16-le"), 2),
        (b"\xfe\xff" + "@echo off\r\n".encode("utf-16-be"), 2),
    ],
    ids=["utf-8-bom", "utf-16-le-bom", "utf-16-be-bom"],
)
def test_text_with_byte_order_mark(data: bytes, bom_length: int) -> None:
    result = detect_type(data)
    assert (result.type, result.family) == ("text", Family.text)
    assert result.signature is not None and result.signature.length == bom_length


def test_utf8_text_without_bom_is_text() -> None:
    assert detect_type("echo héllo wörld\n".encode()).type == "text"


def test_random_binary_is_unknown_not_text() -> None:
    data = bytes(range(256)) * 4
    result = detect_type(data)
    assert (result.type, result.family, result.confidence) == (
        "unknown",
        Family.unknown,
        UNCONFIRMED,
    )


def test_nul_bytes_mean_not_text() -> None:
    assert detect_type(b"hello\x00world").type == "unknown"


def test_printable_ratio_comes_from_settings() -> None:
    data = b"abcdefghi\x01"  # 90 % printable
    assert detect_type(data, Settings(text_min_printable_ratio=0.95)).type == "unknown"
    assert detect_type(data, Settings(text_min_printable_ratio=0.85)).type == "text"


# --- too short, unknown ------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [b"", b"\x89P", b"PK", b"\x7fE", b"Rar!", b"\xd0\xcf\x11", b"\x00\x00\x00\x18fty"],
    ids=["empty", "png-prefix", "pk", "elf-prefix", "rar-prefix", "ole-prefix", "mp4-prefix"],
)
def test_shorter_than_the_signature_is_unknown(data: bytes) -> None:
    """edge: file shorter than the signature (0-10 bytes) → type unknown."""
    result = detect_type(data)
    assert (result.type, result.family, result.signature) == ("unknown", Family.unknown, None)


def test_riskiest_family_wins_for_exe_containing_pdf_marker() -> None:
    """edge (polyglot): MZ at 0 and %PDF- later → executable is reported."""
    data = pe_file() + b"%PDF-1.4"
    assert detect_type(data).family == Family.executable


# --- Content-Disposition -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ('attachment; filename="movie.mp4"', "movie.mp4"),
        ("attachment; filename=movie.mp4", "movie.mp4"),
        ("ATTACHMENT; FILENAME=Movie.MP4", "Movie.MP4"),
        ("inline; filename=report.pdf", "report.pdf"),
        ('attachment; filename="a \\"quoted\\" name.txt"', 'a "quoted" name.txt'),
        ('attachment; filename="semi;colon.zip"', "semi;colon.zip"),
        ("attachment; filename*=UTF-8''na%C3%AFve%20file.pdf", "naïve file.pdf"),
        ("attachment; filename*=utf-8'en'%E2%82%AC%20rates.xlsx", "€ rates.xlsx"),
        ("attachment; filename*=ISO-8859-1''caf%E9.txt", "café.txt"),
        (
            "attachment; filename=\"fallback.exe\"; filename*=UTF-8''real.pdf",
            "real.pdf",
        ),
        (
            "attachment; filename*=UTF-8''real.pdf; filename=\"fallback.exe\"",
            "real.pdf",
        ),
        ("attachment; filename*=KOI8-R''x.pdf; filename=plain.pdf", "plain.pdf"),
        ("attachment; filename*=garbage; filename=plain.pdf", "plain.pdf"),
        ("attachment; filename*=UTF-8''%FF%FE.pdf; filename=plain.pdf", "plain.pdf"),
        ("attachment", None),
        ("", None),
        ('attachment; filename=""', None),
        ("attachment; filename=", None),
        ('attachment; filename="unterminated.exe', "unterminated.exe"),
        ("attachment;;; filename = spaced.zip ;", "spaced.zip"),
    ],
)
def test_content_disposition_variants(header: str, expected: str | None) -> None:
    assert filename_from_content_disposition(header) == expected


def test_content_disposition_never_raises_on_hostile_input() -> None:
    for header in ['"', ";", "=", "filename*='", "filename*=''%", 'a; b="\\', "\x00\x01;\u202e"]:
        filename_from_content_disposition(header)  # must not raise


# --- claimed name: source order and normalisation -----------------------------------------


def test_content_disposition_wins_over_urls() -> None:
    name = claimed_name(
        'attachment; filename="movie.mp4"',
        "https://cdn.example/files/x.bin",
        "https://short.example/abc.zip",
    )
    assert name is not None
    assert (name.display, name.source) == ("movie.mp4", "content-disposition")


def test_final_url_then_original_url() -> None:
    name = claimed_name(
        None, "https://cdn.example/dl/Setup%20File.EXE?x=1#f", "https://a.example/b.zip"
    )
    assert name is not None
    assert (name.display, name.compare, name.source) == (
        "Setup File.EXE",
        "setup file.exe",
        "final-url",
    )
    name = claimed_name(None, "https://cdn.example/", "https://a.example/b.zip")
    assert name is not None
    assert (name.display, name.source) == ("b.zip", "original-url")


def test_no_name_anywhere_is_none() -> None:
    assert claimed_name(None, "https://cdn.example/", "https://a.example") is None


def test_content_disposition_without_filename_falls_back_to_url() -> None:
    name = claimed_name("attachment", "https://cdn.example/a/report.pdf", None)
    assert name is not None and name.source == "final-url"


@pytest.mark.parametrize(
    ("raw", "display"),
    [
        ("../../etc/passwd", "passwd"),
        ("..\\..\\windows\\evil.exe", "evil.exe"),
        ("C:\\Users\\x\\file.pdf", "file.pdf"),
        ("file.exe.", "file.exe"),  # edge: Windows ignores trailing dots
        ("file.exe   ", "file.exe"),  # edge: ... and trailing spaces
        ("file.exe . . ", "file.exe"),
        ("..", None),
        (".", None),
        ("dir/", None),
        ("   ", None),
        ("a%2Fb.zip", "b.zip"),  # decoded slash is still a path separator
        ("photo\u202egpj.exe", "photo\u202egpj.exe"),  # kept for EXT_SPOOFED_NAME (T2.2)
        ("nul\x00byte.pdf", "nul\x00byte.pdf"),  # kept as data; escaped at display
    ],
)
def test_normalize_name(raw: str, display: str | None) -> None:
    """edge: names with \\, .., NUL, RTL override: last segment only, never used as a path."""
    assert normalize_name(raw, decode_percent=True) == display


def test_rfc5987_value_is_not_percent_decoded_twice() -> None:
    header = "attachment; filename*=UTF-8''100%2525.txt"
    name = claimed_name(header, None, None)
    assert name is not None and name.display == "100%25.txt"


def test_content_disposition_path_is_stripped() -> None:
    name = claimed_name('attachment; filename="../../.bashrc"', None, None)
    assert name is not None and name.display == ".bashrc"


# --- extension chain ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "chain"),
    [
        ("movie.mp4", ("mp4",)),
        ("invoice.pdf.exe", ("pdf", "exe")),
        ("Invoice.PDF.EXE", ("pdf", "exe")),
        ("archive.tar.gz", ("tar", "gz")),
        ("README", ()),
        (".bashrc", ()),
        ("..hidden.txt", ("txt",)),
        ("trailing.", ()),
        ("a..b", ("b",)),
        ("download.php", ("php",)),
    ],
)
def test_extension_chain(name: str, chain: tuple[str, ...]) -> None:
    assert extension_chain(name) == chain


def test_last_extension_survives_trailing_dots_after_normalising() -> None:
    normalized = normalize_name("setup.exe. ", decode_percent=False)
    assert normalized is not None
    assert extension_chain(normalized) == ("exe",)
