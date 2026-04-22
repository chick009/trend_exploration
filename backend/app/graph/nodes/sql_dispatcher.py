from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.db.repository import (
    get_entity_dictionary,
    get_latest_source_batch_ids,
    get_sales_velocity_rows,
    get_search_breakout_rows,
    get_social_trend_rows,
    json_loads,
)
from app.graph.state import TrendDiscoveryState
from app.graph.tools import make_tool_invocation, now_iso


def _build_alias_map(dictionary: dict[str, dict[str, Any]]) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for canonical_term, metadata in dictionary.items():
        alias_map[canonical_term.strip().lower()] = canonical_term
        for alias in metadata.get("aliases", []):
            alias_map[str(alias).strip().lower()] = canonical_term
    return alias_map


def _resolve_entity(
    raw_term: str,
    *,
    dictionary: dict[str, dict[str, Any]],
    alias_map: dict[str, str],
    default_entity_type: str,
    fallback_category: str,
) -> tuple[str, str, str]:
    normalized = raw_term.strip()
    canonical = alias_map.get(normalized.lower(), normalized)
    metadata = dictionary.get(canonical, {})
    entity_type = metadata.get("entity_type") or default_entity_type
    category = metadata.get("hb_category") or fallback_category
    return canonical, entity_type, category


def _should_include_entity(entity_type: str, allowed_entity_types: set[str]) -> bool:
    return not allowed_entity_types or entity_type in allowed_entity_types


def select_query_plan(intent: dict) -> tuple[str, ...]:
    entity_types = set(intent.get("entity_types", []))
    focus_hint = (intent.get("focus_hint") or "").lower()

    if entity_types == {"brand"} or "brand" in focus_hint:
        return ("sales", "social")
    if entity_types and entity_types.issubset({"ingredient", "function"}):
        return ("social", "search", "sales")
    if intent.get("analysis_mode") == "cross_market":
        return ("social", "search", "sales")
    return ("social", "search", "sales")


def _aggregate_social(
    *,
    markets: list[str],
    category: str,
    recency_days: int,
    dictionary: dict[str, dict[str, Any]],
    alias_map: dict[str, str],
    allowed_entity_types: set[str],
) -> list[dict[str, Any]]:
    aggregate: dict[tuple[str, str], dict[str, Any]] = {}
    for market in markets:
        for row in get_social_trend_rows(region=market, category=category, recency_days=recency_days):
            for raw_term in json_loads(row["entity_list"], []):
                canonical_term, entity_type, resolved_category = _resolve_entity(
                    raw_term,
                    dictionary=dictionary,
                    alias_map=alias_map,
                    default_entity_type="ingredient",
                    fallback_category=category,
                )
                if not _should_include_entity(entity_type, allowed_entity_types):
                    continue
                key = (market, canonical_term)
                current = aggregate.setdefault(
                    key,
                    {
                        "canonical_term": canonical_term,
                        "entity_type": entity_type,
                        "category": resolved_category,
                        "market": market,
                        "social_post_count": 0,
                        "avg_engagement": 0.0,
                        "avg_positivity_score": 0.0,
                        "source_batch_ids": [],
                    },
                )
                current["social_post_count"] += row.get("post_count") or 0
                current["avg_engagement"] = max(current["avg_engagement"], row.get("avg_engagement") or 0.0)
                current["avg_positivity_score"] = max(
                    current["avg_positivity_score"], row.get("avg_positivity_score") or 0.0
                )
    return sorted(aggregate.values(), key=lambda item: (item["market"], item["canonical_term"]))


def _aggregate_search(
    *,
    markets: list[str],
    category: str,
    recency_days: int,
    dictionary: dict[str, dict[str, Any]],
    alias_map: dict[str, str],
    allowed_entity_types: set[str],
) -> list[dict[str, Any]]:
    aggregate: dict[tuple[str, str], dict[str, Any]] = {}
    for market in markets:
        for row in get_search_breakout_rows(region=market, category=category, recency_days=recency_days):
            canonical_term, entity_type, resolved_category = _resolve_entity(
                row["keyword"],
                dictionary=dictionary,
                alias_map=alias_map,
                default_entity_type="ingredient",
                fallback_category=category,
            )
            if not _should_include_entity(entity_type, allowed_entity_types):
                continue
            key = (market, canonical_term)
            current = aggregate.setdefault(
                key,
                {
                    "canonical_term": canonical_term,
                    "entity_type": entity_type,
                    "category": resolved_category,
                    "market": market,
                    "search_wow_delta": 0.0,
                    "search_index_value": 0.0,
                    "source_batch_ids": set(),
                },
            )
            current["search_wow_delta"] = max(current["search_wow_delta"], row.get("wow_delta") or 0.0)
            current["search_index_value"] = max(current["search_index_value"], row.get("index_value") or 0.0)
            if row.get("source_batch_id"):
                current["source_batch_ids"].add(row["source_batch_id"])

    results = []
    for row in aggregate.values():
        row["source_batch_ids"] = sorted(row["source_batch_ids"])
        results.append(row)
    return sorted(results, key=lambda item: (item["market"], item["canonical_term"]))


def _aggregate_sales(
    *,
    markets: list[str],
    category: str,
    recency_days: int,
    dictionary: dict[str, dict[str, Any]],
    alias_map: dict[str, str],
    allowed_entity_types: set[str],
) -> list[dict[str, Any]]:
    aggregate: dict[tuple[str, str], dict[str, Any]] = {}
    for market in markets:
        for row in get_sales_velocity_rows(region=market, category=category, recency_days=recency_days):
            raw_terms = {term for term in json_loads(row["ingredient_tags"], []) if term}
            brand = row.get("brand")
            if brand:
                raw_terms.add(brand)
            for raw_term in raw_terms:
                default_entity_type = "brand" if brand and raw_term == brand else "ingredient"
                canonical_term, entity_type, resolved_category = _resolve_entity(
                    raw_term,
                    dictionary=dictionary,
                    alias_map=alias_map,
                    default_entity_type=default_entity_type,
                    fallback_category=row.get("category") or category,
                )
                if not _should_include_entity(entity_type, allowed_entity_types):
                    continue
                key = (market, canonical_term)
                current = aggregate.setdefault(
                    key,
                    {
                        "canonical_term": canonical_term,
                        "entity_type": entity_type,
                        "category": resolved_category,
                        "market": market,
                        "sales_velocity": 0.0,
                        "restock_count": 0,
                        "source_batch_ids": set(),
                    },
                )
                current["sales_velocity"] = max(current["sales_velocity"], row.get("avg_velocity") or 0.0)
                current["restock_count"] = max(current["restock_count"], row.get("restock_count") or 0)
                if row.get("source_batch_id"):
                    current["source_batch_ids"].add(row["source_batch_id"])

    results = []
    for row in aggregate.values():
        row["source_batch_ids"] = sorted(row["source_batch_ids"])
        results.append(row)
    return sorted(results, key=lambda item: (item["market"], item["canonical_term"]))


def _render_category_clause(column_name: str, category: str) -> str:
    if category == "all":
        return ""
    return f" AND COALESCE({column_name}, 'all') = '{category}'"


def _build_sql_preview(
    *,
    source: str,
    markets: list[str],
    category: str,
    recency_days: int,
) -> str:
    markets_sql = ", ".join(f"'{market}'" for market in markets)
    recency_sql = f"-{recency_days} days"
    if source == "social":
        return (
            "SELECT COALESCE(llm_entities, entity_mentions, '[]') AS entity_list, "
            "AVG(engagement_score) AS avg_engagement, AVG(positivity_score) AS avg_positivity_score, "
            "COUNT(*) AS post_count "
            "FROM social_posts "
            f"WHERE region IN ({markets_sql}) AND date(post_date) >= date('now', '{recency_sql}')"
            f"{_render_category_clause('llm_category', category)} AND relevance_score >= 0.4 "
            "GROUP BY entity_list"
        )
    if source == "search":
        return (
            "SELECT keyword, wow_delta, index_value, source_batch_id "
            "FROM search_trends "
            f"WHERE geo IN ({markets_sql}) AND date(snapshot_date) >= date('now', '{recency_sql}') "
            f"AND is_breakout = 1{_render_category_clause('llm_category', category)} "
            "AND relevance_score >= 0.4 ORDER BY wow_delta DESC"
        )
    if source == "sales":
        return (
            "SELECT ingredient_tags, brand, category, AVG(wow_velocity) AS avg_velocity, "
            "SUM(units_sold) AS total_units, SUM(is_restocking) AS restock_count, source_batch_id "
            "FROM sales_data "
            f"WHERE region IN ({markets_sql}) AND date(week_start) >= date('now', '{recency_sql}')"
            f"{_render_category_clause('category', category)} "
            "GROUP BY brand, ingredient_tags, category, source_batch_id ORDER BY avg_velocity DESC"
        )
    return ""


_SIGNAL_TITLES = {
    "social": "SQL: aggregate RedNote social posts",
    "search": "SQL: aggregate Google Trends breakouts",
    "sales": "SQL: aggregate sales velocity",
}


def load_sql_results(
    intent: dict[str, Any],
    *,
    seed_source_batch_ids: list[str] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], list[str], tuple[str, ...], list[dict[str, Any]]]:
    markets = list(intent["markets"])
    category = intent["category"]
    recency_days = intent["recency_days"]
    dictionary = get_entity_dictionary()
    alias_map = _build_alias_map(dictionary)
    allowed_entity_types = set(intent.get("entity_types", []))
    query_plan = select_query_plan(intent)

    sql_results: dict[str, list[dict[str, Any]]] = {
        "social": [],
        "search": [],
        "sales": [],
    }

    tool_invocations: list[dict[str, Any]] = []
    aggregators = {
        "social": _aggregate_social,
        "search": _aggregate_search,
        "sales": _aggregate_sales,
    }

    for source in ("social", "search", "sales"):
        if source not in query_plan:
            continue
        started_at = now_iso()
        sql_preview = _build_sql_preview(
            source=source,
            markets=markets,
            category=category,
            recency_days=recency_days,
        )
        try:
            rows = aggregators[source](
                markets=markets,
                category=category,
                recency_days=recency_days,
                dictionary=dictionary,
                alias_map=alias_map,
                allowed_entity_types=allowed_entity_types,
            )
        except Exception as exc:
            tool_invocations.append(
                make_tool_invocation(
                    node="sql_dispatcher",
                    tool=f"sql.{source}",
                    tool_kind="sql",
                    title=_SIGNAL_TITLES[source],
                    started_at=started_at,
                    completed_at=now_iso(),
                    status="error",
                    input_summary=(
                        f"markets={markets} category={category} recency_days={recency_days}"
                    ),
                    sql=sql_preview,
                    error=str(exc),
                )
            )
            raise
        sql_results[source] = rows
        tool_invocations.append(
            make_tool_invocation(
                node="sql_dispatcher",
                tool=f"sql.{source}",
                tool_kind="sql",
                title=_SIGNAL_TITLES[source],
                started_at=started_at,
                completed_at=now_iso(),
                status="success",
                input_summary=(
                    f"markets={markets} category={category} recency_days={recency_days}"
                ),
                sql=sql_preview,
                output_summary=f"{len(rows)} aggregated rows",
                metadata={
                    "markets": markets,
                    "category": category,
                    "recency_days": recency_days,
                    "row_count": len(rows),
                },
            )
        )

    source_batch_ids = set(seed_source_batch_ids or [])
    source_batch_ids.update(get_latest_source_batch_ids())
    for signal_rows in sql_results.values():
        for row in signal_rows:
            source_batch_ids.update(row.get("source_batch_ids", []))

    return sql_results, sorted(source_batch_ids), query_plan, tool_invocations


def run_sql_dispatcher(state: TrendDiscoveryState) -> TrendDiscoveryState:
    sql_results, source_batch_ids, query_plan, tool_invocations = load_sql_results(
        state["query_intent"],
        seed_source_batch_ids=list(state.get("source_batch_ids", [])),
    )

    return {
        "sql_results": sql_results,
        "source_batch_ids": source_batch_ids,
        "execution_log": [
            (
                "[BackendData] "
                f"plan={list(query_plan)} social={len(sql_results['social'])} "
                f"search={len(sql_results['search'])} sales={len(sql_results['sales'])}"
            )
        ],
        "tool_invocations": tool_invocations,
    }
