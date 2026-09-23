"""SQLite connection lifecycle, schema setup and shared exceptions."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class DatabaseError(RuntimeError):
    """Raised when import or persistence cannot preserve the data contract."""


class RecordNotFoundError(DatabaseError):
    """Raised when a requested persisted API resource does not exist."""


@contextmanager
def connect(database_path: str | Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(Path(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(database_path: str | Path) -> Path:
    """Create or update an empty SQLite database from ``schema.sql``."""

    destination = Path(database_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with connect(destination) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(schema)
    return destination


def _query(
    database_path: str | Path,
    query: str,
    parameters: Iterable[Any] = (),
) -> list[dict[str, Any]]:
    try:
        with connect(database_path) as connection:
            return [dict(row) for row in connection.execute(query, tuple(parameters))]
    except sqlite3.Error as error:
        raise DatabaseError(f"Database query failed: {error}") from error
