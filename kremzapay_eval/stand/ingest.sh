#!/usr/bin/env bash
# Index a KB folder into a named collection of the red-team Qdrant, using the bot's own ingest.py unchanged.
# Usage: stand/ingest.sh <kb_dir> <collection>      e.g. stand/ingest.sh kb_clean rt_clean
set -euo pipefail
source "$(dirname "$0")/common.sh"

KB_DIR_ARG="${1:?kb_dir required}"
COLLECTION_ARG="${2:?collection required}"
KB_ABS="$(cd "$EVAL_DIR" && realpath "$KB_DIR_ARG")"

[ -d "$KB_ABS" ] || { echo "no such kb dir: $KB_ABS" >&2; exit 2; }
curl -sf "$QDRANT_URL/collections" >/dev/null || { echo "qdrant not reachable at $QDRANT_URL (run stand/qdrant.sh)" >&2; exit 2; }

echo "ingest $KB_ABS -> $QDRANT_URL / $COLLECTION_ARG"
# ingest.py resolves KB_DIR relative to the bot repo unless absolute, so pass the absolute path.
( cd "$BOT_REPO" && KB_DIR="$KB_ABS" COLLECTION="$COLLECTION_ARG" .venv/bin/python src/ingest.py )

echo "--- collection check ---"
curl -s "$QDRANT_URL/collections/$COLLECTION_ARG" | python3 -c 'import sys,json; d=json.load(sys.stdin)["result"]; print("points:", d["points_count"], "status:", d["status"])'
