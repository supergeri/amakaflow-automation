#!/bin/bash
# run_nightly.sh — Chaos Engine nightly runner
# Cron: 0 23 * * * /path/to/amakaflow-automation/chaos/run_nightly.sh >> /tmp/chaos-engine.log 2>&1

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Chaos Engine nightly run: $(date) ==="

# Ensure backend services are up
if ! curl -sf http://localhost:8001/health > /dev/null 2>&1; then
    echo "ERROR: mapper-api not running. Start with: docker compose up -d"
    exit 1
fi

if ! curl -sf http://localhost:3000 > /dev/null 2>&1; then
    echo "ERROR: UI not running on localhost:3000"
    exit 1
fi

# Run web session
python3 -m chaos.orchestrator --platform web

echo "=== Chaos Engine run complete: $(date) ==="
