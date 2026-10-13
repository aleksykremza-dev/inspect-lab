#!/usr/bin/env bash
# Run an isolated copy of the bot on BOT_PORT against a given collection. Code and files of the bot repo are untouched:
# config.py loads the repo .env with load_dotenv(), which does NOT override variables already set here.
# Usage: stand/bot.sh <collection> [start|stop|status]      e.g. stand/bot.sh rt_clean start
set -euo pipefail
source "$(dirname "$0")/common.sh"

COLLECTION_ARG="${1:?collection required}"
CMD="${2:-start}"
PIDFILE="$RUN_DIR/bot.pid"
LOGFILE="$RUN_DIR/bot.log"
KB_ABS="$EVAL_DIR/kb_clean"   # KB_DIR is only used by ingest; the API reads from Qdrant. Set for completeness.

stop_bot() {
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")" && echo "bot stopped (pid $(cat "$PIDFILE"))"
    sleep 2
  fi
  rm -f "$PIDFILE"
}

status_bot() {
  curl -s -m 5 "http://localhost:${BOT_PORT}/health" || echo "bot not responding on :$BOT_PORT"
  echo
}

case "$CMD" in
  stop) stop_bot ;;
  status) status_bot ;;
  start)
    stop_bot
    if ss -H -ltn "sport = :${BOT_PORT}" | grep -q .; then
      echo "port $BOT_PORT is already occupied; refusing to use an untracked bot" >&2
      exit 2
    fi
    curl -sf "$QDRANT_URL/collections/$COLLECTION_ARG" >/dev/null \
      || { echo "collection $COLLECTION_ARG missing in $QDRANT_URL (run stand/ingest.sh)" >&2; exit 2; }
    echo "starting bot copy on :$BOT_PORT  collection=$COLLECTION_ARG  db=$DB_PATH"
    (
      cd "$BOT_REPO"
      exec env COLLECTION="$COLLECTION_ARG" KB_DIR="$KB_ABS" \
        setsid nohup .venv/bin/uvicorn api:app --app-dir src --host 127.0.0.1 --port "$BOT_PORT"
    ) > "$LOGFILE" 2>&1 < /dev/null &
    BOT_PID=$!
    echo "$BOT_PID" > "$PIDFILE"
    # first start loads the embedding model: allow up to ~3 min
    for i in $(seq 1 180); do
      if ! kill -0 "$BOT_PID" 2>/dev/null; then
        echo "bot process exited before becoming ready:" >&2
        tail -20 "$LOGFILE" >&2
        exit 1
      fi
      if curl -sf -m 3 "http://localhost:${BOT_PORT}/health" >/dev/null 2>&1; then
        echo "bot up after ${i}s:"; status_bot; exit 0
      fi
      sleep 1
    done
    echo "bot did not come up; last log lines:" >&2; tail -20 "$LOGFILE" >&2; exit 1 ;;
  *) echo "unknown command $CMD" >&2; exit 2 ;;
esac
