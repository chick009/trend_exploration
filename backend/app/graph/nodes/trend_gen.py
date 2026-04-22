from __future__ import annotations

import json
from typing import Any

from app.graph import llm as graph_llm
from app.graph.nodes.lenses import LensDefinition, determine_active_lenses
from app.graph.schemas import LensCandidateBatch
from app.graph.state import TrendDiscoveryState
from app.graph.tools import make_tool_invocation, now_iso

CONFIDENCE_PRIORITY = {"low": 0, "medium": 1, "high": 2}


def _term_metrics_lookup(sql_results: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for signal_name, rows in sql_results.items():
        for row in rows:
            canonical_term = row["canonical_term"]
            current = metrics.setdefault(
                canonical_term,
                {
                    "canonical_term": canonical_term,
                    "entity_type": row.get("entity_type", "ingredient"),
                    "category": row.get("category"),
                    "market": row.get("market"),
                    "markets": set(),
                    "social_post_count": 0,
                    "avg_engagement": 0.0,
                    "avg_positivity_score": 0.0,
                    "search_wow_delta": 0.0,
                    "search_index_value": 0.0,
                    "sales_velocity": 0.0,
                    "restock_count": 0,
                    "source_batch_ids": set(),
                },
            )
            current["entity_type"] = row.get("entity_type", current["entity_type"])
            current["category"] = row.get("category", current["category"])
            current["market"] = current.get("market") or row.get("market")
            current["markets"].add(row["market"])
            current["source_batch_ids"].update(row.get("source_batch_ids", []))

            if signal_name == "social":
                current["social_post_count"] = max(current["social_post_count"], row.get("social_post_count", 0))
                current["avg_engagement"] = max(current["avg_engagement"], row.get("avg_engagement", 0.0))
                current["avg_positivity_score"] = max(
                    current["avg_positivity_score"], row.get("avg_positivity_score", 0.0)
                )
            elif signal_name == "search":
                current["search_wow_delta"] = max(current["search_wow_delta"], row.get("search_wow_delta", 0.0))
                current["search_index_value"] = max(current["search_index_value"], row.get("search_index_value", 0.0))
            elif signal_name == "sales":
                current["sales_velocity"] = max(current["sales_velocity"], row.get("sales_velocity", 0.0))
                current["restock_count"] = max(current["restock_count"], row.get("restock_count", 0))

    finalized: dict[str, dict[str, Any]] = {}
    for term, values in metrics.items():
        values["markets"] = sorted(values["markets"])
        values["source_batch_ids"] = sorted(values["source_batch_ids"])
        values["sources_with_signal"] = sum(
            [
                1 if values["social_post_count"] or values["avg_engagement"] else 0,
                1 if values["search_wow_delta"] or values["search_index_value"] else 0,
                1 if values["sales_velocity"] or values["restock_count"] else 0,
            ]
        )
        finalized[term] = values
    return finalized


def _build_lens_slice(
    sql_results: dict[str, list[dict[str, Any]]],
    *,
    active_region: str,
    lens: LensDefinition,
) -> dict[str, list[dict[str, Any]]]:
    data_slice: dict[str, list[dict[str, Any]]] = {}
    include_all_markets = lens.name == "Cross-Market Diffusion"
    for data_key in lens.data_keys:
        rows = sql_results.get(data_key, [])
        if include_all_markets:
            data_slice[data_key] = rows
        else:
            data_slice[data_key] = [row for row in rows if row.get("market") == active_region]
    return data_slice


def _invoke_lens(
    *,
    lens: LensDefinition,
    active_region: str,
    intent: dict,
    data_slice: dict[str, list[dict[str, Any]]],
) -> tuple[LensCandidateBatch, graph_llm.LlmTrace]:
    system_prompt = (
        "You are a senior beauty-trend strategist. "
        "Return structured trend candidates as JSON only."
    )
    prompt = f"""
You are analyzing beauty signals for the {active_region} market through the "{lens.name}" lens.
Lens focus: {lens.description}

Propose at most 5 candidate trends. Fewer is better when signals are thin.

For EACH candidate, fill the schema with:
1. `canonical_term` — MUST already appear as a `canonical_term` in the data rows below. Never invent new terms.
2. `trend_statement` — ONE sentence (<= 25 words) that abstracts the signal into a general consumer or category trend.
   - Describe a behavior, routine, concern, aesthetic, or benefit shift that the data points to.
   - Phrase it as a trend, e.g. "Consumers in {active_region} are shifting to X because Y", "Demand for X is rising as Y", "X is emerging as a new approach to Y".
   - NEVER name a product, SKU, or single brand as the trend. You may reference an ingredient, function, category, or behavior.
   - It should be understandable without knowing the canonical_term.
3. `data_pattern` — cite concrete numbers from the rows (engagement, WoW delta, sales velocity, post counts, markets observed).
4. `viral_reasoning` — explain why these numbers look like a real trend instead of noise, a one-off spike, or a seasonal echo.
5. `strongest_signal` / `weakest_signal` — where the evidence is strongest and weakest (social, search, sales, or cross_market).
6. `self_confidence` — "high", "medium", or "low" based on evidence strength and breadth.

Hard rules:
- Do not output two candidates that describe essentially the same trend under different terms.
- Do not restate the canonical_term as the trend statement.
- Return JSON with a top-level `candidates` array that matches the schema exactly.

Intent:
{json.dumps(intent, default=str)}

Data rows (already filtered to this lens and market):
{json.dumps(data_slice, default=str)}
""".strip()
    return graph_llm.invoke_json_response_with_trace(
        LensCandidateBatch,
        system_prompt=system_prompt,
        user_prompt=prompt,
    )


def _merge_candidate(
    *,
    current: dict[str, Any] | None,
    metrics: dict[str, Any],
    lens_name: str,
    llm_candidate: dict[str, Any],
    active_region: str,
) -> dict[str, Any]:
    reasoning_block = {
        "lens": lens_name,
        "trend_statement": llm_candidate.get("trend_statement", ""),
        "data_pattern": llm_candidate["data_pattern"],
        "viral_reasoning": llm_candidate["viral_reasoning"],
        "strongest_signal": llm_candidate["strongest_signal"],
        "weakest_signal": llm_candidate["weakest_signal"],
        "self_confidence": llm_candidate["self_confidence"],
    }
    if current is None:
        merged = {
            **metrics,
            "market": active_region,
            "lens": lens_name,
            "lenses": [lens_name],
            "trend_statement": llm_candidate.get("trend_statement", ""),
            "data_pattern": llm_candidate["data_pattern"],
            "viral_reasoning": llm_candidate["viral_reasoning"],
            "strongest_signal": llm_candidate["strongest_signal"],
            "weakest_signal": llm_candidate["weakest_signal"],
            "self_confidence": llm_candidate["self_confidence"],
            "reasoning_blocks": [reasoning_block],
        }
        return merged

    if lens_name not in current["lenses"]:
        current["lenses"].append(lens_name)
    current["reasoning_blocks"].append(reasoning_block)
    if CONFIDENCE_PRIORITY[llm_candidate["self_confidence"]] > CONFIDENCE_PRIORITY[current["self_confidence"]]:
        current["self_confidence"] = llm_candidate["self_confidence"]
        current["strongest_signal"] = llm_candidate["strongest_signal"]
        current["weakest_signal"] = llm_candidate["weakest_signal"]
        current["data_pattern"] = llm_candidate["data_pattern"]
        current["viral_reasoning"] = llm_candidate["viral_reasoning"]
        current["lens"] = lens_name
        new_statement = llm_candidate.get("trend_statement", "")
        if new_statement:
            current["trend_statement"] = new_statement
    elif not current.get("trend_statement") and llm_candidate.get("trend_statement"):
        current["trend_statement"] = llm_candidate["trend_statement"]
    return current


def run_trend_gen_agent(state: TrendDiscoveryState) -> TrendDiscoveryState:
    active_region = state["active_region"] or state["query_intent"]["markets"][0]
    sql_results = state.get("sql_results", {})
    intent = state["query_intent"]
    active_lenses = determine_active_lenses(intent)

    if not active_lenses:
        return {
            "trend_candidates": [],
            "execution_log": [f"[TrendGen:{active_region}] skipped (no active lenses)"],
        }

    metrics_lookup = _term_metrics_lookup(sql_results)
    merged_candidates: dict[str, dict[str, Any]] = {}
    tool_invocations: list[dict[str, Any]] = []

    for lens in active_lenses:
        data_slice = _build_lens_slice(sql_results, active_region=active_region, lens=lens)
        if not any(data_slice.values()):
            continue
        input_rows = sum(len(rows) for rows in data_slice.values())
        started_at = now_iso()
        try:
            lens_batch, trace = _invoke_lens(lens=lens, active_region=active_region, intent=intent, data_slice=data_slice)
        except Exception as exc:
            trace = getattr(exc, "trace", None)
            tool_invocations.append(
                make_tool_invocation(
                    node=f"trend_gen_agent:{active_region}",
                    tool="llm.trend_gen",
                    tool_kind="llm",
                    title=f"LLM: generate trend candidates ({lens.name} · {active_region})",
                    started_at=started_at,
                    completed_at=now_iso(),
                    status="error",
                    input_summary=f"lens={lens.name} market={active_region} input_rows={input_rows}",
                    error=str(exc),
                    metadata={"lens": lens.name, "market": active_region},
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
            raise RuntimeError(
                f"[TrendGen:{active_region}] lens {lens.name!r} failed: {exc!s}"
            ) from exc
        tool_invocations.append(
            make_tool_invocation(
                node=f"trend_gen_agent:{active_region}",
                tool="llm.trend_gen",
                tool_kind="llm",
                title=f"LLM: generate trend candidates ({lens.name} · {active_region})",
                started_at=started_at,
                completed_at=now_iso(),
                status="success",
                input_summary=f"lens={lens.name} market={active_region} input_rows={input_rows}",
                output_summary=f"{len(lens_batch.candidates)} candidates proposed",
                metadata={
                    "lens": lens.name,
                    "market": active_region,
                    "candidate_count": len(lens_batch.candidates),
                    "schema": "LensCandidateBatch",
                    "model": trace["model"],
                    "duration_ms": trace["duration_ms"],
                },
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
        for llm_candidate in lens_batch.candidates:
            term = llm_candidate.canonical_term
            metrics = metrics_lookup.get(term)
            if metrics is None:
                continue
            merged_candidates[term] = _merge_candidate(
                current=merged_candidates.get(term),
                metrics=metrics,
                lens_name=lens.name,
                llm_candidate=llm_candidate.model_dump(),
                active_region=active_region,
            )

    results = sorted(merged_candidates.values(), key=lambda item: item["canonical_term"])
    return {
        "trend_candidates": results,
        "execution_log": [f"[TrendGen:{active_region}] generated {len(results)} candidates across {len(active_lenses)} lenses"],
        "source_batch_ids": sorted({batch for candidate in results for batch in candidate["source_batch_ids"]}),
        "tool_invocations": tool_invocations,
    }
