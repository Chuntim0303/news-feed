-- Rollback Migration 008: Remove news scoring model columns

ALTER TABLE alert_log
DROP COLUMN IF EXISTS alert_sent,
DROP COLUMN IF EXISTS surprise_dir,
DROP COLUMN IF EXISTS score_surprise,
DROP COLUMN IF EXISTS score_cap_mult,
DROP COLUMN IF EXISTS score_keyword,
DROP COLUMN IF EXISTS score_total;

ALTER TABLE companies
DROP COLUMN IF EXISTS market_cap_usd;

ALTER TABLE alert_keywords
DROP COLUMN IF EXISTS event_score;
