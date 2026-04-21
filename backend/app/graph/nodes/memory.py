from __future__ import annotations

from app.db.repository import get_prior_trend_snapshot, persist_trend_report
from app.graph.state import TrendDiscoveryState


def run_memory_read(state: TrendDiscoveryState) -> TrendDiscoveryState:
    market = state.get("market", "HK")
    category = state.get("category", "all")
    snapshot = get_prior_trend_snapshot(market=market, category=category)
    return {
        "prior_snapshot": snapshot,
        "execution_log": [f"[MemoryRead] loaded {len(snapshot)} prior trend snapshots"],
    }


def run_memory_write(state: TrendDiscoveryState) -> TrendDiscoveryState:
    report = state.get("formatted_report") or {}
    trends = list(report.get("trends", [])) + list(report.get("watch_list", []))
    if not report or not report.get("report_id") or not trends:
        return {
            "execution_log": ["[MemoryWrite] skipped persistence (no finalized report payload)"],
        }

    persist_trend_report(
        report_id=report["report_id"],
        market=state["market"],
        batch_ids=list(state.get("source_batch_ids") or []),
        trend_rows=trends,
        report_payload=report,
    )
    return {
        "execution_log": [f"[MemoryWrite] persisted {len(trends)} trend snapshots"],
    }
