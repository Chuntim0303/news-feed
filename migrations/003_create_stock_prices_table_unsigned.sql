-- Migration 003 (UNSIGNED version): Create stock prices tables
-- Use this version if your rss_items.id column is INT UNSIGNED
-- Check by running: SHOW CREATE TABLE rss_items;

-- Stock prices table
CREATE TABLE IF NOT EXISTS stock_prices (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
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
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    article_id INT UNSIGNED NOT NULL COMMENT 'Foreign key to rss_items.id',
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
