from __future__ import annotations

import sys
import traceback
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.db.repository import (
    create_analysis_run,
    get_analysis_run,
    json_loads,
    update_analysis_run,
)
from app.graph.graph import build_graph
from app.graph.nodes.intent_parser import build_intent_state_update
from app.graph.nodes.sql_dispatcher import load_sql_results
from app.models.schemas import AnalysisRunRequest
from app.models.schemas import RunStatusResponse, ToolInvocation, TrendReport


def build_run_status_response(row: dict[str, Any]) -> RunStatusResponse:
    report_payload = json_loads(row.get("report_json"), None) if row.get("report_json") else None
    report = TrendReport.model_validate(report_payload) if report_payload else None
    raw_tool_invocations = json_loads(row.get("tool_invocations_json"), []) or []
    tool_invocations = [ToolInvocation.model_validate(entry) for entry in raw_tool_invocations]
    return RunStatusResponse(
        id=row["id"],
        status=row["status"],
        started_at=datetime.fromisoformat(row["started_at"]) if row.get("started_at") else None,
        completed_at=datetime.fromisoformat(row["completed_at"]) if row.get("completed_at") else None,
        error_message=row.get("error_message"),
        execution_trace=json_loads(row.get("execution_trace"), []),
        tool_invocations=tool_invocations,
        stats={"source_batch_ids": json_loads(row.get("source_batch_ids"), [])},
        guardrail_flags=(report.guardrail_flags if report else []),
        report=report,
    )


class AnalysisService:
    def __init__(self) -> None:
        self.graph = build_graph()

    def create_run(self, request: AnalysisRunRequest) -> str:
        run_id = str(uuid4())
        create_analysis_run(run_id, request)
        return run_id

    def get_run_status(self, run_id: str) -> RunStatusResponse:
        row = get_analysis_run(run_id)
        if not row:
            raise LookupError(f"Analysis run not found: {run_id}")
        return build_run_status_response(row)

    def _base_initial_state(self, request: AnalysisRunRequest) -> dict[str, Any]:
        return {
            "market": request.market,
            "category": request.category,
            "recency_days": request.recency_days,
            "analysis_mode": request.analysis_mode,
            "user_query": (request.query or "").strip(),
            "trend_candidates": [],
            "messages": [],
            "guardrail_flags": [],
            "execution_log": [],
            "tool_invocations": [],
            "retry_count": 0,
            "source_batch_ids": [],
            "watch_list_only": False,
        }

    def _report_fallback(self, request: AnalysisRunRequest, final_state: dict[str, Any]) -> dict[str, Any]:
        return {
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

    def iter_run_events(self, run_id: str, request: AnalysisRunRequest):
        update_analysis_run(
            run_id,
            status="running",
            execution_trace=["[Analysis] started"],
            tool_invocations=[],
        )
        config = {"configurable": {"thread_id": run_id}}
        last_trace: list[str] = ["[Analysis] started"]
        source_batch_ids: list[str] = []
        tool_invocations: list[dict[str, Any]] = []
        yield "run.updated", self.get_run_status(run_id)
        try:
            initial_state = self._base_initial_state(request)
            intent_update = build_intent_state_update(initial_state)
            query_intent = dict(intent_update["query_intent"])
            intent_log = list(intent_update.get("execution_log") or [])
            tool_invocations.extend(intent_update.get("tool_invocations") or [])
            last_trace = ["[Analysis] started", *intent_log]
            update_analysis_run(
                run_id,
                status="running",
                execution_trace=last_trace,
                tool_invocations=tool_invocations,
            )
            yield "run.updated", self.get_run_status(run_id)

            sql_results, source_batch_ids, query_plan, sql_tool_invocations = load_sql_results(query_intent)
            tool_invocations.extend(sql_tool_invocations)
            backend_line = (
                "[BackendData] "
                f"plan={list(query_plan)} social={len(sql_results['social'])} "
                f"search={len(sql_results['search'])} sales={len(sql_results['sales'])}"
            )
            initial_state = {
                **initial_state,
                **intent_update,
                "sql_results": sql_results,
                "source_batch_ids": source_batch_ids,
                "execution_log": [*intent_log, backend_line],
                "tool_invocations": list(tool_invocations),
            }
            last_trace = ["[Analysis] started", *initial_state["execution_log"]]
            update_analysis_run(
                run_id,
                status="running",
                execution_trace=last_trace,
                source_batch_ids=source_batch_ids,
                tool_invocations=tool_invocations,
            )
            yield "run.updated", self.get_run_status(run_id)

            final_state = None
            for state_update in self.graph.stream(initial_state, config=config, stream_mode="values"):
                final_state = state_update
                last_trace = ["[Analysis] started", *list(state_update.get("execution_log") or [])]
                tool_invocations = list(state_update.get("tool_invocations") or tool_invocations)
                update_analysis_run(
                    run_id,
                    status="running",
                    execution_trace=last_trace,
                    source_batch_ids=source_batch_ids,
                    tool_invocations=tool_invocations,
                )
                yield "run.updated", self.get_run_status(run_id)
            if final_state is None:
                final_state = self.graph.invoke(initial_state, config=config)
            source_batch_ids = list(final_state.get("source_batch_ids") or [])
            tool_invocations = list(final_state.get("tool_invocations") or tool_invocations)
            report = final_state.get("formatted_report")
            if not report or "report_id" not in report:
                report = self._report_fallback(request, final_state)
            update_analysis_run(
                run_id,
                status="completed",
                execution_trace=report.get("execution_trace", []),
                report=report,
                source_batch_ids=source_batch_ids,
                tool_invocations=tool_invocations,
            )
            yield "run.completed", self.get_run_status(run_id)
        except Exception as exc:
            print(
                f"[AnalysisService] run_id={run_id} exc_type={type(exc).__name__}",
                file=sys.stderr,
                flush=True,
            )
            traceback.print_exc(file=sys.stderr)
            failure_trace = [*last_trace, f"[Analysis] failed: {exc!s}"]
            update_analysis_run(
                run_id,
                status="failed",
                execution_trace=failure_trace,
                error_message=str(exc),
                source_batch_ids=source_batch_ids,
                tool_invocations=tool_invocations,
            )
            yield "run.failed", self.get_run_status(run_id)

    def run(self, run_id: str, request: AnalysisRunRequest) -> None:
        for event_type, event_payload in self.iter_run_events(run_id, request):
            if event_type == "run.failed":
                raise RuntimeError(event_payload.error_message or f"Analysis run failed: {run_id}")
