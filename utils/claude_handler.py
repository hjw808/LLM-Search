import time
import json
import os
from typing import Optional, Dict, Any, List
import logging
from concurrent.futures import ThreadPoolExecutor
import threading

# Try using Anthropic library
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

class ClaudeHandler:
    """Handler for Claude API with enhanced business suggestion prompts."""

    def __init__(self, api_key: str, model: str = "claude-3-haiku-20240307", temperature: float = 0.7, max_tokens: int = 4000):
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("Anthropic library required for this handler. Install with: pip install anthropic")

        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.rate_limit_delay = 1.0  # Claude has moderate rate limits
        self.max_concurrent = 2  # Conservative concurrent requests
        self.provider = "claude"

        # Initialize Anthropic client
        self.client = anthropic.Anthropic(api_key=api_key)

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()

        # Load enhanced prompt
        self.enhanced_prompt = self._load_enhanced_prompt()

    def _load_enhanced_prompt(self) -> str:
        """Load the enhanced prompt for Claude."""
        try:
            prompt_path = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'enhanced_claude_prompt.txt')
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            self.logger.warning(f"Could not load enhanced prompt: {e}")
            return "You are a helpful AI assistant. Answer the user's question naturally and helpfully. Please suggest relevant businesses that could help with this query."

    def generate_response(self, prompt: str, system_message: Optional[str] = None) -> Optional[str]:
        """Generate a response using Claude API with enhanced business suggestions."""
        try:
            # Use enhanced prompt as system message if none provided
            if not system_message:
                system_message = self.enhanced_prompt

            self.logger.info(f"Making Claude request with model {self.model}")

            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system_message,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            # Rate limiting
            time.sleep(self.rate_limit_delay)

            return response.content[0].text

        except anthropic.AuthenticationError:
            self.logger.error("Authentication failed. Please check your Claude API key.")
            return None
        except anthropic.RateLimitError:
            self.logger.warning("Rate limit exceeded. Waiting 60 seconds...")
            time.sleep(60)
            return self.generate_response(prompt, system_message)
        except anthropic.APIError as e:
            self.logger.error(f"Claude API error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            return None

    def generate_queries(self, business_name: str, business_url: str, business_location: str, num_consumer: int, num_business: int, prompt_template: str = None) -> Optional[str]:
        """Generate queries for business visibility testing."""
        if prompt_template:
            # Use provided template with variable substitution
            prompt = prompt_template.format(
                total_queries=num_consumer + num_business,
                business_name=business_name,
                business_url=business_url,
                business_location=business_location,
                num_consumer=num_consumer,
                num_business=num_business
            )
        else:
            # Fallback to simple prompt
            prompt = f"""Generate {num_consumer + num_business} realistic search queries to test AI visibility for {business_name} ({business_url}) operating in {business_location}.

Create exactly {num_consumer} consumer-focused queries and {num_business} business-focused queries.

CONSUMER QUERIES ({num_consumer}):
- Questions a customer might ask when they have a problem that {business_name} could solve
- Should NOT mention {business_name} directly
- Should be natural, conversational questions
- Examples: "My car suspension is bouncing on rough roads", "Where can I get quality suspension upgrades?"

BUSINESS QUERIES ({num_business}):
- Questions someone might ask when specifically researching {business_name}
- Can mention the business name or ask for comparisons
- Examples: "What do people think about {business_name}?", "Is {business_name} better than competitors?"

Format your response as a numbered list with exactly {num_consumer + num_business} queries total.
Make sure each query is self-contained and doesn't require additional context."""

        system_message = "You are an expert at generating realistic search queries for business visibility testing. Create diverse, natural queries that real users would ask."

        return self.generate_response(prompt, system_message)

    def get_ai_response(self, query: str) -> Optional[str]:
        """Get AI response to a query using enhanced prompt for business suggestions."""
        # Use the enhanced prompt that encourages business suggestions
        return self.generate_response(query)

    def get_multiple_responses(self, queries: List[str], progress_callback=None) -> List[Dict[str, Any]]:
        """Get AI responses for multiple queries with parallel processing."""
        results = []

        def process_query(query_data):
            idx, query = query_data
            response = self.get_ai_response(query)
            if progress_callback:
                progress_callback(idx + 1, len(queries))
            return {
                'query_id': idx + 1,
                'query_text': query,
                'response_text': response or "ERROR: Failed to get response",
                'provider': self.provider
            }

        # Process queries in batches to respect rate limits
        batch_size = self.max_concurrent

        for i in range(0, len(queries), batch_size):
            batch_queries = list(enumerate(queries[i:i + batch_size], start=i))

            with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
                batch_results = list(executor.map(process_query, batch_queries))
                results.extend(batch_results)

            # Brief pause between batches
            if i + batch_size < len(queries):
                time.sleep(3)  # Longer delay for Claude

        return results