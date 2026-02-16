"""
Market Reaction Service (Layer 4)

Implements Layer 4 of the news scoring model: Market Reaction Score.
Confirms whether the market is actually reacting to the news by analyzing:
- Volume spikes (vs 20-day baseline)
- Price gaps (pre-market/open vs previous close)
- Trending ticker mentions (frequency vs baseline)

This layer prevents false positives where news sounds important but the market ignores it.

Usage:
    service = MarketReactionService(db_config=db_config)
    score = service.compute_reaction_score(article_id=123, ticker='MRNA')
    # Returns: {'total_score': 4.0, 'volume_score': 2.0, 'gap_score': 2.0, 'trend_score': 0.0}
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import pymysql

logger = logging.getLogger(__name__)


class MarketReactionService:
    """Compute Layer 4 market reaction scores for articles."""

    def __init__(self, db_config: Dict = None):
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

    def _get_connection(self):
        return pymysql.connect(
            **self.db_config,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

    # =========================================================================
    # Volume spike detection
    # =========================================================================

    def compute_volume_score(self, article_id: int, ticker: str) -> float:
        """
        Compute volume spike score (0-2 points).
        
        Scoring:
        - Volume > 3× baseline: +2
        - Volume > 2× baseline: +1
        - Otherwise: 0
        
        Args:
            article_id: Article ID
            ticker: Stock ticker
            
        Returns:
            Volume score (0-2)
        """
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT volume_ratio_1d, volume_zscore_1d
                       FROM article_return_windows
                       WHERE article_id = %s AND ticker = %s""",
                    (article_id, ticker)
                )
                result = cursor.fetchone()

                if not result or result['volume_ratio_1d'] is None:
                    return 0.0

                ratio = float(result['volume_ratio_1d'])

                if ratio >= 3.0:
                    return 2.0
                elif ratio >= 2.0:
                    return 1.0
                else:
                    return 0.0

        finally:
            connection.close()

    # =========================================================================
    # Price gap detection
    # =========================================================================

    def compute_gap_score(self, article_id: int, ticker: str) -> float:
        """
        Compute price gap score (0-2 points).
        
        Scoring:
        - Gap > 5%: +2
        - Gap > 3%: +1
        - Otherwise: 0
        
        Args:
            article_id: Article ID
            ticker: Stock ticker
            
        Returns:
            Gap score (0-2)
        """
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT gap_magnitude
                       FROM article_return_windows
                       WHERE article_id = %s AND ticker = %s""",
                    (article_id, ticker)
                )
                result = cursor.fetchone()

                if not result or result['gap_magnitude'] is None:
                    return 0.0

                gap = abs(float(result['gap_magnitude']))

                if gap >= 5.0:
                    return 2.0
                elif gap >= 3.0:
                    return 1.0
                else:
                    return 0.0

        finally:
            connection.close()

    # =========================================================================
    # Trending ticker detection
    # =========================================================================

    def compute_trend_score(self, article_id: int, ticker: str) -> float:
        """
        Compute trending ticker score (0-1 point).
        
        Scoring:
        - Mentions > 3× normal frequency in last 24h: +1
        - Otherwise: 0
        
        Args:
            article_id: Article ID
            ticker: Stock ticker
            
        Returns:
            Trend score (0-1)
        """
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                # Get article publication date
                cursor.execute(
                    "SELECT published_at FROM rss_items WHERE id = %s",
                    (article_id,)
                )
                article = cursor.fetchone()
                if not article:
                    return 0.0

                pub_date = article['published_at']

                # Count mentions in last 24 hours
                cursor.execute(
                    """SELECT COUNT(*) as recent_count
                       FROM rss_items
                       WHERE stock_tickers LIKE %s
                         AND published_at BETWEEN %s AND %s""",
                    (f'%{ticker}%', pub_date - timedelta(hours=24), pub_date)
                )
                recent = cursor.fetchone()
                recent_count = recent['recent_count'] if recent else 0

                # Count baseline mentions (7-day average before the 24h window)
                cursor.execute(
                    """SELECT COUNT(*) as baseline_count
                       FROM rss_items
                       WHERE stock_tickers LIKE %s
                         AND published_at BETWEEN %s AND %s""",
                    (f'%{ticker}%', 
                     pub_date - timedelta(days=8), 
                     pub_date - timedelta(hours=24))
                )
                baseline = cursor.fetchone()
                baseline_count = baseline['baseline_count'] if baseline else 0
                baseline_avg = baseline_count / 7.0 if baseline_count > 0 else 0.5

                # Check if trending (3× normal frequency)
                if recent_count >= baseline_avg * 3:
                    return 1.0
                else:
                    return 0.0

        finally:
            connection.close()

    # =========================================================================
    # Composite reaction score
    # =========================================================================

    def compute_reaction_score(self, article_id: int, ticker: str) -> Dict:
        """
        Compute full Layer 4 market reaction score.
        
        Args:
            article_id: Article ID
            ticker: Stock ticker
            
        Returns:
            Dict with volume_score, gap_score, trend_score, total_score
        """
        volume_score = self.compute_volume_score(article_id, ticker)
        gap_score = self.compute_gap_score(article_id, ticker)
        trend_score = self.compute_trend_score(article_id, ticker)

        total_score = volume_score + gap_score + trend_score

        logger.info(f"[MARKET_REACTION] Article {article_id}, ticker {ticker}: "
                   f"volume={volume_score}, gap={gap_score}, trend={trend_score}, "
                   f"total={total_score}")

        result = {
            'volume_score': volume_score,
            'gap_score': gap_score,
            'trend_score': trend_score,
            'total_score': total_score,
        }

        # Cache the result
        self._store_reaction_score(article_id, ticker, result)

        return result

    def _store_reaction_score(self, article_id: int, ticker: str, scores: Dict):
        """Store computed reaction score in market_reaction_scores table."""
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO market_reaction_scores
                       (article_id, ticker, volume_score, gap_score, 
                        trend_score, total_reaction_score)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE
                        volume_score = VALUES(volume_score),
                        gap_score = VALUES(gap_score),
                        trend_score = VALUES(trend_score),
                        total_reaction_score = VALUES(total_reaction_score),
                        computed_at = CURRENT_TIMESTAMP""",
                    (article_id, ticker, scores['volume_score'], scores['gap_score'],
                     scores['trend_score'], scores['total_score'])
                )
            connection.commit()
        finally:
            connection.close()

    def get_cached_reaction_score(self, article_id: int, ticker: str) -> Optional[Dict]:
        """
        Get cached reaction score if available.
        
        Args:
            article_id: Article ID
            ticker: Stock ticker
            
        Returns:
            Dict with scores or None if not cached
        """
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT volume_score, gap_score, trend_score, total_reaction_score
                       FROM market_reaction_scores
                       WHERE article_id = %s AND ticker = %s""",
                    (article_id, ticker)
                )
                result = cursor.fetchone()

                if result:
                    return {
                        'volume_score': float(result['volume_score']),
                        'gap_score': float(result['gap_score']),
                        'trend_score': float(result['trend_score']),
                        'total_score': float(result['total_reaction_score']),
                    }

                return None

        finally:
            connection.close()

    # =========================================================================
    # Batch processing
    # =========================================================================

    def process_pending_reactions(self, limit: int = 50):
        """
        Compute reaction scores for articles that have event windows but no reaction score.
        
        Args:
            limit: Max articles to process
        """
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                # Get articles with event windows but no reaction scores
                cursor.execute(
                    """SELECT DISTINCT arw.article_id, arw.ticker
                       FROM article_return_windows arw
                       LEFT JOIN market_reaction_scores mrs 
                         ON mrs.article_id = arw.article_id AND mrs.ticker = arw.ticker
                       WHERE arw.processing_status = 'complete'
                         AND mrs.id IS NULL
                       ORDER BY arw.updated_at DESC
                       LIMIT %s""",
                    (limit,)
                )
                pending = cursor.fetchall()

            logger.info(f"[MARKET_REACTION] Found {len(pending)} article-ticker pairs to process")

            processed = 0
            for item in pending:
                self.compute_reaction_score(item['article_id'], item['ticker'])
                processed += 1

            logger.info(f"[MARKET_REACTION] Processed {processed} reaction scores")
            return {'status': 'success', 'processed': processed}

        finally:
            connection.close()
