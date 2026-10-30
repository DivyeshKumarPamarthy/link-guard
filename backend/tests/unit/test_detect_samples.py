"""The detector over the generated samples (task T2.6).

`test_detect_type.py` checks hand-written byte fixtures; this file checks the real sample
files the demo serves, so the demo and the detector can never drift apart. Skipped when
`samples/` is missing: run `make samples` first.
"""

from pathlib import Path

import pytest

from app.contract.models import DetectionConfidence, Family
from app.engine.detect.signatures import detect_type

SAMPLES = Path(__file__).resolve().parents[3] / "samples"

pytestmark = pytest.mark.skipif(
    not SAMPLES.is_dir(), reason="samples/ is missing: run `make samples` to generate it"
)

CERTAIN = DetectionConfidence.certain
PROBABLE = DetectionConfidence.probable
UNCONFIRMED = DetectionConfidence.unconfirmed

# Path inside samples/ -> (detected type, family, confidence). One row per generated file.
EXPECTED = {
    "sample.exe": ("pe-executable", Family.executable, CERTAIN),
    "sample.elf": ("elf-executable", Family.executable, CERTAIN),
    "sample.dylib": ("macho-executable", Family.executable, CERTAIN),
    # Head-only listing finds no subtype marker in a plain ZIP (spec §7: "subtype unconfirmed").
    "sample.zip": ("zip", Family.archive, UNCONFIRMED),
    "sample.7z": ("7z", Family.archive, CERTAIN),
    "sample.rar": ("rar5", Family.archive, CERTAIN),
    "sample-v4.rar": ("rar4", Family.archive, CERTAIN),
    "sample.pdf": ("pdf", Family.document, CERTAIN),
    "sample.docx": ("docx", Family.document, CERTAIN),
    "sample.xlsx": ("xlsx", Family.document, CERTAIN),
    "sample.doc": ("ole", Family.document, CERTAIN),
    # Scripts have no magic bytes: the detector can only say "text" (spec §7).
    "sample.js": ("text", Family.text, PROBABLE),
    "sample.ps1": ("text", Family.text, PROBABLE),
    "sample.bat": ("text", Family.text, PROBABLE),
    "sample.mp4": ("mp4", Family.media, CERTAIN),
    "sample.mp3": ("mp3", Family.media, CERTAIN),
    "sample-frames.mp3": ("mp3", Family.media, CERTAIN),  # two valid frame headers in a row
    "sample.png": ("png", Family.image, CERTAIN),
    "sample.jpg": ("jpeg", Family.image, CERTAIN),
    # Disguises: the detector reports what the bytes are, whatever the name says.
    "disguised/movie.mp4": ("pe-executable", Family.executable, CERTAIN),
    "disguised/invoice.pdf.exe": ("pe-executable", Family.executable, CERTAIN),
    "disguised/photo.jpg": ("png", Family.image, CERTAIN),
    "disguised/report.docx": ("zip", Family.archive, UNCONFIRMED),
    # An HTML page is text to the detector; calling it a web page is the router's job (T3.1).
    "disguised/file.pdf": ("text", Family.text, PROBABLE),
}


def read_sample(name: str) -> bytes:
    path = SAMPLES / name
    # Plan M7: a missing sample must fail clearly (antivirus may have removed it).
    assert path.is_file(), f"Sample {name!r} is missing from samples/. Run `make samples`."
    return path.read_bytes()


@pytest.mark.parametrize("name, expected", EXPECTED.items(), ids=list(EXPECTED))
def test_sample_is_detected_as_what_it_really_is(
    name: str, expected: tuple[str, Family, DetectionConfidence]
) -> None:
    detection = detect_type(read_sample(name))
    assert (detection.type, detection.family, detection.confidence) == expected


def test_every_generated_sample_has_an_expectation() -> None:
    """A sample added to make_samples.py without a row here would go untested."""
    manifest = (SAMPLES / "SHA256SUMS").read_text().splitlines()
    generated = {line.split("  ", 1)[1] for line in manifest}
    assert generated == set(EXPECTED)


def test_disguised_program_highlights_mz_in_the_hex_strip() -> None:
    """The demo's key moment: the claimed-vs-actual panel highlights the first two bytes."""
    detection = detect_type(read_sample("disguised/movie.mp4"))
    assert detection.signature is not None
    assert (detection.signature.offset, detection.signature.length) == (0, 2)
    assert detection.label == "Windows executable"


def test_mp4_signature_sits_at_offset_four() -> None:
    detection = detect_type(read_sample("sample.mp4"))
    assert detection.signature is not None
    assert (detection.signature.offset, detection.signature.length) == (4, 4)
