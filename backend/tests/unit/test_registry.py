"""Tests for the reason-code registry (task T0.5, spec §8)."""

import re
from pathlib import Path

import pytest

from app.contract.models import ErrorCode
from app.registry.loader import RegistryError, load_registry, parse_registry

APP_DIR = Path(__file__).resolve().parents[2] / "app"

# Spec §8 table: code -> (group, weight, severity, outcome). Rejected/unsupported rows are
# "–" in the spec; decision D26 stores them as weight 0, severity info.
SPEC_TABLE = {
    "TYPE_MISMATCH_EXEC": ("type", 70, "high", "risk"),
    "EXT_DOUBLE": ("type", 40, "medium", "risk"),
    "EXT_SPOOFED_NAME": ("type", 40, "medium", "risk"),
    "TYPE_POLYGLOT": ("type", 30, "medium", "risk"),
    "TYPE_MISMATCH_TEXT": ("type", 20, "low", "risk"),
    "TYPE_MISMATCH_OTHER": ("type", 15, "low", "risk"),
    "EXT_RISKY": ("type", 15, "low", "risk"),
    "TYPE_CONTENT_TYPE_MISMATCH": ("header", 10, "low", "risk"),
    "REDIR_DOWNGRADE": ("redirect", 10, "low", "risk"),
    "REDIR_LONG_CHAIN": ("redirect", 10, "low", "risk"),
    "REDIR_CROSS_DOMAIN": ("redirect", 0, "info", "info"),
    "URL_HOMOGRAPH": ("url", 0, "info", "info"),
    "LINK_CLOUD_SHARE_PAGE": ("link", 0, "info", "info"),
    "TYPE_EXEC_PROBABLE": ("detect", 0, "info", "info"),
    "TYPE_UNKNOWN": ("detect", 0, "info", "info"),
    "SCAN_PARTIAL": ("scope", 0, "info", "info"),
    "FETCH_UNEXPECTED_ENCODING": ("fetch", 0, "info", "info"),
    "LINK_IS_WEB_PAGE": ("link", 0, "info", "unable"),
    "FETCH_TIMEOUT": ("fetch", 0, "info", "unable"),
    "FETCH_INTERRUPTED": ("fetch", 0, "info", "unable"),
    "FETCH_EMPTY": ("fetch", 0, "info", "unable"),
    "FETCH_AUTH_REQUIRED": ("fetch", 0, "info", "unable"),
    "FETCH_RATE_LIMITED": ("fetch", 0, "info", "unable"),
    "FETCH_HTTP_ERROR": ("fetch", 0, "info", "unable"),
    "FETCH_TLS_ERROR": ("fetch", 0, "info", "unable"),
    "FETCH_DNS_ERROR": ("fetch", 0, "info", "unable"),
    "REDIR_LOOP": ("redirect", 0, "info", "unable"),
    "REDIR_TOO_MANY": ("redirect", 0, "info", "unable"),
    "ANALYSIS_ERROR": ("analysis", 0, "info", "unable"),
    "URL_PRIVATE_ADDRESS": ("url", 0, "info", "rejected"),
    "URL_USERINFO": ("url", 0, "info", "rejected"),
    "URL_PORT_BLOCKED": ("url", 0, "info", "rejected"),
    "URL_SCHEME_UNSUPPORTED": ("url", 0, "info", "rejected"),
    "URL_INVALID": ("url", 0, "info", "rejected"),  # D38
    "SSRF_BLOCKED_AT_HOP": ("redirect", 0, "info", "rejected"),
    "REDIR_BAD_TARGET": ("redirect", 0, "info", "rejected"),
    "LINK_TYPE_UNSUPPORTED": ("link", 0, "info", "unsupported"),
}


def test_real_registry_loads() -> None:
    registry = load_registry()
    assert registry.rules_version == "1.0.0"


def test_registry_matches_spec_table_exactly() -> None:
    codes = load_registry().codes
    assert set(codes) == set(SPEC_TABLE)
    for code, (group, weight, severity, outcome) in SPEC_TABLE.items():
        entry = codes[code]
        assert (entry.group, entry.weight, entry.severity, entry.outcome) == (
            group,
            weight,
            severity,
            outcome,
        ), code


def test_only_disguised_executable_has_a_hard_rule() -> None:
    hard = {c: e.hard_min_verdict for c, e in load_registry().codes.items() if e.hard_min_verdict}
    assert hard == {"TYPE_MISMATCH_EXEC": "UNSAFE"}


def test_spec_example_message_renders_from_template() -> None:
    entry = load_registry().codes["TYPE_MISMATCH_EXEC"]
    evidence = {
        "claimed_ext": "mp4",
        "detected": "pe-executable",
        "detected_label": "Windows executable",
    }
    assert entry.message.format(**evidence) == (
        "The file is named .mp4 but its content is a Windows executable."
    )
    assert entry.headline.format(**evidence) == (
        "Blocked: file named .mp4 is actually a Windows executable"
    )


# --- validator: each rule rejects a broken entry -----------------------------------------

VALID_ENTRY = """
    group: type
    weight: 10
    severity: low
    outcome: risk
    evidence: [ext]
    message: "Ends in .{ext}."
    headline: "Ends in .{ext}"
"""


def registry_text(
    code: str = "EXT_TEST", entry: str = VALID_ENTRY, version: str = '"1.0.0"'
) -> str:
    return f"rules_version: {version}\ncodes:\n  {code}:{entry}"


def test_minimal_valid_registry_parses() -> None:
    registry = parse_registry(registry_text())
    assert registry.codes["EXT_TEST"].evidence == ("ext",)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (registry_text(code="BAD_PREFIX"), "prefix not allowed"),
        (registry_text(code="EXT_lower"), "UPPER_SNAKE_CASE"),
        (registry_text(code="EXT"), "UPPER_SNAKE_CASE"),
        (registry_text(entry=VALID_ENTRY.replace("group: type", "group: misc")), "unknown group"),
        (
            registry_text(entry=VALID_ENTRY.replace("weight: 10", "weight: -1")),
            "greater than or equal",
        ),
        (
            registry_text(entry=VALID_ENTRY.replace("weight: 10", "weight: 0")),
            "needs a weight above 0",
        ),
        (
            registry_text(entry=VALID_ENTRY.replace("outcome: risk", "outcome: unable")),
            "only risk codes may add",
        ),
        (registry_text(entry=VALID_ENTRY.replace("severity: low", "severity: huge")), "severity"),
        (registry_text(entry=VALID_ENTRY.replace("outcome: risk", "outcome: maybe")), "outcome"),
        (
            registry_text(entry=VALID_ENTRY.replace("Ends in .{ext}.", "Ends in .{extension}.")),
            "undeclared evidence",
        ),
        (
            registry_text(entry=VALID_ENTRY.replace('"Ends in .{ext}"', '"Ends in .{ext"')),
            "malformed",
        ),
        (registry_text(entry=VALID_ENTRY + "    colour: red\n"), "Extra inputs"),
        (
            registry_text(entry=VALID_ENTRY.replace('    headline: "Ends in .{ext}"\n', "")),
            "headline",
        ),
        (registry_text(version="1.0"), "rules_version"),  # unquoted 1.0 is a YAML float
        (registry_text(version='"v1"'), "rules_version"),
        ("codes: {}\n", "two top-level keys"),
        ('rules_version: "1.0.0"\ncodes: {}\n', "non-empty"),
        ("rules_version: [\n", "not valid YAML"),
    ],
)
def test_validator_rejects(text: str, message: str) -> None:
    with pytest.raises(RegistryError, match=message):
        parse_registry(text)


def test_hard_rule_only_on_risk_codes() -> None:
    entry = VALID_ENTRY.replace("weight: 10", "weight: 0").replace("outcome: risk", "outcome: info")
    entry += "    hard_min_verdict: UNSAFE\n"
    with pytest.raises(RegistryError, match="hard_min_verdict"):
        parse_registry(registry_text(entry=entry))


def test_duplicate_codes_are_refused() -> None:
    text = registry_text() + f"  EXT_TEST:{VALID_ENTRY}"
    with pytest.raises(RegistryError, match="duplicate keys"):
        parse_registry(text)


# --- every code used in backend code must be in the registry ------------------------------

PREFIXES = "URL|SSRF|REDIR|FETCH|LINK|TYPE|EXT|SCAN|ANALYSIS"
# Quoted strings only, so Python names like TYPE_CHECKING are not mistaken for codes.
QUOTED_CODE = re.compile(rf"""["']((?:{PREFIXES})_[A-Z0-9_]+)["']""")


def codes_in_source(text: str) -> set[str]:
    return set(QUOTED_CODE.findall(text))


def test_code_finder_finds_quoted_codes_only() -> None:
    sample = (
        'reason("TYPE_MISMATCH_EXEC")\n'
        "if TYPE_CHECKING: x = 'FETCH_NEW_THING'\n"
        'LG_PROFILE = "dev"'
    )
    assert codes_in_source(sample) == {"TYPE_MISMATCH_EXEC", "FETCH_NEW_THING"}


def test_every_code_used_in_backend_code_is_registered() -> None:
    registered = set(load_registry().codes)
    api_error_codes = {code.value for code in ErrorCode}  # HTTP error codes, not reason codes
    missing: dict[str, set[str]] = {}
    for path in APP_DIR.rglob("*.py"):
        used = codes_in_source(path.read_text(encoding="utf-8")) - registered - api_error_codes
        if used:
            missing[str(path.relative_to(APP_DIR))] = used
    assert missing == {}, f"codes used in code but missing from reason_codes.yaml: {missing}"
