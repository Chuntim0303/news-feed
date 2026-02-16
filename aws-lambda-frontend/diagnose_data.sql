-- Diagnostic queries to find out why no data is returned
-- Run these in MySQL Workbench or command line

-- 1. Check if rss_items exist at all
SELECT 
    COUNT(*) as total_articles,
    MIN(published_at) as earliest,
    MAX(published_at) as latest
FROM rss_items;

-- 2. Check if alert_log has scored articles
SELECT 
    COUNT(*) as total_scored,
    MIN(score_total) as min_score,
    MAX(score_total) as max_score,
    AVG(score_total) as avg_score
FROM alert_log;

-- 3. Check recent articles with scores
SELECT 
    ri.id,
    ri.title,
    DATE(ri.published_at) as pub_date,
    ri.stock_tickers,
    al.score_total
FROM rss_items ri
JOIN alert_log al ON al.rss_item_id = ri.id
ORDER BY ri.published_at DESC
LIMIT 10;

-- 4. Check if article_return_windows table exists and has data
SELECT 
    COUNT(*) as total_windows,
    COUNT(DISTINCT article_id) as unique_articles,
    processing_status,
    COUNT(*) as count_by_status
FROM article_return_windows
GROUP BY processing_status;

-- 5. Check date range of articles with returns
SELECT 
    DATE(ri.published_at) as pub_date,
    COUNT(*) as article_count,
    AVG(al.score_total) as avg_score
FROM rss_items ri
JOIN alert_log al ON al.rss_item_id = ri.id
LEFT JOIN article_return_windows arw ON arw.article_id = ri.id
WHERE arw.article_id IS NOT NULL
GROUP BY DATE(ri.published_at)
ORDER BY pub_date DESC
LIMIT 20;

-- 6. Check if there are articles in Feb 2026
SELECT 
    COUNT(*) as articles_in_feb_2026
FROM rss_items
WHERE DATE(published_at) BETWEEN '2026-02-01' AND '2026-02-28';

-- 7. Find the actual date range that has data
SELECT 
    DATE(ri.published_at) as pub_date,
    COUNT(DISTINCT ri.id) as articles,
    COUNT(DISTINCT arw.article_id) as with_returns,
    AVG(al.score_total) as avg_score
FROM rss_items ri
LEFT JOIN alert_log al ON al.rss_item_id = ri.id
LEFT JOIN article_return_windows arw ON arw.article_id = ri.id
GROUP BY DATE(ri.published_at)
HAVING articles > 0
ORDER BY pub_date DESC
LIMIT 30;
