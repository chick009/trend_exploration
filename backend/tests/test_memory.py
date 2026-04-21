from __future__ import annotations

from app.graph.nodes.memory import run_memory_read, run_memory_write


def test_memory_write_then_read_round_trip(test_database) -> None:
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
                    "evidence": {},
                    "signal_chips": ["REDNOTE", "Google Trends", "Sales"],
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

    read_result = run_memory_read({"market": "HK", "category": "skincare"})
    assert "prior_snapshot" in read_result
    assert "HK:niacinamide" in read_result["prior_snapshot"]
    assert read_result["prior_snapshot"]["HK:niacinamide"]["virality_score"] == 0.81
