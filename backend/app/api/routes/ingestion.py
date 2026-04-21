from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.db.repository import get_ingestion_run, json_loads, list_ingestion_runs
from app.models.schemas import IngestionRunRequest, PaginatedRunsResponse, RunStatusResponse
from app.services.ingestion.ingestion_service import IngestionService

router = APIRouter(prefix="/ingestion_runs", tags=["ingestion"])
service = IngestionService()


@router.post("", response_model=RunStatusResponse)
def create_ingestion_run(request: IngestionRunRequest, background_tasks: BackgroundTasks) -> RunStatusResponse:
    run_id, batch_id = service.create_run(request)
    background_tasks.add_task(service.run, run_id, batch_id, request)
    return RunStatusResponse(id=run_id, status="queued", source_batch_id=batch_id)


@router.get("", response_model=PaginatedRunsResponse)
def get_ingestion_runs(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)) -> PaginatedRunsResponse:
    rows, total = list_ingestion_runs(limit=limit, offset=offset)
    items = [
        RunStatusResponse(
            id=row["id"],
            status=row["status"],
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            error_message=row["error_message"],
            stats=json_loads(row["stats_json"], {}),
            execution_trace=[],
            guardrail_flags=json_loads(row["guardrail_flags"], []),
            source_batch_id=row["source_batch_id"],
        )
        for row in rows
    ]
    return PaginatedRunsResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{run_id}", response_model=RunStatusResponse)
def get_ingestion_status(run_id: str) -> RunStatusResponse:
    row = get_ingestion_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Ingestion run not found")
    return RunStatusResponse(
        id=row["id"],
        status=row["status"],
        started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        error_message=row["error_message"],
        stats=json_loads(row["stats_json"], {}),
        execution_trace=[],
        guardrail_flags=json_loads(row["guardrail_flags"], []),
        source_batch_id=row["source_batch_id"],
    )
