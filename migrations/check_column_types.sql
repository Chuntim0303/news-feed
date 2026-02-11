-- Diagnostic script to check column types
-- Run this to see the exact type of rss_items.id column

SELECT
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_TYPE,
    DATA_TYPE,
    IS_NULLABLE,
    COLUMN_KEY,
    EXTRA
FROM
    INFORMATION_SCHEMA.COLUMNS
WHERE
    TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'rss_items'
    AND COLUMN_NAME = 'id';

-- Also check rss_feeds.id for comparison
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_TYPE,
    DATA_TYPE,
    IS_NULLABLE,
    COLUMN_KEY,
    EXTRA
FROM
    INFORMATION_SCHEMA.COLUMNS
WHERE
    TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'rss_feeds'
    AND COLUMN_NAME = 'id';
