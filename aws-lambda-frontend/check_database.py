"""
Database diagnostic script
Checks if required tables exist and have data
"""

import os
import pymysql

# Database configuration
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASSWORD', ''),
    'database': os.environ.get('DB_NAME', 'news_feed'),
    'port': int(os.environ.get('DB_PORT', 3306)),
}

def check_table(cursor, table_name):
    """Check if table exists and count rows."""
    try:
        cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
        result = cursor.fetchone()
        count = result['count'] if result else 0
        print(f"✓ {table_name}: {count:,} rows")
        return count
    except Exception as e:
        print(f"✗ {table_name}: ERROR - {e}")
        return 0

def check_sample_data(cursor):
    """Check sample data from key tables."""
    print("\n" + "="*60)
    print("SAMPLE DATA CHECK")
    print("="*60)
    
    # Check rss_items with scores
    print("\n1. Recent articles with scores:")
    try:
        cursor.execute("""
            SELECT 
                ri.id,
                ri.title,
                ri.published_at,
                ri.stock_tickers,
                al.score_total
            FROM rss_items ri
            JOIN alert_log al ON al.rss_item_id = ri.id
            ORDER BY ri.published_at DESC
            LIMIT 5
        """)
        articles = cursor.fetchall()
        if articles:
            for art in articles:
                print(f"  - [{art['id']}] {art['title'][:50]}... (Score: {art['score_total']}, Tickers: {art['stock_tickers']})")
        else:
            print("  ⚠ No articles found with scores")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
    
    # Check article_return_windows
    print("\n2. Articles with return windows:")
    try:
        cursor.execute("""
            SELECT 
                article_id,
                ticker,
                return_1d,
                abnormal_return_1d,
                processing_status
            FROM article_return_windows
            WHERE processing_status = 'complete'
            LIMIT 5
        """)
        returns = cursor.fetchall()
        if returns:
            for ret in returns:
                print(f"  - Article {ret['article_id']}, {ret['ticker']}: 1D Return={ret['return_1d']}, Abnormal={ret['abnormal_return_1d']}, Status={ret['processing_status']}")
        else:
            print("  ⚠ No completed return windows found")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")

def main():
    print("="*60)
    print("DATABASE DIAGNOSTIC CHECK")
    print("="*60)
    print(f"Connecting to: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    
    try:
        connection = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
        print("✓ Database connection successful\n")
        
        with connection.cursor() as cursor:
            print("TABLE ROW COUNTS:")
            print("-"*60)
            
            # Check all required tables
            tables = [
                'rss_items',
                'rss_feeds',
                'alert_log',
                'alert_keywords',
                'article_stock_snapshots',
                'article_return_windows',
                'benchmark_returns',
                'ticker_sector_mapping',
                'confounder_events',
                'article_clusters',
                'market_reaction_scores',
                'scoring_backtest_results',
                'stock_prices',
                'companies'
            ]
            
            for table in tables:
                check_table(cursor, table)
            
            # Check sample data
            check_sample_data(cursor)
        
        connection.close()
        
        print("\n" + "="*60)
        print("DIAGNOSTIC COMPLETE")
        print("="*60)
        
    except Exception as e:
        print(f"\n✗ Database connection failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
