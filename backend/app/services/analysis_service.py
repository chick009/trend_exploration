from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.db.repository import (
    create_analysis_run,
    update_analysis_run,
)
from app.graph.graph import build_graph
from app.models.schemas import AnalysisRunRequest


class AnalysisService:
    def __init__(self) -> None:
        self.graph = build_graph()

    def create_run(self, request: AnalysisRunRequest) -> str:
        run_id = str(uuid4())
        create_analysis_run(run_id, request)
        return run_id

    def run(self, run_id: str, request: AnalysisRunRequest) -> None:
        update_analysis_run(run_id, status="running", execution_trace=["[Analysis] started"])
        initial_state = {
            "market": request.market,
            "category": request.category,
            "recency_days": request.recency_days,
            "analysis_mode": request.analysis_mode,
            "user_query": (request.query or "").strip(),
            "trend_candidates": [],
            "messages": [],
            "guardrail_flags": [],
            "execution_log": [],
            "retry_count": 0,
            "source_batch_ids": [],
            "watch_list_only": False,
        }
        config = {"configurable": {"thread_id": run_id}}
        last_trace: list[str] = ["[Analysis] started"]
        source_batch_ids: list[str] = []
        try:
            final_state = None
            for state_update in self.graph.stream(initial_state, config=config, stream_mode="values"):
                final_state = state_update
                last_trace = ["[Analysis] started", *list(state_update.get("execution_log") or [])]
                update_analysis_run(run_id, status="running", execution_trace=last_trace)
            if final_state is None:
                final_state = self.graph.invoke(initial_state, config=config)
            source_batch_ids = list(final_state.get("source_batch_ids") or [])
            report = final_state.get("formatted_report")
            if not report or "report_id" not in report:
                report = {
                    "report_id": str(uuid4()),
                    "generated_at": datetime.utcnow().isoformat(),
                    "market": request.market,
                    "category": request.category,
                    "recency_days": request.recency_days,
                    "trends": [],
                    "watch_list": [],
                    "regional_divergences": final_state.get("formatted_report", {}).get("regional_divergences", []),
                    "execution_trace": final_state.get("execution_log", []),
                    "guardrail_flags": final_state.get("guardrail_flags", ["No report generated."]),
                }
            update_analysis_run(
                run_id,
                status="completed",
                execution_trace=report.get("execution_trace", []),
                report=report,
                source_batch_ids=source_batch_ids,
            )
        except Exception as exc:
            failure_trace = [*last_trace, f"[Analysis] failed: {exc!s}"]
            update_analysis_run(
                run_id,
                status="failed",
                execution_trace=failure_trace,
                error_message=str(exc),
                source_batch_ids=source_batch_ids,
            )
            raise
