"""
FastAPI Backend for AI Visibility Tester
Wraps existing Python scripts and provides REST API endpoints
"""
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import sys
import uuid
from datetime import datetime
import json
import pandas as pd
import glob

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from utils.claude_handler import ClaudeHandler
from utils.openai_handler import OpenAIHandler
from utils.gemini_handler import GeminiHandler
from utils.copilot_handler import CopilotHandler
from utils.text_parser import TextParser

app = FastAPI(title="AI Visibility Tester API", version="1.0.0")

# Configure CORS for Vercel frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://llm-search-frontend-two.vercel.app",
        "https://llm-search-frontend.vercel.app",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",  # Allow all Vercel preview deployments
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for job status (replace with Redis/Database in production)
jobs_storage: Dict[str, Dict[str, Any]] = {}


class TestRunRequest(BaseModel):
    providers: List[str]
    query_types: List[str]
    consumer_queries: int
    business_queries: int
    business_name: Optional[str] = "Fulcrum Suspensions"
    business_url: Optional[str] = None


class TestRunResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatus(BaseModel):
    job_id: str
    status: str  # 'pending', 'running', 'completed', 'failed'
    progress: int  # 0-100
    message: str
    results: Optional[List[Dict[str, Any]]] = None  # Changed from Dict to List
    error: Optional[str] = None


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "AI Visibility Tester API",
        "status": "healthy",
        "version": "1.0.0"
    }


@app.get("/api/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "claude": bool(os.getenv("CLAUDE_API_KEY")),
            "gemini": bool(os.getenv("GEMINI_API_KEY")),
        }
    }


@app.post("/api/test/run", response_model=TestRunResponse)
async def create_test_run(request: TestRunRequest, background_tasks: BackgroundTasks):
    """
    Start a new test run
    Returns job_id immediately, test runs in background
    """
    # Validate providers
    valid_providers = ['openai', 'claude', 'gemini', 'copilot']
    for provider in request.providers:
        if provider not in valid_providers:
            raise HTTPException(status_code=400, detail=f"Invalid provider: {provider}")

    # Generate unique job ID
    job_id = str(uuid.uuid4())

    # Initialize job status
    jobs_storage[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "progress": 0,
        "message": "Test run queued",
        "created_at": datetime.now().isoformat(),
        "results": None,
        "error": None
    }

    # Queue background task
    background_tasks.add_task(
        run_test_background,
        job_id=job_id,
        providers=request.providers,
        query_types=request.query_types,
        consumer_queries=request.consumer_queries,
        business_queries=request.business_queries,
        business_name=request.business_name
    )

    return TestRunResponse(
        job_id=job_id,
        status="pending",
        message="Test run started. Use GET /api/test/status/{job_id} to check progress"
    )


@app.get("/api/test/status/{job_id}", response_model=JobStatus)
async def get_test_status(job_id: str):
    """Get status of a test run"""
    if job_id not in jobs_storage:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatus(**jobs_storage[job_id])


@app.get("/api/reports")
async def list_reports():
    """List all available reports"""
    results_dir = os.path.join(os.path.dirname(__file__), '..', 'results')

    if not os.path.exists(results_dir):
        return []

    # Load config to get business name
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
    business_name = "Unknown Business"
    try:
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            business_name = config.get('business_name', 'Unknown Business')
    except:
        pass

    reports = []

    # Scan for test run metadata files
    for item in os.listdir(results_dir):
        if item.startswith('.test_run_') and item.endswith('.json'):
            metadata_path = os.path.join(results_dir, item)
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)

                    # Transform to frontend format
                    # Use test_run_id as the report ID so it matches the file names
                    report_id = metadata.get('test_run_id', f"{business_name.replace(' ', '_')}_{metadata['timestamp']}")

                    # Find and read analysis CSV to get real metrics
                    analysis_pattern = os.path.join(results_dir, '**', f'*_analysis_testrun_{report_id}*.csv')
                    analysis_files = glob.glob(analysis_pattern, recursive=True)

                    visibility_score = 0
                    business_mentions = 0
                    competitors_found = 0
                    provider_reports = []

                    if analysis_files:
                        try:
                            df = pd.read_csv(analysis_files[0])

                            # Calculate metrics from analysis CSV
                            total_queries = len(df)
                            if total_queries > 0:
                                # Count business mentions using Business_Mentioned column (True/False)
                                if 'Business_Mentioned' in df.columns:
                                    business_mentions = df['Business_Mentioned'].sum()
                                else:
                                    # Fallback: check Response Text column
                                    business_mentions = df['Response Text'].str.contains(business_name, case=False, na=False).sum()

                                visibility_score = int((business_mentions / total_queries) * 100)

                                # Count unique competitors mentioned
                                if 'Competitors_Mentioned' in df.columns:
                                    # Competitors_Mentioned contains comma-separated competitor names
                                    all_competitors = set()
                                    for comp_list in df['Competitors_Mentioned'].dropna():
                                        if comp_list and str(comp_list).strip():
                                            competitors = [c.strip() for c in str(comp_list).split(',')]
                                            all_competitors.update(competitors)
                                    competitors_found = len(all_competitors)

                                # Extract provider from filename
                                filename = os.path.basename(analysis_files[0])
                                provider_match = filename.split('_')[0]  # e.g., "claude" from "claude_analysis_..."

                                provider_reports = [{
                                    "provider": provider_match,
                                    "queries": total_queries,
                                    "business_mentions": int(business_mentions),
                                    "competitors_found": competitors_found,
                                    "visibility_score": visibility_score
                                }]
                        except Exception as e:
                            print(f"Error reading analysis CSV for {report_id}: {e}")

                    report = {
                        "id": report_id,
                        "timestamp": metadata['timestamp'],
                        "business_name": business_name,
                        "providers": metadata.get('providers', []),
                        "total_queries": metadata.get('consumer_queries', 0) + metadata.get('business_queries', 0),
                        "visibility_score": visibility_score,
                        "status": metadata.get('status', 'completed'),
                        "has_analysis": True,
                        "business_mentions": business_mentions,
                        "competitors_found": competitors_found,
                        "provider_reports": provider_reports
                    }
                    reports.append(report)
            except Exception as e:
                print(f"Error reading metadata {item}: {e}")
                continue

    # Sort by timestamp descending
    reports.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    return reports


@app.get("/api/reports/{report_id}/html")
async def get_report_html(report_id: str):
    """Get HTML report for a specific report ID"""
    # Find the HTML report file
    results_dir = os.path.join(os.path.dirname(__file__), '..', 'results')

    # Search for HTML file with this report ID
    html_pattern = os.path.join(results_dir, '**', f'*_report_testrun_{report_id}*.html')
    html_files = glob.glob(html_pattern, recursive=True)

    if not html_files:
        # Try simpler pattern
        html_pattern = os.path.join(results_dir, '**', f'*{report_id}*.html')
        html_files = glob.glob(html_pattern, recursive=True)

    if html_files:
        return FileResponse(html_files[0], media_type='text/html')

    raise HTTPException(status_code=404, detail="HTML report not found")


@app.get("/api/reports/{report_id}/responses")
async def get_report_responses(report_id: str, provider: Optional[str] = None):
    """Get AI responses for a specific report"""
    results_dir = os.path.join(os.path.dirname(__file__), '..', 'results')

    # Find analysis CSV (has competitor data)
    analysis_pattern = os.path.join(results_dir, '**', f'*_analysis_testrun_{report_id}*.csv')
    analysis_files = glob.glob(analysis_pattern, recursive=True)

    if not analysis_files:
        # Fall back to responses CSV
        responses_pattern = os.path.join(results_dir, '**', f'*_responses_testrun_{report_id}*.csv')
        analysis_files = glob.glob(responses_pattern, recursive=True)

    if not analysis_files:
        raise HTTPException(status_code=404, detail="Response data not found")

    # Read CSV and return as JSON
    try:
        df = pd.read_csv(analysis_files[0])

        # Filter by provider if specified
        if provider and 'Provider' in df.columns:
            df = df[df['Provider'].str.lower() == provider.lower()]

        # Replace NaN with None for JSON serialization
        df = df.where(pd.notna(df), None)

        # Convert to list of dicts
        responses = df.to_dict('records')
        return responses
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading responses: {str(e)}")


@app.delete("/api/reports/{report_id}")
async def delete_report(report_id: str):
    """Delete all files associated with a report"""
    results_dir = os.path.join(os.path.dirname(__file__), '..', 'results')

    deleted_files = []

    # Find all files with this test run ID
    patterns = [
        f'*testrun_{report_id}*',
        f'.test_run_{report_id}.json'
    ]

    for pattern in patterns:
        files = glob.glob(os.path.join(results_dir, '**', pattern), recursive=True)
        for file in files:
            try:
                os.remove(file)
                deleted_files.append(file)
            except Exception as e:
                print(f"Error deleting {file}: {e}")

    return {"success": True, "deleted_files": len(deleted_files)}


@app.get("/api/reports/{report_id}/download-responses")
async def download_report_responses(report_id: str, format: str = "csv"):
    """Download responses as CSV or JSON"""
    results_dir = os.path.join(os.path.dirname(__file__), '..', 'results')

    # Find analysis CSV
    analysis_pattern = os.path.join(results_dir, '**', f'*_analysis_testrun_{report_id}*.csv')
    csv_files = glob.glob(analysis_pattern, recursive=True)

    if not csv_files:
        raise HTTPException(status_code=404, detail="Response data not found")

    if format == "csv":
        return FileResponse(csv_files[0], media_type='text/csv',
                          filename=f'responses_{report_id}.csv')
    else:  # json
        df = pd.read_csv(csv_files[0])
        # Replace NaN with None for JSON serialization
        df = df.where(pd.notna(df), None)
        return df.to_dict('records')


@app.get("/api/config")
async def get_config():
    """Get business configuration from config.yaml"""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')

    try:
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        return {
            "name": config.get("business_name", ""),
            "url": config.get("business_url", ""),
            "location": config.get("business_location", "Global"),
            "aliases": config.get("business_aliases", []),
            "queries": {
                "consumer": config.get("num_consumer_queries", 10),
                "business": config.get("num_business_queries", 10)
            }
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Configuration file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading config: {str(e)}")


class ConfigUpdate(BaseModel):
    name: str
    url: str
    location: str
    aliases: List[str]
    queries: Dict[str, int]


@app.post("/api/config")
async def update_config(config: ConfigUpdate):
    """Update business configuration in config.yaml"""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')

    try:
        import yaml
        yaml_config = {
            "business_name": config.name,
            "business_url": config.url,
            "business_location": config.location,
            "business_aliases": config.aliases,
            "num_consumer_queries": config.queries.get("consumer", 10),
            "num_business_queries": config.queries.get("business", 10)
        }

        with open(config_path, 'w') as f:
            yaml.dump(yaml_config, f, default_flow_style=False, indent=2)

        return {"success": True, "message": "Configuration updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving config: {str(e)}")


async def run_test_background(
    job_id: str,
    providers: List[str],
    query_types: List[str],
    consumer_queries: int,
    business_queries: int,
    business_name: str
):
    """
    Background task that runs the actual test
    Executes Python scripts to generate queries, collect responses, and create reports
    """
    try:
        import asyncio
        import subprocess

        # Update status to running
        jobs_storage[job_id]["status"] = "running"
        jobs_storage[job_id]["progress"] = 10
        jobs_storage[job_id]["message"] = "Starting test run..."

        # Paths
        base_dir = os.path.dirname(os.path.dirname(__file__))
        scripts_dir = os.path.join(base_dir, 'scripts')
        config_path = os.path.join(base_dir, 'config.yaml')

        provider_results = []
        queries_paths = {}

        # Step 1: Generate queries for each provider
        jobs_storage[job_id]["progress"] = 15
        jobs_storage[job_id]["message"] = f"Generating queries for {len(providers)} provider(s)..."

        for provider in providers:
            try:
                script_path = os.path.join(scripts_dir, f'{provider}_script.py')
                print(f"Running script: {script_path}")
                print(f"Config path: {config_path}")

                # Check if script exists
                if not os.path.exists(script_path):
                    print(f"Script not found: {script_path}")
                    continue

                # Run generate action
                result = subprocess.run(
                    ['python', script_path, '--config', config_path, '--action', 'generate'],
                    cwd=base_dir,
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                print(f"Generate return code for {provider}: {result.returncode}")
                print(f"Generate stdout: {result.stdout[:500]}")
                print(f"Generate stderr: {result.stderr[:500]}")

                if result.returncode == 0:
                    # Extract queries path from output
                    for line in result.stdout.split('\n'):
                        if 'Saved to:' in line or 'saved to:' in line:
                            queries_path = line.split('to:')[-1].strip().rstrip('.')
                            queries_paths[provider] = queries_path
                            print(f"Found queries path for {provider}: {queries_path}")
                            break
                else:
                    print(f"Error generating queries for {provider}: {result.stderr}")

            except Exception as e:
                print(f"Exception generating queries for {provider}: {e}")
                import traceback
                traceback.print_exc()

        jobs_storage[job_id]["progress"] = 30
        jobs_storage[job_id]["message"] = f"Generated queries for {len(queries_paths)} provider(s). Collecting responses..."

        # Step 2: Collect responses for each provider
        for provider, queries_path in queries_paths.items():
            try:
                script_path = os.path.join(scripts_dir, f'{provider}_script.py')
                print(f"Collecting responses for {provider} from {queries_path}")

                jobs_storage[job_id]["progress"] = 40 + (list(queries_paths.keys()).index(provider) * 30)
                jobs_storage[job_id]["message"] = f"Collecting {provider} responses..."

                # Run collect action
                result = subprocess.run(
                    ['python', script_path, '--config', config_path, '--action', 'collect',
                     '--queries', queries_path, '--test-run-id', job_id],
                    cwd=base_dir,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minutes max for collection
                )

                print(f"Collect return code for {provider}: {result.returncode}")
                print(f"Collect stdout: {result.stdout[:500]}")
                print(f"Collect stderr: {result.stderr[:500]}")

                if result.returncode == 0:
                    provider_results.append({
                        "provider": provider,
                        "success": True,
                        "totalQueries": consumer_queries + business_queries,
                    })
                    print(f"Successfully collected responses for {provider}")
                else:
                    provider_results.append({
                        "provider": provider,
                        "success": False,
                        "error": result.stderr[:200],
                        "totalQueries": consumer_queries + business_queries,
                    })
                    print(f"Failed to collect responses for {provider}: {result.stderr[:200]}")

            except Exception as e:
                print(f"Exception collecting responses for {provider}: {e}")
                import traceback
                traceback.print_exc()
                provider_results.append({
                    "provider": provider,
                    "success": False,
                    "error": str(e)[:200],
                    "totalQueries": consumer_queries + business_queries,
                })

        jobs_storage[job_id]["progress"] = 80
        jobs_storage[job_id]["message"] = "Responses collected. Generating reports..."

        # Step 3: Generate HTML reports for each provider
        results_dir = os.path.join(base_dir, 'results', business_name.replace(' ', '_'))
        report_script = os.path.join(scripts_dir, '4_generate_report.py')

        if os.path.exists(results_dir) and os.path.exists(report_script):
            # Find responses CSV files (not analysis files)
            import glob
            responses_files = glob.glob(os.path.join(results_dir, f'*_responses_testrun_{job_id}*.csv'))

            print(f"Found {len(responses_files)} response files for report generation")
            print(f"Looking in: {results_dir}")
            print(f"Pattern: *_responses_testrun_{job_id}*.csv")

            for responses_file in responses_files:
                try:
                    print(f"Generating report for: {responses_file}")

                    result = subprocess.run(
                        ['python', report_script, '--analysis', responses_file,
                         '--config', config_path, '--test-run-id', job_id],
                        cwd=base_dir,
                        capture_output=True,
                        text=True,
                        timeout=120  # 2 minutes for GPT analysis + report generation
                    )

                    print(f"Report generation return code: {result.returncode}")
                    print(f"Report stdout: {result.stdout[:1000]}")
                    if result.returncode != 0:
                        print(f"Report stderr: {result.stderr[:1000]}")

                except Exception as e:
                    print(f"Exception generating report: {e}")
                    import traceback
                    traceback.print_exc()

        jobs_storage[job_id]["progress"] = 95
        jobs_storage[job_id]["message"] = "Finalizing reports..."

        # Complete
        jobs_storage[job_id]["status"] = "completed"
        jobs_storage[job_id]["progress"] = 100
        jobs_storage[job_id]["message"] = "Test run completed successfully"

        # Format results as array of provider results for frontend compatibility
        provider_results = [
            {
                "provider": provider,
                "success": True,
                "totalQueries": consumer_queries + business_queries,
            }
            for provider in providers
        ]

        jobs_storage[job_id]["results"] = provider_results
        jobs_storage[job_id]["test_run_id"] = job_id
        jobs_storage[job_id]["report_url"] = f"/api/reports/{job_id}"

        # Create a mock metadata file for testing
        results_dir = os.path.join(os.path.dirname(__file__), '..', 'results')
        os.makedirs(results_dir, exist_ok=True)

        metadata_file = os.path.join(results_dir, f'.test_run_{job_id}.json')
        metadata = {
            "test_run_id": job_id,
            "providers": providers,
            "timestamp": datetime.now().isoformat(),
            "total_providers": len(providers),
            "query_types": query_types,
            "consumer_queries": consumer_queries,
            "business_queries": business_queries,
            "status": "completed"
        }

        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

    except Exception as e:
        jobs_storage[job_id]["status"] = "failed"
        jobs_storage[job_id]["progress"] = 0
        jobs_storage[job_id]["message"] = "Test run failed"
        jobs_storage[job_id]["error"] = str(e)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
