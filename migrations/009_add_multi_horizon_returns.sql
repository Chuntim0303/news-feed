-- Migration 009: Add multi-horizon event study infrastructure
--
-- Implements improvements for better stock impact analysis:
--   1. Multi-horizon return windows (1D, 3D, 5D, 10D) with pre-event baseline
--   2. Benchmark tracking for abnormal return calculations
--   3. Volume and volatility metrics for market reaction scoring
--   4. Intraday timestamp precision and session classification
--   5. Ticker relevance weighting for multi-company articles
--   6. Processing status tracking with retry logic
--   7. Confounder flags for event clustering
--
-- This replaces the simple "next-day change" with proper event study methodology.

-- ============================================================================
-- 1. Multi-Horizon Return Windows Table
-- ============================================================================
-- Stores returns at multiple horizons for each article-ticker pair
CREATE TABLE IF NOT EXISTS article_return_windows (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    article_id BIGINT UNSIGNED COMMENT 'Foreign key to rss_items.id',
    ticker VARCHAR(20) NOT NULL,
    
    -- Pre-event baseline (for leakage/anticipation detection)
    return_pre_1d DECIMAL(8, 4) NULL COMMENT 'Return -1 day before publication',
    return_pre_3d DECIMAL(8, 4) NULL COMMENT 'Return -3 days before publication',
    return_pre_5d DECIMAL(8, 4) NULL COMMENT 'Return -5 days before publication',
    
    -- Post-event windows
    return_1d DECIMAL(8, 4) NULL COMMENT 'Return +1 day after publication',
    return_3d DECIMAL(8, 4) NULL COMMENT 'Return +3 days after publication',
    return_5d DECIMAL(8, 4) NULL COMMENT 'Return +5 days after publication',
    return_10d DECIMAL(8, 4) NULL COMMENT 'Return +10 days after publication',
    
    -- Abnormal returns (stock return - benchmark return)
    abnormal_return_1d DECIMAL(8, 4) NULL COMMENT 'Abnormal return vs benchmark +1D',
    abnormal_return_3d DECIMAL(8, 4) NULL COMMENT 'Abnormal return vs benchmark +3D',
    abnormal_return_5d DECIMAL(8, 4) NULL COMMENT 'Abnormal return vs benchmark +5D',
    abnormal_return_10d DECIMAL(8, 4) NULL COMMENT 'Abnormal return vs benchmark +10D',
    
    -- Volume metrics
    volume_baseline_20d BIGINT NULL COMMENT '20-day average volume before event',
    volume_1d BIGINT NULL COMMENT 'Volume on +1 day',
    volume_ratio_1d DECIMAL(6, 2) NULL COMMENT 'Volume ratio vs baseline',
    volume_zscore_1d DECIMAL(6, 2) NULL COMMENT 'Volume z-score vs baseline',
    
    -- Volatility metrics
    volatility_baseline_20d DECIMAL(8, 4) NULL COMMENT '20-day realized volatility before event',
    intraday_range_1d DECIMAL(8, 4) NULL COMMENT '(High - Low) / Open on +1 day',
    gap_magnitude DECIMAL(8, 4) NULL COMMENT 'Gap from prev close to open',
    
    -- Processing metadata
    processing_status ENUM('not_started', 'partial', 'complete', 'failed') 
        DEFAULT 'not_started' COMMENT 'Processing status for retry logic',
    retry_count TINYINT UNSIGNED DEFAULT 0 COMMENT 'Number of retry attempts',
    failure_reason VARCHAR(255) NULL COMMENT 'Reason for processing failure',
    last_processed_at TIMESTAMP NULL COMMENT 'Last processing attempt timestamp',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_article_id (article_id),
    INDEX idx_ticker (ticker),
    INDEX idx_processing_status (processing_status),
    INDEX idx_last_processed (last_processed_at),
    UNIQUE KEY unique_article_ticker (article_id, ticker),
    
    CONSTRAINT fk_return_windows_article
        FOREIGN KEY (article_id) REFERENCES rss_items(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Multi-horizon event study returns for article-ticker pairs';

-- ============================================================================
-- 2. Benchmark Returns Table
-- ============================================================================
-- Stores daily returns for market and sector benchmarks (SPY, XBI, XLV, etc.)
CREATE TABLE IF NOT EXISTS benchmark_returns (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL COMMENT 'Benchmark ticker (SPY, XBI, XLV, etc.)',
    return_date DATE NOT NULL COMMENT 'Trading date',
    
    close_price DECIMAL(12, 4) NOT NULL,
    open_price DECIMAL(12, 4) NULL,
    high_price DECIMAL(12, 4) NULL,
    low_price DECIMAL(12, 4) NULL,
    volume BIGINT NULL,
    
    return_1d DECIMAL(8, 4) NULL COMMENT 'Daily return',
    return_3d DECIMAL(8, 4) NULL COMMENT '3-day cumulative return',
    return_5d DECIMAL(8, 4) NULL COMMENT '5-day cumulative return',
    return_10d DECIMAL(8, 4) NULL COMMENT '10-day cumulative return',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_ticker (ticker),
    INDEX idx_return_date (return_date),
    UNIQUE KEY unique_ticker_date (ticker, return_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Benchmark returns for abnormal return calculations';

-- ============================================================================
-- 3. Sector-Ticker Mapping Table
-- ============================================================================
-- Maps tickers to their sector benchmarks for abnormal return calculations
CREATE TABLE IF NOT EXISTS ticker_sector_mapping (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    sector VARCHAR(50) NOT NULL COMMENT 'Sector name (Healthcare, Technology, etc.)',
    sector_etf VARCHAR(20) NULL COMMENT 'Sector ETF ticker (XLV, XBI, XLK, etc.)',
    market_benchmark VARCHAR(20) DEFAULT 'SPY' COMMENT 'Market benchmark ticker',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_ticker (ticker),
    INDEX idx_sector (sector),
    UNIQUE KEY unique_ticker (ticker)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Maps tickers to sector benchmarks for abnormal return calculations';

-- ============================================================================
-- 4. Enhanced Article-Stock Snapshots
-- ============================================================================
-- Add new columns to existing article_stock_snapshots table
ALTER TABLE article_stock_snapshots
ADD COLUMN ticker_relevance_score DECIMAL(4, 2) DEFAULT 1.0 
    COMMENT 'Relevance weight 0-1 for multi-ticker articles',
ADD COLUMN mention_count TINYINT UNSIGNED DEFAULT 1 
    COMMENT 'Number of times ticker mentioned in article',
ADD COLUMN in_title TINYINT(1) DEFAULT 0 
    COMMENT '1 if ticker/company mentioned in title',
ADD COLUMN publish_session ENUM('pre_market', 'regular', 'post_market', 'unknown') 
    DEFAULT 'unknown' COMMENT 'Market session when article published',
ADD COLUMN publish_timestamp TIMESTAMP NULL 
    COMMENT 'Precise publication timestamp for intraday analysis';

-- ============================================================================
-- 5. Confounder Events Table
-- ============================================================================
-- Tracks known confounding events (earnings, FDA calendar, macro events)
CREATE TABLE IF NOT EXISTS confounder_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_date DATE NOT NULL,
    ticker VARCHAR(20) NULL COMMENT 'NULL for market-wide events',
    event_type ENUM('earnings', 'fda_pdufa', 'fed_meeting', 'cpi_release', 
                    'sector_move', 'other') NOT NULL,
    event_description VARCHAR(255) NULL,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_event_date (event_date),
    INDEX idx_ticker (ticker),
    INDEX idx_event_type (event_type),
    INDEX idx_ticker_date (ticker, event_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Known confounding events for attribution analysis';

-- ============================================================================
-- 6. Article Similarity Clusters
-- ============================================================================
-- Groups near-identical articles for duplicate event handling
CREATE TABLE IF NOT EXISTS article_clusters (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    cluster_date DATE NOT NULL COMMENT 'Date of clustered articles',
    ticker VARCHAR(20) NOT NULL,
    representative_article_id BIGINT UNSIGNED COMMENT 'Primary article in cluster',
    article_ids TEXT NOT NULL COMMENT 'Comma-separated list of article IDs',
    similarity_method VARCHAR(50) DEFAULT 'headline_fuzzy' 
        COMMENT 'Method used for clustering',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_cluster_date (cluster_date),
    INDEX idx_ticker (ticker),
    INDEX idx_representative (representative_article_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Clusters of duplicate/similar articles for deduplication';

-- ============================================================================
-- 7. Market Reaction Score Cache
-- ============================================================================
-- Caches computed Layer 4 market reaction scores
CREATE TABLE IF NOT EXISTS market_reaction_scores (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    article_id BIGINT UNSIGNED,
    ticker VARCHAR(20) NOT NULL,
    
    volume_score DECIMAL(4, 2) DEFAULT 0 COMMENT 'Score from volume spike (0-2)',
    gap_score DECIMAL(4, 2) DEFAULT 0 COMMENT 'Score from price gap (0-2)',
    trend_score DECIMAL(4, 2) DEFAULT 0 COMMENT 'Score from trending mentions (0-1)',
    total_reaction_score DECIMAL(4, 2) DEFAULT 0 COMMENT 'Sum of reaction scores (0-5)',
    
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_article_id (article_id),
    INDEX idx_ticker (ticker),
    UNIQUE KEY unique_article_ticker (article_id, ticker),
    
    CONSTRAINT fk_reaction_scores_article
        FOREIGN KEY (article_id) REFERENCES rss_items(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Cached Layer 4 market reaction scores for articles';

-- ============================================================================
-- 8. Backtesting Results Table
-- ============================================================================
-- Stores calibration and backtesting metrics for model tuning
CREATE TABLE IF NOT EXISTS scoring_backtest_results (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    backtest_date DATE NOT NULL COMMENT 'Date of backtest run',
    score_bucket VARCHAR(20) NOT NULL COMMENT 'Score range (e.g., "10-15", "15-20")',
    
    article_count INT NOT NULL COMMENT 'Number of articles in bucket',
    avg_abnormal_return_1d DECIMAL(8, 4) NULL,
    avg_abnormal_return_3d DECIMAL(8, 4) NULL,
    avg_abnormal_return_5d DECIMAL(8, 4) NULL,
    
    hit_rate DECIMAL(5, 2) NULL COMMENT 'Percentage with |abnormal_return_1d| > 2%',
    precision_at_k INT NULL COMMENT 'Precision@K metric',
    
    config_params JSON NULL COMMENT 'Model parameters used for this backtest',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_backtest_date (backtest_date),
    INDEX idx_score_bucket (score_bucket)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Backtesting results for model calibration and tuning';

-- ============================================================================
-- 9. Update alert_log for Layer 4 integration
-- ============================================================================
ALTER TABLE alert_log
ADD COLUMN score_market_reaction DECIMAL(4, 2) DEFAULT 0 
    COMMENT 'Layer 4: Market reaction score (0-5)';

-- ============================================================================
-- Seed common sector mappings
-- ============================================================================
INSERT INTO ticker_sector_mapping (ticker, sector, sector_etf, market_benchmark) VALUES
('MRNA', 'Healthcare', 'XBI', 'SPY'),
('PFE', 'Healthcare', 'XLV', 'SPY'),
('JNJ', 'Healthcare', 'XLV', 'SPY'),
('ABBV', 'Healthcare', 'XLV', 'SPY'),
('LLY', 'Healthcare', 'XLV', 'SPY'),
('NVO', 'Healthcare', 'XBI', 'SPY'),
('GILD', 'Healthcare', 'XBI', 'SPY'),
('REGN', 'Healthcare', 'XBI', 'SPY'),
('VRTX', 'Healthcare', 'XBI', 'SPY'),
('BIIB', 'Healthcare', 'XBI', 'SPY'),
('AMGN', 'Healthcare', 'XBI', 'SPY'),
('GOOGL', 'Technology', 'XLK', 'SPY'),
('AAPL', 'Technology', 'XLK', 'SPY'),
('MSFT', 'Technology', 'XLK', 'SPY'),
('NVDA', 'Technology', 'XLK', 'SPY'),
('TSLA', 'Consumer Discretionary', 'XLY', 'SPY')
ON DUPLICATE KEY UPDATE 
    sector = VALUES(sector),
    sector_etf = VALUES(sector_etf);
