"""
Stock Impact Analysis Frontend API
Python 3.12 Lambda Function

Provides REST API endpoints for the frontend dashboard to visualize:
- Multi-horizon event study results
- Abnormal returns analysis
- Backtesting metrics
- Alpha candidates
- Processing status
"""

import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

import pymysql

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_db_connection():
    """Create database connection."""
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'news_feed'),
        port=int(os.environ.get('DB_PORT', 3306)),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )


def cors_headers():
    """Return CORS headers for API responses."""
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
    }


def response(status_code: int, body: Dict) -> Dict:
    """Format API response."""
    return {
        'statusCode': status_code,
        'headers': cors_headers(),
        'body': json.dumps(body, default=str)
    }


# ============================================================================
# API Endpoints
# ============================================================================

def get_articles_with_returns(params: Dict) -> Dict:
    """
    Get articles with multi-horizon returns.
    
    Query params:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        min_score: Minimum score threshold
        ticker: Filter by ticker (optional)
        limit: Max results (default 100)
    """
    start_date = params.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = params.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    min_score = float(params.get('min_score', 5.0))
    ticker_filter = params.get('ticker')
    limit = int(params.get('limit', 100))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            query = """
                SELECT 
                    ri.id,
                    ri.title,
                    ri.link,
                    ri.published_at,
                    ri.stock_tickers,
                    al.score_total,
                    al.score_keyword,
                    al.score_surprise,
                    al.score_market_reaction,
                    arw.ticker,
                    arw.return_pre_1d,
                    arw.return_pre_3d,
                    arw.return_pre_5d,
                    arw.return_1d,
                    arw.return_3d,
                    arw.return_5d,
                    arw.return_10d,
                    arw.abnormal_return_1d,
                    arw.abnormal_return_3d,
                    arw.abnormal_return_5d,
                    arw.abnormal_return_10d,
                    arw.volume_ratio_1d,
                    arw.volume_zscore_1d,
                    arw.gap_magnitude,
                    arw.processing_status,
                    ass.ticker_relevance_score,
                    mrs.total_reaction_score
                FROM rss_items ri
                JOIN alert_log al ON al.rss_item_id = ri.id
                LEFT JOIN article_return_windows arw ON arw.article_id = ri.id
                LEFT JOIN article_stock_snapshots ass 
                    ON ass.article_id = ri.id AND ass.ticker = arw.ticker
                LEFT JOIN market_reaction_scores mrs
                    ON mrs.article_id = ri.id AND mrs.ticker = arw.ticker
                WHERE DATE(ri.published_at) BETWEEN %s AND %s
                  AND al.score_total >= %s
            """
            
            query_params = [start_date, end_date, min_score]
            
            if ticker_filter:
                query += " AND arw.ticker = %s"
                query_params.append(ticker_filter)
            
            query += " ORDER BY ri.published_at DESC, al.score_total DESC LIMIT %s"
            query_params.append(limit)
            
            cursor.execute(query, query_params)
            articles = cursor.fetchall()

        # Convert Decimals to floats
        for article in articles:
            for key, value in article.items():
                if isinstance(value, pymysql.converters.Decimal):
                    article[key] = float(value)

        return response(200, {
            'status': 'success',
            'count': len(articles),
            'articles': articles
        })

    except Exception as e:
        logger.error(f"Error fetching articles: {e}", exc_info=True)
        return response(500, {'status': 'error', 'message': str(e)})
    finally:
        connection.close()


def get_alpha_candidates(params: Dict) -> Dict:
    """
    Get alpha candidates (high score + high abnormal return + low confounding).
    
    Query params:
        date: Target date (YYYY-MM-DD, default yesterday)
        min_score: Minimum score (default 15)
        min_abnormal_return: Minimum |abnormal_return| (default 3.0)
        limit: Max results (default 10)
    """
    target_date = params.get('date', (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'))
    min_score = float(params.get('min_score', 15.0))
    min_abnormal_return = float(params.get('min_abnormal_return', 3.0))
    limit = int(params.get('limit', 10))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT 
                       ri.id,
                       ri.title,
                       ri.link,
                       ri.published_at,
                       al.score_total,
                       arw.ticker,
                       arw.abnormal_return_1d,
                       arw.volume_ratio_1d,
                       arw.gap_magnitude,
                       ass.ticker_relevance_score,
                       mrs.total_reaction_score
                   FROM rss_items ri
                   JOIN alert_log al ON al.rss_item_id = ri.id
                   JOIN article_return_windows arw ON arw.article_id = ri.id
                   LEFT JOIN article_stock_snapshots ass 
                       ON ass.article_id = ri.id AND ass.ticker = arw.ticker
                   LEFT JOIN market_reaction_scores mrs
                       ON mrs.article_id = ri.id AND mrs.ticker = arw.ticker
                   WHERE DATE(ri.published_at) = %s
                     AND al.score_total >= %s
                     AND ABS(arw.abnormal_return_1d) >= %s
                     AND arw.processing_status = 'complete'
                   ORDER BY (al.score_total * ABS(arw.abnormal_return_1d)) DESC
                   LIMIT %s""",
                (target_date, min_score, min_abnormal_return, limit)
            )
            candidates = cursor.fetchall()

        for candidate in candidates:
            for key, value in candidate.items():
                if isinstance(value, pymysql.converters.Decimal):
                    candidate[key] = float(value)

        return response(200, {
            'status': 'success',
            'date': target_date,
            'count': len(candidates),
            'candidates': candidates
        })

    except Exception as e:
        logger.error(f"Error fetching alpha candidates: {e}", exc_info=True)
        return response(500, {'status': 'error', 'message': str(e)})
    finally:
        connection.close()


def get_backtest_results(params: Dict) -> Dict:
    """
    Get backtesting results.
    
    Query params:
        limit: Max results (default 10, most recent backtests)
    """
    limit = int(params.get('limit', 10))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT 
                       backtest_date,
                       score_bucket,
                       article_count,
                       avg_abnormal_return_1d,
                       hit_rate,
                       precision_at_k,
                       config_params
                   FROM scoring_backtest_results
                   ORDER BY backtest_date DESC, score_bucket
                   LIMIT %s""",
                (limit * 5,)  # 5 buckets per backtest
            )
            results = cursor.fetchall()

        for result in results:
            for key, value in result.items():
                if isinstance(value, pymysql.converters.Decimal):
                    result[key] = float(value)
            # Parse JSON config_params
            if result.get('config_params'):
                try:
                    result['config_params'] = json.loads(result['config_params'])
                except:
                    pass

        # Group by backtest_date
        grouped = {}
        for result in results:
            date = str(result['backtest_date'])
            if date not in grouped:
                grouped[date] = []
            grouped[date].append(result)

        return response(200, {
            'status': 'success',
            'backtest_results': grouped
        })

    except Exception as e:
        logger.error(f"Error fetching backtest results: {e}", exc_info=True)
        return response(500, {'status': 'error', 'message': str(e)})
    finally:
        connection.close()


def get_processing_status(params: Dict) -> Dict:
    """
    Get processing status summary.
    
    Returns counts by status and recent failures.
    """
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Status counts
            cursor.execute(
                """SELECT 
                       processing_status,
                       COUNT(*) as count
                   FROM article_return_windows
                   WHERE last_processed_at >= NOW() - INTERVAL 7 DAY
                   GROUP BY processing_status"""
            )
            status_counts = cursor.fetchall()

            # Recent failures
            cursor.execute(
                """SELECT 
                       arw.article_id,
                       arw.ticker,
                       arw.failure_reason,
                       arw.retry_count,
                       arw.last_processed_at,
                       ri.title
                   FROM article_return_windows arw
                   JOIN rss_items ri ON ri.id = arw.article_id
                   WHERE arw.processing_status = 'failed'
                     AND arw.retry_count >= 3
                   ORDER BY arw.last_processed_at DESC
                   LIMIT 20"""
            )
            failures = cursor.fetchall()

        return response(200, {
            'status': 'success',
            'status_counts': status_counts,
            'recent_failures': failures
        })

    except Exception as e:
        logger.error(f"Error fetching processing status: {e}", exc_info=True)
        return response(500, {'status': 'error', 'message': str(e)})
    finally:
        connection.close()


def get_score_distribution(params: Dict) -> Dict:
    """
    Get score distribution and average returns by bucket.
    
    Query params:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
    """
    start_date = params.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = params.get('end_date', datetime.now().strftime('%Y-%m-%d'))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT 
                       CASE 
                           WHEN al.score_total < 10 THEN '5-10'
                           WHEN al.score_total < 15 THEN '10-15'
                           WHEN al.score_total < 20 THEN '15-20'
                           WHEN al.score_total < 30 THEN '20-30'
                           ELSE '30+'
                       END as score_bucket,
                       COUNT(*) as count,
                       AVG(arw.abnormal_return_1d) as avg_abnormal_return,
                       AVG(ABS(arw.abnormal_return_1d)) as avg_abs_abnormal_return,
                       SUM(CASE WHEN ABS(arw.abnormal_return_1d) > 2.0 THEN 1 ELSE 0 END) as hit_count
                   FROM alert_log al
                   JOIN rss_items ri ON ri.id = al.rss_item_id
                   JOIN article_return_windows arw ON arw.article_id = al.rss_item_id
                   WHERE DATE(ri.published_at) BETWEEN %s AND %s
                     AND arw.processing_status = 'complete'
                     AND arw.abnormal_return_1d IS NOT NULL
                   GROUP BY score_bucket
                   ORDER BY score_bucket""",
                (start_date, end_date)
            )
            distribution = cursor.fetchall()

        for bucket in distribution:
            for key, value in bucket.items():
                if isinstance(value, pymysql.converters.Decimal):
                    bucket[key] = float(value)
            # Calculate hit rate
            if bucket['count'] > 0:
                bucket['hit_rate'] = bucket['hit_count'] / bucket['count']

        return response(200, {
            'status': 'success',
            'start_date': start_date,
            'end_date': end_date,
            'distribution': distribution
        })

    except Exception as e:
        logger.error(f"Error fetching score distribution: {e}", exc_info=True)
        return response(500, {'status': 'error', 'message': str(e)})
    finally:
        connection.close()


def get_ticker_performance(params: Dict) -> Dict:
    """
    Get performance metrics by ticker.
    
    Query params:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        limit: Max tickers (default 20)
    """
    start_date = params.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = params.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    limit = int(params.get('limit', 20))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT 
                       arw.ticker,
                       COUNT(*) as article_count,
                       AVG(al.score_total) as avg_score,
                       AVG(arw.abnormal_return_1d) as avg_abnormal_return_1d,
                       AVG(arw.abnormal_return_3d) as avg_abnormal_return_3d,
                       AVG(arw.volume_ratio_1d) as avg_volume_ratio,
                       tsm.sector
                   FROM article_return_windows arw
                   JOIN rss_items ri ON ri.id = arw.article_id
                   JOIN alert_log al ON al.rss_item_id = ri.id
                   LEFT JOIN ticker_sector_mapping tsm ON tsm.ticker = arw.ticker
                   WHERE DATE(ri.published_at) BETWEEN %s AND %s
                     AND arw.processing_status = 'complete'
                   GROUP BY arw.ticker, tsm.sector
                   ORDER BY article_count DESC
                   LIMIT %s""",
                (start_date, end_date, limit)
            )
            tickers = cursor.fetchall()

        for ticker in tickers:
            for key, value in ticker.items():
                if isinstance(value, pymysql.converters.Decimal):
                    ticker[key] = float(value)

        return response(200, {
            'status': 'success',
            'start_date': start_date,
            'end_date': end_date,
            'tickers': tickers
        })

    except Exception as e:
        logger.error(f"Error fetching ticker performance: {e}", exc_info=True)
        return response(500, {'status': 'error', 'message': str(e)})
    finally:
        connection.close()


# ============================================================================
# Lambda Handler
# ============================================================================

def lambda_handler(event, context):
    """Main Lambda handler for API Gateway requests."""
    
    # Handle OPTIONS for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return response(200, {'message': 'OK'})

    # Parse request
    path = event.get('path', '/')
    method = event.get('httpMethod', 'GET')
    params = event.get('queryStringParameters') or {}

    logger.info(f"Request: {method} {path} params={params}")

    # Route to appropriate handler
    try:
        if path == '/articles' and method == 'GET':
            return get_articles_with_returns(params)
        
        elif path == '/alpha-candidates' and method == 'GET':
            return get_alpha_candidates(params)
        
        elif path == '/backtest-results' and method == 'GET':
            return get_backtest_results(params)
        
        elif path == '/processing-status' and method == 'GET':
            return get_processing_status(params)
        
        elif path == '/score-distribution' and method == 'GET':
            return get_score_distribution(params)
        
        elif path == '/ticker-performance' and method == 'GET':
            return get_ticker_performance(params)
        
        else:
            return response(404, {'status': 'error', 'message': 'Endpoint not found'})

    except Exception as e:
        logger.error(f"Unhandled error: {e}", exc_info=True)
        return response(500, {'status': 'error', 'message': str(e)})
