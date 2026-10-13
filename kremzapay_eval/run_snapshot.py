"""Code state of a git repo for a run: the code that executes must be committed, so HEAD alone restores it.

Scope = the paths whose code actually runs (stand: src, pyproject.toml, uv.lock; inspect-lab: kremzapay_eval,
injection.py, requirements.txt). Inside the scope the snapshot REFUSES (exit 1) when there is
  - a tracked code/config file changed against HEAD,
  - an untracked code/config file (also names like tokenizer.py: everything executable has to be committed),
  - an ignored .py / .sh file (code that git would not restore).
Nothing is copied and no patch is written, so no file content — and no secret inside an ordinary file — leaves
the repo. Outside the scope and for docs, changes are only listed: path, and sha256 unless the name looks secret.
Run inputs that are ignored on purpose (campaign, KB, manifest) are recorded by their hashes elsewhere.
Usage: python -m kremzapay_eval.run_snapshot <repo> <out_dir> <scope path>...
"""
import fnmatch
import hashlib
import json
import subprocess
import sys
from pathlib import Path

CODE_SUFFIXES = {".py", ".sh", ".json", ".jsonl", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".txt", ".sql", ".lock"}
EXECUTABLE_SUFFIXES = {".py", ".sh"}
SECRET_PATTERNS = (".env", ".env.*", "*.env", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "*secret*", "*credential*",
                   "*.db", "*.sqlite", "*.sqlite3", "*.db-journal")


class SnapshotError(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise SnapshotError(f"git {' '.join(args)} failed in {repo}: {out.stderr.strip()}")
    return out.stdout


def _paths(repo: Path, *args: str) -> list[str]:
    return sorted(p for p in _git(repo, *args, "-z").split("\0") if p)


def _secret_like(path: str) -> bool:
    return any(fnmatch.fnmatch(Path(path).name.lower(), pattern) for pattern in SECRET_PATTERNS)


def _in_scope(path: str, scope: tuple[str, ...]) -> bool:
    return any(path == s or path.startswith(s.rstrip("/") + "/") for s in scope)


def _listed(repo: Path, path: str, kind: str) -> dict:
    entry = {"path": path, "kind": kind}
    file = repo / path
    if not _secret_like(path) and file.is_file():
        entry["sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
    return entry


def snapshot(repo: Path, out_dir: Path, scope: tuple[str, ...]) -> dict:
    repo, out_dir, scope = Path(repo), Path(out_dir), tuple(scope)
    if not (repo / ".git").exists():
        raise SnapshotError(f"{repo}: not a git repository")
    if not scope:
        raise SnapshotError("empty scope: name the paths whose code runs")
    head = _git(repo, "rev-parse", "HEAD").strip()
    code = lambda p: _in_scope(p, scope) and (Path(p).suffix.lower() in CODE_SUFFIXES or _secret_like(p))  # noqa: E731
    changed = _paths(repo, "diff", "HEAD", "--name-only")
    untracked = _paths(repo, "ls-files", "--others", "--exclude-standard")
    ignored = _paths(repo, "ls-files", "--others", "--ignored", "--exclude-standard")
    problems = [f"uncommitted change: {p}" for p in changed if code(p)]
    problems += [f"untracked code: {p}" for p in untracked if code(p)]
    problems += [f"ignored code: {p}" for p in ignored if _in_scope(p, scope)
                 and Path(p).suffix.lower() in EXECUTABLE_SUFFIXES and "__pycache__" not in p]
    if problems:
        raise SnapshotError(f"{repo}: code in scope {scope} is not committed — commit or remove it before a run: "
                            f"{problems}")
    other = [_listed(repo, p, "changed") for p in changed] + [_listed(repo, p, "untracked") for p in untracked]
    info = {"repo": str(repo.resolve()), "head": head, "scope": list(scope), "code_committed": True,
            "other_changes": other}
    out_dir.mkdir(parents=True, exist_ok=False)
    (out_dir / "snapshot.json").write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")
    return info


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        info = snapshot(Path(argv[0]), Path(argv[1]), tuple(argv[2:]))
    except (SnapshotError, OSError) as exc:
        print(f"snapshot refused: {exc}", file=sys.stderr)
        return 1
    print(f"{argv[0]}: head {info['head'][:7]}, code in {info['scope']} committed; "
          f"{len(info['other_changes'])} other change(s) listed -> {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
