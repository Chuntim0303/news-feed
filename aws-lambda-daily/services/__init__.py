"""
Services package for Daily Stock Price & Analysis Lambda
"""

from .stock_price_service import StockPriceService

# TelegramReportService requires fpdf2 which may not be in the Lambda layer.
try:
    from .telegram_report_service import TelegramReportService
except ImportError:
    TelegramReportService = None

__all__ = [
    'StockPriceService',
    'TelegramReportService'
]
