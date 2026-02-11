# Quick Fix for Migration 003 Error

## Step 1: Find Out Your Exact Column Type

Run this command:

```bash
mysql -u your_user -p news_feed < migrations/diagnose_exact_type.sql
```

Look for the output from `SHOW CREATE TABLE rss_items`. Find the line with `id`:

**Example outputs:**
- `id bigint NOT NULL AUTO_INCREMENT` → Use **BIGINT** version
- `id bigint unsigned NOT NULL AUTO_INCREMENT` → Use **BIGINT UNSIGNED** version
- `id int NOT NULL AUTO_INCREMENT` → Use **INT** version

## Step 2: Clean Up Any Failed Attempts

```bash
mysql -u your_user -p news_feed < migrations/003_rollback_stock_prices_table.sql
```

## Step 3: Run the Correct Migration

### If you saw `bigint` (lowercase, no unsigned):

```bash
mysql -u your_user -p news_feed < migrations/003_create_stock_prices_table_bigint.sql
```

### If you saw `bigint unsigned`:

```bash
mysql -u your_user -p news_feed < migrations/003_create_stock_prices_table_bigint_unsigned.sql
```

### If you saw just `int` (no bigint):

```bash
mysql -u your_user -p news_feed < migrations/003_create_stock_prices_table.sql
```

## Step 4: Verify Success

```bash
mysql -u your_user -p news_feed -e "SHOW TABLES LIKE '%stock%';"
```

You should see:
- `article_stock_snapshots`
- `stock_prices`

Then verify the column types match:

```bash
mysql -u your_user -p news_feed -e "SHOW CREATE TABLE article_stock_snapshots\G"
```

Look for `article_id` - it should have the SAME type as `rss_items.id`.

## Still Having Issues?

If you're still getting errors after trying the correct migration:

1. **Check for existing tables from failed attempts:**
   ```bash
   mysql -u your_user -p news_feed -e "DROP TABLE IF EXISTS article_stock_snapshots; DROP TABLE IF EXISTS stock_prices; DROP VIEW IF EXISTS v_articles_with_stock_performance;"
   ```

2. **Try again with the correct migration file**

3. **If FK constraint still fails, you can skip it:**
   The tables will work fine without the foreign key constraint. Just remove the FK lines from the migration file before running it.

## Common Issues

1. **"Table already exists"** → Run the rollback script first
2. **"Incompatible columns"** → You're using the wrong migration version (check Step 1 again)
3. **"Access denied"** → Check your MySQL user has permissions to create tables/indexes/foreign keys

## Need More Help?

Post the output of this command:

```bash
mysql -u your_user -p news_feed -e "SHOW CREATE TABLE rss_items\G" 2>&1
```

This will show us exactly what your schema looks like.
