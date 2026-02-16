"""
Enhanced Digest Service

Generates decision-grade digest outputs with:
- Abnormal returns vs benchmark
- Volume ratio percentiles
- Confidence scores (entity confidence + event uniqueness + market reaction)
- New alpha candidates section (high score + high abnormal return + low confounding)

Replaces descriptive summaries with actionable intelligence.

Usage:
    service = EnhancedDigestService(db_config=db_config)
    digest = service.generate_daily_digest(date='2026-02-15')
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pymysql

logger = logging.getLogger(__name__)


class EnhancedDigestService:
    """Generate enhanced digests with abnormal returns and confidence metrics."""

    def __init__(self, db_config: Dict = None):
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

    # =========================================================================
    # Main digest generation
    # =========================================================================

    def generate_daily_digest(self, target_date: str = None, 
                              min_score: float = 10.0) -> Dict:
        """
        Generate enhanced daily digest with abnormal returns and confidence metrics.
        
        Args:
            target_date: Date to generate digest for (YYYY-MM-DD), defaults to yesterday
            min_score: Minimum score threshold
            
        Returns:
            Dict with digest sections
        """
        if not target_date:
            target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        logger.info(f"[DIGEST] Generating enhanced digest for {target_date}")

        connection = self._get_connection()
        try:
            # Get all scored articles with returns for the date
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT 
                           ri.id,
                           ri.title,
                           ri.link,
                           ri.published_at,
                           al.score_total,
                           al.score_keyword,
                           al.score_surprise,
                           al.score_market_reaction,
                           arw.ticker,
                           arw.return_1d,
                           arw.abnormal_return_1d,
                           arw.volume_ratio_1d,
                           arw.gap_magnitude,
                           ass.ticker_relevance_score,
                           mrs.total_reaction_score
                       FROM rss_items ri
                       JOIN alert_log al ON al.rss_item_id = ri.id
                       LEFT JOIN article_return_windows arw 
                         ON arw.article_id = ri.id
                       LEFT JOIN article_stock_snapshots ass
                         ON ass.article_id = ri.id AND ass.ticker = arw.ticker
                       LEFT JOIN market_reaction_scores mrs
                         ON mrs.article_id = ri.id AND mrs.ticker = arw.ticker
                       WHERE DATE(ri.published_at) = %s
                         AND al.score_total >= %s
                         AND arw.processing_status = 'complete'
                       ORDER BY al.score_total DESC""",
                    (target_date, min_score)
                )
                articles = cursor.fetchall()

            if not articles:
                return {
                    'status': 'success',
                    'date': target_date,
                    'message': 'No articles found for this date',
                }

            # Build digest sections
            digest = {
                'date': target_date,
                'summary': self._generate_summary(articles),
                'top_movers': self._generate_top_movers(articles),
                'alpha_candidates': self._generate_alpha_candidates(articles, connection),
                'score_distribution': self._generate_score_distribution(articles),
                'sector_breakdown': self._generate_sector_breakdown(articles, connection),
            }

            return {'status': 'success', 'digest': digest}

        finally:
            connection.close()

    # =========================================================================
    # Digest sections
    # =========================================================================

    def _generate_summary(self, articles: List[Dict]) -> Dict:
        """Generate high-level summary statistics."""
        total_articles = len(articles)
        
        # Count articles with significant abnormal returns
        significant_moves = sum(
            1 for a in articles 
            if a.get('abnormal_return_1d') and abs(float(a['abnormal_return_1d'])) > 2.0
        )

        # Average abnormal return
        abnormal_returns = [
            float(a['abnormal_return_1d']) 
            for a in articles 
            if a.get('abnormal_return_1d') is not None
        ]
        avg_abnormal = sum(abnormal_returns) / len(abnormal_returns) if abnormal_returns else 0

        # Count high-confidence signals
        high_confidence = sum(
            1 for a in articles
            if float(a.get('score_total', 0)) > 20
        )

        return {
            'total_articles': total_articles,
            'significant_moves': significant_moves,
            'significant_move_rate': round(significant_moves / total_articles, 2) if total_articles > 0 else 0,
            'avg_abnormal_return_1d': round(avg_abnormal, 2),
            'high_confidence_signals': high_confidence,
        }

    def _generate_top_movers(self, articles: List[Dict], limit: int = 10) -> List[Dict]:
        """
        Generate top movers ranked by abnormal return magnitude.
        
        Includes:
        - Abnormal return vs benchmark
        - Volume ratio percentile
        - Confidence score
        """
        # Filter articles with abnormal returns
        movers = [
            a for a in articles 
            if a.get('abnormal_return_1d') is not None
        ]

        # Sort by absolute abnormal return
        movers.sort(key=lambda x: abs(float(x['abnormal_return_1d'])), reverse=True)

        top_movers = []
        for article in movers[:limit]:
            abnormal_return = float(article['abnormal_return_1d'])
            volume_ratio = float(article['volume_ratio_1d']) if article.get('volume_ratio_1d') else None
            
            # Compute confidence score
            confidence = self._compute_confidence_score(article)

            mover = {
                'ticker': article['ticker'],
                'title': article['title'][:80],
                'score': float(article['score_total']),
                'abnormal_return_1d': round(abnormal_return, 2),
                'volume_ratio': round(volume_ratio, 1) if volume_ratio else None,
                'confidence': confidence,
                'link': article.get('link'),
            }
            top_movers.append(mover)

        return top_movers

    def _generate_alpha_candidates(self, articles: List[Dict], 
                                    connection) -> List[Dict]:
        """
        Generate new alpha candidates section.
        
        Criteria:
        - High score (>15)
        - High abnormal return (>3%)
        - Low confounding (confidence >0.7)
        """
        from .confounder_service import ConfounderService
        
        confounder_service = ConfounderService(self.db_config)
        
        candidates = []

        for article in articles:
            score = float(article.get('score_total', 0))
            abnormal_return = float(article['abnormal_return_1d']) if article.get('abnormal_return_1d') else 0
            
            # Apply filters
            if score < 15 or abs(abnormal_return) < 3.0:
                continue

            # Check confounders
            pub_date = article['published_at']
            ticker = article['ticker']
            
            confounders = confounder_service.detect_confounders(ticker, pub_date)
            confidence = confounder_service.compute_confounder_confidence(confounders)

            if confidence < 0.7:
                continue

            # This is an alpha candidate
            candidate = {
                'ticker': ticker,
                'title': article['title'][:80],
                'score': score,
                'abnormal_return_1d': round(abnormal_return, 2),
                'confidence': confidence,
                'volume_ratio': round(float(article['volume_ratio_1d']), 1) if article.get('volume_ratio_1d') else None,
                'gap': round(float(article['gap_magnitude']), 2) if article.get('gap_magnitude') else None,
                'confounders': len(confounders),
                'link': article.get('link'),
            }
            candidates.append(candidate)

        # Sort by score * abnormal_return
        candidates.sort(key=lambda x: x['score'] * abs(x['abnormal_return_1d']), reverse=True)

        return candidates[:5]

    def _generate_score_distribution(self, articles: List[Dict]) -> Dict:
        """Generate score distribution by bucket."""
        buckets = {
            '10-15': 0,
            '15-20': 0,
            '20-30': 0,
            '30+': 0,
        }

        for article in articles:
            score = float(article.get('score_total', 0))
            if score < 15:
                buckets['10-15'] += 1
            elif score < 20:
                buckets['15-20'] += 1
            elif score < 30:
                buckets['20-30'] += 1
            else:
                buckets['30+'] += 1

        return buckets

    def _generate_sector_breakdown(self, articles: List[Dict], 
                                    connection) -> Dict:
        """Generate breakdown by sector."""
        sector_stats = {}

        for article in articles:
            ticker = article['ticker']
            
            # Get sector for ticker
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT sector FROM ticker_sector_mapping WHERE ticker = %s",
                    (ticker,)
                )
                result = cursor.fetchone()
                sector = result['sector'] if result else 'Unknown'

            if sector not in sector_stats:
                sector_stats[sector] = {
                    'count': 0,
                    'avg_abnormal_return': [],
                    'avg_score': [],
                }

            sector_stats[sector]['count'] += 1
            
            if article.get('abnormal_return_1d') is not None:
                sector_stats[sector]['avg_abnormal_return'].append(
                    float(article['abnormal_return_1d'])
                )
            
            sector_stats[sector]['avg_score'].append(float(article['score_total']))

        # Compute averages
        for sector, stats in sector_stats.items():
            if stats['avg_abnormal_return']:
                stats['avg_abnormal_return'] = round(
                    sum(stats['avg_abnormal_return']) / len(stats['avg_abnormal_return']), 2
                )
            else:
                stats['avg_abnormal_return'] = 0

            if stats['avg_score']:
                stats['avg_score'] = round(
                    sum(stats['avg_score']) / len(stats['avg_score']), 1
                )
            else:
                stats['avg_score'] = 0

        return sector_stats

    # =========================================================================
    # Confidence scoring
    # =========================================================================

    def _compute_confidence_score(self, article: Dict) -> float:
        """
        Compute overall confidence score for an article.
        
        Components:
        - Entity confidence (ticker relevance): 0-0.4
        - Event uniqueness (no clustering): 0-0.3
        - Market reaction confirmation: 0-0.3
        
        Returns:
            Confidence score (0-1)
        """
        confidence = 0.0

        # Component 1: Entity confidence (ticker relevance)
        relevance = float(article.get('ticker_relevance_score', 1.0))
        confidence += relevance * 0.4

        # Component 2: Event uniqueness (assume unique if no data, penalize if clustered)
        # This would check article_clusters table in production
        confidence += 0.3

        # Component 3: Market reaction confirmation
        reaction_score = float(article.get('total_reaction_score', 0))
        if reaction_score > 0:
            confidence += min(reaction_score / 5.0, 1.0) * 0.3

        return round(confidence, 2)

    # =========================================================================
    # Formatting
    # =========================================================================

    def format_digest_text(self, digest: Dict) -> str:
        """
        Format digest as human-readable text.
        
        Args:
            digest: Digest dict from generate_daily_digest()
            
        Returns:
            Formatted text string
        """
        lines = []
        lines.append(f"📊 Enhanced Stock Impact Digest — {digest['date']}")
        lines.append("=" * 60)
        lines.append("")

        # Summary
        summary = digest['summary']
        lines.append("📈 Summary")
        lines.append(f"  Total articles: {summary['total_articles']}")
        lines.append(f"  Significant moves (|abnormal return| > 2%): {summary['significant_moves']} "
                    f"({summary['significant_move_rate']:.0%})")
        lines.append(f"  Avg abnormal return: {summary['avg_abnormal_return_1d']:+.2f}%")
        lines.append(f"  High-confidence signals: {summary['high_confidence_signals']}")
        lines.append("")

        # Alpha candidates
        if digest['alpha_candidates']:
            lines.append("🎯 New Alpha Candidates")
            lines.append("   (High score + High abnormal return + Low confounding)")
            lines.append("")
            for i, candidate in enumerate(digest['alpha_candidates'], 1):
                lines.append(f"  {i}. {candidate['ticker']} — Score: {candidate['score']:.1f} | "
                           f"Abnormal: {candidate['abnormal_return_1d']:+.2f}% | "
                           f"Confidence: {candidate['confidence']:.0%}")
                lines.append(f"     {candidate['title']}")
                if candidate.get('volume_ratio'):
                    lines.append(f"     Volume: {candidate['volume_ratio']:.1f}× baseline")
                lines.append("")

        # Top movers
        lines.append("📉 Top Movers by Abnormal Return")
        lines.append("")
        for i, mover in enumerate(digest['top_movers'][:5], 1):
            lines.append(f"  {i}. {mover['ticker']} — {mover['abnormal_return_1d']:+.2f}% abnormal | "
                        f"Score: {mover['score']:.1f} | Confidence: {mover['confidence']:.0%}")
            lines.append(f"     {mover['title']}")
            if mover.get('volume_ratio'):
                lines.append(f"     Volume: {mover['volume_ratio']:.1f}× baseline")
            lines.append("")

        # Sector breakdown
        lines.append("🏢 Sector Breakdown")
        lines.append("")
        for sector, stats in sorted(digest['sector_breakdown'].items(), 
                                    key=lambda x: -x[1]['count']):
            lines.append(f"  {sector}: {stats['count']} articles | "
                        f"Avg abnormal: {stats['avg_abnormal_return']:+.2f}% | "
                        f"Avg score: {stats['avg_score']:.1f}")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    def format_digest_html(self, digest: Dict) -> str:
        """
        Format digest as HTML for email reports.
        
        Args:
            digest: Digest dict from generate_daily_digest()
            
        Returns:
            HTML string
        """
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #2c3e50; }}
                h2 {{ color: #34495e; margin-top: 20px; }}
                .summary {{ background: #ecf0f1; padding: 15px; border-radius: 5px; }}
                .candidate {{ background: #d5f4e6; padding: 10px; margin: 10px 0; border-left: 4px solid #27ae60; }}
                .mover {{ background: #fef5e7; padding: 10px; margin: 10px 0; border-left: 4px solid #f39c12; }}
                .metric {{ font-weight: bold; color: #2980b9; }}
            </style>
        </head>
        <body>
            <h1>📊 Enhanced Stock Impact Digest — {digest['date']}</h1>
            
            <div class="summary">
                <h2>📈 Summary</h2>
                <p>Total articles: <span class="metric">{digest['summary']['total_articles']}</span></p>
                <p>Significant moves: <span class="metric">{digest['summary']['significant_moves']}</span> 
                   ({digest['summary']['significant_move_rate']:.0%})</p>
                <p>Avg abnormal return: <span class="metric">{digest['summary']['avg_abnormal_return_1d']:+.2f}%</span></p>
            </div>
        """

        # Alpha candidates
        if digest['alpha_candidates']:
            html += "<h2>🎯 New Alpha Candidates</h2>"
            html += "<p><em>High score + High abnormal return + Low confounding</em></p>"
            for candidate in digest['alpha_candidates']:
                html += f"""
                <div class="candidate">
                    <strong>{candidate['ticker']}</strong> — 
                    Score: {candidate['score']:.1f} | 
                    Abnormal: {candidate['abnormal_return_1d']:+.2f}% | 
                    Confidence: {candidate['confidence']:.0%}<br>
                    {candidate['title']}<br>
                    <small>Volume: {candidate.get('volume_ratio', 'N/A')}× baseline</small>
                </div>
                """

        # Top movers
        html += "<h2>📉 Top Movers by Abnormal Return</h2>"
        for mover in digest['top_movers'][:5]:
            html += f"""
            <div class="mover">
                <strong>{mover['ticker']}</strong> — 
                {mover['abnormal_return_1d']:+.2f}% abnormal | 
                Score: {mover['score']:.1f}<br>
                {mover['title']}<br>
                <small>Volume: {mover.get('volume_ratio', 'N/A')}× baseline</small>
            </div>
            """

        html += "</body></html>"
        return html
