from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.graph.nodes.formatter import run_report_formatter
from app.graph.nodes.memory import run_memory_read, run_memory_write
from app.graph.nodes.synthesizer import run_evidence_synthesizer
from app.graph.nodes.trend_gen import run_trend_gen_agent
from app.graph.state import TrendDiscoveryState


def route_trend_gen(state: TrendDiscoveryState):
    regions = state["query_intent"]["markets"]
    return [Send("trend_gen_agent", {**state, "active_region": region}) for region in regions]


def confidence_gate(state: TrendDiscoveryState) -> str:
    confirmed = [trend for trend in state.get("synthesized_trends", []) if trend.get("status") == "confirmed"]
    if not confirmed:
        return "insufficient_data"
    if len(confirmed) < 3 or state.get("watch_list_only"):
        return "low_signal"
    return "proceed"


def build_graph():
    builder = StateGraph(TrendDiscoveryState)
    builder.add_node("memory_read", run_memory_read)
    builder.add_node("trend_gen_agent", run_trend_gen_agent)
    builder.add_node("evidence_synthesizer", run_evidence_synthesizer)
    builder.add_node("formatter", run_report_formatter)
    builder.add_node("memory_write", run_memory_write)

    builder.add_edge(START, "memory_read")
    builder.add_conditional_edges("memory_read", route_trend_gen)
    builder.add_edge("trend_gen_agent", "evidence_synthesizer")
    builder.add_conditional_edges(
        "evidence_synthesizer",
        confidence_gate,
        {
            "proceed": "formatter",
            "low_signal": "formatter",
            "insufficient_data": "formatter",
        },
    )
    builder.add_edge("formatter", "memory_write")
    builder.add_edge("memory_write", END)
    return builder.compile(checkpointer=MemorySaver())
