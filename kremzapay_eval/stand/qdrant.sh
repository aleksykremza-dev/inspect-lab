#!/usr/bin/env bash
# Start (or reuse) a separate Qdrant for the red-team stand. Storage lives in run/qdrant, not in the bot repo.
set -euo pipefail
source "$(dirname "$0")/common.sh"

if ! command -v docker >/dev/null; then
  echo "docker not available in WSL: enable Docker Desktop > Settings > Resources > WSL integration > Ubuntu" >&2
  exit 2
fi

if docker ps --format '{{.Names}}' | grep -qx "$QDRANT_NAME"; then
  echo "$QDRANT_NAME already running"
elif docker ps -a --format '{{.Names}}' | grep -qx "$QDRANT_NAME"; then
  docker start "$QDRANT_NAME" >/dev/null && echo "$QDRANT_NAME started"
else
  mkdir -p "$RUN_DIR/qdrant"
  docker run -d --name "$QDRANT_NAME" -p "${QDRANT_PORT}:6333" \
    -v "$RUN_DIR/qdrant:/qdrant/storage" "$QDRANT_IMAGE" >/dev/null
  echo "$QDRANT_NAME created"
fi

for _ in $(seq 1 30); do
  if curl -sf "$QDRANT_URL/collections" >/dev/null; then
    echo "qdrant ready at $QDRANT_URL"
    curl -s "$QDRANT_URL/collections"; echo
    exit 0
  fi
  sleep 1
done
echo "qdrant did not become ready on $QDRANT_URL" >&2
exit 1
