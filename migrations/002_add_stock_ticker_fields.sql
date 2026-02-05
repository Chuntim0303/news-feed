-- Migration: Add stock ticker detection fields
-- Database: MySQL
-- Description: Adds stock ticker tracking to rss_items table

-- Add stock_tickers column to store detected ticker symbols
ALTER TABLE rss_items
ADD COLUMN stock_tickers VARCHAR(500) AFTER author COMMENT 'Comma-separated stock ticker symbols detected in the article';

-- Add index for stock ticker searches
ALTER TABLE rss_items
ADD INDEX idx_stock_tickers (stock_tickers);

-- Add company_names column to store detected company names
ALTER TABLE rss_items
ADD COLUMN company_names VARCHAR(1000) AFTER stock_tickers COMMENT 'Comma-separated company names detected in the article';
