"""Decide whether a finished kremzapay campaign can be reported. Writes <log_dir>/status.json, exits with the status.

    complete      (exit 0) results match the expected campaign, every sample scored without error, nothing pending
    needs_review  (exit 2) as complete, but some attacks are undetermined: ASR is preliminary
    incomplete    (exit 3) anything else — no logs, failed log, errored/unscored/missing/unexpected samples,
                           other dataset, no attacks, or conflicting runs inside one campaign

Which logs count: only those directly in log_dir (run_morning.sh keeps the smoke run in log_dir/smoke) whose task
metadata carries this campaign_id. An eval-set retry keeps the same task_id: the latest log per task_id is used.
All logs of the campaign must share one identity (task, model, dataset hash, phase, task args, run config),
otherwise two experiments could stand in for each other.

--obs-schema N (new campaigns only): every scored sample must carry the stand's observability record of schema N
(config, every model call, the candidate before L4 when an answer was generated, the L4 decision when it ran).
Historical runs are checked without it: fields that did not exist then are not required after the fact.

Usage: python kremzapay_eval/check_results.py <log_dir> --campaign <campaign.jsonl> --phase s1 --campaign-id <id>
       [--obs-schema 1]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root, also when run as a script

from inspect_ai.log import list_eval_logs, read_eval_log

from kremzapay_eval.bot_eval import select_phase
from kremzapay_eval.obs_gate import sample_obs_problems

SCORER = "bot_scorer"
EXIT_CODES = {"complete": 0, "needs_review": 2, "incomplete": 3}
CONFIG_FIELDS = ("limit", "sample_id", "epochs", "epochs_reducer")
OBS_SCHEMAS = (1, 2)
OBS_MAX_LISTED = 10


def obs_problems(logs: list, schema: int | None) -> list[str]:
    """[] when no schema is required; otherwise one summary reason if any scored sample lacks its obs record."""
    if schema is None:
        return []
    if schema not in OBS_SCHEMAS:
        return [f"unknown obs schema {schema} (known: {OBS_SCHEMAS})"]
    problems = []
    for log in logs:
        for sample in log.samples or []:
            score = (sample.scores or {}).get(SCORER)
            if sample.error is None and score is not None:   # errored/unscored samples are reported elsewhere
                problems += sample_obs_problems(str(sample.id), score.metadata or {}, schema)
    if not problems:
        return []
    return [f"obs schema {schema}: {len(problems)} problem(s), first {OBS_MAX_LISTED}: {problems[:OBS_MAX_LISTED]}"]


def identity(log) -> str:
    """What makes two logs the same experiment. eval_id/run differ between retries and are left out."""
    config = log.eval.config.model_dump()
    return json.dumps({"task": log.eval.task, "model": log.eval.model, "metadata": log.eval.metadata,
                       "task_args": log.eval.task_args, "config": {k: config.get(k) for k in CONFIG_FIELDS}},
                      sort_keys=True, default=str)


def campaign_logs(log_dir: Path, campaign_id: str) -> tuple[list, list[str]]:
    """Latest log per task_id of this campaign, and reasons if the campaign's logs disagree on identity."""
    logs = [read_eval_log(info) for info in list_eval_logs(str(log_dir), recursive=False)]
    mine = [log for log in logs if (log.eval.metadata or {}).get("campaign_id") == campaign_id]
    identities = {identity(log) for log in mine}
    reasons = [f"conflicting runs in campaign {campaign_id!r}: {len(identities)} different identities "
               f"(model/dataset/args/config) in {log_dir}"] if len(identities) > 1 else []
    latest: dict[str, object] = {}
    for log in mine:
        if log.eval.task_id not in latest or log.eval.created > latest[log.eval.task_id].eval.created:
            latest[log.eval.task_id] = log
    return list(latest.values()), reasons


def compare_samples(expected: dict[str, str], observed: dict[str, str]) -> list[str]:
    """expected/observed: sample id -> group."""
    reasons = []
    missing = sorted(set(expected) - set(observed))
    extra = sorted(set(observed) - set(expected))
    wrong = sorted(i for i in set(expected) & set(observed) if expected[i] != observed[i])
    if missing:
        reasons.append(f"{len(missing)} expected samples missing: {missing[:10]}")
    if extra:
        reasons.append(f"{len(extra)} unexpected samples: {extra[:10]}")
    if wrong:
        reasons.append(f"group differs from campaign for {wrong[:10]}")
    return reasons


def tally(logs: list) -> tuple[dict, dict[str, str], set[str]]:
    """Sample counts, observed id -> group, attack families seen."""
    counts = {"scored": 0, "errored": 0, "unscored": 0, "determined": 0, "pending_review": 0, "successes": 0}
    observed: dict[str, str] = {}
    families: set[str] = set()
    for log in logs:
        for sample in log.samples or []:
            observed[str(sample.id)] = sample.metadata.get("group")
            score = (sample.scores or {}).get(SCORER)
            if sample.error is not None:
                counts["errored"] += 1
            elif score is None:
                counts["unscored"] += 1
            else:
                counts["scored"] += 1
                if sample.metadata.get("group") != "attack":
                    continue
                families.add(str(sample.metadata.get("family_id") or sample.id))
                if score.value.get("attack_undetermined"):
                    counts["pending_review"] += 1
                else:
                    counts["determined"] += 1
                    counts["successes"] += int(score.value.get("attack_success") == 1)
    return counts, observed, families


def check(log_dir: Path, campaign: Path, phase: str, campaign_id: str, obs_schema: int | None = None) -> dict:
    expected_records = select_phase([json.loads(line) for line in campaign.read_text(encoding="utf-8").splitlines()
                                     if line.strip()], phase)
    expected = {str(r["id"]): r.get("group") for r in expected_records}
    expected_hash = hashlib.sha256(campaign.read_bytes()).hexdigest()
    logs, reasons = campaign_logs(log_dir, campaign_id)
    counts, observed, families = tally(logs)

    if not logs:
        reasons.append(f"no eval logs of campaign {campaign_id!r} in {log_dir}")
    reasons += [f"{log.eval.task}: log status {log.status}" for log in logs if log.status != "success"]
    reasons += [f"dataset differs from {campaign} (sha256 {log.eval.metadata.get('dataset_sha256')} != {expected_hash})"
                for log in logs if log.eval.metadata.get("dataset_sha256") != expected_hash]
    reasons += [f"phase {log.eval.metadata.get('phase')!r} != {phase!r}" for log in logs
                if log.eval.metadata.get("phase") != phase]
    if not any(group == "attack" for group in expected.values()):
        reasons.append("campaign has no attack samples: ASR is undefined")
    reasons += compare_samples(expected, observed)
    if counts["errored"] or counts["unscored"]:
        reasons.append(f"{counts['errored']} errored, {counts['unscored']} unscored samples")
    reasons += obs_problems(logs, obs_schema)

    status = "incomplete" if reasons else ("needs_review" if counts["pending_review"] else "complete")
    determined = counts["determined"]
    return {
        "status": status, "reasons": reasons, "campaign_id": campaign_id, "dataset_sha256": expected_hash,
        "obs_schema": obs_schema,
        "logs": len(logs), "planned": len(expected), "scored": counts["scored"], "errored": counts["errored"],
        "unscored": counts["unscored"],
        "attacks": {"determined": determined, "pending_review": counts["pending_review"],
                    "successes": counts["successes"], "asr": counts["successes"] / determined if determined else None,
                    "families": len(families)},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log_dir")
    ap.add_argument("--campaign", required=True, help="the campaign .jsonl the run was started with")
    ap.add_argument("--phase", default="s1")
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--obs-schema", type=int, default=None,
                    help="require the stand observability record of this schema (new campaigns only)")
    args = ap.parse_args()
    log_dir = Path(args.log_dir)
    result = check(log_dir, Path(args.campaign), args.phase, args.campaign_id, args.obs_schema)
    (log_dir / "status.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    a = result["attacks"]
    asr = "n/a" if a["asr"] is None else f"{a['asr']:.3f}"
    print(f"status: {result['status']} | scored {result['scored']}/{result['planned']}, errored {result['errored']} | "
          f"ASR {asr} = {a['successes']}/{a['determined']} determined attacks ({a['families']} families), "
          f"{a['pending_review']} pending review")
    for reason in result["reasons"]:
        print(f"  - {reason}")
    return EXIT_CODES[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
