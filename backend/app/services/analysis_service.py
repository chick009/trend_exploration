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


def _sql_results_summary(sql_results: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"row_counts": {}, "sample_terms": {}}
    for signal_name, rows in sql_results.items():
        summary["row_counts"][signal_name] = len(rows)
        terms: list[str] = []
        for row in rows:
            term = row.get("canonical_term") or row.get("keyword") or row.get("brand")
            if term and term not in terms:
                terms.append(str(term))
            if len(terms) >= 5:
                break
        summary["sample_terms"][signal_name] = terms
    return summary


def _sample_prior_snapshot(prior_snapshot: dict[str, dict[str, Any]], limit: int = 20) -> dict[str, dict[str, Any]]:
    return dict(list(prior_snapshot.items())[:limit])


def _sample_terms(items: list[dict[str, Any]], *, key: str = "canonical_term", limit: int = 10) -> list[str]:
    terms: list[str] = []
    for item in items:
        value = item.get(key) or item.get("term")
        if value and str(value) not in terms:
            terms.append(str(value))
        if len(terms) >= limit:
            break
    return terms


def _sample_records(items: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    return list(items[:limit])


def _confirmed_trends_from_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [trend for trend in report.get("trends", []) if not trend.get("watch_flag")]


def _gate_route_from_state(state_update: dict[str, Any]) -> str:
    synthesized_trends = list(state_update.get("synthesized_trends") or [])
    confirmed_count = sum(1 for trend in synthesized_trends if trend.get("status") == "confirmed")
    if confirmed_count == 0:
        return "formatter (no confirmed trends)"
    if confirmed_count < 3 or state_update.get("watch_list_only"):
        return "formatter (low_signal)"
    return "formatter"


def _build_node_outputs(
    current: dict[str, Any],
    *,
    initial_state: dict[str, Any] | None = None,
    intent_update: dict[str, Any] | None = None,
    query_plan: list[str] | None = None,
    sql_results: dict[str, list[dict[str, Any]]] | None = None,
    source_batch_ids: list[str] | None = None,
    state_update: dict[str, Any] | None = None,
) -> dict[str, Any]:
    node_outputs = dict(current)
    base_state = initial_state or {}
    if intent_update is not None:
        node_outputs["intent_parser"] = {
            "received_state": {
                "market": base_state.get("market"),
                "category": base_state.get("category"),
                "recency_days": base_state.get("recency_days"),
                "analysis_mode": base_state.get("analysis_mode"),
                "user_query": base_state.get("user_query"),
            },
            "emitted_state": {
                "query_intent": intent_update.get("query_intent"),
                "query_params": intent_update.get("query_params"),
            },
            "raw_output": {
                "query_intent": intent_update.get("query_intent"),
                "query_params": intent_update.get("query_params"),
            },
        }
    if sql_results is not None and query_plan is not None:
        sql_summary = _sql_results_summary(sql_results)
        node_outputs["backend_preload"] = {
            "received_state": {
                "query_intent": intent_update.get("query_intent") if intent_update is not None else base_state.get("query_intent"),
                "query_params": intent_update.get("query_params") if intent_update is not None else base_state.get("query_params"),
            },
            "emitted_state": {
                "query_plan": list(query_plan),
                "source_batch_ids": list(source_batch_ids or []),
                **sql_summary,
            },
            "raw_output": {
                "query_plan": list(query_plan),
                "source_batch_ids": list(source_batch_ids or []),
                **sql_summary,
            },
        }
    if state_update is None:
        return node_outputs

    prior_snapshot = state_update.get("prior_snapshot")
    if prior_snapshot is not None:
        node_outputs["memory_read"] = {
            "received_state": {
                "market": state_update.get("market"),
                "category": state_update.get("category"),
            },
            "emitted_state": {
                "prior_snapshot_count": len(prior_snapshot),
                "prior_snapshot": _sample_prior_snapshot(prior_snapshot),
            },
            "raw_output": {
                "prior_snapshot_count": len(prior_snapshot),
                "prior_snapshot": _sample_prior_snapshot(prior_snapshot),
            },
        }

    if state_update.get("trend_candidates") is not None:
        trend_candidates = list(state_update.get("trend_candidates") or [])
        node_outputs["trend_gen_agent"] = {
            "received_state": {
                "query_intent": state_update.get("query_intent"),
                "source_batch_ids": list(state_update.get("source_batch_ids") or []),
                "sql_results_summary": _sql_results_summary(state_update.get("sql_results") or {"social": [], "search": [], "sales": []}),
            },
            "emitted_state": {
                "candidate_count": len(trend_candidates),
                "candidate_terms": _sample_terms(trend_candidates),
                "regions": sorted({candidate.get("market") for candidate in trend_candidates if candidate.get("market")}),
            },
            "raw_output": {
                "candidate_count": len(trend_candidates),
                "regions": sorted({candidate.get("market") for candidate in trend_candidates if candidate.get("market")}),
                "trend_candidates": _sample_records(trend_candidates),
            },
        }

    if state_update.get("synthesized_trends") is not None:
        synthesized_trends = list(state_update.get("synthesized_trends") or [])
        confirmed_count = sum(1 for trend in synthesized_trends if trend.get("status") == "confirmed")
        watch_count = sum(1 for trend in synthesized_trends if trend.get("status") == "watch")
        node_outputs["evidence_synthesizer"] = {
            "received_state": {
                "prior_snapshot_count": len(state_update.get("prior_snapshot") or {}),
                "trend_candidate_count": len(state_update.get("trend_candidates") or []),
                "candidate_terms": _sample_terms(list(state_update.get("trend_candidates") or [])),
            },
            "emitted_state": {
                "confirmed_count": confirmed_count,
                "watch_count": watch_count,
                "watch_list_only": bool(state_update.get("watch_list_only")),
                "guardrail_flags": list(state_update.get("guardrail_flags") or []),
                "synthesized_terms": _sample_terms(synthesized_trends),
            },
            "raw_output": {
                "confirmed_count": confirmed_count,
                "watch_count": watch_count,
                "watch_list_only": bool(state_update.get("watch_list_only")),
                "guardrail_flags": list(state_update.get("guardrail_flags") or []),
                "synthesized_trends": _sample_records(synthesized_trends),
            },
        }
        node_outputs["confidence_gate"] = {
            "received_state": {
                "confirmed_count": confirmed_count,
                "watch_count": watch_count,
                "watch_list_only": bool(state_update.get("watch_list_only")),
            },
            "emitted_state": {
                "route": _gate_route_from_state(state_update),
            },
            "raw_output": {
                "route": _gate_route_from_state(state_update),
            },
        }

    report = state_update.get("formatted_report")
    if report is not None:
        confirmed_trends = _confirmed_trends_from_report(report)
        node_outputs["memory_write"] = {
            "received_state": {
                "report_id": report.get("report_id"),
                "confirmed_trend_count": len(confirmed_trends),
                "watch_list_count": len(report.get("watch_list", [])),
            },
            "emitted_state": {
                "persisted": bool(confirmed_trends),
                "reason": (
                    "No confirmed trends; trend_exploration intentionally left empty for this run."
                    if not confirmed_trends
                    else f"Persisted {len(confirmed_trends)} confirmed trend snapshots."
                ),
            },
            "raw_output": {
                "report_id": report.get("report_id"),
                "confirmed_trend_count": len(confirmed_trends),
                "watch_list_count": len(report.get("watch_list", [])),
                "persisted": bool(confirmed_trends),
                "reason": (
                    "No confirmed trends; trend_exploration intentionally left empty for this run."
                    if not confirmed_trends
                    else f"Persisted {len(confirmed_trends)} confirmed trend snapshots."
                ),
            },
        }
        node_outputs["formatter"] = {
            "received_state": {
                "synthesized_trend_count": len(state_update.get("synthesized_trends") or []),
                "confirmed_count": sum(
                    1 for trend in list(state_update.get("synthesized_trends") or []) if trend.get("status") == "confirmed"
                ),
                "watch_list_only": bool(state_update.get("watch_list_only")),
                "regional_divergences": list(report.get("regional_divergences", [])),
            },
            "emitted_state": {
                "report_id": report.get("report_id"),
                "trend_count": len(report.get("trends", [])),
                "watch_list_count": len(report.get("watch_list", [])),
                "trend_terms": _sample_terms(list(report.get("trends", [])), key="term"),
                "watch_terms": _sample_terms(list(report.get("watch_list", [])), key="term"),
            },
            "raw_output": {
                **report,
                "trends": _sample_records(list(report.get("trends", []))),
                "watch_list": _sample_records(list(report.get("watch_list", []))),
            },
        }

    return node_outputs


def build_run_status_response(row: dict[str, Any]) -> RunStatusResponse:
    report_payload = json_loads(row.get("report_json"), None) if row.get("report_json") else None
    report = TrendReport.model_validate(report_payload) if report_payload else None
    raw_tool_invocations = json_loads(row.get("tool_invocations_json"), []) or []
    normalized_tool_invocations = [
        {**entry, "messages": entry.get("messages") or []} if isinstance(entry, dict) else entry
        for entry in raw_tool_invocations
    ]
    tool_invocations = [ToolInvocation.model_validate(entry) for entry in normalized_tool_invocations]
    node_outputs = json_loads(row.get("node_outputs_json"), {}) or {}
    return RunStatusResponse(
        id=row["id"],
        status=row["status"],
        started_at=datetime.fromisoformat(row["started_at"]) if row.get("started_at") else None,
        completed_at=datetime.fromisoformat(row["completed_at"]) if row.get("completed_at") else None,
        error_message=row.get("error_message"),
        execution_trace=json_loads(row.get("execution_trace"), []),
        tool_invocations=tool_invocations,
        node_outputs=node_outputs,
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
        node_outputs: dict[str, Any] = {}
        update_analysis_run(
            run_id,
            status="running",
            execution_trace=["[Analysis] started"],
            tool_invocations=[],
            node_outputs=node_outputs,
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
            node_outputs = _build_node_outputs(node_outputs, initial_state=initial_state, intent_update=intent_update)
            last_trace = ["[Analysis] started", *intent_log]
            update_analysis_run(
                run_id,
                status="running",
                execution_trace=last_trace,
                tool_invocations=tool_invocations,
                node_outputs=node_outputs,
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
            node_outputs = _build_node_outputs(
                node_outputs,
                initial_state=initial_state,
                intent_update=intent_update,
                query_plan=query_plan,
                sql_results=sql_results,
                source_batch_ids=source_batch_ids,
            )
            last_trace = ["[Analysis] started", *initial_state["execution_log"]]
            update_analysis_run(
                run_id,
                status="running",
                execution_trace=last_trace,
                source_batch_ids=source_batch_ids,
                tool_invocations=tool_invocations,
                node_outputs=node_outputs,
            )
            yield "run.updated", self.get_run_status(run_id)

            final_state = None
            for state_update in self.graph.stream(initial_state, config=config, stream_mode="values"):
                final_state = state_update
                last_trace = ["[Analysis] started", *list(state_update.get("execution_log") or [])]
                tool_invocations = list(state_update.get("tool_invocations") or tool_invocations)
                node_outputs = _build_node_outputs(node_outputs, state_update=state_update)
                update_analysis_run(
                    run_id,
                    status="running",
                    execution_trace=last_trace,
                    source_batch_ids=source_batch_ids,
                    tool_invocations=tool_invocations,
                    node_outputs=node_outputs,
                )
                yield "run.updated", self.get_run_status(run_id)
            if final_state is None:
                final_state = self.graph.invoke(initial_state, config=config)
            source_batch_ids = list(final_state.get("source_batch_ids") or [])
            tool_invocations = list(final_state.get("tool_invocations") or tool_invocations)
            node_outputs = _build_node_outputs(node_outputs, state_update=final_state)
            report = final_state.get("formatted_report")
            if not report or "report_id" not in report:
                report = self._report_fallback(request, final_state)
                confirmed_trends = _confirmed_trends_from_report(report)
                node_outputs["formatter"] = {
                    "received_state": {
                        "synthesized_trend_count": len(final_state.get("synthesized_trends") or []),
                        "confirmed_count": sum(
                            1 for trend in list(final_state.get("synthesized_trends") or []) if trend.get("status") == "confirmed"
                        ),
                        "watch_list_only": bool(final_state.get("watch_list_only")),
                        "regional_divergences": list(report.get("regional_divergences", [])),
                    },
                    "emitted_state": {
                        "report_id": report.get("report_id"),
                        "trend_count": len(report.get("trends", [])),
                        "watch_list_count": len(report.get("watch_list", [])),
                        "trend_terms": _sample_terms(list(report.get("trends", [])), key="term"),
                        "watch_terms": _sample_terms(list(report.get("watch_list", [])), key="term"),
                    },
                    "raw_output": {
                        **report,
                        "trends": _sample_records(list(report.get("trends", []))),
                        "watch_list": _sample_records(list(report.get("watch_list", []))),
                    },
                }
                node_outputs["memory_write"] = {
                    "received_state": {
                        "report_id": report.get("report_id"),
                        "confirmed_trend_count": len(confirmed_trends),
                        "watch_list_count": len(report.get("watch_list", [])),
                    },
                    "emitted_state": {
                        "persisted": bool(confirmed_trends),
                        "reason": (
                            "No confirmed trends; trend_exploration intentionally left empty for this run."
                            if not confirmed_trends
                            else f"Persisted {len(confirmed_trends)} confirmed trend snapshots."
                        ),
                    },
                    "raw_output": {
                        "report_id": report.get("report_id"),
                        "confirmed_trend_count": len(confirmed_trends),
                        "watch_list_count": len(report.get("watch_list", [])),
                        "persisted": bool(confirmed_trends),
                        "reason": (
                            "No confirmed trends; trend_exploration intentionally left empty for this run."
                            if not confirmed_trends
                            else f"Persisted {len(confirmed_trends)} confirmed trend snapshots."
                        ),
                    },
                }
            report = {
                **report,
                "execution_trace": list(final_state.get("execution_log") or report.get("execution_trace") or []),
                "guardrail_flags": list(final_state.get("guardrail_flags") or report.get("guardrail_flags") or []),
            }
            update_analysis_run(
                run_id,
                status="completed",
                execution_trace=report.get("execution_trace", []),
                report=report,
                source_batch_ids=source_batch_ids,
                tool_invocations=tool_invocations,
                node_outputs=node_outputs,
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
                node_outputs=node_outputs,
            )
            yield "run.failed", self.get_run_status(run_id)

    def run(self, run_id: str, request: AnalysisRunRequest) -> None:
        for event_type, event_payload in self.iter_run_events(run_id, request):
            if event_type == "run.failed":
                raise RuntimeError(event_payload.error_message or f"Analysis run failed: {run_id}")
