ALTER TABLE tiktok_photo_posts ADD COLUMN source_batch_id TEXT;

CREATE INDEX IF NOT EXISTS idx_tiktok_photo_posts_source_batch_id ON tiktok_photo_posts (source_batch_id);
