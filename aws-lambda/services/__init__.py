"""
Services package for RSS Feed Ingestion & Ticker Extraction Lambda

Stock price fetching, news impact analysis, and Telegram reports
have been moved to the separate daily Lambda (aws-lambda-daily).
"""

try:
    from .base_rss_service import BaseRSSService
    from .bloomberg_service import BloombergService
    from .fiercebiotech_service import FiercebiotechService
    from .company_extractor import CompanyExtractor
    from .keyword_alert_service import KeywordAlertService
    from .news_scoring_service import NewsScoringService
except ImportError as e:
    raise ImportError(
        f"Failed to import services: {e}. "
        "Ensure all dependencies from requirements.txt are installed. "
        "For Lambda deployment, run: pip install -r requirements.txt -t lambda_package/"
    ) from e

__all__ = [
    'BaseRSSService', 'BloombergService', 'FiercebiotechService',
    'CompanyExtractor', 'KeywordAlertService', 'NewsScoringService'
]
