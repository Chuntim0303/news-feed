"""
Bloomberg RSS Feed Service
"""

import logging
from typing import Dict, Any, Optional
from .base_rss_service import BaseRSSService
from .stock_ticker_service import StockTickerService

logger = logging.getLogger(__name__)


class BloombergService(BaseRSSService):
    """
    Service for fetching and parsing Bloomberg RSS feeds
    """

    FEED_URL = "https://bloomberg.com/markets/rss"

    def __init__(self, db_config: Dict[str, str]):
        """
        Initialize Bloomberg RSS service

        Args:
            db_config: Database configuration dictionary
        """
        super().__init__(db_config)
        self.feed_title = "Bloomberg Markets"

    def get_feed_url(self) -> str:
        """
        Return the Bloomberg RSS feed URL

        Returns:
            str: RSS feed URL
        """
        return self.FEED_URL

    def parse_item(self, item: Any) -> Dict[str, Any]:
        """
        Parse a Bloomberg RSS feed item

        Bloomberg RSS structure:
        - title: Article title (CDATA)
        - description: Article summary (CDATA)
        - link: Article URL
        - guid: Unique identifier (permalink)
        - dc:creator: Author name(s) (CDATA)
        - pubDate: Publication date (RFC 822)
        - media:content: Image URL and metadata
        - category: Stock symbols and categories

        Args:
            item: RSS feed item from feedparser

        Returns:
            Dict containing parsed item data
        """
        # Extract basic fields
        guid = item.get('id') or item.get('link', '')
        link = item.get('link', '')
        title = item.get('title', '')

        # Extract author from dc:creator
        author = None
        if 'author' in item:
            author = item.get('author')
        elif 'dc_creator' in item:
            author = item.get('dc_creator')

        # Extract summary/description
        summary = item.get('summary', '') or item.get('description', '')

        # Extract content (might be in content field)
        content = None
        if 'content' in item and item['content']:
            content = item['content'][0].get('value', '')

        # Extract image URL from media:content
        image_url = None
        if 'media_content' in item and item['media_content']:
            image_url = item['media_content'][0].get('url')
        elif 'media_thumbnail' in item and item['media_thumbnail']:
            image_url = item['media_thumbnail'][0].get('url')

        # Parse publication date
        published_at = None
        if 'published' in item:
            published_at = self.parse_datetime(item.get('published'))
        elif 'pubDate' in item:
            published_at = self.parse_datetime(item.get('pubDate'))

        # Detect stock tickers (Bloomberg includes them in category tags)
        ticker_info = StockTickerService.detect_all(
            title=title,
            summary=summary,
            content=content,
            rss_item=item  # Pass raw item for Bloomberg tag extraction
        )

        return {
            'guid': guid,
            'link': link,
            'title': self.clean_html(title),
            'author': author,
            'summary': self.clean_html(summary),
            'content': content,
            'image_url': image_url,
            'published_at': published_at,
            'stock_tickers': ticker_info['tickers'],
            'company_names': ticker_info['companies'],
            'raw_item': item  # Keep raw item for debugging if needed
        }
