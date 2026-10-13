"""run_snapshot: the code that runs must be committed, so HEAD restores it; nothing is copied, nothing secret read."""
import json
import shutil
import subprocess

import pytest

from kremzapay_eval.run_snapshot import SnapshotError, main, snapshot

SCOPE = ("src",)


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("needs git")
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / ".gitignore").write_text("ignored/\nsrc/gen/\n.env\n", encoding="utf-8")
    (root / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (root / "README.md").write_text("doc\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "init")
    return root


def test_committed_code_records_head_and_lists_nothing(repo, tmp_path):
    info = snapshot(repo, tmp_path / "snap", SCOPE)
    assert info["code_committed"] is True and len(info["head"]) == 40 and info["other_changes"] == []
    assert json.loads((tmp_path / "snap" / "snapshot.json").read_text(encoding="utf-8")) == info


@pytest.mark.parametrize("plant,expected", [
    (lambda r: (r / "src" / "app.py").write_text("x = 2\n"), "uncommitted change: src/app.py"),
    (lambda r: (r / "src" / "tokenizer.py").write_text("t = 1\n"), "untracked code: src/tokenizer.py"),
    (lambda r: (r / "src" / "big.py").write_bytes(b"#" * (3 * 1024 * 1024)), "untracked code: src/big.py"),
    (lambda r: (r / "src" / "settings.json").write_text("{}"), "untracked code: src/settings.json"),
    (lambda r: ((r / "src" / "gen").mkdir(), (r / "src" / "gen" / "made.py").write_text("y = 1\n")),
     "ignored code: src/gen/made.py"),
])
def test_uncommitted_code_in_scope_refuses_the_run(repo, tmp_path, plant, expected):
    plant(repo)
    with pytest.raises(SnapshotError, match="not committed") as exc:
        snapshot(repo, tmp_path / "snap", SCOPE)
    assert expected in str(exc.value)
    assert not (tmp_path / "snap").exists()


def test_docs_and_out_of_scope_changes_are_listed_and_secrets_are_not_read(repo, tmp_path):
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    (repo / "notes.md").write_text("n\n", encoding="utf-8")
    (repo / "tools").mkdir()
    (repo / "tools" / "helper.py").write_text("h = 1\n", encoding="utf-8")    # code, but outside the run scope
    (repo / "api_secret.txt").write_text("KEY=1\n", encoding="utf-8")
    info = snapshot(repo, tmp_path / "snap", SCOPE)
    listed = {e["path"]: e for e in info["other_changes"]}
    assert listed["README.md"]["kind"] == "changed" and "sha256" in listed["README.md"]
    assert listed["notes.md"]["kind"] == "untracked" and listed["tools/helper.py"]["kind"] == "untracked"
    assert "sha256" not in listed["api_secret.txt"]
    assert not list((tmp_path / "snap").glob("**/*.patch")) and [p.name for p in (tmp_path / "snap").iterdir()] == \
        ["snapshot.json"]


def test_secret_like_file_inside_scope_refuses(repo, tmp_path):
    (repo / "src" / "prod.pem").write_text("k\n", encoding="utf-8")
    with pytest.raises(SnapshotError, match="untracked code: src/prod.pem"):
        snapshot(repo, tmp_path / "snap", SCOPE)


def test_not_a_repo_and_empty_scope_are_errors(repo, tmp_path):
    with pytest.raises(SnapshotError, match="not a git repository"):
        snapshot(tmp_path, tmp_path / "snap", SCOPE)
    with pytest.raises(SnapshotError, match="empty scope"):
        snapshot(repo, tmp_path / "snap", ())


def test_cli_exit_codes(repo, tmp_path):
    assert main([str(repo), str(tmp_path / "ok"), "src"]) == 0
    (repo / "src" / "app.py").write_text("x = 3\n", encoding="utf-8")
    assert main([str(repo), str(tmp_path / "refused"), "src"]) == 1
    assert main([str(repo), str(tmp_path / "usage")]) == 2
