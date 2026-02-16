"""
Ticker Relevance Service

Computes relevance scores for tickers in multi-company articles.
Prevents false signals by weighting tickers based on:
- Mention frequency in article text
- Presence in title vs body
- Proximity to trigger keywords

Usage:
    service = TickerRelevanceService()
    scores = service.compute_relevance_scores(
        article_text="Pfizer announces partnership with Moderna...",
        tickers=['PFE', 'MRNA'],
        company_names=['Pfizer', 'Moderna']
    )
    # Returns: {'PFE': 0.85, 'MRNA': 0.65}
"""

import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class TickerRelevanceService:
    """Compute ticker relevance scores for multi-company articles."""

    # Trigger phrases that indicate significant events
    TRIGGER_PHRASES = [
        'fda approval', 'fda rejection', 'clinical trial', 'phase 3', 'phase 2',
        'breakthrough', 'acquisition', 'merger', 'partnership', 'collaboration',
        'earnings', 'revenue', 'guidance', 'recall', 'lawsuit', 'settlement',
        'approval', 'rejected', 'failed', 'succeeded', 'exceeded', 'missed',
        'announced', 'reported', 'filed', 'submitted', 'received', 'granted',
    ]

    def __init__(self):
        self.trigger_patterns = [
            re.compile(r'\b' + re.escape(phrase) + r'\b', re.IGNORECASE)
            for phrase in self.TRIGGER_PHRASES
        ]

    def compute_relevance_scores(self, title: str, summary: str, 
                                  tickers: List[str], 
                                  company_names: List[str]) -> Dict[str, float]:
        """
        Compute relevance scores for each ticker in an article.
        
        Args:
            title: Article title
            summary: Article summary/body
            tickers: List of ticker symbols
            company_names: List of company names (parallel to tickers)
            
        Returns:
            Dict mapping ticker -> relevance score (0-1)
        """
        if not tickers:
            return {}

        if len(tickers) == 1:
            return {tickers[0]: 1.0}

        title = title or ''
        summary = summary or ''
        full_text = f"{title}. {summary}"

        scores = {}

        for i, ticker in enumerate(tickers):
            company_name = company_names[i] if i < len(company_names) else None
            score = self._compute_single_relevance(
                title, summary, full_text, ticker, company_name
            )
            scores[ticker] = score

        # Normalize scores so the highest is 1.0
        if scores:
            max_score = max(scores.values())
            if max_score > 0:
                scores = {k: round(v / max_score, 2) for k, v in scores.items()}

        return scores

    def _compute_single_relevance(self, title: str, summary: str, full_text: str,
                                   ticker: str, company_name: str = None) -> float:
        """
        Compute relevance score for a single ticker.
        
        Scoring components:
        - Title presence: +0.5
        - Mention frequency: +0.3 (scaled by count)
        - Proximity to triggers: +0.2 (if within 50 chars of trigger phrase)
        """
        score = 0.0

        # Component 1: Title presence (0.5 points)
        title_lower = title.lower()
        ticker_lower = ticker.lower()
        company_lower = company_name.lower() if company_name else ''

        if ticker_lower in title_lower or (company_lower and company_lower in title_lower):
            score += 0.5

        # Component 2: Mention frequency (0.3 points max)
        full_text_lower = full_text.lower()
        
        ticker_mentions = len(re.findall(r'\b' + re.escape(ticker_lower) + r'\b', full_text_lower))
        company_mentions = 0
        if company_lower:
            company_mentions = len(re.findall(r'\b' + re.escape(company_lower) + r'\b', full_text_lower))
        
        total_mentions = ticker_mentions + company_mentions
        
        # Scale: 1 mention = 0.1, 2 = 0.2, 3+ = 0.3
        mention_score = min(total_mentions * 0.1, 0.3)
        score += mention_score

        # Component 3: Proximity to trigger phrases (0.2 points)
        proximity_score = self._compute_proximity_score(
            full_text_lower, ticker_lower, company_lower
        )
        score += proximity_score

        return score

    def _compute_proximity_score(self, text: str, ticker: str, 
                                  company_name: str = None) -> float:
        """
        Check if ticker/company appears near trigger phrases.
        
        Returns:
            0.2 if within 50 chars of a trigger, else 0.0
        """
        # Find all positions of ticker/company mentions
        entity_positions = []
        
        for match in re.finditer(r'\b' + re.escape(ticker) + r'\b', text):
            entity_positions.append(match.start())
        
        if company_name:
            for match in re.finditer(r'\b' + re.escape(company_name) + r'\b', text):
                entity_positions.append(match.start())

        if not entity_positions:
            return 0.0

        # Find all trigger phrase positions
        trigger_positions = []
        for pattern in self.trigger_patterns:
            for match in pattern.finditer(text):
                trigger_positions.append(match.start())

        if not trigger_positions:
            return 0.0

        # Check if any entity is within 50 chars of any trigger
        proximity_threshold = 50
        for entity_pos in entity_positions:
            for trigger_pos in trigger_positions:
                if abs(entity_pos - trigger_pos) <= proximity_threshold:
                    return 0.2

        return 0.0

    def filter_top_relevant_tickers(self, scores: Dict[str, float], 
                                     top_n: int = 3, 
                                     min_score: float = 0.3) -> List[str]:
        """
        Filter to top N most relevant tickers above minimum score.
        
        Args:
            scores: Dict of ticker -> relevance score
            top_n: Max number of tickers to return
            min_score: Minimum relevance score threshold
            
        Returns:
            List of top N ticker symbols
        """
        filtered = {k: v for k, v in scores.items() if v >= min_score}
        sorted_tickers = sorted(filtered.items(), key=lambda x: -x[1])
        return [ticker for ticker, score in sorted_tickers[:top_n]]

    def update_snapshot_relevance(self, db_config: Dict, article_id: int):
        """
        Compute and update relevance scores for all tickers in an article.
        
        Args:
            db_config: Database configuration
            article_id: Article ID
        """
        import pymysql

        connection = pymysql.connect(
            **db_config,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

        try:
            with connection.cursor() as cursor:
                # Get article data
                cursor.execute(
                    """SELECT title, summary, stock_tickers, company_names
                       FROM rss_items WHERE id = %s""",
                    (article_id,)
                )
                article = cursor.fetchone()

                if not article or not article['stock_tickers']:
                    return

                tickers = [t.strip() for t in article['stock_tickers'].split(',') if t.strip()]
                company_names = []
                if article['company_names']:
                    company_names = [c.strip() for c in article['company_names'].split(',') if c.strip()]

                # Compute relevance scores
                scores = self.compute_relevance_scores(
                    article['title'] or '',
                    article['summary'] or '',
                    tickers,
                    company_names
                )

                # Update article_stock_snapshots
                for ticker, score in scores.items():
                    # Count mentions
                    full_text = f"{article['title']}. {article['summary']}".lower()
                    ticker_count = len(re.findall(r'\b' + re.escape(ticker.lower()) + r'\b', full_text))
                    
                    # Check if in title
                    in_title = 1 if ticker.lower() in (article['title'] or '').lower() else 0

                    cursor.execute(
                        """UPDATE article_stock_snapshots
                           SET ticker_relevance_score = %s,
                               mention_count = %s,
                               in_title = %s
                           WHERE article_id = %s AND ticker = %s""",
                        (score, ticker_count, in_title, article_id, ticker)
                    )

                connection.commit()
                logger.info(f"[RELEVANCE] Updated scores for article {article_id}: {scores}")

        finally:
            connection.close()
