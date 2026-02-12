-- Rollback Migration 006: Remove alert_keywords and alert_log tables

DROP TABLE IF EXISTS alert_log;
DROP TABLE IF EXISTS alert_keywords;
