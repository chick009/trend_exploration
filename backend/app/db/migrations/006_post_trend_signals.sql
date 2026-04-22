CREATE TABLE IF NOT EXISTS post_trend_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_table TEXT NOT NULL,
    source_row_id TEXT NOT NULL,
    source_batch_id TEXT,
    search_keyword TEXT,
    input_text TEXT,
    region TEXT NOT NULL,
    category TEXT NOT NULL,
    trend_strength REAL,
    novelty REAL,
    consumer_intent REAL,
    llm_rationale TEXT,
    processing_model TEXT,
    processed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_table, source_row_id)
);

CREATE INDEX IF NOT EXISTS idx_post_trend_signals_source_batch_id ON post_trend_signals (source_batch_id);
CREATE INDEX IF NOT EXISTS idx_post_trend_signals_region ON post_trend_signals (region);
CREATE INDEX IF NOT EXISTS idx_post_trend_signals_category ON post_trend_signals (category);
CREATE INDEX IF NOT EXISTS idx_post_trend_signals_processed_at ON post_trend_signals (processed_at);
