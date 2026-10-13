#!/usr/bin/env bash
# S2 paired run: the same 21 benign questions against the clean-twin KB and the poisoned KB, one new session each.
# Bot: instrumented stand copy (stand/common.sh BOT_REPO). Collections must be ingested first:
#   python kremzapay_eval/data/build_s2_twins.py
#   bash kremzapay_eval/stand/ingest.sh run/kb_s2_clean_all rt_s2_clean
#   bash kremzapay_eval/stand/ingest.sh run/kb_s2_poisoned_all rt_s2_poisoned
# Exit: 0 both variants complete, otherwise the worst check_results status (2 needs_review, 3 incomplete) or 1.
# Observability schema 2 (stand commit c26670b+; context_docs carry canonical_sha256): snapshot/ (HEAD of both repos; refuses uncommitted code),
# collections.json (both collections vs s2_manifest.json), bot_config.json, model_digest_before/after.json,
# run_params.json; check_results --obs-schema 2 requires a complete per-turn obs record.
# Candidate answers end up in the eval logs and the stand DB: local, closed artifacts — not published.
set -uo pipefail
cd "$(dirname "$0")/.."                     # inspect-lab root
source kremzapay_eval/stand/common.sh
STAMP=$(date +%Y%m%d-%H%M)
ATTACKS="${ATTACKS:-kremzapay_eval/s2_campaign.jsonl}"
LOGROOT="logs/s2-$STAMP"
mkdir -p "$LOGROOT"
exec > >(tee -a "$LOGROOT/run.log") 2>&1
fail() { echo "STOP: $1" >&2; exit 1; }
trap 'bash kremzapay_eval/stand/bot.sh none stop >/dev/null 2>&1 || true' EXIT

echo "=== S2 paired run $STAMP — dataset $ATTACKS ==="
.venv/bin/python kremzapay_eval/validate_attacks.py "$ATTACKS" >/dev/null || fail "$ATTACKS invalid"
[ -f kremzapay_eval/s2_manifest.json ] || fail "s2_manifest.json missing (run data/build_s2_twins.py)"

# obs schema 2 (new campaigns): code snapshots, the bot's effective config, model digest before/after, and
# check_results requires the per-turn obs record (every model call, candidate before L4, L4 decision).
OBS_SCHEMA=2
# the code that runs must be committed in both repos (HEAD restores it); otherwise the run does not start
.venv/bin/python -m kremzapay_eval.run_snapshot . "$LOGROOT/snapshot/inspect-lab" \
  kremzapay_eval injection.py requirements.txt || fail "inspect-lab: commit the code before a run"
.venv/bin/python -m kremzapay_eval.run_snapshot "$BOT_REPO" "$LOGROOT/snapshot/stand" \
  src pyproject.toml uv.lock || fail "stand: commit the code before a run"
# the existing index, not a config value, decides what the model sees: both collections vs the manifest
.venv/bin/python -m kremzapay_eval.collection_check "$QDRANT_URL" kremzapay_eval/s2_manifest.json \
  rt_s2_poisoned rt_s2_clean "$LOGROOT/collections.json" || fail "collections do not match s2_manifest.json"
( cd "$BOT_REPO/src" && ../.venv/bin/python -c 'import json, obs; print(json.dumps(obs.config_snapshot()))' ) \
  > "$LOGROOT/bot_config.json" || fail "cannot read the bot's effective config (obs.config_snapshot)"
read -r OLLAMA_URL ANSWER_MODEL < <(.venv/bin/python -c 'import json,sys; c=json.load(open(sys.argv[1])); print(c["ollama_url"], c["answer_model"])' "$LOGROOT/bot_config.json")
.venv/bin/python -m kremzapay_eval.model_digest record "$OLLAMA_URL" "$ANSWER_MODEL" "$LOGROOT/model_digest_before.json" \
  || fail "model digest unreadable before the campaign"

.venv/bin/python - "$LOGROOT/run_params.json" "$ATTACKS" "$BOT_REPO" "$LOGROOT" "$OBS_SCHEMA" <<'EOF'
import hashlib, json, subprocess, sys
from pathlib import Path
import inspect_ai
out, attacks, bot, logroot, obs_schema = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), int(sys.argv[5])
read = lambda p: json.loads((logroot / p).read_text(encoding="utf-8"))
params = {
    "obs_schema": obs_schema,
    "bot_repo": str(bot), "bot_snapshot": read("snapshot/stand/snapshot.json"),
    "bot_config_at_launch": read("bot_config.json"),   # per-variant COLLECTION is set by stand/bot.sh; per turn in obs
    "model_digest_before": read("model_digest_before.json"), "collections": read("collections.json"),
    "dataset": str(attacks), "dataset_sha256": hashlib.sha256(attacks.read_bytes()).hexdigest(),
    "manifest": json.loads(Path("kremzapay_eval/s2_manifest.json").read_text(encoding="utf-8")),
    "inspect_ai": inspect_ai.__version__, "inspect_lab_snapshot": read("snapshot/inspect-lab/snapshot.json"),
}
Path(out).write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding="utf-8")
print("run params ->", out)
EOF

worst=0
for variant in poisoned clean; do
  collection="rt_s2_$variant"
  campaign_id="s2-$STAMP-$variant"
  echo "--- $variant: $collection ---"
  bash kremzapay_eval/stand/bot.sh "$collection" stop >/dev/null 2>&1 || true
  if ss -H -ltn "sport = :${BOT_PORT}" | grep -q .; then fail "port $BOT_PORT occupied by an untracked process"; fi
  bash kremzapay_eval/stand/bot.sh "$collection" start || fail "bot did not start on $collection"
  BOT_URL="http://localhost:${BOT_PORT}" BOT_DB="$DB_PATH" \
    .venv/bin/inspect eval kremzapay_eval/bot_eval.py --model mockllm/model \
    -T attacks="$ATTACKS" -T phase=s2 -T bot_url="http://localhost:${BOT_PORT}" -T bot_db="$DB_PATH" \
    -T campaign_id="$campaign_id" --max-connections 1 --log-dir "$LOGROOT/$variant" --display plain \
    || fail "$variant run errored"
  .venv/bin/python kremzapay_eval/check_results.py "$LOGROOT/$variant" --campaign "$ATTACKS" --phase s2 \
    --campaign-id "$campaign_id" --obs-schema "$OBS_SCHEMA"
  status=$?
  [ "$status" -gt "$worst" ] && worst=$status
  bash kremzapay_eval/stand/bot.sh "$collection" stop || true
done
if ! .venv/bin/python -m kremzapay_eval.model_digest verify "$OLLAMA_URL" "$ANSWER_MODEL" \
     "$LOGROOT/model_digest_before.json" "$LOGROOT/model_digest_after.json"; then
  echo "STOP: model digest unreadable or changed during the campaign — results are not comparable" >&2
  worst=3
fi
echo "=== S2 finished (worst status exit $worst). logs: $LOGROOT ==="
exit "$worst"
