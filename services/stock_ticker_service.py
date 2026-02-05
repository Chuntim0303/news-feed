"""
Stock Ticker Detection Service

This service provides automatic detection of stock ticker symbols from news articles.
It uses two strategies:
1. Direct extraction from Bloomberg RSS category tags
2. Pattern matching for company names in article text
"""

import re
import logging
from typing import Dict, List, Set, Optional, Any
from .stock_ticker_data import COMPANY_TICKER_MAP, ALIAS_TO_COMPANY

logger = logging.getLogger(__name__)


class StockTickerService:
    """
    Service for detecting stock ticker symbols in news articles
    """

    @staticmethod
    def extract_bloomberg_tickers(item: Any) -> List[Dict[str, str]]:
        """
        Extract stock tickers directly from Bloomberg RSS category tags

        Bloomberg includes ticker symbols in category tags like:
        <category domain="stock-symbol">NYS:KKR</category>
        <category domain="stock-symbol">NMS:PLTR</category>

        Args:
            item: Parsed RSS item from feedparser

        Returns:
            List of dicts with ticker info: [{'ticker': 'PLTR', 'exchange': 'NASDAQ', 'source': 'bloomberg'}]
        """
        tickers = []

        if not hasattr(item, 'tags'):
            return tickers

        for tag in item.get('tags', []):
            # Check if this is a stock-symbol category
            if tag.get('scheme') == 'stock-symbol' or tag.get('label') == 'stock-symbol':
                ticker_str = tag.get('term', '')

                # Parse format like "NYS:KKR" or "NMS:PLTR"
                if ':' in ticker_str:
                    exchange_code, ticker = ticker_str.split(':', 1)

                    # Map Bloomberg exchange codes to readable names
                    exchange_map = {
                        'NYS': 'NYSE',
                        'NMS': 'NASDAQ',
                        'TOR': 'Toronto Stock Exchange',
                        'TYO': 'Tokyo Stock Exchange',
                        'LON': 'London Stock Exchange'
                    }

                    exchange = exchange_map.get(exchange_code, exchange_code)

                    # Filter for NYSE and NASDAQ as requested
                    if exchange in ['NYSE', 'NASDAQ']:
                        tickers.append({
                            'ticker': ticker,
                            'exchange': exchange,
                            'source': 'bloomberg_tag'
                        })
                else:
                    # No exchange prefix, assume it's just the ticker
                    tickers.append({
                        'ticker': ticker_str,
                        'exchange': 'Unknown',
                        'source': 'bloomberg_tag'
                    })

        return tickers

    @staticmethod
    def detect_companies_in_text(text: str) -> List[Dict[str, str]]:
        """
        Detect company names in text using pattern matching

        Args:
            text: Text to search for company names

        Returns:
            List of dicts with company and ticker info
        """
        if not text:
            return []

        found_companies = []
        text_lower = text.lower()

        # Check for each company name and aliases
        checked_companies = set()

        for alias, company_key in ALIAS_TO_COMPANY.items():
            # Skip if we already found this company
            if company_key in checked_companies:
                continue

            # Create word boundary regex pattern for the alias
            # This prevents matching "Novo" in "Innovation" for example
            pattern = r'\b' + re.escape(alias) + r'\b'

            if re.search(pattern, text_lower):
                company_data = COMPANY_TICKER_MAP[company_key]

                # Filter for NYSE and NASDAQ
                if company_data['exchange'] in ['NYSE', 'NASDAQ']:
                    found_companies.append({
                        'company': company_data['full_name'],
                        'ticker': company_data['ticker'],
                        'exchange': company_data['exchange'],
                        'source': 'pattern_match',
                        'matched_text': alias
                    })
                    checked_companies.add(company_key)

        return found_companies

    @staticmethod
    def detect_all(title: Optional[str],
                   summary: Optional[str],
                   content: Optional[str],
                   rss_item: Any = None) -> Dict[str, Any]:
        """
        Detect all stock tickers using all available methods

        Args:
            title: Article title
            summary: Article summary
            content: Article content
            rss_item: Original RSS item (for Bloomberg tag extraction)

        Returns:
            Dict with:
            - tickers: Comma-separated ticker symbols
            - companies: Comma-separated company names
            - details: List of detailed ticker info
        """
        all_detections = []

        # Method 1: Extract from Bloomberg RSS tags (if available)
        if rss_item:
            bloomberg_tickers = StockTickerService.extract_bloomberg_tickers(rss_item)
            all_detections.extend(bloomberg_tickers)

        # Method 2: Pattern matching in title
        if title:
            title_companies = StockTickerService.detect_companies_in_text(title)
            all_detections.extend(title_companies)

        # Method 3: Pattern matching in summary
        if summary:
            summary_companies = StockTickerService.detect_companies_in_text(summary)
            all_detections.extend(summary_companies)

        # Method 4: Pattern matching in content (optional, might be slow)
        # Uncomment if needed:
        # if content:
        #     content_companies = StockTickerService.detect_companies_in_text(content)
        #     all_detections.extend(content_companies)

        # Deduplicate by ticker symbol
        unique_tickers = {}
        for detection in all_detections:
            ticker = detection.get('ticker')
            if ticker and ticker not in unique_tickers:
                unique_tickers[ticker] = detection

        # Build response
        tickers_list = list(unique_tickers.keys())
        companies_list = [d.get('company', '') for d in unique_tickers.values() if d.get('company')]

        return {
            'tickers': ','.join(tickers_list) if tickers_list else None,
            'companies': ','.join(companies_list) if companies_list else None,
            'details': list(unique_tickers.values())
        }

    @staticmethod
    def parse_tickers_from_db(ticker_string: Optional[str]) -> List[str]:
        """
        Parse comma-separated ticker string from database

        Args:
            ticker_string: Comma-separated ticker symbols (e.g., "PLTR,KKR")

        Returns:
            List of ticker symbols
        """
        if not ticker_string:
            return []
        return [t.strip() for t in ticker_string.split(',') if t.strip()]
