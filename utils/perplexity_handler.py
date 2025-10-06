import requests
import time
import json
from typing import Optional, Dict, Any, List
import logging
from concurrent.futures import ThreadPoolExecutor
import threading

class PerplexityHandler:
    """Direct HTTP handler for Perplexity API to avoid OpenAI library conflicts."""

    def __init__(self, api_key: str, model: str = "sonar", temperature: float = 0.7, max_tokens: int = 4000):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.rate_limit_delay = 1.5  # Slightly longer delay
        self.max_concurrent = 1  # Sequential for compatibility
        self.base_url = "https://api.pplx.ai/v1/chat/completions"
        self.provider = "perplexity"

        # Load standard prompt
        self.standard_prompt = self._load_standard_prompt()

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()

        # Track failures to avoid spam
        self.consecutive_failures = 0
        self.max_failures = 3
        self.is_blocked = False

    def _load_standard_prompt(self) -> str:
        """Load the standard prompt for Perplexity."""
        try:
            import os
            prompt_path = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'standard_perplexity_prompt.txt')
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            self.logger.warning(f"Could not load standard prompt: {e}")
            return "You are a helpful AI assistant. Answer the user's question naturally and helpfully. If relevant businesses come to mind, mention them."

    def generate_response(self, prompt: str, system_message: Optional[str] = None) -> Optional[str]:
        """Generate a response from Perplexity API with enhanced headers and error handling."""
        # Skip if we're already blocked
        if self.is_blocked:
            self.logger.debug("Skipping Perplexity request - service is blocked")
            return None

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "cross-site",
                "Origin": "https://www.perplexity.ai",
                "Referer": "https://www.perplexity.ai/"
            }

            messages = []
            if system_message:
                messages.append({"role": "system", "content": system_message})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "stream": False
            }

            self.logger.info(f"Making request to {self.base_url} with enhanced headers")

            # Use session for connection reuse
            session = requests.Session()
            session.headers.update(headers)

            response = session.post(
                self.base_url,
                json=payload,
                timeout=120,  # Longer timeout
                verify=True   # Ensure SSL verification
            )

            # Add random delay to avoid bot detection
            import random
            delay = self.rate_limit_delay + random.uniform(0.5, 2.0)
            time.sleep(delay)

            self.logger.info(f"Response status: {response.status_code}")

            if response.status_code == 200:
                # Reset failure count on success
                self.consecutive_failures = 0
                result = response.json()
                if 'choices' in result and len(result['choices']) > 0:
                    return result['choices'][0]['message']['content']
                else:
                    self.logger.error(f"Unexpected response format: {result}")
                    return None
            elif response.status_code == 401:
                self.logger.error("Authentication failed. Please check your Perplexity API key.")
                return None
            elif response.status_code == 403:
                self.consecutive_failures += 1
                if self.consecutive_failures >= self.max_failures:
                    self.is_blocked = True
                    self.logger.warning(f"Perplexity blocked after {self.consecutive_failures} failures - disabling for this session")
                else:
                    self.logger.warning(f"Perplexity access blocked by Cloudflare (failure {self.consecutive_failures}/{self.max_failures})")
                return None
            elif response.status_code == 429:
                self.logger.warning("Rate limit exceeded. Waiting 60 seconds...")
                time.sleep(60)
                return self.generate_response(prompt, system_message)
            else:
                self.logger.error(f"Perplexity API error: {response.status_code}")
                try:
                    error_data = response.json()
                    self.logger.error(f"Error details: {error_data}")
                except:
                    self.logger.error(f"Error response: {response.text[:500]}")
                return None

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request error: {e}")
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
        """Get AI response to a query using standard prompt."""
        return self.generate_response(query, self.standard_prompt)

    def get_multiple_responses(self, queries: List[str], progress_callback=None) -> List[Dict[str, Any]]:
        """Get AI responses for multiple queries with optimized parallel processing."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = []
        batch_size = 5  # Process 5 queries in parallel

        def process_single_query(query_data):
            idx, query = query_data
            response = self.get_ai_response(query)
            return {
                'query_id': idx + 1,
                'query_text': query,
                'response_text': response or "ERROR: Failed to get response",
                'provider': self.provider
            }

        # Process queries in batches to avoid overwhelming the API
        total_processed = 0
        for i in range(0, len(queries), batch_size):
            batch_queries = [(idx, query) for idx, query in enumerate(queries[i:i + batch_size], start=i)]

            with ThreadPoolExecutor(max_workers=min(3, len(batch_queries))) as executor:
                # Submit all queries in the batch
                future_to_query = {executor.submit(process_single_query, query_data): query_data for query_data in batch_queries}

                # Collect results as they complete
                batch_results = []
                for future in as_completed(future_to_query):
                    try:
                        result = future.result()
                        batch_results.append(result)
                        total_processed += 1

                        if progress_callback:
                            progress_callback(total_processed, len(queries))

                        # Short delay to avoid rate limiting
                        time.sleep(0.5)
                    except Exception as e:
                        query_data = future_to_query[future]
                        print(f"Error processing query {query_data[0]}: {e}")
                        batch_results.append({
                            'query_id': query_data[0] + 1,
                            'query_text': query_data[1],
                            'response_text': f"ERROR: {str(e)}",
                            'provider': self.provider
                        })

                # Sort batch results by query_id to maintain order
                batch_results.sort(key=lambda x: x['query_id'])
                results.extend(batch_results)

            # Pause between batches to be respectful to the API
            if i + batch_size < len(queries):
                time.sleep(1)

        return results