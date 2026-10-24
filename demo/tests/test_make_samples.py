"""Tests for the samples generator (spec §11, task T2.6).

The generator must be reproducible: the same bytes on every run and every machine, so a
test result never depends on who generated the samples or when.
"""

import hashlib
import io
import random
import zipfile
import zlib
from pathlib import Path

import make_samples

# sha256 of the SHA256SUMS manifest. It changes only when the generator changes on purpose:
# then run `make samples` and paste the new value from `shasum -a 256 samples/SHA256SUMS`.
EXPECTED_MANIFEST_SHA256 = "76ba69f871811307cbf26294e36753ef4390c190703cc076a6a475c53b278351"

DISGUISED = {
    "movie.mp4": "sample.exe",
    "invoice.pdf.exe": "sample.exe",
    "photo.jpg": "sample.png",
    "report.docx": "sample.zip",
}


def test_two_runs_write_identical_files(tmp_path: Path) -> None:
    first = make_samples.write_samples(tmp_path / "one")
    second = make_samples.write_samples(tmp_path / "two")
    assert first == second
    for name in first:
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()


def test_manifest_lists_every_file_with_its_hash(tmp_path: Path) -> None:
    digests = make_samples.write_samples(tmp_path)
    lines = (tmp_path / "SHA256SUMS").read_text().splitlines()
    assert lines == [f"{digest}  {name}" for name, digest in sorted(digests.items())]
    for name, digest in digests.items():
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == digest


def test_output_is_hash_stable_across_machines(tmp_path: Path) -> None:
    make_samples.write_samples(tmp_path)
    manifest = (tmp_path / "SHA256SUMS").read_bytes()
    assert hashlib.sha256(manifest).hexdigest() == EXPECTED_MANIFEST_SHA256, (
        "The samples changed. If you changed make_samples.py on purpose, update "
        "EXPECTED_MANIFEST_SHA256; otherwise something made the output depend on the machine."
    )


def test_every_spec_format_has_a_genuine_sample(tmp_path: Path) -> None:
    names = set(make_samples.write_samples(tmp_path))
    for expected in [
        "sample.exe",
        "sample.elf",
        "sample.dylib",
        "sample.zip",
        "sample.7z",
        "sample.rar",
        "sample-v4.rar",
        "sample.pdf",
        "sample.docx",
        "sample.xlsx",
        "sample.doc",
        "sample.js",
        "sample.ps1",
        "sample.bat",
        "sample.mp4",
        "sample.mp3",
        "sample-frames.mp3",
        "sample.png",
        "sample.jpg",
    ]:
        assert expected in names


def test_disguised_variants_reuse_the_real_bytes(tmp_path: Path) -> None:
    make_samples.write_samples(tmp_path)
    for disguise, real in DISGUISED.items():
        assert (tmp_path / "disguised" / disguise).read_bytes() == (tmp_path / real).read_bytes()


def test_disguised_pdf_is_an_html_error_page(tmp_path: Path) -> None:
    make_samples.write_samples(tmp_path)
    body = (tmp_path / "disguised" / "file.pdf").read_bytes()
    assert body.lower().startswith(b"<!doctype html")
    assert b"%PDF-" not in body


def test_hello_pe_has_a_valid_pe_header(tmp_path: Path) -> None:
    pe = make_samples.hello_pe()
    assert pe[:2] == b"MZ"
    e_lfanew = int.from_bytes(pe[0x3C:0x40], "little")
    assert pe[e_lfanew : e_lfanew + 4] == b"PE\0\0"
    assert b"Hello from LinkGuard" in pe


def test_samples_are_small(tmp_path: Path) -> None:
    make_samples.write_samples(tmp_path)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert path.stat().st_size < 64 * 1024, path.name


def test_zip_based_samples_are_valid_archives() -> None:
    for data, must_contain in [
        (make_samples.docx(), "word/document.xml"),
        (make_samples.xlsx(), "xl/workbook.xml"),
        (make_samples.plain_zip(random.Random(1)), "readme.txt"),
    ]:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            assert archive.testzip() is None  # every stored entry's CRC matches
            assert must_contain in archive.namelist()


def test_rar5_header_crcs_match() -> None:
    data = make_samples.rar5()[8:]  # after the signature
    for _ in range(2):  # main header, end-of-archive header
        size = data[4]
        assert int.from_bytes(data[:4], "little") == zlib.crc32(data[4 : 5 + size])
        data = data[5 + size :]
    assert data == b""


def test_pdf_xref_offsets_point_at_objects() -> None:
    pdf = make_samples.tiny_pdf()
    xref_at = int(pdf.rsplit(b"startxref\n", 1)[1].split(b"\n", 1)[0])
    assert pdf[xref_at:].startswith(b"xref")
    entries = pdf[xref_at:].split(b"\n")[3:8]  # objects 1..5
    for number, entry in enumerate(entries, start=1):
        offset = int(entry[:10])
        assert pdf[offset:].startswith(f"{number} 0 obj".encode())
