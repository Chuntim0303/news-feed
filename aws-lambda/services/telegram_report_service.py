"""
Telegram Report Service

Generates PDF reports of news impact analysis and sends them via Telegram Bot API.

Requirements:
    - fpdf2 (pip install fpdf2) — lightweight PDF generation, no system deps
    - TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables

Usage:
    service = TelegramReportService(db_config=db_config)
    service.generate_and_send_report()
"""

import os
import io
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from urllib.request import urlopen, Request
from urllib.error import HTTPError

import pymysql
from fpdf import FPDF

logger = logging.getLogger(__name__)


class TelegramReportService:
    """Generate PDF news impact reports and send via Telegram."""

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

    def _get_connection(self):
        return pymysql.connect(
            **self.db_config,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

    # ------------------------------------------------------------------
    # Data queries
    # ------------------------------------------------------------------

    def _get_price_impact_data(self, limit: int = 20) -> List[Dict]:
        """Get articles sorted by absolute price change."""
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT
                        ri.title, ri.published_at, ri.stock_tickers,
                        ass.ticker, ass.price_at_publication,
                        ass.price_current AS price_next_day,
                        ass.price_change_since_article AS change_pct
                    FROM article_stock_snapshots ass
                    JOIN rss_items ri ON ass.article_id = ri.id
                    WHERE ass.price_at_publication IS NOT NULL
                      AND ass.price_change_since_article IS NOT NULL
                    ORDER BY ABS(ass.price_change_since_article) DESC
                    LIMIT %s""",
                    (limit,)
                )
                return cursor.fetchall()
        finally:
            connection.close()

    def _get_volume_data(self, limit: int = 15) -> List[Dict]:
        """Get articles with unusual volume activity."""
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT
                        ri.title, ri.published_at,
                        ass.ticker,
                        sp_news.volume AS news_volume,
                        sp_news.close_price,
                        sp_news.change_percent,
                        (SELECT AVG(sp2.volume) FROM stock_prices sp2
                         WHERE sp2.ticker = ass.ticker) AS avg_volume
                    FROM article_stock_snapshots ass
                    JOIN rss_items ri ON ass.article_id = ri.id
                    LEFT JOIN stock_prices sp_news ON sp_news.ticker = ass.ticker
                        AND sp_news.price_date = (
                            SELECT MIN(sp3.price_date) FROM stock_prices sp3
                            WHERE sp3.ticker = ass.ticker
                              AND sp3.price_date >= DATE(ri.published_at)
                        )
                    WHERE sp_news.volume IS NOT NULL
                      AND sp_news.volume > 0
                    ORDER BY (sp_news.volume / NULLIF(
                        (SELECT AVG(sp4.volume) FROM stock_prices sp4
                         WHERE sp4.ticker = ass.ticker), 0)) DESC
                    LIMIT %s""",
                    (limit,)
                )
                return cursor.fetchall()
        finally:
            connection.close()

    def _get_summary_stats(self) -> Dict:
        """Get summary statistics for the report."""
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT
                        COUNT(*) AS total_snapshots,
                        SUM(CASE WHEN price_change_since_article > 0 THEN 1 ELSE 0 END) AS positive,
                        SUM(CASE WHEN price_change_since_article < 0 THEN 1 ELSE 0 END) AS negative,
                        SUM(CASE WHEN price_change_since_article = 0 THEN 1 ELSE 0 END) AS neutral,
                        AVG(price_change_since_article) AS avg_change,
                        MAX(price_change_since_article) AS max_gain,
                        MIN(price_change_since_article) AS max_loss
                    FROM article_stock_snapshots
                    WHERE price_change_since_article IS NOT NULL"""
                )
                return cursor.fetchone()
        finally:
            connection.close()

    # ------------------------------------------------------------------
    # PDF generation
    # ------------------------------------------------------------------

    def generate_pdf(self) -> bytes:
        """Generate a PDF report with news impact analysis."""
        now = datetime.now()
        impact_data = self._get_price_impact_data(limit=20)
        volume_data = self._get_volume_data(limit=15)
        stats = self._get_summary_stats()

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)

        # --- Title page ---
        pdf.add_page()
        pdf.set_font('Helvetica', 'B', 22)
        pdf.cell(0, 15, 'News Impact Report', new_x='LMARGIN', new_y='NEXT', align='C')
        pdf.set_font('Helvetica', '', 11)
        pdf.cell(0, 8, f'Generated: {now.strftime("%Y-%m-%d %H:%M UTC+8")}',
                 new_x='LMARGIN', new_y='NEXT', align='C')
        pdf.ln(5)

        # --- Summary ---
        pdf.set_font('Helvetica', 'B', 14)
        pdf.cell(0, 10, 'Summary', new_x='LMARGIN', new_y='NEXT')
        pdf.set_font('Helvetica', '', 10)

        if stats and stats.get('total_snapshots'):
            total = int(stats['total_snapshots'])
            pos = int(stats['positive'] or 0)
            neg = int(stats['negative'] or 0)
            avg = float(stats['avg_change'] or 0)
            gain = float(stats['max_gain'] or 0)
            loss = float(stats['max_loss'] or 0)

            pdf.cell(0, 6, f'Total article-ticker pairs analyzed: {total}',
                     new_x='LMARGIN', new_y='NEXT')
            pdf.cell(0, 6, f'Positive moves: {pos} ({pos*100//total}%)  |  '
                           f'Negative moves: {neg} ({neg*100//total}%)',
                     new_x='LMARGIN', new_y='NEXT')
            pdf.cell(0, 6, f'Average change: {avg:+.2f}%  |  '
                           f'Max gain: {gain:+.2f}%  |  Max loss: {loss:+.2f}%',
                     new_x='LMARGIN', new_y='NEXT')
        else:
            pdf.cell(0, 6, 'No snapshot data available.',
                     new_x='LMARGIN', new_y='NEXT')

        pdf.ln(5)

        # --- Price Impact Table ---
        pdf.set_font('Helvetica', 'B', 14)
        pdf.cell(0, 10, 'Top Price Movers', new_x='LMARGIN', new_y='NEXT')

        if impact_data:
            # Table header
            col_w = [18, 20, 28, 28, 96]
            pdf.set_font('Helvetica', 'B', 8)
            pdf.cell(col_w[0], 7, 'Ticker', border=1)
            pdf.cell(col_w[1], 7, 'Change %', border=1, align='R')
            pdf.cell(col_w[2], 7, 'Pub Price', border=1, align='R')
            pdf.cell(col_w[3], 7, 'Next Day', border=1, align='R')
            pdf.cell(col_w[4], 7, 'Article Title', border=1)
            pdf.ln()

            pdf.set_font('Helvetica', '', 7)
            for row in impact_data:
                change = float(row['change_pct'] or 0)
                pub_price = float(row['price_at_publication'] or 0)
                next_price = float(row['price_next_day'] or 0)
                title = (row['title'] or '')[:60]
                # Sanitize for PDF (remove non-latin1 chars)
                title = title.encode('latin-1', 'replace').decode('latin-1')
                ticker = str(row['ticker'] or '')

                arrow = '+' if change >= 0 else ''

                pdf.cell(col_w[0], 6, ticker, border=1)
                pdf.cell(col_w[1], 6, f'{arrow}{change:.2f}%', border=1, align='R')
                pdf.cell(col_w[2], 6, f'${pub_price:.2f}', border=1, align='R')
                pdf.cell(col_w[3], 6, f'${next_price:.2f}', border=1, align='R')
                pdf.cell(col_w[4], 6, title, border=1)
                pdf.ln()
        else:
            pdf.set_font('Helvetica', '', 10)
            pdf.cell(0, 6, 'No price impact data available.',
                     new_x='LMARGIN', new_y='NEXT')

        pdf.ln(5)

        # --- Volume Analysis Table ---
        pdf.set_font('Helvetica', 'B', 14)
        pdf.cell(0, 10, 'Volume Analysis (News Day vs Average)',
                 new_x='LMARGIN', new_y='NEXT')

        if volume_data:
            col_w = [18, 28, 28, 20, 20, 76]
            pdf.set_font('Helvetica', 'B', 8)
            pdf.cell(col_w[0], 7, 'Ticker', border=1)
            pdf.cell(col_w[1], 7, 'News Vol', border=1, align='R')
            pdf.cell(col_w[2], 7, 'Avg Vol', border=1, align='R')
            pdf.cell(col_w[3], 7, 'Ratio', border=1, align='R')
            pdf.cell(col_w[4], 7, 'Price %', border=1, align='R')
            pdf.cell(col_w[5], 7, 'Article Title', border=1)
            pdf.ln()

            pdf.set_font('Helvetica', '', 7)
            for row in volume_data:
                news_vol = int(row['news_volume'] or 0)
                avg_vol = int(row['avg_volume'] or 1)
                ratio = news_vol / avg_vol if avg_vol > 0 else 0
                change = float(row['change_percent'] or 0)
                title = (row['title'] or '')[:48]
                title = title.encode('latin-1', 'replace').decode('latin-1')
                ticker = str(row['ticker'] or '')

                signal = ' !!!' if ratio > 2.0 else ' !' if ratio > 1.5 else ''

                pdf.cell(col_w[0], 6, ticker, border=1)
                pdf.cell(col_w[1], 6, f'{news_vol:,}', border=1, align='R')
                pdf.cell(col_w[2], 6, f'{avg_vol:,}', border=1, align='R')
                pdf.cell(col_w[3], 6, f'{ratio:.1f}x{signal}', border=1, align='R')
                pdf.cell(col_w[4], 6, f'{change:+.2f}%', border=1, align='R')
                pdf.cell(col_w[5], 6, title, border=1)
                pdf.ln()

            pdf.ln(3)
            pdf.set_font('Helvetica', 'I', 7)
            pdf.cell(0, 5, '!!! = Volume > 2x average (strong signal)    '
                           '! = Volume > 1.5x average (moderate signal)',
                     new_x='LMARGIN', new_y='NEXT')
        else:
            pdf.set_font('Helvetica', '', 10)
            pdf.cell(0, 6, 'No volume data available.',
                     new_x='LMARGIN', new_y='NEXT')

        # --- Footer ---
        pdf.ln(10)
        pdf.set_font('Helvetica', 'I', 8)
        pdf.cell(0, 5, 'RSS Feed Tracker - News Impact Analysis',
                 new_x='LMARGIN', new_y='NEXT', align='C')

        return pdf.output()

    # ------------------------------------------------------------------
    # Telegram sending
    # ------------------------------------------------------------------

    def send_telegram_document(self, pdf_bytes: bytes, filename: str = None,
                                caption: str = None) -> Dict:
        """
        Send a PDF document to Telegram via Bot API.

        Args:
            pdf_bytes: PDF file content as bytes
            filename: Filename for the document
            caption: Optional caption text

        Returns:
            Telegram API response dict
        """
        if not self.bot_token or not self.chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

        if not filename:
            filename = f"news_impact_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"

        url = f"{self.TELEGRAM_API_URL.format(token=self.bot_token)}/sendDocument"

        # Build multipart form data
        boundary = '----FormBoundary7MA4YWxkTrZu0gW'
        body = b''

        # chat_id field
        body += f'--{boundary}\r\n'.encode()
        body += f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'.encode()
        body += f'{self.chat_id}\r\n'.encode()

        # caption field
        if caption:
            body += f'--{boundary}\r\n'.encode()
            body += f'Content-Disposition: form-data; name="caption"\r\n\r\n'.encode()
            body += f'{caption}\r\n'.encode()

        # document field
        body += f'--{boundary}\r\n'.encode()
        body += (f'Content-Disposition: form-data; name="document"; '
                 f'filename="{filename}"\r\n').encode()
        body += f'Content-Type: application/pdf\r\n\r\n'.encode()
        body += pdf_bytes
        body += f'\r\n--{boundary}--\r\n'.encode()

        req = Request(url, data=body, method='POST')
        req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')

        try:
            response = urlopen(req, timeout=30)
            result = json.loads(response.read().decode('utf-8'))
            logger.info(f"Telegram document sent successfully")
            return result
        except HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else str(e)
            logger.error(f"Telegram API error {e.code}: {error_body}")
            raise
        except Exception as e:
            logger.error(f"Error sending to Telegram: {e}")
            raise

    def send_telegram_message(self, text: str) -> Dict:
        """Send a plain text message to Telegram."""
        if not self.bot_token or not self.chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

        url = f"{self.TELEGRAM_API_URL.format(token=self.bot_token)}/sendMessage"
        payload = json.dumps({
            'chat_id': self.chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }).encode('utf-8')

        req = Request(url, data=payload, method='POST')
        req.add_header('Content-Type', 'application/json')

        response = urlopen(req, timeout=15)
        return json.loads(response.read().decode('utf-8'))

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def generate_and_send_report(self) -> Dict:
        """Generate the PDF report and send it to Telegram."""
        logger.info("Generating news impact PDF report...")
        pdf_bytes = self.generate_pdf()
        logger.info(f"PDF generated: {len(pdf_bytes)} bytes")

        now = datetime.now()
        filename = f"news_impact_{now.strftime('%Y%m%d_%H%M')}.pdf"
        caption = f"News Impact Report - {now.strftime('%Y-%m-%d %H:%M')}"

        result = self.send_telegram_document(pdf_bytes, filename=filename, caption=caption)

        return {
            'status': 'success',
            'pdf_size_bytes': len(pdf_bytes),
            'filename': filename,
            'telegram_ok': result.get('ok', False)
        }
