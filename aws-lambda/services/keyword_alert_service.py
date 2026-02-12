"""
Keyword Alert Service

Checks new RSS articles against user-defined keywords stored in the database.
Scores each match using the composite news scoring model (keyword event score,
market cap multiplier, surprise phrases) and only sends Telegram alerts when
the score exceeds the user's threshold.

All matches are logged to alert_log with full score breakdowns regardless of
whether an alert is sent.

Usage:
    service = KeywordAlertService(db_config=db_config)
    alerts = service.check_and_alert(
        article_id=123, title="...", summary="...",
        market_caps=[800_000_000]
    )
"""

import os
import re
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.request import urlopen, Request
from urllib.error import HTTPError

import pymysql

from .news_scoring_service import NewsScoringService

logger = logging.getLogger(__name__)

# Default alert threshold when no user setting exists
DEFAULT_ALERT_THRESHOLD = 5


class KeywordAlertService:
    """Check articles against keywords, score them, and send Telegram alerts."""

    TELEGRAM_API_URL = "https://api.telegram.org/bot{token}"

    def __init__(self, db_config: Dict = None, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or os.environ.get('TELEGRAM_BOT_TOKEN', '')
        self.chat_id = chat_id or os.environ.get('TELEGRAM_CHAT_ID', '')
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
        self._keywords = None
        self._scorer = NewsScoringService()

    def _get_connection(self):
        return pymysql.connect(
            **self.db_config,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

    # ------------------------------------------------------------------
    # Keyword management (used by Telegram bot commands)
    # ------------------------------------------------------------------

    def get_active_keywords(self) -> List[Dict]:
        """Load all active keywords (including event_score) from the database."""
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, keyword, event_score FROM alert_keywords WHERE is_active = 1"
                )
                return cursor.fetchall()
        finally:
            connection.close()

    def add_keyword(self, keyword: str, created_by: str = None,
                    event_score: int = 5) -> Dict:
        """Add a new keyword with an event score. Returns status dict."""
        keyword = keyword.strip().lower()
        if not keyword:
            return {'status': 'error', 'message': 'Keyword cannot be empty'}

        event_score = max(1, min(10, event_score))

        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                try:
                    cursor.execute(
                        """INSERT INTO alert_keywords (keyword, created_by, event_score)
                           VALUES (%s, %s, %s)""",
                        (keyword, created_by, event_score)
                    )
                    connection.commit()
                    return {'status': 'success',
                            'message': f'Keyword "{keyword}" added (score={event_score})'}
                except pymysql.err.IntegrityError:
                    # Already exists — reactivate if inactive
                    cursor.execute(
                        """UPDATE alert_keywords SET is_active = 1, event_score = %s
                           WHERE keyword = %s AND is_active = 0""",
                        (event_score, keyword)
                    )
                    connection.commit()
                    if cursor.rowcount > 0:
                        return {'status': 'success',
                                'message': f'Keyword "{keyword}" reactivated (score={event_score})'}
                    return {'status': 'exists', 'message': f'Keyword "{keyword}" already exists'}
        finally:
            connection.close()

    def update_keyword_score(self, keyword: str, event_score: int) -> Dict:
        """Update the event_score for an existing keyword."""
        keyword = keyword.strip().lower()
        event_score = max(1, min(10, event_score))

        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE alert_keywords SET event_score = %s
                       WHERE keyword = %s AND is_active = 1""",
                    (event_score, keyword)
                )
                connection.commit()
                if cursor.rowcount > 0:
                    return {'status': 'success',
                            'message': f'Keyword "{keyword}" score updated to {event_score}'}
                return {'status': 'not_found', 'message': f'Keyword "{keyword}" not found'}
        finally:
            connection.close()

    def remove_keyword(self, keyword: str) -> Dict:
        """Deactivate a keyword. Returns status dict."""
        keyword = keyword.strip().lower()
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE alert_keywords SET is_active = 0
                       WHERE keyword = %s AND is_active = 1""",
                    (keyword,)
                )
                connection.commit()
                if cursor.rowcount > 0:
                    return {'status': 'success', 'message': f'Keyword "{keyword}" removed'}
                return {'status': 'not_found', 'message': f'Keyword "{keyword}" not found'}
        finally:
            connection.close()

    # ------------------------------------------------------------------
    # User threshold
    # ------------------------------------------------------------------

    def _get_alert_threshold(self) -> float:
        """Get the alert threshold for the current chat from bot_settings."""
        if not self.chat_id:
            return DEFAULT_ALERT_THRESHOLD

        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT alert_threshold, alert_mode FROM bot_settings WHERE chat_id = %s",
                    (str(self.chat_id),)
                )
                row = cursor.fetchone()
                if row:
                    mode = row.get('alert_mode', 'normal')
                    threshold = row.get('alert_threshold', DEFAULT_ALERT_THRESHOLD)
                    # In quiet mode, use a higher minimum threshold
                    if mode == 'quiet':
                        return max(threshold, 10)
                    return threshold
                return DEFAULT_ALERT_THRESHOLD
        except Exception as e:
            logger.warning(f"Could not fetch alert threshold: {e}")
            return DEFAULT_ALERT_THRESHOLD
        finally:
            connection.close()

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def _load_keywords(self):
        """Load and cache keywords for the current invocation."""
        if self._keywords is None:
            self._keywords = self.get_active_keywords()
        return self._keywords

    def match_keywords(self, text: str) -> List[Dict]:
        """
        Check text against all active keywords using word-boundary matching.

        Args:
            text: Text to check (title + summary)

        Returns:
            List of matched keyword dicts [{'id': ..., 'keyword': ..., 'event_score': ...}, ...]
        """
        if not text:
            return []

        keywords = self._load_keywords()
        if not keywords:
            return []

        text_lower = text.lower()
        matched = []
        for kw in keywords:
            pattern = r'\b' + re.escape(kw['keyword']) + r'\b'
            if re.search(pattern, text_lower):
                matched.append(kw)

        return matched

    # ------------------------------------------------------------------
    # Telegram alerts
    # ------------------------------------------------------------------

    def _send_telegram_message(self, text: str) -> Optional[Dict]:
        """Send a message via Telegram Bot API."""
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram credentials not configured, skipping alert")
            return None

        url = f"{self.TELEGRAM_API_URL.format(token=self.bot_token)}/sendMessage"
        payload = json.dumps({
            'chat_id': self.chat_id,
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
            logger.error(f"Failed to send Telegram alert: {e}")
            return None

    def _format_alert_message(self, title: str, link: str, source: str,
                               matched_keywords: List[Dict],
                               score_result: Dict) -> str:
        """Format a Telegram alert message with score breakdown."""
        kw_list = ', '.join(
            f'<b>{kw["keyword"]}</b> ({kw.get("event_score", 5)})'
            for kw in matched_keywords
        )

        score_total = score_result.get('score_total', 0)
        cap_mult = score_result.get('score_cap_mult', 1.0)
        surprise = score_result.get('score_surprise', 0)
        surprise_dir = score_result.get('surprise_dir', 'none')

        msg = (
            f"🔔 <b>Keyword Alert</b> — Score: <b>{score_total:.1f}</b>\n\n"
            f"<b>{title}</b>\n"
            f"Source: {source}\n"
            f"Keywords: {kw_list}\n"
        )

        # Score breakdown line
        breakdown_parts = [f"KW={score_result.get('score_keyword', 0)}"]
        if cap_mult != 1.0:
            breakdown_parts.append(f"×{cap_mult}")
        if surprise > 0:
            dir_icon = "📈" if surprise_dir == 'positive' else "📉" if surprise_dir == 'negative' else "⚡"
            breakdown_parts.append(f"Surprise={surprise} {dir_icon}")
        msg += f"Score: {' | '.join(breakdown_parts)}\n"

        # Show surprise phrases if any
        surprise_phrases = score_result.get('surprise_phrases', [])
        if surprise_phrases:
            phrases_str = ', '.join(f'"{p[0]}"' for p in surprise_phrases)
            msg += f"Detected: {phrases_str}\n"

        if link:
            msg += f"\n<a href=\"{link}\">Read article</a>"
        return msg

    # ------------------------------------------------------------------
    # Main entry point — check and alert
    # ------------------------------------------------------------------

    def check_and_alert(self, article_id: int, title: str, summary: str = None,
                        link: str = None, source: str = None,
                        market_caps: List[Optional[int]] = None) -> List[Dict]:
        """
        Check an article against keywords. Score the match using the composite
        scoring model. Send Telegram alert only if score >= threshold.
        Always log the match with full score breakdown.

        Args:
            article_id: rss_items.id
            title: Article title
            summary: Article summary (optional)
            link: Article URL (optional)
            source: Feed name (optional)
            market_caps: List of market caps for matched companies (optional)

        Returns:
            List of matched keywords that were logged (regardless of alert)
        """
        text = title or ''
        if summary:
            text = f"{text}. {summary}"

        matched = self.match_keywords(text)
        if not matched:
            return []

        logger.info(f"[ALERT] Article {article_id} matched {len(matched)} keywords: "
                    f"{[kw['keyword'] for kw in matched]}")

        # Score the article
        score_result = self._scorer.score_article(
            text=text,
            matched_keywords=matched,
            market_caps=market_caps or []
        )

        # Get user threshold
        threshold = self._get_alert_threshold()
        should_alert = score_result['score_total'] >= threshold

        logger.info(f"[ALERT] Article {article_id} score={score_result['score_total']:.2f} "
                    f"threshold={threshold} alert={'YES' if should_alert else 'NO'}")

        # Filter out already-logged keywords
        connection = self._get_connection()
        new_matches = []
        try:
            with connection.cursor() as cursor:
                for kw in matched:
                    cursor.execute(
                        """SELECT id FROM alert_log
                           WHERE rss_item_id = %s AND keyword_id = %s""",
                        (article_id, kw['id'])
                    )
                    if cursor.fetchone() is None:
                        new_matches.append(kw)

            if not new_matches:
                logger.info(f"[ALERT] All matches for article {article_id} already logged, skipping")
                return []

            # Send Telegram alert only if score meets threshold
            if should_alert:
                msg = self._format_alert_message(
                    title=title or '(no title)',
                    link=link or '',
                    source=source or 'Unknown',
                    matched_keywords=new_matches,
                    score_result=score_result
                )
                self._send_telegram_message(msg)

            # Log all matches with score breakdown (even if no alert sent)
            with connection.cursor() as cursor:
                for kw in new_matches:
                    try:
                        cursor.execute(
                            """INSERT INTO alert_log
                               (rss_item_id, keyword_id, keyword,
                                score_total, score_keyword, score_cap_mult,
                                score_surprise, surprise_dir, alert_sent)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                            (article_id, kw['id'], kw['keyword'],
                             score_result['score_total'],
                             score_result['score_keyword'],
                             score_result['score_cap_mult'],
                             score_result['score_surprise'],
                             score_result['surprise_dir'],
                             1 if should_alert else 0)
                        )
                    except pymysql.err.IntegrityError:
                        pass
            connection.commit()

        finally:
            connection.close()

        return new_matches
