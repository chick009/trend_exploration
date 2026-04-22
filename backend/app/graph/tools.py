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
TRACE_FIELD_LIMIT = 262_144


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


def _truncate_text(value: str | None, *, field_name: str, metadata: dict[str, Any]) -> str | None:
    if value is None or len(value) <= TRACE_FIELD_LIMIT:
        return value
    truncated_fields = list(metadata.get("truncated_fields") or [])
    if field_name not in truncated_fields:
        truncated_fields.append(field_name)
    metadata["truncated_fields"] = truncated_fields
    metadata["_truncated"] = True
    return f"{value[:TRACE_FIELD_LIMIT]}\n...[truncated]"


def _truncate_messages(messages: list[dict[str, str]] | None, metadata: dict[str, Any]) -> list[dict[str, str]] | None:
    if messages is None:
        return None
    truncated_messages: list[dict[str, str]] = []
    changed = False
    for message in messages:
        content = message.get("content")
        truncated_content = _truncate_text(content, field_name="messages", metadata=metadata)
        if truncated_content != content:
            changed = True
        truncated_messages.append({**message, "content": truncated_content or ""})
    return truncated_messages if changed else messages


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
    system_prompt: str | None = None,
    user_prompt: str | None = None,
    response_text: str | None = None,
    messages: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Return a serializable tool-invocation record.

    The structure is deliberately flat so it can be persisted as JSON and
    consumed verbatim by the frontend timeline.
    """
    serialized_metadata = dict(metadata or {})
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
        "metadata": serialized_metadata,
        "system_prompt": _truncate_text(system_prompt, field_name="system_prompt", metadata=serialized_metadata),
        "user_prompt": _truncate_text(user_prompt, field_name="user_prompt", metadata=serialized_metadata),
        "response_text": _truncate_text(response_text, field_name="response_text", metadata=serialized_metadata),
        "messages": _truncate_messages(messages, serialized_metadata),
    }
