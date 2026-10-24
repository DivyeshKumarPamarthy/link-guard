"""Generate the harmless sample files the demo server serves (spec §11, task T2.6).

Usage: `make samples`, or `uv run python make_samples.py [--out DIR]` inside `demo/`.

Writes into `samples/` (gitignored, never committed):
- one small genuine file for every format in spec §7, built byte by byte here;
- `disguised/`: the same bytes under misleading names (movie.mp4 that is really a program...);
- `SHA256SUMS`: the hash of every file, so two machines can compare their samples.

Reproducible on purpose: "random" bytes come from a fixed seed, ZIP entries get a fixed date
and no timestamp anywhere depends on the clock, so every run writes identical bytes.
Every file is harmless: nothing here is ever executed. The "hello" program only returns.
"""

import argparse
import hashlib
import io
import random
import struct
import zipfile
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "samples"

SEED = 20261016  # fixed seed: the "random" pixels and padding are the same on every run
ZIP_DATE_TIME = (2026, 10, 16, 0, 0, 0)  # fixed entry date instead of "now"
GREETING = b"Hello from LinkGuard"


# --- executables -------------------------------------------------------------------------


def hello_pe() -> bytes:
    """A 1 KB 32-bit Windows program (PE) whose only code is `xor eax, eax; ret`.

    It imports nothing and does nothing but return 0, so it is harmless even if someone
    runs it. Layout: DOS header (MZ) -> PE signature at e_lfanew -> COFF header ->
    optional header -> one `.text` section header, then the section itself at 0x200.
    """
    e_lfanew = 0x40
    file_alignment, section_alignment = 0x200, 0x1000
    # DOS header: the usual values (spec §2's example bytes 4d5a9000 0300...), e_lfanew last.
    dos_header = struct.pack(
        "<2s13H8x2H20xI", b"MZ", 0x90, 3, 0, 4, 0, 0xFFFF, 0, 0xB8, 0, 0, 0, 0x40, 0, 0, 0,
        e_lfanew,
    )  # fmt: skip
    coff_header = struct.pack(
        "<HHIIIHH",
        0x014C,  # machine: Intel 386
        1,  # one section
        0,  # timestamp 0: reproducible
        0,
        0,
        224,  # size of the PE32 optional header
        0x0102,  # executable image, 32-bit
    )
    optional_header = struct.pack(
        "<HBBIIIIIIIIIHHHHHHIIIIHHIIIIII",
        0x10B,  # PE32
        0, 0,  # linker version
        file_alignment,  # size of code
        0, 0,  # initialised / uninitialised data
        section_alignment,  # entry point: start of .text
        section_alignment,  # base of code
        0,  # base of data
        0x400000,  # image base
        section_alignment,
        file_alignment,
        4, 0, 0, 0, 4, 0,  # OS, image and subsystem versions
        0,  # Win32 version value
        2 * section_alignment,  # size of image: headers page + .text page
        file_alignment,  # size of headers
        0,  # checksum
        3,  # subsystem: console
        0,  # DLL characteristics
        0x100000, 0x1000, 0x100000, 0x1000,  # stack and heap sizes
        0,  # loader flags
        16,  # number of data directories (all empty: no imports)
    ) + bytes(16 * 8)  # fmt: skip
    code = b"\x31\xc0\xc3"  # xor eax, eax; ret
    text = code + GREETING + b". This program does nothing and exits.\0"
    section_header = struct.pack(
        "<8sIIIIIIHHI",
        b".text",
        len(text),  # virtual size
        section_alignment,  # virtual address
        file_alignment,  # size of raw data
        file_alignment,  # pointer to raw data
        0, 0, 0, 0,
        0x60000020,  # code, execute, read
    )  # fmt: skip
    headers = dos_header + b"PE\0\0" + coff_header + optional_header + section_header
    return headers.ljust(file_alignment, b"\0") + text.ljust(file_alignment, b"\0")


def hello_elf() -> bytes:
    """A 129-byte 64-bit Linux program (ELF) that only calls exit(0)."""
    base = 0x400000
    header_size, program_header_size = 64, 56
    code = b"\xb8\x3c\x00\x00\x00\x31\xff\x0f\x05"  # mov eax, 60 (exit); xor edi, edi; syscall
    total = header_size + program_header_size + len(code)
    ident = b"\x7fELF" + bytes([2, 1, 1, 0]) + bytes(8)  # 64-bit, little-endian, version 1
    header = ident + struct.pack(
        "<HHIQQQIHHHHHH",
        2,  # executable
        0x3E,  # x86-64
        1,
        base + header_size + program_header_size,  # entry point: the code
        header_size,  # program headers follow this header
        0,  # no section headers
        0,
        header_size,
        program_header_size,
        1,
        0,
        0,
        0,
    )
    load = struct.pack("<IIQQQQQQ", 1, 5, 0, base, base, total, total, 0x1000)  # load all, R+X
    return header + load + code


def macho_header() -> bytes:
    """A 64-bit macOS Mach-O header (x86-64 dylib) with no load commands: header only."""
    return struct.pack("<IiiIIIII", 0xFEEDFACF, 0x01000007, 3, 6, 0, 0, 0, 0)


# --- archives ----------------------------------------------------------------------------


def zip_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    """A ZIP built in memory with stored (uncompressed) entries and fixed metadata.

    `create_system` and `external_attr` are set explicitly because zipfile otherwise
    records the current OS, which would make Windows and Linux runs differ.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=ZIP_DATE_TIME)
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return buffer.getvalue()


def plain_zip(rng: random.Random) -> bytes:
    return zip_bytes(
        [
            ("readme.txt", GREETING + b". A plain ZIP archive for tests.\n"),
            ("data.bin", rng.randbytes(256)),
        ]
    )


XML_HEAD = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
CONTENT_TYPES_NS = b"http://schemas.openxmlformats.org/package/2006/content-types"
RELS_NS = b"http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_DOC_REL = (
    b"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
)


def content_types(overrides: list[tuple[bytes, bytes]]) -> bytes:
    parts = b"".join(
        b'<Override PartName="' + part + b'" ContentType="' + kind + b'"/>'
        for part, kind in overrides
    )
    return (
        XML_HEAD + b'<Types xmlns="' + CONTENT_TYPES_NS + b'">'
        b'<Default Extension="rels" '
        b'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        b'<Default Extension="xml" ContentType="application/xml"/>' + parts + b"</Types>"
    )


def relationships(rel_type: bytes, target: bytes) -> bytes:
    return (
        XML_HEAD + b'<Relationships xmlns="' + RELS_NS + b'">'
        b'<Relationship Id="rId1" Type="' + rel_type + b'" Target="' + target + b'"/>'
        b"</Relationships>"
    )


def docx() -> bytes:
    """The smallest Word document: content types, one relationship, one paragraph."""
    main = b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
    document = (
        XML_HEAD + b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
        b'2006/main"><w:body><w:p><w:r><w:t>' + GREETING + b"</w:t></w:r></w:p></w:body>"
        b"</w:document>"
    )
    return zip_bytes(
        [
            ("[Content_Types].xml", content_types([(b"/word/document.xml", main)])),
            ("_rels/.rels", relationships(OFFICE_DOC_REL, b"word/document.xml")),
            ("word/document.xml", document),
        ]
    )


def xlsx() -> bytes:
    """The smallest spreadsheet: a workbook with one sheet holding one text cell."""
    sheet_ns = b"http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = b"http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    workbook = (
        XML_HEAD + b'<workbook xmlns="' + sheet_ns + b'" xmlns:r="' + rel_ns + b'">'
        b'<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    sheet = (
        XML_HEAD + b'<worksheet xmlns="' + sheet_ns + b'"><sheetData><row r="1">'
        b'<c r="A1" t="inlineStr"><is><t>' + GREETING + b"</t></is></c></row></sheetData>"
        b"</worksheet>"
    )
    office = b"application/vnd.openxmlformats-officedocument.spreadsheetml"
    return zip_bytes(
        [
            (
                "[Content_Types].xml",
                content_types(
                    [
                        (b"/xl/workbook.xml", office + b".sheet.main+xml"),
                        (b"/xl/worksheets/sheet1.xml", office + b".worksheet+xml"),
                    ]
                ),
            ),
            ("_rels/.rels", relationships(OFFICE_DOC_REL, b"xl/workbook.xml")),
            ("xl/workbook.xml", workbook),
            (
                "xl/_rels/workbook.xml.rels",
                relationships(rel_ns + b"/worksheet", b"worksheets/sheet1.xml"),
            ),
            ("xl/worksheets/sheet1.xml", sheet),
        ]
    )


def seven_zip() -> bytes:
    """An empty 7z archive: the 32-byte signature header pointing at no next header."""
    next_header = struct.pack("<QQI", 0, 0, zlib.crc32(b""))  # offset, size, CRC of nothing
    return (
        b"7z\xbc\xaf\x27\x1c"
        + b"\x00\x04"
        + struct.pack("<I", zlib.crc32(next_header))
        + (next_header)
    )


def rar5() -> bytes:
    """An empty RAR5 archive: signature, main archive header, end-of-archive header.

    Each header is CRC32, then its size and fields as variable-length integers (all < 128
    here, so one byte each).
    """

    def block(fields: bytes) -> bytes:
        body = bytes([len(fields)]) + fields
        return struct.pack("<I", zlib.crc32(body)) + body

    main = block(bytes([1, 0, 0]))  # type 1 (main), no header flags, no archive flags
    end = block(bytes([5, 0, 0]))  # type 5 (end of archive)
    return b"Rar!\x1a\x07\x01\x00" + main + end


def rar4() -> bytes:
    """An empty RAR4 archive: marker block, archive header, end-of-archive block.

    RAR4 headers start with the low 16 bits of the CRC32 of everything after the CRC field.
    """

    def block(head_type: int, flags: int, extra: bytes) -> bytes:
        rest = struct.pack("<BHH", head_type, flags, 7 + len(extra)) + extra
        return struct.pack("<H", zlib.crc32(rest) & 0xFFFF) + rest

    archive_header = block(0x73, 0, bytes(6))  # two reserved fields
    end = block(0x7B, 0x4000, b"")
    return b"Rar!\x1a\x07\x00" + archive_header + end


# --- documents ---------------------------------------------------------------------------


def tiny_pdf() -> bytes:
    """A complete one-page PDF saying "Hello from LinkGuard", with a correct xref table."""
    stream = b"BT /F1 18 Tf 20 40 Td (" + GREETING + b") Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 100] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += str(number).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref_at = len(pdf)
    pdf += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n0000000000 65535 f \n"
    pdf += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    pdf += b"trailer\n<< /Size " + str(len(objects) + 1).encode() + b" /Root 1 0 R >>\n"
    return pdf + b"startxref\n" + str(xref_at).encode() + b"\n%%EOF\n"


def ole_container() -> bytes:
    """An empty OLE compound file (the container of .msi, .doc and .xls), version 3.

    512-byte header, then sector 0 = the allocation table (FAT), sector 1 = the directory
    holding only the root entry.
    """
    free, end_of_chain, fat_sector, no_stream = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFF
    header = struct.pack(
        "<8s16sHHHHH6xIIIIIIIII109I",
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
        bytes(16),  # class id
        0x003E, 0x0003,  # minor, major version
        0xFFFE,  # byte order: little-endian
        9, 6,  # 512-byte sectors, 64-byte mini sectors
        0,  # directory sectors (always 0 in version 3)
        1,  # FAT sectors
        1,  # first directory sector
        0,  # transaction signature
        4096,  # mini stream cutoff
        end_of_chain, 0,  # no mini FAT
        end_of_chain, 0,  # no extra FAT index sectors
        0, *([free] * 108),  # the FAT lives in sector 0
    )  # fmt: skip
    fat = struct.pack("<128I", fat_sector, end_of_chain, *([free] * 126))
    name = "Root Entry\0".encode("utf-16-le")
    root = struct.pack(
        "<64sHBBIII16sIQQIQ",
        name, len(name), 5, 1,  # name, its length, type root storage, colour black
        no_stream, no_stream, no_stream, bytes(16), 0, 0, 0,
        end_of_chain, 0,  # empty mini stream
    )  # fmt: skip
    unused = struct.pack(
        "<64sHBBIII16sIQQIQ", bytes(64), 0, 0, 0, no_stream, no_stream, no_stream, bytes(16),
        0, 0, 0, 0, 0,
    )  # fmt: skip
    return header + fat + root + unused * 3


# --- media and images --------------------------------------------------------------------


def png(rng: random.Random, size: int = 16) -> bytes:
    """A 16x16 colour PNG with seeded random pixels. Level-0 zlib keeps the bytes the same
    on every zlib version (stored blocks, no compression choices)."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = struct.pack(">I", zlib.crc32(kind + data))
        return struct.pack(">I", len(data)) + kind + data + crc

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    rows = b"".join(b"\x00" + rng.randbytes(size * 3) for _ in range(size))  # filter 0 per row
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows, 0))
        + chunk(b"IEND", b"")
    )


def jpeg() -> bytes:
    """An 8x8 mid-grey baseline JPEG built by hand.

    Each Huffman table holds one 1-bit code: DC "difference 0" and AC "end of block". So the
    whole image is the bits `00`, padded with ones to the byte 0x3F.
    """

    def segment(marker: int, data: bytes) -> bytes:
        return struct.pack(">BBH", 0xFF, marker, len(data) + 2) + data

    one_code = bytes([1] + [0] * 15) + b"\x00"  # one code of length 1, for symbol 0
    return (
        b"\xff\xd8"  # start of image
        + segment(0xE0, b"JFIF\0\x01\x01\x00\x00\x01\x00\x01\x00\x00")
        + segment(0xDB, b"\x00" + bytes([1] * 64))  # quantisation table 0: all ones
        + segment(0xC0, b"\x08\x00\x08\x00\x08\x01\x01\x11\x00")  # 8x8, 1 component
        + segment(0xC4, b"\x00" + one_code)  # DC table 0
        + segment(0xC4, b"\x10" + one_code)  # AC table 0
        + segment(0xDA, b"\x01\x01\x00\x00\x3f\x00")  # start of scan
        + b"\x3f"
        + b"\xff\xd9"  # end of image
    )


def mp4(rng: random.Random) -> bytes:
    """MP4-shaped bytes: an `ftyp` box, then a small `mdat` box of seeded random data.
    Detectors only need `ftyp` at offset 4; there is no `moov`, so players won't play it."""
    ftyp = struct.pack(">I4s4sI8s", 24, b"ftyp", b"isom", 0x200, b"isomiso2")
    media = rng.randbytes(2048)
    return ftyp + struct.pack(">I4s", 8 + len(media), b"mdat") + media


# MPEG-1 Layer III, 128 kbit/s, 44.1 kHz, no padding: 417-byte frames of silence.
MP3_FRAME = b"\xff\xfb\x90\x00" + bytes(413)


def mp3_frames(count: int = 3) -> bytes:
    """Bare MP3 frames with no ID3 tag (detected from two valid frame headers in a row)."""
    return MP3_FRAME * count


def mp3_with_id3() -> bytes:
    """An ID3v2.3 tag holding a title frame, then three MP3 frames."""
    title = b"\x00" + b"LinkGuard sample"  # encoding byte 0 = Latin-1
    frame = b"TIT2" + struct.pack(">IH", len(title), 0) + title
    tag = b"ID3\x03\x00\x00" + bytes([0, 0, 0, len(frame)]) + frame  # size < 128: one byte
    return tag + mp3_frames()


# --- scripts (text) and the HTML error page ----------------------------------------------

SCRIPTS = {
    "sample.js": b'// LinkGuard sample script: harmless.\nconsole.log("Hello from LinkGuard");\n',
    "sample.ps1": b'# LinkGuard sample script: harmless.\nWrite-Output "Hello from LinkGuard"\n',
    "sample.bat": (
        b"@echo off\r\nrem LinkGuard sample script: harmless.\r\necho Hello from LinkGuard\r\n"
    ),
}

HTML_ERROR_PAGE = (
    b'<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
    b"<title>404 Not Found</title></head>\n<body><h1>Not Found</h1>\n"
    b"<p>The requested file was not found on this server.</p></body></html>\n"
)


# --- putting it together -----------------------------------------------------------------


def genuine_samples() -> dict[str, bytes]:
    """One genuine file per spec §7 format (both RAR versions, both MP3 detection paths)."""
    rng = random.Random(SEED)
    return {
        "sample.exe": hello_pe(),
        "sample.elf": hello_elf(),
        "sample.dylib": macho_header(),
        "sample.zip": plain_zip(rng),
        "sample.7z": seven_zip(),
        "sample.rar": rar5(),
        "sample-v4.rar": rar4(),
        "sample.pdf": tiny_pdf(),
        "sample.docx": docx(),
        "sample.xlsx": xlsx(),
        "sample.doc": ole_container(),
        **SCRIPTS,
        "sample.mp4": mp4(rng),
        "sample.mp3": mp3_with_id3(),
        "sample-frames.mp3": mp3_frames(),
        "sample.png": png(rng),
        "sample.jpg": jpeg(),
    }


def disguised_samples(genuine: dict[str, bytes]) -> dict[str, bytes]:
    """The disguises from spec §11: a real file's bytes under a name that lies about it."""
    return {
        "movie.mp4": genuine["sample.exe"],
        "invoice.pdf.exe": genuine["sample.exe"],
        "photo.jpg": genuine["sample.png"],
        "report.docx": genuine["sample.zip"],
        "file.pdf": HTML_ERROR_PAGE,
    }


def write_samples(out_dir: Path) -> dict[str, str]:
    """Write every sample under `out_dir` plus SHA256SUMS; return {relative path: sha256}.

    Names are our own constants, never remote data. Existing files are overwritten.
    """
    genuine = genuine_samples()
    files = dict(genuine)
    files.update({f"disguised/{name}": data for name, data in disguised_samples(genuine).items()})
    (out_dir / "disguised").mkdir(parents=True, exist_ok=True)
    digests = {}
    for name, data in files.items():
        (out_dir / name).write_bytes(data)
        digests[name] = hashlib.sha256(data).hexdigest()
    manifest = "".join(f"{digest}  {name}\n" for name, digest in sorted(digests.items()))
    # Bytes, not text: write_text would turn \n into \r\n on Windows and change the hash.
    (out_dir / "SHA256SUMS").write_bytes(manifest.encode())
    return digests


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate LinkGuard's harmless sample files.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output folder")
    out_dir = parser.parse_args().out
    digests = write_samples(out_dir)
    print(f"Wrote {len(digests)} samples to {out_dir} (hashes in SHA256SUMS)")


if __name__ == "__main__":
    main()
