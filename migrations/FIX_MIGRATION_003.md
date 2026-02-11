# How to Fix Migration 003 Foreign Key Error

## The Problem

You're getting this error when running migration 003:
```
Error Code: 3780. Referencing column 'article_id' and referenced column 'id' in foreign key constraint 'article_stock_snapshots_ibfk_1' are incompatible.
```

This happens because the `article_id` column type doesn't exactly match the `rss_items.id` column type.

## Step 1: Check Your Current Schema

Run this command to check the exact type of your `rss_items.id` column:

```bash
mysql -u your_user -p news_feed < migrations/check_column_types.sql
```

Or manually:

```sql
SHOW CREATE TABLE rss_items;
```

Look for the `id` column definition. You'll see one of these:
- `id INT AUTO_INCREMENT PRIMARY KEY` (signed integer)
- `id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY` (unsigned integer)
- `id BIGINT AUTO_INCREMENT PRIMARY KEY` (big integer - **most common**)
- `id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY` (unsigned big integer)

## Step 2: Choose the Right Migration

### Option A: If `id` is `BIGINT` - **MOST COMMON** ⭐

This is the most common configuration. Use:

```bash
mysql -u your_user -p news_feed < migrations/003_create_stock_prices_table_bigint.sql
```

### Option B: If `id` is `BIGINT UNSIGNED`

Same as Option A - the bigint migration works for both signed and unsigned BIGINT.

### Option C: If `id` is `INT` (signed)

Use the original migration:

```bash
mysql -u your_user -p news_feed < migrations/003_create_stock_prices_table.sql
```

If this fails, try the v2 version which adds the foreign key separately:

```bash
mysql -u your_user -p news_feed < migrations/003_create_stock_prices_table_v2.sql
```

### Option D: If `id` is `INT UNSIGNED`

Use the unsigned version:

```bash
mysql -u your_user -p news_feed < migrations/003_create_stock_prices_table_unsigned.sql
```

## Step 3: If You Already Tried and Failed

If you already ran one of the migrations and it partially succeeded, first clean up:

```bash
mysql -u your_user -p news_feed < migrations/003_rollback_stock_prices_table.sql
```

Then run the correct version from Step 2.

## Step 4: Manual Fix (If All Else Fails)

If you're still having issues, create the tables manually without the foreign key:

```sql
-- 1. Create stock_prices table (this should always work)
CREATE TABLE IF NOT EXISTS stock_prices (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,  -- Use BIGINT to match rss_items
    ticker VARCHAR(20) NOT NULL,
    price DECIMAL(12, 4) NOT NULL,
    price_date DATE NOT NULL,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ticker (ticker),
    INDEX idx_ticker_date (ticker, price_date),
    UNIQUE KEY unique_ticker_date (ticker, price_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Create article_stock_snapshots WITHOUT foreign key
CREATE TABLE IF NOT EXISTS article_stock_snapshots (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,  -- Use BIGINT to match rss_items
    article_id BIGINT NOT NULL,  -- MUST match rss_items.id type exactly
    ticker VARCHAR(20) NOT NULL,
    price_at_publication DECIMAL(12, 4) NULL,
    price_current DECIMAL(12, 4) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_article_id (article_id),
    INDEX idx_ticker (ticker),
    UNIQUE KEY unique_article_ticker (article_id, ticker)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Try to add the foreign key
-- If this fails, you can skip it and just use the indexes
ALTER TABLE article_stock_snapshots
ADD CONSTRAINT fk_article_stock_snapshots_article
    FOREIGN KEY (article_id) REFERENCES rss_items(id) ON DELETE CASCADE;
```

## Alternative: Skip Foreign Keys

Foreign keys are nice for data integrity, but not strictly required. If you continue to have issues, you can:

1. Use the tables WITHOUT the foreign key constraint
2. Handle referential integrity in your application code
3. The indexes will still allow efficient queries

The extraction system will work fine either way!

## Verify Success

After successfully running the migration, verify the tables exist:

```sql
SHOW TABLES LIKE '%stock%';

DESCRIBE stock_prices;
DESCRIBE article_stock_snapshots;
```

You should see both tables created successfully.
