"""Write the API's OpenAPI document to backend/openapi.json (run by `make openapi`).

The web app's TypeScript types are generated from this file, and CI fails if either file is
out of date, so the contract cannot drift between backend and web app.
"""

import json
import sys
import tempfile
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

OUTPUT = Path(__file__).resolve().parents[1] / "openapi.json"


def main() -> None:
    # A throwaway database: exporting the schema must not create linkguard.db.
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Settings(database_url=f"sqlite:///{tmp}/openapi.db"))
        document = app.openapi()
    OUTPUT.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"wrote {OUTPUT.relative_to(Path.cwd()) if OUTPUT.is_relative_to(Path.cwd()) else OUTPUT}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
