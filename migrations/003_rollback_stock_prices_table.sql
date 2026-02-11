-- Rollback Migration 003: Drop stock prices tables and views

DROP VIEW IF EXISTS v_articles_with_stock_performance;

DROP TABLE IF EXISTS article_stock_snapshots;

DROP TABLE IF EXISTS stock_prices;
