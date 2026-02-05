-- Rollback Migration: Remove stock ticker detection fields
-- Database: MySQL
-- Description: Removes stock ticker tracking columns from rss_items table

-- Remove index
ALTER TABLE rss_items DROP INDEX idx_stock_tickers;

-- Remove columns
ALTER TABLE rss_items DROP COLUMN company_names;
ALTER TABLE rss_items DROP COLUMN stock_tickers;
