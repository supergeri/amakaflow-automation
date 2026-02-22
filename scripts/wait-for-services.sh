#!/bin/bash
# Health check script that waits for services to be ready

set -e

FRONTEND_URL="${1:-http://localhost:3000}"
BACKEND_URL="${2:-http://localhost:8004/health}"
TIMEOUT="${3:-120}"
INTERVAL=3

echo "Waiting for services..."
echo "  Frontend: $FRONTEND_URL"
echo "  Backend: $BACKEND_URL"
echo "  Timeout: ${TIMEOUT}s"
echo ""

start_time=$(date +%s)
elapsed=0

while [ $elapsed -lt $TIMEOUT ]; do
    # Check frontend
    if curl -sf --max-time 2 "$FRONTEND_URL" > /dev/null 2>&1; then
        frontend_status="READY"
    else
        frontend_status="WAITING"
    fi
    
    # Check backend
    if curl -sf --max-time 2 "$BACKEND_URL" > /dev/null 2>&1; then
        backend_status="READY"
    else
        backend_status="WAITING"
    fi
    
    echo "[$(date +%H:%M:%S)] Frontend: $frontend_status | Backend: $backend_status"
    
    if [ "$frontend_status" = "READY" ] && [ "$backend_status" = "READY" ]; then
        echo ""
        echo "All services are ready!"
        exit 0
    fi
    
    sleep $INTERVAL
    elapsed=$(($(date +%s) - start_time))
done

echo ""
echo "Timeout reached. Services not ready."
exit 1
