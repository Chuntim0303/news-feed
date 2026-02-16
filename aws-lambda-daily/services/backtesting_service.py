"""
Backtesting and Calibration Service

Evaluates scoring model performance and provides calibration metrics:
- Precision@K for top scored alerts
- Hit rate by score bucket
- Average abnormal return by score decile
- Model parameter tuning recommendations

Usage:
    service = BacktestingService(db_config=db_config)
    results = service.run_backtest(start_date='2026-01-01', end_date='2026-02-01')
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pymysql

logger = logging.getLogger(__name__)


class BacktestingService:
    """Backtest and calibrate the news scoring model."""

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
    # Backtest execution
    # =========================================================================

    def run_backtest(self, start_date: str = None, end_date: str = None,
                     min_score: float = 5.0) -> Dict:
        """
        Run backtest on historical scored articles.
        
        Args:
            start_date: Start date (YYYY-MM-DD), defaults to 30 days ago
            end_date: End date (YYYY-MM-DD), defaults to today
            min_score: Minimum score threshold to include
            
        Returns:
            Dict with backtest results and metrics
        """
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')

        logger.info(f"[BACKTEST] Running backtest from {start_date} to {end_date}")

        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                # Get all scored articles with returns in date range
                cursor.execute(
                    """SELECT 
                           al.score_total,
                           al.score_keyword,
                           al.score_cap_mult,
                           al.score_surprise,
                           al.score_market_reaction,
                           arw.ticker,
                           arw.return_1d,
                           arw.return_3d,
                           arw.return_5d,
                           arw.abnormal_return_1d,
                           arw.abnormal_return_3d,
                           arw.abnormal_return_5d,
                           ri.published_at
                       FROM alert_log al
                       JOIN rss_items ri ON ri.id = al.rss_item_id
                       JOIN article_return_windows arw 
                         ON arw.article_id = al.rss_item_id
                       WHERE DATE(ri.published_at) BETWEEN %s AND %s
                         AND al.score_total >= %s
                         AND arw.processing_status = 'complete'
                         AND arw.abnormal_return_1d IS NOT NULL""",
                    (start_date, end_date, min_score)
                )
                data = cursor.fetchall()

            if not data:
                logger.warning("[BACKTEST] No data found for backtest period")
                return {'status': 'error', 'message': 'No data found'}

            logger.info(f"[BACKTEST] Analyzing {len(data)} article-ticker pairs")

            # Compute metrics
            results = {
                'period': {'start': start_date, 'end': end_date},
                'total_samples': len(data),
                'score_buckets': self._analyze_by_score_bucket(data),
                'precision_at_k': self._compute_precision_at_k(data),
                'hit_rate_by_bucket': self._compute_hit_rate_by_bucket(data),
                'avg_returns_by_decile': self._compute_returns_by_decile(data),
                'layer_contribution': self._analyze_layer_contribution(data),
            }

            # Store results
            self._store_backtest_results(results)

            return {'status': 'success', 'results': results}

        finally:
            connection.close()

    # =========================================================================
    # Metric computations
    # =========================================================================

    def _analyze_by_score_bucket(self, data: List[Dict]) -> Dict:
        """Group data by score buckets and compute average returns."""
        buckets = {
            '5-10': [],
            '10-15': [],
            '15-20': [],
            '20-30': [],
            '30+': [],
        }

        for row in data:
            score = float(row['score_total'])
            abnormal_1d = float(row['abnormal_return_1d']) if row['abnormal_return_1d'] else 0

            if score < 10:
                buckets['5-10'].append(abnormal_1d)
            elif score < 15:
                buckets['10-15'].append(abnormal_1d)
            elif score < 20:
                buckets['15-20'].append(abnormal_1d)
            elif score < 30:
                buckets['20-30'].append(abnormal_1d)
            else:
                buckets['30+'].append(abnormal_1d)

        results = {}
        for bucket, values in buckets.items():
            if values:
                results[bucket] = {
                    'count': len(values),
                    'avg_abnormal_return_1d': round(sum(values) / len(values), 2),
                    'max_abnormal_return_1d': round(max(values), 2),
                    'min_abnormal_return_1d': round(min(values), 2),
                }
            else:
                results[bucket] = {'count': 0}

        return results

    def _compute_precision_at_k(self, data: List[Dict], k: int = 10) -> Dict:
        """
        Compute Precision@K: percentage of top K scored articles with |abnormal_return| > 2%.
        """
        sorted_data = sorted(data, key=lambda x: -float(x['score_total']))
        top_k = sorted_data[:k]

        if not top_k:
            return {'k': k, 'precision': 0.0}

        hits = sum(1 for row in top_k if abs(float(row['abnormal_return_1d'] or 0)) > 2.0)
        precision = hits / len(top_k)

        return {
            'k': k,
            'precision': round(precision, 2),
            'hits': hits,
            'total': len(top_k),
        }

    def _compute_hit_rate_by_bucket(self, data: List[Dict]) -> Dict:
        """
        Compute hit rate (|abnormal_return_1d| > 2%) for each score bucket.
        """
        buckets = {
            '5-10': {'hits': 0, 'total': 0},
            '10-15': {'hits': 0, 'total': 0},
            '15-20': {'hits': 0, 'total': 0},
            '20-30': {'hits': 0, 'total': 0},
            '30+': {'hits': 0, 'total': 0},
        }

        for row in data:
            score = float(row['score_total'])
            abnormal_1d = float(row['abnormal_return_1d']) if row['abnormal_return_1d'] else 0
            is_hit = abs(abnormal_1d) > 2.0

            if score < 10:
                bucket = '5-10'
            elif score < 15:
                bucket = '10-15'
            elif score < 20:
                bucket = '15-20'
            elif score < 30:
                bucket = '20-30'
            else:
                bucket = '30+'

            buckets[bucket]['total'] += 1
            if is_hit:
                buckets[bucket]['hits'] += 1

        results = {}
        for bucket, counts in buckets.items():
            if counts['total'] > 0:
                hit_rate = counts['hits'] / counts['total']
                results[bucket] = {
                    'hit_rate': round(hit_rate, 2),
                    'hits': counts['hits'],
                    'total': counts['total'],
                }
            else:
                results[bucket] = {'hit_rate': 0.0, 'hits': 0, 'total': 0}

        return results

    def _compute_returns_by_decile(self, data: List[Dict]) -> Dict:
        """
        Compute average abnormal returns by score decile.
        """
        sorted_data = sorted(data, key=lambda x: float(x['score_total']))
        n = len(sorted_data)
        decile_size = n // 10

        deciles = {}
        for i in range(10):
            start_idx = i * decile_size
            end_idx = start_idx + decile_size if i < 9 else n
            decile_data = sorted_data[start_idx:end_idx]

            if decile_data:
                avg_return = sum(float(row['abnormal_return_1d'] or 0) for row in decile_data) / len(decile_data)
                deciles[f'D{i+1}'] = {
                    'avg_abnormal_return_1d': round(avg_return, 2),
                    'count': len(decile_data),
                    'score_range': f"{float(decile_data[0]['score_total']):.1f}-{float(decile_data[-1]['score_total']):.1f}"
                }

        return deciles

    def _analyze_layer_contribution(self, data: List[Dict]) -> Dict:
        """
        Analyze correlation between each scoring layer and abnormal returns.
        """
        layers = {
            'keyword': [],
            'market_cap': [],
            'surprise': [],
            'market_reaction': [],
        }

        for row in data:
            abnormal_1d = float(row['abnormal_return_1d']) if row['abnormal_return_1d'] else 0
            
            layers['keyword'].append((float(row['score_keyword'] or 0), abnormal_1d))
            layers['market_cap'].append((float(row['score_cap_mult'] or 1.0), abnormal_1d))
            layers['surprise'].append((float(row['score_surprise'] or 0), abnormal_1d))
            layers['market_reaction'].append((float(row['score_market_reaction'] or 0), abnormal_1d))

        results = {}
        for layer, pairs in layers.items():
            if pairs:
                correlation = self._compute_correlation(pairs)
                results[layer] = {
                    'correlation': round(correlation, 3),
                    'interpretation': self._interpret_correlation(correlation)
                }

        return results

    def _compute_correlation(self, pairs: List[Tuple[float, float]]) -> float:
        """Compute Pearson correlation coefficient."""
        if len(pairs) < 2:
            return 0.0

        x_values = [p[0] for p in pairs]
        y_values = [p[1] for p in pairs]

        n = len(pairs)
        mean_x = sum(x_values) / n
        mean_y = sum(y_values) / n

        numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
        denominator_x = sum((x - mean_x) ** 2 for x in x_values) ** 0.5
        denominator_y = sum((y - mean_y) ** 2 for y in y_values) ** 0.5

        if denominator_x == 0 or denominator_y == 0:
            return 0.0

        return numerator / (denominator_x * denominator_y)

    def _interpret_correlation(self, corr: float) -> str:
        """Interpret correlation strength."""
        abs_corr = abs(corr)
        if abs_corr > 0.7:
            return 'strong'
        elif abs_corr > 0.4:
            return 'moderate'
        elif abs_corr > 0.2:
            return 'weak'
        else:
            return 'negligible'

    # =========================================================================
    # Storage
    # =========================================================================

    def _store_backtest_results(self, results: Dict):
        """Store backtest results in database."""
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                backtest_date = datetime.now().strftime('%Y-%m-%d')

                for bucket, metrics in results.get('score_buckets', {}).items():
                    if metrics.get('count', 0) > 0:
                        cursor.execute(
                            """INSERT INTO scoring_backtest_results
                               (backtest_date, score_bucket, article_count,
                                avg_abnormal_return_1d, hit_rate, config_params)
                               VALUES (%s, %s, %s, %s, %s, %s)""",
                            (backtest_date, bucket, metrics['count'],
                             metrics.get('avg_abnormal_return_1d'),
                             results['hit_rate_by_bucket'].get(bucket, {}).get('hit_rate'),
                             json.dumps(results.get('layer_contribution', {})))
                        )

            connection.commit()
            logger.info(f"[BACKTEST] Stored results for {backtest_date}")

        finally:
            connection.close()

    # =========================================================================
    # Recommendations
    # =========================================================================

    def generate_tuning_recommendations(self, backtest_results: Dict) -> List[str]:
        """
        Generate recommendations for model parameter tuning based on backtest results.
        
        Args:
            backtest_results: Results from run_backtest()
            
        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Check layer contributions
        layer_contrib = backtest_results.get('layer_contribution', {})
        
        for layer, metrics in layer_contrib.items():
            corr = metrics.get('correlation', 0)
            if abs(corr) < 0.1:
                recommendations.append(
                    f"⚠️ {layer.title()} layer shows negligible correlation ({corr:.2f}) "
                    f"with returns. Consider adjusting weights or removing."
                )

        # Check hit rates
        hit_rates = backtest_results.get('hit_rate_by_bucket', {})
        high_score_hit_rate = hit_rates.get('20-30', {}).get('hit_rate', 0)
        
        if high_score_hit_rate < 0.3:
            recommendations.append(
                f"⚠️ High-score articles (20-30) have low hit rate ({high_score_hit_rate:.0%}). "
                f"Consider raising alert threshold or adjusting scoring weights."
            )

        # Check precision@K
        precision = backtest_results.get('precision_at_k', {}).get('precision', 0)
        if precision < 0.5:
            recommendations.append(
                f"⚠️ Precision@10 is low ({precision:.0%}). "
                f"Top-scored articles are not reliably predicting moves."
            )

        if not recommendations:
            recommendations.append("✅ Model performance looks good. No immediate tuning needed.")

        return recommendations
