"""
News Scoring Service

Composite scoring model that determines the impact significance of each news article.
Instead of alerting on every keyword match, articles are scored across multiple layers:

  Layer 1: Keyword Event Score — user-assigned importance per keyword (1-10)
  Layer 2: Market Cap Multiplier — amplifies scores for small/mid-cap stocks
  Layer 3: Surprise Score — NLP detection of unexpected/beat/miss language
  Layer 4: Market Reaction Score — (planned, not yet implemented)

Final Score = (keyword_sum × cap_multiplier) + surprise_score

See NEWS_SCORING_MODEL.md for full documentation.

Usage:
    scorer = NewsScoringService()
    result = scorer.score_article(
        text="Pfizer receives unexpected FDA breakthrough designation",
        matched_keywords=[{'id': 1, 'keyword': 'pfizer', 'event_score': 8}, ...],
        market_caps=[150_000_000_000]  # from company_extractor
    )
    # result = {
    #     'score_total': 18.0,
    #     'score_keyword': 14,
    #     'score_cap_mult': 1.0,
    #     'score_surprise': 4.0,
    #     'surprise_dir': 'positive',
    #     'surprise_phrases': [('unexpected', 2, 'positive'), ...]
    # }
"""

import re
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Surprise phrase dictionaries
# ---------------------------------------------------------------------------

POSITIVE_SURPRISE_PHRASES: List[Tuple[str, int]] = [
    # (phrase, score)
    ("statistically significant improvement", 3),
    ("exceeded primary endpoint", 3),
    ("complete response", 3),
    ("better than expected", 2),
    ("exceeded expectations", 2),
    ("beat estimates", 2),
    ("blew past", 2),
    ("strong efficacy", 2),
    ("unexpected", 2),
    ("breakthrough", 2),
    ("first-in-class", 2),
    ("accelerated approval", 2),
    ("raised guidance", 2),
    ("record revenue", 2),
    ("superior to", 2),
    ("outperformed", 1),
    ("ahead of schedule", 1),
    ("positive data", 1),
]

NEGATIVE_SURPRISE_PHRASES: List[Tuple[str, int]] = [
    ("complete response letter", 3),
    ("clinical hold", 3),
    ("did not achieve", 2),
    ("worse than expected", 2),
    ("missed estimates", 2),
    ("failed to meet", 2),
    ("safety concern", 2),
    ("adverse event", 2),
    ("recall", 2),
    ("lowered guidance", 2),
    ("terminated", 2),
    ("suspended", 2),
    ("warning letter", 2),
    ("downgraded", 1),
    ("disappointing", 1),
]

SURPRISE_SCORE_CAP = 5


# ---------------------------------------------------------------------------
# Market Cap Multiplier Tiers
# ---------------------------------------------------------------------------

MARKET_CAP_TIERS = [
    # (upper_bound_usd, multiplier)
    (1_000_000_000, 1.6),       # < $1B
    (5_000_000_000, 1.3),       # $1B - $5B
    (20_000_000_000, 1.1),      # $5B - $20B
]
MARKET_CAP_DEFAULT_MULTIPLIER = 1.0  # > $20B or unknown


class NewsScoringService:
    """Score news articles using a composite model."""

    def __init__(self):
        # Pre-compile regex patterns for surprise phrases (longest first to avoid partial matches)
        self._positive_patterns = [
            (re.compile(r'\b' + re.escape(phrase) + r'\b', re.IGNORECASE), score, phrase)
            for phrase, score in sorted(POSITIVE_SURPRISE_PHRASES, key=lambda x: -len(x[0]))
        ]
        self._negative_patterns = [
            (re.compile(r'\b' + re.escape(phrase) + r'\b', re.IGNORECASE), score, phrase)
            for phrase, score in sorted(NEGATIVE_SURPRISE_PHRASES, key=lambda x: -len(x[0]))
        ]

    # ------------------------------------------------------------------
    # Layer 1: Keyword Event Score
    # ------------------------------------------------------------------

    @staticmethod
    def compute_keyword_score(matched_keywords: List[Dict]) -> int:
        """
        Sum the event_score of all matched keywords.

        Args:
            matched_keywords: List of keyword dicts with 'event_score' key.
                              Falls back to 5 if event_score is missing.

        Returns:
            Sum of event scores.
        """
        return sum(kw.get('event_score', 5) for kw in matched_keywords)

    # ------------------------------------------------------------------
    # Layer 2: Market Cap Multiplier
    # ------------------------------------------------------------------

    @staticmethod
    def get_market_cap_multiplier(market_cap_usd: Optional[int]) -> float:
        """
        Determine the multiplier based on market capitalization.

        Args:
            market_cap_usd: Market cap in USD, or None if unknown.

        Returns:
            Multiplier (1.0 to 1.6).
        """
        if market_cap_usd is None:
            return MARKET_CAP_DEFAULT_MULTIPLIER

        for upper_bound, multiplier in MARKET_CAP_TIERS:
            if market_cap_usd < upper_bound:
                return multiplier

        return MARKET_CAP_DEFAULT_MULTIPLIER

    @staticmethod
    def get_smallest_market_cap(market_caps: List[Optional[int]]) -> Optional[int]:
        """
        From a list of market caps (one per matched ticker), return the smallest.
        None values are ignored. Returns None if all are None.
        """
        valid = [mc for mc in market_caps if mc is not None]
        return min(valid) if valid else None

    # ------------------------------------------------------------------
    # Layer 3: Surprise Score
    # ------------------------------------------------------------------

    def detect_surprise_phrases(self, text: str) -> Dict:
        """
        Scan text for positive and negative surprise phrases.

        Args:
            text: Article title + summary.

        Returns:
            Dict with:
                - score: capped surprise score (0-5)
                - raw_score: uncapped sum
                - direction: 'positive', 'negative', 'mixed', or 'none'
                - phrases: list of (phrase, score, direction) tuples
        """
        if not text:
            return {'score': 0, 'raw_score': 0, 'direction': 'none', 'phrases': []}

        found_phrases = []
        matched_spans = set()

        # Check positive phrases
        for pattern, score, phrase in self._positive_patterns:
            for match in pattern.finditer(text):
                span = (match.start(), match.end())
                # Avoid double-counting overlapping phrases
                if not any(s[0] <= span[0] < s[1] or s[0] < span[1] <= s[1] for s in matched_spans):
                    found_phrases.append((phrase, score, 'positive'))
                    matched_spans.add(span)

        # Check negative phrases
        for pattern, score, phrase in self._negative_patterns:
            for match in pattern.finditer(text):
                span = (match.start(), match.end())
                if not any(s[0] <= span[0] < s[1] or s[0] < span[1] <= s[1] for s in matched_spans):
                    found_phrases.append((phrase, score, 'negative'))
                    matched_spans.add(span)

        if not found_phrases:
            return {'score': 0, 'raw_score': 0, 'direction': 'none', 'phrases': []}

        raw_score = sum(s for _, s, _ in found_phrases)
        capped_score = min(raw_score, SURPRISE_SCORE_CAP)

        # Determine direction
        pos_count = sum(1 for _, _, d in found_phrases if d == 'positive')
        neg_count = sum(1 for _, _, d in found_phrases if d == 'negative')
        if pos_count > 0 and neg_count > 0:
            direction = 'mixed'
        elif pos_count > 0:
            direction = 'positive'
        elif neg_count > 0:
            direction = 'negative'
        else:
            direction = 'none'

        return {
            'score': capped_score,
            'raw_score': raw_score,
            'direction': direction,
            'phrases': found_phrases,
        }

    # ------------------------------------------------------------------
    # Composite scoring
    # ------------------------------------------------------------------

    def score_article(self, text: str, matched_keywords: List[Dict],
                      market_caps: List[Optional[int]] = None) -> Dict:
        """
        Compute the composite score for an article.

        Args:
            text: Full article text (title + summary).
            matched_keywords: List of keyword dicts, each with 'event_score'.
            market_caps: List of market caps (one per matched company/ticker).
                         Pass None or empty list if no tickers found.

        Returns:
            Dict with full score breakdown:
                - score_total: final composite score
                - score_keyword: sum of keyword event scores
                - score_cap_mult: market cap multiplier used
                - score_surprise: surprise score (0-5)
                - surprise_dir: 'positive', 'negative', 'mixed', 'none'
                - surprise_phrases: list of (phrase, score, direction)
        """
        # Layer 1: Keyword event scores
        score_keyword = self.compute_keyword_score(matched_keywords)

        # Layer 2: Market cap multiplier
        market_caps = market_caps or []
        smallest_cap = self.get_smallest_market_cap(market_caps)
        cap_multiplier = self.get_market_cap_multiplier(smallest_cap)

        # Layer 3: Surprise score
        surprise = self.detect_surprise_phrases(text)

        # Final score
        adjusted_keyword = score_keyword * cap_multiplier
        score_total = adjusted_keyword + surprise['score']

        result = {
            'score_total': round(score_total, 2),
            'score_keyword': score_keyword,
            'score_cap_mult': cap_multiplier,
            'score_surprise': surprise['score'],
            'surprise_dir': surprise['direction'],
            'surprise_phrases': surprise['phrases'],
            'market_cap_usd': smallest_cap,
        }

        logger.info(
            f"[SCORING] keyword_sum={score_keyword} × cap_mult={cap_multiplier} "
            f"+ surprise={surprise['score']} ({surprise['direction']}) "
            f"= total={score_total:.2f} | "
            f"phrases={[p[0] for p in surprise['phrases']]}"
        )

        return result
