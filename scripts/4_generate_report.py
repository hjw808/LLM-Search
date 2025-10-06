#!/usr/bin/env python3

import sys
import os
import pandas as pd
import argparse
import yaml
from datetime import datetime
from jinja2 import Template

# Add utils to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        return {}

def load_analysis_data(analysis_path: str) -> pd.DataFrame:
    """Load analysis data from CSV file."""
    try:
        df = pd.read_csv(analysis_path, encoding='utf-8')
        print(f"Loaded {len(df)} analysis records from {analysis_path}")

        # If this is a raw response CSV, analyze it
        if 'Business_Mentioned' not in df.columns:
            print("Analyzing raw responses for business mentions...")
            df = analyze_responses(df)

        return df
    except Exception as e:
        print(f"Error loading analysis data: {e}")
        sys.exit(1)

def analyze_responses(df: pd.DataFrame) -> pd.DataFrame:
    """Analyze raw responses for business mentions and competitors using GPT."""
    from utils.mention_scanner import MentionScanner
    from utils.competitor_extractor import CompetitorExtractor

    # Load config to get business details
    config_path = 'config.yaml'
    config = load_config(config_path)

    # Initialize mention scanner
    scanner = MentionScanner(
        business_name=config.get('business_name', ''),
        business_url=config.get('business_url', ''),
        business_aliases=config.get('business_aliases', []),
        competitors=config.get('competitors', [])
    )

    # Initialize competitor extractor for GPT-based analysis
    extractor = CompetitorExtractor(
        business_name=config.get('business_name', ''),
        business_aliases=config.get('business_aliases', [])
    )

    # Step 1: Collect all responses for GPT analysis
    print("Step 1: Collecting all responses for GPT competitor analysis...")
    all_response_texts = [str(row.get('Response Text', '')) for _, row in df.iterrows()]

    # Step 2: Use GPT to analyze all responses at once to find competitors
    print("Step 2: Using GPT to analyze competitors across all responses...")
    # Note: extract_competitors now returns the overall counts across all responses
    overall_competitor_counts = extractor.extract_competitors(all_response_texts)
    competitor_names = list(overall_competitor_counts.keys())
    print(f"Found {len(competitor_names)} unique competitors: {', '.join(competitor_names[:5])}{'...' if len(competitor_names) > 5 else ''}")

    # Step 3: For each response, check which competitors are mentioned
    print("Step 3: Mapping competitors to individual responses...")
    business_mentioned = []
    competitors_mentioned = []
    business_position = []

    business_name_lower = config.get('business_name', '').lower()

    for idx, row in df.iterrows():
        response_text = str(row.get('Response Text', ''))
        response_lower = response_text.lower()

        # Check for business mention
        business_scan_result = scanner.scan_for_business_mentions(response_text)
        business_found = business_scan_result.get('mentioned', False)
        business_mentioned.append(business_found)

        # Check which of the discovered competitors are in this specific response
        competitors_in_response = []
        for competitor in competitor_names:
            if competitor.lower() in response_lower:
                competitors_in_response.append(competitor)

        # Also check pre-defined competitors if any
        predefined_competitors = scanner._check_competitors(response_lower)
        all_competitors = list(set(competitors_in_response + predefined_competitors))

        if all_competitors:
            competitors_mentioned.append(';'.join(all_competitors))
        else:
            competitors_mentioned.append('None')

        # Determine position (simplified)
        if business_found and business_name_lower:
            mention_pos = response_lower.find(business_name_lower)
            if mention_pos >= 0 and len(response_lower) > 0:
                relative_pos = mention_pos / len(response_lower)
                if relative_pos < 0.33:
                    business_position.append('Early')
                elif relative_pos < 0.67:
                    business_position.append('Middle')
                else:
                    business_position.append('Late')
            else:
                business_position.append('Not mentioned')
        else:
            business_position.append('Not mentioned')

    # Add the new columns
    df['Business_Mentioned'] = business_mentioned
    df['Competitors_Mentioned'] = competitors_mentioned
    df['Business_Position'] = business_position

    print("Analysis complete!")
    return df


def analyze_provider_performance(df: pd.DataFrame) -> dict:
    """Analyze which AI engines found what companies."""
    provider_analysis = {}

    if 'Provider' in df.columns:
        for provider in df['Provider'].unique():
            provider_data = df[df['Provider'] == provider]

            # Find business mentions
            business_found = provider_data[provider_data['Business_Mentioned'] == True]

            # Get all competitors mentioned by this provider
            all_competitors = []
            for comp_str in provider_data['Competitors_Mentioned'].dropna():
                if comp_str != 'None':
                    all_competitors.extend(comp_str.split(';'))

            provider_analysis[provider] = {
                'business_found_count': len(business_found),
                'total_queries': len(provider_data),
                'competitors_found': list(set(all_competitors)),
                'competitor_frequency': pd.Series(all_competitors).value_counts().to_dict() if all_competitors else {}
            }

    return provider_analysis

def rank_competitors(df: pd.DataFrame) -> dict:
    """Rank competitors by how often they appear across all AI engines."""
    all_competitors = []

    # Collect all competitor mentions
    for comp_str in df['Competitors_Mentioned'].dropna():
        if comp_str != 'None':
            all_competitors.extend(comp_str.split(';'))

    # Count frequency and rank
    if all_competitors:
        competitor_ranking = pd.Series(all_competitors).value_counts().to_dict()
        return competitor_ranking
    return {}


def create_simple_html_report(df: pd.DataFrame, config: dict, provider_analysis: dict, competitor_ranking: dict) -> str:
    """Create simple HTML report focused on basic analysis."""

    # Calculate summary statistics
    total_queries = len(df)
    business_mentioned = len(df[df['Business_Mentioned'] == True])
    mention_rate = (business_mentioned / total_queries * 100) if total_queries > 0 else 0

    html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Visibility Report - {{ config.business_name }}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { max-width: 1000px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; border-bottom: 3px solid #007acc; padding-bottom: 10px; }
        h2 { color: #444; border-bottom: 1px solid #ddd; padding-bottom: 5px; margin-top: 30px; }
        h3 { color: #555; margin-top: 20px; }
        .summary { background: #f9f9f9; padding: 20px; border-radius: 6px; margin: 20px 0; }
        .provider-section { background: #fff; border: 1px solid #ddd; padding: 20px; margin: 15px 0; border-radius: 6px; }
        .found { color: #28a745; font-weight: bold; }
        .not-found { color: #dc3545; font-weight: bold; }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #f8f9fa; font-weight: bold; }
        .rank { font-weight: bold; color: #007acc; }
    </style>
</head>
<body>
    <div class="container">
        <h1>AI Visibility Analysis Report</h1>

        <div class="summary">
            <h2>Summary</h2>
            <p><strong>Business:</strong> {{ config.business_name }}</p>
            <p><strong>Total Queries:</strong> {{ total_queries }}</p>
            <p><strong>Business Found:</strong> <span class="{% if business_mentioned > 0 %}found{% else %}not-found{% endif %}">{{ business_mentioned }} times</span> ({{ "%.1f"|format(mention_rate) }}%)</p>
            <p><strong>Generated:</strong> {{ datetime.now().strftime('%Y-%m-%d %H:%M:%S') }}</p>
        </div>

        <h2>AI Engine Results</h2>

        {% for provider, analysis in provider_analysis.items() %}
        <div class="provider-section">
            <h3>{{ provider|title }} AI Engine</h3>
            <p><strong>Business Found:</strong>
                <span class="{% if analysis.business_found_count > 0 %}found{% else %}not-found{% endif %}">
                    {{ analysis.business_found_count }} out of {{ analysis.total_queries }} queries
                </span>
            </p>

            {% if analysis.competitors_found %}
            <p><strong>Competitors Found:</strong></p>
            <ul>
                {% for competitor in analysis.competitors_found %}
                <li>{{ competitor }}</li>
                {% endfor %}
            </ul>
            {% else %}
            <p><strong>Competitors Found:</strong> None</p>
            {% endif %}
        </div>
        {% endfor %}

        <h2>Competitor Ranking</h2>
        <p>Competitors ranked by how often they appear across all AI engines:</p>

        {% if competitor_ranking %}
        <table>
            <tr>
                <th>Rank</th>
                <th>Competitor</th>
                <th>Total Mentions</th>
            </tr>
            {% for competitor, count in competitor_ranking.items() %}
            <tr>
                <td class="rank">{{ loop.index }}</td>
                <td>{{ competitor }}</td>
                <td>{{ count }}</td>
            </tr>
            {% endfor %}
        </table>
        {% else %}
        <p>No competitors were mentioned by any AI engine.</p>
        {% endif %}

        <div style="margin-top: 40px; text-align: center; color: #666; font-size: 0.9em;">
            <p>Report generated by AI Visibility Testing System</p>
        </div>
    </div>
</body>
</html>
    """

    template = Template(html_template)
    return template.render(
        config=config,
        provider_analysis=provider_analysis,
        competitor_ranking=competitor_ranking,
        mention_rate=mention_rate,
        business_mentioned=business_mentioned,
        total_queries=total_queries,
        datetime=datetime
    )

def main():
    parser = argparse.ArgumentParser(description='Generate simple AI visibility report')
    parser.add_argument('--analysis', required=True, help='Path to analysis CSV file')
    parser.add_argument('--config', default='config.yaml', help='Path to configuration file')
    parser.add_argument('--output', help='Custom output file path')
    parser.add_argument('--test-run-id', help='Test run ID for grouping reports')

    args = parser.parse_args()

    # Load data
    config = load_config(args.config)
    df = load_analysis_data(args.analysis)

    # Save analyzed data with Competitors_Mentioned column if it was added
    if 'Competitors_Mentioned' in df.columns:
        analysis_dir = os.path.dirname(args.analysis)
        analysis_filename = os.path.basename(args.analysis)
        analyzed_filename = analysis_filename.replace('responses', 'analysis')

        # If filename wasn't changed (didn't contain 'responses'), add 'analysis_' prefix
        if analyzed_filename == analysis_filename:
            analyzed_filename = 'analysis_' + analyzed_filename

        analyzed_path = os.path.join(analysis_dir, analyzed_filename)

        try:
            df.to_csv(analyzed_path, index=False, encoding='utf-8')
            print(f"Saved analyzed data to: {analyzed_path}")
        except Exception as e:
            print(f"Warning: Could not save analyzed data: {e}")

    print(f"Generating simple report for {len(df)} queries...")

    # Analyze provider performance
    provider_analysis = analyze_provider_performance(df)
    print(f"Analyzed {len(provider_analysis)} providers")

    # Rank competitors
    competitor_ranking = rank_competitors(df)
    print(f"Ranked {len(competitor_ranking)} competitors")

    # Generate HTML report
    print("Generating simple HTML report...")
    html_content = create_simple_html_report(df, config, provider_analysis, competitor_ranking)

    # Save report
    if args.output:
        report_path = args.output
    else:
        # Generate path based on analysis file
        analysis_dir = os.path.dirname(args.analysis)
        analysis_filename = os.path.basename(args.analysis)

        # If test run ID is provided, include it in the filename
        if args.test_run_id:
            # Extract provider from filename (e.g., openai_responses_...)
            provider_match = analysis_filename.split('_')[0]  # Get first part (provider name)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_filename = f"{provider_match}_responses_testrun_{args.test_run_id}_{timestamp}.html"
        else:
            report_filename = analysis_filename.replace('analysis_', 'report_').replace('.csv', '.html')

        report_path = os.path.join(analysis_dir, report_filename)

    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Simple report saved to: {report_path}")
    except Exception as e:
        print(f"Error saving report: {e}")
        sys.exit(1)

    # Print summary
    total_queries = len(df)
    business_mentioned = len(df[df['Business_Mentioned'] == True])
    mention_rate = (business_mentioned / total_queries * 100) if total_queries > 0 else 0

    print(f"\n=== Simple Report Summary ===")
    print(f"Business: {config.get('business_name', 'Unknown')}")
    print(f"Total Queries: {total_queries}")
    print(f"Business Mentions: {business_mentioned}")
    print(f"Overall Mention Rate: {mention_rate:.1f}%")
    print(f"Competitors Found: {len(competitor_ranking)}")
    print(f"\nSimple report generation completed!")
    print(f"Open the report: {os.path.abspath(report_path)}")

if __name__ == "__main__":
    main()