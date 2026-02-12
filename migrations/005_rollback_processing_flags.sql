-- Rollback Migration 005: Remove processing status flags from rss_items

DROP INDEX idx_rss_items_ticker_processed ON rss_items;
DROP INDEX idx_rss_items_price_processed  ON rss_items;

ALTER TABLE rss_items
    DROP COLUMN ticker_processed,
    DROP COLUMN price_processed;
