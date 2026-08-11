"""FastAPI server for sandboxed R code execution using resource limits.

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
    format="[R-SANDBOX] %(asctime)s - %(levelname)s - %(message)s",
    force=True,
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
for handler in logger.handlers:
    handler.setStream(sys.stderr)

app = FastAPI(title="R Sandboxed Code Runner", version="1.0.0")

# Ensure jobs directory exists at startup
# Defaults to /sandbox/jobs (the tmpfs mount used in Docker); override with
# SANDBOX_JOBS_DIR when running the server directly on a host.
JOBS_DIR = os.getenv("SANDBOX_JOBS_DIR", "/sandbox/jobs")
os.makedirs(JOBS_DIR, exist_ok=True)

# Module-level cache for vault secrets
_vault_secrets_cache: dict[str, Any] | None = None
_vault_secrets_loaded: bool = False


def load_vault_secrets() -> dict[str, Any]:
    """Load secrets from a Vault Secrets YAML file."""
    global _vault_secrets_cache, _vault_secrets_loaded

    if _vault_secrets_loaded:
        return _vault_secrets_cache or {}

    use_vault_secrets = os.getenv("USE_VAULT_SECRETS", "false").lower() == "true"
    if not use_vault_secrets:
        _vault_secrets_loaded = True
        _vault_secrets_cache = {}
        return {}

    secrets_path = Path("/secrets/secret.yaml")
    if not secrets_path.exists():
        logger.warning("[VAULT] /secrets/secret.yaml not found. Using env vars only.")
        _vault_secrets_loaded = True
        _vault_secrets_cache = {}
        return {}

    if yaml is None:
        logger.warning("[VAULT] PyYAML not installed. Cannot load vault secrets.")
        _vault_secrets_loaded = True
        _vault_secrets_cache = {}
        return {}

    try:
        with open(secrets_path, "r", encoding="utf-8") as f:
            secrets = yaml.safe_load(f)

        if not isinstance(secrets, dict) or not secrets:
            _vault_secrets_loaded = True
            _vault_secrets_cache = {}
            return {}

        flat_secrets: dict[str, Any] = {}
        for key, value in secrets.items():
            if isinstance(value, dict):
                for nk, nv in value.items():
                    flat_secrets[f"{key}_{nk}".upper()] = nv
            else:
                flat_secrets[key.upper()] = value

        logger.info(f"[VAULT] Loaded {len(flat_secrets)} secrets")
        _vault_secrets_loaded = True
        _vault_secrets_cache = flat_secrets
        return flat_secrets
    except Exception as e:
        logger.error(f"[VAULT] Failed to load vault secrets: {e}")
        _vault_secrets_loaded = True
        _vault_secrets_cache = {}
        return {}


def get_env_with_vault(key: str, default: str = "") -> str:
    """Get environment variable with Vault Secrets support (vault > env)."""
    vault_secrets = load_vault_secrets()
    for vault_key, vault_value in vault_secrets.items():
        if vault_key.upper() == key.upper():
            return str(vault_value)
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
    files: Optional[Dict[str, str]] = None
    s3_inputs: Optional[List[S3FileRef]] = None
    s3_outputs: Optional[List[S3FileRef]] = None


class RunResponse(BaseModel):
    """Response model for code execution."""

    job_id: str
    exit_code: int
    stdout: str
    stderr: str
    truncated: Optional[dict] = None
    files: Optional[Dict[str, str]] = None
    s3_files: Optional[List[S3FileRef]] = None


def write_job(
    source: str,
    files: Optional[Dict[str, str]] = None,
    s3_inputs: Optional[List[S3FileRef]] = None,
) -> tuple[str, str, str]:
    """Write R source code and optional files to a temporary job directory."""
    os.makedirs(JOBS_DIR, exist_ok=True)
    job_id = str(uuid.uuid4())
    job_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    # Pre-create common output directories
    for subdir in ["outputs", "outputs/plots", "outputs/data", "plots", "results", "figures"]:
        os.makedirs(os.path.join(job_dir, subdir), exist_ok=True)

    # Write main R file
    path = os.path.join(job_dir, "main.R")
    with open(path, "w") as f:
        f.write(source)

    # Copy R helpers to job directory (makes it sourceable)
    r_helpers_path = os.path.join(os.path.dirname(__file__), "r_helpers.R")
    if os.path.exists(r_helpers_path):
        shutil.copy(r_helpers_path, os.path.join(job_dir, "r_helpers.R"))
    else:
        logger.warning("r_helpers.R not found. S3 functions will not be available.")

    # Create S3 info file with input references
    if s3_inputs:
        s3_info = {"inputs": [{"bucket": ref.bucket, "key": ref.key} for ref in s3_inputs]}
        with open(os.path.join(job_dir, "s3_info.json"), "w") as f:
            json.dump(s3_info, f)

    # Write additional files if provided
    if files:
        for filename, base64_content in files.items():
            safe_filename = os.path.basename(filename)
            if safe_filename and safe_filename != "main.R":
                try:
                    file_content = base64.b64decode(base64_content)
                    with open(os.path.join(job_dir, safe_filename), "wb") as f:
                        f.write(file_content)
                except Exception:
                    pass

    return job_id, job_dir, path


def build_cmd(job_dir: str, args: Optional[List[str]]) -> List[str]:
    """Build the command to execute R code."""
    if args is None:
        args = []
    return ["Rscript", "--vanilla", "main.R"] + args


def collect_output_files(job_dir: str) -> Dict[str, str]:
    """Collect output files from job directory and return as base64."""
    output_files: Dict[str, str] = {}
    image_extensions = {".png", ".jpg", ".jpeg", ".svg", ".pdf", ".gif"}
    skip_files = {"main.R", "r_helpers.R", "s3_info.json", "s3_results.json", "Rplots.pdf"}

    # Get S3 file basenames to skip duplicates
    s3_results_path = os.path.join(job_dir, "s3_results.json")
    s3_file_keys: set[str] = set()
    if os.path.exists(s3_results_path):
        try:
            with open(s3_results_path, "r") as f:
                results = json.load(f)
                s3_file_keys = {
                    os.path.basename(ref.get("key", "")) for ref in results.get("created", [])
                }
        except Exception:
            pass

    try:
        for file_path in Path(job_dir).iterdir():
            if file_path.is_file() and file_path.name not in skip_files:
                if file_path.name in s3_file_keys:
                    continue
                if file_path.suffix.lower() in image_extensions or file_path.suffix.lower() == ".csv":
                    try:
                        if file_path.stat().st_size <= 1 * 1024 * 1024:
                            with open(file_path, "rb") as f:
                                output_files[file_path.name] = base64.b64encode(f.read()).decode(
                                    "utf-8"
                                )
                    except Exception:
                        pass
    except Exception:
        pass

    return output_files


def collect_s3_outputs(job_dir: str) -> List[S3FileRef]:
    """Collect S3 file references from s3_results.json."""
    s3_results_path = os.path.join(job_dir, "s3_results.json")
    if os.path.exists(s3_results_path):
        try:
            with open(s3_results_path, "r") as f:
                results = json.load(f)
                return [S3FileRef(**ref) for ref in results.get("created", [])]
        except Exception:
            pass
    return []


def r_exec(
    job_dir: str,
    inner_cmd: List[str],
    stdin_data: str,
    timeout: int = 30,
    mem_mb: int = 2048,
    cpu_seconds: int = 30,
) -> tuple[int, str, str]:
    """Execute R code with resource limits and restricted environment."""
    restricted_env = {
        "PATH": "/usr/bin:/usr/local/bin:/bin",
        "HOME": job_dir,
        "TMPDIR": job_dir,
        # R-specific environment
        "R_LIBS_USER": "",  # Prevent user library loading
        # AWS Credentials for S3 access
        "AWS_ACCESS_KEY_ID": get_env_with_vault("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": get_env_with_vault("AWS_SECRET_ACCESS_KEY", ""),
        "AWS_SESSION_TOKEN": get_env_with_vault("AWS_SESSION_TOKEN", ""),
        "AWS_DEFAULT_REGION": get_env_with_vault("AWS_DEFAULT_REGION", "us-east-1"),
    }

    aws_default_bucket = get_env_with_vault("AWS_DEFAULT_BUCKET", "").strip()
    if aws_default_bucket:
        restricted_env["AWS_DEFAULT_BUCKET"] = aws_default_bucket

    allowed_buckets = get_env_with_vault("ALLOWED_S3_BUCKETS", "").strip()
    if allowed_buckets:
        restricted_env["ALLOWED_S3_BUCKETS"] = allowed_buckets

    def set_limits():
        """Set resource limits for the child process."""
        try:
            # NOTE: RLIMIT_AS not set — R and its libraries need large virtual address space
            print("[RESOURCE] RLIMIT_AS not set (container memory limits apply)", file=sys.stderr, flush=True)

            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
            print(f"[RESOURCE] Set RLIMIT_CPU to {cpu_seconds}s", file=sys.stderr, flush=True)

            resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
            print("[RESOURCE] Set RLIMIT_FSIZE to 50MB", file=sys.stderr, flush=True)

            # R needs more file descriptors than Python (loads many .so files at startup)
            resource.setrlimit(resource.RLIMIT_NOFILE, (512, 512))
            print("[RESOURCE] Set RLIMIT_NOFILE to 512", file=sys.stderr, flush=True)

            try:
                resource.setrlimit(resource.RLIMIT_NPROC, (512, 512))
                print("[RESOURCE] Set RLIMIT_NPROC to 512", file=sys.stderr, flush=True)
            except (ValueError, OSError) as e:
                print(f"[RESOURCE] Could not set RLIMIT_NPROC: {e}", file=sys.stderr, flush=True)
        except (ValueError, OSError) as e:
            print(f"[RESOURCE] Could not set resource limits: {e}", file=sys.stderr, flush=True)

    try:
        proc = subprocess.run(
            inner_cmd,
            input=stdin_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=job_dir,
            timeout=timeout,
            env=restricted_env,
            preexec_fn=set_limits,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        logger.error(f"Job execution timed out after {timeout} seconds")
        return 124, "", "Execution timed out"
    except Exception as e:
        logger.error(f"Job execution failed: {e}", exc_info=True)
        return 1, "", f"Execution error: {str(e)}"


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "r-sandbox",
        "status": "healthy",
        "version": "1.0.0",
        "endpoints": {"health": "/health", "run": "/run"},
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/debug/env")
async def debug_env():
    """Debug endpoint to check environment configuration."""

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
            "AWS_DEFAULT_REGION": os.getenv("AWS_DEFAULT_REGION", "<NOT SET>"),
            "AWS_DEFAULT_BUCKET": os.getenv("AWS_DEFAULT_BUCKET", "<NOT SET>"),
        },
        "sandbox": {
            "SANDBOX_SINGLE_WORKER": os.getenv("SANDBOX_SINGLE_WORKER", "<NOT SET>"),
        },
    }


@app.post("/run", response_model=RunResponse)
async def run_code(req: RunReq) -> RunResponse:
    """Execute R code in a sandboxed environment."""
    timeout = 30
    if req.limits and "wall_ms" in req.limits:
        timeout = max(1, min(60, req.limits["wall_ms"] // 1000))

    mem_mb = 2048
    cpu_seconds = 30
    if req.limits:
        if "mem_mb" in req.limits:
            mem_mb = max(32, min(2048, req.limits["mem_mb"]))
        if "cpu_s" in req.limits:
            cpu_seconds = max(1, min(30, req.limits["cpu_s"]))

    job_id, job_dir, path = write_job(req.source, req.files, req.s3_inputs)
    logger.info(f"[JOB] Starting job {job_id} (timeout={timeout}s, cpu={cpu_seconds}s)")

    try:
        cmd = build_cmd(job_dir, req.args)
        exit_code, stdout, stderr = r_exec(
            job_dir, cmd, req.stdin or "", timeout=timeout, mem_mb=mem_mb, cpu_seconds=cpu_seconds
        )
        logger.info(f"[JOB] Job {job_id} completed with exit_code={exit_code}")
        if stderr:
            logger.warning(f"[JOB] Job {job_id} stderr: {stderr[:1000]}")

        output_files = collect_output_files(job_dir)
        s3_files = collect_s3_outputs(job_dir)
        if s3_files:
            logger.info(f"[JOB] Job {job_id} created {len(s3_files)} S3 file(s)")

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
        try:
            shutil.rmtree(job_dir)
        except Exception:
            pass


if __name__ == "__main__":
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    if log_level == "DEBUG":
        logger.setLevel(logging.DEBUG)

    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": "[R-SANDBOX] %(asctime)s - %(levelname)s - %(message)s"},
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
        },
        "root": {"level": log_level, "handlers": ["default"]},
    }

    vault_secrets = load_vault_secrets()
    if vault_secrets:
        logger.info(f"[STARTUP] Vault Secrets: Loaded {len(vault_secrets)} secrets")

    # Configure workers
    workers_env = get_env_with_vault("UVICORN_WORKERS", "")
    workers = None
    if workers_env:
        try:
            workers = int(workers_env)
        except ValueError:
            workers = None

    if workers is None:
        try:
            import multiprocessing

            workers = multiprocessing.cpu_count()
        except Exception:
            workers = 1

    workers = max(1, min(workers, 32))

    if get_env_with_vault("SANDBOX_SINGLE_WORKER", "").lower() == "true":
        workers = 1
        logger.info("[CONFIG] Single worker mode enabled")

    logger.info(f"[CONFIG] Starting uvicorn with {workers} worker(s) on 0.0.0.0:8081")

    if workers > 1:
        uvicorn.run("server:app", host="0.0.0.0", port=8081, workers=workers, log_config=log_config)
    else:
        uvicorn.run(app, host="0.0.0.0", port=8081, log_config=log_config)
