#!/usr/bin/env bash
# Complete setup script for Sliderule - sets up everything from a fresh git clone
# Usage: bash scripts/setup.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Sliderule Setup${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker is installed${NC}"

# Ensure Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${YELLOW}Docker is not running. Attempting to start Docker...${NC}"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        open --background -a Docker
        # Wait for Docker to start
        while ! docker info > /dev/null 2>&1; do
            echo -e "${YELLOW}Waiting for Docker to start...${NC}"
            sleep 2
        done
    fi
fi

echo -e "${YELLOW}Starting Docker Compose services...${NC}"
docker compose -f "$ROOT_DIR/docker/docker-compose.yml" up -d
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Docker Compose services started successfully${NC}"
else
    echo -e "${RED}✗ Failed to start Docker Compose services${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}✗ Docker Compose is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose is installed${NC}"

if ! command -v python &> /dev/null; then
    echo -e "${RED}✗ Python 3 is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python 3 is installed${NC}"

# Create virtual environment if it doesn't exist
echo ""
echo -e "${YELLOW}Setting up Python virtual environment...${NC}"

if [ ! -d "$VENV_DIR" ]; then
    python -m venv "$VENV_DIR"
    echo -e "${GREEN}✓ Python virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Python virtual environment already exists${NC}"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"
echo -e "${GREEN}✓ Virtual environment activated${NC}"

# Upgrade pip
echo ""
echo -e "${YELLOW}Installing dependencies...${NC}"
"$PIP_BIN" install --quiet --upgrade pip setuptools wheel

# Install Python dependencies
if [ -f "$ROOT_DIR/requirements.txt" ]; then
    "$PIP_BIN" install --quiet -r "$ROOT_DIR/requirements.txt"
    echo -e "${GREEN}✓ Python dependencies installed${NC}"
else
    echo -e "${RED}✗ requirements.txt not found${NC}"
    exit 1
fi

    # Build Sphinx documentation
    echo ""
    echo -e "${YELLOW}Building Sphinx documentation...${NC}"
    "$PYTHON_BIN" -m sphinx -b html "$ROOT_DIR/docs" "$ROOT_DIR/docs/_build/html"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Sphinx documentation built successfully${NC}"
    else
        echo -e "${RED}✗ Sphinx documentation build failed${NC}"
        exit 1
    fi

# Start Docker Compose stack
echo ""
echo -e "${YELLOW}Starting Docker Compose services...${NC}"
cd "$ROOT_DIR/docker"
docker-compose up -d --remove-orphans
cd "$ROOT_DIR"

# Wait for services to be healthy
echo -e "${YELLOW}Waiting for services to be ready...${NC}"
sleep 3

"$PYTHON_BIN" << 'PYWAIT'
import sys
import time
import psycopg

def wait_ready(label: str, dsn: str, timeout: int = 90) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with psycopg.connect(dsn, connect_timeout=2):
                print(f"✓ {label} is ready")
                return
        except Exception:
            time.sleep(1)
    print(f"✗ {label} failed to start")
    sys.exit(1)

wait_ready("Citus coordinator", "host=localhost port=5432 user=postgres password=postgres dbname=postgres")
wait_ready("CockroachDB", "host=localhost port=26257 user=root dbname=defaultdb")
PYWAIT

echo -e "${GREEN}✓ All Docker services are healthy${NC}"

# Initialize databases
echo ""
echo -e "${YELLOW}Initializing databases...${NC}"
export PYTHONPATH="$ROOT_DIR"
"$PYTHON_BIN" "$ROOT_DIR/scripts/init_all.py"
echo -e "${GREEN}✓ Databases initialized${NC}"

echo ""
echo -e "${YELLOW}Starting APIs...${NC}"
SLIDERULE_DETACH=true "$ROOT_DIR/scripts/start_services.sh"

echo ""
echo -e "${YELLOW}Verifying APIs...${NC}"
"$PYTHON_BIN" << 'PYCHECK'
import json
import sys
import time
import urllib.request

def wait_http(url: str, timeout: int = 30):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            time.sleep(1)
    return None

citus = wait_http("http://127.0.0.1:8000/db-backend")
cockroach = wait_http("http://127.0.0.1:8001/db-backend")

if not citus or citus.get("backend") != "citus":
    print("✗ Citus API failed health check")
    sys.exit(1)
if not cockroach or cockroach.get("backend") != "cockroachdb":
    print("✗ CockroachDB API failed health check")
    sys.exit(1)

print("✓ Citus API is healthy")
print("✓ CockroachDB API is healthy")
PYCHECK

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "One-command bootstrap complete. APIs are running."
echo ""
echo "To view the web UIs once APIs are running:"
echo "  bash scripts/check_and_open_all_uis.sh"
echo ""
echo "API docs:"
echo "  http://localhost:8000/docs"
echo "  http://localhost:8001/docs"
echo ""