#!/bin/bash

# Migration Runner Script
# Runs all migrations in the correct order with error checking

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Database credentials (customize these)
DB_USER="${DB_USER:-root}"
DB_NAME="${DB_NAME:-news_feed}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-3306}"

# Function to print colored output
print_info() {
    echo -e "${BLUE}ℹ ${1}${NC}"
}

print_success() {
    echo -e "${GREEN}✓ ${1}${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ ${1}${NC}"
}

print_error() {
    echo -e "${RED}✗ ${1}${NC}"
}

# Function to run SQL command
run_sql() {
    mysql -u "$DB_USER" -p"$DB_PASS" -h "$DB_HOST" -P "$DB_PORT" "$DB_NAME" -e "$1" 2>&1
}

# Function to run SQL file
run_sql_file() {
    mysql -u "$DB_USER" -p"$DB_PASS" -h "$DB_HOST" -P "$DB_PORT" "$DB_NAME" < "$1" 2>&1
}

# Function to check if table exists
table_exists() {
    result=$(mysql -u "$DB_USER" -p"$DB_PASS" -h "$DB_HOST" -P "$DB_PORT" "$DB_NAME" -sse "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '$DB_NAME' AND table_name = '$1';" 2>&1)
    [ "$result" -eq "1" ]
}

# Function to check if column exists
column_exists() {
    result=$(mysql -u "$DB_USER" -p"$DB_PASS" -h "$DB_HOST" -P "$DB_PORT" "$DB_NAME" -sse "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = '$DB_NAME' AND table_name = '$1' AND column_name = '$2';" 2>&1)
    [ "$result" -eq "1" ]
}

# Get database password
echo ""
print_info "MySQL Migration Runner"
echo "======================="
echo ""
print_info "Database: ${DB_NAME}"
print_info "User: ${DB_USER}"
print_info "Host: ${DB_HOST}:${DB_PORT}"
echo ""
read -sp "Enter MySQL password: " DB_PASS
echo ""
echo ""

# Test database connection
print_info "Testing database connection..."
if ! run_sql "SELECT 1;" > /dev/null 2>&1; then
    print_error "Failed to connect to database. Please check your credentials."
    exit 1
fi
print_success "Connected to database successfully"
echo ""

# Check current database state
print_info "Checking current database state..."
echo ""

# Migration 001: Create RSS tables
print_info "Step 1: Checking base RSS tables..."
if table_exists "rss_feeds" && table_exists "rss_items"; then
    print_success "Base RSS tables already exist"
else
    print_warning "Base RSS tables not found. Running migration 001..."
    if run_sql_file "migrations/001_create_rss_tables.sql" > /dev/null 2>&1; then
        print_success "Migration 001 completed: RSS tables created"
    else
        print_error "Migration 001 failed"
        exit 1
    fi
fi
echo ""

# Migration 002: Add stock ticker fields
print_info "Step 2: Checking stock ticker columns..."
if column_exists "rss_items" "stock_tickers" && column_exists "rss_items" "company_names"; then
    print_success "Stock ticker columns already exist"
else
    print_warning "Stock ticker columns not found. Running migration 002..."
    if run_sql_file "migrations/002_add_stock_ticker_fields.sql" > /dev/null 2>&1; then
        print_success "Migration 002 completed: Stock ticker columns added"
    else
        print_error "Migration 002 failed"
        exit 1
    fi
fi
echo ""

# Migration 003: Detect ID type and create stock price tables
print_info "Step 3: Detecting rss_items.id column type..."
ID_TYPE=$(mysql -u "$DB_USER" -p"$DB_PASS" -h "$DB_HOST" -P "$DB_PORT" "$DB_NAME" -sse "SELECT COLUMN_TYPE FROM information_schema.columns WHERE table_schema = '$DB_NAME' AND table_name = 'rss_items' AND column_name = 'id';" 2>&1)

print_info "Detected ID type: ${ID_TYPE}"

# Determine which migration file to use
if [[ "$ID_TYPE" == *"unsigned"* ]]; then
    if [[ "$ID_TYPE" == "bigint"* ]]; then
        MIGRATION_FILE="migrations/003_create_stock_prices_table_bigint_unsigned.sql"
        print_info "Using: BIGINT UNSIGNED migration"
    else
        MIGRATION_FILE="migrations/003_create_stock_prices_table_unsigned.sql"
        print_info "Using: INT UNSIGNED migration"
    fi
else
    if [[ "$ID_TYPE" == "bigint"* ]]; then
        MIGRATION_FILE="migrations/003_create_stock_prices_table_bigint.sql"
        print_info "Using: BIGINT migration"
    else
        MIGRATION_FILE="migrations/003_create_stock_prices_table.sql"
        print_info "Using: INT migration"
    fi
fi

# Check if stock price tables already exist
if table_exists "stock_prices" && table_exists "article_stock_snapshots"; then
    print_success "Stock price tables already exist"

    # Check if we need to recreate them (column type mismatch)
    ARTICLE_ID_TYPE=$(mysql -u "$DB_USER" -p"$DB_PASS" -h "$DB_HOST" -P "$DB_PORT" "$DB_NAME" -sse "SELECT COLUMN_TYPE FROM information_schema.columns WHERE table_schema = '$DB_NAME' AND table_name = 'article_stock_snapshots' AND column_name = 'article_id';" 2>&1)

    if [[ "$ARTICLE_ID_TYPE" != "$ID_TYPE" ]]; then
        print_warning "Column type mismatch detected!"
        print_warning "rss_items.id: ${ID_TYPE}"
        print_warning "article_stock_snapshots.article_id: ${ARTICLE_ID_TYPE}"
        print_warning "Dropping and recreating tables..."

        if run_sql_file "migrations/003_rollback_stock_prices_table.sql" > /dev/null 2>&1; then
            print_success "Old tables dropped"
        else
            print_error "Failed to drop old tables"
            exit 1
        fi

        if run_sql_file "$MIGRATION_FILE" > /dev/null 2>&1; then
            print_success "Migration 003 completed: Stock price tables created"
        else
            print_error "Migration 003 failed"
            exit 1
        fi
    fi
else
    print_warning "Stock price tables not found. Running migration 003..."

    # Clean up any partially created tables
    run_sql_file "migrations/003_rollback_stock_prices_table.sql" > /dev/null 2>&1 || true

    if run_sql_file "$MIGRATION_FILE" > /dev/null 2>&1; then
        print_success "Migration 003 completed: Stock price tables created"
    else
        print_error "Migration 003 failed. Output:"
        run_sql_file "$MIGRATION_FILE"
        exit 1
    fi
fi
echo ""

# Final verification
print_info "Verifying all tables..."
TABLES=("rss_feeds" "rss_items" "stock_prices" "article_stock_snapshots")
ALL_GOOD=true

for table in "${TABLES[@]}"; do
    if table_exists "$table"; then
        print_success "Table '${table}' exists"
    else
        print_error "Table '${table}' is missing!"
        ALL_GOOD=false
    fi
done
echo ""

# Test the view
print_info "Testing view..."
if run_sql "SELECT COUNT(*) FROM v_articles_with_stock_performance;" > /dev/null 2>&1; then
    print_success "View 'v_articles_with_stock_performance' is working"
else
    print_warning "View might have issues, but this is non-critical"
fi
echo ""

if [ "$ALL_GOOD" = true ]; then
    print_success "===================================="
    print_success "All migrations completed successfully!"
    print_success "===================================="
    echo ""
    print_info "Database schema is ready for use."
    echo ""
    print_info "Tables created:"
    echo "  - rss_feeds (RSS feed sources)"
    echo "  - rss_items (RSS articles with stock tickers)"
    echo "  - stock_prices (Historical stock price data)"
    echo "  - article_stock_snapshots (Links articles to stock prices)"
    echo ""
    print_info "View created:"
    echo "  - v_articles_with_stock_performance"
    echo ""
else
    print_error "Some migrations failed. Please check the errors above."
    exit 1
fi
