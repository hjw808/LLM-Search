#!/usr/bin/env python3
"""
Alternative Perplexity handler using httpx and HTTP/2 to bypass Cloudflare.
"""

import httpx
import asyncio
import time
import random
from typing import Optional, List, Dict, Any
import logging

class PerplexityHandlerAlt:
    def __init__(self, api_key: str, model: str = "llama-3.1-sonar-large-128k-online"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.pplx.ai/v1/chat/completions"
        self.temperature = 0.7
        self.max_tokens = 2000
        self.rate_limit_delay = 1.5
        self.provider = "perplexity"
        self.logger = logging.getLogger(__name__)

    async def generate_response_async(self, prompt: str, system_message: Optional[str] = None) -> Optional[str]:
        """Generate response using httpx with HTTP/2."""
        try:
            # More realistic browser headers
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
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
                "X-Requested-With": "XMLHttpRequest"
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

            # Use HTTP/2 client
            async with httpx.AsyncClient(http2=True, timeout=30.0, verify=False) as client:
                # Add random delay
                await asyncio.sleep(random.uniform(0.5, 2.0))

                response = await client.post(
                    self.base_url,
                    headers=headers,
                    json=payload
                )

                self.logger.info(f"Response status: {response.status_code}")

                if response.status_code == 200:
                    result = response.json()
                    if 'choices' in result and len(result['choices']) > 0:
                        return result['choices'][0]['message']['content']
                    else:
                        self.logger.error(f"Unexpected response format: {result}")
                        return None
                elif response.status_code == 403:
                    self.logger.error("403 Forbidden - Cloudflare protection active")
                    return None
                else:
                    self.logger.error(f"API error {response.status_code}: {response.text}")
                    return None

        except Exception as e:
            self.logger.error(f"Error calling Perplexity API: {e}")
            return None

    def generate_response(self, prompt: str, system_message: Optional[str] = None) -> Optional[str]:
        """Sync wrapper for async method."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.generate_response_async(prompt, system_message))

    def get_ai_response(self, query: str) -> Optional[str]:
        """Get AI response using standard prompt."""
        return self.generate_response(query)

    def get_multiple_responses(self, queries: List[str], progress_callback=None) -> List[Dict[str, Any]]:
        """Get responses with slower, more human-like timing."""
        results = []

        for idx, query in enumerate(queries):
            # Add longer, more random delays
            if idx > 0:
                delay = random.uniform(3, 8)  # 3-8 seconds between requests
                time.sleep(delay)

            response = self.get_ai_response(query)
            if progress_callback:
                progress_callback(idx + 1, len(queries))

            results.append({
                'query_id': idx + 1,
                'query_text': query,
                'response_text': response or "ERROR: Failed to get response",
                'provider': self.provider
            })

        return results