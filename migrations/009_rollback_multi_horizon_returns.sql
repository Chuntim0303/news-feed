-- Rollback Migration 009: Remove multi-horizon event study infrastructure

-- Remove Layer 4 column from alert_log
ALTER TABLE alert_log DROP COLUMN IF EXISTS score_market_reaction;

-- Drop new tables (in reverse order of dependencies)
DROP TABLE IF EXISTS scoring_backtest_results;
DROP TABLE IF EXISTS market_reaction_scores;
DROP TABLE IF EXISTS article_clusters;
DROP TABLE IF EXISTS confounder_events;
DROP TABLE IF EXISTS ticker_sector_mapping;
DROP TABLE IF EXISTS benchmark_returns;
DROP TABLE IF EXISTS article_return_windows;

-- Remove columns from article_stock_snapshots
ALTER TABLE article_stock_snapshots 
DROP COLUMN IF EXISTS ticker_relevance_score,
DROP COLUMN IF EXISTS mention_count,
DROP COLUMN IF EXISTS in_title,
DROP COLUMN IF EXISTS publish_session,
DROP COLUMN IF EXISTS publish_timestamp;
