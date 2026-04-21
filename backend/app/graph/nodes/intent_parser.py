from __future__ import annotations

from app.graph import llm as graph_llm
from app.graph.schemas import QueryIntent
from app.graph.state import TrendDiscoveryState

SUPPORTED_MARKETS = ("HK", "KR", "TW", "SG")
SUPPORTED_CATEGORIES = {"skincare", "haircare", "makeup", "supplements", "all"}
SUPPORTED_ENTITY_TYPES = {"ingredient", "brand", "function"}


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


def parse_query_intent(state: TrendDiscoveryState) -> TrendDiscoveryState:
    market = state.get("market", "HK")
    if market not in {*SUPPORTED_MARKETS, "cross"}:
        return {
            "query_intent": _default_intent(state).model_dump(),
            "execution_log": [f"[IntentParser] unsupported market={market!r}; expected one of {[*SUPPORTED_MARKETS, 'cross']}"],
            "guardrail_flags": [f"Unsupported market: {market!r}"],
        }

    user_query = (state.get("user_query") or "").strip()
    llm_intent: QueryIntent | None = None
    if user_query:
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

User query:
{user_query}
""".strip()
        llm_intent = graph_llm.get_chat_model(temperature=0.0).with_structured_output(QueryIntent).invoke(
            [("system", "Return only structured intent fields."), ("human", prompt)]
        )

    query_intent = _merge_intent(state, llm_intent)
    log_lines = [
        (
            "[IntentParser] "
            f"markets={query_intent.markets} category={query_intent.category} "
            f"recency_days={query_intent.recency_days} analysis_mode={query_intent.analysis_mode} "
            f"entity_types={query_intent.entity_types}"
        )
    ]
    if query_intent.focus_hint:
        log_lines.append(f"[IntentParser] focus_hint={query_intent.focus_hint}")
    if user_query:
        log_lines.append(f"[IntentParser] user_query={user_query[:500]}{'…' if len(user_query) > 500 else ''}")
    return {"query_intent": query_intent.model_dump(), "execution_log": log_lines}
