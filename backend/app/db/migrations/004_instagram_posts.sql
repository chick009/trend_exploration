CREATE TABLE IF NOT EXISTS instagram_posts (
    post_id TEXT PRIMARY KEY,
    search_keyword TEXT NOT NULL,
    code TEXT,
    username TEXT,
    full_name TEXT,
    caption TEXT,
    hashtags_json TEXT,
    mentions_json TEXT,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0,
    is_video INTEGER DEFAULT 0,
    created_at TEXT,
    location_name TEXT,
    city TEXT,
    lat REAL,
    lng REAL,
    source_batch_id TEXT,
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_instagram_posts_search_keyword ON instagram_posts (search_keyword);
CREATE INDEX IF NOT EXISTS idx_instagram_posts_source_batch_id ON instagram_posts (source_batch_id);
CREATE INDEX IF NOT EXISTS idx_instagram_posts_fetched_at ON instagram_posts (fetched_at);
