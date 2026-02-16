"""
Context-Aware Keyword Matcher

Improves keyword matching with semantic understanding:
- Negation handling ("not approved", "no impact")
- Entity-role linking (which company got approved/rejected?)
- Context windows around matches

Reduces false positives from simple regex matching.

Usage:
    matcher = ContextAwareMatcher()
    matches = matcher.match_with_context(
        text="FDA did not approve Pfizer's drug",
        keywords=['fda', 'approval', 'pfizer']
    )
    # Returns matches with negation flags and context
"""

import re
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class ContextAwareMatcher:
    """Context-aware keyword matching with negation and entity linking."""

    # Negation words that flip sentiment
    NEGATION_WORDS = [
        'not', 'no', 'never', 'neither', 'nor', 'none', 'nobody', 'nothing',
        'without', 'lack', 'lacking', 'failed', 'fails', 'failure',
        'denied', 'denies', 'reject', 'rejected', 'rejects',
    ]

    # Distance threshold for negation (words)
    NEGATION_WINDOW = 5

    def __init__(self):
        self.negation_pattern = re.compile(
            r'\b(' + '|'.join(re.escape(w) for w in self.NEGATION_WORDS) + r')\b',
            re.IGNORECASE
        )

    def match_with_context(self, text: str, keywords: List[Dict]) -> List[Dict]:
        """
        Match keywords with context awareness.
        
        Args:
            text: Article text (title + summary)
            keywords: List of keyword dicts with 'keyword' and 'event_score'
            
        Returns:
            List of matched keyword dicts with added context fields:
            - is_negated: bool
            - context_snippet: str (surrounding text)
            - confidence: float (0-1, reduced if negated)
        """
        if not text or not keywords:
            return []

        text_lower = text.lower()
        words = re.findall(r'\b\w+\b', text_lower)
        
        matches = []

        for kw in keywords:
            keyword_lower = kw['keyword'].lower()
            pattern = r'\b' + re.escape(keyword_lower) + r'\b'
            
            for match in re.finditer(pattern, text_lower):
                match_pos = match.start()
                
                # Extract context window (50 chars before and after)
                context_start = max(0, match_pos - 50)
                context_end = min(len(text), match_pos + len(keyword_lower) + 50)
                context_snippet = text[context_start:context_end].strip()
                
                # Check for negation
                is_negated = self._check_negation(text_lower, match_pos, words)
                
                # Compute confidence (reduced if negated)
                confidence = 0.3 if is_negated else 1.0
                
                match_dict = {
                    **kw,
                    'is_negated': is_negated,
                    'context_snippet': context_snippet,
                    'confidence': confidence,
                }
                
                matches.append(match_dict)
                break

        return matches

    def _check_negation(self, text: str, match_pos: int, words: List[str]) -> bool:
        """
        Check if a keyword match is negated.
        
        Args:
            text: Full text (lowercase)
            match_pos: Character position of match
            words: List of words in text
            
        Returns:
            True if negated, False otherwise
        """
        # Get word index of the match
        text_before_match = text[:match_pos]
        word_idx = len(re.findall(r'\b\w+\b', text_before_match))
        
        # Check words within negation window before the match
        window_start = max(0, word_idx - self.NEGATION_WINDOW)
        window_words = words[window_start:word_idx]
        
        # Check if any negation word appears in window
        for word in window_words:
            if word in self.NEGATION_WORDS:
                return True
        
        return False

    def filter_confident_matches(self, matches: List[Dict], 
                                  min_confidence: float = 0.5) -> List[Dict]:
        """
        Filter matches to only those above confidence threshold.
        
        Args:
            matches: List of matches with confidence scores
            min_confidence: Minimum confidence threshold
            
        Returns:
            Filtered list of matches
        """
        return [m for m in matches if m.get('confidence', 1.0) >= min_confidence]

    def adjust_scores_for_context(self, matches: List[Dict]) -> List[Dict]:
        """
        Adjust event scores based on context (negation, etc.).
        
        Args:
            matches: List of matches with context
            
        Returns:
            Matches with adjusted event_score
        """
        adjusted = []
        
        for match in matches:
            adjusted_match = match.copy()
            
            if match.get('is_negated', False):
                original_score = match.get('event_score', 5)
                adjusted_match['event_score'] = max(1, int(original_score * 0.3))
                adjusted_match['score_adjustment_reason'] = 'negated'
            
            adjusted.append(adjusted_match)
        
        return adjusted

    def extract_entity_roles(self, text: str, tickers: List[str], 
                             trigger_phrase: str) -> Dict[str, str]:
        """
        Link entities to roles in the event (e.g., which company got approved?).
        
        Args:
            text: Article text
            tickers: List of tickers mentioned
            trigger_phrase: Trigger phrase (e.g., "fda approval")
            
        Returns:
            Dict mapping ticker -> role ('subject', 'object', 'mentioned')
        """
        if not tickers or not trigger_phrase:
            return {}

        text_lower = text.lower()
        trigger_lower = trigger_phrase.lower()
        
        # Find trigger phrase position
        trigger_match = re.search(r'\b' + re.escape(trigger_lower) + r'\b', text_lower)
        if not trigger_match:
            return {}

        trigger_pos = trigger_match.start()
        
        roles = {}
        
        for ticker in tickers:
            ticker_lower = ticker.lower()
            
            # Find closest mention to trigger phrase
            closest_distance = float('inf')
            closest_pos = None
            
            for match in re.finditer(r'\b' + re.escape(ticker_lower) + r'\b', text_lower):
                distance = abs(match.start() - trigger_pos)
                if distance < closest_distance:
                    closest_distance = distance
                    closest_pos = match.start()
            
            if closest_pos is None:
                roles[ticker] = 'mentioned'
            elif closest_distance < 50:
                if closest_pos < trigger_pos:
                    roles[ticker] = 'subject'
                else:
                    roles[ticker] = 'object'
            else:
                roles[ticker] = 'mentioned'
        
        return roles
