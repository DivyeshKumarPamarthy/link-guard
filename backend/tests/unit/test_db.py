"""Tests for the scans table (task T0.6)."""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import inspect, text

from app.db.models import ScanRow, make_engine, make_session_factory

EXPECTED_COLUMNS = {
    "id",
    "state",
    "status",
    "verdict",
    "display_verdict",
    "input_url",
    "final_url",
    "result_json",
    "schema_version",
    "engine_version",
    "rules_version",
    "created_at",
    "completed_at",
}


def test_create_all_makes_the_scans_table(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'lg.db'}")
    columns = {c["name"] for c in inspect(engine).get_columns("scans")}
    assert columns == EXPECTED_COLUMNS


def test_wal_mode_is_on(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'lg.db'}")
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"


def test_write_read_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "lg.db"
    created = datetime(2026, 10, 16, 10, 15, tzinfo=UTC)
    row = ScanRow(
        id="9f3c2d1e-4b5a-4c6d-8e7f-0a1b2c3d4e5f",
        state="done",
        status="completed",
        verdict="UNSAFE",
        display_verdict="UNSAFE",
        input_url="https://short.example/abc?token=secret",
        final_url="https://files.example/movie.mp4",
        result_json='{"schema_version": "1.0"}',
        schema_version="1.0",
        engine_version="1.0.0",
        rules_version="1.0.0",
        created_at=created,
        completed_at=created,
    )
    with make_session_factory(make_engine(f"sqlite:///{db_path}"))() as session:
        session.add(row)
        session.commit()

    # A fresh engine proves the data really reached the file, not just a cache.
    with make_session_factory(make_engine(f"sqlite:///{db_path}"))() as session:
        loaded = session.get(ScanRow, "9f3c2d1e-4b5a-4c6d-8e7f-0a1b2c3d4e5f")
        assert loaded is not None
        assert loaded.state == "done"
        assert loaded.verdict == "UNSAFE"
        assert loaded.input_url == "https://short.example/abc?token=secret"
        assert loaded.result_json == '{"schema_version": "1.0"}'
        # SQLite drops the timezone; the value itself must survive.
        assert loaded.created_at.replace(tzinfo=UTC) == created


def test_queued_row_allows_empty_outcome(tmp_path: Path) -> None:
    factory = make_session_factory(make_engine(f"sqlite:///{tmp_path / 'lg.db'}"))
    with factory() as session:
        session.add(
            ScanRow(
                id="0b7e6a52-1d2c-4f3e-9a8b-7c6d5e4f3a2b",
                state="queued",
                status=None,
                verdict=None,
                display_verdict=None,
                input_url="https://x.example/a",
                final_url=None,
                result_json=None,
                schema_version="1.0",
                engine_version="1.0.0",
                rules_version="1.0.0",
                created_at=datetime.now(UTC),
                completed_at=None,
            )
        )
        session.commit()
        assert session.get(ScanRow, "0b7e6a52-1d2c-4f3e-9a8b-7c6d5e4f3a2b") is not None


def test_create_all_is_safe_to_run_twice(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'lg.db'}"
    make_engine(url)
    make_engine(url)  # startup runs this every time; must not fail on an existing table
