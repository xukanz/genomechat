# GenomeChat

A full-stack conversational AI platform with multi-agent capabilities for genomics research, data analysis, and code generation. Ask questions in plain language across public variant, association, and annotation databases; the system plans the work, queries the data, runs analysis code, and streams a synthesised answer back.

Built with FastAPI, LangGraph, LangChain, React, and TypeScript.

## 📦 Monorepo Structure

```
genomechat/
├── backend/                     # Platform backend services
│   ├── src/
│   │   ├── agents/              # LangGraph agents (Coordinator, Orchestrator, Coder, SQL Agent)
│   │   ├── api/                 # FastAPI routes and application
│   │   ├── config/              # Configuration (settings, database registry)
│   │   ├── graph/               # LangGraph state and builder
│   │   ├── models/              # Pydantic models
│   │   ├── prompts/             # Agent system prompts (with per-database context)
│   │   ├── service/
│   │   │   ├── database/        # Connections (SQLite, DuckDB, MySQL, Postgres, …)
│   │   │   ├── memory/          # Memory pipeline (Phase 0.5, default off)
│   │   │   └── observability/   # OpenTelemetry tracing + MongoDB exporter
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

Built with LangGraph. Four nodes make up the top-level graph: every request enters at the coordinator, and the worker nodes always hand control back to the orchestrator.

- **Coordinator** — routes incoming queries; small talk gets answered directly, real work is handed off
- **Orchestrator** — plans and coordinates multi-step tasks, then synthesises the final answer
- **Coder** — generates and executes Python or R in a sandboxed service
- **SQL Agent** — schema-aware SQL generation with a validation and safety pipeline

The **Summarizer** is not a node but a `SummarizationMiddleware` on the orchestrator, running on its own (cheaper) model to compress the history when the context window fills.

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
- `GET /databases/{database_id}` — profile detail (type, SQL dialect, domain, example questions)
- `POST /databases/{database_id}/connect` — switch active profile

#### Conversations (`/conversations`)
- `GET /conversations` — list the caller's conversations (optionally filtered by project)
- `GET /conversations/{conversation_id}` — conversation metadata
- `GET /conversations/{conversation_id}/history` — replay the stored message history
- `PATCH /conversations/{conversation_id}` — rename
- `DELETE /conversations/{conversation_id}` — delete

#### Projects (`/projects`)
Projects group conversations, own reusable code snippets, and can be shared with other users.

- `GET /projects` — list owned and shared-with-me projects
- `POST /projects` — create
- `GET|PATCH|DELETE /projects/{project_id}` — read, update, delete (the default project cannot be deleted)
- `POST /projects/{project_id}/conversations/{conversation_id}/move` — move a conversation between projects
- `GET|POST /projects/{project_id}/shares` — list or grant shared access
- `DELETE /projects/{project_id}/shares/{user_id}` — revoke shared access
- `GET|POST /projects/{project_id}/snippets` — list or create snippets injected into the coder prompt
- `PUT|DELETE /projects/{project_id}/snippets/{snippet_id}` — update or delete a snippet
- `PATCH /projects/{project_id}/snippets/{snippet_id}/toggle` — enable/disable without deleting

#### Artifacts (`/artifacts`)
Files produced by the coder and SQL agents, tracked in MongoDB and stored in S3.

- `GET /artifacts` — list generated files (filter by thread, project, file type, or content type; paginated)
- `GET /artifacts/{file_id}/download` — presigned download URL
- `POST /artifacts/batch-download-urls` — presigned URLs for many files at once

#### Reports (`/reports`)
- `GET /reports` — list saved reports
- `POST /reports` — save an assistant answer as a report
- `GET /reports/check?conversation_id=&message_index=` — whether a given message has already been saved
- `GET /reports/conversation/{conversation_id}` — reports saved from one conversation
- `GET|PATCH|DELETE /reports/{report_id}` — read, update, delete

#### Feedback (`/feedback`)
- `POST /feedback` — create or update thumbs up/down on a message
- `GET /feedback/message?conversation_id=&message_index=` — feedback for a single message
- `GET /feedback/conversation/{conversation_id}` — all feedback in a conversation
- `DELETE /feedback/{feedback_id}` — delete by id
- `DELETE /feedback/message/{conversation_id}/{message_index}` — delete by message position

#### Users (`/users`)
- `GET /users/search` — look up users by email or name (used by the project share dialog)
- `PATCH /users/me` — update the caller's profile

#### Internal (`/internal`, gated by `INTERNAL_OBSERVABILITY_ENABLED`)
- `GET /internal/traces` — query captured spans
- `GET /internal/traces/raw` — raw transcript access; reserved for a later phase, currently returns `501`
- `GET /internal/memory` — inspect extracted memories
- `POST /internal/memory/consolidate` — trigger a consolidation pass on demand

#### Health
- `GET /health` — health check
- `GET /health/detailed` — MongoDB and Python-sandbox connectivity plus a redacted config summary; reports `degraded` if either is unreachable

Interactive docs are served at `/docs` (Swagger UI) and `/redoc`.

### Research Modes

- **Standard** — efficient, direct responses
- **Deep Research** — multi-faceted analysis with iterative deepening and findings passed between agents

### Tools Available to Agents

**Database** — `execute_sql_query`, `execute_sql_query_and_save`, `get_database_schema`, `get_random_subsamples`

**Files** — `list_files_by_thread`, `list_files_by_type`, `read_file_from_s3`, `list_s3_files`

**Code execution** — `execute_code` (Python), `execute_r_code` (R)

**Planning** — `manage_plan`, the orchestrator's todo list; its updates are streamed to the UI as plan events

**SQL pipeline** — `execute_sql_pipeline`, used by the agentic SQL graph to generate, validate, and run a query in one call

Not every tool goes to every agent. The coder gets the file and code-execution tools, the orchestrator gets `manage_plan` only, and the SQL agent gets the schema, sampling, and pipeline tools.

## 🛠️ Setup & Development

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Node.js 18+
- MongoDB — required, and not only for checkpoints: user accounts, conversations, projects, reports, and file metadata all live there
- An LLM provider (see Environment Variables)
- Optional: AWS S3 for generated files, R for the R sandbox

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

Built with [LangGraph](https://github.com/langchain-ai/langgraph), [LangChain](https://github.com/langchain-ai/langchain), FastAPI, and React.

Data courtesy of [NCBI ClinVar](https://www.ncbi.nlm.nih.gov/clinvar/), the [NHGRI-EBI GWAS Catalog](https://www.ebi.ac.uk/gwas/), and [Ensembl](https://www.ensembl.org/).
