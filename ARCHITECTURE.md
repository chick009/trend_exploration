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
│  SerpApi Google Trends  ──► search_trends (+ keyword LLM enrich) │
│  TikTok Photo (TikHub)  ──► tiktok_photo_posts               │
│  Instagram (TikHub)   ──► instagram_posts                  │
│  (optional RedNote)     ──► social_posts                     │
│  Synthetic sales seed   ──► sales_data                     │
│  Post LLM/heuristic score ──► post_trend_signals           │
│  Shared reference       ──► entity_dictionary                │
└──────────────────────────────────────────────────────────────┘
                              │ SQLite (trend_mvp.sqlite)
                              ▼
┌──────────────────────────────────────────────────────────────┐
│     PHASE 2 — ANALYSIS RUN (on-demand, two-stage)           │
│                                                              │
│  A) AnalysisService orchestration (before LangGraph.stream)   │
│     intent_parser.build_intent_state_update → load_sql_results │
│     (social from post_trend_signals, search, sales, memory)   │
│     → builds initial_state: query_intent, sql_results,        │
│       prior_snapshot, source_batch_ids, tool_invocations      │
│                                                              │
│  B) LangGraph (backend/app/graph/graph.py) — 4 nodes          │
│     START ──► route_trend_gen (Send per market)              │
│                    │                                         │
│                    ▼                                         │
│         trend_gen_agent × N  ──►  evidence_synthesizer       │
│                    │              confidence_gate            │
│                    │              (all routes → formatter)   │
│                    ▼                                         │
│              formatter ──► memory_write ──► END              │
└──────────────────────────────────────────────────────────────┘
                              ▼
                      trend_exploration table
                              ▼
                React UI (cards + reasoning trace + llm_ops)
```

Phase 1 runs on a schedule (`apscheduler`) and never touches an agent. Phase 2 runs per user click: **`AnalysisService.iter_run_events`** (`backend/app/services/analysis_service.py`) first resolves intent and loads all SQLite slices (including prior-trend **memory** rows), then streams the compiled LangGraph so LLM-heavy work stays inside the graph while I/O and deterministic SQL stay in one place before the first graph step.

This split keeps agent latency bounded (no external API calls at query time) and makes Phase 1 independently replayable when a vendor rate-limits or returns garbage.

---

## 4. Phase 1 — Data Ingestion

All ingestion clients live in `backend/app/services/ingestion/` and share three non-negotiable conventions:

1. Every inserted row carries a `source_batch_id` (UUID per run) so Phase 2 can cite the exact batch behind any number.
2. **TikTok** and **Instagram** rows fetched in an ingestion run are scored by `LLMEnrichmentService` into **`post_trend_signals`** (trend strength, novelty, consumer intent, category, region, rationale). That table is what **`load_sql_results`** aggregates as the **social** slice for analysis. Optional **keyword-level** enrichment also classifies Google Trends keywords before they land in **`search_trends`**. Downstream SQL still applies **`relevance_score >= 0.4`** where applicable so weak matches drop out early.
3. The canonical `entity_dictionary` is the single dictionary used during enrichment, during SQL aggregation, and during candidate generation. There is no second taxonomy anywhere in the system.

Key tables after Phase 1 (see `backend/app/db/migrations/`):

| Table | Who writes | Who reads |
|---|---|---|
| `entity_dictionary` | `seed_reference_data` / reference seeds | Ingestion heuristics, `load_sql_results` |
| `search_trends` | `SerpApiClient` + per-keyword `enrich_keyword` | `load_sql_results` |
| `tiktok_photo_posts` | `run_tiktok_photo_fetch_clean_save` | `fetch_posts_for_scoring` → signals |
| `instagram_posts` | `run_instagram_fetch_clean_save` | `fetch_posts_for_scoring` → signals |
| `social_posts` | `rednote_client.py` (separate / optional pipelines) | Legacy or other flows |
| `post_trend_signals` | `LLMEnrichmentService.score_post` after fetch | `load_sql_results` (social slice) |
| `sales_data` | `SalesSeedService` → `seed_sales_data` | `load_sql_results` |
| `trend_exploration` | `memory_write` (graph) | `load_sql_results` (memory slice), UI |

### Ingestion entrypoint (`IngestionService`)

Scheduled or on-demand runs are implemented in **`backend/app/services/ingestion/ingestion_service.py`**:

1. **`create_run`** allocates a `run_id` and a **`batch_id`** (`batch-{uuid}`) shared by every row written in that run.
2. **`run`** updates run status, builds **recency support** metadata (`source_capabilities.build_recency_support`) so the UI knows which sources honor the requested window, then executes selected **`request.sources`** in order: **`google_trends`**, **`sales`**, **`tiktok`**, **`instagram`**.
3. If **TikTok** and/or **Instagram** ran, a **second phase** loads all new posts for this `batch_id` via **`fetch_posts_for_scoring`**, calls **`score_post`** on each caption/text, and **`upsert_post_trend_signals`** writes one signal row per post.
4. The run completes with **stats** (row counts, limits, `batch_id`) and **guardrail_flags** (e.g. missing API keys, empty hashtag results, fetch failures).

### Google Trends — extraction

**Module:** `backend/app/services/ingestion/serpapi_client.py` — **`SerpApiClient.fetch_trends`**.

| Step | What happens |
|---|---|
| **Config** | Uses market → **geo** and **tz** (e.g. HK → `-480`), `date` from `recent_days` (`now 7-d`, `today 1-m`, or a custom range), Google Trends **category `44`** (Beauty & Fitness), **`data_type=TIMESERIES`**. |
| **Batching** | Seed keywords from the ingestion request are processed in **chunks of up to five** queries per SerpApi call (`q` comma-separated). |
| **HTTP** | `httpx` GET `https://serpapi.com/search` with retries and timeouts; non-success metadata raises. |
| **Normalization** | For each term, **`interest_over_time.timeline_data`** is parsed into a numeric series; **`compute_wow_delta`** compares the last 7 days vs the prior 7; **`is_breakout`** is set when WoW exceeds a threshold (live data: `0.25`; synthetic path uses `0.2`). |
| **Persistence** | Each row is passed through **`LLMEnrichmentService.enrich_keyword`** (same JSON schema as social text: `llm_category`, `relevance_score`, entities, etc.), merged with **`source_batch_id`**, and **`upsert_search_trend`** writes **`search_trends`**. |

**Synthetic fallback:** If **`SERPAPI_API_KEY`** is unset, **`_synthetic_trends`** generates plausible index series with a **deterministic RNG seed** per `(market, category, term, recent_days)`, bumps momentum for a few hard-coded demo terms per region, and tags `source: synthetic_serpapi`. Downstream code treats these like real rows for demos and tests.

### Synthetic sales data — extraction

**Module:** `backend/app/services/ingestion/sales_seed.py` — **`SalesSeedService.refresh`** calls **`seed_sales_data`** in **`backend/app/db/bootstrap.py`**.

| Step | What happens |
|---|---|
| **Seeds** | **`SALES_SKU_SEEDS`** (from `app/seed/reference_data.py`) define SKU, product name, brand, **`ingredient_tags`** (JSON list), and **category**. |
| **Simulation** | For each SKU × **region** (`HK`, `KR`, `TW`, `SG`) × **week** (rolling window of recent Mondays), a **pseudo-random walk** (`random.Random(11)`) produces **units_sold**, **revenue**, and **`wow_velocity`** week-over-week. Demo bias adds extra growth for a few ingredient/region pairs (e.g. tranexamic acid in HK). |
| **`is_restocking`** | Set when WoW velocity exceeds a threshold (`0.25`) to mimic restock spikes. |
| **Persistence** | **`INSERT OR REPLACE`** into **`sales_data`** with a fixed provenance tag **`source_batch_id = synthetic_sales_seed`**. The service reports a fixed **`rows_seeded`** count (`216`) for observability. |

This is **fully synthetic** — there is no external retail API. It exists so the analysis graph can demonstrate **sales–social convergence** without customer data.

### TikTok (photo) — extraction

**Module:** `backend/app/services/ingestion/tiktok_photo_client.py`.

| Step | What happens |
|---|---|
| **API** | **TikHub** `GET https://api.tikhub.io/api/v1/tiktok/web/fetch_search_photo` with **`Authorization: Bearer {TIKHUB_API_KEY}`**, query params **`keyword`**, **`count`** (capped by `MAX_SOCIAL_POSTS_PER_KEYWORD` and request limits), optional **`cookie`**. |
| **Resilience** | Retries with backoff on transient failures; 400 responses are logged and may surface to the user via guardrail flags. |
| **Parse** | **`extract_tiktok_photo_posts`** walks `data.item_list` and maps **id**, **desc**, author stats, **likes / comments / shares / plays / collects**, ad flag, share URL, etc. |
| **Clean & save** | **`cleaned_posts_to_db_rows`** normalizes into DB columns; **`upsert_tiktok_photo_posts`** writes **`tiktok_photo_posts`** with **`search_keyword`** and **`source_batch_id`**. |

### Instagram — extraction

**Module:** `backend/app/services/ingestion/instagram_client.py`.

| Step | What happens |
|---|---|
| **API** | **TikHub** `GET .../api/v1/instagram/v2/fetch_hashtag_posts` with **`keyword`** (hashtag-style) and **`feed_type`** (e.g. `top` from `IngestionRunRequest.instagram_feed_type`). |
| **Hashtag resolution** | **`build_hashtag_keyword_candidates`** tries the raw keyword and fallbacks (stripped `#`, decomposed phrases) because the endpoint is hashtag-oriented — phrase-like seeds may return zero posts until a candidate matches. |
| **Parse** | **`extract_instagram_posts`** maps **post_id**, **caption**, **hashtags**, **mentions**, **likes / comments / views**, location, **`taken_at`**, etc. |
| **Clean & save** | **`cleaned_posts_to_db_rows`** → **`upsert_instagram_posts`** into **`instagram_posts`** with **`source_batch_id`**. |

### Data processing after social fetch

**Goal:** Turn variable-length captions into **structured, comparable signals** stored in **`post_trend_signals`**, keyed by **`(source_table, source_row_id, source_batch_id)`** so Phase 2 can aggregate by keyword and market without re-reading raw vendor JSON.

**Module:** `backend/app/services/ingestion/llm_enrichment.py` — **`LLMEnrichmentService`**.

| Stage | Function | Behavior |
|---|---|---|
| **Selection** | `fetch_posts_for_scoring(batch_id)` (`repository.py`) | UNION of **new** `instagram_posts` and `tiktok_photo_posts` rows for this batch that **do not yet** have a matching **`post_trend_signals`** row. |
| **Input text** | Ingestion loop | Prefers post **caption / description**; falls back to **search_keyword** or **source_row_id** if text is empty. |
| **Scoring** | **`score_post`** | If **`OPENROUTER_API_KEY`** is set, **`_openrouter_score_post`** asks the model for strict JSON: **`region`**, **`category`**, **`trend_strength`**, **`novelty`**, **`consumer_intent`**, **`rationale`**. On failure or missing key, **`_heuristic_score_post`** derives the same fields from **lexicons** (trend / novelty / intent / sentiment terms) plus **`entity_dictionary`** mention counts. |
| **Write** | **`upsert_post_trend_signals`** | One row per post with **`processing_model`**, **`processed_at`**, and text snippet cap for storage. |

**Keyword enrichment (Google Trends rows):** **`enrich_keyword`** delegates to **`enrich_text`** with the same LLM-vs-heuristic split: OpenRouter returns **`llm_category`**, **`llm_subcategory`**, **`positivity_score`**, **`relevance_score`**, **`llm_entities`**, **`llm_summary`**; otherwise **`_heuristic_enrich_text`** uses dictionary and keyword rules. Ingestion merges that onto each **`search_trends`** row before upsert.

### End-to-end flow (one ingestion run)

```
IngestionRunRequest (market, category, recent_days, sources[], target_keywords[])
        │
        ├─ google_trends ──► SerpApiClient.fetch_trends ──► enrich_keyword ──► search_trends
        │
        ├─ sales ──────────► SalesSeedService.refresh ──► seed_sales_data ──► sales_data
        │
        ├─ tiktok ─────────► run_tiktok_photo_fetch_clean_save ──► tiktok_photo_posts
        │
        └─ instagram ──────► run_instagram_fetch_clean_save ──► instagram_posts
                                    │
                                    ▼
                    fetch_posts_for_scoring(batch_id)
                                    │
                                    ▼
                    score_post (LLM or heuristic) × N
                                    │
                                    ▼
                         post_trend_signals
```

---


## 5. Phase 2 — Orchestration + LangGraph Topology

**Orchestration** lives in `AnalysisService.iter_run_events` (`backend/app/services/analysis_service.py`). It runs **`build_intent_state_update`** (same logic as `intent_parser` node module) and **`load_sql_results`** before `graph.stream(...)`, merges their `tool_invocations` and `execution_log` into the initial state, and persists incremental **`node_outputs`** for the UI graph panel.

**LangGraph** is defined in `backend/app/graph/graph.py`: **four nodes**, two routers (`START` → `route_trend_gen`, then `confidence_gate`).

```
START
  │
  ▼                    (initial_state built by AnalysisService:
route_trend_gen         query_intent, sql_results, prior_snapshot, …)
  │
  ├── Send(trend_gen_agent, HK)
  ├── Send(trend_gen_agent, KR)     … parallel per market …
  └── Send(trend_gen_agent, SG)
          │
          ▼  (fan-in: trend_candidates reducer)
  evidence_synthesizer
          │
   confidence_gate ──► proceed | low_signal | insufficient_data
          │                    (all three → formatter)
          ▼
      formatter
          │
          ▼
    memory_write ──► END
```

### 5.1 Shared State (`TrendDiscoveryState`)

Single `TypedDict` (`backend/app/graph/state.py`) with reducer-aware fields:

- `trend_candidates: Annotated[list[dict], operator.add]` — lets parallel per-market branches concatenate their candidates without write conflicts.
- `execution_log`, `guardrail_flags`, `tool_invocations`, `source_batch_ids` — all `operator.add` reducers so every node can append without reading prior values.
- `prior_snapshot` — loaded **before** the graph runs, inside `load_sql_results` via `get_prior_trend_snapshots`, and passed on `initial_state` for lifecycle staging in the synthesizer.

This is the "shared context object" pattern — agents never talk to each other directly, they only update slices of state.

### 5.2 Responsibilities: service vs graph

| Layer | Component | Kind | Primary responsibility |
|---|---|---|---|
| Service | `build_intent_state_update` | LLM (optional) | Turn free-form `user_query` + UI filters into `QueryIntent` + `query_params` |
| Service | `load_sql_results` | Deterministic | Canonicalize and aggregate **social** (from `post_trend_signals`), **search**, **sales**, and **memory** (prior `trend_exploration` rows); set `prior_snapshot` |
| Graph | `trend_gen_agent` | LLM (fan-out) | One branch per market; analytical lenses; structured `LensCandidateBatch` |
| Graph | `evidence_synthesizer` | Hybrid | Scoring + adversarial `SynthesizerVerdictBatch` |
| Graph | `formatter` | Deterministic | UI-ready `TrendReport` fields (including downstream `llm_ops` merge on the service) |
| Graph | `memory_write` | Deterministic | Persist confirmed trends to `trend_exploration` |

`run_sql_dispatcher` in `sql_dispatcher.py` remains a thin wrapper around `load_sql_results` for tests or future graph re-integration; production runs invoke **`load_sql_results` directly from `AnalysisService`**.

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

### 5.5 Per-component contracts

Contracts are split between **service-stage** helpers (`intent_parser` module, `load_sql_results`) and **LangGraph nodes**. System-wide guardrails are summarized in §6.

#### 5.5.1 Service: prior snapshot + memory slice (`load_sql_results`)

| | |
|---|---|
| **Responsibility** | Inside `load_sql_results`, the **`memory`** slice loads recent `trend_exploration` rows via `get_prior_trend_snapshots` and builds `prior_snapshot` for lifecycle comparison. The same function also populates `sql_results["memory"]` with those rows for transparency in `node_outputs.backend_preload`. |
| **Invoked by** | `AnalysisService.iter_run_events` before `graph.stream` |
| **Writes** | Returned tuple: `sql_results`, `prior_snapshot`, `source_batch_ids`, `query_plan`, `tool_invocations` merged into `initial_state` |
| **Context control** | SQL-only; no LLM. Markets and category scoped consistently with the rest of the run. |
| **Guardrails** | Missing prior rows degrade gracefully in `determine_lifecycle_stage`. Each query emits a `tool_invocation` with SQL preview (`sql.memory`). |

#### 5.5.2 Service: `build_intent_state_update` (intent module)

| | |
|---|---|
| **Responsibility** | Turn the optional `user_query` plus UI fields into a strict `QueryIntent` (markets, category, recency, entity types, analysis mode, optional `focus_hint`). Build a `query_params` preview (planned signal slices and rendered SQL previews) for transparency. |
| **Invoked by** | `AnalysisService.iter_run_events` as the first step of a run |
| **Writes** | `query_intent`, `query_params`, optional `tool_invocations`, `execution_log` merged into state before SQL load |
| **Context control** | The LLM call is skipped entirely when `user_query` is empty; deterministic defaults are used. When the LLM runs it sees only: the allowed enums, the four UI constraints, the data-source schema reference, and the user query. No business data, no prior snapshot. |
| **Guardrails** | (1) UI constraints OVERRIDE the model — `_merge_intent` re-clamps `markets`, `category`, and `analysis_mode` after the call. (2) `markets ⊆ {HK, KR, TW, SG}`, `category ∈ SUPPORTED_CATEGORIES`, `entity_types ⊆ SUPPORTED_ENTITY_TYPES`, `recency_days ∈ [1, 30]` are enforced both in the prompt and by the `QueryIntent` Pydantic schema. (3) Unknown markets fall back to a deterministic intent and a `guardrail_flag` is appended. (4) JSON validation failures raise via `JsonResponseError` with the full prompt/response trace attached. |

#### 5.5.3 Service: `load_sql_results` — deterministic data layer

| | |
|---|---|
| **Responsibility** | Run all reads needed for the run: **`social`** aggregates LLM-scored **`post_trend_signals`** (keyword / strength / novelty / intent), **`search`** and **`sales`** as before, plus **`memory`** (prior trends). Canonicalize through `entity_dictionary`, aggregate per `(market, canonical_term)` where applicable, emit `source_batch_ids`. This is the *only* path that reads these operational tables during an analysis run. |
| **Invoked by** | `AnalysisService.iter_run_events` after intent; `run_sql_dispatcher` wraps the same function for tests |
| **Returns** | `sql_results = {social, search, sales, memory}`, `prior_snapshot`, consolidated `source_batch_ids`, `query_plan`, `tool_invocations` |
| **Context control** | `select_query_plan` currently returns all four slices `(social, search, sales, memory)` for every run. Social aggregation uses `post_trend_signals` (not raw `social_posts` in the hot path). No LLM inside this function. |
| **Guardrails** | (1) Search rows still respect `relevance_score >= 0.4` where applicable in repository queries. (2) Alias resolution via `_resolve_entity` collapses synonyms. (3) Entity-type allowlist (`_should_include_entity`) drops entity types the user did not ask for. (4) Each signal slice records its SQL preview in a `tool_invocation`. (5) Failures bubble up as exceptions with the failing SQL recorded. |

#### 5.5.4 `trend_gen_agent` — per-market, per-lens hypothesis generator

| | |
|---|---|
| **Responsibility** | For one `active_region`, run every active analytical lens and propose a small set of candidate trends. Each candidate must abstract the signal into a one-sentence general trend (`trend_statement`) and cite concrete numbers (`data_pattern`). Merge duplicate `canonical_term`s across lenses, preserving every `reasoning_block`. |
| **Reads from state** | `active_region` (injected by `Send`), `query_intent`, `sql_results` |
| **Writes to state** | `trend_candidates` (appended via reducer), `source_batch_ids`, `tool_invocations`, `execution_log` |
| **Context control** | `_build_lens_slice` filters `sql_results` to (a) only the data sources the active lens declares and (b) only the active market — except for `Cross-Market Diffusion`, which intentionally sees all markets. The model sees the lens definition, the intent, and the filtered slice — never the raw post text, never other markets' slices, never prior snapshots. |
| **Guardrails** | (1) `canonical_term MUST already appear in the data rows` — enforced in the prompt and re-checked by `metrics_lookup` (unknown terms are dropped in `_merge_candidate`, which is the hallucination fence). (2) `trend_statement` rules: ONE sentence, ≤25 words, must describe a behavior/aesthetic/benefit shift, and must NOT be a product, SKU, or single brand name. (3) Hard cap of 5 candidates per lens. (4) `LensCandidateBatch` Pydantic schema validates every field; structured-output failures raise. (5) When a lens slice is empty the lens is silently skipped — no fabricated candidates. (6) Per-lens `tool_invocation` records the prompt, response, model, and duration. |

#### 5.5.5 `evidence_synthesizer` — scorer + adversarial reviewer

| | |
|---|---|
| **Responsibility** | Two-step process: (a) **deterministic** — normalize signals within the run, compute `virality_score = 0.35·social + 0.30·sales + 0.25·search + 0.10·cross_market`, assign `confidence_tier` based on signal breadth, derive `lifecycle_stage` from `prior_snapshot`, detect cross-market divergences. (b) **LLM** — issue a skeptical `SynthesizerVerdictBatch` per candidate that may sharpen `trend_statement` and tags `status ∈ {confirmed, watch, noise}`, plus `hype_only` and `seasonal_risk`. |
| **Reads from state** | `trend_candidates`, `prior_snapshot`, `market` |
| **Writes to state** | `synthesized_trends`, `formatted_report.regional_divergences`, `watch_list_only`, `guardrail_flags`, `tool_invocations`, `execution_log` |
| **Context control** | The LLM only sees aggregated per-candidate metrics (`virality_score`, `confidence_tier`, `markets`, signal totals, reasoning blocks). It does not see raw posts, individual SQL rows, or the full `sql_results` payload. Prompt size is bounded by the candidate count, not by data volume. |
| **Guardrails** | (1) Scoring math is pure Python — the model is never asked to invent a number. (2) Verdict can only set `status` to one of three enum values; a Pydantic schema rejects anything else. (3) Post-LLM enforcement: `confidence_tier == "low"` is auto-demoted from `confirmed` to `watch`; `hype_only` confirmed candidates are demoted to `watch`; `seasonal_risk` candidates that are not `high` confidence are demoted. (4) `noise` candidates are dropped entirely. (5) Optional `trend_statement` from the verdict only overwrites the existing one when non-empty (the abstraction never disappears). (6) **`confidence_gate` always routes to `formatter`** — `insufficient_data` and `low_signal` still produce a report (often empty trends or watch-list collapse) so the UI never dead-ends without a payload. |

#### 5.5.6 `formatter` — UI report shaper

| | |
|---|---|
| **Responsibility** | Build the API/UI payload from `synthesized_trends`: ranked trends, watch list, regional divergences, evidence strings, signal chips, lifecycle stage. Promotes `trend_statement` to `headline` (with a deterministic fallback). |
| **Reads from state** | `synthesized_trends`, `watch_list_only`, `formatted_report.regional_divergences`, `market`, `category`, `recency_days`, `execution_log`, `guardrail_flags` |
| **Writes to state** | `formatted_report` (full UI report), `execution_log` |
| **Context control** | Deterministic pure-Python projection. No LLM call. Each evidence string is built from a number that originated in SQL (`{social_post_count}`, `{search_wow_delta}`, `{sales_velocity}`, `{restock_count}`). |
| **Guardrails** | (1) Hard caps at `trends[:10]` and `watch_list[:10]` so payloads stay bounded. (2) `watch_flag` collapses everything to the watch list when `watch_list_only` is set or `confidence_tier == "low"`. (3) `_build_headline` falls back to a term-based sentence only when the LLM-supplied `trend_statement` is missing — there is always a deterministic backstop. (4) `signal_chips` are gated by per-source scores so the UI can only claim a source contributed when that source actually fired. |

#### 5.5.7 `memory_write` — durable analytical memory

| | |
|---|---|
| **Responsibility** | Persist the **confirmed** (non-watch) trends from this run into `trend_exploration` so the next run's **`load_sql_results` memory slice** has lifecycle reference rows. Skip cleanly when the report is empty or only contains watch items. |
| **Reads from state** | `formatted_report`, `market`, `source_batch_ids` |
| **Writes to state** | `tool_invocations`, `execution_log`, `guardrail_flags` (when the insert is intentionally skipped) |
| **Context control** | Only the *finalized*, scored, verified trend rows are persisted — never raw LLM output, never candidates, never the prompt. This is what makes prompt re-engineering safe: prompts can be rewritten without invalidating analytical history. |
| **Guardrails** | (1) Refuses to write when `report_id` is missing. (2) Refuses to write when there are zero confirmed trends, and emits a `guardrail_flag` so the UI shows that the table was intentionally not touched. (3) Idempotent `INSERT OR REPLACE` keyed on `(report_id, market, canonical_term)` — re-running the same run does not double-insert. (4) Persists the full `report_json` alongside numeric columns so a future analysis can replay the exact card the user saw. |

#### 5.5.8 Routers (`route_trend_gen`, `confidence_gate`)

Routers are not agents but they *are* contracts:

- **`route_trend_gen`** — fans out one `Send("trend_gen_agent", {..., active_region: m})` per market in `query_intent.markets`. Guardrail: if the intent has no markets the run still completes deterministically because `_default_intent` always populates at least one market.
- **`confidence_gate`** — pure function of `synthesized_trends` and `watch_list_only`. Three labels — `proceed`, `low_signal`, `insufficient_data` — all **route to `formatter`** in `graph.py`. The synthesizer sets `watch_list_only` and `guardrail_flags` so the formatter can collapse output appropriately; there is no `END` shortcut after synthesis. No LLM, no hidden retry.

---

## 6. Guardrails and Context Control

Guardrails sit at six clearly-separated layers. Each one has a single job and can fail loudly.

1. **Signal quality filters.** Search breakouts and related paths still enforce `relevance_score >= 0.4` where the repository applies Google Trends filters. Social signals for the graph are aggregated from **`post_trend_signals`** (LLM-scored during ingestion), so off-topic content is reduced before aggregation.
2. **Canonicalization guardrail.** The Trend Gen prompt says explicitly: `canonical_term MUST already appear as a canonical_term in the data rows below. Never invent new terms.` Candidates whose `canonical_term` is not in `metrics_lookup` are dropped in `_merge_candidate`. This is the hallucination fence.
3. **Structured output contract.** Every LLM call goes through `invoke_json_response_with_trace(Schema, …)` (`backend/app/graph/llm.py`). If the model replies with something that doesn't validate against the Pydantic schema, the node raises and the UI surfaces the failure — no silent degradation.
4. **Trend-statement rules.** `LensCandidate.trend_statement` is constrained to <=25 words, must describe a consumer behavior or benefit shift, and explicitly may not be a product or single brand name. This stops the "we discovered that Estee Lauder Advanced Night Repair is trending" failure mode.
5. **Adversarial verdict.** The Evidence Synthesizer runs a second LLM pass whose only job is to challenge each candidate on seasonal repeat risk, single-post dominance, hype without sales, and baseline spikes. Its schema is `SynthesizerVerdictBatch` with `status ∈ {confirmed, watch, noise}`. `noise` items are dropped; `hype_only` items are demoted to watch.
6. **Confidence gate (routing semantics).** `confidence_gate` labels the run as `proceed`, `low_signal`, or `insufficient_data`, but **all three edges go to `formatter`** in the compiled graph. Low-signal and insufficient runs still yield a `formatted_report` (often empty ranked trends, watch list, and `guardrail_flags`) so the API and UI always receive a terminal payload.

**Context control** is handled by slicing, not by prompting the model to "please ignore irrelevant context":

- `load_sql_results` filters by market, category, recency, and entity type before building the JSON the model sees.
- `_build_lens_slice` further restricts rows to the active market (except for Cross-Market Diffusion).
- The Synthesizer's prompt only receives aggregated per-candidate metrics, never raw posts.

This means prompt sizes stay small and deterministic as data grows — adding a new market or another month of ingestion does not inflate the Trend Gen prompt.

---

## 7. Memory

Two memory layers, with different roles:

1. **Run-scoped memory (LangGraph checkpointer).** `MemorySaver()` is attached to the compiled graph. Every node write goes through the checkpointer keyed on `thread_id = run_id`. This powers restartability and streaming progress to the UI but is **process-local**.
2. **Analytical memory (SQLite `trend_exploration`).** Durable. Every finalized run writes its confirmed trends via `persist_trend_report` from the **`memory_write` graph node**. The **next** run loads prior rows **before** LangGraph starts: `load_sql_results` calls `get_prior_trend_snapshots`, fills `prior_snapshot` on `initial_state`, and exposes the same rows under `sql_results["memory"]` for debugging. The Synthesizer uses `prior_snapshot` in `determine_lifecycle_stage(current_score, previous_score)` to assign `emerging / accelerating / peak / declining / stable`.

The deliberate design choice here is that **LLM outputs do not become memory.** Only the scored, verified, lifecycle-tagged trend row is persisted. If tomorrow we rebuild prompts, the analytical history is still valid.

---

## 8. Message Passing, Tool Invocations, and LLM telemetry

LangGraph's reducer model (`Annotated[..., operator.add]`) is the sole message bus **between graph nodes**. The service layer concatenates pre-graph invocations (intent + SQL) with graph-emitted invocations before persisting a single `tool_invocations` list on the run.

Every LLM and SQL step appends **tool invocation records** via `make_tool_invocation(...)`. Each record carries:

- `node`, `tool`, `tool_kind` (`sql` | `llm` | `memory`)
- `started_at`, `completed_at`, `status`, and wall-clock `duration_ms` (derived from timestamps where applicable)
- For SQL: the literal query preview
- For LLM: `system_prompt`, `user_prompt`, `response_text`, `model`, and **`metadata`** enriched with **`duration_ms`**, **`prompt_tokens`**, **`completion_tokens`**, **`total_tokens`**, and **`estimated_cost_usd`** when the provider returns usage (see `LlmTrace` in `backend/app/graph/llm.py` — values are extracted from `response_metadata` / `usage_metadata`, including OpenRouter-style `cost` fields when present)
- `input_summary`, `output_summary`, `metadata`

**Trace size control:** `make_tool_invocation` in `backend/app/graph/tools.py` truncates very large prompt/response/message fields (default cap `TRACE_FIELD_LIMIT`) and records which fields were truncated in `metadata`, so observability stays bounded without dropping the invocation row entirely.

These invocations are what the UI's `ToolInvocationTimeline.tsx` and `AgentNodeDrawer.tsx` render. Click any node on the graph panel and you see the exact prompt and exact SQL that produced its output, plus per-call latency and token/cost metadata when available. This is the observability substrate — the same records can be exported to Langfuse or a metrics pipeline without changing node contracts.

**Aggregated LLM ops on the report:** After a successful run, `AnalysisService` attaches **`llm_ops`** to the finalized `TrendReport` by calling `_aggregate_llm_ops(tool_invocations)`. That structure (`LlmOpsSummary` in `backend/app/models/schemas.py`) contains:

- **`overall`** — total LLM call count, summed prompt/completion/total tokens, summed wall-clock latency (`total_latency_ms`), **average latency per call** (`avg_latency_ms`), summed **`estimated_cost_usd`** (when the gateway reports per-call cost), and the set of **`models`** touched
- **`by_node`** — the same metrics **grouped by graph node name** (e.g. `intent_parser`, `trend_gen_agent`, `evidence_synthesizer`), with `trend_gen_agent:HK`-style nodes folded under `trend_gen_agent` for readable dashboards

Completed runs also surface **`stats.llm_ops`** on `RunStatusResponse` when hydrating from the database (`build_run_status_response`), so historical runs show the same cost/latency rollup as live streams.

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
- **`GraphWorkflowPanel.tsx` + `AgentNodeDrawer.tsx` + `ToolInvocationTimeline.tsx` + `ReasoningTrace.tsx`** — the transparency layer. Renders the LangGraph topology live, shows node status as the run proceeds, and opens a drawer that exposes the literal prompts, SQL, and raw model outputs for any node. `ReasoningTrace.tsx` shows the timestamped `execution_log`. When the API returns a completed **`TrendReport`**, the UI can surface **`report.llm_ops`** (overall + per-node latency, tokens, and estimated spend) alongside cards and traces.

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

- **No agent-to-agent chat.** All coordination is through state reducers (and the service pre-step). Conversational handoffs add non-determinism with no observed benefit on this workload.
- **No re-entrant retry loops across the whole graph.** Retries would hide quality issues. If synthesis yields no confirmed trends, **`confidence_gate` still reaches `formatter`**, which produces an empty or watch-heavy report plus **`guardrail_flags`** rather than silently terminating the graph.
- **No fine-tuned models.** Every LLM call is a prompt + schema against a hosted model (`OpenRouter`). Iteration speed mattered more than style polish for a tool whose underlying signal sources change weekly.

### Trade-offs we accepted

- **Slight loss of narrative polish** in exchange for a strict rule that every number traces to a SQL row. The headlines and "why viral" narratives are intentionally compact and data-first.
- **Slight increase in LLM cost** from running multiple lenses per market, in exchange for higher recall of trend types the single-prompt baseline was missing.
- **Process-local graph memory** instead of a distributed checkpoint store. Acceptable because durable memory lives in SQLite; the graph checkpointer is only for run progress streaming.

---

## 12. LLMOps Considerations

What this design makes easy to operate once it's in front of real users.

- **Observability.** Every LLM and SQL call is recorded as a `ToolInvocation` with prompts, responses, wall-clock duration, and (when the gateway exposes them) **token usage and estimated USD cost** on each invocation's `metadata`. Exporting the same JSON to Langfuse is a single emitter — no changes to node contracts.
- **Latency control (measurement-first).** Per-call **`duration_ms`** is stored on both the trace object (`LlmTrace` in `llm.py`) and merged into `tool_invocations`. **`llm_ops.overall.total_latency_ms`** and **`avg_latency_ms`** give run-level P95-style monitoring when you aggregate many runs in your warehouse; **`llm_ops.by_node`** highlights which node (intent vs trend gen vs synthesizer) dominates tail latency.
- **Cost control (measurement-first).** When OpenRouter (or another compatible gateway) returns **`cost` / `total_cost` / `estimated_cost`** in response metadata, it is summed into **`metadata.estimated_cost_usd`** per call and rolled up into **`TrendReport.llm_ops.overall.estimated_cost_usd`**. That supports credit caps, per-tenant budgets, and anomaly alerts ("this run cost 10× the rolling average") without guessing from token counts alone. Model routing remains a **`openrouter_model`** (and optional per-call `model=` override) configuration concern for future tiered routing.
- **Prompt versioning.** Each node's prompt is a string constant inside its node module (intent and graph nodes). A golden-set harness can diff `LensCandidateBatch` outputs across prompt versions because the schema is fixed.
- **Evaluation.** Because the score and the rationale are separated (numbers from SQL, narrative from LLM), offline evaluation can test them independently:
  - Numerical correctness: replay a frozen SQLite snapshot and assert the scores and confidence tiers.
  - Narrative quality: LLM-as-judge on `why_viral` strings against a rubric (grounded / overclaiming / hallucinated number).
- **Governance.** Raw social text is LLM-enriched offline; Phase 2 trend agents consume **aggregated** `post_trend_signals` and other rollups. Truncation in `make_tool_invocation` limits accidental exfiltration of huge payloads into run JSON stored in SQLite.

---

## 13. Where to Read the Code

| Concern | File |
|---|---|
| Graph topology | `backend/app/graph/graph.py` |
| Run orchestration (intent + SQL preload, `llm_ops` merge) | `backend/app/services/analysis_service.py` |
| Shared state | `backend/app/graph/state.py` |
| API models (`TrendReport.llm_ops`, `LlmOpsSummary`) | `backend/app/models/schemas.py` |
| Schemas | `backend/app/graph/schemas.py` |
| LLM adapter + usage/cost trace | `backend/app/graph/llm.py` |
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
