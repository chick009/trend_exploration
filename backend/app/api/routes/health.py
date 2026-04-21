from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from app.db.repository import get_latest_source_health
from app.models.schemas import SourceHealth, SourcesHealthResponse

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/sources/health", response_model=SourcesHealthResponse)
def get_sources_health() -> SourcesHealthResponse:
    rows = []
    for row in get_latest_source_health():
        rows.append(
            SourceHealth(
                source=row["source"],
                latest_batch_id=row["latest_batch_id"],
                latest_completed_at=(
                    datetime.fromisoformat(row["latest_completed_at"]) if row["latest_completed_at"] else None
                ),
                row_count=row["row_count"] or 0,
            )
        )
    return SourcesHealthResponse(sources=rows)
