import time
import json
from typing import Optional, Dict, Any, List
import logging
from concurrent.futures import ThreadPoolExecutor
import threading

# Try using OpenAI library with custom base URL (many providers support this)
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

class OpenAICompatibleHandler:
    """Handler that uses OpenAI library with custom base URL for Perplexity."""

    def __init__(self, api_key: str, model: str = "llama-3.1-sonar-large-128k-online", temperature: float = 0.7, max_tokens: int = 4000):
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI library required for this handler. Install with: pip install openai")

        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.rate_limit_delay = 1.0  # Slower for compatibility
        self.max_concurrent = 1  # Sequential for compatibility

        # Initialize OpenAI client with Perplexity endpoint
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.pplx.ai/v1"
        )

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()

    def generate_response(self, prompt: str, system_message: Optional[str] = None) -> Optional[str]:
        """Generate a response using OpenAI-compatible format."""
        try:
            messages = []
            if system_message:
                messages.append({"role": "system", "content": system_message})
            messages.append({"role": "user", "content": prompt})

            self.logger.info(f"Making OpenAI-compatible request with model {self.model}")

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            # Rate limiting
            time.sleep(self.rate_limit_delay)

            return response.choices[0].message.content

        except openai.AuthenticationError:
            self.logger.error("Authentication failed. Please check your Perplexity API key.")
            return None
        except openai.RateLimitError:
            self.logger.warning("Rate limit exceeded. Waiting 60 seconds...")
            time.sleep(60)
            return self.generate_response(prompt, system_message)
        except openai.APIError as e:
            self.logger.error(f"Perplexity API error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            return None

    def generate_queries(self, business_name: str, business_url: str, num_consumer: int, num_business: int, prompt_template: str = None) -> Optional[str]:
        """Generate queries for business visibility testing."""
        if prompt_template:
            # Use provided template with variable substitution
            prompt = prompt_template.format(
                total_queries=num_consumer + num_business,
                business_name=business_name,
                business_url=business_url,
                num_consumer=num_consumer,
                num_business=num_business
            )
        else:
            # Fallback to simple prompt
            prompt = f"""Generate {num_consumer + num_business} realistic search queries to test AI visibility for {business_name} ({business_url}).

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
        """Get AI response to a query as if the user was asking for help."""
        system_message = "You are a helpful AI assistant. Answer the user's question naturally and helpfully. If relevant businesses come to mind, mention them."

        return self.generate_response(query, system_message)

    def get_multiple_responses(self, queries: List[str], progress_callback=None) -> List[Dict[str, Any]]:
        """Get AI responses for multiple queries sequentially (safer for compatibility)."""
        results = []

        for idx, query in enumerate(queries):
            response = self.get_ai_response(query)
            if progress_callback:
                progress_callback(idx + 1, len(queries))

            results.append({
                'query_id': idx + 1,
                'query_text': query,
                'response_text': response or "ERROR: Failed to get response"
            })

            # Longer delay between requests for compatibility
            if idx < len(queries) - 1:
                time.sleep(2)

        return results