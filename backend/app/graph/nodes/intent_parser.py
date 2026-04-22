from __future__ import annotations

from app.graph import llm as graph_llm
from app.graph.nodes.sql_dispatcher import select_query_plan
from app.graph.schemas import QueryIntent
from app.graph.state import TrendDiscoveryState
from app.graph.tools import make_tool_invocation, now_iso

SUPPORTED_MARKETS = ("HK", "KR", "TW", "SG")
SUPPORTED_CATEGORIES = {"skincare", "haircare", "makeup", "supplements", "all"}
SUPPORTED_ENTITY_TYPES = {"ingredient", "brand", "function"}

PLANNER_SCHEMA_REFERENCE = """
Relevant queryable tables and important columns:

1. search_trends (Google Trends breakout table)
- keyword TEXT
- geo TEXT
- snapshot_date DATE
- index_value REAL
- wow_delta REAL
- is_breakout INTEGER
- related_rising TEXT
- llm_category TEXT
- llm_subcategory TEXT
- relevance_score REAL
- source_batch_id TEXT
Use for Google Trends questions. Market filter is `geo`; recency filter is `snapshot_date`.

2. sales_data (weekly sales velocity table)
- sku TEXT
- product_name TEXT
- brand TEXT
- ingredient_tags TEXT
- category TEXT
- region TEXT
- week_start DATE
- units_sold INTEGER
- revenue REAL
- wow_velocity REAL
- is_restocking INTEGER
- source_batch_id TEXT
Use for sales momentum and restocking questions. Market filter is `region`; recency filter is `week_start`.

3. post_trend_signals (LLM-scored post signal table)
- source_table TEXT
- source_row_id TEXT
- source_batch_id TEXT
- search_keyword TEXT
- input_text TEXT
- region TEXT
- category TEXT
- trend_strength REAL
- novelty REAL
- consumer_intent REAL
- llm_rationale TEXT
- processing_model TEXT
- processed_at DATETIME
Use for social trend strength / novelty / consumer intent questions. Market filter is `region`; recency filter is `processed_at`.

Column-name alignment notes:
- Google Trends market column is `geo`.
- Sales and post-trend-signals market column is `region`.
- Search category column is `llm_category`; sales and post-trend-signals category column is `category`.
- Recent Google Trends means `snapshot_date`; recent sales means `week_start`; recent post scoring means `processed_at`.
""".strip()


def _default_markets(state: TrendDiscoveryState) -> list[str]:
    market = state.get("market", "HK")
    if market == "cross" or state.get("analysis_mode") == "cross_market":
        return list(SUPPORTED_MARKETS)
    return [market]


def _default_intent(state: TrendDiscoveryState) -> QueryIntent:
    return QueryIntent(
        markets=_default_markets(state),
        category=state.get("category", "all"),
        recency_days=state.get("recency_days", 14),
        entity_types=["ingredient", "brand", "function"],
        analysis_mode="cross_market"
        if state.get("market") == "cross" or state.get("analysis_mode") == "cross_market"
        else "single_market",
        focus_hint=None,
    )


def _merge_intent(state: TrendDiscoveryState, llm_intent: QueryIntent | None) -> QueryIntent:
    defaults = _default_intent(state)
    if llm_intent is None:
        return defaults

    requested_markets = defaults.markets
    requested_category = defaults.category
    requested_mode = defaults.analysis_mode

    resolved_markets = llm_intent.markets if requested_mode == "cross_market" else requested_markets
    if not resolved_markets:
        resolved_markets = requested_markets
    resolved_markets = [market for market in resolved_markets if market in SUPPORTED_MARKETS] or requested_markets

    resolved_category = llm_intent.category if requested_category == "all" else requested_category
    if resolved_category not in SUPPORTED_CATEGORIES:
        resolved_category = requested_category

    resolved_entity_types = [
        entity_type for entity_type in llm_intent.entity_types if entity_type in SUPPORTED_ENTITY_TYPES
    ] or defaults.entity_types

    return QueryIntent(
        markets=resolved_markets,
        category=resolved_category,
        recency_days=llm_intent.recency_days,
        entity_types=resolved_entity_types,
        analysis_mode=requested_mode,
        focus_hint=(llm_intent.focus_hint or None),
    )


def _render_category_clause(column_name: str, category: str) -> str:
    if category == "all":
        return ""
    return f" AND COALESCE({column_name}, 'all') = '{category}'"


def _build_query_params(query_intent: QueryIntent) -> dict[str, object]:
    query_plan = list(select_query_plan(query_intent.model_dump()))
    markets_sql = ", ".join(f"'{market}'" for market in query_intent.markets)
    recency_sql = f"-{query_intent.recency_days} days"
    sql_preview: dict[str, str] = {}

    if "social" in query_plan:
        sql_preview["social"] = (
            "SELECT COALESCE(llm_entities, entity_mentions, '[]') AS entity_list, "
            "AVG(engagement_score) AS avg_engagement, AVG(positivity_score) AS avg_positivity_score, "
            "COUNT(*) AS post_count FROM social_posts "
            f"WHERE region IN ({markets_sql}) AND date(post_date) >= date('now', '{recency_sql}')"
            f"{_render_category_clause('llm_category', query_intent.category)} AND relevance_score >= 0.4 "
            "GROUP BY entity_list"
        )
    if "search" in query_plan:
        sql_preview["search"] = (
            "SELECT keyword, wow_delta, index_value, source_batch_id FROM search_trends "
            f"WHERE geo IN ({markets_sql}) AND date(snapshot_date) >= date('now', '{recency_sql}') "
            f"AND is_breakout = 1{_render_category_clause('llm_category', query_intent.category)} "
            "AND relevance_score >= 0.4 ORDER BY wow_delta DESC"
        )
    if "sales" in query_plan:
        sql_preview["sales"] = (
            "SELECT ingredient_tags, brand, category, AVG(wow_velocity) AS avg_velocity, "
            "SUM(units_sold) AS total_units, SUM(is_restocking) AS restock_count, source_batch_id "
            "FROM sales_data "
            f"WHERE region IN ({markets_sql}) AND date(week_start) >= date('now', '{recency_sql}')"
            f"{_render_category_clause('category', query_intent.category)} "
            "GROUP BY brand, ingredient_tags, category, source_batch_id ORDER BY avg_velocity DESC"
        )

    return {
        "query_plan": query_plan,
        "sql_preview": sql_preview,
    }


def build_intent_state_update(state: TrendDiscoveryState) -> TrendDiscoveryState:
    market = state.get("market", "HK")
    if market not in {*SUPPORTED_MARKETS, "cross"}:
        fallback_intent = _default_intent(state)
        return {
            "query_intent": fallback_intent.model_dump(),
            "query_params": _build_query_params(fallback_intent),
            "execution_log": [f"[IntentParser] unsupported market={market!r}; expected one of {[*SUPPORTED_MARKETS, 'cross']}"],
            "guardrail_flags": [f"Unsupported market: {market!r}"],
        }

    user_query = (state.get("user_query") or "").strip()
    llm_intent: QueryIntent | None = None
    tool_invocations: list[dict] = []
    if user_query:
        system_prompt = "Return only structured intent fields as JSON."
        prompt = f"""
You convert a trend-analysis request into strict structured intent.
Use only these market codes: {list(SUPPORTED_MARKETS)}.
Use only these categories: {sorted(SUPPORTED_CATEGORIES)}.
Use only these entity types: {sorted(SUPPORTED_ENTITY_TYPES)}.
Respect the explicit UI constraints from the request context.
Return a compact intent for a V2 single-run analysis.

Request context:
- requested_market: {state.get("market")}
- requested_category: {state.get("category")}
- requested_recency_days: {state.get("recency_days")}
- requested_analysis_mode: {state.get("analysis_mode")}

Schema reference:
{PLANNER_SCHEMA_REFERENCE}

User query:
{user_query}
""".strip()
        started_at = now_iso()
        try:
            llm_intent, trace = graph_llm.invoke_json_response_with_trace(
                QueryIntent,
                system_prompt=system_prompt,
                user_prompt=prompt,
            )
        except Exception as exc:
            trace = getattr(exc, "trace", None)
            tool_invocations.append(
                make_tool_invocation(
                    node="intent_parser",
                    tool="llm.intent_parser",
                    tool_kind="llm",
                    title="LLM: parse user query into structured intent",
                    started_at=started_at,
                    completed_at=now_iso(),
                    status="error",
                    input_summary=f"user_query={user_query[:200]}",
                    error=str(exc),
                    system_prompt=(trace or {}).get("system_prompt", system_prompt),
                    user_prompt=(trace or {}).get("user_prompt", prompt),
                    response_text=(trace or {}).get("response_text"),
                    messages=[
                        {"role": "system", "content": (trace or {}).get("system_prompt", system_prompt)},
                        {"role": "user", "content": (trace or {}).get("user_prompt", prompt)},
                    ],
                )
            )
            raise RuntimeError(f"[IntentParser] LLM intent parse failed: {exc!s}") from exc
        tool_invocations.append(
            make_tool_invocation(
                node="intent_parser",
                tool="llm.intent_parser",
                tool_kind="llm",
                title="LLM: parse user query into structured intent",
                started_at=started_at,
                completed_at=now_iso(),
                status="success",
                input_summary=f"user_query={user_query[:200]}",
                output_summary=(
                    f"markets={list(llm_intent.markets)} category={llm_intent.category} "
                    f"entity_types={list(llm_intent.entity_types)} "
                    f"analysis_mode={llm_intent.analysis_mode}"
                ),
                metadata={"schema": "QueryIntent", "model": trace["model"], "duration_ms": trace["duration_ms"]},
                system_prompt=trace["system_prompt"],
                user_prompt=trace["user_prompt"],
                response_text=trace["response_text"],
                messages=[
                    {"role": "system", "content": trace["system_prompt"]},
                    {"role": "user", "content": trace["user_prompt"]},
                    {"role": "assistant", "content": trace["response_text"] or ""},
                ],
            )
        )

    query_intent = _merge_intent(state, llm_intent)
    query_params = _build_query_params(query_intent)
    log_lines = [
        (
            "[IntentParser] "
            f"text2sql plan={query_params['query_plan']} markets={query_intent.markets} category={query_intent.category} "
            f"recency_days={query_intent.recency_days} analysis_mode={query_intent.analysis_mode} "
            f"entity_types={query_intent.entity_types}"
        )
    ]
    if query_intent.focus_hint:
        log_lines.append(f"[IntentParser] focus_hint={query_intent.focus_hint}")
    if user_query:
        log_lines.append(f"[IntentParser] user_query={user_query[:500]}{'…' if len(user_query) > 500 else ''}")
    return {
        "query_intent": query_intent.model_dump(),
        "query_params": query_params,
        "execution_log": log_lines,
        "tool_invocations": tool_invocations,
    }


def parse_query_intent(state: TrendDiscoveryState) -> TrendDiscoveryState:
    return build_intent_state_update(state)
