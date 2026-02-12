-- Migration 006: Create alert_keywords table and alert_log table
--
-- Keywords are matched (case-insensitive) against article title and summary
-- during RSS feed ingestion. Matches trigger a Telegram alert.
--
-- Users can manage keywords via Telegram bot commands:
--   /add <keyword>    — add a keyword
--   /remove <keyword> — remove a keyword
--   /list             — list all active keywords

-- NOTE: Column types must match the referenced tables exactly.
-- Run this first to check your rss_items.id type:
--   SELECT COLUMN_NAME, COLUMN_TYPE FROM INFORMATION_SCHEMA.COLUMNS
--   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'rss_items' AND COLUMN_NAME = 'id';

CREATE TABLE IF NOT EXISTS alert_keywords (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    keyword     VARCHAR(255) NOT NULL,
    is_active   TINYINT(1)  NOT NULL DEFAULT 1,
    created_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by  VARCHAR(100) DEFAULT NULL COMMENT 'Telegram user who added this keyword',
    UNIQUE KEY uk_keyword (keyword)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Log of alerts sent, to avoid duplicate notifications
-- rss_item_id type must match rss_items.id exactly
CREATE TABLE IF NOT EXISTS alert_log (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    rss_item_id     BIGINT UNSIGNED NOT NULL,
    keyword_id      INT UNSIGNED NOT NULL,
    keyword         VARCHAR(255) NOT NULL,
    sent_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_item_keyword (rss_item_id, keyword_id),
    FOREIGN KEY (rss_item_id) REFERENCES rss_items(id) ON DELETE CASCADE,
    FOREIGN KEY (keyword_id)  REFERENCES alert_keywords(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
