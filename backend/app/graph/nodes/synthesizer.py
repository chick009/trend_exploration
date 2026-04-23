from __future__ import annotations

from collections import defaultdict
import json
from typing import Any

from app.graph import llm as graph_llm
from app.graph.schemas import SynthesizerVerdictBatch
from app.graph.state import TrendDiscoveryState
from app.graph.tools import make_tool_invocation, now_iso


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


def _normalize_reason_sentence(text: str) -> str:
    normalized = " ".join(str(text).split()).strip()
    if not normalized:
        return ""
    if normalized[-1] not in ".!?":
        normalized += "."
    return normalized


def _resolve_viral_reasons(candidate: dict[str, Any], verdict: dict[str, Any]) -> list[str]:
    normalized: list[str] = []
    for reason in verdict.get("viral_reasons", []):
        cleaned = _normalize_reason_sentence(reason)
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
        if len(normalized) >= 3:
            break
    if normalized:
        return normalized

    fallback_reason = candidate.get("viral_reasoning") or candidate.get("data_pattern")
    cleaned_fallback = _normalize_reason_sentence(fallback_reason or "")
    if cleaned_fallback:
        return [cleaned_fallback]
    return ["The tracked evidence is aligning strongly enough to suggest this is more than isolated noise."]


def _invoke_verdicts(candidates: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], graph_llm.LlmTrace | None]:
    if not candidates:
        return {}, None
    payload = [
        {
            "canonical_term": candidate["canonical_term"],
            "trend_statement": candidate.get("trend_statement", ""),
            "markets": candidate.get("markets", [candidate.get("market")]),
            "virality_score": candidate["virality_score"],
            "confidence_tier": candidate["confidence_tier"],
            "data_pattern": candidate.get("data_pattern"),
            "viral_reasoning": candidate.get("viral_reasoning"),
            "reasoning_blocks": candidate.get("reasoning_blocks", []),
            "social_post_count": candidate.get("social_post_count", 0),
            "avg_engagement": candidate.get("avg_engagement", 0.0),
            "avg_signal_strength": candidate.get("avg_signal_strength", 0.0),
            "avg_novelty": candidate.get("avg_novelty", 0.0),
            "avg_consumer_intent": candidate.get("avg_consumer_intent", 0.0),
            "search_wow_delta": candidate.get("search_wow_delta", 0.0),
            "sales_velocity": candidate.get("sales_velocity", 0.0),
            "restock_count": candidate.get("restock_count", 0),
            "market_scores": candidate.get("market_scores", {}),
        }
        for candidate in candidates
    ]
    system_prompt = (
        "You are a skeptical senior trend analyst. "
        "Return structured verdicts as JSON only."
    )
    prompt = f"""
Review each candidate trend and decide whether it is a real emerging trend or noise.

For every candidate, weigh these challenges:
1. Is `trend_statement` a genuine behavioral or category shift, or just repackaged baseline hype?
2. Could this be a seasonal / cyclical repeat rather than a new trend?
3. Is the signal driven by one viral post, or by a broad pattern across sources?
4. Do sales and search confirm the social story, or does social lead alone?
5. Is the space truly emerging, or already saturated / mature?

Return ONE verdict per `canonical_term`:
- `status`: "confirmed" | "watch" | "noise". Be strict: mark "noise" when the signal is thin, duplicative, or purely hype.
- `trend_statement`: optional. Provide ONLY if you can sharpen the abstraction. Keep it ONE sentence, general (behavior, routine, aesthetic, benefit). NEVER a product or single brand. Omit/null if the existing statement is already correct.
- `viral_reasons`: 1-3 concise reasons for "why this is viral".
  - Each reason must be exactly one sentence.
  - Each reason must be grounded in the evidence figures or source alignment in the candidate payload.
  - Use concrete evidence such as search delta, post-signal strength, sales velocity, restocks, or cross-market spread.
  - Do not just restate the canonical term or trend label.
- `challenge_notes`: 1-3 short, concrete critiques that reference specific weaknesses in the evidence.
- `hype_only`: true if the signal is purely social without commerce or search backing.
- `seasonal_risk`: true if this is plausibly a recurring seasonal pattern.

Return JSON with a top-level `verdicts` array matching the schema.

Candidates:
{json.dumps(payload, default=str)}
""".strip()
    verdict_batch, trace = graph_llm.invoke_json_response_with_trace(
        SynthesizerVerdictBatch,
        system_prompt=system_prompt,
        user_prompt=prompt,
    )
    return {verdict.canonical_term: verdict.model_dump() for verdict in verdict_batch.verdicts}, trace


def run_evidence_synthesizer(state: TrendDiscoveryState) -> TrendDiscoveryState:
    raw_candidates = state.get("trend_candidates", [])
    if not raw_candidates:
        return {
            "synthesized_trends": [],
            "guardrail_flags": ["No candidates available for synthesis."],
            "execution_log": ["[Synthesizer] no candidates found", "[ConfidenceGate] route=end (no high/medium trends)"],
            "tool_invocations": [],
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
            new_statement = (candidate.get("trend_statement") or "").strip()
            if new_statement:
                existing["trend_statement"] = new_statement
            existing["provisional_virality_score"] = candidate["provisional_virality_score"]
        elif not existing.get("trend_statement") and candidate.get("trend_statement"):
            existing["trend_statement"] = candidate["trend_statement"]

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
        previous = prior_snapshot.get(f"{candidate['market']}:{candidate['canonical_term']}")
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

    tool_invocations: list[dict[str, Any]] = []
    verdict_started_at = now_iso()
    try:
        verdicts, trace = _invoke_verdicts(synthesized)
    except Exception as exc:
        trace = getattr(exc, "trace", None)
        tool_invocations.append(
            make_tool_invocation(
                node="evidence_synthesizer",
                tool="llm.synthesizer",
                tool_kind="llm",
                title="LLM: skeptical verdicts on candidate trends",
                started_at=verdict_started_at,
                completed_at=now_iso(),
                status="error",
                input_summary=f"candidates={len(synthesized)}",
                error=str(exc),
                metadata={
                    "schema": "SynthesizerVerdictBatch",
                    "model": (trace or {}).get("model"),
                    "duration_ms": (trace or {}).get("duration_ms"),
                    "prompt_tokens": (trace or {}).get("prompt_tokens"),
                    "completion_tokens": (trace or {}).get("completion_tokens"),
                    "total_tokens": (trace or {}).get("total_tokens"),
                    "estimated_cost_usd": (trace or {}).get("estimated_cost_usd"),
                },
                system_prompt=(trace or {}).get("system_prompt"),
                user_prompt=(trace or {}).get("user_prompt"),
                response_text=(trace or {}).get("response_text"),
                messages=[
                    {"role": "system", "content": (trace or {}).get("system_prompt", "")},
                    {"role": "user", "content": (trace or {}).get("user_prompt", "")},
                ]
                if trace
                else None,
            )
        )
        raise RuntimeError(f"[Synthesizer] verdict generation failed: {exc!s}") from exc
    tool_invocations.append(
        make_tool_invocation(
            node="evidence_synthesizer",
            tool="llm.synthesizer",
            tool_kind="llm",
            title="LLM: skeptical verdicts on candidate trends",
            started_at=verdict_started_at,
            completed_at=now_iso(),
            status="success",
            input_summary=f"candidates={len(synthesized)}",
            output_summary=f"{len(verdicts)} verdicts returned",
            metadata={
                "schema": "SynthesizerVerdictBatch",
                "model": trace["model"] if trace else None,
                "duration_ms": trace["duration_ms"] if trace else None,
                "prompt_tokens": trace.get("prompt_tokens") if trace else None,
                "completion_tokens": trace.get("completion_tokens") if trace else None,
                "total_tokens": trace.get("total_tokens") if trace else None,
                "estimated_cost_usd": trace.get("estimated_cost_usd") if trace else None,
            },
            system_prompt=trace["system_prompt"] if trace else None,
            user_prompt=trace["user_prompt"] if trace else None,
            response_text=trace["response_text"] if trace else None,
            messages=[
                {"role": "system", "content": trace["system_prompt"]},
                {"role": "user", "content": trace["user_prompt"]},
                {"role": "assistant", "content": trace["response_text"] or ""},
            ]
            if trace
            else None,
        )
    )
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
        sharpened_statement = (verdict.get("trend_statement") or "").strip()
        if sharpened_statement:
            candidate["trend_statement"] = sharpened_statement
        candidate["viral_reasons"] = _resolve_viral_reasons(candidate, verdict)
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
        gate = "[ConfidenceGate] route=formatter (no confirmed trends)"
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
        "tool_invocations": tool_invocations,
    }
