import re
from typing import List, Tuple, Dict, Any
import logging

class TextParser:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Pre-compile regex patterns for better performance
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile all regex patterns for better performance."""
        self.numbered_item_pattern = re.compile(r'^\d+[\.\)]\s*(.+)$')
        self.quote_pattern = re.compile(r'^["\'](.+)["\']$')
        self.provider_split_pattern = re.compile(r'=== (\w+) RESPONSES ===')
        self.query_pattern = re.compile(r'QUERY\s+(\d+):\s*(.+?)(?=\nRESPONSE|\n---|\Z)', re.DOTALL)
        self.response_pattern = re.compile(r'RESPONSE\s+(\d+)\s*\([^)]+\):\s*(.+?)(?=\n---|\nQUERY|\Z)', re.DOTALL)

    def parse_queries_from_response(self, response: str) -> List[str]:
        """Parse numbered queries from Perplexity API response."""
        if not response:
            return []

        queries = []
        lines = response.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip section headers
            if line.startswith('##') or line.startswith('#'):
                continue

            # Match numbered list items using compiled pattern
            match = self.numbered_item_pattern.match(line)
            if match:
                query = match.group(1).strip()
                # Remove quotes if present using compiled pattern
                quote_match = self.quote_pattern.match(query)
                if quote_match:
                    query = quote_match.group(1)
                # Remove brackets if present [detailed, specific, self-contained query]
                query = re.sub(r'^\[.*?\]$', '', query).strip()
                if query and not query.startswith('[') and not query.endswith(']'):
                    queries.append(query)

        self.logger.info(f"Parsed {len(queries)} queries from response")
        return queries

    def parse_responses_file(self, file_path: str) -> List[Dict[str, str]]:
        """Parse query-response pairs from responses file (supports both single and multi-provider formats)."""
        results = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Check if this is a multi-provider format
            if '=== ' in content and ' RESPONSES ===' in content:
                results = self._parse_multi_provider_format(content)
            else:
                results = self._parse_single_provider_format(content)

            self.logger.info(f"Parsed {len(results)} query-response pairs from {file_path}")
            return results

        except Exception as e:
            self.logger.error(f"Error parsing responses file: {e}")
            return []

    def _parse_single_provider_format(self, content: str) -> List[Dict[str, str]]:
        """Parse single provider format."""
        results = []
        sections = content.split('---')

        query_pattern = r'QUERY\s+(\d+):\s*(.+?)(?=\nRESPONSE|\n---|\Z)'
        response_pattern = r'RESPONSE\s+(\d+):\s*(.+?)(?=\n---|\nQUERY|\Z)'

        for section in sections:
            section = section.strip()
            if not section:
                continue

            query_match = re.search(query_pattern, section, re.DOTALL)
            response_match = re.search(response_pattern, section, re.DOTALL)

            if query_match and response_match:
                query_id = query_match.group(1)
                query_text = query_match.group(2).strip()
                response_text = response_match.group(2).strip()

                results.append({
                    'query_id': int(query_id),
                    'query_text': query_text,
                    'response_text': response_text,
                    'provider': 'unknown'
                })

        return results

    def _parse_multi_provider_format(self, content: str) -> List[Dict[str, str]]:
        """Parse multi-provider format."""
        results = []

        # Split by provider sections using compiled pattern
        provider_sections = self.provider_split_pattern.split(content)

        for i in range(1, len(provider_sections), 2):
            if i + 1 < len(provider_sections):
                provider = provider_sections[i].lower()
                provider_content = provider_sections[i + 1]

                # Parse responses within this provider section
                sections = provider_content.split('---')

                for section in sections:
                    section = section.strip()
                    if not section:
                        continue

                    # Use compiled patterns
                    query_match = self.query_pattern.search(section)
                    response_match = self.response_pattern.search(section)

                    if query_match and response_match:
                        query_id = query_match.group(1)
                        query_text = query_match.group(2).strip()
                        response_text = response_match.group(2).strip()

                        results.append({
                            'query_id': int(query_id),
                            'query_text': query_text,
                            'response_text': response_text,
                            'provider': provider
                        })

        return results

    def clean_text(self, text: str) -> str:
        """Clean and normalize text for analysis."""
        if not text:
            return ""

        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def extract_domain_from_url(self, url: str) -> str:
        """Extract domain from URL for matching."""
        if not url:
            return ""

        # Remove protocol
        domain = re.sub(r'^https?://', '', url)
        # Remove www.
        domain = re.sub(r'^www\.', '', domain)
        # Remove path
        domain = domain.split('/')[0]

        return domain.lower()

    def categorize_query_type(self, query: str, business_name: str, query_id: int = None, num_consumer: int = 5) -> str:
        """Categorize query as consumer or business-focused based on position and content."""

        # First, try position-based classification if we have query_id
        if query_id is not None:
            if query_id <= num_consumer:
                return "Consumer"
            else:
                return "Business"

        # Fallback to content-based classification
        query_lower = query.lower()
        business_lower = business_name.lower()

        # If business name is explicitly mentioned, it's business-focused
        if business_lower in query_lower:
            return "Business"

        # Strong business indicators (fleet, company operations, bulk pricing, etc.)
        strong_business_keywords = [
            "fleet", "company", "business", "bulk pricing", "contractor",
            "logistics", "rental fleet", "mining", "construction company",
            "service agreements", "warranty support", "ongoing service",
            "scalable", "ROI", "extended warranty", "refurbishment programs"
        ]

        if any(keyword in query_lower for keyword in strong_business_keywords):
            return "Business"

        # Weaker business indicators that might appear in consumer queries
        weak_business_keywords = [
            "review", "opinion", "think about", "better than", "compare",
            "vs", "versus", "service"
        ]

        # Only classify as business if multiple weak indicators or very specific phrases
        weak_matches = sum(1 for keyword in weak_business_keywords if keyword in query_lower)
        if weak_matches >= 2 or "what do people think about" in query_lower or "is X better than" in query_lower:
            return "Business"

        return "Consumer"