from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.db.repository import get_table_rows, get_table_schema, list_database_tables
from app.models.schemas import (
    DbColumnSchema,
    DbTableInfo,
    DbTableRowsResponse,
    DbTableSchemaResponse,
    DbTablesResponse,
)

router = APIRouter(prefix="/db", tags=["db-browser"])


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@router.get("/tables", response_model=DbTablesResponse)
def list_tables() -> DbTablesResponse:
    rows = list_database_tables()
    return DbTablesResponse(
        tables=[
            DbTableInfo(
                name=row["name"],
                description=row["description"],
                row_count=row["row_count"],
                last_updated=_parse_datetime(row["last_updated"]),
            )
            for row in rows
        ]
    )


@router.get("/tables/{table_name}/schema", response_model=DbTableSchemaResponse)
def describe_table(table_name: str) -> DbTableSchemaResponse:
    try:
        columns = get_table_schema(table_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return DbTableSchemaResponse(
        table=table_name,
        columns=[DbColumnSchema.model_validate(column) for column in columns],
    )


@router.get("/tables/{table_name}/rows", response_model=DbTableRowsResponse)
def list_table_rows(
    table_name: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, description="Global search text or a column-scoped search when column is set."),
    column: str | None = Query(None, description="Optional whitelisted column for column-scoped search."),
    order_by: str | None = Query(None, description="Whitelisted sort column."),
    order_dir: str = Query("desc", pattern="^(?i)(asc|desc)$"),
) -> DbTableRowsResponse:
    try:
        rows, total = get_table_rows(
            table_name,
            limit=limit,
            offset=offset,
            search=search,
            column=column,
            order_by=order_by,
            order_dir=order_dir,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    columns = list(rows[0].keys()) if rows else [column["name"] for column in get_table_schema(table_name)]
    return DbTableRowsResponse(
        table=table_name,
        columns=columns,
        rows=rows,
        total=total,
        limit=limit,
        offset=offset,
    )
