-- Migration 007: Create bot_settings table for Telegram bot user preferences
--
-- Stores per-chat settings for the Telegram bot interface.
-- Each chat (user or group) gets one row of settings.

CREATE TABLE IF NOT EXISTS bot_settings (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    chat_id         VARCHAR(50) NOT NULL COMMENT 'Telegram chat ID',
    alert_mode      ENUM('normal', 'quiet') NOT NULL DEFAULT 'normal' COMMENT 'normal = all alerts, quiet = urgent only',
    alert_threshold INT NOT NULL DEFAULT 1 COMMENT 'Min keyword matches to trigger alert (1 = any match)',
    morning_brief   TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Receive morning brief digest',
    eod_recap       TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Receive end-of-day recap',
    weekly_report   TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Receive weekly report',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_chat_id (chat_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Track which sources are enabled/disabled per chat
CREATE TABLE IF NOT EXISTS bot_source_settings (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    chat_id     VARCHAR(50) NOT NULL COMMENT 'Telegram chat ID',
    source_name VARCHAR(100) NOT NULL COMMENT 'Feed source name (e.g. bloomberg, fiercebiotech)',
    is_enabled  TINYINT(1) NOT NULL DEFAULT 1,
    UNIQUE KEY uk_chat_source (chat_id, source_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
