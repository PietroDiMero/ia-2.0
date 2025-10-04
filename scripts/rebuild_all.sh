#!/usr/bin/env bash
set -euo pipefail
echo "[rebuild_all] Full stack rebuild (Docker)"
docker compose down --remove-orphans || true
docker compose build --no-cache
docker compose up -d
echo "[rebuild_all] Waiting for backend health..."
for i in {1..30}; do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo "[rebuild_all] Backend OK"; exit 0; fi
  sleep 2
done
echo "[rebuild_all] ERROR: backend not healthy after timeout" >&2
exit 1
