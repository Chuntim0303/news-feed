-- Run this to see the EXACT column definition
SHOW CREATE TABLE rss_items;

-- Also check the exact data type details
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_KEY,
    EXTRA
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'rss_items'
  AND COLUMN_NAME = 'id';

-- Check if tables from previous attempt exist
SHOW TABLES LIKE '%stock%';

-- If article_stock_snapshots exists, check its column type
SELECT
    COLUMN_NAME,
    COLUMN_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'article_stock_snapshots'
  AND COLUMN_NAME IN ('id', 'article_id');
