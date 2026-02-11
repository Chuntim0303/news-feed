"""
AWS Lambda Function for RSS Feed Tracking System

This Lambda function handles:
1. Fetching RSS feeds from Bloomberg and Fierce Biotech
2. Parsing feed items and storing in MySQL database
3. Extracting company names and stock tickers from articles (spaCy NER)
4. Fetching stock prices via Twelve Data API
5. Building article-stock snapshots for news impact analysis
6. Querying stored feed items and stock performance

Environment Variables Required:
- DB_HOST: MySQL database host
- DB_USER: MySQL database user
- DB_PASSWORD: MySQL database password
- DB_NAME: MySQL database name
- DB_PORT: MySQL database port (default: 3306)
- TWELVE_DATA_API_KEY: API key for Twelve Data stock prices
"""

import json
import logging
import os
from typing import Dict, Any, List

import pymysql

from services import (BloombergService, FiercebiotechService, CompanyExtractor,
                     StockPriceService, TelegramReportService)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_db_config() -> Dict[str, str]:
    """Get database configuration from environment variables."""
    return {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'user': os.environ.get('DB_USER', 'root'),
        'password': os.environ.get('DB_PASSWORD', ''),
        'database': os.environ.get('DB_NAME', 'test'),
        'port': os.environ.get('DB_PORT', '3306')
    }


# ---------------------------------------------------------------------------
# RSS Feed Fetching
# ---------------------------------------------------------------------------

def fetch_bloomberg_feed(db_config: Dict[str, str]) -> Dict[str, Any]:
    """Fetch and store Bloomberg RSS feed."""
    try:
        service = BloombergService(db_config)
        result = service.fetch_and_save()
        logger.info(f"Bloomberg fetch result: {result}")
        return result
    except Exception as e:
        logger.error(f"Error fetching Bloomberg feed: {e}", exc_info=True)
        return {'status': 'error', 'source': 'bloomberg', 'error': str(e)}


def fetch_fiercebiotech_feed(db_config: Dict[str, str]) -> Dict[str, Any]:
    """Fetch and store Fierce Biotech RSS feed."""
    try:
        service = FiercebiotechService(db_config)
        result = service.fetch_and_save()
        logger.info(f"Fierce Biotech fetch result: {result}")
        return result
    except Exception as e:
        logger.error(f"Error fetching Fierce Biotech feed: {e}", exc_info=True)
        return {'status': 'error', 'source': 'fiercebiotech', 'error': str(e)}


def fetch_all_feeds(db_config: Dict[str, str]) -> Dict[str, Any]:
    """Fetch all RSS feeds, then extract tickers from new articles."""
    results = {
        'bloomberg': fetch_bloomberg_feed(db_config),
        'fiercebiotech': fetch_fiercebiotech_feed(db_config)
    }

    # Auto-extract tickers from newly fetched articles
    ticker_result = extract_tickers(db_config, {'limit': 50})

    return {
        'status': 'success',
        'message': 'All feeds processed',
        'results': results,
        'ticker_extraction': ticker_result
    }


# ---------------------------------------------------------------------------
# Ticker Extraction
# ---------------------------------------------------------------------------

def extract_tickers(db_config: Dict[str, str], params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Extract company names and stock tickers from articles that haven't been processed yet.

    Params:
        limit: Max articles to process (default: 50)
    """
    params = params or {}
    limit = int(params.get('limit', 50))

    connection = None
    try:
        extractor = CompanyExtractor(db_config=db_config)

        connection = pymysql.connect(
            host=db_config['host'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database'],
            port=int(db_config.get('port', 3306)),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

        with connection.cursor() as cursor:
            # Find articles without tickers
            cursor.execute(
                """SELECT id, title, summary FROM rss_items
                   WHERE stock_tickers IS NULL OR stock_tickers = ''
                   ORDER BY published_at DESC
                   LIMIT %s""",
                (limit,)
            )
            articles = cursor.fetchall()

        if not articles:
            return {'status': 'success', 'message': 'No articles to process', 'processed': 0}

        updated = 0
        for article in articles:
            text = article['title'] or ''
            if article.get('summary'):
                text = f"{text}. {article['summary']}"

            result = extractor.extract_companies_and_tickers(text)
            tickers_str, companies_str = extractor.format_for_database(result)

            if tickers_str:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """UPDATE rss_items
                           SET stock_tickers = %s, company_names = %s
                           WHERE id = %s""",
                        (tickers_str, companies_str, article['id'])
                    )
                updated += 1

        connection.commit()
        logger.info(f"Extracted tickers for {updated}/{len(articles)} articles")

        return {
            'status': 'success',
            'processed': len(articles),
            'updated': updated
        }

    except Exception as e:
        logger.error(f"Error extracting tickers: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}
    finally:
        if connection:
            connection.close()


# ---------------------------------------------------------------------------
# Stock Price Fetching
# ---------------------------------------------------------------------------

def fetch_stock_prices(db_config: Dict[str, str], params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Fetch stock prices for articles that have tickers but no price snapshots yet.

    Params:
        limit: Max articles to process (default: 50)
        days_around: Days before/after article date to fetch (default: 2)
    """
    params = params or {}
    limit = int(params.get('limit', 50))
    days_around = int(params.get('days_around', 2))

    try:
        service = StockPriceService(db_config=db_config)
        service.fetch_prices_for_articles(limit=limit, days_around=days_around)

        return {
            'status': 'success',
            'message': f'Fetched stock prices (limit={limit}, days_around={days_around})'
        }

    except Exception as e:
        logger.error(f"Error fetching stock prices: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}


# ---------------------------------------------------------------------------
# News Impact Analysis
# ---------------------------------------------------------------------------

def get_news_impact(db_config: Dict[str, str], params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Get news impact analysis — articles with their stock price changes.

    Params:
        ticker: Filter by specific ticker
        limit: Max results (default: 30)
        sort: 'change' (default) or 'date'
    """
    params = params or {}
    limit = int(params.get('limit', 30))
    ticker_filter = params.get('ticker')
    sort = params.get('sort', 'change')

    connection = None
    try:
        connection = pymysql.connect(
            host=db_config['host'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database'],
            port=int(db_config.get('port', 3306)),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

        with connection.cursor() as cursor:
            query = """
                SELECT
                    ri.id, ri.title, ri.published_at, ri.stock_tickers, ri.company_names,
                    ass.ticker, ass.price_at_publication, ass.price_current AS price_next_day,
                    ass.price_change_since_article AS change_pct,
                    sp.volume, sp.open_price, sp.close_price, sp.high_price, sp.low_price
                FROM article_stock_snapshots ass
                JOIN rss_items ri ON ass.article_id = ri.id
                LEFT JOIN stock_prices sp ON sp.ticker = ass.ticker
                    AND sp.price_date = (
                        SELECT MIN(sp2.price_date) FROM stock_prices sp2
                        WHERE sp2.ticker = ass.ticker
                          AND sp2.price_date >= DATE(ri.published_at)
                    )
                WHERE ass.price_at_publication IS NOT NULL
            """
            query_params = []

            if ticker_filter:
                query += " AND ass.ticker = %s"
                query_params.append(ticker_filter)

            if sort == 'date':
                query += " ORDER BY ri.published_at DESC"
            else:
                query += " ORDER BY ABS(ass.price_change_since_article) DESC"

            query += " LIMIT %s"
            query_params.append(limit)

            cursor.execute(query, query_params)
            rows = cursor.fetchall()

        # Convert datetimes
        for row in rows:
            if row.get('published_at'):
                row['published_at'] = row['published_at'].isoformat()
            # Convert Decimal to float for JSON
            for key in ['price_at_publication', 'price_next_day', 'change_pct',
                        'open_price', 'close_price', 'high_price', 'low_price']:
                if row.get(key) is not None:
                    row[key] = float(row[key])
            if row.get('volume') is not None:
                row['volume'] = int(row['volume'])

        return {
            'status': 'success',
            'count': len(rows),
            'items': rows
        }

    except Exception as e:
        logger.error(f"Error getting news impact: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}
    finally:
        if connection:
            connection.close()


# ---------------------------------------------------------------------------
# Telegram Report
# ---------------------------------------------------------------------------

def send_report(db_config: Dict[str, str], params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Generate a PDF news impact report and send it to Telegram.

    Params:
        (none required — uses TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars)
    """
    try:
        service = TelegramReportService(db_config=db_config)
        result = service.generate_and_send_report()
        return result
    except Exception as e:
        logger.error(f"Error sending report: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_news(db_config: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search news items in the database.

    Params: keyword, source, limit, offset, date_from, date_to, ticker
    """
    connection = None
    try:
        connection = pymysql.connect(
            host=db_config['host'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database'],
            port=int(db_config.get('port', 3306)),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

        with connection.cursor() as cursor:
            query = """
                SELECT
                    i.id, i.guid, i.link, i.title, i.author, i.summary,
                    i.content, i.image_url, i.published_at, i.fetched_at,
                    i.created_at, i.stock_tickers, i.company_names,
                    f.title as feed_title, f.url as feed_url
                FROM rss_items i
                JOIN rss_feeds f ON i.feed_id = f.id
                WHERE 1=1
            """
            query_params = []

            if params.get('keyword'):
                query += " AND (i.title LIKE %s OR i.summary LIKE %s OR i.content LIKE %s)"
                keyword = f"%{params['keyword']}%"
                query_params.extend([keyword, keyword, keyword])

            if params.get('source'):
                query += " AND f.title LIKE %s"
                query_params.append(f"%{params['source']}%")

            if params.get('date_from'):
                query += " AND i.published_at >= %s"
                query_params.append(params['date_from'])

            if params.get('date_to'):
                query += " AND i.published_at <= %s"
                query_params.append(params['date_to'])

            if params.get('ticker'):
                query += " AND FIND_IN_SET(%s, i.stock_tickers) > 0"
                query_params.append(params['ticker'])

            query += " ORDER BY i.published_at DESC"

            limit = int(params.get('limit', 50))
            offset = int(params.get('offset', 0))
            query += " LIMIT %s OFFSET %s"
            query_params.extend([limit, offset])

            cursor.execute(query, query_params)
            results = cursor.fetchall()

            for result in results:
                if result.get('published_at'):
                    result['published_at'] = result['published_at'].isoformat()
                if result.get('fetched_at'):
                    result['fetched_at'] = result['fetched_at'].isoformat()
                if result.get('created_at'):
                    result['created_at'] = result['created_at'].isoformat()

            return {
                'status': 'success',
                'count': len(results),
                'items': results
            }

    except Exception as e:
        logger.error(f"Error searching news: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}
    finally:
        if connection:
            connection.close()


# ---------------------------------------------------------------------------
# Lambda Handler
# ---------------------------------------------------------------------------

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler function

    Supported actions:
    - fetch_bloomberg: Fetch Bloomberg RSS feed
    - fetch_fiercebiotech: Fetch Fierce Biotech RSS feed
    - fetch_all: Fetch all feeds + auto-extract tickers
    - extract_tickers: Extract tickers from unprocessed articles
    - fetch_stock_prices: Fetch stock prices for articles with tickers
    - news_impact: Get news impact analysis (price/volume changes)
    - send_report: Generate PDF report and send to Telegram
    - search: Search news items

    Args:
        event: Lambda event object with 'action' and optional 'params'
        context: Lambda context object

    Returns:
        Dict with response data
    """
    logger.info(f"Lambda invoked with event: {json.dumps(event)}")

    db_config = get_db_config()
    action = event.get('action', 'fetch_all')
    params = event.get('params', {})

    try:
        if action == 'fetch_bloomberg':
            result = fetch_bloomberg_feed(db_config)

        elif action == 'fetch_fiercebiotech':
            result = fetch_fiercebiotech_feed(db_config)

        elif action == 'fetch_all':
            result = fetch_all_feeds(db_config)

        elif action == 'extract_tickers':
            result = extract_tickers(db_config, params)

        elif action == 'fetch_stock_prices':
            result = fetch_stock_prices(db_config, params)

        elif action == 'news_impact':
            result = get_news_impact(db_config, params)

        elif action == 'send_report':
            result = send_report(db_config, params)

        elif action == 'search':
            result = search_news(db_config, params)

        else:
            result = {
                'status': 'error',
                'error': f'Unknown action: {action}',
                'available_actions': [
                    'fetch_bloomberg',
                    'fetch_fiercebiotech',
                    'fetch_all',
                    'extract_tickers',
                    'fetch_stock_prices',
                    'news_impact',
                    'send_report',
                    'search'
                ]
            }

        return {
            'statusCode': 200 if result.get('status') == 'success' else 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(result, default=str)
        }

    except Exception as e:
        logger.error(f"Lambda execution error: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'status': 'error',
                'error': str(e)
            })
        }


# For local testing
if __name__ == '__main__':
    import sys

    test_actions = {
        'fetch': {'action': 'fetch_all'},
        'tickers': {'action': 'extract_tickers', 'params': {'limit': 10}},
        'prices': {'action': 'fetch_stock_prices', 'params': {'limit': 10}},
        'impact': {'action': 'news_impact', 'params': {'limit': 10}},
        'report': {'action': 'send_report'},
        'search': {'action': 'search', 'params': {'keyword': 'Alphabet'}},
    }

    action_name = sys.argv[1] if len(sys.argv) > 1 else 'fetch'
    test_event = test_actions.get(action_name, {'action': action_name})

    class MockContext:
        def __init__(self):
            self.function_name = 'rss-tracker-test'
            self.memory_limit_in_mb = 512
            self.invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789:function:rss-tracker-test'
            self.aws_request_id = 'test-request-id'

    print(f"Testing action: {test_event.get('action')}")
    result = lambda_handler(test_event, MockContext())
    print(json.dumps(json.loads(result['body']), indent=2, default=str))
