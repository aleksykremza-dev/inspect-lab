"""Model name -> digest from Ollama (/api/tags), checked before and after a campaign.

This verifies the installed configuration, not which weights served a given call: the model must not be updated
during a campaign, and a digest that differs after the campaign, or cannot be read, fails the run.
Usage:
  python -m kremzapay_eval.model_digest record <ollama_url> <model> <out.json>
  python -m kremzapay_eval.model_digest verify <ollama_url> <model> <before.json> <out.json>
Exit 0 ok, 1 digest unreadable or changed (the reason is printed and written to the out file when possible).
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

TIMEOUT_S = 10.0


class DigestError(RuntimeError):
    pass


def digest(ollama_url: str, model: str) -> str:
    try:
        response = httpx.get(ollama_url.rstrip("/") + "/api/tags", timeout=TIMEOUT_S)
        response.raise_for_status()
        models = response.json()["models"]
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise DigestError(f"cannot read {ollama_url}/api/tags: {exc!r}") from exc
    found = [m for m in models if isinstance(m, dict) and model in (m.get("name"), m.get("model"))]
    if len(found) != 1:
        raise DigestError(f"model {model!r}: {len(found)} matching entries in {ollama_url}/api/tags")
    value = found[0].get("digest")
    if not isinstance(value, str) or not value:
        raise DigestError(f"model {model!r}: no digest in {ollama_url}/api/tags")
    return value


def _record(ollama_url: str, model: str) -> dict:
    return {"model": model, "ollama_url": ollama_url, "digest": digest(ollama_url, model),
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def main(argv: list[str]) -> int:
    if not argv or (argv[0], len(argv)) not in (("record", 4), ("verify", 5)):
        print(__doc__, file=sys.stderr)
        return 2
    url, model, out = argv[1], argv[2], Path(argv[-1])
    try:
        record = _record(url, model)
    except DigestError as exc:
        print(f"model digest: {exc}", file=sys.stderr)
        out.write_text(json.dumps({"model": model, "ollama_url": url, "error": str(exc)}, indent=1), encoding="utf-8")
        return 1
    if argv[0] == "verify":
        before = json.loads(Path(argv[3]).read_text(encoding="utf-8"))
        record["same_as_before"] = record["digest"] == before.get("digest") and before.get("model") == model
        if not record["same_as_before"]:
            out.write_text(json.dumps(record, indent=1), encoding="utf-8")
            print(f"model digest changed during the campaign: {before.get('digest')} -> {record['digest']}",
                  file=sys.stderr)
            return 1
    out.write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(f"{model}: {record['digest'][:19]}… -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
