"""
AWS Lambda Function — Daily Stock Price & News Impact Analysis

Runs once per day (recommended: after US market close, ~4:30 PM ET / ~4:30 AM UTC+8).

Pipeline:
1. Fetch stock prices for all tickers referenced in recent articles
2. Build article-stock snapshots (pre-news vs post-news price comparison)
3. Optionally generate a PDF report and send via Telegram

Digests (triggered via separate EventBridge schedules):
- morning_brief: Top headlines + watchlist items (9:00 AM)
- eod_recap: What moved + which news triggered (after market close)
- weekly_report: Keyword-spike correlations (Sunday evening)

Environment Variables Required:
- DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT
- TWELVE_DATA_API_KEY
- TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (optional, for reports/digests)
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from urllib.request import urlopen, Request

import pymysql

from services import StockPriceService

# TelegramReportService is optional (requires fpdf2)
try:
    from services import TelegramReportService
except ImportError:
    TelegramReportService = None

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
        'port': int(os.environ.get('DB_PORT', '3306'))
    }


# ---------------------------------------------------------------------------
# Stock Price Fetching
# ---------------------------------------------------------------------------

def fetch_stock_prices(db_config: Dict[str, str], params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Fetch stock prices for articles that have tickers but no price snapshots yet.

    Params:
        limit: Max articles to process per group (default: 200)
        days_around: Days before/after article date to fetch (default: 2)
        lookback_hours: Re-check incomplete snapshots within this window (default: 48)
    """
    params = params or {}
    limit = int(params.get('limit', 200))
    days_around = int(params.get('days_around', 2))
    lookback_hours = int(params.get('lookback_hours', 48))

    try:
        service = StockPriceService(db_config=db_config)
        result = service.fetch_prices_for_articles(
            limit=limit, days_around=days_around, lookback_hours=lookback_hours
        )

        return {
            'status': 'success',
            'message': f'Fetched stock prices (limit={limit}, days_around={days_around}, lookback={lookback_hours}h)',
            'details': result
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

        # Convert datetimes and Decimals for JSON serialization
        for row in rows:
            if row.get('published_at'):
                row['published_at'] = row['published_at'].isoformat()
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
        if TelegramReportService is None:
            return {
                'status': 'error',
                'error': 'TelegramReportService unavailable — fpdf2 package is missing from the Lambda layer'
            }
        service = TelegramReportService(db_config=db_config)
        result = service.generate_and_send_report()
        return result
    except Exception as e:
        logger.error(f"Error sending report: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}


# ---------------------------------------------------------------------------
# Telegram Messaging Helper
# ---------------------------------------------------------------------------

def _send_telegram_message(chat_id: str, text: str) -> Optional[Dict]:
    """Send a message to a Telegram chat."""
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    if not bot_token:
        return None

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = json.dumps({
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }).encode('utf-8')

    try:
        req = Request(url, data=payload, method='POST')
        req.add_header('Content-Type', 'application/json')
        response = urlopen(req, timeout=10)
        return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        logger.error(f"Failed to send Telegram message to {chat_id}: {e}")
        return None


def _get_subscribed_chats(db_config: Dict[str, str], digest_column: str) -> List[str]:
    """Get chat IDs that have a specific digest enabled."""
    connection = pymysql.connect(
        host=db_config['host'], user=db_config['user'],
        password=db_config['password'], database=db_config['database'],
        port=int(db_config.get('port', 3306)),
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT chat_id FROM bot_settings WHERE {digest_column} = 1"
            )
            rows = cursor.fetchall()
        return [r['chat_id'] for r in rows]
    except Exception as e:
        logger.warning(f"Could not fetch subscribed chats for {digest_column}: {e}")
        # Fallback to TELEGRAM_CHAT_ID env var
        fallback = os.environ.get('TELEGRAM_CHAT_ID', '')
        return [fallback] if fallback else []
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Digests
# ---------------------------------------------------------------------------

def morning_brief(db_config: Dict[str, str], params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Morning brief digest — top headlines + watchlist-specific items.
    Sent to all chats with morning_brief enabled.
    """
    params = params or {}
    hours = int(params.get('hours', 16))  # Look back ~16h (overnight)
    since = datetime.now() - timedelta(hours=hours)

    connection = pymysql.connect(
        host=db_config['host'], user=db_config['user'],
        password=db_config['password'], database=db_config['database'],
        port=int(db_config.get('port', 3306)),
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
    )
    try:
        with connection.cursor() as cursor:
            # Top headlines
            cursor.execute(
                """SELECT ri.title, ri.published_at, ri.stock_tickers, ri.link,
                          f.title AS feed_title
                   FROM rss_items ri
                   JOIN rss_feeds f ON ri.feed_id = f.id
                   WHERE ri.published_at >= %s
                   ORDER BY ri.published_at DESC
                   LIMIT 10""",
                (since,)
            )
            headlines = cursor.fetchall()

            # Watchlist items (articles matching active keywords)
            cursor.execute(
                """SELECT ri.title, ri.published_at, ri.stock_tickers, ri.link,
                          al.keyword
                   FROM alert_log al
                   JOIN rss_items ri ON al.rss_item_id = ri.id
                   WHERE al.sent_at >= %s
                   ORDER BY al.sent_at DESC
                   LIMIT 5""",
                (since,)
            )
            watchlist = cursor.fetchall()

        if not headlines and not watchlist:
            return {'status': 'success', 'message': 'No headlines to report', 'sent': 0}

        lines = [f"☀️ <b>Morning Brief</b> — {datetime.now().strftime('%b %d, %Y')}\n"]

        if headlines:
            lines.append(f"<b>Top {len(headlines)} Headlines:</b>")
            for h in headlines[:5]:
                pub = h['published_at'].strftime('%H:%M') if h.get('published_at') else '?'
                tickers = f" [{h['stock_tickers']}]" if h.get('stock_tickers') else ''
                title = (h['title'] or '')[:70]
                link = h.get('link', '')
                line = f"• <b>{pub}</b> {title}{tickers}"
                if link:
                    line += f"\n  <a href=\"{link}\">read</a>"
                lines.append(line)

        if watchlist:
            lines.append(f"\n🔔 <b>Watchlist Matches:</b>")
            for w in watchlist:
                title = (w['title'] or '')[:60]
                lines.append(f"• <b>{w['keyword']}</b> — {title}")

        lines.append(f"\n📊 Total new articles: {len(headlines)}")

        message = '\n'.join(lines)
        chats = _get_subscribed_chats(db_config, 'morning_brief')
        sent = 0
        for chat_id in chats:
            if _send_telegram_message(chat_id, message):
                sent += 1

        return {'status': 'success', 'sent': sent, 'headlines': len(headlines)}

    except Exception as e:
        logger.error(f"Error generating morning brief: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}
    finally:
        connection.close()


def eod_recap(db_config: Dict[str, str], params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    End-of-day recap — what moved + which news triggered + links.
    Sent to all chats with eod_recap enabled.
    """
    params = params or {}
    since = datetime.now() - timedelta(hours=24)

    connection = pymysql.connect(
        host=db_config['host'], user=db_config['user'],
        password=db_config['password'], database=db_config['database'],
        port=int(db_config.get('port', 3306)),
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
    )
    try:
        with connection.cursor() as cursor:
            # Top movers
            cursor.execute(
                """SELECT ass.ticker,
                          ass.price_at_publication, ass.price_current,
                          ass.price_change_since_article AS change_pct,
                          ri.title, ri.link, ri.published_at
                   FROM article_stock_snapshots ass
                   JOIN rss_items ri ON ass.article_id = ri.id
                   WHERE ri.published_at >= %s
                     AND ass.price_change_since_article IS NOT NULL
                   ORDER BY ABS(ass.price_change_since_article) DESC
                   LIMIT 10""",
                (since,)
            )
            movers = cursor.fetchall()

            # Alerts triggered today
            cursor.execute(
                """SELECT al.keyword, ri.title, ri.link, al.sent_at
                   FROM alert_log al
                   JOIN rss_items ri ON al.rss_item_id = ri.id
                   WHERE al.sent_at >= %s
                   ORDER BY al.sent_at DESC""",
                (since,)
            )
            alerts = cursor.fetchall()

            # Article count
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM rss_items WHERE published_at >= %s",
                (since,)
            )
            total = cursor.fetchone()['cnt']

        lines = [f"🌙 <b>End-of-Day Recap</b> — {datetime.now().strftime('%b %d, %Y')}\n"]
        lines.append(f"📰 Articles today: {total}")

        if movers:
            lines.append(f"\n<b>Top Movers:</b>")
            for m in movers[:5]:
                change = float(m['change_pct'] or 0)
                arrow = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                pub_price = float(m['price_at_publication'] or 0)
                cur_price = float(m['price_current'] or 0)
                title = (m['title'] or '')[:50]
                link = m.get('link', '')
                line = f"  {arrow} <b>{m['ticker']}</b> {change:+.2f}% (${pub_price:.2f}→${cur_price:.2f})"
                line += f"\n     {title}"
                if link:
                    line += f"\n     <a href=\"{link}\">read</a>"
                lines.append(line)
        else:
            lines.append("\nNo price impact data available today.")

        if alerts:
            lines.append(f"\n🔔 <b>Alerts Triggered ({len(alerts)}):</b>")
            for a in alerts[:5]:
                title = (a['title'] or '')[:50]
                lines.append(f"  • <b>{a['keyword']}</b> — {title}")
            if len(alerts) > 5:
                lines.append(f"  ... and {len(alerts) - 5} more")

        message = '\n'.join(lines)
        chats = _get_subscribed_chats(db_config, 'eod_recap')
        sent = 0
        for chat_id in chats:
            if _send_telegram_message(chat_id, message):
                sent += 1

        return {'status': 'success', 'sent': sent, 'movers': len(movers), 'alerts': len(alerts)}

    except Exception as e:
        logger.error(f"Error generating EOD recap: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}
    finally:
        connection.close()


def weekly_report(db_config: Dict[str, str], params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Weekly report — which keywords correlated most with price spikes.
    Sent to all chats with weekly_report enabled.
    """
    params = params or {}
    since = datetime.now() - timedelta(days=7)

    connection = pymysql.connect(
        host=db_config['host'], user=db_config['user'],
        password=db_config['password'], database=db_config['database'],
        port=int(db_config.get('port', 3306)),
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
    )
    try:
        with connection.cursor() as cursor:
            # Keywords that triggered alerts this week
            cursor.execute(
                """SELECT al.keyword, COUNT(*) AS alert_count
                   FROM alert_log al
                   WHERE al.sent_at >= %s
                   GROUP BY al.keyword
                   ORDER BY alert_count DESC
                   LIMIT 10""",
                (since,)
            )
            keyword_stats = cursor.fetchall()

            # Keywords correlated with biggest price moves
            cursor.execute(
                """SELECT al.keyword,
                          AVG(ABS(ass.price_change_since_article)) AS avg_impact,
                          COUNT(*) AS cnt
                   FROM alert_log al
                   JOIN rss_items ri ON al.rss_item_id = ri.id
                   JOIN article_stock_snapshots ass ON ass.article_id = ri.id
                   WHERE al.sent_at >= %s
                     AND ass.price_change_since_article IS NOT NULL
                   GROUP BY al.keyword
                   HAVING cnt >= 2
                   ORDER BY avg_impact DESC
                   LIMIT 10""",
                (since,)
            )
            keyword_impact = cursor.fetchall()

            # Top movers of the week
            cursor.execute(
                """SELECT ass.ticker,
                          AVG(ass.price_change_since_article) AS avg_change,
                          MAX(ABS(ass.price_change_since_article)) AS max_change,
                          COUNT(*) AS article_count
                   FROM article_stock_snapshots ass
                   JOIN rss_items ri ON ass.article_id = ri.id
                   WHERE ri.published_at >= %s
                     AND ass.price_change_since_article IS NOT NULL
                   GROUP BY ass.ticker
                   ORDER BY max_change DESC
                   LIMIT 10""",
                (since,)
            )
            ticker_stats = cursor.fetchall()

            # Total counts
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM rss_items WHERE published_at >= %s",
                (since,)
            )
            total_articles = cursor.fetchone()['cnt']

            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM alert_log WHERE sent_at >= %s",
                (since,)
            )
            total_alerts = cursor.fetchone()['cnt']

        lines = [
            f"📅 <b>Weekly Report</b> — {(datetime.now() - timedelta(days=7)).strftime('%b %d')} to {datetime.now().strftime('%b %d, %Y')}\n",
            f"📰 Articles: {total_articles} | 🔔 Alerts: {total_alerts}\n"
        ]

        if keyword_stats:
            lines.append("<b>Most Active Keywords:</b>")
            for ks in keyword_stats[:5]:
                lines.append(f"  • <b>{ks['keyword']}</b> — {ks['alert_count']} alerts")

        if keyword_impact:
            lines.append(f"\n<b>Keywords with Highest Price Impact:</b>")
            for ki in keyword_impact[:5]:
                avg = float(ki['avg_impact'] or 0)
                lines.append(f"  • <b>{ki['keyword']}</b> — avg |{avg:.2f}%| across {ki['cnt']} articles")

        if ticker_stats:
            lines.append(f"\n<b>Most Volatile Tickers:</b>")
            for ts in ticker_stats[:5]:
                max_chg = float(ts['max_change'] or 0)
                avg_chg = float(ts['avg_change'] or 0)
                lines.append(
                    f"  • <b>{ts['ticker']}</b> — max |{max_chg:.2f}%|, "
                    f"avg {avg_chg:+.2f}% ({ts['article_count']} articles)"
                )

        if not keyword_stats and not ticker_stats:
            lines.append("Not enough data for this week's report.")

        message = '\n'.join(lines)
        chats = _get_subscribed_chats(db_config, 'weekly_report')
        sent = 0
        for chat_id in chats:
            if _send_telegram_message(chat_id, message):
                sent += 1

        return {'status': 'success', 'sent': sent}

    except Exception as e:
        logger.error(f"Error generating weekly report: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Full Daily Pipeline
# ---------------------------------------------------------------------------

def run_daily_pipeline(db_config: Dict[str, str], params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Run the full daily pipeline:
    1. Fetch stock prices for articles with tickers
    2. Build article-stock snapshots
    3. Send Telegram report (if configured)
    """
    params = params or {}
    results = {}

    # Step 1: Fetch stock prices
    logger.info("=== Step 1: Fetching stock prices ===")
    price_result = fetch_stock_prices(db_config, {
        'limit': int(params.get('limit', 50)),
        'days_around': int(params.get('days_around', 2))
    })
    results['stock_prices'] = price_result

    if price_result.get('status') == 'error':
        logger.error(f"Stock price fetch failed: {price_result.get('error')}")
        # Continue anyway — snapshots may still work with existing price data

    # Step 2: Get impact summary for logging
    logger.info("=== Step 2: News impact analysis ===")
    impact_result = get_news_impact(db_config, {'limit': 10, 'sort': 'change'})
    results['top_movers'] = {
        'status': impact_result.get('status'),
        'count': impact_result.get('count', 0)
    }

    if impact_result.get('items'):
        for item in impact_result['items'][:5]:
            logger.info(f"  {item.get('ticker')}: {item.get('change_pct', 0):+.2f}% — "
                        f"{str(item.get('title', ''))[:60]}")

    # Step 3: Send Telegram report (if configured)
    send_telegram = params.get('send_report', True)
    if send_telegram and TelegramReportService is not None:
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        if bot_token:
            logger.info("=== Step 3: Sending Telegram report ===")
            report_result = send_report(db_config, params)
            results['telegram_report'] = report_result
        else:
            logger.info("=== Step 3: Skipped (TELEGRAM_BOT_TOKEN not set) ===")
            results['telegram_report'] = {'status': 'skipped', 'reason': 'TELEGRAM_BOT_TOKEN not set'}
    else:
        logger.info("=== Step 3: Skipped (report disabled or fpdf2 missing) ===")
        results['telegram_report'] = {'status': 'skipped', 'reason': 'disabled or fpdf2 missing'}

    results['status'] = 'success'
    results['message'] = 'Daily pipeline completed'
    return results


# ---------------------------------------------------------------------------
# Lambda Handler
# ---------------------------------------------------------------------------

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler — Daily Stock Price & Analysis + Digests

    Supported actions:
    - run_daily (default): Full pipeline — prices → snapshots → report
    - fetch_stock_prices: Fetch stock prices only
    - news_impact: Query news impact data
    - send_report: Generate and send Telegram PDF report
    - morning_brief: Send morning digest to subscribed chats
    - eod_recap: Send end-of-day recap to subscribed chats
    - weekly_report: Send weekly keyword-impact report to subscribed chats

    Args:
        event: Lambda event object with optional 'action' and 'params'
        context: Lambda context object

    Returns:
        Dict with response data
    """
    logger.info(f"Daily Lambda invoked with event: {json.dumps(event)}")

    db_config = get_db_config()
    action = event.get('action', 'run_daily')
    params = event.get('params', {})

    try:
        if action == 'run_daily':
            result = run_daily_pipeline(db_config, params)

        elif action == 'fetch_stock_prices':
            result = fetch_stock_prices(db_config, params)

        elif action == 'news_impact':
            result = get_news_impact(db_config, params)

        elif action == 'send_report':
            result = send_report(db_config, params)

        elif action == 'morning_brief':
            result = morning_brief(db_config, params)

        elif action == 'eod_recap':
            result = eod_recap(db_config, params)

        elif action == 'weekly_report':
            result = weekly_report(db_config, params)

        else:
            result = {
                'status': 'error',
                'error': f'Unknown action: {action}',
                'available_actions': [
                    'run_daily',
                    'fetch_stock_prices',
                    'news_impact',
                    'send_report',
                    'morning_brief',
                    'eod_recap',
                    'weekly_report'
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
        logger.error(f"Daily Lambda execution error: {e}", exc_info=True)
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
        'daily': {'action': 'run_daily'},
        'prices': {'action': 'fetch_stock_prices', 'params': {'limit': 10}},
        'impact': {'action': 'news_impact', 'params': {'limit': 10}},
        'report': {'action': 'send_report'},
    }

    action_name = sys.argv[1] if len(sys.argv) > 1 else 'daily'
    test_event = test_actions.get(action_name, {'action': action_name})

    class MockContext:
        def __init__(self):
            self.function_name = 'news-feed-daily-test'
            self.memory_limit_in_mb = 256
            self.invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789:function:news-feed-daily-test'
            self.aws_request_id = 'test-request-id'

    print(f"Testing action: {test_event.get('action')}")
    result = lambda_handler(test_event, MockContext())
    print(json.dumps(json.loads(result['body']), indent=2, default=str))
