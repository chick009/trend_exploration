from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.core.config import get_settings


def _configure_connection(connection: sqlite3.Connection) -> sqlite3.Connection:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def get_connection(database_path: Path | None = None) -> sqlite3.Connection:
    settings = get_settings()
    path = database_path or settings.database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return _configure_connection(sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES))


@contextmanager
def connection_scope(database_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    connection = get_connection(database_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
