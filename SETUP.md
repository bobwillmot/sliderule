# sliderule Clean Setup Guide

This guide documents setup implementation details for sliderule and links to the canonical operational documentation in README.

## What Changed

### Before (Complex)
- Multiple manual scripts run separately
- Database initialization logic scattered across files
- Embedded Python code in bash scripts
- No unified entry point

### Now (Clean)
- **Single `scripts/setup.sh`** command sets up everything
- **Unified `init_all.py`** handles both Citus and CockroachDB
- **Simplified `start_services.sh`** just starts the APIs
- **Clean `shutdown.sh`** stops APIs and Docker services safely
- **Configuration file** (`.env.example`) documents all options

## Documentation Map

For day-to-day commands and runbooks, use README as the single source of truth:

- Setup, startup, and API lifecycle commands: [README.md](README.md#setup)
- Dual deployment checks and troubleshooting: [README.md](README.md#dual-deployment-citus--cockroachdb)
- Observability and test workflows: [README.md](README.md#observability-with-opentelemetry), [README.md](README.md#tests)

## Scripts Overview

### `scripts/setup.sh` (New)
**Purpose:** Complete initial setup from git clone

**Does:**
1. Checks prerequisites (Docker, Python 3, Docker Compose)
2. Creates `.venv` virtual environment
3. Installs `requirements.txt` dependencies
4. Starts Docker Compose stack
5. Waits for services to be healthy
6. Runs `scripts/init_all.py` for database initialization

**When to use:** First time after cloning, or to reset everything

```bash
bash scripts/setup.sh
```

### `scripts/init_all.py` (New)
**Purpose:** Unified database initialization for both backends

**Does:**
1. **Citus initialization:**
   - Creates database if needed
   - Loads schema with Citus extensions
   - Seeds reference data (books, instruments, types)
   - Loads stored procedures

2. **CockroachDB initialization:**
   - Creates database if needed
   - Loads CockroachDB-compatible schema (no Citus extensions)
   - Seeds reference data

**When to use:** Reset databases while keeping Docker services running

```bash
.venv/bin/python scripts/init_all.py
```

### `scripts/start_services.sh` (Updated)
**Purpose:** Start both API services

**Does:**
1. Sets up environment variables
2. Kills any existing uvicorn processes
3. Starts Citus API on port 8000
4. Starts CockroachDB API on port 8001
5. Logs output to `/tmp/citus.log` and `/tmp/cockroachdb.log`

**When to use:** Start the APIs (assumes databases are initialized)

```bash
bash scripts/start_services.sh
```

### `scripts/shutdown.sh` (New)
**Purpose:** Cleanly stop API and Docker services

**Does:**
1. Stops Citus and CockroachDB uvicorn processes
2. Ensures any stuck API process is force-stopped
3. Runs Docker Compose down with orphan cleanup

**When to use:** End of development session, before a clean restart, or before re-running setup

```bash
bash scripts/shutdown.sh
```

### `.env.example` (New)
**Purpose:** Documents all configuration options

**Contains:**
- Database URLs for Citus and CockroachDB
- OpenTelemetry/Grafana settings
- API host and port configuration
- Python path setup

**When to use:** Copy to `.env.local` to override defaults

```bash
cp .env.example .env.local
# Edit .env.local as needed
```

## What's Next

After setup internals are understood, continue with [README.md](README.md) for:
- command workflows and troubleshooting
- API and UI usage
- test commands and CI-aligned validation
- observability dashboards and telemetry setup
