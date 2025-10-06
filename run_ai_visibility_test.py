#!/usr/bin/env python3

import sys
import os
import yaml
import argparse
import subprocess
from datetime import datetime
import time
import glob
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

def run_script(script_name: str, action: str, config_path: str, queries_path: str = None) -> tuple:
    """Run a provider script and return (success, output_path)."""
    script_path = os.path.join(os.path.dirname(__file__), 'scripts', script_name)

    cmd = [sys.executable, script_path, '--config', config_path, '--action', action]
    if queries_path and action == 'collect':
        cmd.extend(['--queries', queries_path])

    try:
        print(f"\n{'='*60}")
        print(f"Running {script_name} - {action}")
        print(f"{'='*60}")

        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        if result.returncode == 0:
            print(result.stdout)

            # Extract output path from stdout
            if 'saved to:' in result.stdout.lower():
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'saved to:' in line.lower():
                        # Extract path after "Saved to: " (case insensitive)
                        lower_line = line.lower()
                        saved_to_index = lower_line.find('saved to:')
                        if saved_to_index >= 0:
                            output_path = line[saved_to_index + len('saved to:'):].strip()
                            # Remove any trailing periods or extra whitespace
                            output_path = output_path.rstrip('.')
                            return True, output_path

            return True, None
        else:
            print(f"Error running {script_name}:")
            print(result.stdout)
            if result.stderr:
                print("STDERR:")
                print(result.stderr)
            return False, None

    except Exception as e:
        print(f"Exception running {script_name}: {e}")
        return False, None

def get_available_providers(config: dict) -> list:
    """Get list of enabled providers based on environment variables."""
    providers = []

    if config.get('enable_openai', True) and os.getenv('OPENAI_API_KEY'):
        providers.append('openai')

    if config.get('enable_claude', True) and os.getenv('CLAUDE_API_KEY'):
        providers.append('claude')

    return providers

def select_providers(available_providers: list) -> list:
    """Interactive provider selection."""
    print("\nAvailable AI Providers:")
    for i, provider in enumerate(available_providers, 1):
        print(f"{i}. {provider.title()}")
    print(f"{len(available_providers) + 1}. All providers")

    while True:
        try:
            choice = input(f"\nSelect providers (1-{len(available_providers) + 1}) or comma-separated numbers: ").strip()

            if choice == str(len(available_providers) + 1):
                return available_providers

            if ',' in choice:
                # Multiple selections
                selections = [int(x.strip()) for x in choice.split(',')]
                selected_providers = []
                for sel in selections:
                    if 1 <= sel <= len(available_providers):
                        selected_providers.append(available_providers[sel - 1])
                    else:
                        raise ValueError(f"Invalid selection: {sel}")
                return selected_providers
            else:
                # Single selection
                selection = int(choice)
                if 1 <= selection <= len(available_providers):
                    return [available_providers[selection - 1]]
                else:
                    raise ValueError(f"Invalid selection: {selection}")

        except (ValueError, IndexError) as e:
            print(f"Invalid input: {e}. Please try again.")

def generate_combined_queries(config: dict, provider_queries: dict) -> str:
    """Combine queries from multiple providers into a single file."""
    output_dir = config.get('output_directory', './results')
    business_name = config['business_name'].replace(' ', '_').replace('/', '_')
    business_dir = os.path.join(output_dir, business_name)
    os.makedirs(business_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    combined_filename = f"combined_queries_{business_name}_{timestamp}.txt"
    combined_path = os.path.join(business_dir, combined_filename)

    all_queries = set()  # Use set to avoid duplicates

    # Read queries from each provider file
    for provider, queries_path in provider_queries.items():
        if queries_path and os.path.exists(queries_path):
            try:
                with open(queries_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#') and not line.startswith('Total queries:'):
                        # Remove numbering if present (handle format like "1. query text")
                        if line and line[0].isdigit() and '. ' in line:
                            # Find the first occurrence of '. ' and take everything after it
                            dot_index = line.find('. ')
                            if dot_index > 0:
                                query = line[dot_index + 2:].strip()
                                if query:
                                    all_queries.add(query)
                        elif line and not line[0].isdigit():
                            # Line without numbering
                            all_queries.add(line)
            except Exception as e:
                print(f"Error reading queries from {provider}: {e}")

    # Convert back to list and sort
    unique_queries = sorted(list(all_queries))

    # Write combined queries
    try:
        with open(combined_path, 'w', encoding='utf-8') as f:
            f.write(f"# Combined Queries for {config['business_name']}\n")
            f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Providers: {', '.join(provider_queries.keys())}\n")
            f.write(f"# Total unique queries: {len(unique_queries)}\n\n")

            for i, query in enumerate(unique_queries, 1):
                f.write(f"{i}. {query}\n")

        print(f"\nCombined {len(unique_queries)} unique queries from {len(provider_queries)} providers")
        print(f"Saved to: {combined_path}")
        return combined_path

    except Exception as e:
        print(f"Error saving combined queries: {e}")
        return None

def find_latest_file(directory: str, pattern: str) -> str:
    """Find the most recent file matching pattern in directory."""
    try:
        files = glob.glob(os.path.join(directory, pattern))
        if files:
            return max(files, key=os.path.getctime)
        return None
    except Exception:
        return None

def generate_combined_report(config: dict, response_files: list) -> None:
    """Generate a combined report from all response files."""
    if not response_files:
        print("No response files to generate report from")
        return

    # Import and run the report generator
    try:
        # Create a temporary combined responses file
        output_dir = config.get('output_directory', './results')
        business_name = config['business_name'].replace(' ', '_').replace('/', '_')
        business_dir = os.path.join(output_dir, business_name)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        combined_csv = os.path.join(business_dir, f"combined_responses_{business_name}_{timestamp}.csv")

        # Combine all CSV files
        import csv
        all_responses = []

        for response_file in response_files:
            if os.path.exists(response_file):
                try:
                    with open(response_file, 'r', newline='', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            all_responses.append(row)
                except Exception as e:
                    print(f"Error reading {response_file}: {e}")

        if all_responses:
            # Write combined CSV
            with open(combined_csv, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ['Query ID', 'Query Text', 'Provider', 'Response Text']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_responses)

            print(f"\nCombined {len(all_responses)} responses into: {combined_csv}")

            # Generate report immediately
            print("\nGenerating analysis report...")
            report_script = os.path.join(os.path.dirname(__file__), 'scripts', '4_generate_report.py')
            cmd = [sys.executable, report_script, '--analysis', combined_csv, '--config', 'config.yaml']

            try:
                result = subprocess.run(cmd, text=True, encoding='utf-8')
                if result.returncode == 0:
                    print("✅ Analysis report generated successfully!")

                    # Find and display the report file
                    report_files = glob.glob(os.path.join(business_dir, f"*report*.html"))
                    if report_files:
                        latest_report = max(report_files, key=os.path.getctime)
                        print(f"📊 Report saved to: {latest_report}")
                        print(f"🌐 Open in browser: file:///{latest_report.replace(os.sep, '/')}")
                else:
                    print("⚠️ Report generation had issues but data collection completed successfully")
            except Exception as e:
                print(f"⚠️ Error running report generator: {e}")
                print("✅ Data collection completed - you can manually run the report generator later")

    except Exception as e:
        print(f"Error generating combined report: {e}")

def main():
    parser = argparse.ArgumentParser(description='Master AI Visibility Testing Controller')
    parser.add_argument('--config', default='config.yaml', help='Path to configuration file')
    parser.add_argument('--action', choices=['generate', 'collect', 'full'], default='full',
                        help='Action to perform: generate queries, collect responses, or full pipeline')
    parser.add_argument('--providers',
                        help='Comma-separated list of providers (perplexity,openai,claude) or "all"')
    parser.add_argument('--queries', help='Path to queries file (for collect action)')
    parser.add_argument('--auto', action='store_true',
                        help='Run automatically with all enabled providers (no interactive selection)')

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Get available providers
    available_providers = get_available_providers(config)

    if not available_providers:
        print("No providers are enabled or have valid API keys configured.")
        print("Please check your config.yaml file.")
        sys.exit(1)

    print(f"Business: {config['business_name']}")
    print(f"Available providers: {', '.join(available_providers)}")

    # Select providers to run
    if args.providers:
        if args.providers.lower() == 'all':
            selected_providers = available_providers
        else:
            requested = [p.strip().lower() for p in args.providers.split(',')]
            selected_providers = [p for p in available_providers if p in requested]
            if not selected_providers:
                print(f"None of the requested providers ({args.providers}) are available.")
                sys.exit(1)
    elif args.auto:
        selected_providers = available_providers
    else:
        selected_providers = select_providers(available_providers)

    print(f"\nSelected providers: {', '.join(selected_providers)}")

    # Provider script mapping
    script_mapping = {
        'openai': 'openai_script.py',
        'claude': 'claude_script.py'
    }

    start_time = time.time()

    if args.action in ['generate', 'full']:
        print(f"\n{'='*80}")
        print("PHASE 1: QUERY GENERATION")
        print(f"{'='*80}")

        provider_queries = {}

        for provider in selected_providers:
            script_name = script_mapping[provider]
            success, queries_path = run_script(script_name, 'generate', args.config)

            if success and queries_path:
                provider_queries[provider] = queries_path
                print(f"[SUCCESS] {provider.title()} query generation completed")
            else:
                print(f"[FAILED] {provider.title()} query generation failed")

        # Generate combined queries file if multiple providers succeeded
        combined_queries_path = None
        if len(provider_queries) > 1:
            combined_queries_path = generate_combined_queries(config, provider_queries)
        elif len(provider_queries) == 1:
            combined_queries_path = list(provider_queries.values())[0]

        if args.action == 'generate':
            total_time = time.time() - start_time
            print(f"\n{'='*80}")
            print(f"QUERY GENERATION COMPLETED in {total_time:.1f} seconds")
            print(f"{'='*80}")

            if combined_queries_path:
                print(f"Use this queries file for collection: {combined_queries_path}")
            return

    if args.action in ['collect', 'full']:
        print(f"\n{'='*80}")
        print("PHASE 2: RESPONSE COLLECTION")
        print(f"{'='*80}")

        # Determine queries file to use
        if args.action == 'collect':
            if args.queries:
                queries_file = args.queries
            else:
                # Try to find the most recent queries file
                output_dir = config.get('output_directory', './results')
                business_name = config['business_name'].replace(' ', '_').replace('/', '_')
                business_dir = os.path.join(output_dir, business_name)

                queries_file = find_latest_file(business_dir, "*queries*.txt")
                if not queries_file:
                    print("No queries file specified and no recent queries file found.")
                    print("Please provide --queries argument or run generate first.")
                    sys.exit(1)
        else:
            # Use combined queries from generation phase
            queries_file = combined_queries_path

        if not queries_file or not os.path.exists(queries_file):
            print(f"Queries file not found: {queries_file}")
            sys.exit(1)

        print(f"Using queries file: {queries_file}")

        response_files = []

        # Run all providers in parallel for faster execution
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def collect_provider_responses(provider):
            script_name = script_mapping[provider]
            success, response_path = run_script(script_name, 'collect', args.config, queries_file)
            return provider, success, response_path

        print(f"Running {len(selected_providers)} providers in parallel...")

        with ThreadPoolExecutor(max_workers=len(selected_providers)) as executor:
            future_to_provider = {
                executor.submit(collect_provider_responses, provider): provider
                for provider in selected_providers
            }

            for future in as_completed(future_to_provider):
                provider, success, response_path = future.result()
                if success and response_path:
                    response_files.append(response_path)
                    print(f"[SUCCESS] {provider.title()} response collection completed")
                else:
                    print(f"[FAILED] {provider.title()} response collection failed")

        # Generate combined report
        if response_files:
            generate_combined_report(config, response_files)

    total_time = time.time() - start_time
    print(f"\n{'='*80}")
    print(f"AI VISIBILITY TESTING COMPLETED in {total_time:.1f} seconds ({total_time/60:.1f} minutes)")
    print(f"Providers: {', '.join(selected_providers)}")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()