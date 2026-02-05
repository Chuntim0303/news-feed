"""
AWS Lambda Function for RSS Feed Tracking System

This Lambda function handles:
1. Fetching RSS feeds from Bloomberg and Fierce Biotech
2. Parsing feed items
3. Storing items in MySQL database
4. Querying stored feed items

Environment Variables Required:
- DB_HOST: MySQL database host
- DB_USER: MySQL database user
- DB_PASSWORD: MySQL database password
- DB_NAME: MySQL database name
- DB_PORT: MySQL database port (default: 3306)
"""

import json
import logging
import os
from typing import Dict, Any, List

from services import BloombergService, FiercebiotechService

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_db_config() -> Dict[str, str]:
    """
    Get database configuration from environment variables

    Returns:
        Dict with database configuration
    """
    return {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'user': os.environ.get('DB_USER', 'root'),
        'password': os.environ.get('DB_PASSWORD', ''),
        'database': os.environ.get('DB_NAME', 'test'),
        'port': os.environ.get('DB_PORT', '3306')
    }


def fetch_bloomberg_feed(db_config: Dict[str, str]) -> Dict[str, Any]:
    """
    Fetch and store Bloomberg RSS feed

    Args:
        db_config: Database configuration

    Returns:
        Dict with operation results
    """
    try:
        service = BloombergService(db_config)
        result = service.fetch_and_save()
        logger.info(f"Bloomberg fetch result: {result}")
        return result
    except Exception as e:
        logger.error(f"Error fetching Bloomberg feed: {e}", exc_info=True)
        return {
            'status': 'error',
            'source': 'bloomberg',
            'error': str(e)
        }


def fetch_fiercebiotech_feed(db_config: Dict[str, str]) -> Dict[str, Any]:
    """
    Fetch and store Fierce Biotech RSS feed

    Args:
        db_config: Database configuration

    Returns:
        Dict with operation results
    """
    try:
        service = FiercebiotechService(db_config)
        result = service.fetch_and_save()
        logger.info(f"Fierce Biotech fetch result: {result}")
        return result
    except Exception as e:
        logger.error(f"Error fetching Fierce Biotech feed: {e}", exc_info=True)
        return {
            'status': 'error',
            'source': 'fiercebiotech',
            'error': str(e)
        }


def fetch_all_feeds(db_config: Dict[str, str]) -> Dict[str, Any]:
    """
    Fetch all RSS feeds

    Args:
        db_config: Database configuration

    Returns:
        Dict with results from all feeds
    """
    results = {
        'bloomberg': fetch_bloomberg_feed(db_config),
        'fiercebiotech': fetch_fiercebiotech_feed(db_config)
    }

    return {
        'status': 'success',
        'message': 'All feeds processed',
        'results': results
    }


def search_news(db_config: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search news items in the database

    Args:
        db_config: Database configuration
        params: Search parameters (keyword, source, limit, offset, date_from, date_to)

    Returns:
        Dict with search results
    """
    import pymysql

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
            # Build query
            query = """
                SELECT
                    i.id, i.guid, i.link, i.title, i.author, i.stock_tickers,
                    i.company_names, i.summary, i.content, i.image_url,
                    i.published_at, i.fetched_at, i.created_at,
                    f.title as feed_title, f.url as feed_url
                FROM rss_items i
                JOIN rss_feeds f ON i.feed_id = f.id
                WHERE 1=1
            """
            query_params = []

            # Add filters
            if params.get('keyword'):
                query += " AND (i.title LIKE %s OR i.summary LIKE %s OR i.content LIKE %s)"
                keyword = f"%{params['keyword']}%"
                query_params.extend([keyword, keyword, keyword])

            if params.get('ticker'):
                # Search for ticker in stock_tickers field (comma-separated)
                query += " AND (i.stock_tickers LIKE %s OR i.stock_tickers = %s)"
                ticker = params['ticker']
                query_params.extend([f"%{ticker}%", ticker])

            if params.get('company'):
                # Search for company name in company_names field
                query += " AND i.company_names LIKE %s"
                query_params.append(f"%{params['company']}%")

            if params.get('source'):
                query += " AND f.title LIKE %s"
                query_params.append(f"%{params['source']}%")

            if params.get('date_from'):
                query += " AND i.published_at >= %s"
                query_params.append(params['date_from'])

            if params.get('date_to'):
                query += " AND i.published_at <= %s"
                query_params.append(params['date_to'])

            # Add ordering
            query += " ORDER BY i.published_at DESC"

            # Add pagination
            limit = int(params.get('limit', 50))
            offset = int(params.get('offset', 0))
            query += " LIMIT %s OFFSET %s"
            query_params.extend([limit, offset])

            # Execute query
            cursor.execute(query, query_params)
            results = cursor.fetchall()

            # Convert datetime objects to strings
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
        return {
            'status': 'error',
            'error': str(e)
        }
    finally:
        if connection:
            connection.close()


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler function

    Supported actions:
    - fetch_bloomberg: Fetch Bloomberg RSS feed
    - fetch_fiercebiotech: Fetch Fierce Biotech RSS feed
    - fetch_all: Fetch all RSS feeds
    - search: Search news items

    Args:
        event: Lambda event object with 'action' and optional parameters
        context: Lambda context object

    Returns:
        Dict with response data
    """
    logger.info(f"Lambda invoked with event: {json.dumps(event)}")

    # Get database configuration
    db_config = get_db_config()

    # Get action from event
    action = event.get('action', 'fetch_all')

    try:
        if action == 'fetch_bloomberg':
            result = fetch_bloomberg_feed(db_config)

        elif action == 'fetch_fiercebiotech':
            result = fetch_fiercebiotech_feed(db_config)

        elif action == 'fetch_all':
            result = fetch_all_feeds(db_config)

        elif action == 'search':
            params = event.get('params', {})
            result = search_news(db_config, params)

        else:
            result = {
                'status': 'error',
                'error': f'Unknown action: {action}',
                'available_actions': [
                    'fetch_bloomberg',
                    'fetch_fiercebiotech',
                    'fetch_all',
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
    # Test event for fetching all feeds
    test_event = {
        'action': 'fetch_all'
    }

    # Mock context
    class MockContext:
        def __init__(self):
            self.function_name = 'rss-tracker-test'
            self.memory_limit_in_mb = 128
            self.invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789:function:rss-tracker-test'
            self.aws_request_id = 'test-request-id'

    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2))
