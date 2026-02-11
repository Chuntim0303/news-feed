"""
Company Name and Ticker Extraction using spaCy NER

This module provides functionality to extract company names from text
(e.g., article titles and summaries) using spaCy's Named Entity Recognition,
and map them to stock ticker symbols.

Usage:
    extractor = CompanyExtractor()
    result = extractor.extract_companies_and_tickers("Apple and Microsoft announce partnership")
    # Returns: {
    #     'companies': ['Apple', 'Microsoft'],
    #     'tickers': ['AAPL', 'MSFT'],
    #     'matches': [
    #         {'company': 'Apple', 'ticker': 'AAPL', 'exchange': 'NASDAQ', ...},
    #         ...
    #     ]
    # }
"""

import re
import spacy
from typing import List, Dict, Optional, Set, Tuple
from .stock_ticker_data import COMPANY_TICKER_MAP, ALIAS_TO_COMPANY


class CompanyExtractor:
    """Extract company names and map them to stock tickers using NER."""

    def __init__(self, model_name: str = "en_core_web_sm"):
        """
        Initialize the company extractor with a spaCy model.

        Args:
            model_name: Name of the spaCy model to use (default: en_core_web_sm)
                       Install with: python -m spacy download en_core_web_sm
        """
        try:
            self.nlp = spacy.load(model_name)
        except OSError:
            raise RuntimeError(
                f"spaCy model '{model_name}' not found. "
                f"Install it with: python -m spacy download {model_name}"
            )

        # Build a case-insensitive lookup for faster matching
        self._build_lookup_index()

    def _build_lookup_index(self):
        """Build efficient lookup structures for company matching."""
        # Normalize all keys to lowercase for case-insensitive matching
        self.normalized_map = {
            key.lower(): (key, data)
            for key, data in COMPANY_TICKER_MAP.items()
        }

        # Build alias lookup (already normalized in stock_ticker_data.py)
        self.alias_map = {
            alias.lower(): company.lower()
            for alias, company in ALIAS_TO_COMPANY.items()
        }

    def extract_organizations(self, text: str) -> List[str]:
        """
        Extract organization names from text using spaCy NER.

        Args:
            text: Input text to extract organizations from

        Returns:
            List of organization names detected by NER
        """
        if not text:
            return []

        doc = self.nlp(text)

        # Extract all ORG entities
        organizations = []
        for ent in doc.ents:
            if ent.label_ == "ORG":
                # Clean up the entity text
                org_name = ent.text.strip()
                if org_name and len(org_name) > 1:  # Filter out single characters
                    organizations.append(org_name)

        return organizations

    def _normalize_company_name(self, name: str) -> str:
        """
        Normalize company name for matching.

        Args:
            name: Company name to normalize

        Returns:
            Normalized company name
        """
        # Convert to lowercase
        normalized = name.lower().strip()

        # Remove common suffixes that might prevent matching
        suffixes = [
            r'\s+inc\.?$', r'\s+incorporated$', r'\s+corp\.?$',
            r'\s+corporation$', r'\s+ltd\.?$', r'\s+limited$',
            r'\s+plc$', r'\s+llc$', r'\s+co\.?$', r'\s+company$',
            r'\s+ag$', r'\s+se$', r'\s+s\.a\.$', r'\s+n\.v\.$'
        ]

        for suffix in suffixes:
            normalized = re.sub(suffix, '', normalized, flags=re.IGNORECASE)

        # Remove possessives
        normalized = re.sub(r"'s$", '', normalized)

        # Clean up extra whitespace
        normalized = ' '.join(normalized.split())

        return normalized

    def find_ticker_info(self, company_name: str) -> Optional[Dict]:
        """
        Find ticker information for a given company name.

        Args:
            company_name: Company name to look up

        Returns:
            Dict with ticker info if found, None otherwise
        """
        normalized = self._normalize_company_name(company_name)

        # Try exact match first
        if normalized in self.normalized_map:
            original_key, data = self.normalized_map[normalized]
            return {
                'company': company_name,
                'matched_key': original_key,
                'ticker': data['ticker'],
                'exchange': data['exchange'],
                'full_name': data['full_name']
            }

        # Try alias match
        if normalized in self.alias_map:
            matched_company = self.alias_map[normalized]
            if matched_company in self.normalized_map:
                original_key, data = self.normalized_map[matched_company]
                return {
                    'company': company_name,
                    'matched_key': original_key,
                    'matched_via': 'alias',
                    'ticker': data['ticker'],
                    'exchange': data['exchange'],
                    'full_name': data['full_name']
                }

        # Try partial matching (fuzzy match)
        for key, (original_key, data) in self.normalized_map.items():
            # Check if the normalized company name contains or is contained by a known company
            if normalized in key or key in normalized:
                # Prefer longer matches (more specific)
                return {
                    'company': company_name,
                    'matched_key': original_key,
                    'matched_via': 'partial',
                    'ticker': data['ticker'],
                    'exchange': data['exchange'],
                    'full_name': data['full_name'],
                    'confidence': 'medium'
                }

        return None

    def extract_companies_and_tickers(self, text: str) -> Dict:
        """
        Extract companies and their tickers from text.

        Args:
            text: Input text to process

        Returns:
            Dict containing:
                - companies: List of all detected company names
                - tickers: List of tickers (de-duplicated)
                - matches: List of dicts with full match details
                - unmatched: List of companies without ticker matches
        """
        # Extract organizations using NER
        organizations = self.extract_organizations(text)

        # Remove duplicates while preserving order
        seen = set()
        unique_orgs = []
        for org in organizations:
            org_lower = org.lower()
            if org_lower not in seen:
                seen.add(org_lower)
                unique_orgs.append(org)

        # Match to tickers
        matches = []
        unmatched = []
        tickers_set = set()

        for org in unique_orgs:
            ticker_info = self.find_ticker_info(org)
            if ticker_info:
                matches.append(ticker_info)
                tickers_set.add(ticker_info['ticker'])
            else:
                unmatched.append(org)

        return {
            'companies': unique_orgs,
            'tickers': sorted(list(tickers_set)),  # Sort for consistency
            'matches': matches,
            'unmatched': unmatched
        }

    def format_for_database(self, extraction_result: Dict) -> Tuple[str, str]:
        """
        Format extraction results for database storage.

        Args:
            extraction_result: Result from extract_companies_and_tickers()

        Returns:
            Tuple of (stock_tickers, company_names) as comma-separated strings
        """
        stock_tickers = ','.join(extraction_result['tickers'])
        company_names = ','.join(extraction_result['companies'])

        return stock_tickers, company_names


def extract_from_article(title: str, summary: str = None) -> Dict:
    """
    Convenience function to extract companies and tickers from an article.

    Args:
        title: Article title
        summary: Optional article summary/description

    Returns:
        Extraction result dict from extract_companies_and_tickers()
    """
    extractor = CompanyExtractor()

    # Combine title and summary for better context
    text = title
    if summary:
        text = f"{title}. {summary}"

    return extractor.extract_companies_and_tickers(text)
