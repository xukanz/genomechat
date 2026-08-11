# GenomeChat

A full-stack conversational AI platform with multi-agent capabilities for genomics research, data analysis, and code generation. Ask questions in plain language across public variant, association, and annotation databases; the system plans the work, queries the data, runs analysis code, searches the literature, and streams a synthesised answer back.

Built with FastAPI, LangGraph, the Claude Agent SDK, React, and TypeScript.

## 📦 Monorepo Structure

```
genomechat/
├── backend/                     # Platform backend services
│   ├── src/
│   │   ├── agents/              # LangGraph agents (Coordinator, Orchestrator, Coder, SQL Agent)
│   │   │                        #   + SDK variants (coder_sdk, orchestrator_sdk)
│   │   ├── api/                 # FastAPI routes and application
│   │   ├── config/              # Configuration (settings, database registry, agent backends)
│   │   ├── graph/               # LangGraph state and builder
│   │   ├── models/              # Pydantic models
│   │   ├── prompts/             # Agent system prompts (with per-database context)
│   │   ├── service/
│   │   │   ├── database/        # Connections (SQLite, DuckDB, MySQL, Postgres, …)
│   │   │   ├── mcp/             # In-process MCP servers wrapping tools for the SDK
│   │   │   ├── memory/          # Memory pipeline (Phase 0.5, default off)
│   │   │   ├── observability/   # OpenTelemetry tracing + MongoDB exporter
│   │   │   └── sdk_runtime/     # Claude Agent SDK transcript isolation
│   │   ├── tools/               # LangChain tools for agents
│   │   └── utils/               # Utility functions
│   ├── databases/               # Built database artifacts (see Data Sources)
│   ├── scripts/                 # Data preparation, audits, migrations
│   └── tests/                   # Test suite
├── frontend/                    # React + TypeScript SPA
├── sandbox/                     # Python code execution sandbox (separate service)
├── r-sandbox/                   # R code execution sandbox (separate service)
├── docker/                      # Docker Compose files (dev + prod)
└── docs/                        # Documentation
```

## 🧬 Data Sources

Three database profiles ship by default, all built from public genomics resources. Switch between them at runtime from the UI or the API — no restart needed.

| Profile | Source | Storage | License |
|---|---|---|---|
| **clinvar** | [NCBI ClinVar](https://www.ncbi.nlm.nih.gov/clinvar/) variant/condition assertions | SQLite, built locally | Public domain |
| **gwas** | [NHGRI-EBI GWAS Catalog](https://www.ebi.ac.uk/gwas/) associations + studies | Parquet via DuckDB, built locally | CC BY 4.0 |
| **ensembl** | [Ensembl](https://www.ensembl.org/) human core annotation | Live query against the public MySQL mirror | Open |

Build the two local ones before first run:

```bash
cd backend
uv run python scripts/build_genomics_databases.py --download
```

This downloads roughly 500 MB of source files into `backend/databases/_raw/` and produces `databases/clinvar/clinvar.db` (~1.7 GB, 4.5M rows) plus `databases/gwas/*.parquet`. Both the raw downloads and the built artifacts are gitignored — every checkout rebuilds them. The ClinVar build keeps GRCh38 rows only; pass `--clinvar-full` to keep every assembly (roughly double).

Budget about 15 minutes for the first run, most of it download time.

The `ensembl` profile needs no preparation — it queries `ensembldb.ensembl.org:3306` anonymously. Set `DB_REGISTRY_ENSEMBL_ENABLED=false` if you have no outbound access on port 3306.

## 🚀 Key Features

### Multi-Agent System

Built with LangGraph:

- **Coordinator** — routes incoming queries; small talk gets answered directly, real work is handed off
- **Orchestrator** — plans and coordinates multi-step tasks, then synthesises the final answer
- **Coder** — generates and executes Python or R in a sandboxed service
- **SQL Agent** — schema-aware SQL generation with a validation and safety pipeline
- **Summarizer** — compresses long conversations when the context window fills

### Dual Agent Backends

Worker agents can run through either the LangChain factory or the **Claude Agent SDK**, selected per agent by feature flag and defaulting to LangChain:

```bash
CODER_BACKEND=sdk            # route the coder through claude-agent-sdk
ORCHESTRATOR_BACKEND=sdk     # prototype — see docs/backend/phase2_operator_guide.md
```

Both paths share the same system prompts, the same tool surface (MCP-wrapped), and the same failure semantics, so the two are directly comparable. The SDK path requires the `claude` CLI on `PATH`.

### Observability

OpenTelemetry spans for every node, tool call, and LLM request, exported to MongoDB and optionally to Langfuse. Attributes follow the OTel GenAI semantic conventions, so third-party dashboards render them without translation.

```bash
OTEL_ENABLED=true
TRACE_STORAGE_ENABLED=true
```

Then `GET /internal/traces` after a chat turn. Access is tenant-scoped, audited, and rate-limited.

### Context Window Management

Long conversations are summarised automatically at 70% of the model's input window, and stale tool outputs are cleared independently. Configurable via the `CONTEXT_*` settings.

### API Endpoints

#### Authentication (`/auth`)
- `POST /auth/register` — user registration
- `POST /auth/login` — login (OAuth2 password flow)
- `POST /auth/refresh` — refresh access token
- `GET /auth/me` — current user info
- `POST /auth/logout` — logout

#### Chat (`/chat`)
- `POST /chat` — synchronous chat
- `POST /chat/stream` — streaming chat over Server-Sent Events

#### Databases (`/databases`)
- `GET /databases` — list available profiles
- `GET /databases/active` — currently active profile
- `POST /databases/{database_id}/connect` — switch active profile

#### Internal (`/internal`, gated by `INTERNAL_OBSERVABILITY_ENABLED`)
- `GET /internal/traces` — query captured spans
- `GET /internal/health/agent-backends` — which backend each agent resolves to
- `GET /internal/memory` — inspect extracted memories

#### Health
- `GET /health` — health check

### Research Modes

- **Standard** — efficient, direct responses
- **Deep Research** — multi-faceted analysis with iterative deepening and findings passed between agents

### Tools Available to Agents

**Database** — `execute_sql_query`, `execute_sql_query_and_save`, `get_database_schema`, `get_random_subsamples`

**Files** — `list_files_by_thread`, `list_files_by_type`, `read_file_from_s3`, `list_s3_files`

**Code execution** — `execute_code` (Python), `execute_r_code` (R)

## 🛠️ Setup & Development

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Node.js 18+
- MongoDB — required, and not only for checkpoints: user accounts, conversations, projects, reports, and file metadata all live there
- An LLM provider (see Environment Variables)
- Optional: AWS S3 for generated files, the `claude` CLI for the SDK backends, R for the R sandbox

### Backend Setup

```bash
cd backend

# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

uv python pin 3.12
uv sync

cp .env.example .env
# Edit .env — see the required fields below

# Build the local databases (first run only)
uv run python scripts/build_genomics_databases.py --download

uv run python main.py          # http://localhost:8000
```

### Frontend Setup

```bash
cd frontend
npm install
echo "VITE_API_URL=http://localhost:8000" > .env
npm run dev                     # http://localhost:5173
```

### Sandbox Setup

```bash
cd sandbox
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
SANDBOX_JOBS_DIR=./.sandbox_jobs python server.py    # http://localhost:8080
```

`SANDBOX_JOBS_DIR` is only needed outside Docker — in a container the default `/sandbox/jobs` tmpfs mount is used.

### Docker Compose (Full Stack)

```bash
cp backend/.env.example backend/.env
touch sandbox/.env r-sandbox/.env      # compose requires these files to exist
cd docker
docker compose up -d
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- Python sandbox: http://localhost:8080
- R sandbox: http://localhost:8081

MongoDB is **not** part of the compose file — point `MONGODB_CONNECTION_STRING` at a reachable instance.

### Environment Variables

`backend/.env.example` is the authoritative reference and documents every setting. These are required, and the backend will not start without them:

```bash
JWT_SECRET_KEY=...             # python -c 'import secrets; print(secrets.token_urlsafe(32))'
MONGODB_CONNECTION_STRING=mongodb://localhost:27017
```

Plus credentials for whichever LLM provider `backend/src/config/agents.py` targets. `src/service/llm.py` supports direct Anthropic and OpenAI as well as gateway-fronted Azure, Bedrock, and GCP.

### Development Commands

```bash
uv run pytest                              # test suite
uv run pytest --cov=src --cov-report=html  # with coverage
uv run ruff format .                       # format
uv run ruff check --fix .                  # lint
uv run mypy src/                           # type check
```

### CLI Tool

An interactive CLI for testing without the frontend:

```bash
uv run python cli.py                         # streaming, standard mode
uv run python cli.py --no-stream             # clearer errors when debugging
uv run python cli.py --research-mode deep_research
```

Commands: `/help`, `/clear`, `/thread`, `/sync`, `/stream`, `/mode standard|deep`, `/login`, `/register`, `/logout`, `/whoami`, `/exit`.

## 🏗️ Architecture

### Agent Workflow

```
START → Coordinator → Orchestrator → Workers (Coder / SQL Agent) → Orchestrator → End
```

1. **Coordinator** decides whether the query needs the full pipeline
2. **Orchestrator** builds a plan and routes to one worker at a time
3. **Workers** execute and return control to the orchestrator
4. **Orchestrator** synthesises once the plan is complete
5. The response streams to the client over SSE

### State Management

**Backend** — LangGraph checkpoints in MongoDB, thread IDs of the form `{user_id}:{conversation_id}`, and a runtime-switchable database registry. Request-scoped state (active database, agent backend) is carried in `ContextVar`s so concurrent requests never interfere.

**Frontend** — Zustand stores for auth, conversations, projects, databases, artifacts, feedback, reports, snippets, and UI state.

### Streaming

Server-Sent Events carry token-by-token output, plan updates, agent start/end events, tool events, and generated file metadata.

## 🧪 Testing

```bash
cd backend
uv run pytest
uv run pytest tests/test_config/test_database_registry.py -v
```

## 🔒 Security

- JWT authentication with refresh tokens; bcrypt password hashing
- SQL agent validation pipeline: LLM review, DDL rejection, automatic row limits
- Code execution isolated in a separate container — non-root, read-only root filesystem, tmpfs scratch, `no-new-privileges`, PID cap, and per-process resource limits
- Table whitelisting per database profile

## 🙏 Acknowledgments

Built with [LangGraph](https://github.com/langchain-ai/langgraph), the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python), FastAPI, and React.

Data courtesy of [NCBI ClinVar](https://www.ncbi.nlm.nih.gov/clinvar/), the [NHGRI-EBI GWAS Catalog](https://www.ebi.ac.uk/gwas/), and [Ensembl](https://www.ensembl.org/).
