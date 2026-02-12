-- Migration 005: Add processing status flags to rss_items
--
-- ticker_processed: 0 = not yet processed, 1 = ticker extraction attempted
-- price_processed:  0 = not yet processed, 1 = price fetch + snapshot attempted
--
-- This allows easy tracing of failed extractions:
--   Failed ticker extraction: ticker_processed = 1 AND (stock_tickers IS NULL OR stock_tickers = '')
--   Failed price fetch:       price_processed = 1 AND article has no snapshot or NULL prices

ALTER TABLE rss_items
    ADD COLUMN ticker_processed TINYINT(1) NOT NULL DEFAULT 0 AFTER company_names,
    ADD COLUMN price_processed  TINYINT(1) NOT NULL DEFAULT 0 AFTER ticker_processed;

-- Backfill: mark existing articles that already have tickers as processed
UPDATE rss_items SET ticker_processed = 1
WHERE stock_tickers IS NOT NULL AND stock_tickers != '';

-- Backfill: mark articles that already have snapshots as price-processed
UPDATE rss_items ri SET ri.price_processed = 1
WHERE ri.id IN (SELECT DISTINCT article_id FROM article_stock_snapshots);

-- Index for fast lookups of unprocessed articles
CREATE INDEX idx_rss_items_ticker_processed ON rss_items (ticker_processed);
CREATE INDEX idx_rss_items_price_processed  ON rss_items (price_processed);
