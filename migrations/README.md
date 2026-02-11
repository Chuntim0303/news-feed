# Database Migrations Guide

This directory contains all database migration scripts for the News Feed application.

## Quick Start - Two Options

### Option 1: Automated Script (Recommended) ⭐

The bash script automatically detects your database schema and runs the correct migrations:

```bash
cd migrations
./run_all_migrations.sh
```

**Features:**
- ✅ Automatically detects your `rss_items.id` column type
- ✅ Runs migrations in the correct order
- ✅ Checks if migrations already completed
- ✅ Fixes column type mismatches
- ✅ Provides colored output and progress tracking
- ✅ Verifies everything works at the end

**Requirements:**
- Bash shell
- MySQL client
- Database already created (`CREATE DATABASE news_feed;`)

### Option 2: Single SQL File

If you know your `rss_items.id` is **BIGINT UNSIGNED** (most common):

```bash
mysql -u your_user -p news_feed < migrations/setup_database.sql
```

**Note:** This assumes BIGINT UNSIGNED. If your setup is different, use Option 1 instead.

---

## Migration Files Overview

### Base Migrations

| File | Description | Creates |
|------|-------------|---------|
| `001_create_rss_tables.sql` | Creates base RSS feed tables | `rss_feeds`, `rss_items` |
| `002_add_stock_ticker_fields.sql` | Adds stock ticker columns | `stock_tickers`, `company_names` columns |
| `003_create_stock_prices_table*.sql` | Creates stock price tables | `stock_prices`, `article_stock_snapshots`, view |

### Migration 003 Variants

Migration 003 has multiple versions depending on your `rss_items.id` column type:

- `003_create_stock_prices_table.sql` - For **INT**
- `003_create_stock_prices_table_unsigned.sql` - For **INT UNSIGNED**
- `003_create_stock_prices_table_bigint.sql` - For **BIGINT**
- `003_create_stock_prices_table_bigint_unsigned.sql` - For **BIGINT UNSIGNED** ⭐ Most common

### Rollback Files

| File | Description |
|------|-------------|
| `001_rollback_rss_tables.sql` | Drops RSS tables |
| `002_rollback_stock_ticker_fields.sql` | Removes stock ticker columns |
| `003_rollback_stock_prices_table.sql` | Drops stock price tables |

### Helper Scripts

- `setup_database.sql` - Complete setup in one file (BIGINT UNSIGNED)
- `run_all_migrations.sh` - Automated migration runner ⭐
- `diagnose_exact_type.sql` - Diagnose your schema
- `check_column_types.sql` - Check column types

---

## Manual Step-by-Step (If Automated Script Fails)

### Step 1: Check Your Schema

Find out your `rss_items.id` column type:

```bash
mysql -u your_user -p news_feed -e "SHOW CREATE TABLE rss_items\G" | grep "id"
```

You'll see one of these:
- `id int` → Use **INT** versions
- `id int unsigned` → Use **INT UNSIGNED** versions
- `id bigint` → Use **BIGINT** versions
- `id bigint unsigned` → Use **BIGINT UNSIGNED** versions ⭐

### Step 2: Run Migration 001

```bash
mysql -u your_user -p news_feed < migrations/001_create_rss_tables.sql
```

### Step 3: Run Migration 002

```bash
mysql -u your_user -p news_feed < migrations/002_add_stock_ticker_fields.sql
```

### Step 4: Run the Correct Migration 003

Choose based on Step 1 result:

**For INT:**
```bash
mysql -u your_user -p news_feed < migrations/003_create_stock_prices_table.sql
```

**For INT UNSIGNED:**
```bash
mysql -u your_user -p news_feed < migrations/003_create_stock_prices_table_unsigned.sql
```

**For BIGINT:**
```bash
mysql -u your_user -p news_feed < migrations/003_create_stock_prices_table_bigint.sql
```

**For BIGINT UNSIGNED:** (most common)
```bash
mysql -u your_user -p news_feed < migrations/003_create_stock_prices_table_bigint_unsigned.sql
```

### Step 5: Verify

```bash
mysql -u your_user -p news_feed -e "SHOW TABLES;"
mysql -u your_user -p news_feed -e "SELECT * FROM v_articles_with_stock_performance LIMIT 1;"
```

---

## Troubleshooting

### Error: "Unknown column 'i.stock_tickers'"

**Cause:** You ran migration 003 before migration 002.

**Fix:**
```bash
# Rollback migration 003
mysql -u your_user -p news_feed < migrations/003_rollback_stock_prices_table.sql

# Run migration 002
mysql -u your_user -p news_feed < migrations/002_add_stock_ticker_fields.sql

# Run migration 003 again (correct version)
mysql -u your_user -p news_feed < migrations/003_create_stock_prices_table_bigint_unsigned.sql
```

### Error: "Referencing column 'article_id' and referenced column 'id' in foreign key constraint are incompatible"

**Cause:** Column type mismatch between `rss_items.id` and `article_stock_snapshots.article_id`.

**Fix:**
```bash
# Rollback migration 003
mysql -u your_user -p news_feed < migrations/003_rollback_stock_prices_table.sql

# Check your exact type
mysql -u your_user -p news_feed -e "SHOW CREATE TABLE rss_items\G" | grep "id"

# Run the matching migration 003 file
```

### Error: "Table already exists"

**Fix:** The table exists from a previous attempt. Either:

1. **Drop and recreate:**
   ```bash
   mysql -u your_user -p news_feed < migrations/003_rollback_stock_prices_table.sql
   # Then run the migration again
   ```

2. **Or just continue** - if the table structure is correct, you can skip this migration.

### Error: "Access denied for user"

**Cause:** Your MySQL user doesn't have sufficient privileges.

**Fix:**
```sql
-- As root user:
GRANT ALL PRIVILEGES ON news_feed.* TO 'your_user'@'localhost';
FLUSH PRIVILEGES;
```

---

## Database Schema Overview

After all migrations are complete, you'll have:

### Tables

1. **rss_feeds** - RSS feed sources
   - Stores feed URLs, titles, descriptions

2. **rss_items** - RSS articles
   - Stores articles with detected stock tickers and company names
   - References `rss_feeds`

3. **stock_prices** - Historical stock price data
   - Stores daily stock prices, volumes, market caps
   - Unique constraint on (ticker, date)

4. **article_stock_snapshots** - Article-Stock price links
   - Links articles to stock prices at publication time
   - Tracks price changes since article was published
   - References `rss_items`

### Views

1. **v_articles_with_stock_performance**
   - Joins articles with their stock performance data
   - Easy querying for analysis

---

## Environment Variables (for run_all_migrations.sh)

Set these before running the script:

```bash
export DB_USER="your_username"
export DB_NAME="news_feed"
export DB_HOST="localhost"
export DB_PORT="3306"

./run_all_migrations.sh
```

Or just run the script and it will use defaults (root, news_feed, localhost:3306).

---

## Need Help?

1. **Check schema:** `mysql -u user -p news_feed -e "SHOW CREATE TABLE rss_items\G"`
2. **List tables:** `mysql -u user -p news_feed -e "SHOW TABLES;"`
3. **View columns:** `mysql -u user -p news_feed -e "DESCRIBE table_name;"`

For more troubleshooting help, see:
- `QUICK_FIX.md` - Quick fixes for common errors
- `RUN_MIGRATIONS_IN_ORDER.md` - Detailed migration order guide
- `FIX_MIGRATION_003.md` - Specific fixes for migration 003

---

## Development

### Adding New Migrations

1. Create a new migration file: `00X_description.sql`
2. Create a rollback file: `00X_rollback_description.sql`
3. Update `run_all_migrations.sh` to include the new migration
4. Test on a clean database

### Best Practices

- ✅ Always create a rollback script
- ✅ Use `IF NOT EXISTS` where possible
- ✅ Add descriptive comments
- ✅ Test migrations on a copy of production data
- ✅ Run migrations during low-traffic periods
