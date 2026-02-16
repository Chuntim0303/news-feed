"""
Confounder Detection Service

Identifies confounding events that may affect stock price attribution:
- Earnings announcements
- FDA PDUFA dates
- Fed meetings (FOMC)
- CPI/macro releases
- Sector-wide moves

Usage:
    service = ConfounderService(db_config=db_config)
    confounders = service.detect_confounders(ticker='MRNA', date='2026-02-15')
    # Returns: [{'type': 'earnings', 'description': 'Q4 earnings call'}, ...]
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pymysql

logger = logging.getLogger(__name__)


class ConfounderService:
    """Detect confounding events for attribution analysis."""

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
    # Confounder detection
    # =========================================================================

    def detect_confounders(self, ticker: str, event_date: datetime, 
                           window_days: int = 1) -> List[Dict]:
        """
        Detect confounding events around a specific date.
        
        Args:
            ticker: Stock ticker
            event_date: Event date to check
            window_days: Days before/after to check
            
        Returns:
            List of confounder dicts with type and description
        """
        confounders = []

        # Check database for known confounders
        db_confounders = self._get_db_confounders(ticker, event_date, window_days)
        confounders.extend(db_confounders)

        # Check for sector-wide moves
        sector_move = self._detect_sector_move(ticker, event_date)
        if sector_move:
            confounders.append(sector_move)

        # Check for multiple articles on same ticker/date (event clustering)
        article_cluster = self._detect_article_clustering(ticker, event_date)
        if article_cluster:
            confounders.append(article_cluster)

        return confounders

    def _get_db_confounders(self, ticker: str, event_date: datetime, 
                            window_days: int) -> List[Dict]:
        """Get confounders from confounder_events table."""
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                start_date = event_date - timedelta(days=window_days)
                end_date = event_date + timedelta(days=window_days)

                cursor.execute(
                    """SELECT event_type, event_description
                       FROM confounder_events
                       WHERE (ticker = %s OR ticker IS NULL)
                         AND event_date BETWEEN %s AND %s""",
                    (ticker, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                )
                rows = cursor.fetchall()

                return [
                    {
                        'type': row['event_type'],
                        'description': row['event_description'],
                        'source': 'database'
                    }
                    for row in rows
                ]

        finally:
            connection.close()

    def _detect_sector_move(self, ticker: str, event_date: datetime) -> Optional[Dict]:
        """
        Detect if the entire sector moved significantly on this date.
        
        Returns:
            Confounder dict if sector move detected, None otherwise
        """
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                # Get sector benchmark for this ticker
                cursor.execute(
                    """SELECT sector_etf FROM ticker_sector_mapping WHERE ticker = %s""",
                    (ticker,)
                )
                mapping = cursor.fetchone()

                if not mapping or not mapping['sector_etf']:
                    return None

                sector_etf = mapping['sector_etf']
                event_date_str = event_date.strftime('%Y-%m-%d')

                # Check if sector ETF moved > 3% on this date
                cursor.execute(
                    """SELECT return_1d FROM benchmark_returns
                       WHERE ticker = %s AND return_date = %s""",
                    (sector_etf, event_date_str)
                )
                result = cursor.fetchone()

                if result and result['return_1d'] is not None:
                    sector_return = abs(float(result['return_1d']))
                    if sector_return > 3.0:
                        return {
                            'type': 'sector_move',
                            'description': f'Sector {sector_etf} moved {sector_return:.1f}%',
                            'source': 'computed'
                        }

                return None

        finally:
            connection.close()

    def _detect_article_clustering(self, ticker: str, event_date: datetime) -> Optional[Dict]:
        """
        Detect if multiple articles about this ticker were published on the same date.
        
        Returns:
            Confounder dict if clustering detected, None otherwise
        """
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                event_date_str = event_date.strftime('%Y-%m-%d')

                cursor.execute(
                    """SELECT COUNT(*) as article_count
                       FROM rss_items
                       WHERE stock_tickers LIKE %s
                         AND DATE(published_at) = %s""",
                    (f'%{ticker}%', event_date_str)
                )
                result = cursor.fetchone()

                if result and result['article_count'] > 3:
                    return {
                        'type': 'article_clustering',
                        'description': f'{result["article_count"]} articles on same date',
                        'source': 'computed'
                    }

                return None

        finally:
            connection.close()

    # =========================================================================
    # Confounder impact scoring
    # =========================================================================

    def compute_confounder_confidence(self, confounders: List[Dict]) -> float:
        """
        Compute confidence score based on confounders present.
        
        More confounders = lower confidence in attribution.
        
        Args:
            confounders: List of detected confounders
            
        Returns:
            Confidence score (0-1), where 1 = high confidence, 0 = low confidence
        """
        if not confounders:
            return 1.0

        # Weight different confounder types
        weights = {
            'earnings': 0.3,
            'fda_pdufa': 0.2,
            'fed_meeting': 0.2,
            'cpi_release': 0.2,
            'sector_move': 0.15,
            'article_clustering': 0.1,
            'other': 0.1,
        }

        total_penalty = 0.0
        for conf in confounders:
            conf_type = conf.get('type', 'other')
            penalty = weights.get(conf_type, 0.1)
            total_penalty += penalty

        # Confidence = 1 - total_penalty (capped at 0)
        confidence = max(0.0, 1.0 - total_penalty)

        return round(confidence, 2)

    # =========================================================================
    # Batch operations
    # =========================================================================

    def add_confounder_event(self, event_date: datetime, event_type: str,
                             ticker: str = None, description: str = None):
        """
        Add a known confounder event to the database.
        
        Args:
            event_date: Date of the event
            event_type: Type (earnings, fda_pdufa, fed_meeting, etc.)
            ticker: Ticker symbol (None for market-wide events)
            description: Event description
        """
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO confounder_events
                       (event_date, ticker, event_type, event_description)
                       VALUES (%s, %s, %s, %s)""",
                    (event_date.strftime('%Y-%m-%d'), ticker, event_type, description)
                )
            connection.commit()
            logger.info(f"[CONFOUNDER] Added {event_type} event for {ticker or 'market'} "
                       f"on {event_date.strftime('%Y-%m-%d')}")
        finally:
            connection.close()

    def import_earnings_calendar(self, earnings_data: List[Dict]):
        """
        Bulk import earnings dates.
        
        Args:
            earnings_data: List of dicts with 'ticker', 'date', 'description'
        """
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                for item in earnings_data:
                    cursor.execute(
                        """INSERT IGNORE INTO confounder_events
                           (event_date, ticker, event_type, event_description)
                           VALUES (%s, %s, 'earnings', %s)""",
                        (item['date'], item['ticker'], item.get('description', 'Earnings call'))
                    )
            connection.commit()
            logger.info(f"[CONFOUNDER] Imported {len(earnings_data)} earnings events")
        finally:
            connection.close()
