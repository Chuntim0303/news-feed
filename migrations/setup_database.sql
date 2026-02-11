-- Complete Database Setup Script
-- Run this file to set up the entire database schema
--
-- Usage: mysql -u your_user -p news_feed < migrations/setup_database.sql
--
-- Note: This assumes rss_items.id is BIGINT UNSIGNED (most common)
-- If your setup is different, use run_all_migrations.sh instead

-- ============================================================================
-- MIGRATION 001: Create base RSS tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS rss_feeds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    url VARCHAR(500) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS rss_items (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    feed_id INT NOT NULL,
    title VARCHAR(500) NOT NULL,
    link VARCHAR(1000) NOT NULL UNIQUE,
    description TEXT,
    content TEXT,
    author VARCHAR(255),
    published_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (feed_id) REFERENCES rss_feeds(id) ON DELETE CASCADE,
    INDEX idx_feed_id (feed_id),
    INDEX idx_published_at (published_at),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- MIGRATION 002: Add stock ticker detection fields
-- ============================================================================

-- Check if columns already exist, if not add them
SET @col_exists_tickers = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
    AND table_name = 'rss_items'
    AND column_name = 'stock_tickers'
);

SET @col_exists_companies = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
    AND table_name = 'rss_items'
    AND column_name = 'company_names'
);

-- Add stock_tickers column if it doesn't exist
SET @sql_add_tickers = IF(
    @col_exists_tickers = 0,
    'ALTER TABLE rss_items ADD COLUMN stock_tickers VARCHAR(500) AFTER author COMMENT ''Comma-separated stock ticker symbols detected in the article''',
    'SELECT ''Column stock_tickers already exists'' AS info'
);
PREPARE stmt FROM @sql_add_tickers;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add index for stock_tickers if column was just added
SET @sql_add_index = IF(
    @col_exists_tickers = 0,
    'ALTER TABLE rss_items ADD INDEX idx_stock_tickers (stock_tickers)',
    'SELECT ''Index idx_stock_tickers already exists or skipped'' AS info'
);
PREPARE stmt FROM @sql_add_index;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add company_names column if it doesn't exist
SET @sql_add_companies = IF(
    @col_exists_companies = 0,
    'ALTER TABLE rss_items ADD COLUMN company_names VARCHAR(1000) AFTER stock_tickers COMMENT ''Comma-separated company names detected in the article''',
    'SELECT ''Column company_names already exists'' AS info'
);
PREPARE stmt FROM @sql_add_companies;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================================================
-- MIGRATION 003: Create stock price tables (BIGINT UNSIGNED version)
-- ============================================================================

-- Drop existing tables if they exist (in case of type mismatch)
DROP TABLE IF EXISTS article_stock_snapshots;
DROP TABLE IF EXISTS stock_prices;
DROP VIEW IF EXISTS v_articles_with_stock_performance;

-- Stock prices table
CREATE TABLE IF NOT EXISTS stock_prices (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    price DECIMAL(12, 4) NOT NULL COMMENT 'Stock price',
    open_price DECIMAL(12, 4) NULL COMMENT 'Opening price for the day',
    high_price DECIMAL(12, 4) NULL COMMENT 'Highest price for the day',
    low_price DECIMAL(12, 4) NULL COMMENT 'Lowest price for the day',
    close_price DECIMAL(12, 4) NULL COMMENT 'Closing price for the day',
    volume BIGINT NULL COMMENT 'Trading volume',
    change_amount DECIMAL(12, 4) NULL COMMENT 'Price change amount',
    change_percent DECIMAL(8, 4) NULL COMMENT 'Price change percentage',
    market_cap BIGINT NULL COMMENT 'Market capitalization',
    exchange VARCHAR(50) NULL COMMENT 'Stock exchange (NYSE, NASDAQ, etc.)',
    currency VARCHAR(10) DEFAULT 'USD' COMMENT 'Currency of the price',
    price_date DATE NOT NULL COMMENT 'Date of the price',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When the price was fetched',

    -- Indexes for efficient querying
    INDEX idx_ticker (ticker),
    INDEX idx_price_date (price_date),
    INDEX idx_ticker_date (ticker, price_date),
    INDEX idx_fetched_at (fetched_at),

    -- Unique constraint to prevent duplicate entries for same ticker/date
    UNIQUE KEY unique_ticker_date (ticker, price_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Stock price data for tickers mentioned in RSS articles';

-- Table to link articles with stock prices at time of publication
CREATE TABLE IF NOT EXISTS article_stock_snapshots (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    article_id BIGINT UNSIGNED NOT NULL COMMENT 'Foreign key to rss_items.id (BIGINT UNSIGNED)',
    ticker VARCHAR(20) NOT NULL,
    price_at_publication DECIMAL(12, 4) NULL COMMENT 'Stock price when article was published',
    price_current DECIMAL(12, 4) NULL COMMENT 'Current stock price (updated periodically)',
    price_change_since_article DECIMAL(8, 4) NULL COMMENT 'Percent change since article publication',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign key to rss_items
    FOREIGN KEY (article_id) REFERENCES rss_items(id) ON DELETE CASCADE,

    -- Indexes
    INDEX idx_article_id (article_id),
    INDEX idx_ticker (ticker),
    INDEX idx_created_at (created_at),

    -- Unique constraint
    UNIQUE KEY unique_article_ticker (article_id, ticker)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Links articles to stock price snapshots for correlation analysis';

-- Create a view for easy querying of articles with their stock performance
CREATE OR REPLACE VIEW v_articles_with_stock_performance AS
SELECT
    i.id,
    i.title,
    i.published_at,
    i.stock_tickers,
    i.company_names,
    ass.ticker,
    ass.price_at_publication,
    ass.price_current,
    ass.price_change_since_article,
    f.title as feed_title
FROM rss_items i
LEFT JOIN article_stock_snapshots ass ON i.id = ass.article_id
LEFT JOIN rss_feeds f ON i.feed_id = f.id
WHERE i.stock_tickers IS NOT NULL AND i.stock_tickers != '';

-- ============================================================================
-- Setup Complete!
-- ============================================================================

SELECT 'Database setup completed successfully!' AS status;

-- Show created tables
SELECT
    'Tables created:' AS info,
    GROUP_CONCAT(table_name ORDER BY table_name SEPARATOR ', ') AS tables
FROM information_schema.tables
WHERE table_schema = DATABASE()
AND table_name IN ('rss_feeds', 'rss_items', 'stock_prices', 'article_stock_snapshots');

-- Show view
SELECT
    'Views created:' AS info,
    GROUP_CONCAT(table_name ORDER BY table_name SEPARATOR ', ') AS views
FROM information_schema.views
WHERE table_schema = DATABASE()
AND table_name = 'v_articles_with_stock_performance';
