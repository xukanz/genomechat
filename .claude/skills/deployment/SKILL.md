---
name: deployment
description: Kubernetes and Vault deployment specifics for GenomeChat — env-var separator conventions, required secrets, Vault secret mounting, and runtime API URL injection for the frontend. Use when deploying backend, frontend, or sandbox images to Kubernetes, configuring production secrets, or debugging why a deployed service can't reach the backend or read its credentials.
---

# GenomeChat Deployment

Non-obvious deployment constraints. Standard `docker build` / `docker-compose up` usage is
derivable from the Dockerfiles in `backend/`, `frontend/`, `sandbox/`, `r-sandbox/` and the
compose files in `docker/` — this file covers only what those don't tell you.

## Kubernetes Deployment

The application is container-ready for Kubernetes deployment:

1. **Backend Deployment**:
   - Directory: `backend/`
   - Environment variables use semicolon (`;`) separator
   - Required: `OPENAI_AZURE_API_KEY;OPENAI_AZURE_SLUG` (the pre-rename
     `PORTKEY_*` names are still accepted, so existing secrets keep working)
   - Automatic HTTPS/TLS via Kubernetes Ingress

2. **Frontend Deployment**:
   - Directory: `frontend/`
   - API URL supports **runtime injection** (build once, deploy anywhere)
   - Set `VITE_API_URL` at deployment time via environment variable or Vault Secrets

3. **Vault Secrets (Production)**:
   - Set `USE_VAULT_SECRETS=true` in environment variables
   - Secrets mounted at `/secrets/secret.yaml`
   - Secrets override environment variables when both present

**Key Features:**
- 🔒 Automatic HTTPS/TLS via Kubernetes Ingress
- 🔄 Auto-restart on failure
- 🏥 Health probes every ~15 seconds
- 🌐 Configurable CORS via CORS_ORIGINS and the optional CORS_ORIGIN_REGEX
- 🗄️ Vault Secrets support for secure credential management
- 🔄 Runtime API URL injection (no rebuild needed to change backend URL)
