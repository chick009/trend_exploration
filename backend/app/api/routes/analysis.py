from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.db.repository import get_latest_trend_report, list_analysis_runs
from app.models.schemas import AnalysisRunRequest, PaginatedRunsResponse, RunStatusResponse, TrendReport
from app.services.analysis_service import AnalysisService, build_run_status_response

router = APIRouter(tags=["analysis"])
service = AnalysisService()


@router.post("/analysis_runs", response_model=RunStatusResponse)
def create_analysis_run(request: AnalysisRunRequest, background_tasks: BackgroundTasks) -> RunStatusResponse:
    run_id = service.create_run(request)
    background_tasks.add_task(service.run, run_id, request)
    return RunStatusResponse(id=run_id, status="queued")


@router.post("/analysis_runs/stream")
def stream_analysis_run(request: AnalysisRunRequest) -> StreamingResponse:
    run_id = service.create_run(request)

    def iter_stream():
        created_event = {
            "type": "run.created",
            "run": service.get_run_status(run_id).model_dump(mode="json"),
        }
        yield json.dumps(created_event) + "\n"
        for event_type, run_status in service.iter_run_events(run_id, request):
            yield json.dumps({"type": event_type, "run": run_status.model_dump(mode="json")}) + "\n"

    return StreamingResponse(iter_stream(), media_type="application/x-ndjson")


@router.get("/analysis_runs", response_model=PaginatedRunsResponse)
def get_analysis_runs(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)) -> PaginatedRunsResponse:
    rows, total = list_analysis_runs(limit=limit, offset=offset)
    items = [build_run_status_response(row) for row in rows]
    return PaginatedRunsResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/analysis_runs/{run_id}", response_model=RunStatusResponse)
def get_analysis_status(run_id: str) -> RunStatusResponse:
    try:
        return service.get_run_status(run_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Analysis run not found")


@router.get("/trends/latest", response_model=TrendReport)
def get_latest_trends(
    market: str = Query(default="HK"),
    category: str = Query(default="skincare"),
) -> TrendReport:
    payload = get_latest_trend_report(market, category)
    if not payload:
        raise HTTPException(status_code=404, detail="No completed trend report found")
    return TrendReport.model_validate(payload)
