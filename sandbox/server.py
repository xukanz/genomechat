"""FastAPI server for sandboxed Python code execution using resource limits.

Supports optional Vault Secrets via /secrets/secret.yaml.
"""

import base64
import json
import logging
import os
import resource
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

# Configure logging to output to stderr so Docker captures it
logging.basicConfig(
    level=logging.INFO,
    format='[SANDBOX] %(asctime)s - %(levelname)s - %(message)s',
    force=True,  # Force reconfiguration if already configured
    handlers=[
        logging.StreamHandler(sys.stderr)  # Explicitly write to stderr
    ]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# Also ensure all log messages go to stderr
for handler in logger.handlers:
    handler.setStream(sys.stderr)

app = FastAPI(title="Sandboxed Code Runner", version="1.0.0")

# Ensure jobs directory exists at startup
# Defaults to /sandbox/jobs (the tmpfs mount used in Docker); override with
# SANDBOX_JOBS_DIR when running the server directly on a host.
JOBS_DIR = os.getenv("SANDBOX_JOBS_DIR", "/sandbox/jobs")
os.makedirs(JOBS_DIR, exist_ok=True)

# Module-level cache for vault secrets (loaded once per process to avoid log spam)
_vault_secrets_cache: dict[str, Any] | None = None
_vault_secrets_loaded: bool = False


def load_vault_secrets() -> dict[str, Any]:
    """Load secrets from a Vault Secrets YAML file.

    Returns:
        Dictionary of key-value pairs from secret.yaml, or empty dict if not available.

    Note:
        This function checks for USE_VAULT_SECRETS environment variable and
        /secrets/secret.yaml file. If either is missing, returns empty dict.
        Results are cached after first load to avoid repeated file reads and log spam.
    """
    global _vault_secrets_cache, _vault_secrets_loaded

    # Return cached result if already loaded (prevents log spam on repeated calls)
    if _vault_secrets_loaded:
        return _vault_secrets_cache or {}

    use_vault_secrets_env = os.getenv("USE_VAULT_SECRETS", "false")
    use_vault_secrets = use_vault_secrets_env.lower() == "true"

    if not use_vault_secrets:
        logger.debug(f"[VAULT] USE_VAULT_SECRETS is '{use_vault_secrets_env}' (not 'true'), skipping Vault Secrets")
        _vault_secrets_loaded = True
        _vault_secrets_cache = {}
        return {}

    logger.info("[VAULT] USE_VAULT_SECRETS=true, attempting to load secrets from /secrets/secret.yaml")
    
    secrets_path = Path("/secrets/secret.yaml")
    
    if not secrets_path.exists():
        logger.warning(
            "[VAULT] USE_VAULT_SECRETS=true but /secrets/secret.yaml not found. "
            "Falling back to environment variables only."
        )
        _vault_secrets_loaded = True
        _vault_secrets_cache = {}
        return {}

    logger.info(f"[VAULT] Found secret.yaml file at {secrets_path}")

    if yaml is None:
        logger.warning(
            "[VAULT] PyYAML not installed. Cannot load vault secrets. "
            "Install pyyaml to use vault secrets feature."
        )
        _vault_secrets_loaded = True
        _vault_secrets_cache = {}
        return {}
    
    try:
        with open(secrets_path, "r", encoding="utf-8") as f:
            file_content = f.read()
            logger.info(f"[VAULT] Read {len(file_content)} bytes from secret.yaml")

            # NOTE: Never log file content - it contains secrets!
            if not file_content:
                logger.warning("[VAULT] File exists but is completely empty (0 bytes)")
                _vault_secrets_loaded = True
                _vault_secrets_cache = {}
                return {}

            secrets = yaml.safe_load(file_content)

            if secrets is None:
                logger.warning("[VAULT] YAML parsed to None (file may contain only comments or whitespace)")
                _vault_secrets_loaded = True
                _vault_secrets_cache = {}
                return {}

            if not isinstance(secrets, dict):
                # Don't log the actual value - it may contain secrets
                logger.warning(f"[VAULT] YAML parsed but result is not a dict (got {type(secrets).__name__})")
                _vault_secrets_loaded = True
                _vault_secrets_cache = {}
                return {}

            if not secrets:
                logger.warning("[VAULT] secret.yaml parsed successfully but contains no key-value pairs")
                _vault_secrets_loaded = True
                _vault_secrets_cache = {}
                return {}
        
        # Convert to flat dict if nested structure
        if isinstance(secrets, dict):
            # Handle both flat and nested structures
            flat_secrets = {}
            for key, value in secrets.items():
                if isinstance(value, dict):
                    # If nested, flatten with underscore separator
                    for nested_key, nested_value in value.items():
                        flat_secrets[f"{key}_{nested_key}".upper()] = nested_value
                else:
                    flat_secrets[key.upper()] = value
            
            if flat_secrets:
                logger.info(f"[VAULT] Loaded {len(flat_secrets)} secrets from Vault Secrets: {list(flat_secrets.keys())}")
            else:
                logger.warning("[VAULT] No valid secrets found in secret.yaml after parsing")
            _vault_secrets_loaded = True
            _vault_secrets_cache = flat_secrets
            return flat_secrets
        else:
            logger.warning(f"[VAULT] Vault secrets file is not in expected format (got {type(secrets)}, expected dict)")
            _vault_secrets_loaded = True
            _vault_secrets_cache = {}
            return {}
    except yaml.YAMLError as e:
        logger.error(
            f"[VAULT] YAML parsing error in /secrets/secret.yaml: {e}. "
            "Falling back to environment variables only."
        )
        _vault_secrets_loaded = True
        _vault_secrets_cache = {}
        return {}
    except Exception as e:
        logger.error(
            f"[VAULT] Failed to load vault secrets from /secrets/secret.yaml: {e}. "
            "Falling back to environment variables only.",
            exc_info=True
        )
        _vault_secrets_loaded = True
        _vault_secrets_cache = {}
        return {}


def get_env_with_vault(key: str, default: str = "") -> str:
    """Get environment variable with Vault Secrets support.
    
    Priority: Vault Secrets > Environment Variables
    
    Args:
        key: Environment variable name
        default: Default value if not found
        
    Returns:
        Value from vault secrets, environment variable, or default
    """
    vault_secrets = load_vault_secrets()
    
    # Check vault secrets first (case-insensitive)
    for vault_key, vault_value in vault_secrets.items():
        if vault_key.upper() == key.upper():
            return str(vault_value)
    
    # Fall back to environment variable
    return os.getenv(key, default)


class S3FileRef(BaseModel):
    """S3 file reference model."""

    bucket: str
    key: str


class RunReq(BaseModel):
    """Request model for code execution."""

    source: str
    stdin: Optional[str] = ""
    args: Optional[List[str]] = None
    limits: Optional[dict] = None
    files: Optional[Dict[str, str]] = None  # filename -> base64 content
    s3_inputs: Optional[List[S3FileRef]] = None  # S3 files available to code
    s3_outputs: Optional[List[S3FileRef]] = None  # S3 files code should create


class RunResponse(BaseModel):
    """Response model for code execution."""

    job_id: str
    exit_code: int
    stdout: str
    stderr: str
    truncated: Optional[dict] = None
    files: Optional[Dict[str, str]] = None  # filename -> base64 content
    s3_files: Optional[List[S3FileRef]] = None  # S3 files created during execution


def write_job(source: str, files: Optional[Dict[str, str]] = None, 
              s3_inputs: Optional[List[S3FileRef]] = None) -> tuple[str, str, str]:
    """Write Python source code and optional files to a temporary job directory.

    Args:
        source: Python source code to execute
        files: Optional dictionary mapping filename -> base64 content
        s3_inputs: Optional list of S3 file references available to code

    Returns:
        Tuple of (job_id, job_dir, file_path)
    """
    # Ensure jobs directory exists
    os.makedirs(JOBS_DIR, exist_ok=True)
    
    job_id = str(uuid.uuid4())
    job_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    # Pre-create common output directories that LLM-generated code might use
    # This is a safety net - prompt also instructs LLM to create dirs, but this prevents
    # failures if the LLM forgets. These are ephemeral and cleaned up after job completion.
    for subdir in ["outputs", "outputs/plots", "outputs/data", "plots", "results", "figures"]:
        os.makedirs(os.path.join(job_dir, subdir), exist_ok=True)

    # Write main Python file
    path = os.path.join(job_dir, "main.py")
    with open(path, "w") as f:
        f.write(source)
    
    # Copy S3 helpers module to job directory (makes it importable)
    s3_helpers_path = os.path.join(os.path.dirname(__file__), "s3_helpers.py")
    if os.path.exists(s3_helpers_path):
        shutil.copy(s3_helpers_path, os.path.join(job_dir, "s3_helpers.py"))
        logger.info(f"Copied s3_helpers.py to {job_dir}")
    else:
        logger.warning(f"s3_helpers.py not found at {s3_helpers_path}. S3 functions will not be available.")
    
    # Create S3 info file with input references (optional, for code introspection)
    if s3_inputs:
        s3_info = {
            "inputs": [{"bucket": ref.bucket, "key": ref.key} for ref in s3_inputs]
        }
        s3_info_path = os.path.join(job_dir, "s3_info.json")
        with open(s3_info_path, "w") as f:
            json.dump(s3_info, f)
    
    # Write additional files if provided
    if files:
        for filename, base64_content in files.items():
            # Sanitize filename to prevent directory traversal
            safe_filename = os.path.basename(filename)
            if safe_filename and safe_filename != "main.py":
                file_path = os.path.join(job_dir, safe_filename)
                try:
                    file_content = base64.b64decode(base64_content)
                    with open(file_path, "wb") as f:
                        f.write(file_content)
                except Exception:
                    # If file decode fails, skip it
                    pass
    
    return job_id, job_dir, path


def build_cmd(job_dir: str, args: Optional[List[str]]) -> List[str]:
    """Build the command to execute Python code.

    Args:
        job_dir: Job directory path
        args: Optional command-line arguments

    Returns:
        Command list for execution
    """
    if args is None:
        args = []
    # sys.executable, not "python3": the interpreter running this server is the
    # one that has requirements.txt installed. In the Docker image those two
    # happen to be the same, but the documented local dev setup runs the server
    # from .venv while bare "python3" resolves to the system interpreter — which
    # has no matplotlib/numpy/pandas. The agent then either pip-installs them
    # per job into a directory that is deleted right afterwards, or falls back
    # to hand-drawing charts with PIL.
    # Use a relative script path since we set cwd to job_dir.
    return [sys.executable, "main.py"] + args


def set_resource_limits(mem_mb: int = 256, cpu_seconds: int = 3, max_file_size_mb: int = 10, max_files: int = 64):
    """Set resource limits for the current process (will be inherited by child).

    Args:
        mem_mb: Maximum memory in MB
        cpu_seconds: Maximum CPU time in seconds
        max_file_size_mb: Maximum file size in MB
        max_files: Maximum number of open files
    """
    try:
        # RLIMIT_AS: Maximum address space (virtual memory) in bytes
        resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 1024 * 1024, mem_mb * 1024 * 1024))
        
        # RLIMIT_CPU: Maximum CPU time in seconds
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        
        # RLIMIT_FSIZE: Maximum file size in bytes
        resource.setrlimit(resource.RLIMIT_FSIZE, (max_file_size_mb * 1024 * 1024, max_file_size_mb * 1024 * 1024))
        
        # RLIMIT_NOFILE: Maximum number of open file descriptors
        resource.setrlimit(resource.RLIMIT_NOFILE, (max_files, max_files))
    except (ValueError, OSError) as e:
        # If setting limits fails, log but continue (may not have permissions)
        import logging
        logging.warning(f"Could not set resource limits: {e}")


def collect_output_files(job_dir: str) -> Dict[str, str]:
    """Collect output files (images, etc.) from job directory and return as base64.
    
    Only collects files that are NOT reported in s3_results.json.
    Large files (> 1MB) are skipped if they're in S3.
    
    Args:
        job_dir: Job directory to scan for output files
        
    Returns:
        Dictionary mapping job-relative path -> base64 content (only for small
        files not in S3). Paths are relative, e.g. "outputs/plots/chart.png".
    """
    output_files = {}
    image_extensions = {'.png', '.jpg', '.jpeg', '.svg', '.pdf', '.gif'}
    control_files = {"main.py", "s3_helpers.py", "s3_info.json", "s3_results.json"}
    collectable_extensions = image_extensions | {'.csv'}
    
    # Get list of S3 files from s3_results.json
    s3_results_path = os.path.join(job_dir, "s3_results.json")
    s3_file_keys = set()
    if os.path.exists(s3_results_path):
        try:
            with open(s3_results_path, "r") as f:
                results = json.load(f)
                created_files = results.get("created", [])
                # Extract just the filename from S3 keys for comparison
                s3_file_keys = {os.path.basename(f.get("key", "")) for f in created_files}
        except Exception:
            pass
    
    try:
        # rglob, not iterdir: generated plots routinely land in a subdirectory,
        # because the agent is told to read its input from outputs/<name>.csv and
        # writes the chart alongside it under outputs/plots/. A top-level-only
        # scan dropped those files, and the job dir is deleted immediately after,
        # so a successfully rendered chart vanished with no error logged anywhere.
        for file_path in Path(job_dir).rglob("*"):
            if not file_path.is_file() or file_path.name in control_files:
                continue

            relative = file_path.relative_to(job_dir)

            # JOBS_DIR is a relative path, so a job whose CWD is its own directory
            # can end up containing a nested .sandbox_jobs tree. Never let one
            # job's response carry another job's files.
            if ".sandbox_jobs" in relative.parts:
                continue

            # Skip if file is reported in S3
            if file_path.name in s3_file_keys:
                continue

            if file_path.suffix.lower() not in collectable_extensions:
                continue

            try:
                file_size = file_path.stat().st_size
                # Only include small files (< 1MB) for base64 embedding.
                # Large files should be uploaded to S3 instead.
                if file_size > 1 * 1024 * 1024:  # 1MB limit
                    logger.warning(
                        f"[JOB] Not returning {relative}: {file_size} bytes exceeds "
                        f"the 1MB inline limit. Upload it to S3 to keep it."
                    )
                    continue

                with open(file_path, "rb") as f:
                    base64_content = base64.b64encode(f.read()).decode('utf-8')

                # Key by relative path so nested files keep a distinct, meaningful
                # name rather than colliding on basename.
                output_files[relative.as_posix()] = base64_content
            except Exception:
                logger.warning(f"[JOB] Could not read output file {relative}", exc_info=True)
    except Exception:
        logger.warning(f"[JOB] Could not scan {job_dir} for output files", exc_info=True)

    return output_files


def collect_s3_outputs(job_dir: str) -> List[S3FileRef]:
    """Collect information about S3 files created during execution.
    
    This reads from a JSON file (s3_results.json) that the executed code writes
    to report created S3 files.
    
    Args:
        job_dir: Job directory to check for s3_results.json
        
    Returns:
        List of S3FileRef objects representing created S3 files
    """
    s3_results_path = os.path.join(job_dir, "s3_results.json")
    if os.path.exists(s3_results_path):
        try:
            with open(s3_results_path, "r") as f:
                results = json.load(f)
                created_files = results.get("created", [])
                return [S3FileRef(**ref) for ref in created_files]
        except Exception:
            # If JSON parsing fails, return empty list
            pass
    return []


def python_exec(job_dir: str, inner_cmd: List[str], stdin_data: str, timeout: int = 7, 
                mem_mb: int = 256, cpu_seconds: int = 3) -> tuple[int, str, str]:
    """Execute Python code with resource limits and restricted environment.

    Args:
        job_dir: Job directory (working directory for execution)
        inner_cmd: Command to execute (e.g., ["python3", "main.py"])
        stdin_data: Standard input data
        timeout: Execution timeout in seconds (wall-clock time)
        mem_mb: Memory limit in MB
        cpu_seconds: CPU time limit in seconds

    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    # Load Vault Secrets if enabled (for Kubernetes deployment)
    vault_secrets = load_vault_secrets()
    
    # Create restricted environment with AWS credentials for S3 access
    # Priority: Vault Secrets > Environment Variables
    restricted_env = {
        "PATH": "/usr/bin:/bin",
        "HOME": job_dir,
        "TMPDIR": job_dir,
        "PYTHONUNBUFFERED": "1",
        "MPLBACKEND": "Agg",  # Headless matplotlib backend
        # AWS Credentials for S3 access (from vault secrets or env vars)
        "AWS_ACCESS_KEY_ID": get_env_with_vault("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": get_env_with_vault("AWS_SECRET_ACCESS_KEY", ""),
        "AWS_SESSION_TOKEN": get_env_with_vault("AWS_SESSION_TOKEN", ""),
        "AWS_DEFAULT_REGION": get_env_with_vault("AWS_DEFAULT_REGION", "us-east-1"),
    }
    
    # Only include AWS_DEFAULT_BUCKET if it's non-empty (from vault secrets or env vars)
    aws_default_bucket = get_env_with_vault("AWS_DEFAULT_BUCKET", "").strip()
    if aws_default_bucket:
        restricted_env["AWS_DEFAULT_BUCKET"] = aws_default_bucket
        source = "Vault Secrets" if "AWS_DEFAULT_BUCKET" in vault_secrets else "Environment Variable"
        logger.info(f"[ENV] AWS_DEFAULT_BUCKET is set from {source} (length: {len(aws_default_bucket)})")
    else:
        logger.warning("[ENV] AWS_DEFAULT_BUCKET is not set or is empty")
    
    # Only include ALLOWED_S3_BUCKETS if it's non-empty (from vault secrets or env vars)
    allowed_buckets = get_env_with_vault("ALLOWED_S3_BUCKETS", "").strip()
    if allowed_buckets:
        restricted_env["ALLOWED_S3_BUCKETS"] = allowed_buckets
    
    # Define preexec function to set resource limits for child process
    def set_limits():
        """Set resource limits for the child process."""
        # Write to stderr directly so it shows up in Docker logs
        import sys
        try:
            # NOTE: We intentionally do NOT set RLIMIT_AS (virtual address space limit).
            # NumPy, pandas, and matplotlib need to mmap their .so files which requires
            # 3-4GB+ virtual address space even though actual RAM usage is much lower.
            # On Kubernetes, container memory limits (cgroups) provide the real protection.
            # Setting RLIMIT_AS causes "failed to map segment from shared object" errors.
            print("[RESOURCE] RLIMIT_AS not set (container memory limits apply)", file=sys.stderr, flush=True)
            
            # RLIMIT_CPU: Maximum CPU time in seconds
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
            print(f"[RESOURCE] Set RLIMIT_CPU to {cpu_seconds}s", file=sys.stderr, flush=True)
            
            # RLIMIT_FSIZE: Maximum file size in bytes (50 MB for data analysis)
            resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
            print("[RESOURCE] Set RLIMIT_FSIZE to 50MB", file=sys.stderr, flush=True)
            
            # RLIMIT_NOFILE: Maximum number of open file descriptors (increased for S3 operations)
            resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
            print("[RESOURCE] Set RLIMIT_NOFILE to 128", file=sys.stderr, flush=True)
            
            # RLIMIT_NPROC: Maximum number of processes/threads (critical for boto3 SSL operations)
            # boto3/botocore uses threads for SSL and concurrent operations
            try:
                resource.setrlimit(resource.RLIMIT_NPROC, (512, 512))  # Increased to 512
                actual_limit = resource.getrlimit(resource.RLIMIT_NPROC)
                print(f"[RESOURCE] Set RLIMIT_NPROC to 512 (actual: {actual_limit})", file=sys.stderr, flush=True)
            except (ValueError, OSError) as e:
                # RLIMIT_NPROC may not be available on all systems
                print(f"[RESOURCE] Could not set RLIMIT_NPROC: {e}", file=sys.stderr, flush=True)
        except (ValueError, OSError) as e:
            # If setting limits fails, log and continue (may not have permissions)
            print(f"[RESOURCE] Could not set some resource limits: {e}", file=sys.stderr, flush=True)
    
    try:
        # Execute command with resource limits and restricted environment
        proc = subprocess.run(
            inner_cmd,
            input=stdin_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=job_dir,  # Set working directory to job_dir for file system isolation
            timeout=timeout,
            env=restricted_env,
            preexec_fn=set_limits,  # Set resource limits before executing
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        logger.error(f"Job execution timed out after {timeout} seconds")
        return 124, "", "Execution timed out"
    except Exception as e:
        logger.error(f"Job execution failed with exception: {e}", exc_info=True)
        return 1, "", f"Execution error: {str(e)}"


@app.get("/")
async def root():
    """Root endpoint for health checks."""
    return {
        "service": "sandbox",
        "status": "healthy",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "run": "/run"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/debug/env")
async def debug_env():
    """Debug endpoint to check environment configuration.

    Returns sanitized view of critical environment variables.
    """
    def mask_secret(value: str | None) -> str:
        if not value:
            return "<NOT SET>"
        if len(value) <= 8:
            return "****"
        return f"{value[:4]}...{value[-4:]}"

    return {
        "aws": {
            "AWS_ACCESS_KEY_ID": mask_secret(os.getenv("AWS_ACCESS_KEY_ID")),
            "AWS_SECRET_ACCESS_KEY": mask_secret(os.getenv("AWS_SECRET_ACCESS_KEY")),
            "AWS_SESSION_TOKEN": mask_secret(os.getenv("AWS_SESSION_TOKEN")),
            "AWS_DEFAULT_REGION": os.getenv("AWS_DEFAULT_REGION", "<NOT SET>"),
            "AWS_DEFAULT_BUCKET": os.getenv("AWS_DEFAULT_BUCKET", "<NOT SET>"),
            "ALLOWED_S3_BUCKETS": os.getenv("ALLOWED_S3_BUCKETS", "<NOT SET>"),
        },
        "sandbox": {
            "SANDBOX_SINGLE_WORKER": os.getenv("SANDBOX_SINGLE_WORKER", "<NOT SET>"),
        },
        "env_file_hint": "If all AWS vars show <NOT SET>, check that sandbox/.env exists and docker-compose is reading it"
    }


@app.post("/run", response_model=RunResponse)
async def run_code(req: RunReq) -> RunResponse:
    """Execute Python code in a sandboxed environment.

    Args:
        req: Code execution request

    Returns:
        Execution result with stdout, stderr, and exit code

    Raises:
        HTTPException: If execution fails
    """
    # Determine timeout from limits or use default
    timeout = 30  # Increased default for data analysis
    if req.limits and "wall_ms" in req.limits:
        timeout = max(1, min(60, req.limits["wall_ms"] // 1000))  # Clamp between 1-60s

    # Determine resource limits from request or use defaults
    mem_mb = 2048  # Increased for matplotlib plotting + pandas + S3 operations
    cpu_seconds = 30  # Increased for data processing, plotting, and S3 uploads
    if req.limits:
        if "mem_mb" in req.limits:
            mem_mb = max(32, min(2048, req.limits["mem_mb"]))  # Clamp between 32-2048 MB
        if "cpu_s" in req.limits:
            cpu_seconds = max(1, min(30, req.limits["cpu_s"]))  # Clamp between 1-30s
    
    job_id, job_dir, path = write_job(req.source, req.files, req.s3_inputs)
    logger.info(f"[JOB] Starting job {job_id} with mem_mb={mem_mb}, cpu_seconds={cpu_seconds}, timeout={timeout}s")
    logger.info(f"[JOB] S3 inputs: {req.s3_inputs}, S3 outputs: {req.s3_outputs}")
    print(f"[JOB] Starting job {job_id}", file=sys.stderr, flush=True)  # Also print to stderr for Docker
    
    try:
        cmd = build_cmd(job_dir, req.args)
        logger.info(f"[JOB] Command: {' '.join(cmd)}")
        exit_code, stdout, stderr = python_exec(
            job_dir, cmd, req.stdin or "", timeout=timeout, 
            mem_mb=mem_mb, cpu_seconds=cpu_seconds
        )
        logger.info(f"[JOB] Job {job_id} completed with exit_code={exit_code}")
        print(f"[JOB] Job {job_id} completed with exit_code={exit_code}", file=sys.stderr, flush=True)
        if stderr:
            logger.warning(f"[JOB] Job {job_id} stderr: {stderr[:1000]}")
            print(f"[JOB] Job {job_id} stderr: {stderr[:1000]}", file=sys.stderr, flush=True)
        if stdout:
            logger.info(f"[JOB] Job {job_id} stdout: {stdout[:500]}")

        # Collect output files (images, CSV, etc.)
        output_files = collect_output_files(job_dir)
        logger.debug(f"Job {job_id} collected {len(output_files)} output file(s)")
        
        # Collect S3 files created during execution
        s3_files = collect_s3_outputs(job_dir)
        if s3_files:
            logger.info(f"Job {job_id} created {len(s3_files)} S3 file(s): {s3_files}")

        # Cap output size (64 KiB each)
        stdout_capped = stdout[:65536]
        stderr_capped = stderr[:65536]
        truncated = {
            "stdout": len(stdout) > 65536,
            "stderr": len(stderr) > 65536,
        }

        return RunResponse(
            job_id=job_id,
            exit_code=exit_code,
            stdout=stdout_capped,
            stderr=stderr_capped,
            truncated=truncated,
            files=output_files if output_files else None,
            s3_files=s3_files if s3_files else None,
        )
    except Exception as e:
        return RunResponse(
            job_id=job_id,
            exit_code=2,
            stdout="",
            stderr=f"Execution error: {str(e)[:65536]}",
        )
    finally:
        # Cleanup job directory
        try:
            shutil.rmtree(job_dir)
        except Exception:
            pass


if __name__ == "__main__":
    # Check if DEBUG logging is enabled for more verbose vault diagnostics
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    if log_level == "DEBUG":
        logger.setLevel(logging.DEBUG)
        logger.info("[CONFIG] Debug logging enabled")
    
    # Configure uvicorn to use our logging configuration
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "[SANDBOX] %(asctime)s - %(levelname)s - %(message)s",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
        },
        "root": {
            "level": log_level,
            "handlers": ["default"],
        },
    }
    
    # Load vault secrets at startup to verify configuration
    vault_secrets = load_vault_secrets()
    if vault_secrets:
        logger.info(f"[STARTUP] Vault Secrets enabled: Loaded {len(vault_secrets)} secrets")
    else:
        use_vault_env = os.getenv("USE_VAULT_SECRETS", "false")
        if use_vault_env.lower() == "true":
            logger.warning("[STARTUP] USE_VAULT_SECRETS=true but no secrets loaded. Check /secrets/secret.yaml")
        else:
            logger.info("[STARTUP] Vault Secrets disabled (USE_VAULT_SECRETS not set to 'true')")
    
    # Configure workers for production scalability
    # Priority: Environment variable > CPU count detection > Default (1)
    # Kubernetes can set UVICORN_WORKERS environment variable
    workers_env = get_env_with_vault("UVICORN_WORKERS", "")
    if workers_env:
        try:
            workers = int(workers_env)
            logger.info(f"[CONFIG] Using {workers} workers from UVICORN_WORKERS environment variable")
        except ValueError:
            logger.warning(f"[CONFIG] Invalid UVICORN_WORKERS value '{workers_env}', using CPU detection")
            workers = None
    else:
        workers = None
    
    # If not set, detect CPU count (good default for Kubernetes)
    if workers is None:
        try:
            import multiprocessing
            cpu_count = multiprocessing.cpu_count()
            # Use CPU count as workers (optimal for CPU-bound workloads)
            # In Kubernetes with 12 CPUs, this will use 12 workers
            workers = cpu_count
            logger.info(f"[CONFIG] Detected {cpu_count} CPUs, using {workers} workers")
        except Exception as e:
            logger.warning(f"[CONFIG] Could not detect CPU count: {e}, using 1 worker")
            workers = 1
    
    # Ensure workers is at least 1 and reasonable (max 32 to prevent resource exhaustion)
    workers = max(1, min(workers, 32))
    
    # For development, allow single worker mode via vault secrets or environment variable
    single_worker = get_env_with_vault("SANDBOX_SINGLE_WORKER", "").lower()
    if single_worker == "true":
        workers = 1
        logger.info("[CONFIG] Single worker mode enabled (SANDBOX_SINGLE_WORKER=true)")
    
    logger.info(f"[CONFIG] Starting uvicorn with {workers} worker(s) on 0.0.0.0:8080")
    
    # When using multiple workers, uvicorn requires an import string instead of app object
    if workers > 1:
        uvicorn.run(
            "server:app",  # Import string required for multi-worker mode
            host="0.0.0.0", 
            port=8080, 
            workers=workers,
            log_config=log_config
        )
    else:
        uvicorn.run(
            app,  # App object works fine for single worker
            host="0.0.0.0", 
            port=8080, 
            log_config=log_config
        )

