"""run_morning.sh must not report a failed full pass as done. Runs the real script in a sandbox where the stand,
ollama, docker and inspect are replaced by stubs; FULL_EXIT sets the exit code of `inspect eval-set`."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "run_morning.sh"
OK = "#!/usr/bin/env bash\nexit 0\n"
STUBS = {
    "kremzapay_eval/stand/common.sh": 'RUN_DIR="$PWD/run"; BOT_PORT=1; DB_PATH="$PWD/run/bot.db"; mkdir -p "$RUN_DIR"\n',
    "kremzapay_eval/stand/qdrant.sh": OK,
    "kremzapay_eval/stand/ingest.sh": OK,
    "kremzapay_eval/stand/bot.sh": '#!/usr/bin/env bash\necho "bot.sh $*" >> "$PWD/run/bot_calls"\n',
    "kremzapay_eval/attacks.jsonl": "{}\n",
    "kremzapay_eval/campaign_s1.jsonl": "{}\n",
    ".venv/bin/python": '#!/usr/bin/env bash\necho "python $*" >> "$PWD/run/calls"\n'
                        '[ "$1" = kremzapay_eval/check_results.py ] && exit "${CHECK_EXIT:-0}"\nexit 0\n',
    ".venv/bin/pytest": OK,
    ".venv/bin/inspect": '#!/usr/bin/env bash\necho "inspect $*" >> "$PWD/run/calls"\n'
                         '[ "$1" = eval-set ] && exit "${FULL_EXIT:-0}"\nexit 0\n',
    "bin/curl": OK,
    "bin/docker": OK,
}


def run_script(tmp_path: Path, full_exit: int, **extra_env) -> subprocess.CompletedProcess:
    for rel, body in STUBS.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    shutil.copy(SCRIPT, tmp_path / "kremzapay_eval" / "run_morning.sh")
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}", "FULL_EXIT": str(full_exit), **extra_env}
    return subprocess.run(["bash", str(tmp_path / "kremzapay_eval" / "run_morning.sh")], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=60)


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_successful_run_exits_zero_and_stops_bot(tmp_path):
    result = run_script(tmp_path, 0)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "=== done" in result.stdout
    assert "bot.sh rt_clean stop" in (tmp_path / "run" / "bot_calls").read_text()


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_failed_full_pass_propagates_exit_code_and_still_stops_bot(tmp_path):
    result = run_script(tmp_path, 3)
    assert result.returncode == 3, result.stdout + result.stderr
    assert "=== done" not in result.stdout
    assert "bot.sh rt_clean stop" in (tmp_path / "run" / "bot_calls").read_text()


def dataset_args(tmp_path: Path) -> list[str]:
    """Dataset path each step used: validator argument and every inspect -T attacks=."""
    paths = []
    for line in (tmp_path / "run" / "calls").read_text().splitlines():
        words = line.split()
        if words[:2] == ["python", "kremzapay_eval/validate_attacks.py"]:
            paths.append(words[2])
        paths += [w.split("=", 1)[1] for w in words if w.startswith("attacks=")]
    return paths


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_one_attacks_path_for_preflight_smoke_and_full(tmp_path):
    result = run_script(tmp_path, 0, ATTACKS="kremzapay_eval/campaign_s1.jsonl")
    assert result.returncode == 0, result.stdout + result.stderr
    assert dataset_args(tmp_path) == ["kremzapay_eval/campaign_s1.jsonl"] * 3   # validate, smoke, full


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_missing_attacks_file_stops_before_stand(tmp_path):
    result = run_script(tmp_path, 0, ATTACKS="kremzapay_eval/nope.jsonl")
    assert result.returncode != 0
    assert "STOP: kremzapay_eval/nope.jsonl missing" in result.stdout + result.stderr   # script tees stderr to stdout
    assert not (tmp_path / "run" / "bot_calls").exists()


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_near_dup_decisions_passed_to_validator(tmp_path):
    result = run_script(tmp_path, 0, ATTACKS="kremzapay_eval/campaign_s1.jsonl",
                        NEAR_DUP_DECISIONS="kremzapay_eval/near_dup_decisions.jsonl")
    assert result.returncode == 0, result.stdout + result.stderr
    calls = (tmp_path / "run" / "calls").read_text()
    assert "validate_attacks.py kremzapay_eval/campaign_s1.jsonl --near-dup-decisions kremzapay_eval/near_dup_decisions.jsonl" in calls


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize("check_exit,status", [(2, "needs_review"), (3, "incomplete")])
def test_unfinished_results_exit_with_status_not_done(tmp_path, check_exit, status):
    result = run_script(tmp_path, 0, CHECK_EXIT=str(check_exit))
    out = result.stdout + result.stderr
    assert result.returncode == check_exit, out
    assert "=== done" not in out and status in out
    assert "bot.sh rt_clean stop" in (tmp_path / "run" / "bot_calls").read_text()


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_checker_gets_full_run_dir_campaign_and_id_and_smoke_logs_go_to_subdir(tmp_path):
    run_script(tmp_path, 0, ATTACKS="kremzapay_eval/campaign_s1.jsonl", CAMPAIGN_ID="camp-7")
    calls = (tmp_path / "run" / "calls").read_text().splitlines()
    smoke = next(c for c in calls if c.startswith("inspect eval "))
    full = next(c for c in calls if c.startswith("inspect eval-set "))
    checker = next(c for c in calls if "check_results.py" in c).split()
    log_dir = full.split("--log-dir ")[1].split()[0]
    smoke_dir = Path(smoke.split("--log-dir ")[1].split()[0])
    assert smoke_dir == Path(log_dir).parent / "smoke"
    assert not smoke_dir.is_relative_to(Path(log_dir))  # eval-set scans its directory recursively
    assert "campaign_id=camp-7" in full and "campaign_id=camp-7-smoke" in smoke   # smoke is its own campaign
    assert checker[2] == log_dir
    assert checker[checker.index("--campaign") + 1] == "kremzapay_eval/campaign_s1.jsonl"
    assert checker[checker.index("--campaign-id") + 1] == "camp-7"
    assert checker[checker.index("--phase") + 1] == "s1"
