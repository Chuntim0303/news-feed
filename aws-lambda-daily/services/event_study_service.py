"""
Event Study Service

Implements multi-horizon event study methodology for stock impact analysis.
Replaces simple "next-day change" with proper event windows and abnormal returns.

Key features:
- Multi-horizon returns: +1D, +3D, +5D, +10D
- Pre-event baseline: -1D, -3D, -5D (leakage detection)
- Abnormal returns: stock return - benchmark return
- Volume and volatility metrics for market reaction scoring
- Processing status tracking with retry logic

Usage:
    service = EventStudyService(db_config=db_config)
    service.compute_event_windows(article_id=123, ticker='MRNA')
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import HTTPError
import json

import pymysql

logger = logging.getLogger(__name__)


class EventStudyService:
    """Compute multi-horizon event study returns with abnormal return calculations."""

    TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"
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
        """Make a request to the Twelve Data API."""
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
                logger.warning("Rate limited, waiting 60s...")
                time.sleep(60)
                self._last_request_time = time.time()
                return self._api_request(endpoint, params)
            return None
        except Exception:
            return None

    # =========================================================================
    # Price data fetching
    # =========================================================================

    def fetch_prices_around_date(self, ticker: str, center_date: datetime, 
                                  days_before: int = 5, days_after: int = 10) -> List[Dict]:
        """
        Fetch daily OHLCV data around a specific date.
        
        Args:
            ticker: Stock ticker
            center_date: Event date (article publication)
            days_before: Days before event to fetch
            days_after: Days after event to fetch
            
        Returns:
            List of daily price dicts with date, open, high, low, close, volume
        """
        start_date = (center_date - timedelta(days=days_before + 25)).strftime('%Y-%m-%d')
        end_date = (center_date + timedelta(days=days_after + 5)).strftime('%Y-%m-%d')

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
                    'date': datetime.strptime(v['datetime'][:10], '%Y-%m-%d'),
                    'open': float(v['open']),
                    'high': float(v['high']),
                    'low': float(v['low']),
                    'close': float(v['close']),
                    'volume': int(v['volume']) if v.get('volume') else 0,
                })
            except (ValueError, KeyError):
                continue

        return sorted(prices, key=lambda x: x['date'])

    # =========================================================================
    # Return calculations
    # =========================================================================

    def compute_returns(self, prices: List[Dict], event_date: datetime) -> Dict:
        """
        Compute multi-horizon returns around an event date.
        
        Args:
            prices: List of price dicts sorted by date
            event_date: Event date (article publication)
            
        Returns:
            Dict with return_pre_1d, return_pre_3d, return_pre_5d,
            return_1d, return_3d, return_5d, return_10d
        """
        if not prices:
            return {}

        # Find event date index (or closest trading day before)
        event_idx = None
        for i, p in enumerate(prices):
            if p['date'] <= event_date:
                event_idx = i
            else:
                break

        if event_idx is None:
            return {}

        event_price = prices[event_idx]['close']
        
        returns = {}

        # Pre-event returns (looking backward)
        for days, key in [(1, 'return_pre_1d'), (3, 'return_pre_3d'), (5, 'return_pre_5d')]:
            pre_idx = event_idx - days
            if pre_idx >= 0:
                pre_price = prices[pre_idx]['close']
                if pre_price > 0:
                    returns[key] = round(((event_price - pre_price) / pre_price) * 100, 4)

        # Post-event returns (looking forward)
        for days, key in [(1, 'return_1d'), (3, 'return_3d'), (5, 'return_5d'), (10, 'return_10d')]:
            post_idx = event_idx + days
            if post_idx < len(prices):
                post_price = prices[post_idx]['close']
                if event_price > 0:
                    returns[key] = round(((post_price - event_price) / event_price) * 100, 4)

        return returns

    def compute_volume_metrics(self, prices: List[Dict], event_date: datetime) -> Dict:
        """
        Compute volume metrics: baseline, ratio, z-score.
        
        Args:
            prices: List of price dicts sorted by date
            event_date: Event date
            
        Returns:
            Dict with volume_baseline_20d, volume_1d, volume_ratio_1d, volume_zscore_1d
        """
        if not prices:
            return {}

        # Find event date index
        event_idx = None
        for i, p in enumerate(prices):
            if p['date'] <= event_date:
                event_idx = i
            else:
                break

        if event_idx is None or event_idx + 1 >= len(prices):
            return {}

        # Get 20-day baseline before event
        baseline_start = max(0, event_idx - 20)
        baseline_volumes = [p['volume'] for p in prices[baseline_start:event_idx] if p['volume'] > 0]

        if not baseline_volumes:
            return {}

        baseline_avg = sum(baseline_volumes) / len(baseline_volumes)
        baseline_std = (sum((v - baseline_avg) ** 2 for v in baseline_volumes) / len(baseline_volumes)) ** 0.5

        # Get +1 day volume
        volume_1d = prices[event_idx + 1]['volume']

        metrics = {
            'volume_baseline_20d': int(baseline_avg),
            'volume_1d': volume_1d,
        }

        if baseline_avg > 0:
            metrics['volume_ratio_1d'] = round(volume_1d / baseline_avg, 2)

        if baseline_std > 0:
            metrics['volume_zscore_1d'] = round((volume_1d - baseline_avg) / baseline_std, 2)

        return metrics

    def compute_volatility_metrics(self, prices: List[Dict], event_date: datetime) -> Dict:
        """
        Compute volatility metrics: baseline volatility, intraday range, gap.
        
        Args:
            prices: List of price dicts sorted by date
            event_date: Event date
            
        Returns:
            Dict with volatility_baseline_20d, intraday_range_1d, gap_magnitude
        """
        if not prices:
            return {}

        event_idx = None
        for i, p in enumerate(prices):
            if p['date'] <= event_date:
                event_idx = i
            else:
                break

        if event_idx is None or event_idx + 1 >= len(prices):
            return {}

        # Compute 20-day realized volatility before event
        baseline_start = max(0, event_idx - 20)
        daily_returns = []
        for i in range(baseline_start + 1, event_idx + 1):
            if prices[i - 1]['close'] > 0:
                ret = (prices[i]['close'] - prices[i - 1]['close']) / prices[i - 1]['close']
                daily_returns.append(ret)

        metrics = {}

        if daily_returns:
            mean_ret = sum(daily_returns) / len(daily_returns)
            variance = sum((r - mean_ret) ** 2 for r in daily_returns) / len(daily_returns)
            volatility = (variance ** 0.5) * (252 ** 0.5)
            metrics['volatility_baseline_20d'] = round(volatility * 100, 4)

        # Intraday range on +1 day
        next_day = prices[event_idx + 1]
        if next_day['open'] > 0:
            intraday_range = ((next_day['high'] - next_day['low']) / next_day['open']) * 100
            metrics['intraday_range_1d'] = round(intraday_range, 4)

        # Gap from previous close to next open
        prev_close = prices[event_idx]['close']
        if prev_close > 0:
            gap = ((next_day['open'] - prev_close) / prev_close) * 100
            metrics['gap_magnitude'] = round(gap, 4)

        return metrics

    # =========================================================================
    # Benchmark returns
    # =========================================================================

    def get_benchmark_returns(self, ticker: str, event_date: datetime) -> Dict:
        """
        Get benchmark returns for abnormal return calculation.
        
        Args:
            ticker: Stock ticker
            event_date: Event date
            
        Returns:
            Dict with benchmark_return_1d, benchmark_return_3d, etc.
        """
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                # Get sector benchmark for this ticker
                cursor.execute(
                    """SELECT sector_etf, market_benchmark 
                       FROM ticker_sector_mapping 
                       WHERE ticker = %s""",
                    (ticker,)
                )
                mapping = cursor.fetchone()

                if not mapping:
                    benchmark_ticker = 'SPY'
                else:
                    benchmark_ticker = mapping['sector_etf'] or mapping['market_benchmark'] or 'SPY'

                # Get benchmark returns around event date
                event_date_str = event_date.strftime('%Y-%m-%d')
                cursor.execute(
                    """SELECT return_1d, return_3d, return_5d, return_10d
                       FROM benchmark_returns
                       WHERE ticker = %s AND return_date = %s""",
                    (benchmark_ticker, event_date_str)
                )
                result = cursor.fetchone()

                if result:
                    return {
                        'benchmark_return_1d': result['return_1d'],
                        'benchmark_return_3d': result['return_3d'],
                        'benchmark_return_5d': result['return_5d'],
                        'benchmark_return_10d': result['return_10d'],
                    }

                return {}

        finally:
            connection.close()

    def compute_abnormal_returns(self, stock_returns: Dict, benchmark_returns: Dict) -> Dict:
        """
        Compute abnormal returns (stock return - benchmark return).
        
        Args:
            stock_returns: Dict with return_1d, return_3d, etc.
            benchmark_returns: Dict with benchmark_return_1d, etc.
            
        Returns:
            Dict with abnormal_return_1d, abnormal_return_3d, etc.
        """
        abnormal = {}

        for horizon in ['1d', '3d', '5d', '10d']:
            stock_key = f'return_{horizon}'
            bench_key = f'benchmark_return_{horizon}'
            abnormal_key = f'abnormal_return_{horizon}'

            if stock_key in stock_returns and bench_key in benchmark_returns:
                if stock_returns[stock_key] is not None and benchmark_returns[bench_key] is not None:
                    abnormal[abnormal_key] = round(
                        stock_returns[stock_key] - benchmark_returns[bench_key], 4
                    )

        return abnormal

    # =========================================================================
    # Main processing
    # =========================================================================

    def compute_event_windows(self, article_id: int, ticker: str, 
                              published_at: datetime = None) -> Dict:
        """
        Compute full event study for an article-ticker pair.
        
        Args:
            article_id: Article ID
            ticker: Stock ticker
            published_at: Publication timestamp (fetched from DB if None)
            
        Returns:
            Dict with all computed metrics
        """
        connection = self._get_connection()
        
        try:
            # Get article publication date if not provided
            if published_at is None:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT published_at FROM rss_items WHERE id = %s",
                        (article_id,)
                    )
                    row = cursor.fetchone()
                    if not row:
                        return {'status': 'error', 'message': 'Article not found'}
                    published_at = row['published_at']

            logger.info(f"[EVENT_STUDY] Computing windows for article {article_id}, "
                       f"ticker {ticker}, date {published_at}")

            # Fetch price data
            prices = self.fetch_prices_around_date(ticker, published_at, days_before=25, days_after=15)
            
            if not prices:
                self._update_processing_status(
                    article_id, ticker, 'failed', 'No price data available'
                )
                return {'status': 'error', 'message': 'No price data available'}

            # Compute all metrics
            returns = self.compute_returns(prices, published_at)
            volume_metrics = self.compute_volume_metrics(prices, published_at)
            volatility_metrics = self.compute_volatility_metrics(prices, published_at)
            benchmark_returns = self.get_benchmark_returns(ticker, published_at)
            abnormal_returns = self.compute_abnormal_returns(returns, benchmark_returns)

            # Merge all metrics
            metrics = {**returns, **volume_metrics, **volatility_metrics, **abnormal_returns}

            # Store in database
            self._store_event_windows(article_id, ticker, metrics)

            logger.info(f"[EVENT_STUDY] Stored metrics for {ticker}: "
                       f"return_1d={metrics.get('return_1d')}, "
                       f"abnormal_1d={metrics.get('abnormal_return_1d')}")

            return {'status': 'success', 'metrics': metrics}

        except Exception as e:
            logger.error(f"Error computing event windows: {e}", exc_info=True)
            self._update_processing_status(article_id, ticker, 'failed', str(e))
            return {'status': 'error', 'message': str(e)}

        finally:
            connection.close()

    def _store_event_windows(self, article_id: int, ticker: str, metrics: Dict):
        """Store computed metrics in article_return_windows table."""
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO article_return_windows
                       (article_id, ticker, 
                        return_pre_1d, return_pre_3d, return_pre_5d,
                        return_1d, return_3d, return_5d, return_10d,
                        abnormal_return_1d, abnormal_return_3d, 
                        abnormal_return_5d, abnormal_return_10d,
                        volume_baseline_20d, volume_1d, volume_ratio_1d, volume_zscore_1d,
                        volatility_baseline_20d, intraday_range_1d, gap_magnitude,
                        processing_status, last_processed_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                               %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                       ON DUPLICATE KEY UPDATE
                        return_pre_1d = VALUES(return_pre_1d),
                        return_pre_3d = VALUES(return_pre_3d),
                        return_pre_5d = VALUES(return_pre_5d),
                        return_1d = VALUES(return_1d),
                        return_3d = VALUES(return_3d),
                        return_5d = VALUES(return_5d),
                        return_10d = VALUES(return_10d),
                        abnormal_return_1d = VALUES(abnormal_return_1d),
                        abnormal_return_3d = VALUES(abnormal_return_3d),
                        abnormal_return_5d = VALUES(abnormal_return_5d),
                        abnormal_return_10d = VALUES(abnormal_return_10d),
                        volume_baseline_20d = VALUES(volume_baseline_20d),
                        volume_1d = VALUES(volume_1d),
                        volume_ratio_1d = VALUES(volume_ratio_1d),
                        volume_zscore_1d = VALUES(volume_zscore_1d),
                        volatility_baseline_20d = VALUES(volatility_baseline_20d),
                        intraday_range_1d = VALUES(intraday_range_1d),
                        gap_magnitude = VALUES(gap_magnitude),
                        processing_status = VALUES(processing_status),
                        last_processed_at = VALUES(last_processed_at)""",
                    (article_id, ticker,
                     metrics.get('return_pre_1d'), metrics.get('return_pre_3d'), metrics.get('return_pre_5d'),
                     metrics.get('return_1d'), metrics.get('return_3d'), 
                     metrics.get('return_5d'), metrics.get('return_10d'),
                     metrics.get('abnormal_return_1d'), metrics.get('abnormal_return_3d'),
                     metrics.get('abnormal_return_5d'), metrics.get('abnormal_return_10d'),
                     metrics.get('volume_baseline_20d'), metrics.get('volume_1d'),
                     metrics.get('volume_ratio_1d'), metrics.get('volume_zscore_1d'),
                     metrics.get('volatility_baseline_20d'), metrics.get('intraday_range_1d'),
                     metrics.get('gap_magnitude'), 'complete')
                )
            connection.commit()
        finally:
            connection.close()

    def _update_processing_status(self, article_id: int, ticker: str, 
                                   status: str, reason: str = None):
        """Update processing status for retry logic."""
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO article_return_windows
                       (article_id, ticker, processing_status, failure_reason, 
                        retry_count, last_processed_at)
                       VALUES (%s, %s, %s, %s, 1, NOW())
                       ON DUPLICATE KEY UPDATE
                        processing_status = VALUES(processing_status),
                        failure_reason = VALUES(failure_reason),
                        retry_count = retry_count + 1,
                        last_processed_at = VALUES(last_processed_at)""",
                    (article_id, ticker, status, reason)
                )
            connection.commit()
        finally:
            connection.close()

    # =========================================================================
    # Batch processing
    # =========================================================================

    def process_pending_articles(self, limit: int = 50, retry_failed: bool = True):
        """
        Process articles that need event study computation.
        
        Args:
            limit: Max articles to process
            retry_failed: Whether to retry previously failed articles
        """
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                # Get articles with tickers that need processing
                query = """
                    SELECT DISTINCT ri.id, ri.published_at, ri.stock_tickers
                    FROM rss_items ri
                    LEFT JOIN article_return_windows arw ON arw.article_id = ri.id
                    WHERE ri.stock_tickers IS NOT NULL 
                      AND ri.stock_tickers != ''
                      AND (arw.processing_status IS NULL 
                           OR arw.processing_status = 'not_started'
                """
                
                if retry_failed:
                    query += " OR (arw.processing_status = 'failed' AND arw.retry_count < 3)"
                
                query += ") ORDER BY ri.published_at DESC LIMIT %s"
                
                cursor.execute(query, (limit,))
                articles = cursor.fetchall()

            logger.info(f"[EVENT_STUDY] Found {len(articles)} articles to process")

            processed = 0
            for article in articles:
                tickers = [t.strip() for t in article['stock_tickers'].split(',') if t.strip()]
                
                for ticker in tickers:
                    result = self.compute_event_windows(
                        article['id'], ticker, article['published_at']
                    )
                    if result.get('status') == 'success':
                        processed += 1

            logger.info(f"[EVENT_STUDY] Processed {processed} article-ticker pairs")
            return {'status': 'success', 'processed': processed}

        finally:
            connection.close()
