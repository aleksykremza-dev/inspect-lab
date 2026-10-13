#!/usr/bin/env bash
# One command to run the S1 (English) red-team pass against an isolated bot copy.
# Fails fast with a clear message if anything isn't ready. NOT a blind auto-run: it runs a 5-sample smoke
# first and only continues to the full pass if the smoke succeeds.
#
# Prerequisites that must be done by hand first:
#   - Docker Desktop with WSL integration ON  (stand/qdrant.sh checks this)
#   - ollama serve running with qwen2.5:7b-instruct pulled
#   - attacks.jsonl assembled  (data/etl_cyberseceval.py + data/build_control.py + assemble)
#
# Dataset: ATTACKS=<path from the inspect-lab root> (default kremzapay_eval/attacks.jsonl). The same file is
# validated, smoke-run and fully run:  ATTACKS=kremzapay_eval/campaign_s1.jsonl bash kremzapay_eval/run_morning.sh
# NEAR_DUP_DECISIONS=<decisions.jsonl> passes reviewed near-duplicate decisions to the validator.
# CAMPAIGN_ID (default kremzapay-<stamp>) is written into every log; the result check only trusts that campaign.
set -uo pipefail
cd "$(dirname "$0")/.."                     # inspect-lab root
source kremzapay_eval/stand/common.sh
STAMP=$(date +%Y%m%d-%H%M)
LOGDIR="logs/kremzapay-$STAMP"
FULL_LOGDIR="$LOGDIR/full"
RUNLOG="$RUN_DIR/run-$STAMP.log"
exec > >(tee -a "$RUNLOG") 2>&1
ATTACKS="${ATTACKS:-kremzapay_eval/attacks.jsonl}"
CAMPAIGN_ID="${CAMPAIGN_ID:-kremzapay-$STAMP}"
PHASE=s1
echo "=== morning run $STAMP — campaign $CAMPAIGN_ID, dataset $ATTACKS ==="

fail() { echo "STOP: $1" >&2; exit 1; }

echo "--- preflight ---"
[ -f "$ATTACKS" ] || fail "$ATTACKS missing (assemble it first)"
DECISION_ARGS=()                            # reviewed near-duplicate decisions, if any
[ -n "${NEAR_DUP_DECISIONS:-}" ] && DECISION_ARGS=(--near-dup-decisions "$NEAR_DUP_DECISIONS")
.venv/bin/python kremzapay_eval/validate_attacks.py "$ATTACKS" "${DECISION_ARGS[@]}" >/dev/null \
  || fail "$ATTACKS invalid (run validate_attacks.py on it)"
.venv/bin/pytest -q -p no:warnings kremzapay_eval/tests/ >/dev/null 2>&1 || fail "unit tests red"
curl -sf -m 3 http://localhost:11434/api/tags >/dev/null || fail "ollama not running (ollama serve &)"
command -v docker >/dev/null || fail "docker not in WSL (enable Docker Desktop WSL integration)"
echo "preflight ok"

echo "--- stand: qdrant + ingest rt_clean + bot ---"
bash kremzapay_eval/stand/qdrant.sh || fail "qdrant did not start"
bash kremzapay_eval/stand/ingest.sh kb_clean rt_clean || fail "ingest rt_clean failed"
cleanup() { bash kremzapay_eval/stand/bot.sh rt_clean stop || true; }
trap cleanup EXIT                           # stop the bot copy on every exit path, including failures
bash kremzapay_eval/stand/bot.sh rt_clean start || fail "bot copy did not come up"

echo "--- smoke (5 samples) ---"
BOT_URL="http://localhost:${BOT_PORT}" BOT_DB="$DB_PATH" \
  .venv/bin/inspect eval kremzapay_eval/bot_eval.py --model mockllm/model \
  -T attacks="$ATTACKS" -T phase="$PHASE" -T bot_url="http://localhost:${BOT_PORT}" -T bot_db="$DB_PATH" \
  -T campaign_id="$CAMPAIGN_ID-smoke" --limit 5 --log-dir "$LOGDIR/smoke" --display plain || fail "smoke run errored — check $RUNLOG, do NOT trust full run"
echo "smoke ok — logs in $LOGDIR/smoke (kept apart from the full pass)"

echo "--- full S1 pass ---"
BOT_URL="http://localhost:${BOT_PORT}" BOT_DB="$DB_PATH" \
  .venv/bin/inspect eval-set kremzapay_eval/bot_eval.py --model mockllm/model \
  -T attacks="$ATTACKS" -T phase="$PHASE" -T bot_url="http://localhost:${BOT_PORT}" -T bot_db="$DB_PATH" \
  -T campaign_id="$CAMPAIGN_ID" --max-connections 2 --fail-on-error=0.1 --retry-on-error=2 --log-dir "$FULL_LOGDIR" --display plain
status=$?
if [ "$status" -ne 0 ]; then
  echo "STOP: full pass failed (exit $status) — results are incomplete, do NOT publish numbers. logs in $LOGDIR" >&2
  exit "$status"
fi

echo "--- result check ---"                    # exit 0 of eval-set is not completeness: errors <10% still pass
.venv/bin/python kremzapay_eval/check_results.py "$FULL_LOGDIR" --campaign "$ATTACKS" --phase "$PHASE" --campaign-id "$CAMPAIGN_ID"
result=$?
case "$result" in
  0) echo "=== done: complete. logs and status.json in $FULL_LOGDIR ===" ;;
  2) echo "=== finished: needs_review — ASR is preliminary until pending attacks are reviewed. $FULL_LOGDIR/status.json ==="
     exit 2 ;;
  *) echo "STOP: incomplete (exit $result) — do NOT publish numbers. reasons in $FULL_LOGDIR/status.json" >&2
     exit "$result" ;;
esac
echo "next: inspect view --log-dir $FULL_LOGDIR"
