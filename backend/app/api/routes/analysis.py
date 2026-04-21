from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.db.repository import get_analysis_run, get_latest_trend_report, json_loads, list_analysis_runs
from app.models.schemas import AnalysisRunRequest, PaginatedRunsResponse, RunStatusResponse, TrendReport
from app.services.analysis_service import AnalysisService

router = APIRouter(tags=["analysis"])
service = AnalysisService()


@router.post("/analysis_runs", response_model=RunStatusResponse)
def create_analysis_run(request: AnalysisRunRequest, background_tasks: BackgroundTasks) -> RunStatusResponse:
    run_id = service.create_run(request)
    background_tasks.add_task(service.run, run_id, request)
    return RunStatusResponse(id=run_id, status="queued")


@router.get("/analysis_runs", response_model=PaginatedRunsResponse)
def get_analysis_runs(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)) -> PaginatedRunsResponse:
    rows, total = list_analysis_runs(limit=limit, offset=offset)
    items = [
        RunStatusResponse(
            id=row["id"],
            status=row["status"],
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            error_message=row["error_message"],
            stats={"source_batch_ids": json_loads(row["source_batch_ids"], [])},
            execution_trace=json_loads(row["execution_trace"], []),
        )
        for row in rows
    ]
    return PaginatedRunsResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/analysis_runs/{run_id}", response_model=RunStatusResponse)
def get_analysis_status(run_id: str) -> RunStatusResponse:
    row = get_analysis_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    report_payload = json_loads(row["report_json"], None) if row["report_json"] else None
    return RunStatusResponse(
        id=row["id"],
        status=row["status"],
        started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        error_message=row["error_message"],
        execution_trace=json_loads(row["execution_trace"], []),
        stats={"source_batch_ids": json_loads(row["source_batch_ids"], [])},
        report=TrendReport.model_validate(report_payload) if report_payload else None,
    )


@router.get("/trends/latest", response_model=TrendReport)
def get_latest_trends(
    market: str = Query(default="HK"),
    category: str = Query(default="skincare"),
) -> TrendReport:
    payload = get_latest_trend_report(market, category)
    if not payload:
        raise HTTPException(status_code=404, detail="No completed trend report found")
    return TrendReport.model_validate(payload)
