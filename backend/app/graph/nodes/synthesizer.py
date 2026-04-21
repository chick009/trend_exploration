from __future__ import annotations

from collections import defaultdict
import json
from typing import Any

from app.graph import llm as graph_llm
from app.graph.schemas import SynthesizerVerdictBatch
from app.graph.state import TrendDiscoveryState


def normalize_score(value: float, min_value: float, max_value: float) -> float:
    if max_value == min_value:
        return 0.5 if value > 0 else 0.0
    return max(0.0, min(1.0, (value - min_value) / (max_value - min_value)))


def assign_confidence(sources_with_signal: int, virality_score: float) -> str:
    if sources_with_signal >= 3 and virality_score > 0.65:
        return "high"
    if sources_with_signal >= 2 and virality_score > 0.4:
        return "medium"
    return "low"


def determine_lifecycle_stage(current_score: float, previous_score: float | None) -> str:
    if previous_score is None:
        return "accelerating" if current_score >= 0.6 else "emerging"
    if current_score < previous_score - 0.10:
        return "declining"
    if current_score > previous_score + 0.15:
        return "accelerating"
    if current_score > 0.75 and current_score <= previous_score + 0.05:
        return "peak"
    return "stable"


def detect_divergence(candidates: list[dict]) -> list[dict]:
    by_term: dict[str, dict[str, float]] = defaultdict(dict)
    for candidate in candidates:
        by_term[candidate["canonical_term"]][candidate["market"]] = candidate["provisional_virality_score"]
    divergences = []
    for term, market_scores in by_term.items():
        if len(market_scores) < 2:
            continue
        values = list(market_scores.values())
        if max(values) - min(values) > 0.35:
            divergences.append({"term": term, "market_scores": market_scores})
    return divergences


def _signal_count(candidate: dict[str, Any]) -> int:
    return sum(
        [
            1 if candidate.get("social_post_count") or candidate.get("avg_engagement") else 0,
            1 if candidate.get("search_wow_delta") or candidate.get("search_index_value") else 0,
            1 if candidate.get("sales_velocity") or candidate.get("restock_count") else 0,
        ]
    )


def _score_candidate(
    candidate: dict[str, Any],
    *,
    social_range: tuple[float, float],
    search_range: tuple[float, float],
    sales_range: tuple[float, float],
) -> dict[str, float]:
    social_score = normalize_score(candidate.get("avg_engagement", 0.0), social_range[0], social_range[1])
    search_score = normalize_score(candidate.get("search_wow_delta", 0.0), search_range[0], search_range[1])
    sales_score = normalize_score(candidate.get("sales_velocity", 0.0), sales_range[0], sales_range[1])
    cross_score = 1.0 if len(candidate.get("markets", [candidate["market"]])) > 1 else 0.0
    virality_score = round(
        0.35 * social_score + 0.30 * sales_score + 0.25 * search_score + 0.10 * cross_score,
        4,
    )
    return {
        "social_score": round(social_score, 4),
        "search_score": round(search_score, 4),
        "sales_score": round(sales_score, 4),
        "cross_market_score": cross_score,
        "virality_score": virality_score,
    }


def _invoke_verdicts(candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not candidates:
        return {}
    payload = [
        {
            "canonical_term": candidate["canonical_term"],
            "markets": candidate.get("markets", [candidate.get("market")]),
            "virality_score": candidate["virality_score"],
            "confidence_tier": candidate["confidence_tier"],
            "data_pattern": candidate.get("data_pattern"),
            "viral_reasoning": candidate.get("viral_reasoning"),
            "reasoning_blocks": candidate.get("reasoning_blocks", []),
            "social_post_count": candidate.get("social_post_count", 0),
            "avg_engagement": candidate.get("avg_engagement", 0.0),
            "search_wow_delta": candidate.get("search_wow_delta", 0.0),
            "sales_velocity": candidate.get("sales_velocity", 0.0),
            "restock_count": candidate.get("restock_count", 0),
            "market_scores": candidate.get("market_scores", {}),
        }
        for candidate in candidates
    ]
    prompt = f"""
You are a skeptical trend analyst reviewing candidate trends.
For each candidate, challenge it on:
1. Seasonal repeat risk.
2. Whether one post is driving the whole signal.
3. Whether social leads or lags search.
4. Whether there is sales confirmation or only hype.
5. Whether the candidate is truly emerging versus a baseline spike.

Return one verdict per canonical_term with:
- status: confirmed, watch, or noise
- concise challenge_notes
- hype_only true/false
- seasonal_risk true/false

Candidates:
{json.dumps(payload, default=str)}
""".strip()
    verdict_batch = graph_llm.get_chat_model(temperature=0.0).with_structured_output(SynthesizerVerdictBatch).invoke(
        [("system", "Return structured skeptical verdicts only."), ("human", prompt)]
    )
    return {verdict.canonical_term: verdict.model_dump() for verdict in verdict_batch.verdicts}


def run_evidence_synthesizer(state: TrendDiscoveryState) -> TrendDiscoveryState:
    raw_candidates = state.get("trend_candidates", [])
    if not raw_candidates:
        return {
            "synthesized_trends": [],
            "guardrail_flags": ["No candidates available for synthesis."],
            "execution_log": ["[Synthesizer] no candidates found", "[ConfidenceGate] route=end (no high/medium trends)"],
        }

    social_values = [candidate.get("avg_engagement", 0.0) for candidate in raw_candidates]
    search_values = [candidate.get("search_wow_delta", 0.0) for candidate in raw_candidates]
    sales_values = [candidate.get("sales_velocity", 0.0) for candidate in raw_candidates]

    scored_raw: list[dict[str, Any]] = []
    for candidate in raw_candidates:
        provisional_scores = _score_candidate(
            candidate,
            social_range=(min(social_values), max(social_values)),
            search_range=(min(search_values), max(search_values)),
            sales_range=(min(sales_values), max(sales_values)),
        )
        scored_raw.append({**candidate, **provisional_scores, "provisional_virality_score": provisional_scores["virality_score"]})

    merged: dict[str, dict[str, Any]] = {}
    divergences = detect_divergence(scored_raw)
    for candidate in scored_raw:
        term = candidate["canonical_term"]
        existing = merged.get(term)
        if not existing:
            existing = {**candidate}
            existing["markets"] = [candidate["market"]]
            existing["market_scores"] = {candidate["market"]: candidate["provisional_virality_score"]}
            existing["lenses"] = list(candidate.get("lenses", []))
            existing["reasoning_blocks"] = list(candidate.get("reasoning_blocks", []))
            merged[term] = existing
            continue
        for key in ("social_post_count", "restock_count"):
            existing[key] = max(existing.get(key, 0), candidate.get(key, 0))
        for key in ("avg_engagement", "avg_positivity_score", "search_wow_delta", "search_index_value", "sales_velocity"):
            existing[key] = max(existing.get(key, 0.0), candidate.get(key, 0.0))
        existing["source_batch_ids"] = sorted(set(existing["source_batch_ids"]) | set(candidate["source_batch_ids"]))
        existing["markets"] = sorted(set(existing["markets"]) | {candidate["market"]})
        existing["market_scores"][candidate["market"]] = max(
            existing["market_scores"].get(candidate["market"], 0.0),
            candidate["provisional_virality_score"],
        )
        for lens in candidate.get("lenses", []):
            if lens not in existing["lenses"]:
                existing["lenses"].append(lens)
        existing["reasoning_blocks"].extend(candidate.get("reasoning_blocks", []))
        if candidate["provisional_virality_score"] >= existing.get("provisional_virality_score", 0.0):
            for key in (
                "market",
                "lens",
                "data_pattern",
                "viral_reasoning",
                "strongest_signal",
                "weakest_signal",
                "self_confidence",
            ):
                existing[key] = candidate.get(key)
            existing["provisional_virality_score"] = candidate["provisional_virality_score"]

    synthesized = []
    prior_snapshot = state.get("prior_snapshot", {})
    for candidate in merged.values():
        score_payload = _score_candidate(
            candidate,
            social_range=(min(social_values), max(social_values)),
            search_range=(min(search_values), max(search_values)),
            sales_range=(min(sales_values), max(sales_values)),
        )
        virality_score = score_payload["virality_score"]
        confidence_tier = assign_confidence(_signal_count(candidate), virality_score)
        previous = prior_snapshot.get(f"{state['market']}:{candidate['canonical_term']}")
        lifecycle_stage = determine_lifecycle_stage(
            virality_score,
            previous_score=previous.get("virality_score") if previous else None,
        )
        synthesized.append(
            {
                **candidate,
                **score_payload,
                "virality_score": virality_score,
                "confidence_tier": confidence_tier,
                "sentiment_score": round(candidate.get("avg_positivity_score", 0.0), 4),
                "sources_count": _signal_count(candidate),
                "lifecycle_stage": lifecycle_stage,
            }
        )

    verdicts = _invoke_verdicts(synthesized)
    filtered_synthesized = []
    for candidate in synthesized:
        verdict = verdicts.get(candidate["canonical_term"], {})
        final_status = verdict.get("status") or ("confirmed" if candidate["confidence_tier"] != "low" else "watch")
        if final_status != "noise" and candidate["confidence_tier"] == "low":
            final_status = "watch"
        if final_status == "confirmed" and verdict.get("hype_only"):
            final_status = "watch"
        if verdict.get("seasonal_risk") and candidate["confidence_tier"] != "high":
            final_status = "watch"
        candidate["status"] = final_status
        candidate["challenge_notes"] = verdict.get("challenge_notes", [])
        candidate["hype_only"] = verdict.get("hype_only", False)
        candidate["seasonal_risk"] = verdict.get("seasonal_risk", False)
        if final_status != "noise":
            filtered_synthesized.append(candidate)

    synthesized = filtered_synthesized
    synthesized.sort(key=lambda item: item["virality_score"], reverse=True)
    guardrail_flags = []
    confirmed_count = sum(1 for item in synthesized if item["status"] == "confirmed")
    if confirmed_count == 0:
        guardrail_flags.append("No confirmed trends found; returning watch list only.")
    watch_list_only = 0 < confirmed_count < 3
    if watch_list_only:
        guardrail_flags.append("Low-signal run: fewer than 3 confirmed trends; collapsing output into the watch list.")
    if confirmed_count == 0:
        gate = "[ConfidenceGate] route=end (no confirmed trends)"
    elif watch_list_only:
        gate = "[ConfidenceGate] route=formatter (low_signal)"
    else:
        gate = "[ConfidenceGate] route=formatter"
    return {
        "synthesized_trends": synthesized,
        "guardrail_flags": guardrail_flags,
        "execution_log": [f"[Synthesizer] scored {len(synthesized)} trends", gate],
        "formatted_report": {"regional_divergences": divergences},
        "watch_list_only": watch_list_only,
    }
