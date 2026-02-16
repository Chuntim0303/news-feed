-- Check the exact data type of rss_items.id
SELECT 
    COLUMN_NAME,
    COLUMN_TYPE,
    DATA_TYPE,
    COLUMN_KEY,
    EXTRA
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'news_feed'
  AND TABLE_NAME = 'rss_items'
  AND COLUMN_NAME = 'id';

-- Also check article_stock_snapshots.article_id for reference
SELECT 
    COLUMN_NAME,
    COLUMN_TYPE,
    DATA_TYPE,
    COLUMN_KEY,
    EXTRA
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'news_feed'
  AND TABLE_NAME = 'article_stock_snapshots'
  AND COLUMN_NAME = 'article_id';
