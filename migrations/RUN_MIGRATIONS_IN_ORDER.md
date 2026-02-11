# Migration Order Fix

## The Issue
Migration 003 creates a view that references columns that don't exist yet!

The view tries to use:
- `i.stock_tickers`
- `i.company_names`

But these are added by **migration 002**, which you haven't run yet.

## The Fix: Run Migrations in Order

### Step 1: Run Migration 002 First
```bash
# This adds the stock_tickers and company_names columns
mysql -u your_user -p news_feed < migrations/002_add_stock_ticker_fields.sql
```

### Step 2: Check Your rss_items.id Type
```bash
mysql -u your_user -p news_feed -e "SHOW CREATE TABLE rss_items\G" | grep "id bigint"
```

Look for:
- `id bigint unsigned` → Use UNSIGNED version
- `id bigint` (no unsigned) → Use regular BIGINT version

### Step 3: Clean Up Any Failed Migration 003 Attempts
```bash
mysql -u your_user -p news_feed < migrations/003_rollback_stock_prices_table.sql
```

### Step 4: Run the Correct Migration 003

**If you have BIGINT UNSIGNED:**
```bash
mysql -u your_user -p news_feed < migrations/003_create_stock_prices_table_bigint_unsigned.sql
```

**If you have plain BIGINT:**
```bash
mysql -u your_user -p news_feed < migrations/003_create_stock_prices_table_bigint.sql
```

### Step 5: Verify Everything Works
```bash
mysql -u your_user -p news_feed -e "SELECT * FROM v_articles_with_stock_performance LIMIT 1;"
```

If this runs without errors, you're good! ✅

## Quick One-Liner (if you know your type)

For **BIGINT UNSIGNED** (most common):
```bash
mysql -u your_user -p news_feed < migrations/002_add_stock_ticker_fields.sql && \
mysql -u your_user -p news_feed < migrations/003_rollback_stock_prices_table.sql && \
mysql -u your_user -p news_feed < migrations/003_create_stock_prices_table_bigint_unsigned.sql
```

For **plain BIGINT**:
```bash
mysql -u your_user -p news_feed < migrations/002_add_stock_ticker_fields.sql && \
mysql -u your_user -p news_feed < migrations/003_rollback_stock_prices_table.sql && \
mysql -u your_user -p news_feed < migrations/003_create_stock_prices_table_bigint.sql
```

## Why This Happened
Migration 003 depends on columns from migration 002, but the migrations weren't numbered clearly enough to show this dependency. Always run migrations in numerical order!
