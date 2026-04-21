CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS entity_dictionary (
    canonical_term TEXT PRIMARY KEY,
    aliases TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    hb_category TEXT,
    origin_market TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS search_trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    geo TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    index_value REAL,
    wow_delta REAL,
    is_breakout INTEGER DEFAULT 0,
    related_rising TEXT,
    raw_timeseries TEXT,
    source TEXT DEFAULT 'serpapi',
    llm_category TEXT,
    llm_subcategory TEXT,
    relevance_score REAL DEFAULT 0,
    processed_at DATETIME,
    source_batch_id TEXT,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(keyword, geo, snapshot_date)
);

CREATE TABLE IF NOT EXISTS social_posts (
    id TEXT PRIMARY KEY,
    platform TEXT DEFAULT 'rednote',
    region TEXT,
    post_date DATE NOT NULL,
    title TEXT,
    content_text TEXT,
    hashtags TEXT,
    entity_mentions TEXT,
    comment_mentions TEXT,
    liked_count INTEGER DEFAULT 0,
    collected_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    share_count INTEGER DEFAULT 0,
    engagement_score REAL DEFAULT 0.0,
    seed_keyword TEXT,
    llm_category TEXT,
    llm_subcategory TEXT,
    positivity_score REAL DEFAULT 0.0,
    sentiment_label TEXT,
    relevance_score REAL DEFAULT 0.0,
    llm_entities TEXT,
    llm_summary TEXT,
    processed_at DATETIME,
    processing_model TEXT,
    source_batch_id TEXT,
    source_payload TEXT,
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sales_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL,
    product_name TEXT,
    brand TEXT,
    ingredient_tags TEXT,
    category TEXT,
    region TEXT,
    week_start DATE,
    units_sold INTEGER,
    revenue REAL,
    wow_velocity REAL,
    is_restocking INTEGER DEFAULT 0,
    source_batch_id TEXT DEFAULT 'synthetic_seed',
    UNIQUE(sku, region, week_start)
);

CREATE TABLE IF NOT EXISTS trend_exploration (
    trend_id TEXT PRIMARY KEY,
    canonical_term TEXT NOT NULL,
    entity_type TEXT,
    hb_category TEXT,
    virality_score REAL,
    confidence_tier TEXT,
    sources_count INTEGER,
    social_score REAL,
    search_score REAL,
    sales_score REAL,
    cross_market_score REAL,
    sentiment_score REAL,
    avg_positivity_score REAL,
    market TEXT,
    analysis_date DATETIME,
    current_batch_id TEXT,
    source_batch_ids TEXT,
    candidate_json TEXT,
    evidence_summary TEXT,
    llm_rationale TEXT,
    status TEXT DEFAULT 'confirmed',
    report_json TEXT
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    market TEXT,
    category TEXT,
    recent_days INTEGER,
    from_timestamp DATETIME,
    to_timestamp DATETIME,
    sources TEXT,
    seed_terms TEXT,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    error_message TEXT,
    stats_json TEXT,
    guardrail_flags TEXT,
    source_batch_id TEXT
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    market TEXT,
    category TEXT,
    recency_days INTEGER,
    analysis_mode TEXT,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    error_message TEXT,
    execution_trace TEXT,
    report_json TEXT,
    source_batch_ids TEXT
);
