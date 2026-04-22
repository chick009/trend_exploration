from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.graph.state import TrendDiscoveryState


def _trend_stage(score: float) -> str:
    if score >= 0.8:
        return "accelerating"
    if score >= 0.6:
        return "emerging"
    if score >= 0.4:
        return "watch"
    return "early"


def _build_headline(candidate: dict) -> str:
    statement = (candidate.get("trend_statement") or "").strip()
    if statement:
        return statement
    if candidate["search_score"] >= candidate["social_score"] and candidate["search_score"] >= candidate["sales_score"]:
        return f"Search breakout building around {candidate['canonical_term']}"
    if candidate["sales_score"] >= candidate["social_score"]:
        return f"Sales momentum confirms interest in {candidate['canonical_term']}"
    return f"Social buzz is clustering around {candidate['canonical_term']}"


def _build_why_viral(candidate: dict) -> str:
    primary_reason = candidate.get("viral_reasoning") or candidate.get("data_pattern") or (
        f"{candidate['canonical_term']} is showing aligned movement across the tracked signals."
    )
    if candidate.get("challenge_notes"):
        return f"{primary_reason} Skeptical review notes: {'; '.join(candidate['challenge_notes'][:2])}."
    return primary_reason


def run_report_formatter(state: TrendDiscoveryState) -> TrendDiscoveryState:
    ranked = []
    watch_list = []
    watch_list_only = state.get("watch_list_only", False)
    for index, candidate in enumerate(state.get("synthesized_trends", []), start=1):
        trend = {
            "rank": index,
            "term": candidate["canonical_term"],
            "entity_type": candidate["entity_type"],
            "virality_score": candidate["virality_score"],
            "confidence_tier": candidate["confidence_tier"],
            "trend_statement": (candidate.get("trend_statement") or "").strip(),
            "headline": _build_headline(candidate),
            "why_viral": _build_why_viral(candidate),
            "evidence": {
                "social": f"{candidate['social_post_count']} posts; avg engagement {candidate['avg_engagement']:.2f}",
                "search": f"{candidate['search_wow_delta']:.0%} WoW search delta",
                "sales": f"{candidate['sales_velocity']:.0%} WoW sales velocity; {candidate['restock_count']} restocks",
                "cross_market": (
                    f"Observed across {', '.join(candidate['markets'])}"
                    if candidate["cross_market_score"]
                    else "Single-market signal"
                ),
            },
            "signal_chips": [
                chip
                for chip, enabled in [
                    ("REDNOTE", candidate["social_score"] > 0),
                    ("Google Trends", candidate["search_score"] > 0),
                    ("Sales", candidate["sales_score"] > 0),
                    ("Cross-Market", candidate["cross_market_score"] > 0),
                ]
                if enabled
            ],
            "trend_stage": _trend_stage(candidate["virality_score"]),
            "watch_flag": watch_list_only or candidate.get("status") == "watch" or candidate["confidence_tier"] == "low",
            "positivity_score": candidate.get("avg_positivity_score", 0.0),
            "social_score": candidate["social_score"],
            "search_score": candidate["search_score"],
            "sales_score": candidate["sales_score"],
            "cross_market_score": candidate["cross_market_score"],
            "sources_count": candidate["sources_count"],
            "category": candidate.get("category"),
            "market": candidate["market"],
            "source_batch_ids": candidate["source_batch_ids"],
            "sentiment_score": candidate.get("sentiment_score", 0.0),
            "lens": ", ".join(candidate.get("lenses", [])) or candidate.get("lens"),
            "lifecycle_stage": candidate.get("lifecycle_stage"),
            "self_confidence": candidate.get("self_confidence"),
            "challenge_notes": candidate.get("challenge_notes", []),
        }
        if trend["watch_flag"]:
            watch_list.append(trend)
        else:
            ranked.append(trend)

    formatter_log = f"[Formatter] produced {len(ranked)} ranked trends and {len(watch_list)} watch items"
    prior_trace = list(state.get("execution_log", []))
    report = {
        "report_id": str(uuid4()),
        "generated_at": datetime.utcnow().isoformat(),
        "market": state["market"],
        "category": state["category"],
        "recency_days": state["recency_days"],
        "trends": ranked[:10],
        "watch_list": watch_list[:10],
        "regional_divergences": state.get("formatted_report", {}).get("regional_divergences", []),
        "execution_trace": prior_trace + [formatter_log],
        "guardrail_flags": state.get("guardrail_flags", []),
    }
    return {
        "formatted_report": report,
        "execution_log": [formatter_log],
    }
