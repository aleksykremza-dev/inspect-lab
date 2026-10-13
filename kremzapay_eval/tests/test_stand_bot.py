"""Check stand startup against local process stubs, without Docker or a model."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "stand" / "bot.sh"


@pytest.fixture
def stand(tmp_path):
    if shutil.which("bash") is None:
        pytest.skip("needs bash")
    repo = tmp_path / "repo"
    run = tmp_path / "run"
    tools = tmp_path / "bin"
    for directory in (repo / ".venv/bin", run, tools):
        directory.mkdir(parents=True, exist_ok=True)
    script = tmp_path / "bot.sh"
    shutil.copy(SCRIPT, script)
    (tmp_path / "common.sh").write_text(
        f'BOT_REPO="{repo}"\nRUN_DIR="{run}"\nEVAL_DIR="{tmp_path}"\n'
        'BOT_PORT=8021\nQDRANT_URL=http://unused\nDB_PATH="$RUN_DIR/bot.db"\n', encoding="utf-8"
    )
    stubs = {
        tools / "ss": '#!/bin/bash\n[ "${PORT_OCCUPIED:-0}" = 1 ] && echo LISTEN\nexit 0\n',
        tools / "curl": '#!/bin/bash\nexit 0\n',
        repo / ".venv/bin/uvicorn": '#!/bin/bash\nexec sleep 60\n',
    }
    for path, content in stubs.items():
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)
    env = {**os.environ, "PATH": f"{tools}:{os.environ['PATH']}"}
    yield script, run, env
    subprocess.run(["bash", str(script), "rt_clean", "stop"], env=env,
                   capture_output=True, timeout=10)


def test_occupied_port_is_not_reported_as_our_bot(stand):
    script, run, env = stand
    result = subprocess.run(["bash", str(script), "rt_clean", "start"],
                            env={**env, "PORT_OCCUPIED": "1"}, capture_output=True,
                            text=True, timeout=10)
    assert result.returncode == 2
    assert "already occupied" in result.stderr
    assert not (run / "bot.pid").exists()


def test_pidfile_tracks_running_server_and_stop_terminates_it(stand):
    script, run, env = stand
    result = subprocess.run(["bash", str(script), "rt_clean", "start"], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    pid = int((run / "bot.pid").read_text())
    os.kill(pid, 0)
    stopped = subprocess.run(["bash", str(script), "rt_clean", "stop"], env=env,
                             capture_output=True, text=True, timeout=10)
    assert stopped.returncode == 0
    assert f"bot stopped (pid {pid})" in stopped.stdout
    assert not (run / "bot.pid").exists()
