"""
Base RSS Service class for fetching and parsing RSS feeds
"""

import feedparser
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import pymysql
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseRSSService(ABC):
    """
    Abstract base class for RSS feed services
    """

    def __init__(self, db_config: Dict[str, str]):
        """
        Initialize the RSS service with database configuration

        Args:
            db_config: Database configuration dictionary with keys:
                      host, user, password, database, port
        """
        self.db_config = db_config
        self.feed_url = None
        self.feed_title = None

    @abstractmethod
    def get_feed_url(self) -> str:
        """
        Return the RSS feed URL

        Returns:
            str: RSS feed URL
        """
        pass

    @abstractmethod
    def parse_item(self, item: Any) -> Dict[str, Any]:
        """
        Parse a single RSS feed item into standardized format

        Args:
            item: RSS feed item from feedparser

        Returns:
            Dict containing parsed item data
        """
        pass

    def get_db_connection(self):
        """
        Create and return a database connection

        Returns:
            pymysql.Connection: Database connection object
        """
        return pymysql.connect(
            host=self.db_config['host'],
            user=self.db_config['user'],
            password=self.db_config['password'],
            database=self.db_config['database'],
            port=int(self.db_config.get('port', 3306)),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

    def get_or_create_feed(self, connection) -> int:
        """
        Get or create the RSS feed record in the database

        Args:
            connection: Database connection

        Returns:
            int: Feed ID
        """
        feed_url = self.get_feed_url()

        with connection.cursor() as cursor:
            # Check if feed exists
            cursor.execute(
                "SELECT id FROM rss_feeds WHERE url = %s",
                (feed_url,)
            )
            result = cursor.fetchone()

            if result:
                return result['id']

            # Create new feed
            cursor.execute(
                """
                INSERT INTO rss_feeds (url, title, is_active, next_fetch_at)
                VALUES (%s, %s, %s, %s)
                """,
                (feed_url, self.feed_title, True, datetime.now())
            )
            connection.commit()
            return cursor.lastrowid

    def update_feed_metadata(self, connection, feed_id: int, feed_data: Any):
        """
        Update feed metadata from parsed feed

        Args:
            connection: Database connection
            feed_id: Feed ID
            feed_data: Parsed feed data from feedparser
        """
        with connection.cursor() as cursor:
            feed_info = feed_data.get('feed', {})

            update_data = {
                'title': feed_info.get('title', self.feed_title),
                'site_url': feed_info.get('link'),
                'description': feed_info.get('description'),
                'language': feed_info.get('language'),
                'last_fetch_at': datetime.now(),
                'next_fetch_at': datetime.now() + timedelta(minutes=60)
            }

            # Handle etag and last_modified if present
            if hasattr(feed_data, 'etag'):
                update_data['etag'] = feed_data.etag
            if hasattr(feed_data, 'modified'):
                update_data['last_modified'] = feed_data.modified

            # Build update query
            update_fields = ', '.join([f"{k} = %s" for k in update_data.keys()])
            cursor.execute(
                f"UPDATE rss_feeds SET {update_fields} WHERE id = %s",
                (*update_data.values(), feed_id)
            )
            connection.commit()

    def save_item(self, connection, feed_id: int, item_data: Dict[str, Any]) -> bool:
        """
        Save a single RSS item to the database

        Args:
            connection: Database connection
            feed_id: Feed ID
            item_data: Parsed item data

        Returns:
            bool: True if item was inserted, False if already exists
        """
        with connection.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO rss_items (
                        feed_id, guid, link, title, author, summary,
                        content, image_url, published_at, fetched_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        feed_id,
                        item_data['guid'],
                        item_data.get('link'),
                        item_data.get('title'),
                        item_data.get('author'),
                        item_data.get('summary'),
                        item_data.get('content'),
                        item_data.get('image_url'),
                        item_data.get('published_at'),
                        datetime.now()
                    )
                )
                connection.commit()
                return True
            except pymysql.err.IntegrityError as e:
                # Item already exists (duplicate guid)
                logger.debug(f"Item already exists: {item_data['guid']}")
                return False

    def fetch_and_save(self) -> Dict[str, Any]:
        """
        Fetch RSS feed and save items to database

        Returns:
            Dict with status and statistics
        """
        feed_url = self.get_feed_url()
        logger.info(f"Fetching RSS feed: {feed_url}")

        # Parse RSS feed
        feed = feedparser.parse(feed_url)

        if feed.bozo:
            logger.warning(f"Feed parsing warning: {feed.bozo_exception}")

        connection = None
        new_items = 0
        existing_items = 0

        try:
            connection = self.get_db_connection()

            # Get or create feed record
            feed_id = self.get_or_create_feed(connection)

            # Update feed metadata
            self.update_feed_metadata(connection, feed_id, feed)

            # Process each item
            for entry in feed.entries:
                try:
                    item_data = self.parse_item(entry)
                    if self.save_item(connection, feed_id, item_data):
                        new_items += 1
                    else:
                        existing_items += 1
                except Exception as e:
                    logger.error(f"Error processing item: {e}", exc_info=True)
                    continue

            return {
                'status': 'success',
                'feed_id': feed_id,
                'feed_url': feed_url,
                'total_items': len(feed.entries),
                'new_items': new_items,
                'existing_items': existing_items
            }

        except Exception as e:
            logger.error(f"Error fetching RSS feed: {e}", exc_info=True)
            return {
                'status': 'error',
                'feed_url': feed_url,
                'error': str(e)
            }
        finally:
            if connection:
                connection.close()

    @staticmethod
    def parse_datetime(date_string: Optional[str]) -> Optional[datetime]:
        """
        Parse various datetime formats to datetime object

        Args:
            date_string: Date string to parse

        Returns:
            datetime object or None
        """
        if not date_string:
            return None

        try:
            # Try parsing common formats
            from dateutil import parser
            return parser.parse(date_string)
        except Exception as e:
            logger.warning(f"Could not parse date: {date_string} - {e}")
            return None

    @staticmethod
    def clean_html(html_content: Optional[str]) -> Optional[str]:
        """
        Remove HTML tags from content

        Args:
            html_content: HTML string

        Returns:
            Cleaned text or None
        """
        if not html_content:
            return None

        try:
            from html.parser import HTMLParser

            class MLStripper(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.reset()
                    self.strict = False
                    self.convert_charrefs = True
                    self.text = []

                def handle_data(self, d):
                    self.text.append(d)

                def get_data(self):
                    return ''.join(self.text)

            s = MLStripper()
            s.feed(html_content)
            return s.get_data()
        except Exception as e:
            logger.warning(f"Could not clean HTML: {e}")
            return html_content
