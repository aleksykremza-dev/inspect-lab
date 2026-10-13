#!/usr/bin/env bash
# Shared settings for the isolated bot copy. Source this file; never edit the bot repo itself.
BOT_REPO="${BOT_REPO:-$HOME/projects/kremzapay-bot-stand}"   # instrumented copy; main bot repo is never run here
EVAL_DIR="$HOME/projects/inspect-lab/kremzapay_eval"
RUN_DIR="$EVAL_DIR/run"

QDRANT_NAME="qdrant-redteam"
QDRANT_IMAGE="qdrant/qdrant:v1.18.2"        # same image tag as the bot's docker-compose.yml
QDRANT_PORT=6336                            # the bot's own Qdrant is on 6335 - not touched
BOT_PORT=8021                               # the bot's own API is on 8020 - not touched

export QDRANT_URL="http://localhost:${QDRANT_PORT}"
export DB_PATH="$RUN_DIR/bot.db"            # isolated tickets/messages DB, read by bot_eval.stopped_by()
export OLLAMA_URL="http://localhost:11434"
export ANSWER_MODEL="${ANSWER_MODEL:-qwen2.5:7b-instruct}"
export MAX_INFLIGHT=2

mkdir -p "$RUN_DIR"
