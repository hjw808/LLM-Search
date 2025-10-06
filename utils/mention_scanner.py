import re
from typing import List, Dict, Any, Tuple
import logging

class MentionScanner:
    def __init__(self, business_name: str, business_url: str, business_aliases: List[str] = None, competitors: List[str] = None):
        self.business_name = business_name
        self.business_url = business_url
        self.business_aliases = business_aliases or []
        self.competitors = competitors or []
        self.logger = logging.getLogger(__name__)

        # Create domain pattern from URL
        self.domain_pattern = self._create_domain_pattern(business_url)

        # Pre-compile regex patterns for better performance
        self._compile_patterns()

    def _create_domain_pattern(self, url: str) -> str:
        """Create regex pattern for domain matching."""
        if not url:
            return ""

        # Extract domain
        domain = re.sub(r'^https?://', '', url)
        domain = re.sub(r'^www\.', '', domain)
        domain = domain.split('/')[0]

        # Escape special regex characters
        domain = re.escape(domain)
        return domain

    def _compile_patterns(self):
        """Pre-compile all regex patterns for better performance."""
        # Business name patterns
        business_terms = [self.business_name] + self.business_aliases
        business_escaped = [re.escape(term.lower()) for term in business_terms if term]

        if business_escaped:
            business_pattern = '|'.join(f'({term})' for term in business_escaped)
            self.business_regex = re.compile(business_pattern, re.IGNORECASE)
        else:
            self.business_regex = None

        # Domain pattern
        if self.domain_pattern:
            self.domain_regex = re.compile(self.domain_pattern, re.IGNORECASE)
        else:
            self.domain_regex = None

        # Competitor patterns
        if self.competitors:
            competitor_escaped = [re.escape(comp.lower()) for comp in self.competitors if comp]
            if competitor_escaped:
                competitor_pattern = '|'.join(f'({comp})' for comp in competitor_escaped)
                self.competitor_regex = re.compile(competitor_pattern, re.IGNORECASE)
            else:
                self.competitor_regex = None
        else:
            self.competitor_regex = None

    def scan_for_business_mentions(self, text: str) -> Dict[str, Any]:
        """Scan text for business mentions and return detailed analysis."""
        if not text:
            return self._empty_result()

        text_lower = text.lower()

        # Check for business name mentions
        business_mentioned = self._check_business_name_mentions(text_lower)

        # Check for URL/domain mentions
        domain_mentioned = self._check_domain_mentions(text_lower)

        # Overall business mentioned
        mentioned = business_mentioned or domain_mentioned

        # Check position if mentioned
        position = self._get_mention_position(text_lower) if mentioned else None

        # Analyze context
        context_type = self._analyze_context(text_lower) if mentioned else None

        # Check competitors
        competitors_mentioned = self._check_competitors(text_lower)

        return {
            'business_mentioned': mentioned,
            'business_name_found': business_mentioned,
            'domain_found': domain_mentioned,
            'position': position,
            'context_type': context_type,
            'competitors_mentioned': competitors_mentioned,
            'mention_details': self._get_mention_details(text, mentioned)
        }

    def _check_business_name_mentions(self, text_lower: str) -> bool:
        """Check if business name or aliases are mentioned using compiled regex."""
        if self.business_regex:
            return bool(self.business_regex.search(text_lower))
        return False

    def _check_domain_mentions(self, text_lower: str) -> bool:
        """Check if business domain/URL is mentioned using compiled regex."""
        if self.domain_regex:
            return bool(self.domain_regex.search(text_lower))
        return False

    def _get_mention_position(self, text_lower: str) -> str:
        """Determine where in the text the business is mentioned using compiled regex."""
        text_length = len(text_lower)
        if text_length == 0:
            return "Unknown"

        # Use compiled regex to find first mention position
        if self.business_regex:
            match = self.business_regex.search(text_lower)
            if match:
                business_pos = match.start()
                # Calculate relative position
                relative_pos = business_pos / text_length

                if relative_pos < 0.33:
                    return "Beginning"
                elif relative_pos < 0.67:
                    return "Middle"
                else:
                    return "End"

        return "Unknown"

    def _analyze_context(self, text_lower: str) -> str:
        """Analyze the context in which the business is mentioned."""
        # Positive indicators
        positive_words = [
            'recommend', 'best', 'excellent', 'great', 'good', 'quality',
            'trusted', 'reliable', 'professional', 'expert', 'top'
        ]

        # Negative indicators
        negative_words = [
            'avoid', 'bad', 'poor', 'terrible', 'worst', 'problem',
            'issue', 'complaint', 'disappointing'
        ]

        # Neutral/comparison indicators
        comparison_words = [
            'option', 'alternative', 'consider', 'compare', 'choice',
            'available', 'include', 'among', 'such as'
        ]

        # Count word types around business mentions
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        comparison_count = sum(1 for word in comparison_words if word in text_lower)

        # Determine context
        if positive_count > negative_count and positive_count > 0:
            return "Recommended"
        elif negative_count > positive_count and negative_count > 0:
            return "Negative"
        elif comparison_count > 0:
            return "Comparison"
        else:
            return "Neutral"

    def _check_competitors(self, text_lower: str) -> List[str]:
        """Check which competitors are mentioned using compiled regex."""
        mentioned_competitors = []

        if self.competitor_regex:
            matches = self.competitor_regex.findall(text_lower)
            # Extract non-empty groups from matches
            for match in matches:
                if isinstance(match, tuple):
                    # Find the non-empty group
                    for group in match:
                        if group:
                            mentioned_competitors.append(group)
                            break
                else:
                    mentioned_competitors.append(match)

        return mentioned_competitors

    def _get_mention_details(self, text: str, mentioned: bool) -> Dict[str, Any]:
        """Get detailed information about mentions."""
        if not mentioned:
            return {}

        details = {}
        text_lower = text.lower()

        # Find exact mention locations
        mentions = []

        # Check business name
        business_matches = list(re.finditer(re.escape(self.business_name.lower()), text_lower))
        for match in business_matches:
            mentions.append({
                'text': self.business_name,
                'start': match.start(),
                'end': match.end(),
                'type': 'business_name'
            })

        # Check aliases
        for alias in self.business_aliases:
            alias_matches = list(re.finditer(re.escape(alias.lower()), text_lower))
            for match in alias_matches:
                mentions.append({
                    'text': alias,
                    'start': match.start(),
                    'end': match.end(),
                    'type': 'alias'
                })

        details['mentions'] = mentions
        details['total_mentions'] = len(mentions)

        return details

    def _empty_result(self) -> Dict[str, Any]:
        """Return empty analysis result."""
        return {
            'business_mentioned': False,
            'business_name_found': False,
            'domain_found': False,
            'position': None,
            'context_type': None,
            'competitors_mentioned': [],
            'mention_details': {}
        }