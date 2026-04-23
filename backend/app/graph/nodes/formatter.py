from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.graph.state import TrendDiscoveryState

TREND_SENTENCE_CUES = (
    "consumers",
    "demand",
    "interest",
    "momentum",
    "shift",
    "shifting",
    "rising",
    "growing",
    "seeking",
    "leaning",
    "prioritizing",
    "emerging",
    "accelerating",
    "building",
)


def _trend_stage(score: float) -> str:
    if score >= 0.8:
        return "accelerating"
    if score >= 0.6:
        return "emerging"
    if score >= 0.4:
        return "watch"
    return "early"


def _normalize_sentence(text: str) -> str:
    normalized = " ".join(text.split()).strip()
    if not normalized:
        return ""
    if normalized[-1] not in ".!?":
        normalized += "."
    return normalized


def _looks_like_descriptive_trend(candidate: dict, statement: str) -> bool:
    normalized = _normalize_sentence(statement)
    if not normalized:
        return False
    normalized_core = normalized.rstrip(".!?").strip().lower()
    canonical_term = str(candidate.get("canonical_term") or "").strip().lower()
    if normalized_core == canonical_term:
        return False
    if len(normalized_core.split()) >= 6:
        return True
    return any(cue in normalized_core for cue in TREND_SENTENCE_CUES)


def _fallback_trend_sentence(candidate: dict) -> str:
    market = candidate.get("market")
    market_text = f" in {market}" if market else ""
    category = candidate.get("category")
    category_text = category if category and category != "all" else "beauty"
    term = candidate["canonical_term"]
    entity_type = candidate.get("entity_type")

    if candidate["search_score"] >= candidate["social_score"] and candidate["search_score"] >= candidate["sales_score"]:
        return _normalize_sentence(
            f"Search interest{market_text} is accelerating around {term}, signaling a broader shift in {category_text} demand"
        )
    if candidate["sales_score"] >= candidate["social_score"]:
        return _normalize_sentence(
            f"Purchase momentum{market_text} is building around {term}, suggesting the trend is moving from awareness into conversion"
        )
    if entity_type == "brand":
        return _normalize_sentence(
            f"Consumers{market_text} are responding to {term}-led brand momentum in {category_text}"
        )
    if entity_type == "function":
        return _normalize_sentence(
            f"Consumers{market_text} are leaning further into {term}-oriented {category_text} routines"
        )
    return _normalize_sentence(
        f"Consumers{market_text} are increasingly seeking {term}-led solutions within {category_text}"
    )


def _build_headline(candidate: dict) -> str:
    statement = (candidate.get("trend_statement") or "").strip()
    if _looks_like_descriptive_trend(candidate, statement):
        return _normalize_sentence(statement)
    return _fallback_trend_sentence(candidate)


def _build_viral_reasons(candidate: dict) -> list[str]:
    normalized: list[str] = []
    for reason in candidate.get("viral_reasons", []):
        cleaned = _normalize_sentence(reason)
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
        if len(normalized) >= 3:
            break
    if normalized:
        return normalized
    fallback_reason = candidate.get("viral_reasoning") or candidate.get("data_pattern") or (
        "The tracked evidence is aligning strongly enough to suggest this is more than isolated noise."
    )
    return [_normalize_sentence(fallback_reason)]


def _build_why_viral(candidate: dict, viral_reasons: list[str]) -> str:
    return viral_reasons[0] if viral_reasons else _build_viral_reasons(candidate)[0]


def run_report_formatter(state: TrendDiscoveryState) -> TrendDiscoveryState:
    ranked = []
    watch_list = []
    watch_list_only = state.get("watch_list_only", False)
    for index, candidate in enumerate(state.get("synthesized_trends", []), start=1):
        headline = _build_headline(candidate)
        viral_reasons = _build_viral_reasons(candidate)
        trend = {
            "rank": index,
            "term": candidate["canonical_term"],
            "entity_type": candidate["entity_type"],
            "virality_score": candidate["virality_score"],
            "confidence_tier": candidate["confidence_tier"],
            "trend_statement": headline,
            "headline": headline,
            "why_viral": _build_why_viral(candidate, viral_reasons),
            "viral_reasons": viral_reasons,
            "evidence": {
                "social": (
                    f"{candidate['social_post_count']} post signals; "
                    f"avg trend strength {candidate.get('avg_signal_strength', candidate['avg_engagement']):.2f}"
                ),
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
                    ("Post Signals", candidate["social_score"] > 0),
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
