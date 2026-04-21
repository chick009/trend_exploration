from __future__ import annotations

import pytest

from app.db.connection import connection_scope
from app.db.repository import safe_sql_execute


def test_safe_sql_execute_allows_select(test_database) -> None:
    with connection_scope() as connection:
        rows = safe_sql_execute(connection, "SELECT 1 AS value")
    assert rows == [{"value": 1}]


def test_safe_sql_execute_blocks_updates(test_database) -> None:
    with connection_scope() as connection:
        with pytest.raises(ValueError):
            safe_sql_execute(connection, "UPDATE social_posts SET liked_count = 1")
