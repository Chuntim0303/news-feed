-- Migration 008: Add news scoring model columns
--
-- Adds scoring infrastructure for the composite news scoring model:
--   1. event_score on alert_keywords (user-assigned importance per keyword)
--   2. market_cap_usd on companies (for market cap multiplier)
--   3. Score breakdown columns on alert_log (for auditing and /why command)
--
-- See NEWS_SCORING_MODEL.md for full documentation.

-- 1. Add event_score to alert_keywords
--    Each keyword gets a score 1-10 representing its significance.
--    Default = 5 (moderate importance).
ALTER TABLE alert_keywords
ADD COLUMN event_score TINYINT UNSIGNED NOT NULL DEFAULT 5
    COMMENT 'Impact score 1-10, used in news scoring model';

-- 2. Add market_cap_usd to companies
--    Stored in whole USD. Used to compute the market cap multiplier:
--      < $1B   → ×1.6
--      $1B-5B  → ×1.3
--      $5B-20B → ×1.1
--      > $20B  → ×1.0
ALTER TABLE companies
ADD COLUMN market_cap_usd BIGINT UNSIGNED DEFAULT NULL
    COMMENT 'Market capitalization in USD, for scoring multiplier';

-- 3. Add score breakdown columns to alert_log
--    Every keyword match is logged with its full score breakdown,
--    regardless of whether an alert was actually sent.
ALTER TABLE alert_log
ADD COLUMN score_total     DECIMAL(6,2) DEFAULT NULL COMMENT 'Final composite score',
ADD COLUMN score_keyword   DECIMAL(6,2) DEFAULT NULL COMMENT 'Sum of matched keyword event_scores',
ADD COLUMN score_cap_mult  DECIMAL(4,2) DEFAULT NULL COMMENT 'Market cap multiplier applied (1.0-1.6)',
ADD COLUMN score_surprise  DECIMAL(4,2) DEFAULT NULL COMMENT 'Surprise phrase score (0-5)',
ADD COLUMN surprise_dir    ENUM('positive','negative','mixed','none') DEFAULT 'none'
    COMMENT 'Direction of surprise phrases detected',
ADD COLUMN alert_sent      TINYINT(1) NOT NULL DEFAULT 1
    COMMENT '1 = alert was sent to Telegram, 0 = below threshold (silent log)';
