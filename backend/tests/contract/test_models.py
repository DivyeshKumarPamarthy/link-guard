"""Contract tests (task T0.4, spec §2 and §3).

The example JSON files are the spec's examples. If a model change breaks them,
the contract changed and docs/decisions.md must say so.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.contract.models import (
    ErrorBody,
    ScanAccepted,
    ScanRequest,
    ScanResult,
)

EXAMPLES = Path(__file__).parent / "examples"


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((EXAMPLES / f"{name}.json").read_text())
    return data


@pytest.mark.parametrize(
    "name", ["scan_result_unsafe", "scan_result_queued", "scan_result_rejected"]
)
def test_examples_validate(name: str) -> None:
    ScanResult.model_validate(load(name))


def test_spec_example_round_trips_unchanged() -> None:
    data = load("scan_result_unsafe")
    dumped = ScanResult.model_validate(data).model_dump(mode="json")
    assert dumped == data


def test_unknown_fields_are_tolerated() -> None:
    """Clients must ignore unknown fields so 1.x can add fields without breaking them."""
    data = load("scan_result_unsafe")
    data["added_in_1_1"] = {"anything": True}
    data["file"]["new_file_field"] = 1
    data["reasons"][0]["new_reason_field"] = "x"
    result = ScanResult.model_validate(data)
    assert "added_in_1_1" not in result.model_dump()


def test_unknown_reason_code_is_accepted() -> None:
    """Codes are open: a client renders an unknown code as a generic card."""
    data = load("scan_result_unsafe")
    data["reasons"][0]["code"] = "PE_SOMETHING_NEW"
    ScanResult.model_validate(data)


def test_request_ignores_unknown_fields_and_defaults_url() -> None:
    assert ScanRequest.model_validate({"url": "x", "client_hint": 1}).url == "x"
    assert ScanRequest.model_validate({}).url == ""


def test_scan_accepted_shape() -> None:
    body = ScanAccepted.model_validate(
        {"scan_id": "9f3c2d1e-4b5a-4c6d-8e7f-0a1b2c3d4e5f", "state": "queued", "poll_after_ms": 500}
    ).model_dump(mode="json")
    assert body == {
        "schema_version": "1.0",
        "scan_id": "9f3c2d1e-4b5a-4c6d-8e7f-0a1b2c3d4e5f",
        "state": "queued",
        "poll_after_ms": 500,
    }


def test_error_body_shape() -> None:
    body = ErrorBody.model_validate({"error": {"code": "URL_EMPTY", "message": "Paste a link."}})
    assert body.model_dump(mode="json") == {
        "schema_version": "1.0",
        "error": {"code": "URL_EMPTY", "message": "Paste a link."},
    }


def test_wrong_schema_version_is_refused() -> None:
    data = load("scan_result_unsafe")
    data["schema_version"] = "2.0"
    with pytest.raises(ValidationError):
        ScanResult.model_validate(data)


def test_negative_weight_is_refused() -> None:
    data = load("scan_result_unsafe")
    data["reasons"][0]["weight"] = -5
    with pytest.raises(ValidationError):
        ScanResult.model_validate(data)


@pytest.mark.parametrize("hex_value", ["4D5A", "4d5", "zz", "00" * 17])
def test_first_bytes_hex_must_be_lowercase_pairs_up_to_16_bytes(hex_value: str) -> None:
    data = load("scan_result_unsafe")
    data["file"]["first_bytes_hex"] = hex_value
    with pytest.raises(ValidationError):
        ScanResult.model_validate(data)


# --- outcome rules (spec §3) ------------------------------------------------------------


def expect_invalid(data: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        ScanResult.model_validate(data)


def test_outcome_fields_must_be_null_while_queued() -> None:
    data = load("scan_result_queued")
    data["verdict"] = "SAFE"
    expect_invalid(data, "must be null until done")


def test_done_scan_needs_status() -> None:
    data = load("scan_result_unsafe")
    data["status"] = None
    expect_invalid(data, "needs status")


def test_rejected_scan_has_no_verdict() -> None:
    data = load("scan_result_rejected")
    data["verdict"] = "UNABLE_TO_VERIFY"
    expect_invalid(data, "only when status is completed")


def test_rejected_scan_must_display_rejected() -> None:
    data = load("scan_result_rejected")
    data["display_verdict"] = "UNSUPPORTED"
    expect_invalid(data, "must display")


def test_completed_scan_needs_verdict_and_confidence() -> None:
    data = load("scan_result_unsafe")
    data["confidence"] = None
    expect_invalid(data, "needs verdict and confidence")


def test_completed_scan_cannot_display_rejected() -> None:
    data = load("scan_result_unsafe")
    data["display_verdict"] = "REJECTED"
    expect_invalid(data, "cannot display")


def safe_result() -> dict[str, Any]:
    data = load("scan_result_unsafe")
    data.update(verdict="SAFE", display_verdict="SAFE", score=0, reasons=[])
    return data


def test_display_safe_is_valid_for_full_scope_high_confidence() -> None:
    ScanResult.model_validate(safe_result())


def test_partial_scan_can_never_display_plain_safe() -> None:
    data = safe_result()
    data["scope"]["mode"] = "partial"
    expect_invalid(data, "display SAFE needs")


def test_low_confidence_can_never_display_plain_safe() -> None:
    data = safe_result()
    data["confidence"] = "low"
    expect_invalid(data, "display SAFE needs")


def test_partial_safe_displays_no_issues_in_checked_part() -> None:
    data = safe_result()
    data["scope"]["mode"] = "partial"
    data["confidence"] = "medium"
    data["display_verdict"] = "NO_ISSUES_IN_CHECKED_PART"
    ScanResult.model_validate(data)
