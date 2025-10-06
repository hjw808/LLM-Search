import re
import os
import json
from typing import List, Dict
from collections import Counter
from openai import OpenAI

class CompetitorExtractor:
    """Auto-discover competitors and business names mentioned in AI responses using GPT analysis."""

    def __init__(self, business_name: str, business_aliases: List[str] = None):
        self.business_name = business_name.lower()
        self.business_aliases = [alias.lower() for alias in (business_aliases or [])]
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    def extract_competitors(self, responses: List[str]) -> dict:
        """
        Extract all competitor business names from AI responses using GPT analysis.
        Returns dict with competitor names and their mention counts.
        """
        print("Analyzing responses with GPT to extract competitors...")

        all_competitors = []

        # Analyze each response individually for better accuracy
        for idx, response_text in enumerate(responses, 1):
            if not response_text or not response_text.strip():
                continue

            # Create the analysis prompt for this single response
            analysis_prompt = f"""Review the following AI response and extract ONLY competitor business/brand/company names that were recommended or mentioned.

Target Business (DO NOT include): {self.business_name}
Aliases to exclude: {', '.join(self.business_aliases) if self.business_aliases else 'None'}

Rules for extraction:
- Extract ONLY company/manufacturer/brand names (e.g., "Pedders Suspension", "Old Man Emu", "Bilstein", "Lovells")
- DO NOT extract: product names (e.g., "Trak Ryder", "Foam Cell Pro", "Nitrocharger Sport", "BP-51")
- DO NOT extract: locations (e.g., "Gold Coast", "Melbourne", "Sydney", "Subaru City Perth")
- DO NOT extract: vehicle brands/models (e.g., "Toyota", "Ford Ranger", "Landcruiser")
- DO NOT extract: generic business names or dealers (e.g., "Offroad Townsville", "Lakeside Subaru")
- DO NOT extract: equipment manufacturers unless they are actual suspension brands
- Normalize company names (e.g., "Pedders" and "Pedders Suspension" should be "Pedders Suspension")
- List each competitor only ONCE per response, even if mentioned multiple times

Output ONLY a JSON array of competitor names found in this response.
Format: ["Company Name 1", "Company Name 2"]
If no competitors found, return: []

AI Response to analyze:

{response_text}"""

            try:
                # Call GPT to analyze this single response
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a precise business name extraction assistant. Extract only suspension/automotive company/brand names, not products, dealers, or locations. Output valid JSON only."},
                        {"role": "user", "content": analysis_prompt}
                    ],
                    temperature=0.2,
                    response_format={"type": "json_object"}
                )

                result_text = response.choices[0].message.content
                result_data = json.loads(result_text)

                # Handle both array and object responses
                if isinstance(result_data, dict):
                    # If GPT returned {"competitors": [...]} or similar
                    competitors_in_response = result_data.get('competitors', list(result_data.values())[0] if result_data else [])
                else:
                    competitors_in_response = result_data

                # Add to overall list
                all_competitors.extend(competitors_in_response)

                if idx % 5 == 0:
                    print(f"  Processed {idx}/{len(responses)} responses...")

            except Exception as e:
                print(f"  Error analyzing response {idx}: {e}")
                continue

        # Normalize competitor names before counting
        normalized_competitors = []
        for comp in all_competitors:
            normalized = self._normalize_competitor_name(comp)
            if normalized:
                normalized_competitors.append(normalized)

        # Count occurrences
        competitor_counts = Counter(normalized_competitors)

        # Filter out the target business if it slipped through
        filtered = {
            name: count for name, count in competitor_counts.items()
            if name.lower() != self.business_name and name.lower() not in self.business_aliases
        }

        print(f"GPT extracted {len(filtered)} unique competitors from {len(responses)} responses")
        return dict(sorted(filtered.items(), key=lambda x: x[1], reverse=True))

    def _normalize_competitor_name(self, name: str) -> str:
        """Normalize competitor names to handle common variations."""
        if not name:
            return ""

        name_lower = name.lower().strip()

        # Common normalization patterns
        normalizations = {
            # Dobinsons variations
            'dobinsons': 'Dobinsons',
            'dobinsons 4x4': 'Dobinsons',
            'dobinsons suspension': 'Dobinsons',

            # Old Man Emu variations
            'old man emu': 'Old Man Emu',
            'ome': 'Old Man Emu',
            'old man emu suspension': 'Old Man Emu',

            # Pedders variations
            'pedders': 'Pedders Suspension',
            'pedders suspension': 'Pedders Suspension',
            'pedders suspension & brakes': 'Pedders Suspension',

            # Tough Dog variations
            'tough dog': 'Tough Dog',
            'tough dog suspension': 'Tough Dog',

            # Lovells variations
            'lovells': 'Lovells Suspension',
            'lovells suspension': 'Lovells Suspension',

            # Bilstein variations
            'bilstein': 'Bilstein',

            # Fox variations
            'fox': 'Fox',
            'fox shocks': 'Fox',

            # Rough Country variations
            'rough country': 'Rough Country',
        }

        # Check for exact match
        if name_lower in normalizations:
            return normalizations[name_lower]

        # If no match found, return the original name with title case
        return name.strip()

    def _fallback_extraction(self, responses: List[str]) -> dict:
        """Fallback extraction method if GPT fails - uses simple capitalized word detection."""
        all_candidates = []

        for response in responses:
            # Simple pattern: capitalized multi-word phrases
            pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z0-9][a-z0-9]*)+)\b'
            matches = re.findall(pattern, response)

            for match in matches:
                cleaned = match.strip()
                if (len(cleaned) > 2 and
                    cleaned.lower() != self.business_name and
                    cleaned.lower() not in self.business_aliases):
                    all_candidates.append(cleaned)

        # Count and return
        competitor_counts = Counter(all_candidates)
        return dict(sorted(competitor_counts.items(), key=lambda x: x[1], reverse=True))

    def analyze_competitor_context(self, text: str, competitor: str) -> dict:
        """Analyze the context in which a competitor is mentioned."""
        text_lower = text.lower()
        competitor_lower = competitor.lower()

        # Find the position
        pos = text_lower.find(competitor_lower)
        if pos == -1:
            return {'mentioned': False}

        # Extract surrounding context (100 chars before and after)
        start = max(0, pos - 100)
        end = min(len(text), pos + len(competitor) + 100)
        context = text[start:end]

        # Determine sentiment/recommendation level
        positive_indicators = [
            'recommend', 'best', 'excellent', 'great', 'top', 'quality',
            'reliable', 'trusted', 'popular', 'leading', 'premium'
        ]

        negative_indicators = [
            'avoid', 'not recommend', 'poor', 'bad', 'worst', 'inferior'
        ]

        context_lower = context.lower()
        positive_count = sum(1 for word in positive_indicators if word in context_lower)
        negative_count = sum(1 for word in negative_indicators if word in context_lower)

        if positive_count > negative_count:
            sentiment = 'positive'
        elif negative_count > positive_count:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'

        return {
            'mentioned': True,
            'context': context,
            'sentiment': sentiment,
            'position': 'early' if pos < len(text) / 3 else 'middle' if pos < 2 * len(text) / 3 else 'late'
        }
