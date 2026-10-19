"""The checked-in OpenAPI document must match the app (task T0.4).

If this fails, run `make openapi` and commit backend/openapi.json and web/src/api/types.ts.
"""

import json
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

OPENAPI_FILE = Path(__file__).resolve().parents[2] / "openapi.json"


def current_document(tmp_path: Path) -> dict[str, object]:
    return create_app(Settings(database_url=f"sqlite:///{tmp_path / 'o.db'}")).openapi()


def test_checked_in_openapi_is_up_to_date(tmp_path: Path) -> None:
    on_disk = json.loads(OPENAPI_FILE.read_text(encoding="utf-8"))
    assert on_disk == current_document(tmp_path), "run `make openapi` and commit the result"


def test_only_the_two_contract_endpoints_exist(tmp_path: Path) -> None:
    paths = current_document(tmp_path)["paths"]
    assert isinstance(paths, dict)
    assert {path: sorted(ops) for path, ops in paths.items()} == {
        "/api/scans": ["post"],
        "/api/scans/{scan_id}": ["get"],
    }


def test_no_422_is_documented(tmp_path: Path) -> None:
    assert '"422"' not in json.dumps(current_document(tmp_path))
