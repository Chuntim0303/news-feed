"""
Fierce Biotech RSS Feed Service
"""

import logging
import re
from typing import Dict, Any, Optional
from .base_rss_service import BaseRSSService
from .stock_ticker_service import StockTickerService

logger = logging.getLogger(__name__)


class FiercebiotechService(BaseRSSService):
    """
    Service for fetching and parsing Fierce Biotech RSS feeds
    """

    FEED_URL = "https://www.fiercebiotech.com/rss/xml"

    def __init__(self, db_config: Dict[str, str]):
        """
        Initialize Fierce Biotech RSS service

        Args:
            db_config: Database configuration dictionary
        """
        super().__init__(db_config)
        self.feed_title = "Fierce Biotech"

    def get_feed_url(self) -> str:
        """
        Return the Fierce Biotech RSS feed URL

        Returns:
            str: RSS feed URL
        """
        return self.FEED_URL

    def extract_text_from_html_link(self, html_link: Optional[str]) -> Optional[str]:
        """
        Extract plain text from HTML anchor tag

        Fierce Biotech includes HTML in title and author fields like:
        <a href="/path">Text</a>

        Args:
            html_link: HTML string with anchor tag

        Returns:
            Extracted text or None
        """
        if not html_link:
            return None

        # Extract text from <a> tag
        match = re.search(r'>([^<]+)</a>', html_link)
        if match:
            return match.group(1)

        # If no match, clean HTML tags
        return self.clean_html(html_link)

    def parse_fiercebiotech_date(self, date_string: Optional[str]) -> Optional[Any]:
        """
        Parse Fierce Biotech date format

        Fierce Biotech uses format: "Feb 5, 2026 4:54am"

        Args:
            date_string: Date string to parse

        Returns:
            datetime object or None
        """
        if not date_string:
            return None

        try:
            from datetime import datetime
            # Try parsing "Feb 5, 2026 4:54am" format
            # Clean the string first
            cleaned = date_string.strip()

            # Handle AM/PM
            if 'am' in cleaned.lower() or 'pm' in cleaned.lower():
                # Convert to 12-hour format with AM/PM
                if 'am' in cleaned.lower():
                    cleaned = cleaned.replace('am', ' AM').replace('AM', ' AM')
                else:
                    cleaned = cleaned.replace('pm', ' PM').replace('PM', ' PM')

                # Try parsing with time
                try:
                    return datetime.strptime(cleaned, '%b %d, %Y %I:%M %p')
                except ValueError:
                    pass

            # Fall back to general parser
            return self.parse_datetime(date_string)
        except Exception as e:
            logger.warning(f"Could not parse Fierce Biotech date: {date_string} - {e}")
            return None

    def parse_item(self, item: Any) -> Dict[str, Any]:
        """
        Parse a Fierce Biotech RSS feed item

        Fierce Biotech RSS structure:
        - title: Contains HTML link tag <a href="...">Title</a>
        - link: Article URL
        - description: Article summary (plain text)
        - pubDate: Publication date in format "Feb 5, 2026 4:54am"
        - dc:creator: Author name(s) in HTML link tag
        - guid: Unique identifier (permalink)

        Args:
            item: RSS feed item from feedparser

        Returns:
            Dict containing parsed item data
        """
        # Extract basic fields
        guid = item.get('id') or item.get('link', '')
        link = item.get('link', '')

        # Extract title (contains HTML)
        title_html = item.get('title', '')
        title = self.extract_text_from_html_link(title_html)

        # Extract author from dc:creator (contains HTML)
        author_html = None
        if 'author' in item:
            author_html = item.get('author')
        elif 'dc_creator' in item:
            author_html = item.get('dc_creator')

        author = self.extract_text_from_html_link(author_html)

        # Handle multiple authors (comma-separated in HTML)
        if author and ',' in author:
            # Keep the full author list
            author = author.strip()

        # Extract summary/description
        summary = item.get('summary', '') or item.get('description', '')
        summary = self.clean_html(summary)

        # Extract content
        content = None
        if 'content' in item and item['content']:
            content = item['content'][0].get('value', '')

        # Fierce Biotech typically doesn't include images in RSS
        image_url = None

        # Parse publication date (custom format)
        published_at = None
        if 'published' in item:
            published_at = self.parse_fiercebiotech_date(item.get('published'))
        elif 'pubDate' in item:
            published_at = self.parse_fiercebiotech_date(item.get('pubDate'))

        # Detect stock tickers using pattern matching (Fierce Biotech doesn't have ticker tags)
        ticker_info = StockTickerService.detect_all(
            title=title,
            summary=summary,
            content=content,
            rss_item=None  # No RSS tags to extract from
        )

        return {
            'guid': guid,
            'link': link,
            'title': title,
            'author': author,
            'summary': summary,
            'content': content,
            'image_url': image_url,
            'published_at': published_at,
            'stock_tickers': ticker_info['tickers'],
            'company_names': ticker_info['companies']
        }
