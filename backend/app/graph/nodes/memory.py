from __future__ import annotations

from app.db.repository import get_prior_trend_snapshot, persist_trend_report
from app.graph.state import TrendDiscoveryState
from app.graph.tools import make_tool_invocation, now_iso


def run_memory_read(state: TrendDiscoveryState) -> TrendDiscoveryState:
    market = state.get("market", "HK")
    category = state.get("category", "all")
    started_at = now_iso()
    snapshot = get_prior_trend_snapshot(market=market, category=category)
    invocation = make_tool_invocation(
        node="memory_read",
        tool="memory.read",
        tool_kind="memory",
        title="Memory: load prior trend snapshots",
        started_at=started_at,
        completed_at=now_iso(),
        status="success",
        input_summary=f"market={market} category={category}",
        sql=(
            "SELECT canonical_term, market, hb_category, virality_score, confidence_tier, "
            "status, analysis_date FROM trend_exploration "
            "WHERE market = :market AND COALESCE(hb_category,'all') = :category "
            "AND datetime(analysis_date) >= datetime('now','-30 days') "
            "ORDER BY datetime(analysis_date) DESC"
        ),
        output_summary=f"{len(snapshot)} prior snapshot rows",
        metadata={"row_count": len(snapshot)},
    )
    return {
        "prior_snapshot": snapshot,
        "execution_log": [f"[MemoryRead] loaded {len(snapshot)} prior trend snapshots"],
        "tool_invocations": [invocation],
    }


def run_memory_write(state: TrendDiscoveryState) -> TrendDiscoveryState:
    report = state.get("formatted_report") or {}
    trends = list(report.get("trends", [])) + list(report.get("watch_list", []))
    if not report or not report.get("report_id") or not trends:
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

    started_at = now_iso()
    persist_trend_report(
        report_id=report["report_id"],
        market=state["market"],
        batch_ids=list(state.get("source_batch_ids") or []),
        trend_rows=trends,
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
            f"report_id={report['report_id']} market={state.get('market')} trends={len(trends)}"
        ),
        sql="INSERT OR REPLACE INTO trend_exploration (...) VALUES (...)",
        output_summary=f"persisted {len(trends)} trend snapshots",
        metadata={"trend_count": len(trends)},
    )
    return {
        "execution_log": [f"[MemoryWrite] persisted {len(trends)} trend snapshots"],
        "tool_invocations": [invocation],
    }
