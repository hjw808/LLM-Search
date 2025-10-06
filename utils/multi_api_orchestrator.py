import time
import json
import os
from typing import Optional, Dict, Any, List, Union
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from .perplexity_handler import PerplexityHandler
from .openai_handler import OpenAIHandler
from .claude_handler import ClaudeHandler

class MultiAPIOrchestrator:
    """Orchestrator for running queries across multiple AI providers simultaneously."""

    def __init__(self, config: dict):
        """Initialize handlers for all available APIs based on config."""
        self.config = config
        self.handlers = {}
        self.logger = logging.getLogger(__name__)

        # Initialize available handlers based on API keys in config
        self._initialize_handlers()

    def _initialize_handlers(self):
        """Initialize API handlers based on available API keys."""

        # Perplexity (check if enabled)
        if (self.config.get('enable_perplexity', True) and
            'perplexity_api_key' in self.config and self.config['perplexity_api_key']):
            try:
                self.handlers['perplexity'] = PerplexityHandler(
                    api_key=self.config['perplexity_api_key'],
                    model=self.config.get('perplexity_model', 'sonar'),
                    temperature=self.config.get('temperature', 0.7),
                    max_tokens=self.config.get('max_tokens', 4000)
                )
                self.logger.info("Perplexity handler initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize Perplexity handler: {e}")
        elif not self.config.get('enable_perplexity', True):
            self.logger.info("Perplexity disabled in configuration")

        # OpenAI (check if enabled)
        if (self.config.get('enable_openai', True) and
            'openai_api_key' in self.config and self.config['openai_api_key']):
            try:
                self.handlers['openai'] = OpenAIHandler(
                    api_key=self.config['openai_api_key'],
                    model=self.config.get('openai_model', 'gpt-4o-mini'),
                    temperature=self.config.get('temperature', 0.7),
                    max_tokens=self.config.get('max_tokens', 4000)
                )
                self.logger.info("OpenAI handler initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize OpenAI handler: {e}")
        elif not self.config.get('enable_openai', True):
            self.logger.info("OpenAI disabled in configuration")

        # Claude (check if enabled)
        if (self.config.get('enable_claude', True) and
            'claude_api_key' in self.config and self.config['claude_api_key']):
            try:
                self.handlers['claude'] = ClaudeHandler(
                    api_key=self.config['claude_api_key'],
                    model=self.config.get('claude_model', 'claude-3-haiku-20240307'),
                    temperature=self.config.get('temperature', 0.7),
                    max_tokens=self.config.get('max_tokens', 4000)
                )
                self.logger.info("Claude handler initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize Claude handler: {e}")
        elif not self.config.get('enable_claude', True):
            self.logger.info("Claude disabled in configuration")

        if not self.handlers:
            raise ValueError("No API handlers could be initialized. Please check your API keys.")

        self.logger.info(f"Initialized {len(self.handlers)} API handlers: {list(self.handlers.keys())}")

    def get_available_providers(self) -> List[str]:
        """Get list of available providers."""
        return list(self.handlers.keys())

    def generate_queries(self, business_name: str, business_url: str, business_location: str, num_consumer: int, num_business: int, prompt_template: str = None) -> Optional[str]:
        """Generate queries using available handlers with fallback."""
        if not self.handlers:
            self.logger.error("No handlers available")
            return None

        # Try providers in order of preference: perplexity, openai, claude
        provider_order = ['perplexity', 'openai', 'claude']

        for provider_name in provider_order:
            if provider_name in self.handlers:
                handler = self.handlers[provider_name]
                self.logger.info(f"Attempting query generation with {provider_name}")

                try:
                    result = handler.generate_queries(business_name, business_url, business_location, num_consumer, num_business, prompt_template)
                    if result:
                        self.logger.info(f"Successfully generated queries using {provider_name}")
                        return result
                    else:
                        self.logger.warning(f"Query generation failed with {provider_name}, trying next provider")
                except Exception as e:
                    self.logger.warning(f"Error with {provider_name}: {e}, trying next provider")
                    continue

        # If no provider worked, try any remaining handlers
        for provider_name, handler in self.handlers.items():
            if provider_name not in provider_order:
                self.logger.info(f"Attempting query generation with {provider_name} (fallback)")
                try:
                    result = handler.generate_queries(business_name, business_url, business_location, num_consumer, num_business, prompt_template)
                    if result:
                        self.logger.info(f"Successfully generated queries using {provider_name}")
                        return result
                except Exception as e:
                    self.logger.warning(f"Error with {provider_name}: {e}")
                    continue

        self.logger.error("All providers failed for query generation")
        return None

    def get_single_response(self, query: str, provider: str = None) -> Optional[Dict[str, Any]]:
        """Get response from a single provider."""
        if provider and provider in self.handlers:
            handler = self.handlers[provider]
        else:
            # Use first available handler
            handler = next(iter(self.handlers.values()))
            provider = handler.provider

        response = handler.get_ai_response(query)
        return {
            'provider': provider,
            'response_text': response or "ERROR: Failed to get response",
            'timestamp': time.time()
        }

    def get_multiple_responses_single_provider(self, queries: List[str], provider: str, progress_callback=None) -> List[Dict[str, Any]]:
        """Get responses from a single provider for multiple queries."""
        if provider not in self.handlers:
            self.logger.error(f"Provider {provider} not available")
            return []

        handler = self.handlers[provider]
        return handler.get_multiple_responses(queries, progress_callback)

    def get_multiple_responses_all_providers(self, queries: List[str], progress_callback=None) -> Dict[str, List[Dict[str, Any]]]:
        """Get responses from ALL available providers for multiple queries."""
        results = {}

        def process_provider(provider_data):
            provider, handler = provider_data
            self.logger.info(f"Starting {provider} processing...")

            def provider_progress(current, total):
                if progress_callback:
                    progress_callback(provider, current, total)

            try:
                provider_results = handler.get_multiple_responses(queries, provider_progress)
                self.logger.info(f"Completed {provider} processing: {len(provider_results)} responses")
                return provider, provider_results
            except Exception as e:
                self.logger.error(f"Error with {provider}: {e}")
                return provider, []

        # Run all providers in parallel
        with ThreadPoolExecutor(max_workers=len(self.handlers)) as executor:
            future_to_provider = {
                executor.submit(process_provider, item): item[0]
                for item in self.handlers.items()
            }

            for future in as_completed(future_to_provider):
                provider, provider_results = future.result()
                results[provider] = provider_results

        return results

    def get_response_comparison(self, query: str) -> Dict[str, Dict[str, Any]]:
        """Get responses from all providers for a single query for comparison."""
        results = {}

        def get_provider_response(provider_data):
            provider, handler = provider_data
            try:
                response = handler.get_ai_response(query)
                return provider, {
                    'response_text': response or "ERROR: Failed to get response",
                    'timestamp': time.time(),
                    'provider': provider
                }
            except Exception as e:
                self.logger.error(f"Error with {provider}: {e}")
                return provider, {
                    'response_text': f"ERROR: {str(e)}",
                    'timestamp': time.time(),
                    'provider': provider
                }

        # Run all providers in parallel for single query
        with ThreadPoolExecutor(max_workers=len(self.handlers)) as executor:
            future_to_provider = {
                executor.submit(get_provider_response, item): item[0]
                for item in self.handlers.items()
            }

            for future in as_completed(future_to_provider):
                provider, response_data = future.result()
                results[provider] = response_data

        return results

    def get_provider_statistics(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics about available providers."""
        stats = {}
        for provider, handler in self.handlers.items():
            stats[provider] = {
                'model': handler.model,
                'rate_limit_delay': handler.rate_limit_delay,
                'max_concurrent': handler.max_concurrent,
                'available': True
            }
        return stats