"""The `scans` table and how to open the database (task T0.6).

SQLite is enough for a single-user localhost tool. The full ScanResult is stored as JSON in
`result_json`; the other columns copy the fields worth reading without parsing that JSON.
WAL mode lets the API read while a background scan writes. `create_all` makes the table on
startup, with no migrations tool (decision D14): if the table changes in Phase 1, delete the
local .db file.
"""

from datetime import datetime

from sqlalchemy import DateTime, Engine, String, Text, create_engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry


class Base(DeclarativeBase):
    pass


class ScanRow(Base):
    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUIDv4 text
    state: Mapped[str] = mapped_column(String(16))
    status: Mapped[str | None] = mapped_column(String(16))
    verdict: Mapped[str | None] = mapped_column(String(32))
    display_verdict: Mapped[str | None] = mapped_column(String(32))
    input_url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text)
    schema_version: Mapped[str] = mapped_column(String(16))
    engine_version: Mapped[str] = mapped_column(String(32))
    rules_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def _enable_wal(dbapi_connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def make_engine(database_url: str) -> Engine:
    """Create the engine, switch on WAL for every connection, and create missing tables."""
    engine = create_engine(
        database_url,
        # The API's threads and the scan background task share the engine.
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _enable_wal)
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker:  # type: ignore[type-arg]
    # expire_on_commit=False: rows stay readable after the short transaction ends.
    return sessionmaker(engine, expire_on_commit=False)
