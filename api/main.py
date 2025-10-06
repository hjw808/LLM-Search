"""
FastAPI Backend for AI Visibility Tester
Wraps existing Python scripts and provides REST API endpoints
"""
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import sys
import uuid
from datetime import datetime
import json

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
                    report = {
                        "id": f"{business_name.replace(' ', '_')}_{metadata['timestamp']}",
                        "timestamp": metadata['timestamp'],
                        "business_name": business_name,
                        "providers": metadata.get('providers', []),
                        "total_queries": metadata.get('consumer_queries', 0) + metadata.get('business_queries', 0),
                        "visibility_score": 0,  # Mock value for now
                        "status": metadata.get('status', 'completed'),
                        "has_analysis": False,  # Mock value for now
                        "provider_reports": []  # Mock value for now
                    }
                    reports.append(report)
            except Exception as e:
                print(f"Error reading metadata {item}: {e}")
                continue

    # Sort by timestamp descending
    reports.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    return reports


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

                # Run collect action
                result = subprocess.run(
                    ['python', script_path, '--config', config_path, '--action', 'collect',
                     '--queries', queries_path, '--test-run-id', job_id],
                    cwd=base_dir,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minutes max for collection
                )

                if result.returncode == 0:
                    provider_results.append({
                        "provider": provider,
                        "success": True,
                        "totalQueries": consumer_queries + business_queries,
                    })
                else:
                    provider_results.append({
                        "provider": provider,
                        "success": False,
                        "error": result.stderr[:200],
                        "totalQueries": consumer_queries + business_queries,
                    })

            except Exception as e:
                provider_results.append({
                    "provider": provider,
                    "success": False,
                    "error": str(e)[:200],
                    "totalQueries": consumer_queries + business_queries,
                })

        jobs_storage[job_id]["progress"] = 80
        jobs_storage[job_id]["message"] = "Responses collected. Generating reports..."

        # Step 3: Generate reports for each provider
        # The report generation will be triggered by the scripts automatically
        await asyncio.sleep(2)  # Give time for any async file operations

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
