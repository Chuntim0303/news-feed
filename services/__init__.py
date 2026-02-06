"""
Services package for RSS feed tracking system
"""

try:
    from .base_rss_service import BaseRSSService
    from .bloomberg_service import BloombergService
    from .fiercebiotech_service import FiercebiotechService
except ImportError as e:
    raise ImportError(
        f"Failed to import services: {e}. "
        "Ensure all dependencies from requirements.txt are installed. "
        "For Lambda deployment, run: pip install -r requirements.txt -t lambda_package/"
    ) from e

__all__ = ['BaseRSSService', 'BloombergService', 'FiercebiotechService']
