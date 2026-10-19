"""Load and validate the reason-code registry (spec §8).

The registry is the one place where codes, weights and wording live, so the scorer has no
magic numbers and every message the user sees can be reviewed in one file. Validation runs
at startup and in tests: a broken registry stops the app instead of producing odd verdicts.
"""

import re
import string
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.contract.models import Severity

DEFAULT_PATH = Path(__file__).with_name("reason_codes.yaml")

# Phase 1 prefixes. Phase 2+ adds REP_ BROWSER_ PE_ ARCH_ DOC_ PDF_ SCRIPT_ TOR_ MSI_ YARA_.
ALLOWED_PREFIXES = (
    "URL_",
    "SSRF_",
    "REDIR_",
    "FETCH_",
    "LINK_",
    "TYPE_",
    "EXT_",
    "SCAN_",
    "ANALYSIS_",
)
ALLOWED_GROUPS = (
    "type",
    "header",
    "redirect",
    "url",
    "link",
    "detect",
    "scope",
    "fetch",
    "analysis",
)
CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

Outcome = Literal["risk", "info", "unable", "rejected", "unsupported"]


class RegistryError(ValueError):
    """The registry file is invalid; the message names the code and the problem."""


class ReasonCodeSpec(BaseModel):
    """One registry entry. Unknown keys are refused so typos cannot slip through."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group: str
    weight: int = Field(ge=0)
    severity: Severity
    outcome: Outcome
    hard_min_verdict: Literal["SUSPICIOUS", "UNSAFE"] | None = None
    evidence: tuple[str, ...] = ()
    message: str
    headline: str


@dataclass(frozen=True)
class Registry:
    rules_version: str
    codes: dict[str, ReasonCodeSpec]


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate keys (plain YAML silently keeps the last one)."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    keys = [loader.construct_object(key_node) for key_node, _ in node.value]
    duplicates = sorted({str(k) for k in keys if keys.count(k) > 1})
    if duplicates:
        raise RegistryError(f"duplicate keys in registry: {', '.join(duplicates)}")
    return loader.construct_mapping(node)


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def template_fields(template: str) -> set[str]:
    """Names used as {placeholders} in a template. Raises ValueError on broken braces."""
    return {field for _, field, _, _ in string.Formatter().parse(template) if field is not None}


def _check_entry(code: str, entry: ReasonCodeSpec) -> None:
    if not CODE_PATTERN.match(code):
        raise RegistryError(f"{code}: codes are UPPER_SNAKE_CASE with a prefix")
    if not code.startswith(ALLOWED_PREFIXES):
        raise RegistryError(f"{code}: prefix not allowed in Phase 1")
    if entry.group not in ALLOWED_GROUPS:
        raise RegistryError(f"{code}: unknown group {entry.group!r}")
    if entry.outcome == "risk" and entry.weight == 0:
        raise RegistryError(f"{code}: a risk code needs a weight above 0")
    if entry.outcome != "risk" and entry.weight != 0:
        raise RegistryError(f"{code}: only risk codes may add to the score")
    if entry.hard_min_verdict and entry.outcome != "risk":
        raise RegistryError(f"{code}: only risk codes may set hard_min_verdict")
    for name, template in (("message", entry.message), ("headline", entry.headline)):
        try:
            used = template_fields(template)
        except ValueError as exc:
            raise RegistryError(f"{code}: {name} template is malformed ({exc})") from exc
        undeclared = used - set(entry.evidence)
        if undeclared:
            raise RegistryError(f"{code}: {name} uses undeclared evidence {sorted(undeclared)}")
        # Prove it renders with exactly the declared keys.
        template.format(**{key: "x" for key in entry.evidence})


def parse_registry(text: str) -> Registry:
    """Parse and validate registry YAML text."""
    try:
        data = yaml.load(
            text, Loader=_UniqueKeyLoader
        )  # a SafeLoader subclass: never constructs Python objects
    except yaml.YAMLError as exc:
        raise RegistryError(f"registry is not valid YAML: {exc}") from exc
    if not isinstance(data, dict) or set(data) != {"rules_version", "codes"}:
        raise RegistryError("registry needs exactly two top-level keys: rules_version, codes")
    version = data["rules_version"]
    if not isinstance(version, str) or not VERSION_PATTERN.match(version):
        raise RegistryError('rules_version must be a quoted version like "1.0.0"')
    if not isinstance(data["codes"], dict) or not data["codes"]:
        raise RegistryError("codes must be a non-empty mapping")

    codes: dict[str, ReasonCodeSpec] = {}
    for code, raw in data["codes"].items():
        try:
            entry = ReasonCodeSpec.model_validate(raw)
        except ValidationError as exc:
            raise RegistryError(f"{code}: {exc}") from exc
        _check_entry(str(code), entry)
        codes[str(code)] = entry
    return Registry(rules_version=version, codes=codes)


def load_registry(path: Path = DEFAULT_PATH) -> Registry:
    return parse_registry(path.read_text(encoding="utf-8"))


@lru_cache
def get_registry() -> Registry:
    """The validated registry for this process, loaded once."""
    return load_registry()
