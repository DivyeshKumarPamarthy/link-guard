"""Golden tests for the scorer (spec §9): `<case>.input.json` -> `<case>.expected.json`.

Each input lists raw findings (code + evidence) and the fetcher's read facts. An optional
`weight_overrides` changes a registry weight for that case only, so the exact thresholds
29 and 59 can be tested even though no combination of the real starter weights reaches them.
The expected file is written by hand; never regenerate it from the scorer's output.
"""

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.engine.fetcher.redirects import Finding
from app.engine.scoring.scope import ReadFacts
from app.engine.scoring.scorer import ScoreOutcome, Thresholds, score_scan
from app.registry.loader import Registry, get_registry

GOLDEN_DIR = Path(__file__).parent
CASES = sorted(p.name.removesuffix(".input.json") for p in GOLDEN_DIR.glob("*.input.json"))


def registry_with(overrides: dict[str, int]) -> Registry:
    real = get_registry()
    codes = dict(real.codes)
    for code, weight in overrides.items():
        codes[code] = codes[code].model_copy(update={"weight": weight})
    return Registry(rules_version=real.rules_version, codes=codes)


def summary(outcome: ScoreOutcome) -> dict[str, object]:
    return {
        "status": outcome.status,
        "verdict": outcome.verdict,
        "display_verdict": outcome.display_verdict,
        "score": outcome.score,
        "confidence": outcome.confidence,
        "scope_mode": outcome.scope.mode,
        "scope_label": outcome.scope.label,
        "headline": outcome.headline,
        "reason_codes": [reason.code for reason in outcome.reasons],
    }


def test_there_are_golden_cases() -> None:
    assert len(CASES) >= 15


@pytest.mark.parametrize("case", CASES)
def test_golden_case(case: str) -> None:
    data = json.loads((GOLDEN_DIR / f"{case}.input.json").read_text(encoding="utf-8"))
    expected = json.loads((GOLDEN_DIR / f"{case}.expected.json").read_text(encoding="utf-8"))
    findings = [Finding(f["code"], f.get("evidence", {})) for f in data["findings"]]
    outcome = score_scan(
        findings,
        ReadFacts(**data.get("read", {})),
        registry_with(data.get("weight_overrides", {})),
        Thresholds.from_settings(Settings()),
    )
    assert json.loads(json.dumps(summary(outcome))) == expected
