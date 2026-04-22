# Trend Discovery — Core Architecture & Solution Design

Multi-agent system that discovers emerging viral trends in the Health & Beauty retail domain and returns transparent justifications for each trend. Built on **LangGraph** with a deterministic SQLite substrate, LLM-based reasoning nodes, and a React UI that exposes the full agent trace.

---

## 1. Problem Framing

A business user (buyer, merchandiser, strategy lead) needs to know:

1. **What is emerging right now** in their chosen market (HK / KR / TW / SG / cross-market) and category (skincare / haircare / makeup / supplements).
2. **Why each item is considered viral** — which sources agree, which numbers support it, and where the evidence is weak.

Three signal families must be fused and kept honest:

| Signal family | Source | What it tells us |
|---|---|---|
| Social | RedNote (TikHub), TikTok Photo, Instagram | Cultural attention, early adoption |
| Search | Google Trends via SerpApi | Intent, breakout velocity |
| Sales | Internal synthetic `sales_data` | Commercial confirmation |

A trend is only meaningful when more than one of these agree and the system can **point at the rows** that back the claim. Everything in the architecture below is ultimately in service of that "show your work" requirement.

---

## 2. Design Principles

These principles drove every boundary in the system. They also shape where LLMs are and are not used.

1. **Deterministic data, LLM reasoning.** All SQL and all scoring math are pure Python. LLM calls are narrow: intent parsing, candidate generation per lens, adversarial verdicts, and narrative formatting. Numbers the user sees are never invented by the model.
2. **Canonicalize early.** Every raw mention (`"niacinamide"`, `"vitamin b3"`, `"烟酰胺"`) is collapsed to a canonical entity in `entity_dictionary` before any agent reasons about it. This kills most "same trend under two names" bugs at the source.
3. **Structured output is mandatory.** Every LLM call returns a Pydantic schema (`QueryIntent`, `LensCandidateBatch`, `SynthesizerVerdictBatch`). No free-form JSON parsing outside of the model → schema round-trip.
4. **Context control through slicing.** An agent only sees the data it needs. The Trend Gen agent only receives rows filtered to its active market and active lens. The Synthesizer only sees scored candidates and divergence. The Formatter only sees synthesized trends plus execution log.
5. **Every conclusion must be traceable.** `source_batch_ids`, per-node `tool_invocations`, and the final `execution_trace` let the UI reconstruct which ingestion batch, which SQL aggregate, which prompt, and which verdict produced each trend card.

---

## 3. Two-Phase Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                 PHASE 1 — DATA PIPELINE (scheduled)          │
│                                                              │
│  SerpApi Google Trends  ──► search_trends                    │
│  TikHub RedNote         ──► social_posts                     │
│  TikTok Photo / IG      ──► social_posts (platform field)    │
│  Synthetic CSV seed     ──► sales_data                       │
│  LLM enrichment pass    ──► post_trend_signals               │
│  Shared reference       ──► entity_dictionary                │
└──────────────────────────────────────────────────────────────┘
                              │ SQLite (trend_mvp.sqlite)
                              ▼
┌──────────────────────────────────────────────────────────────┐
│          PHASE 2 — MULTI-AGENT LANGGRAPH (on-demand)         │
│                                                              │
│  memory_read → intent_parser → sql_dispatcher                │
│                                    │                         │
│                                    ├── Send(HK) ─┐           │
│                                    ├── Send(KR) ─┤           │
│                                    ├── Send(TW) ─┼─► trend_  │
│                                    └── Send(SG) ─┘   gen_    │
│                                                     agent    │
│                                       (fan-in via reducer)   │
│                                                ▼             │
│                                  evidence_synthesizer        │
│                                                │             │
│                              confidence_gate ──┤             │
│                                                ▼             │
│                                            formatter         │
│                                                │             │
│                                           memory_write       │
└──────────────────────────────────────────────────────────────┘
                              ▼
                      trend_exploration table
                              ▼
                React UI (cards + reasoning trace)
```

Phase 1 runs on a schedule (`apscheduler`) and never touches an agent. Phase 2 runs per user click, reads the already-canonicalized SQLite store, and writes a finalized report back.

This split keeps agent latency bounded (no external API calls at query time) and makes Phase 1 independently replayable when a vendor rate-limits or returns garbage.

---

## 4. Phase 1 — Data Ingestion

All ingestion clients live in `backend/app/services/ingestion/` and share three non-negotiable conventions:

1. Every inserted row carries a `source_batch_id` (UUID per run) so Phase 2 can cite the exact batch behind any number.
2. A shared `llm_enrichment` pass scores every social post for relevance, category, sentiment/positivity, and canonical entities. Rows with `relevance_score < 0.4` are filtered out by the SQL dispatcher — this is the first guardrail against off-topic drift.
3. The canonical `entity_dictionary` is the single dictionary used during enrichment, during SQL aggregation, and during candidate generation. There is no second taxonomy anywhere in the system.

Key tables after Phase 1 (see `backend/app/db/migrations/`):

| Table | Who writes | Who reads |
|---|---|---|
| `entity_dictionary` | Seed + LLM enrichment | Everyone |
| `search_trends` | `serpapi_client.py` | `sql_dispatcher` |
| `social_posts` | `rednote_client.py`, `tiktok_photo_client.py`, `instagram_client.py` | `sql_dispatcher` |
| `sales_data` | `sales_seed.py` | `sql_dispatcher` |
| `post_trend_signals` | `llm_enrichment.py` | `sql_dispatcher` |
| `trend_exploration` | `memory_write` | `memory_read`, UI |

---

## 5. Phase 2 — LangGraph Agent Topology

Defined in `backend/app/graph/graph.py`. Seven nodes, two routers.

```
START
  │
  ▼
memory_read ──► intent_parser ──► sql_dispatcher
                                      │
                              route_trend_gen (Send per market)
                                      │
                                      ▼
                           trend_gen_agent  × N markets
                                      │
                         (merge via trend_candidates reducer)
                                      │
                                      ▼
                           evidence_synthesizer
                                      │
                             confidence_gate
                          ┌───────────┼────────────┐
                          ▼           ▼            ▼
                       proceed    low_signal   insufficient
                          │           │            │
                          └─────► formatter ◄──────┘
                                      │
                                      ▼
                               memory_write ──► END
```

### 5.1 Shared State (`TrendDiscoveryState`)

Single `TypedDict` (`backend/app/graph/state.py`) with reducer-aware fields:

- `trend_candidates: Annotated[list[dict], operator.add]` — lets parallel per-market branches concatenate their candidates without write conflicts.
- `execution_log`, `guardrail_flags`, `tool_invocations`, `source_batch_ids` — all `operator.add` reducers so every node can append without reading prior values.
- `prior_snapshot` — snapshot from `trend_exploration` keyed by `"{market}:{term}"`, used for lifecycle staging (emerging → accelerating → peak → declining).

This is the "shared context object" pattern — agents never talk to each other directly, they only update slices of state.

### 5.2 Agents and their responsibilities

| Node | Kind | Primary responsibility |
|---|---|---|
| `memory_read` | Deterministic | Load prior `trend_exploration` rows for this market/category as lifecycle reference |
| `intent_parser` | LLM (optional) | Turn free-form `user_query` + UI filters into a validated `QueryIntent` schema |
| `sql_dispatcher` | Deterministic | Canonicalize, aggregate social / search / sales rows from SQLite |
| `trend_gen_agent` | LLM (fan-out) | One branch per market; applies multiple analytical lenses to propose candidate trends |
| `evidence_synthesizer` | Hybrid | Deterministic scoring + LLM adversarial verdicts |
| `formatter` | Deterministic | Build the UI-ready report payload with evidence strings and signal chips |
| `memory_write` | Deterministic | Persist confirmed trends to `trend_exploration` for the next run's lifecycle comparison |

### 5.3 Why fan-out on market, not on entity

`route_trend_gen` uses `Send("trend_gen_agent", {..., "active_region": m})` per market. Market-level fan-out was chosen over entity-level fan-out because:

- **Cost**: one LLM call per lens per market (~3-5 calls) vs. potentially 20+ calls per entity.
- **Quality**: the model reasons better when it sees a coherent market slice and can compare entities against each other.
- **Parallelism**: LangGraph executes Sends in parallel, so cross-market analysis stays fast.

### 5.4 The lens system (`backend/app/graph/nodes/lenses.py`)

Inside one market branch, the Trend Gen agent runs several **analytical lenses** rather than a single monolithic prompt. Each lens is a (name, allowed data sources, description) triple:

| Lens | Active when | Data slice |
|---|---|---|
| Momentum | Always | social + search |
| Cross-Market Diffusion | `analysis_mode = cross_market` or >1 market | social + search + sales (all markets) |
| Social-Sales Convergence | Always | social + sales |
| Emerging Ingredient | Intent includes `ingredient` or `function` | social + search |
| Brand Breakout | Intent includes `brand` | social + sales |

Each lens produces its own `LensCandidateBatch`. The node then merges duplicate `canonical_term`s across lenses and keeps every `reasoning_block` — so a trend that appeared in three lenses literally has three pieces of reasoning attached to it. This is the transparency substrate the UI uses for the "why is this viral" expandable section.

---

## 6. Guardrails and Context Control

Guardrails sit at six clearly-separated layers. Each one has a single job and can fail loudly.

1. **Ingestion relevance filter.** `relevance_score >= 0.4` in every SQL aggregate (`sql_dispatcher.py`). Anything the enrichment LLM didn't mark relevant never reaches an agent.
2. **Canonicalization guardrail.** The Trend Gen prompt says explicitly: `canonical_term MUST already appear as a canonical_term in the data rows below. Never invent new terms.` Candidates whose `canonical_term` is not in `metrics_lookup` are dropped in `_merge_candidate`. This is the hallucination fence.
3. **Structured output contract.** Every LLM call goes through `invoke_json_response_with_trace(Schema, …)` (`backend/app/graph/llm.py`). If the model replies with something that doesn't validate against the Pydantic schema, the node raises and the UI surfaces the failure — no silent degradation.
4. **Trend-statement rules.** `LensCandidate.trend_statement` is constrained to <=25 words, must describe a consumer behavior or benefit shift, and explicitly may not be a product or single brand name. This stops the "we discovered that Estee Lauder Advanced Night Repair is trending" failure mode.
5. **Adversarial verdict.** The Evidence Synthesizer runs a second LLM pass whose only job is to challenge each candidate on seasonal repeat risk, single-post dominance, hype without sales, and baseline spikes. Its schema is `SynthesizerVerdictBatch` with `status ∈ {confirmed, watch, noise}`. `noise` items are dropped; `hype_only` items are demoted to watch.
6. **Confidence gate.** `confidence_gate` routes the run to `proceed`, `low_signal`, or `insufficient_data`. In `low_signal` the formatter still runs but collapses output into the watch list — the user sees "we didn't find enough confirmed trends" instead of a silent half-answer.

**Context control** is handled by slicing, not by prompting the model to "please ignore irrelevant context":

- `sql_dispatcher` filters by market, category, recency, and entity type before building the JSON the model sees.
- `_build_lens_slice` further restricts rows to the active market (except for Cross-Market Diffusion).
- The Synthesizer's prompt only receives aggregated per-candidate metrics, never raw posts.

This means prompt sizes stay small and deterministic as data grows — adding a new market or another month of ingestion does not inflate the Trend Gen prompt.

---

## 7. Memory

Two memory layers, with different roles:

1. **Run-scoped memory (LangGraph checkpointer).** `MemorySaver()` is attached to the compiled graph. Every node write goes through the checkpointer keyed on `thread_id = run_id`. This powers restartability and streaming progress to the UI but is **process-local**.
2. **Analytical memory (SQLite `trend_exploration`).** Durable. Every finalized run writes its confirmed trends via `persist_trend_report`. The next run's `memory_read` loads them and the Synthesizer uses them in `determine_lifecycle_stage(current_score, previous_score)` to assign `emerging / accelerating / peak / declining / stable`.

The deliberate design choice here is that **LLM outputs do not become memory.** Only the scored, verified, lifecycle-tagged trend row is persisted. If tomorrow we rebuild prompts, the analytical history is still valid.

---

## 8. Message Passing and Tool Invocations

LangGraph's reducer model (`Annotated[..., operator.add]`) is the sole message bus between nodes. There is no direct agent-to-agent function call anywhere in the graph.

Every node also appends **tool invocation records** to `tool_invocations` via `make_tool_invocation(...)`. Each record carries:

- `node`, `tool`, `tool_kind` (`sql` | `llm` | `memory`)
- `started_at`, `completed_at`, `status`
- For SQL: the literal query preview
- For LLM: `system_prompt`, `user_prompt`, `response_text`, `model`, `duration_ms`
- `input_summary`, `output_summary`, `metadata`

These invocations are what the UI's `ToolInvocationTimeline.tsx` and `AgentNodeDrawer.tsx` render. Click any node on the graph panel and you see the exact prompt and exact SQL that produced its output. This is the observability substrate — the same records would be exported to Langfuse in production without changing the node code.

---

## 9. Scoring and Explainability

The `evidence_synthesizer` (`backend/app/graph/nodes/synthesizer.py`) computes a single virality score per trend:

```
virality = 0.35 · social + 0.30 · sales + 0.25 · search + 0.10 · cross_market
```

Weights reflect empirical priors for Health & Beauty — social and sales are the strongest leading indicators; cross-market is a tiebreaker, not a driver. Each sub-score is min-max normalized **within the current run's candidate set**, so the score is always "how does this compare to other candidates we found today" rather than a raw unbounded number.

Confidence tier is a function of **signal breadth**, not just score:

```python
if sources_with_signal >= 3 and virality > 0.65: "high"
elif sources_with_signal >= 2 and virality > 0.40: "medium"
else: "low"
```

This is what forces multi-source agreement into the final rating. A social-only spike with a huge engagement score will still be capped at "low" — and downgraded to `watch` — because only one source fired.

The `formatter` then turns this into UI evidence:

```json
{
  "term": "Tranexamic Acid",
  "virality_score": 0.82,
  "confidence_tier": "high",
  "headline": "Search breakout building around Tranexamic Acid",
  "why_viral": "...concrete data pattern + skeptical review notes...",
  "evidence": {
    "social":       "340 posts; avg engagement 0.09",
    "search":       "34% WoW search delta",
    "sales":        "28% WoW sales velocity; 2 restocks",
    "cross_market": "Observed across HK, KR, TW"
  },
  "signal_chips": ["RedNote", "Google Trends", "Sales", "Cross-Market"],
  "trend_stage": "accelerating",
  "lifecycle_stage": "accelerating",
  "challenge_notes": ["KR search peaked 3 weeks ago — HK may be late-cycle"]
}
```

Every string in `evidence.*` is built from a number that originated in SQL. The model is never asked to invent "340 posts".

---

## 10. UI (React + Vite)

`frontend/src/` — three panels, all consuming the same report payload.

- **`FilterSidebar.tsx`** — market / category / recency pickers and an optional free-form user query. This is what populates `AnalysisRunRequest`.
- **`TrendCard.tsx` + `TrendReportTables.tsx`** — ranked trend cards with virality bar, signal chips, trend-stage pill, and an expandable "why viral" section that renders `why_viral`, per-source `evidence`, `challenge_notes`, and `regional_divergences`.
- **`GraphWorkflowPanel.tsx` + `AgentNodeDrawer.tsx` + `ToolInvocationTimeline.tsx` + `ReasoningTrace.tsx`** — the transparency layer. Renders the LangGraph topology live, shows node status as the run proceeds, and opens a drawer that exposes the literal prompts, SQL, and raw model outputs for any node. `ReasoningTrace.tsx` shows the timestamped `execution_log`.

The user never has to trust the model. They can always click into the node, see the SQL, see the prompt, see the verdict, and reject the conclusion with full context.

---

## 11. Design Decisions and Trade-offs

Where I drew boundaries and why — captured as the questions we actually had to answer while building this.

### What stays deterministic

- **SQL aggregation and normalization.** Pure Python. The moment SQL generation becomes LLM-driven, the system inherits a whole class of bugs (bad joins, missing filters) that are unacceptable when the numbers feed an explainability claim. Deterministic SQL also makes Phase 1 replayable.
- **Score math.** Weights, normalization, confidence tiering, lifecycle staging. These are the numbers the user sees. If we A/B a new weighting, we change a constant and rerun the harness — not a prompt.
- **Canonicalization.** Alias resolution is a dictionary lookup. LLMs enrich the dictionary offline during ingestion, but online lookup is a pure Python `alias_map.get(term.lower())`.

### What LLMs own

- **Intent parsing.** Free-form "show me what's rising in Korean skincare in the last two weeks" → structured `QueryIntent`. This is exactly where LLMs excel — bounded translation with a strict schema on the far side.
- **Lens-based candidate generation.** Turning rows + context into a testable trend hypothesis with a written rationale. The model sees numbers and proposes a story; it does not produce numbers.
- **Adversarial verdicts.** The second LLM pass (`evidence_synthesizer`) exists specifically because the first pass has the well-known bias of over-confirming. Splitting generation and critique into two prompts, each with its own schema, substantially improved the watch-list rate on ambiguous signals in dev.

### Things that were intentionally left out

- **No agent-to-agent chat.** All coordination is through state reducers. Conversational handoffs add non-determinism with no observed benefit on this workload.
- **No re-entrant retry loops across the whole graph.** Retries would hide quality issues. If the Synthesizer returns empty, the confidence gate ends the run with an honest "insufficient data" rather than looping the Trend Gen agent on the same inputs.
- **No fine-tuned models.** Every LLM call is a prompt + schema against a hosted model (`OpenRouter`). Iteration speed mattered more than style polish for a tool whose underlying signal sources change weekly.

### Trade-offs we accepted

- **Slight loss of narrative polish** in exchange for a strict rule that every number traces to a SQL row. The headlines and "why viral" narratives are intentionally compact and data-first.
- **Slight increase in LLM cost** from running multiple lenses per market, in exchange for higher recall of trend types the single-prompt baseline was missing.
- **Process-local graph memory** instead of a distributed checkpoint store. Acceptable because durable memory lives in SQLite; the graph checkpointer is only for run progress streaming.

---

## 12. LLMOps Considerations

What this design makes easy to operate once it's in front of real users.

- **Observability.** Every LLM and SQL call is already recorded as a `ToolInvocation` with prompts, responses, and timings. Exporting these to Langfuse is a single emitter — no changes to node code.
- **Prompt versioning.** Each node's prompt is a string constant inside its node module. A golden-set harness can diff `LensCandidateBatch` outputs across prompt versions because the schema is fixed.
- **Evaluation.** Because the score and the rationale are separated (numbers from SQL, narrative from LLM), offline evaluation can test them independently:
  - Numerical correctness: replay a frozen SQLite snapshot and assert the scores and confidence tiers.
  - Narrative quality: LLM-as-judge on `why_viral` strings against a rubric (grounded / overclaiming / hallucinated number).
- **Cost control.** Model routing is one `openrouter_model` setting; the intent parser could use a cheaper model than the lens generator with a two-line change.
- **Governance.** Raw social text is LLM-enriched offline, and only aggregated counts + canonical entities flow into Phase 2 prompts. PII-bearing raw post text never reaches the trend agents.

---

## 13. Where to Read the Code

| Concern | File |
|---|---|
| Graph topology | `backend/app/graph/graph.py` |
| Shared state | `backend/app/graph/state.py` |
| Schemas | `backend/app/graph/schemas.py` |
| LLM adapter + tracing | `backend/app/graph/llm.py` |
| Intent parsing | `backend/app/graph/nodes/intent_parser.py` |
| SQL dispatch + canonicalization | `backend/app/graph/nodes/sql_dispatcher.py` |
| Lens definitions | `backend/app/graph/nodes/lenses.py` |
| Trend generation | `backend/app/graph/nodes/trend_gen.py` |
| Scoring + adversarial verdict | `backend/app/graph/nodes/synthesizer.py` |
| Report shaping | `backend/app/graph/nodes/formatter.py` |
| Memory read/write | `backend/app/graph/nodes/memory.py` |
| Ingestion clients | `backend/app/services/ingestion/` |
| Frontend trend cards | `frontend/src/components/TrendCard.tsx` |
| Frontend graph panel | `frontend/src/components/GraphWorkflowPanel.tsx` |
