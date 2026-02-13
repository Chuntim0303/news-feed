"""
Stock Price Service

Fetches stock price data using Twelve Data API and stores it in the database.
Also builds article-stock snapshots for news impact analysis.

Twelve Data free tier: 8 API calls per minute, 800 per day.

Usage:
    service = StockPriceService()

    # Fetch and store daily prices for a ticker around a specific date
    service.fetch_and_store_prices("GOOGL", date="2026-02-10")

    # Fetch prices for all articles and build snapshots
    service.fetch_prices_for_articles()
"""

import os
import time
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import HTTPError

import pymysql

logger = logging.getLogger(__name__)


class StockPriceService:
    """Fetch stock prices via Twelve Data API and build article-stock snapshots."""

    TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"
    # 8 calls/min = 1 call per 8 seconds
    RATE_LIMIT_DELAY = 8.0

    def __init__(self, db_config: Dict = None, api_key: str = None):
        self.api_key = api_key or os.environ.get('TWELVE_DATA_API_KEY', '')
        if not self.api_key:
            logger.warning("TWELVE_DATA_API_KEY not set")
        if db_config:
            self.db_config = db_config
        else:
            self.db_config = {
                'host': os.environ.get('DB_HOST', 'localhost'),
                'user': os.environ.get('DB_USER', 'root'),
                'password': os.environ.get('DB_PASSWORD', ''),
                'database': os.environ.get('DB_NAME', 'news_feed'),
                'port': int(os.environ.get('DB_PORT', 3306)),
            }
        self._last_request_time = 0

    def _get_connection(self):
        return pymysql.connect(
            **self.db_config,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

    def _rate_limit(self):
        """Enforce rate limit: wait if needed to stay under 8 calls/min."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            wait = self.RATE_LIMIT_DELAY - elapsed
            time.sleep(wait)
        self._last_request_time = time.time()

    def _api_request(self, endpoint: str, params: Dict) -> Optional[Dict]:
        """
        Make a request to the Twelve Data API.

        Args:
            endpoint: API endpoint (e.g., '/time_series')
            params: Query parameters

        Returns:
            Parsed JSON response or None on error
        """
        self._rate_limit()

        params['apikey'] = self.api_key
        query_string = '&'.join(f"{k}={v}" for k, v in params.items())
        url = f"{self.TWELVE_DATA_BASE_URL}{endpoint}?{query_string}"

        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urlopen(req, timeout=15)
            data = json.loads(response.read().decode('utf-8'))

            if data.get('status') == 'error':
                return None

            return data

        except HTTPError as e:
            if e.code == 429:
                logger.warning("rate limited, waiting 60s...")
                time.sleep(60)
                self._last_request_time = time.time()
                return self._api_request(endpoint, params)
            return None
        except Exception:
            return None

    def fetch_prices(self, ticker: str, start_date: str, end_date: str) -> List[Dict]:
        """
        Fetch daily OHLCV data for a ticker from Twelve Data.

        Args:
            ticker: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            List of daily price dicts
        """
        data = self._api_request('/time_series', {
            'symbol': ticker,
            'interval': '1day',
            'start_date': start_date,
            'end_date': end_date,
            'order': 'asc',
        })

        if not data or 'values' not in data:
            return []

        prices = []
        for v in data['values']:
            try:
                prices.append({
                    'ticker': ticker,
                    'price': float(v['close']),
                    'open_price': float(v['open']),
                    'high_price': float(v['high']),
                    'low_price': float(v['low']),
                    'close_price': float(v['close']),
                    'volume': int(v['volume']) if v.get('volume') else 0,
                    'price_date': v['datetime'][:10],
                })
            except (ValueError, KeyError):
                continue

        # Calculate change amounts
        for i, p in enumerate(prices):
            if i > 0:
                prev_close = prices[i - 1]['close_price']
                if prev_close > 0:
                    p['change_amount'] = round(p['close_price'] - prev_close, 4)
                    p['change_percent'] = round(
                        ((p['close_price'] - prev_close) / prev_close) * 100, 4
                    )
                else:
                    p['change_amount'] = 0
                    p['change_percent'] = 0
            else:
                p['change_amount'] = 0
                p['change_percent'] = 0

        return prices

    def store_prices(self, prices: List[Dict]) -> int:
        """
        Store price data in the stock_prices table.

        Returns:
            Number of rows inserted/updated
        """
        if not prices:
            return 0

        connection = self._get_connection()
        count = 0
        try:
            with connection.cursor() as cursor:
                for p in prices:
                    cursor.execute(
                        """INSERT INTO stock_prices
                           (ticker, price, open_price, high_price, low_price,
                            close_price, volume, change_amount, change_percent, price_date)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON DUPLICATE KEY UPDATE
                               price = VALUES(price),
                               open_price = VALUES(open_price),
                               high_price = VALUES(high_price),
                               low_price = VALUES(low_price),
                               close_price = VALUES(close_price),
                               volume = VALUES(volume),
                               change_amount = VALUES(change_amount),
                               change_percent = VALUES(change_percent)""",
                        (p['ticker'], p['price'], p['open_price'], p['high_price'],
                         p['low_price'], p['close_price'], p['volume'],
                         p['change_amount'], p['change_percent'], p['price_date'])
                    )
                    count += cursor.rowcount

            connection.commit()
        finally:
            connection.close()

        return count

    def fetch_and_store_prices(self, ticker: str, date: str, days_around: int = 2) -> int:
        """
        Fetch prices around a specific date and store in DB.

        Args:
            ticker: Stock ticker symbol
            date: Center date (YYYY-MM-DD)
            days_around: Days before and after to fetch

        Returns:
            Number of rows stored
        """
        center = datetime.strptime(date, '%Y-%m-%d')
        start = (center - timedelta(days=days_around)).strftime('%Y-%m-%d')
        end = (center + timedelta(days=days_around)).strftime('%Y-%m-%d')

        prices = self.fetch_prices(ticker, start, end)
        if prices:
            return self.store_prices(prices)
        return 0

    def fetch_prices_for_articles(self, limit: int = 200, days_around: int = 2,
                                   lookback_hours: int = 48):
        """
        Find articles with tickers, fetch price data around their publication dates.
        Only fetches a small window (days_around) before/after each article date.

        Processes two groups to ensure full coverage:
        1. Articles that have never been snapshotted
        2. Recent articles whose snapshots have NULL prices (data wasn't available yet)

        Args:
            limit: Max number of articles to process per group
            days_around: Days before/after publication to fetch
            lookback_hours: How far back to look for articles needing re-processing
        """
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                # Group 1: Articles with tickers not yet price-processed
                cursor.execute(
                    """SELECT DISTINCT ri.id, ri.title, ri.stock_tickers,
                              ri.published_at, ri.created_at
                       FROM rss_items ri
                       WHERE ri.stock_tickers IS NOT NULL
                         AND ri.stock_tickers != ''
                         AND ri.price_processed = 0
                       ORDER BY ri.published_at DESC
                       LIMIT %s""",
                    (limit,)
                )
                new_articles = list(cursor.fetchall())
                logger.info(f"[DAILY] Found {len(new_articles)} articles not yet price-processed")

                # Group 2: Recent articles whose snapshots have NULL prices
                # (prices may not have been available when first processed)
                cursor.execute(
                    """SELECT DISTINCT ri.id, ri.title, ri.stock_tickers,
                              ri.published_at, ri.created_at
                       FROM rss_items ri
                       JOIN article_stock_snapshots ass ON ass.article_id = ri.id
                       WHERE ri.stock_tickers IS NOT NULL
                         AND ri.stock_tickers != ''
                         AND (ass.price_at_publication IS NULL
                              OR ass.price_current IS NULL)
                         AND ri.created_at >= NOW() - INTERVAL %s HOUR
                       ORDER BY ri.published_at DESC
                       LIMIT %s""",
                    (lookback_hours, limit)
                )
                retry_articles = list(cursor.fetchall())
                logger.info(f"[DAILY] Found {len(retry_articles)} articles with incomplete snapshots "
                            f"(within last {lookback_hours}h)")

            # Merge and deduplicate
            seen_ids = set()
            articles = []
            for article in new_articles + retry_articles:
                if article['id'] not in seen_ids:
                    seen_ids.add(article['id'])
                    articles.append(article)

            if not articles:
                logger.info("No articles need price data.")
                return

            logger.info(f"Processing {len(articles)} articles...")

            # Collect unique (ticker, date_range) pairs to minimize API calls
            # Group by ticker -> merge overlapping date ranges
            ticker_dates = {}
            for article in articles:
                tickers = [t.strip() for t in article['stock_tickers'].split(',') if t.strip()]
                pub_date = article['published_at']
                if pub_date:
                    for ticker in tickers:
                        if ticker not in ticker_dates:
                            ticker_dates[ticker] = {'min_date': pub_date, 'max_date': pub_date}
                        else:
                            if pub_date < ticker_dates[ticker]['min_date']:
                                ticker_dates[ticker]['min_date'] = pub_date
                            if pub_date > ticker_dates[ticker]['max_date']:
                                ticker_dates[ticker]['max_date'] = pub_date

            total = len(ticker_dates)
            total_stored = 0
            failed = []

            logger.info(f"Fetching prices for {total} unique tickers (8 calls/min)...")
            est_minutes = (total * self.RATE_LIMIT_DELAY) / 60
            logger.info(f"Estimated time: ~{est_minutes:.1f} minutes")

            for i, (ticker, dates) in enumerate(ticker_dates.items(), 1):
                start = (dates['min_date'] - timedelta(days=days_around)).strftime('%Y-%m-%d')
                end = (dates['max_date'] + timedelta(days=days_around)).strftime('%Y-%m-%d')

                logger.info(f"  [{i}/{total}] {ticker} ({start} to {end})...")

                prices = self.fetch_prices(ticker, start, end)
                if prices:
                    stored = self.store_prices(prices)
                    total_stored += stored
                    logger.info(f"    {len(prices)} days, {stored} stored")
                else:
                    failed.append(ticker)
                    logger.info(f"    no data")

            if failed:
                logger.warning(f"No data for ({len(failed)}): {', '.join(failed)}")

            logger.info(f"Total: {total_stored} price records stored")

            # Now build snapshots
            self.build_article_snapshots(articles)

        finally:
            connection.close()

    def build_article_snapshots(self, articles: Optional[List[Dict]] = None):
        """
        Build article_stock_snapshots entries linking articles to price data.
        For each article+ticker, records:
        - price_at_publication: closing price on or before the article's publication date
        - price_current: closing price on the next trading day
        - price_change_since_article: % change
        """
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                if articles is None:
                    cursor.execute(
                        """SELECT DISTINCT ri.id, ri.title, ri.stock_tickers, ri.published_at
                           FROM rss_items ri
                           WHERE ri.stock_tickers IS NOT NULL
                             AND ri.stock_tickers != ''
                             AND ri.price_processed = 0
                           ORDER BY ri.published_at DESC
                           LIMIT 100"""
                    )
                    articles = cursor.fetchall()

                if not articles:
                    logger.info("No articles to build snapshots for.")
                    return

                snapshot_count = 0
                for article in articles:
                    tickers = [t.strip() for t in article['stock_tickers'].split(',') if t.strip()]
                    pub_date = article['published_at']

                    if not pub_date:
                        continue

                    pub_date_str = pub_date.strftime('%Y-%m-%d') if isinstance(pub_date, datetime) else str(pub_date)[:10]

                    for ticker in tickers:
                        # Get price on or just before publication date
                        cursor.execute(
                            """SELECT close_price, price_date FROM stock_prices
                               WHERE ticker = %s AND price_date <= %s
                               ORDER BY price_date DESC LIMIT 1""",
                            (ticker, pub_date_str)
                        )
                        pub_price_row = cursor.fetchone()

                        # Get price on the next trading day after publication
                        cursor.execute(
                            """SELECT close_price, price_date FROM stock_prices
                               WHERE ticker = %s AND price_date > %s
                               ORDER BY price_date ASC LIMIT 1""",
                            (ticker, pub_date_str)
                        )
                        next_price_row = cursor.fetchone()

                        price_at_pub = pub_price_row['close_price'] if pub_price_row else None
                        price_after = next_price_row['close_price'] if next_price_row else None

                        # Calculate % change
                        change_pct = None
                        if price_at_pub and price_after and float(price_at_pub) > 0:
                            change_pct = round(
                                ((float(price_after) - float(price_at_pub)) / float(price_at_pub)) * 100, 4
                            )

                        try:
                            cursor.execute(
                                """INSERT INTO article_stock_snapshots
                                   (article_id, ticker, price_at_publication, price_current,
                                    price_change_since_article)
                                   VALUES (%s, %s, %s, %s, %s)
                                   ON DUPLICATE KEY UPDATE
                                       price_current = VALUES(price_current),
                                       price_change_since_article = VALUES(price_change_since_article)""",
                                (article['id'], ticker, price_at_pub, price_after, change_pct)
                            )
                            snapshot_count += 1
                        except pymysql.err.IntegrityError:
                            pass

                    # Mark article as price-processed regardless of whether prices were found
                    cursor.execute(
                        """UPDATE rss_items SET price_processed = 1 WHERE id = %s""",
                        (article['id'],)
                    )

                connection.commit()
                logger.info(f"Built {snapshot_count} article-stock snapshots")

        finally:
            connection.close()

    def get_article_tickers(self) -> List[str]:
        """Get all unique tickers mentioned in articles."""
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT DISTINCT stock_tickers FROM rss_items
                       WHERE stock_tickers IS NOT NULL AND stock_tickers != ''"""
                )
                rows = cursor.fetchall()

            tickers = set()
            for row in rows:
                for t in row['stock_tickers'].split(','):
                    t = t.strip()
                    if t:
                        tickers.add(t)

            return sorted(tickers)
        finally:
            connection.close()
