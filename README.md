# AI Visibility Testing Automation

## 🚀 Quick Start

1. **Configure API Keys**:
   ```yaml
   # Edit config.yaml
   perplexity_api_key: "your-perplexity-api-key"
   openai_api_key: "your-openai-api-key"
   claude_api_key: "your-claude-api-key"
   ```

2. **Run the Complete Pipeline**:
   ```bash
   python run_ai_visibility_test.py
   ```

That's it! The system will automatically:
- Generate test queries using selected AI providers
- Collect responses from chosen AI services
- Analyze business mentions and competitor references
- Generate a comprehensive HTML report

## 📋 What It Does

This tool tests how visible your business is across major AI search platforms by:

1. **Generating Realistic Queries**: Creates consumer and business-focused search queries
2. **Multi-Platform Testing**: Queries Perplexity, OpenAI, and Claude (your choice)
3. **Smart Analysis**: Detects business mentions, competitor references, and ranking
4. **Comprehensive Reporting**: Generates detailed HTML reports with insights

## 🎮 Usage Options

### Interactive Mode (Recommended)
```bash
python run_ai_visibility_test.py
```
Select which AI providers to use interactively.

### Automatic Mode
```bash
# Run all enabled providers automatically
python run_ai_visibility_test.py --auto

# Run specific providers only
python run_ai_visibility_test.py --providers openai,claude --auto
python run_ai_visibility_test.py --providers perplexity --auto

# Skip problematic providers (e.g., if Perplexity is blocked)
python run_ai_visibility_test.py --providers openai,claude --auto
```

### Individual Components
```bash
# Generate queries only
python run_ai_visibility_test.py --action generate --providers openai

# Collect responses only (requires existing queries file)
python run_ai_visibility_test.py --action collect --queries "path/to/queries.txt"
```

### Individual Provider Scripts
```bash
# Run each provider separately
python scripts/openai_script.py --action generate
python scripts/claude_script.py --action collect --queries "path/to/queries.txt"
python scripts/perplexity_script.py --action generate
```

## 🔧 Configuration

Edit `config.yaml` to customize:

```yaml
# Business Details
business_name: "Your Business Name"
business_url: "https://yourbusiness.com"

# Query Settings
num_consumer_queries: 10  # Customer-focused queries
num_business_queries: 10  # Business-focused queries

# Provider Settings (enable/disable as needed)
enable_perplexity: true   # Set to false if getting 403 errors
enable_openai: true
enable_claude: true

# API Keys (only required for enabled providers)
perplexity_api_key: "your-key"
openai_api_key: "your-key"
claude_api_key: "your-key"

# Competitors (optional)
competitors:
  - "Competitor 1"
  - "Competitor 2"
```

## 📊 Reports

The tool generates:
- **Query Analysis**: Which queries mentioned your business
- **Provider Comparison**: Performance across different AI platforms
- **Competitor Tracking**: How often competitors are mentioned
- **Visibility Metrics**: Overall visibility scores and trends

## 🛠️ Project Structure

```
ai-visibility-tester/
├── config.yaml                    # Configuration file
├── requirements.txt               # Python dependencies
├── run_ai_visibility_test.py     # Main controller script
├── scripts/
│   ├── openai_script.py          # OpenAI provider only
│   ├── claude_script.py          # Claude provider only
│   ├── perplexity_script.py      # Perplexity provider only
│   └── 4_generate_report.py      # Report generator
├── utils/
│   ├── openai_handler.py         # OpenAI API wrapper
│   ├── claude_handler.py         # Claude API wrapper
│   ├── perplexity_handler.py     # Perplexity API wrapper
│   ├── text_parser.py            # Text parsing utilities
│   └── mention_scanner.py        # Business mention detection
├── prompts/
│   ├── query_generation_prompt.txt
│   ├── enhanced_openai_prompt.txt
│   ├── enhanced_claude_prompt.txt
│   └── standard_perplexity_prompt.txt
└── results/
    └── [business_name]/          # Generated files
```

## 📦 Requirements

```bash
pip install -r requirements.txt
```

## 🔍 Troubleshooting

- **403 Errors from Perplexity**: Use `--providers openai,claude` to skip Perplexity
- **No Providers Available**: Check API keys are set in config.yaml
- **Provider Disabled**: Ensure `enable_X: true` in config.yaml
- **API Rate Limits**: The system includes automatic rate limiting

## 🎯 Use Cases

- **SEO Monitoring**: Track AI search visibility
- **Competitor Analysis**: Compare against competitors
- **Content Strategy**: Understand what triggers AI mentions
- **Brand Monitoring**: Track brand presence in AI responses

## 📈 What Gets Analyzed

- **Business Mention Rate** - How often your business is mentioned
- **Query Type Performance** - Consumer vs business-focused queries
- **Position Analysis** - Where mentions appear in responses
- **Context Analysis** - How your business is described
- **Competitor Tracking** - Which competitors are mentioned alongside you

## 🔧 Advanced Usage

### Custom Configuration
```bash
python run_ai_visibility_test.py --config custom_config.yaml
```

### Generate Combined Report
The system automatically combines results from multiple providers and generates a unified analysis report.

### Individual Provider Analysis
Each provider script can be run independently for focused testing or troubleshooting specific API issues.