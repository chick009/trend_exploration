"""Helpers for recording LangGraph tool invocations during an analysis run.

Tool invocations are structured records that describe every side-effect the
LangGraph multi-agent run performs: SQL reads against the local SQLite
database, LLM calls used for planning/scoring, and memory read/write
operations. They are appended to `TrendDiscoveryState.tool_invocations` and
surfaced on `RunStatusResponse.tool_invocations` so the frontend can render a
live tool-use timeline while the stream is running.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4


ToolKind = str  # "sql" | "llm" | "memory"


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def _duration_ms(started_at: str, completed_at: str | None) -> float | None:
    if not completed_at:
        return None
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(completed_at)
    except ValueError:
        return None
    return round((end - start).total_seconds() * 1000, 2)


def make_tool_invocation(
    *,
    node: str,
    tool: str,
    tool_kind: ToolKind,
    title: str,
    started_at: str,
    completed_at: str | None = None,
    status: str = "success",
    input_summary: str | None = None,
    sql: str | None = None,
    output_summary: str | None = None,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a serializable tool-invocation record.

    The structure is deliberately flat so it can be persisted as JSON and
    consumed verbatim by the frontend timeline.
    """

    return {
        "id": uuid4().hex,
        "node": node,
        "tool": tool,
        "tool_kind": tool_kind,
        "title": title,
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": _duration_ms(started_at, completed_at),
        "input_summary": input_summary,
        "sql": sql,
        "output_summary": output_summary,
        "error": error,
        "metadata": metadata or {},
    }
