from __future__ import annotations

from app.db.repository import persist_trend_report
from app.graph.state import TrendDiscoveryState
from app.graph.tools import make_tool_invocation, now_iso


def run_memory_write(state: TrendDiscoveryState) -> TrendDiscoveryState:
    report = state.get("formatted_report") or {}
    if not report or not report.get("report_id"):
        return {
            "execution_log": ["[MemoryWrite] skipped persistence (no finalized report payload)"],
            "tool_invocations": [
                make_tool_invocation(
                    node="memory_write",
                    tool="memory.write",
                    tool_kind="memory",
                    title="Memory: persist trend report",
                    started_at=now_iso(),
                    completed_at=now_iso(),
                    status="success",
                    output_summary="skipped (no finalized report payload)",
                )
            ],
        }

    confirmed_trends = [trend for trend in report.get("trends", []) if not trend.get("watch_flag")]
    if not confirmed_trends:
        message = "No confirmed trends; trend_exploration intentionally left empty for this run."
        return {
            "execution_log": [f"[MemoryWrite] skipped insert ({message})"],
            "guardrail_flags": [message],
            "tool_invocations": [
                make_tool_invocation(
                    node="memory_write",
                    tool="memory.write",
                    tool_kind="memory",
                    title="Memory: persist trend report",
                    started_at=now_iso(),
                    completed_at=now_iso(),
                    status="success",
                    output_summary="skipped insert (no confirmed trends)",
                    metadata={"confirmed_trend_count": 0},
                )
            ],
        }

    started_at = now_iso()
    persist_trend_report(
        report_id=report["report_id"],
        market=state["market"],
        batch_ids=list(state.get("source_batch_ids") or []),
        trend_rows=confirmed_trends,
        report_payload=report,
    )
    invocation = make_tool_invocation(
        node="memory_write",
        tool="memory.write",
        tool_kind="memory",
        title="Memory: persist trend report",
        started_at=started_at,
        completed_at=now_iso(),
        status="success",
        input_summary=(
            f"report_id={report['report_id']} market={state.get('market')} trends={len(confirmed_trends)}"
        ),
        sql="INSERT OR REPLACE INTO trend_exploration (...) VALUES (...)",
        output_summary=f"persisted {len(confirmed_trends)} confirmed trend snapshots",
        metadata={"trend_count": len(confirmed_trends)},
    )
    return {
        "execution_log": [f"[MemoryWrite] persisted {len(confirmed_trends)} confirmed trend snapshots"],
        "tool_invocations": [invocation],
    }
