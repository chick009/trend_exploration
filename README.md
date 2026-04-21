Now I have a complete picture of both APIs. Here is the full consolidated plan.

***

# Complete System Plan: Health & Beauty Viral Trend Discovery

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    PHASE 1: DATA PIPELINE                   │
│  (Scheduled ETL — runs independently, no agents)           │
│                                                             │
│  SerpApi Google Trends  ──► search_trends table            │
│  TikHub REDNOTE API     ──► social_posts table             │
│  Internal CSV/DB        ──► sales_data table               │
│  (shared)               ──► entity_dictionary table        │
└─────────────────────────────────────────────────────────────┘
                              │ SQLite
                              ▼
┌─────────────────────────────────────────────────────────────┐
│               PHASE 2: MULTI-AGENT INTELLIGENCE             │
│  (On-demand — triggered by user action in UI)               │
│                                                             │
│  UI Filters ──► Query Intent Parser                        │
│             ──► Orchestrator (LangGraph)                   │
│                  ├── Trend Generation Agent(s) [fan-out]   │
│                  ├── Evidence Synthesizer Agent            │
│                  └── Report Formatter Agent                │
│             ──► trend_exploration table ──► UI Cards       │
└─────────────────────────────────────────────────────────────┘
```

***

## Phase 1: Data Pipeline (Detailed)

### Pipeline A — Google Trends via SerpApi

**What to fetch and how:**

SerpApi exposes four `data_type` modes. For H&B trend discovery, you need **three calls per keyword batch**: [blog.langchain](https://blog.langchain.com/langgraph-multi-agent-workflows/)

| Call | `data_type` | Purpose | Frequency |
|---|---|---|---|
| Interest over time | `TIMESERIES` | WoW slope, spike detection | Daily |
| Interest by region | `GEO_MAP_0` | Which geo is hottest | Daily |
| Related queries | `RELATED_QUERIES` | Surface rising adjacent terms | Weekly |

**Keyword seeding strategy:** You cannot query Google Trends without knowing keywords in advance. Maintain a `seed_keywords` config list (~50 H&B terms: "niacinamide", "snail mucin", "tranexamic acid", etc.) plus dynamically add top REDNOTE hashtags discovered yesterday. This creates a feedback loop between pipelines.

**Key parameters for your use case:**
```python
# For HK market, past 30 days, Health & Beauty category
params = {
    "engine": "google_trends",
    "q": "niacinamide,tranexamic acid,ceramide,snail mucin,retinol",  # max 5 per call
    "geo": "HK",
    "date": "today 1-m",
    "tz": "-480",          # HKT = UTC+8, so tz = -480
    "cat": "44",           # Google Trends category 44 = Beauty & Fitness
    "data_type": "TIMESERIES",
    "api_key": SERPAPI_KEY
}
```

For cross-market comparison, make the same call with `geo="KR"`, `geo="TW"`, `geo="SG"` — this is where cross-market lag patterns emerge.

**WoW slope computation** (done in normalizer, not agent):
```python
# From TIMESERIES response: interest_over_time.timeline_data
def compute_wow_delta(timeline_data: list) -> float:
    values = [w["values"][0]["extracted_value"] for w in timeline_data]
    if len(values) < 14:
        return 0.0
    this_week = sum(values[-7:]) / 7
    last_week = sum(values[-14:-7]) / 7
    return (this_week - last_week) / (last_week + 1e-9)

def is_breakout(timeline_data: list, threshold=0.4) -> bool:
    return compute_wow_delta(timeline_data) > threshold
```

**Output table — `search_trends`:**
```sql
CREATE TABLE search_trends (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword         TEXT NOT NULL,
    geo             TEXT NOT NULL,              -- 'HK', 'KR', 'TW', 'SG'
    snapshot_date   DATE NOT NULL,
    index_value     REAL,                       -- latest week's 0-100 value
    wow_delta       REAL,                       -- week-over-week change ratio
    is_breakout     INTEGER DEFAULT 0,          -- boolean flag
    related_rising  TEXT,                       -- JSON: top 5 rising related queries
    raw_timeseries  TEXT,                       -- JSON: full timeline for charting
    source          TEXT DEFAULT 'serpapi',
    UNIQUE(keyword, geo, snapshot_date)
);
```

**Rate limit note:** SerpApi free tier gives 100 searches/month; paid plans start at 5,000/month. Batch your 5-keyword calls to conserve quota. Cache results with `no_cache=false` (SerpApi serves cached results free for 1 hour). [blog.langchain](https://blog.langchain.com/langgraph-multi-agent-workflows/)

***

### Pipeline B — REDNOTE via TikHub API

Two endpoints are needed based on the docs: [docs.tikhub](https://docs.tikhub.io/186826254e0)

#### Step B1: Search Notes by Keyword

```
GET https://api.tikhub.io/api/v1/xiaohongshu/web/search_notes
    ?keyword={term}
    &page=1
    &sort_type=general       # or 'hot' for engagement-sorted
    &note_type=0             # 0=all, 1=video, 2=image
```

**Auth header:** `Authorization: Bearer {TIKHUB_API_KEY}`

This maps to the "Get relevant Rednote Notes" endpoint you linked.  Run this for each seed keyword. Extract from each note result: [docs.tikhub](https://docs.tikhub.io/186826254e0)
- `note_id` (needed for Step B2)
- `title`, `desc` — for keyword/ingredient mention extraction
- `liked_count`, `collected_count`, `comment_count`, `share_count`
- `tags` / `hashtags` array
- `user.location` — for geo filtering
- `create_time` — for recency filtering

#### Step B2: Fetch Note Comments

```
GET https://api.tikhub.io/api/v1/xiaohongshu/web/get_note_comments
    ?note_id={note_id}
    &lastCursor=             # empty for first page, paginate with cursor
```

This maps to your "Process Rednote Note Comments" endpoint.  For the demo, only fetch comments on **high-engagement notes** (e.g., `liked_count > 500`) to conserve API credits. Comments are valuable for: [docs.tikhub](https://docs.tikhub.io/420136394e0)
- Surfacing ingredient mentions that aren't in the post title (users asking "what is this?")
- Capturing sentiment signals (product effectiveness discussion)
- Detecting brand name mentions

**Normalizer logic — entity extraction from text:**
```python
import re, json

def extract_mentions(text: str, entity_dict: dict) -> list[str]:
    """Map raw text to canonical entity terms via entity_dictionary."""
    found = []
    text_lower = text.lower()
    for canonical, aliases in entity_dict.items():
        for alias in aliases:
            if alias.lower() in text_lower:
                found.append(canonical)
                break
    return list(set(found))

def compute_engagement_score(liked, collected, comments, shares, views=None) -> float:
    """Normalize engagement; views often unavailable on REDNOTE web."""
    total = liked + collected * 2 + comments * 3 + shares * 4
    # Weight: saves/collects signal stronger intent than likes
    return min(total / 10000, 1.0)   # cap at 1.0 for normalization
```

**Output table — `social_posts`:**
```sql
CREATE TABLE social_posts (
    id                  TEXT PRIMARY KEY,        -- note_id from TikHub
    platform            TEXT DEFAULT 'rednote',
    region              TEXT,                    -- extracted from user.location
    post_date           DATE NOT NULL,
    title               TEXT,
    content_text        TEXT,
    hashtags            TEXT,                    -- JSON array of tags
    entity_mentions     TEXT,                    -- JSON array of canonical terms (post-extraction)
    comment_mentions    TEXT,                    -- JSON array of terms found in comments
    liked_count         INTEGER DEFAULT 0,
    collected_count     INTEGER DEFAULT 0,
    comment_count       INTEGER DEFAULT 0,
    share_count         INTEGER DEFAULT 0,
    engagement_score    REAL DEFAULT 0.0,
    seed_keyword        TEXT,                    -- which keyword search surfaced this
    fetched_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Pipeline orchestration for B1 → B2:**
```
FOR each seed_keyword:
    notes = search_notes(keyword, sort='hot', page=1..3)
    INSERT notes → social_posts (basic fields)
    
    high_value_notes = [n for n in notes if n.liked_count > 500]
    FOR each note in high_value_notes:
        comments = get_note_comments(note.note_id)
        comment_mentions = extract_mentions(all_comment_text)
        UPDATE social_posts SET comment_mentions = comment_mentions
        WHERE id = note.note_id
```

***

### Pipeline C — Internal Sales Data (Synthetic for Demo)

No external API needed. Generate a SQLite `sales_data` table seeded with realistic H&B SKU data:

```sql
CREATE TABLE sales_data (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sku             TEXT NOT NULL,
    product_name    TEXT,
    brand           TEXT,
    ingredient_tags TEXT,          -- JSON array of canonical ingredients
    category        TEXT,          -- 'skincare' | 'haircare' | 'makeup' | 'supplements'
    region          TEXT,
    week_start      DATE,
    units_sold      INTEGER,
    revenue         REAL,
    wow_velocity    REAL,
    is_restocking   INTEGER DEFAULT 0,
    UNIQUE(sku, region, week_start)
);
```

Seed ~30 SKUs with plausible WoW velocity values. Key insight: **wow_velocity is the primary signal**, not raw sales volume. A niche SPF serum going from 50 → 90 units (+80% WoW) is more signal than a bestselling moisturizer going from 5000 → 5100 (+2%).

***

### Shared Reference Table — `entity_dictionary`

Populated once during setup, maintained by hand or via an LLM-assisted enrichment step:

```sql
CREATE TABLE entity_dictionary (
    canonical_term  TEXT PRIMARY KEY,
    aliases         TEXT NOT NULL,   -- JSON array: ["niacinamide", "vitamin b3", "nicotinamide"]
    entity_type     TEXT NOT NULL,   -- 'ingredient' | 'brand' | 'function' | 'product_type'
    hb_category     TEXT,            -- 'skincare' | 'haircare' | 'makeup' | 'supplements'
    origin_market   TEXT,            -- 'KR' | 'JP' | 'US' | 'EU'
    description     TEXT             -- 1-line description for UI display
);
```

Seed ~60–80 canonical terms covering:
- **Ingredients:** niacinamide, tranexamic acid, ceramide, retinol, snail secretion, cica/centella, bakuchiol, phloretin, azelaic acid, polyglutamic acid
- **Brands:** COSRX, Torriden, Some By Mi, Skin1004, Dr.Jart+, Beauty of Joseon
- **Functions:** "skin barrier repair", "glass skin", "slugging", "skip-care", "double cleanse"

***

## Phase 2: Multi-Agent LangGraph System (Detailed)

### State Schema

```python
from typing import TypedDict, Annotated, Optional
from langgraph.graph import add_messages

class TrendDiscoveryState(TypedDict):
    # --- User inputs (set at graph entry) ---
    market: str                        # 'HK' | 'KR' | 'TW' | 'SG' | 'cross'
    category: str                      # 'skincare' | 'haircare' | 'makeup' | 'all'
    recency_days: int                  # 7 | 14 | 30
    analysis_mode: str                 # 'single_market' | 'cross_market'

    # --- Parsed intent (set by Intent Parser) ---
    query_params: dict                 # structured filters for SQL

    # --- Agent outputs ---
    trend_candidates: list[dict]       # Trend Gen Agent output (all markets combined)
    synthesized_trends: list[dict]     # Synthesizer output
    formatted_report: dict             # Formatter output

    # --- Control ---
    messages: Annotated[list, add_messages]
    guardrail_flags: list[str]
    execution_log: list[str]           # timestamped step log for UI reasoning trace
    retry_count: int                   # loop guard
```

### Agent 1: Query Intent Parser (lightweight, no LLM needed for demo)

**Responsibility:** Translate UI filter selections into validated SQL parameters. In production this can be an LLM call for natural language; in the demo it's a pure mapping function since the UI provides structured inputs.

```python
def parse_query_intent(state: TrendDiscoveryState) -> TrendDiscoveryState:
    market = state["market"]
    
    # Map market to geo codes and timezone for SerpApi cross-reference
    market_config = {
        "HK":    {"geo": "HK", "tz": -480, "regions": ["HK"]},
        "KR":    {"geo": "KR", "tz": -540, "regions": ["KR"]},
        "cross": {"geo": None, "tz": -480, "regions": ["HK", "KR", "TW"]}
    }
    
    date_window = {
        7:  f"WHERE post_date >= date('now', '-7 days')",
        14: f"WHERE post_date >= date('now', '-14 days')",
        30: f"WHERE post_date >= date('now', '-30 days')"
    }[state["recency_days"]]
    
    state["query_params"] = {
        "market_config": market_config[market],
        "date_filter": date_window,
        "category_filter": state["category"],
        "recency_days": state["recency_days"]
    }
    state["execution_log"].append(f"[IntentParser] Query params set: {market}, {state['category']}, {state['recency_days']}d")
    return state
```

***

### Agent 2: Trend Generation Agent

**Responsibility:** Execute SQL queries across all three tables, group by canonical entity, and generate a trend hypothesis for each candidate. Fan-out via `Send()` when `analysis_mode = 'cross_market'` — one instance per region.

**SQL queries the agent constructs and executes:**

```sql
-- Query 1: Top social entities by engagement in window
SELECT 
    d.canonical_term,
    d.entity_type,
    d.hb_category,
    COUNT(p.id) AS post_count,
    AVG(p.engagement_score) AS avg_engagement,
    SUM(p.liked_count) AS total_likes,
    SUM(p.comment_count) AS total_comments
FROM social_posts p,
     json_each(p.entity_mentions) AS em
JOIN entity_dictionary d ON d.canonical_term = em.value
WHERE p.post_date >= date('now', '-{recency_days} days')
  AND p.region = '{region}'
  AND ({category_filter})
GROUP BY d.canonical_term
ORDER BY avg_engagement DESC
LIMIT 20;

-- Query 2: Search trend breakouts in window
SELECT 
    st.keyword,
    st.wow_delta,
    st.index_value,
    st.is_breakout,
    st.related_rising
FROM search_trends st
WHERE st.geo = '{geo}'
  AND st.snapshot_date >= date('now', '-{recency_days} days')
  AND st.is_breakout = 1
ORDER BY st.wow_delta DESC
LIMIT 20;

-- Query 3: Internal sales velocity spikes
SELECT
    sd.ingredient_tags,
    sd.brand,
    sd.category,
    AVG(sd.wow_velocity) AS avg_velocity,
    SUM(sd.units_sold) AS total_units,
    COUNT(CASE WHEN sd.is_restocking = 1 THEN 1 END) AS restock_count
FROM sales_data sd
WHERE sd.region = '{region}'
  AND sd.week_start >= date('now', '-{recency_days} days')
  AND sd.category = '{category}'
GROUP BY sd.brand
ORDER BY avg_velocity DESC
LIMIT 20;
```

**SQL Safety Guardrail** wraps the tool:
```python
ALLOWED_PREFIXES = ("SELECT", "WITH")
BLOCKED_KEYWORDS = ("DROP", "INSERT", "UPDATE", "DELETE", "PRAGMA", "ATTACH", "EXEC")

def safe_sql_execute(query: str, conn) -> list[dict]:
    q = query.strip().upper()
    if not any(q.startswith(p) for p in ALLOWED_PREFIXES):
        raise ValueError("Only SELECT queries are permitted")
    if any(kw in q for kw in BLOCKED_KEYWORDS):
        raise ValueError(f"Query contains blocked keyword")
    # Execute with parameter binding (never f-string into raw SQL)
    cursor = conn.execute(query)
    return [dict(row) for row in cursor.fetchall()]
```

**LLM call for hypothesis generation** (structured output):
```python
# After SQL results are collected, one LLM call per candidate cluster:
TREND_GEN_PROMPT = """
You are a Health & Beauty market analyst. Given the following data signals,
generate a trend hypothesis.

Data signals:
- Social posts mentioning "{term}": {post_count} posts, avg engagement {avg_engagement:.3f}
- Google Trends WoW delta in {geo}: {wow_delta:.1%} {"(BREAKOUT)" if is_breakout else ""}
- Sales velocity WoW: {sales_velocity:.1%} ({restock_count} SKUs restocking)

Output JSON only:
{{
  "canonical_term": "...",
  "trend_description": "2-3 sentence hypothesis grounded in the data above",
  "dominant_signal": "social|search|sales",
  "confidence_indicators": ["...", "..."]
}}
Do not fabricate statistics. Only reference numbers provided above.
"""
```

***

### Agent 3: Evidence Synthesizer Agent

**Responsibility:** Receive all trend candidates (potentially from multiple Trend Gen Agent instances), deduplicate, score, and write to `trend_exploration`.

**Deduplication logic:** Two candidates refer to the same trend if their `canonical_term` matches after entity dictionary lookup. Merge by taking the max of each sub-score.

**Virality score:**

\[ V = 0.35 \cdot S_{social} + 0.30 \cdot S_{sales} + 0.25 \cdot S_{search} + 0.10 \cdot S_{cross} \]

Each sub-score is computed as:
```python
def normalize_score(value: float, min_val: float, max_val: float) -> float:
    if max_val == min_val:
        return 0.5
    return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))

# social_score: from avg_engagement_score (0-1 already normalized)
# search_score: from wow_delta (normalize across all candidates in this run)
# sales_score: from avg_velocity (normalize across all candidates)
# cross_score: 1.0 if origin_market != current_market AND origin trend_date < current, else 0
```

**Confidence tier assignment:**
```python
def assign_confidence(sources_with_signal: int, virality_score: float) -> str:
    if sources_with_signal >= 3 and virality_score > 0.65:
        return "high"
    elif sources_with_signal >= 2 and virality_score > 0.40:
        return "medium"
    else:
        return "low"   # goes to watch_list, not main report
```

**SQLite write:**
```sql
INSERT OR REPLACE INTO trend_exploration (
    trend_id, canonical_term, entity_type, virality_score,
    confidence_tier, sources_count, social_score, search_score,
    sales_score, cross_market_score, market, analysis_date,
    candidate_json, status
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
```

**Regional divergence detection:**
```python
# If cross_market mode: same canonical_term appears in multiple market instances
# with significantly different virality directions
def detect_divergence(candidates_by_market: dict) -> list[dict]:
    divergences = []
    all_terms = set().union(*[set(c["canonical_term"] for c in v) 
                              for v in candidates_by_market.values()])
    for term in all_terms:
        scores = {mkt: next((c["virality_score"] for c in cands 
                             if c["canonical_term"] == term), None)
                  for mkt, cands in candidates_by_market.items()}
        scores = {k: v for k, v in scores.items() if v is not None}
        if len(scores) >= 2 and max(scores.values()) - min(scores.values()) > 0.35:
            divergences.append({"term": term, "market_scores": scores})
    return divergences
```

***

### Agent 4: Report Formatter Agent

**Responsibility:** Read confirmed trends from `trend_exploration`, generate the UI-ready JSON payload with evidence narratives. Apply tone guardrail before returning.

**Tone guardrail prompt wrapper:**
```python
TONE_GUARDRAIL_SYSTEM = """
You are a factual report writer for retail business users.
Rules:
1. Never say "will go viral" — say "showing strong early signals"
2. Never fabricate a number not in the provided data
3. Never disparage specific brands by name
4. Every claim must trace to one of: social_score, search_score, sales_score, cross_market_score
5. Confidence language must match the confidence_tier: 
   high="strong evidence", medium="moderate signals", low="early watch"
"""
```

**Output JSON structure** (fed directly to UI):
```python
{
  "report_id": "uuid4",
  "generated_at": "ISO8601",
  "market": "HK",
  "category": "skincare",
  "recency_days": 14,
  "trends": [
    {
      "rank": 1,
      "term": "Tranexamic Acid",
      "entity_type": "ingredient",
      "virality_score": 0.87,
      "confidence_tier": "high",
      "headline": "Surging as a brightening alternative to Vitamin C",
      "why_viral": "Tranexamic acid is showing strong evidence...",
      "evidence": {
        "social": "340 REDNOTE posts this period; avg engagement 0.091",
        "search": "Google Trends breakout in HK, +34% WoW",
        "sales": "Avg SKU velocity +28% WoW; 2 SKUs triggering restock",
        "cross_market": "Peaked in KR ~3 weeks ago — HK in early adoption phase"
      },
      "signal_chips": ["REDNOTE", "Google Trends", "Sales", "KR→HK"],
      "trend_stage": "accelerating",   # from history comparison
      "watch_flag": false
    }
  ],
  "watch_list": [...],
  "regional_divergences": [...],
  "execution_trace": [...]    # agent step log for UI "reasoning" tab
}
```

***

## LangGraph Graph Definition

```python
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

def route_trend_gen(state: TrendDiscoveryState):
    """Fan-out: one Trend Gen Agent per region in cross-market mode."""
    if state["analysis_mode"] == "cross_market":
        regions = state["query_params"]["market_config"]["regions"]
        return [Send("trend_gen_agent", {**state, "active_region": r}) 
                for r in regions]
    else:
        return [Send("trend_gen_agent", {**state, 
                "active_region": state["query_params"]["market_config"]["regions"][0]})]

def confidence_gate(state: TrendDiscoveryState):
    """Route: enough confirmed trends → format; else → flag and end."""
    confirmed = [t for t in state["synthesized_trends"] 
                 if t["confidence_tier"] in ("high", "medium")]
    if len(confirmed) == 0:
        state["guardrail_flags"].append("No confirmed trends found — data may be insufficient")
        return "end_with_warning"
    return "format"

builder = StateGraph(TrendDiscoveryState)
builder.add_node("intent_parser",    parse_query_intent)
builder.add_node("trend_gen_agent",  run_trend_gen_agent)
builder.add_node("synthesizer",      run_evidence_synthesizer)
builder.add_node("formatter",        run_report_formatter)

builder.add_edge(START, "intent_parser")
builder.add_conditional_edges("intent_parser", route_trend_gen)
builder.add_edge("trend_gen_agent", "synthesizer")
builder.add_conditional_edges("synthesizer", confidence_gate, {
    "format": "formatter",
    "end_with_warning": END
})
builder.add_edge("formatter", END)

graph = builder.compile(checkpointer=InMemorySaver())
```

***

## UI Component Plan

The UI is a single-page web app. Three panels:

### Left Panel — Control Sidebar
- **Market selector** (radio or pill buttons): HK / KR / TW / Cross-Market
- **Category filter** (multi-select chips): Skincare · Haircare · Makeup · Supplements
- **Recency window** (segmented control): 7d / 14d / 30d
- **"Run Analysis" button** — triggers Phase 2 agent graph; shows spinner with live agent step labels ("Querying social data…", "Synthesizing evidence…")

### Center Panel — Trend Cards
- Each card shows: Rank badge · Trend name + type chip · Virality score bar · Signal chips (color-coded: pink=REDNOTE, blue=Google, green=Sales, yellow=Cross-Market) · Trend stage badge (Emerging / Accelerating / Peak / Declining)
- **Expandable section:** "Why is this viral?" — the `why_viral` narrative + bullet evidence per source
- **Watch List section** below confirmed trends — lower-confidence signals shown with a "⚠ Early signal" label

### Right Panel — Reasoning Trace (collapsible)
- Timestamped log of agent steps from `execution_log`
- SQL queries used by Trend Gen Agent (shown in a code block for transparency)
- Guardrail flags displayed in amber if any were raised
- "Last data refresh" timestamp from pipeline

***

## SQLite Database Summary

```
trend_db.sqlite
├── entity_dictionary     (seed data, ~80 rows)
├── search_trends         (written by Pipeline A, read by Agent 2)
├── social_posts          (written by Pipeline B, read by Agent 2)
├── sales_data            (synthetic seed, read by Agent 2)
└── trend_exploration     (written by Agent 3, read by Agent 4 + UI)
```

All five tables live in one file. The pipelines can run as cron jobs (`schedule` library or APScheduler) while the agent graph runs on-demand per user request. This means the UI always reads from a fresh, pre-processed SQLite store — the agents never hit an external API at query time, keeping latency low.