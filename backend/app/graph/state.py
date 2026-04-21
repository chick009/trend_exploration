from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict

from langgraph.graph import add_messages


class TrendDiscoveryState(TypedDict, total=False):
    market: str
    category: str
    recency_days: int
    analysis_mode: str
    user_query: str
    query_intent: dict
    query_params: dict
    sql_results: dict
    prior_snapshot: dict[str, dict]
    active_region: Optional[str]
    trend_candidates: Annotated[list[dict], operator.add]
    synthesized_trends: list[dict]
    formatted_report: dict
    messages: Annotated[list, add_messages]
    guardrail_flags: Annotated[list[str], operator.add]
    execution_log: Annotated[list[str], operator.add]
    retry_count: int
    watch_list_only: bool
    source_batch_ids: Annotated[list[str], operator.add]
