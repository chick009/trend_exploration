from __future__ import annotations

from datetime import datetime

from app.db.repository import upsert_post_trend_signals, upsert_search_trend
from app.graph.nodes.formatter import run_report_formatter
from app.graph.nodes.memory import run_memory_write
from app.graph.nodes.sql_dispatcher import load_sql_results


def test_memory_write_then_backend_preload_round_trip(test_database) -> None:
    state = {
        "market": "HK",
        "category": "skincare",
        "source_batch_ids": ["batch-1"],
        "formatted_report": {
            "report_id": "report-1",
            "generated_at": "2026-04-21T00:00:00",
            "market": "HK",
            "category": "skincare",
            "recency_days": 14,
            "trends": [
                {
                    "rank": 1,
                    "term": "niacinamide",
                    "entity_type": "ingredient",
                    "virality_score": 0.81,
                    "confidence_tier": "high",
                    "headline": "Search breakout building around niacinamide",
                    "why_viral": "niacinamide is showing broad support.",
                    "viral_reasons": ["Niacinamide is showing broad support."],
                    "evidence": {},
                    "signal_chips": ["Post Signals", "Google Trends", "Sales"],
                    "trend_stage": "accelerating",
                    "watch_flag": False,
                    "positivity_score": 0.8,
                    "social_score": 0.7,
                    "search_score": 0.9,
                    "sales_score": 0.6,
                    "cross_market_score": 0.0,
                    "sources_count": 3,
                    "category": "skincare",
                    "market": "HK",
                    "source_batch_ids": ["batch-1"],
                    "sentiment_score": 0.8,
                    "lens": "Momentum",
                    "lifecycle_stage": "emerging",
                    "self_confidence": "high",
                    "challenge_notes": ["Multi-signal confirmation."],
                }
            ],
            "watch_list": [],
            "regional_divergences": [],
            "execution_trace": [],
            "guardrail_flags": [],
        },
    }

    write_result = run_memory_write(state)
    assert "[MemoryWrite]" in write_result["execution_log"][0]

    sql_results, prior_snapshot, source_batch_ids, query_plan, tool_invocations = load_sql_results(
        {
            "markets": ["HK"],
            "category": "skincare",
            "recency_days": 14,
            "entity_types": ["ingredient", "brand", "function"],
            "analysis_mode": "single_market",
            "focus_hint": None,
        }
    )
    assert "memory" in query_plan
    assert "HK:niacinamide" in prior_snapshot
    assert prior_snapshot["HK:niacinamide"]["virality_score"] == 0.81
    assert sql_results["memory"][0]["canonical_term"] == "niacinamide"
    assert "batch-1" in source_batch_ids
    assert any(invocation["tool"] == "sql.memory" for invocation in tool_invocations)


def test_backend_preload_uses_post_trend_signals_for_social_source(test_database) -> None:
    processed_at = datetime.utcnow().isoformat()
    upsert_post_trend_signals(
        [
            {
                "source_table": "instagram_posts",
                "source_row_id": "ig-1",
                "source_batch_id": "signal-batch-1",
                "search_keyword": "niacinamide",
                "input_text": "niacinamide serum is trending again",
                "region": "HK",
                "category": "skincare",
                "trend_strength": 0.8,
                "novelty": 0.4,
                "consumer_intent": 0.7,
                "llm_rationale": "Strong skincare chatter.",
                "processing_model": "test-model",
                "processed_at": processed_at,
            },
            {
                "source_table": "tiktok_photo_posts",
                "source_row_id": "tt-1",
                "source_batch_id": "signal-batch-1",
                "search_keyword": "niacinamide",
                "input_text": "viral niacinamide routine post",
                "region": "HK",
                "category": "skincare",
                "trend_strength": 0.6,
                "novelty": 0.5,
                "consumer_intent": 0.8,
                "llm_rationale": "Repeated social proof.",
                "processing_model": "test-model",
                "processed_at": processed_at,
            },
        ]
    )

    sql_results, _, source_batch_ids, _, tool_invocations = load_sql_results(
        {
            "markets": ["HK"],
            "category": "skincare",
            "recency_days": 14,
            "entity_types": ["ingredient", "brand", "function"],
            "analysis_mode": "single_market",
            "focus_hint": None,
        }
    )

    social_rows = sql_results["social"]
    assert len(social_rows) == 1
    assert social_rows[0]["canonical_term"] == "niacinamide"
    assert social_rows[0]["social_post_count"] == 2
    assert social_rows[0]["avg_signal_strength"] == 0.7
    assert social_rows[0]["avg_consumer_intent"] == 0.75
    assert social_rows[0]["source_batch_ids"] == ["signal-batch-1"]
    assert "signal-batch-1" in source_batch_ids
    assert any(
        invocation["tool"] == "sql.social" and "post_trend_signals" in (invocation.get("sql") or "")
        for invocation in tool_invocations
    )


def test_backend_preload_search_matches_normalized_llm_category(test_database) -> None:
    upsert_search_trend(
        {
            "keyword": "niacinamide",
            "geo": "KR",
            "snapshot_date": datetime.utcnow().date().isoformat(),
            "index_value": 72,
            "wow_delta": 0.42,
            "is_breakout": True,
            "related_rising": ["niacinamide serum"],
            "raw_timeseries": [12, 18, 24, 31, 45, 58, 72],
            "source": "serpapi",
            "llm_category": "skincare, makeup",
            "llm_subcategory": "serums",
            "relevance_score": 0.83,
            "processed_at": datetime.utcnow().isoformat(),
            "source_batch_id": "search-batch-1",
        }
    )

    sql_results, _, source_batch_ids, _, tool_invocations = load_sql_results(
        {
            "markets": ["KR"],
            "category": "skincare",
            "recency_days": 14,
            "entity_types": ["ingredient", "brand", "function"],
            "analysis_mode": "single_market",
            "focus_hint": None,
        }
    )

    assert len(sql_results["search"]) == 1
    assert sql_results["search"][0]["canonical_term"] == "niacinamide"
    assert sql_results["search"][0]["source_batch_ids"] == ["search-batch-1"]
    assert "search-batch-1" in source_batch_ids
    assert any(
        invocation["tool"] == "sql.search" and "INSTR(',' ||" in (invocation.get("sql") or "")
        for invocation in tool_invocations
    )


def test_formatter_promotes_sentence_trend_over_term_only_label(test_database) -> None:
    result = run_report_formatter(
        {
            "market": "KR",
            "category": "skincare",
            "recency_days": 14,
            "execution_log": [],
            "guardrail_flags": [],
            "formatted_report": {"regional_divergences": []},
            "synthesized_trends": [
                {
                    "canonical_term": "niacinamide",
                    "entity_type": "ingredient",
                    "virality_score": 0.71,
                    "confidence_tier": "high",
                    "trend_statement": "niacinamide",
                    "viral_reasoning": "Multiple signals are aligning around barrier-support routines.",
                    "social_post_count": 5,
                    "avg_signal_strength": 0.72,
                    "avg_engagement": 0.72,
                    "avg_positivity_score": 0.65,
                    "social_score": 0.68,
                    "search_score": 0.74,
                    "sales_score": 0.41,
                    "cross_market_score": 0.0,
                    "search_wow_delta": 0.52,
                    "sales_velocity": 0.18,
                    "restock_count": 1,
                    "sources_count": 3,
                    "category": "skincare",
                    "market": "KR",
                    "markets": ["KR"],
                    "source_batch_ids": ["batch-1"],
                    "sentiment_score": 0.65,
                    "lifecycle_stage": "accelerating",
                    "self_confidence": "high",
                    "challenge_notes": [],
                    "status": "confirmed",
                    "watch_flag": False,
                }
            ],
        }
    )

    trend = result["formatted_report"]["trends"][0]
    assert trend["headline"] != "niacinamide"
    assert trend["trend_statement"] == trend["headline"]
    assert "niacinamide" in trend["headline"].lower()
    assert trend["headline"].endswith(".")
    assert trend["viral_reasons"]
