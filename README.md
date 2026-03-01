# sliderule Prototype

[![Python application](https://github.com/bobwillmot/sliderule/actions/workflows/python-app.yml/badge.svg)](https://github.com/bobwillmot/sliderule/actions/workflows/python-app.yml)
[![codecov](https://codecov.io/gh/bobwillmot/sliderule/branch/main/graph/badge.svg)](https://codecov.io/gh/bobwillmot/sliderule)

Minimal CQRS-aligned, bi-temporal event store on Citus with stored procedures and a FastAPI web front end. Events store non-economic data in a `non_economic_data` column and include a numeric `type_id`. The schema distributes `events` by `book_id`.

## Features

- **Multi-master Insert**: Citus sharded, replicated tables (replication factor 2)
- **Bi-temporal Data**: All entities track both business time (valid_time) and system time (valid_time_start/valid_time_end)
- **Non-economic Data**: Flexible JSONB column for non-standardized fields
- **Point-in-Time Queries**: Query data as of any historical timestamp

## AI Assistance Note

- Prefer the latest GPT Codex model where available when using AI-assisted coding workflows in this repository.

## Documentation Map

- Setup internals and script design rationale: [SETUP.md](SETUP.md)
- Historical interaction log: [summaries/CHAT_SUMMARY.md](summaries/CHAT_SUMMARY.md)
- Refactoring rationale and architectural outcomes: [summaries/REFACTORING_SUMMARY.md](summaries/REFACTORING_SUMMARY.md)

## Quick Start

Complete setup and start everything in one command:

```bash
bash scripts/setup.sh
```

This will:
1. ✓ Check prerequisites (Docker, Python 3)
2. ✓ Create Python virtual environment
3. ✓ Install dependencies
4. ✓ Start Docker Compose services (Citus, CockroachDB, Tempo, Grafana)
5. ✓ Initialize both databases with schema and reference data
6. ✓ Start both APIs (Citus + CockroachDB)
7. ✓ Verify API health checks

### Start both APIs

```bash
bash scripts/start_services.sh &
```

To open both UIs side-by-side in default web browser:

```bash
bash scripts/check_and_open_all_uis.sh
```

This opens:
- **Citus API Docs**: http://localhost:8000/docs
- **CockroachDB API Docs**: http://localhost:8001/docs
  - **Grafana Traces Dashboard**: http://localhost:3000/d/sliderule-traces
  - **Grafana Host Metrics Dashboard**: http://localhost:3000/d/sliderule-host-metrics
  - **Grafana Trace Context Viewer**: http://localhost:3000/d/trace-context-viewer/trace-context-viewer

Clean shutdown (APIs + Docker services):

```bash
bash scripts/shutdown.sh
```

## Prerequisites

- **Docker & Docker Compose**: Required for Citus, CockroachDB, and observability stack
- **Python 3.13+**: For application APIs
- **Git**: For cloning the repository

### macOS Setup via Homebrew (Recommended)

Install all prerequisites via [Homebrew](https://brew.sh):

```bash
# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Docker
brew install docker

# Install Python 3.13
brew install python@3.13

# Verify installation
docker version
python3.13 --version
```

### Windows Setup (WSL2 Recommended)

For Windows, use WSL2 with Ubuntu 22.04+:

```bash
# Install WSL2 and Ubuntu
wsl --install -d Ubuntu-22.04

# Inside WSL2/Ubuntu:
sudo apt-get update
sudo apt-get install -y python3.13 python3.13-venv docker.io docker-compose

# Add user to docker group (avoid sudo)
sudo usermod -aG docker $USER
```

Then follow the same setup steps below.

## Corporate Windows Setup (Access + Versions)

Minimum tested versions for a Windows desktop environment:

- Windows 11 23H2 (or Windows 10 22H2)
- VS Code 1.86+ (stable)
- Git 2.44+
- Docker Desktop 4.28+ (WSL2 backend)
- WSL2 with Ubuntu 22.04+ (recommended for Docker and Python tooling)

VS Code extensions to install:

- `ms-python.python`
- `ms-python.vscode-pylance`
- `ms-azuretools.vscode-docker`
- `GitHub.vscode-pull-request-github`
- `GitHub.copilot`
- `GitHub.copilot-chat` (optional)
- `ms-vscode-remote.remote-wsl` (if using WSL2)

Corporate access requirements (common):

- GitHub access via SSO or PAT with repo read/write as needed
- Docker registry access for Docker Hub or an internal registry
- Proxy/cert setup for HTTPS inspection (install corporate CA into Windows, WSL, and Docker)
- Allowlist outbound domains if required: `github.com`, `api.github.com`, `objects.githubusercontent.com`,
  `pypi.org`, `files.pythonhosted.org`, `docker.io`, `registry-1.docker.io`

## Setup

For setup script internals and design rationale, see [SETUP.md](SETUP.md).

### Complete Setup (Recommended)

One command to set everything up:

```bash
bash scripts/setup.sh
```

This will:
1. Check all prerequisites
2. Create and activate Python virtual environment
3. Install Python dependencies
4. Start Docker Compose services
5. Wait for services to be healthy
6. Initialize databases for both Citus and CockroachDB
7. Load schemas and reference data
8. Start both APIs automatically
9. Run API health checks


### Restart Both APIs (If Needed)

```bash
bash scripts/start_services.sh &
```

This restarts:
- **Citus API** on http://localhost:8000
- **CockroachDB API** on http://localhost:8001

Both will be sending traces to Grafana (Tempo).

### Start Individual APIs

If you only need one backend:

```bash
# Citus only
export PYTHONPATH=.
.venv/bin/uvicorn app_citus.main:app --host 127.0.0.1 --port 8000

# CockroachDB only
export PYTHONPATH=.
export DATABASE_URL_COCKROACH=postgresql://root@localhost:26257/sliderule?sslmode=disable
.venv/bin/uvicorn app_cockroachdb.main:app --host 127.0.0.1 --port 8001
```

### Development Mode (with Auto-Reload)

For development with auto-reload on code changes:

```bash
export PYTHONPATH=.
.venv/bin/uvicorn app_citus.main:app --reload --host 127.0.0.1 --port 8000
```

### View API Documentation

Once the API is running, visit:
- **Citus Swagger Docs**: http://localhost:8000/docs
- **CockroachDB Swagger Docs**: http://localhost:8001/docs

## Dual Deployment (Citus + CockroachDB)

Run both backends side-by-side for parity checks and comparisons.

### Architecture

- Citus API (`app_citus`): `http://localhost:8000`
- CockroachDB API (`app_cockroachdb`): `http://localhost:8001`
- Shared app layer: `app_abstract`
- Backend identity: `GET /db-backend` returns `citus` or `cockroachdb`

### Prerequisites

For a full one-command startup (recommended), use:

```bash
bash scripts/setup.sh
```

Manual dual-deployment steps are below.

```bash
cd docker
docker-compose up -d
docker-compose ps
```

Expected services: coordinator, worker1, worker2, cockroachdb.



### Verify both are healthy

```bash
curl -s http://localhost:8000/db-backend
curl -s http://localhost:8001/db-backend
```

### Sanity-check books/instruments then open all UIs

```bash
bash scripts/check_and_open_all_uis.sh
```

Check-only mode (no browser launch):

```bash
bash scripts/check_and_open_all_uis.sh --check-only
```

### Notes

- Both APIs expose the same contract; cluster/shard status payloads differ by backend.
- `GET /status/cluster` and `GET /status/shards` are backend-specific metadata views.
- Restart only API processes when possible; keep databases running unless schema changes require reinit.
- If port `8000` is already bound, Citus may already be up—verify via `/db-backend` before force-restarting.

### Troubleshooting

- CockroachDB on `26257` already in use: run `cd docker && docker-compose ps` to verify service state.
- Citus API startup failure: check coordinator logs with `cd docker && docker-compose logs coordinator`.
- CockroachDB schema init issues: check `cd docker && docker-compose logs cockroachdb`.

### Clean shutdown (APIs + Docker)

```bash
bash scripts/shutdown.sh
```

## Observability with OpenTelemetry

The Docker Compose stack includes **Grafana Tempo** for distributed tracing and **Grafana** for visualization/correlation.

### Access Observability UIs

When the Docker stack is running (`cd docker && docker-compose up -d`), access:

  - **Grafana Dashboard**: http://localhost:3000/d/sliderule-traces (Sliderule traces in Grafana/Tempo)
  - **Grafana Host Metrics Dashboard**: http://localhost:3000/d/sliderule-host-metrics (host CPU/memory/disk/network from Prometheus)
  - **Grafana Trace Context Viewer**: http://localhost:3000/d/trace-context-viewer/trace-context-viewer (jump from trace IDs to logs/context)

### OpenTelemetry Integration

The application uses OpenTelemetry to send traces to **Tempo**. Required packages are in `requirements.txt`:

```
opentelemetry-api>=1.20.0
opentelemetry-sdk>=1.20.0
opentelemetry-instrumentation-fastapi>=0.41b0
opentelemetry-instrumentation-psycopg>=0.41b0
opentelemetry-exporter-otlp-proto-grpc>=1.20.0
```

### Trace Export Configuration

The application exports traces via OTLP to Tempo:
- **Tempo**: `localhost:4317` (OTLP gRPC)

Configure via environment variables:
```bash
export OTEL_EXPORTER_TEMPO_ENDPOINT=http://localhost:4317
export OTEL_DEPLOYMENT_ENV=development
```

### OpenTelemetry Log Export (Application Logs)

Application logs are shipped over OTLP by default:

```bash
export OTEL_LOGS_ENABLED=true
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://localhost:4319
export OTEL_APP_LOG_LEVEL=INFO
```

Notes:
- Log export is enabled by default. Set `OTEL_LOGS_ENABLED=false` to disable.
- Setting `OTEL_LOGS_ENABLED=true` is optional unless you want to be explicit in your shell/session.
- `scripts/start_services.sh` enables log export unless you override `OTEL_LOGS_ENABLED`.
- In this workspace, `otel-collector` receives OTLP logs on `localhost:4319` and forwards them to Loki.
- If `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` is not set, the app falls back to `OTEL_EXPORTER_TEMPO_ENDPOINT`.

### Python Application Setup

To instrument a FastAPI application:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# Initialize tracing
trace.set_tracer_provider(TracerProvider())
tracer_provider = trace.get_tracer_provider()

# Configure OTLP exporter to Tempo
otlp_exporter = OTLPSpanExporter(
    endpoint="http://localhost:4317",
    insecure=True
)
tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

# Auto-instrument FastAPI
FastAPIInstrumentor().instrument_app(app)
```

### What You Get

- **Distributed tracing** across API endpoints, database operations, and business logic
- **Request flow visualization** with latency breakdown by component
- **Business context** in traces: trade IDs, book IDs, instruments, bi-temporal timestamps
- **Error tracking** with full exception details and stack traces
- **Grafana-native tracing** through Tempo with log/metric correlation

### Recommended Trace Filters (Tempo)

Use these tags on `sliderule.trades.book` spans to find business flows quickly in Grafana Explore:

- **Backend identity**: `app.backend` (`citus` or `cockroachdb`)
- **Trade identity**: `trade.event_id`, `trade.event_type`, `trade.prior_event_id`
- **Trade context**: `trade.book1_id`, `trade.book2_id`, `trade.instrument_key`, `trade.currency`
- **Execution context**: `trade.created_by`, `trade.has_prior_event`, `bitemporal.valid_time`
- **DB context**: `db.system`, `db.namespace`

Resource attributes are also attached to service traces for environment-level filtering:

- `service.name`, `service.version`, `service.namespace`
- `deployment.environment`, `host.name`

Quick searches to use in **Grafana Explore**:

- Citus trade booking spans: `operation=sliderule.trades.book` + tag `app.backend=citus`
- CockroachDB trade booking spans: `operation=sliderule.trades.book` + tag `app.backend=cockroachdb`
- Follow a single trade: tag `trade.event_id=<event-id>`
- Show corrections only: tag `trade.has_prior_event=true`

### Observability Endpoints

**Tempo + Grafana:**
- Grafana UI: http://localhost:3000
- Tempo HTTP API: `localhost:3200`
- Tempo OTLP gRPC receiver: `localhost:4317`
- Tempo OTLP HTTP receiver: `localhost:4318`

**Prometheus + Node Exporter:**
- Prometheus UI: http://localhost:9090
- Node Exporter metrics: http://localhost:9100/metrics

## Web UI

Open http://localhost:8000

## API Documentation

### Interactive Swagger UI
Open http://localhost:8000/docs for the interactive Swagger UI with:
- Full endpoint documentation
- Auto-generated request/response schemas
- **Try it out** buttons to test endpoints live
- Parameter descriptions and validation rules
- Status codes and error handling

### Alternative: ReDoc
Open http://localhost:8000/redoc for a cleaner, documentation-style view of all endpoints.

## Demo: All Features

### 1. Book a New Trade (OpenEvent)
```bash
curl -X POST http://localhost:8000/trades \
  -H "Content-Type: application/json" \
  -d '{
    "book1_id": "ALPHA_TRADING",
    "book2_id": "BETA_CAPITAL",
    "book1_side": "BUY",
    "instrument_key": "AAPL",
    "quantity": 100,
    "price": 150.50,
    "currency": "USD",
    "non_economic_data": {"source": "demo"},
    "valid_time": "2026-02-16T10:30:00Z",
    "created_by": "trader1",
    "type_id": 1
  }'
```
Response: `{"event_id": "abc-123..."}`

### 2. View Positions for a Book
```bash
curl http://localhost:8000/positions/ALPHA_TRADING
```
Returns shares and proceeds aggregated from all trades:
```json
[
  {"instrument_key": "AAPL", "position_type": "Shares", "quantity": 100.0, "valid_time": "2026-02-16T10:30:00Z"},
  {"instrument_key": "USD", "position_type": "Proceeds", "quantity": -15050.0, "valid_time": "2026-02-16T10:30:00Z"}
]
```

### 3. View All Trades for a Book
```bash
curl http://localhost:8000/trades/book/ALPHA_TRADING
```
Lists all events (open, cancelled, novated) with full details and timestamps.

### 4. List Cancellable Trades (Reference Trades)
For Cancel and Novation events, get valid reference trades:
```bash
curl http://localhost:8000/trades/book/ALPHA_TRADING/cancellable
```
Returns only OpenEvent trades that haven't been cancelled or novated.

### 5. Cancel a Trade (CancelEvent)
```bash
curl -X POST http://localhost:8000/trades \
  -H "Content-Type: application/json" \
  -d '{
    "book1_id": "ALPHA_TRADING",
    "book2_id": "BETA_CAPITAL",
    "book1_side": "BUY",
    "instrument_key": "AAPL",
    "quantity": 100,
    "price": 150.50,
    "currency": "USD",
    "non_economic_data": {"source": "demo", "reason": "cancel"},
    "valid_time": "2026-02-16T11:00:00Z",
    "created_by": "trader1",
    "type_id": 2,
    "prior_event_id": "abc-123..."
  }'
```
- Requires `prior_event_id` referencing the OpenEvent
- Automatically reverses all position deltas from original trade
- Prevents double-cancellation: second cancel attempt returns 400 error

### 6. Transfer Trade to Another Book (NovationEvent)
```bash
curl -X POST http://localhost:8000/trades \
  -H "Content-Type: application/json" \
  -d '{
    "book1_id": "GAMMA_FUND",
    "book2_id": "BETA_CAPITAL",
    "book1_side": "BUY",
    "instrument_key": "AAPL",
    "quantity": 100,
    "price": 150.50,
    "currency": "USD",
    "non_economic_data": {"source": "demo", "reason": "transfer"},
    "valid_time": "2026-02-16T12:00:00Z",
    "created_by": "trader1",
    "type_id": 5,
    "prior_event_id": "abc-123..."
  }'
```
- Moves trade from ALPHA_TRADING to GAMMA_FUND
- Reverses position from original book, creates position in new book
- Original trade record unchanged (immutable event source)

### 7. Point-in-Time Position Query
```bash
# View positions as of Feb 15, 2026
curl "http://localhost:8000/positions/ALPHA_TRADING?valid_time=2026-02-15T23:59:59Z"
```
Returns positions including only trades valid as of that timestamp.

### 8. Check Cluster Status
```bash
curl http://localhost:8000/status/cluster
```
Returns Citus cluster metrics:
```json
{
  "shards": {"count": 32, "replication_factor": 2},
  "nodes": [
    {"name": "worker1", "role": "primary", "active": true, "port": 5432},
    {"name": "worker2", "role": "primary", "active": true, "port": 5432}
  ],
  "counts": {"books": 12, "instruments": 10, "trade_events": 150},
  "db_stats": {"connections": 2, "xact_commit": 64162, ...}
}
```

### 9. View Shard Placements
```bash
curl http://localhost:8000/status/shards
```
Shows which shards are on which nodes for distributed query planning.

### 10. Web UI Workflow
1. Open http://localhost:8000
2. **Book a Trade**: Fill form with BUY/SELL, quantity, price → click "Book trade"
3. **View Positions**: Scroll to "Positions" panel → positions auto-update
4. **View Trades**: Scroll to "Trades" panel → shows all book trades
5. **Cancel a Trade**: Click "Cancel" button on any OpenEvent row → immediate action with validation
6. **Novate a Trade**: Select event type "NovationEvent" → Reference Trade dropdown auto-populates
7. **Refresh**: Click single "Refresh" button → syncs both Positions and Trades panels

## API Endpoints

### Trade Booking
```bash
POST /trades
{
  "book1_id": "ALPHA_TRADING",
  "book2_id": "BETA_CAPITAL",
  "book1_side": "BUY",
  "instrument_key": "AAPL",
  "quantity": 100,
  "price": 150.50,
  "currency": "USD",
  "non_economic_data": {"settlement_date": "2026-02-15"},
  "valid_time": "2026-02-13T10:30:00Z",
  "created_by": "trader1",
  "type_id": 1
}
```

Response: `{"event_id": "uuid"}`

### Events (Current)
```bash
GET /trades/{event_id}
```

Returns the event for the given event id.

### Positions (Current)
```bash
GET /positions/{book_id}
```

Returns net positions by instrument and `position_type` as-of now by default.

Default (`/positions/{book_id}`) returns positions aggregated from `position_effects`.

Position types:
- `Shares`: stock quantity deltas
- `Proceeds`: cash deltas (for buys, stock `Shares` increase and cash `Proceeds` decrease)

Point-in-time query (both default to now if omitted):

```bash
GET /positions/{book_id}?valid_time=2026-02-15T10:00:00Z&system_time=2026-02-15T10:00:00Z
```

### Cluster Status
```bash
GET /status/cluster
```

Returns Citus cluster metrics, node status, and database activity.

### Shard Placements
```bash
GET /status/shards
```

Returns shard distribution and node placement details.

## Sample

```bash
python scripts/book_sample.py
```

## Tests

```bash
pytest --cov=app_abstract --cov=app_citus --cov=app_cockroachdb --cov-report=term-missing
```

This is the same command used in the GitHub Actions Python workflow.

## Development Guidelines

### Three-Part Consistency Rule

When making changes to data model, business logic, or API contracts, you **must** keep the following three components in sync:

1. **Database** (`sql/schema.sql` and `sql/procs.sql`)
   - Schema definitions and constraints
   - Stored procedure logic and validation
   - All business rules must be enforced at the database level

2. **Application** (`app/models.py` and `app/main.py`)
   - Pydantic models and field validators
   - API endpoint signatures
   - Request/response mapping to database columns
   - All array indices must match SQL SELECT column order

3. **User Interface** (`static/index.html`)
   - Form inputs must match API request schema
   - Field names must correspond to Python model attributes
   - Helper text should explain business constraints to users
   - Dropdown/select options must reflect available choices from API

### Testing Requirements

After any data model change:

```bash
# Run full test suite
pytest tests/ -v

# Run with coverage
pytest --cov=app_abstract --cov=app_citus --cov=app_cockroachdb --cov-report=html

# Test API manually  
curl -X POST http://localhost:8000/trades -H "Content-Type: application/json" \
  -d '{"book1_id": "...", ...}'
```

### Critical Checklist

- [ ] Database schema updated (schema.sql, procs.sql)
- [ ] Python models updated with new/changed fields (models.py)
- [ ] API endpoints updated with new field mappings (main.py)
- [ ] Array indices in SELECT mappings match query column order
- [ ] HTML form fields match Python request model (index.html)
- [ ] Field names in JavaScript match API request schema
- [ ] All validators/constraints synced across DB, Python, UI
- [ ] Tests updated to reflect new business rules
- [ ] Full test suite passes locally before pushing
- [ ] Manual testing via API or UI confirms behavior

### Example: Adding a Business Rule

If adding a constraint like "only OpenEvents can be cancelled":

1. **Database**: Add validation in stored procedure that checks type_id
2. **App**: Update query to filter results (e.g., `type_id = 1`)
3. **UI**: Update helper text and disable form inputs when constraint prevents action
4. **Tests**: Add test cases validating the constraint in all three layers

This ensures the business rule is enforced consistently and users understand the constraint.

### Position Calculation

**Critical**: Positions are **always** calculated from `position_effects`, never read from a cached positions table. This prevents stale data when transactions don't complete properly.

**How it works**:
1. Every trade operation (OpenEvent, CancelEvent, NovationEvent) writes position deltas into `position_effects`
2. The `/positions/{book_id}` API endpoint calls database function `get_positions(book_id, valid_time, system_time)`
3. `get_positions(...)` aggregates directly from `position_effects` joined to `trade_events` on each request
4. When no temporal parameters provided: includes ALL recorded trades (netted to current state)
5. When temporal parameters provided: includes trades valid/recorded as of that point in time

**Why this design**:
- **Consistency**: Positions always reflect the source-of-truth `trade_events` 
- **Temporal Queries**: Can query positions at any historical point in time
- **Error Resilience**: Even if the `positions` cache becomes corrupted, calculations are correct
- **Cancellation**: When all trades are cancelled, position correctly shows 0

**Test coverage**:
- `test_cancel_trade_reverses_positions`: Single trade cancellation → position 0
- `test_cancelling_all_trades_results_in_zero_position`: Multiple trades all cancelled → position 0
- `test_get_positions_endpoint_reflects_cancellations`: API correctly reflects cancellations

## Lint

```bash
flake8 .
```

Flake8 settings are defined in `.flake8` and used consistently in local runs and CI.

## Chat-Driven Development Guide

This project is designed to be developed exclusively via AI chat (GitHub Copilot Chat) with Claude Haiku 4.5 as the standard model. The following guidance ensures effective, safe, and consistent chat-driven development.

### Core Principles

1. **Chat as Sole Development Interface**: All code changes flow through chat interactions. No direct terminal editing or manual file manipulation outside the chat context.
2. **Instruction-First Development**: Changes are guided by `.github/copilot-instructions.md`, which evolves alongside the codebase.
3. **Git History as Record**: Each chat session produces atomic commits with clear messages; `CHAT_SUMMARY.md` preserves intent and context.
4. **Verification Before Commit**: Tests and linting pass locally before any push; no broken code reaches remote.

### Interaction Patterns

#### Small, Focused Changes
For fixes or minor additions (< 100 lines):
- Describe the change in natural language
- Ask the AI to implement and test
- Review the diff locally if needed
- Request commit and push in next chat message

**Example**:
```
Fix the calculation in get_positions() - I think there's a logic error in the quantity sign.
```

#### Feature Implementation
For larger features (> 100 lines or cross-layer):
- **Phase 1**: Ask AI to outline changes across DB / App / UI layers
- **Phase 2**: Implement each layer separately (start with tests, then implementation)
- **Phase 3**: Run full test suite and manual smoke test
- **Phase 4**: Commit with detailed message linking to domain model

**Example**:
```
Add support for AmendEvent (type_id=3). Outline what needs to change in schema, models, API, UI, and tests.
```

#### Ambiguity Resolution
If the intent is unclear:
- Ask for a clarification question
- Provide example input/output
- Link to relevant sections of `.github/copilot-instructions.md`

### Change Governance

#### Self-Service (No Review Required)
- Bug fixes with test coverage
- Documentation updates
- Refactoring that improves DRY (passes all existing tests)
- UI cosmetic changes
- Configuration updates

#### Requires Validation / Review
- Schema changes (must preserve bi-temporal semantics)
- Event type changes (must align with CDM and domain model)
- API contract changes (must update docs and tests)
- Multi-layer refactoring (must maintain three-part consistency)

#### Review Process
1. AI implements and commits locally
2. You review the output and tests in the terminal (`git show`, `pytest`)
3. Request re-work if issues found: **"That doesn't look right because..."**
4. Request push when satisfied: **"commit and push"**

### Change Validation Checklist

Before requesting commit and push, verify:

- [ ] All tests pass: `pytest --cov=app_abstract --cov=app_citus --cov=app_cockroachdb --cov-report=term-missing`
- [ ] No flake8 violations: `flake8 .`
- [ ] Three-part consistency: DB changes ↔ App models ↔ UI forms
- [ ] Event type changes preserve constraints (Pydantic validators + SQL checks)
- [ ] Commit message references the domain model or prior decision
- [ ] `CHAT_SUMMARY.md` is up to date with session intent
- [ ] If database schema changed: `scripts/init_db.py` was run locally
- [ ] If API contract changed: docstring or test example updated
- [ ] UI changes manually tested at `http://127.0.0.1:8000` (if applicable)

### Session Context & Continuation

#### Session Start
1. AI loads `.github/copilot-instructions.md` (latest version)
2. AI checks recent `CHAT_SUMMARY.md` entries to understand ongoing work
3. You provide current request or ask AI to summarize backlog

#### Mid-Session
- AI frequently references `copilot-instructions.md` for domain constraints
- AI suggests tests for changes before implementing
- If context feels stale, request: **"pull latest and remind me what we're doing"**

#### Session End / Rollover
- Request: **"update CHAT_SUMMARY.md with what we accomplished"**
- AI appends dated entry with: prompt, changes, validation, commit hash, AI model used
- Commit and push summary: **"commit and push"**

#### Long Running Sessions
If session grows > 100 exchanges or feels unfocused:
- Request: **"summarize progress and suggest next steps"**
- Review `CHAT_SUMMARY.md` to decide: continue or start fresh session

### Model & Tool Selection

**Default Model**: Claude Haiku 4.5 (via GitHub Copilot Chat)
- Fast, cost-effective, sufficient for most tasks
- Excellent at following detailed instructions
- Good at refactoring and incremental changes

**When to Request Sonnet or Opus**:
- Complex architectural decisions (use @mention or explicit request)
- Multi-file refactoring with high interdependencies
- When Haiku seems uncertain or produces incomplete code

**Required Tools**:
- VS Code with Copilot Chat extension
- Terminal access for `git`, `python`, `pytest`, `flake8`
- Docker Desktop for local Citus/database
- Simple Browser or native browser for UI testing

### Escalation & Rollback

#### If Tests Fail After Commit
1. Request: **"revert the last commit"** → `git revert HEAD`
2. Describe the failure
3. Request: **"fix and retest before committing"**

#### If Data Model Breaks Assumption
1. Request: **"explain how this change affects bi-temporal queries"**
2. If assumption was violated, roll back and re-plan
3. Reference `.github/copilot-instructions.md` constraints

#### If Style or Lint Fails
1. Request: **"fix linting and retest"**
2. AI will correct and re-commit
3. No rollback required (lint is cosmetic)

#### If Domain Logic Question Arises
1. Request: **"review the Trade Model Expectations section and confirm this approach"**
2. AI will cross-check instructions and propose aligned changes
3. Commit once you agree with approach

### Example Session Flow

```
You:   "Add a novation UI button that cancels the old trade and books a new one."

AI:    [Asks clarifying questions about pre-population, error handling]

You:   "Auto-populate the new book with the old counterparty. If booking fails, show error."

AI:    [Outlines: DB procs update, API endpoint changes, UI form changes, test cases]

You:   "Looks good, go ahead."

AI:    [Implements across all three layers, runs tests]

AI:    [Outputs: "All tests pass (15 passed), linting clean, ready to review"]

You:   [Reviews git diff and test output]

You:   "commit and push"

AI:    [Commits and pushes, updates CHAT_SUMMARY.md with session recap]

You:   "Manual test at UI - novation works end-to-end ✓"
```

### Frequently Asked Questions (Chat-Driven Dev)

**Q: Can I edit a file directly outside chat?**
A: Discouraged. If you do, inform the AI in the next message so it can re-sync understanding of current state.

**Q: What if I disagree with the AI's design choice?**
A: Request clarification: **"I think this approach violates [constraint]. Let's [alternative]."** AI will adjust or defend with reference to instructions.

**Q: How do I handle merge conflicts in chat?**
A: Pull first, then message: **"pull latest and resolve conflicts"** or request manual merge if complex.

**Q: Can I use different AI models in one session?**
A: Avoid switching; consistency helps. If needed, message: **"use Claude Sonnet for this architectural decision"** with @mention or explicit request.

**Q: What if tests need a database reset?**
A: Request: **"reinitialize the database"** → `python scripts/init_db.py`. AI will handle and re-run tests.

## Data Model

### Events
- **Primary Key**: (book_id, event_id)
- **Sharding**: Distributed by book_id across Citus workers
- **Temporal Columns**: valid_time_start, valid_time_end
- **Business Data**: valid_time (when trade occurred), quantity, price, type_id
- **Metadata**: event_id (trade identifier), book1_side, non_economic_data

### Book1-Side Trades
Every trade creates exactly one event:
- Book1 and Book2 are stored in the same row
- Book1 side indicates BUY or SELL from Book1's perspective

### Positions
Positions are derived (not stored) via aggregation:
- Net quantity = SUM(BUY quantity) - SUM(SELL quantity)
- Calculated by instrument and book

## Citus Configuration

- **Coordinator Node**: Receives queries, routes to workers
- **Worker Nodes**: Store sharded data
- **Replication Factor**: 2 (each shard has 2 replicas)
- **Shard Count**: 32 shards for trade_events
- **Reference Tables**: books, instruments replicated to all workers

This configuration enables multi-master insert capability: if one worker fails, the other replica can handle reads and writes continue on the coordinator.
- **Reference Tables**: books, instruments replicated to all workers
