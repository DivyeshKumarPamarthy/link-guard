"""No source or doc file may contain invisible, bidi or control characters.

Such characters make code display differently from how it runs ("Trojan Source",
CVE-2021-42574). Write them as escapes instead, e.g. backslash-u-202e in a string.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCANNED_DIRS = [
    "backend/app",
    "backend/tests",
    "backend/scripts",
    "web/src",
    "docs",
    "demo",
    ".github",
]
SCANNED_FILES = ["README.md", "CLAUDE.md", "Makefile", ".env.example", "web/index.html"]
TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".css",
    ".html",
    ".toml",
}


def is_hidden(ch: str) -> bool:
    code = ord(ch)
    return (
        (code < 0x20 and ch not in "\n\t\r")
        or 0x7F <= code <= 0x9F
        or 0x200B <= code <= 0x200F  # zero-width, LRM/RLM
        or 0x202A <= code <= 0x202E  # bidi embeddings and overrides
        or 0x2066 <= code <= 0x2069  # bidi isolates
        or code in (0x2028, 0x2029, 0xFEFF)
    )


def text_files() -> list[Path]:
    files = [REPO / name for name in SCANNED_FILES if (REPO / name).exists()]
    for directory in SCANNED_DIRS:
        for path in (REPO / directory).rglob("*"):
            if path.is_file() and path.suffix in TEXT_SUFFIXES and "node_modules" not in path.parts:
                files.append(path)
    return files


def test_scanner_detects_a_hidden_character() -> None:
    assert is_hidden(chr(0x202E)) and is_hidden(chr(0x1B)) and not is_hidden("é")


def test_no_hidden_characters_in_repository_text_files() -> None:
    found = {}
    for path in text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        hidden = sorted({f"U+{ord(ch):04X}" for ch in text if is_hidden(ch)})
        if hidden:
            found[str(path.relative_to(REPO))] = hidden
    assert found == {}, f"hidden characters found (write them as escapes): {found}"
