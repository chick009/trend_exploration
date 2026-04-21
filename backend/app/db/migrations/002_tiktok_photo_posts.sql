CREATE TABLE IF NOT EXISTS tiktok_photo_posts (
    id TEXT PRIMARY KEY,
    search_keyword TEXT NOT NULL,
    create_time_unix INTEGER,
    create_time TEXT,
    description TEXT,
    author_json TEXT,
    image_url TEXT,
    cover_url TEXT,
    stats_json TEXT,
    hashtags_json TEXT,
    music_json TEXT,
    is_ad INTEGER DEFAULT 0,
    share_url TEXT,
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tiktok_photo_posts_search_keyword ON tiktok_photo_posts (search_keyword);
CREATE INDEX IF NOT EXISTS idx_tiktok_photo_posts_fetched_at ON tiktok_photo_posts (fetched_at);
