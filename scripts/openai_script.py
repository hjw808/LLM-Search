#!/usr/bin/env python3

import sys
import os
import yaml
import argparse
from datetime import datetime
import logging
from dotenv import load_dotenv

# Load environment variables from .env file in parent directory
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(env_path)

# Add utils to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.openai_handler import OpenAIHandler
from utils.text_parser import TextParser

def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

def load_prompt_template(prompt_path: str) -> str:
    """Load prompt template from file."""
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error loading prompt template: {e}")
        sys.exit(1)

def load_queries(queries_path: str) -> list:
    """Load queries from file."""
    try:
        with open(queries_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        queries = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('Total queries:'):
                # Remove numbering if present
                if '. ' in line:
                    query = line.split('. ', 1)[1]
                    queries.append(query)
                elif line:
                    queries.append(line)

        return queries
    except Exception as e:
        print(f"Error loading queries: {e}")
        sys.exit(1)

def generate_queries(config: dict) -> str:
    """Generate queries using OpenAI."""
    # Check if OpenAI is enabled
    if not config.get('enable_openai', True):
        print("OpenAI is disabled in configuration")
        return None

    # Check API key from environment
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("Error: Please set OPENAI_API_KEY in .env file")
        return None

    # Strip any whitespace that might have been added
    api_key = api_key.strip()

    # Initialize OpenAI handler
    try:
        handler = OpenAIHandler(
            api_key=api_key,
            model=config.get('openai_model', 'gpt-4o-mini'),
            temperature=config.get('temperature', 0.7),
            max_tokens=config.get('max_tokens', 4000)
        )
        print("OpenAI handler initialized")
    except Exception as e:
        print(f"Failed to initialize OpenAI handler: {e}")
        return None

    # Load prompt template
    template_path = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'query_generation_prompt.txt')
    prompt_template = load_prompt_template(template_path)

    # Generate queries
    print("Calling OpenAI API for query generation...")
    queries_response = handler.generate_queries(
        business_name=config['business_name'],
        business_url=config['business_url'],
        business_location=config.get('business_location', 'Global'),
        num_consumer=config['num_consumer_queries'],
        num_business=config['num_business_queries'],
        prompt_template=prompt_template
    )

    return queries_response

def collect_responses(config: dict, queries_path: str, test_run_id: str = None) -> str:
    """Collect responses using OpenAI."""
    # Check if OpenAI is enabled
    if not config.get('enable_openai', True):
        print("OpenAI is disabled in configuration")
        return None

    # Check API key from environment
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("Error: Please set OPENAI_API_KEY in .env file")
        return None

    # Strip any whitespace that might have been added
    api_key = api_key.strip()

    # Load queries
    queries = load_queries(queries_path)
    if not queries:
        print("No queries found to process")
        return None

    print(f"Processing {len(queries)} queries with OpenAI...")

    # Initialize OpenAI handler
    try:
        handler = OpenAIHandler(
            api_key=api_key,
            model=config.get('openai_model', 'gpt-4o-mini'),
            temperature=config.get('temperature', 0.7),
            max_tokens=config.get('max_tokens', 4000)
        )
        print("OpenAI handler initialized")
    except Exception as e:
        print(f"Failed to initialize OpenAI handler: {e}")
        return None

    # Progress callback
    def progress_callback(current, total):
        percentage = (current / total) * 100
        print(f"OpenAI progress: {current}/{total} ({percentage:.1f}%)")

    # Get responses
    results = handler.get_multiple_responses(queries, progress_callback)

    if not results:
        print("No responses collected")
        return None

    # Save results
    output_dir = config.get('output_directory', './results')
    business_name = config['business_name'].replace(' ', '_').replace('/', '_')
    business_dir = os.path.join(output_dir, business_name)
    os.makedirs(business_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Include test run ID in filename if provided
    if test_run_id:
        output_filename = f"openai_responses_testrun_{test_run_id}_{timestamp}.csv"
    else:
        output_filename = f"openai_responses_{business_name}_{timestamp}.csv"

    output_path = os.path.join(business_dir, output_filename)

    # Write CSV
    try:
        import csv
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Query ID', 'Query Text', 'Provider', 'Response Text'])

            for result in results:
                writer.writerow([
                    result['query_id'],
                    result['query_text'],
                    result['provider'],
                    result['response_text']
                ])

        print(f"OpenAI responses saved to: {output_path}")
        return output_path
    except Exception as e:
        print(f"Error saving responses: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='OpenAI AI Visibility Testing')
    parser.add_argument('--config', default='config.yaml', help='Path to configuration file')
    parser.add_argument('--action', choices=['generate', 'collect'], required=True,
                        help='Action to perform: generate queries or collect responses')
    parser.add_argument('--queries', help='Path to queries file (required for collect action)')
    parser.add_argument('--test-run-id', help='Test run ID for grouping reports')

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    if args.action == 'generate':
        print(f"Generating queries for: {config['business_name']} using OpenAI")

        queries_response = generate_queries(config)
        if not queries_response:
            print("Failed to generate queries")
            sys.exit(1)

        # Parse and save queries
        parser = TextParser()
        queries = parser.parse_queries_from_response(queries_response)

        if not queries:
            print("Error: No queries were parsed from the response")
            sys.exit(1)

        # Save queries
        output_dir = config.get('output_directory', './results')
        business_name = config['business_name'].replace(' ', '_').replace('/', '_')
        business_dir = os.path.join(output_dir, business_name)
        os.makedirs(business_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        queries_filename = f"openai_queries_{business_name}_{timestamp}.txt"
        queries_path = os.path.join(business_dir, queries_filename)

        with open(queries_path, 'w', encoding='utf-8') as f:
            f.write(f"# OpenAI Queries for {config['business_name']}\n")
            f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Total queries: {len(queries)}\n\n")

            for i, query in enumerate(queries, 1):
                f.write(f"{i}. {query}\n")

        print(f"Generated {len(queries)} queries")
        print(f"Saved to: {queries_path}")

    elif args.action == 'collect':
        if not args.queries:
            print("Error: --queries argument is required for collect action")
            sys.exit(1)

        print(f"Collecting responses for queries from: {args.queries}")

        output_path = collect_responses(config, args.queries, args.test_run_id)
        if not output_path:
            print("Failed to collect responses")
            sys.exit(1)

        print(f"OpenAI collection completed!")
        print(f"Results saved to: {output_path}")

if __name__ == "__main__":
    main()