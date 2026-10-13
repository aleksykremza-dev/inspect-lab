"""Do the two S2 Qdrant collections hold exactly the article versions the manifest describes?

A config value (CHUNK_SIZE) says nothing about how an existing index was built, so the collections themselves are
read (Qdrant scroll, payload only) and checked before a run:
  - every manifest article (id + title) is in each collection as exactly one point, chunk 0 (not split);
  - its block "[id : title]\\n<text>" — the exact string the bot puts into the answer prompt — has the manifest
    sha256: poisoned_block_sha256 in the poisoned collection, clean_block_sha256 in the clean one;
  - all other points (the shared KB) are identical in both collections;
  - neither collection is empty or unreadable.
The result (problems + a digest of each collection's content) goes to <out.json>; any problem -> exit 1.
Usage: python -m kremzapay_eval.collection_check <qdrant_url> <s2_manifest.json> <poisoned> <clean> <out.json>
"""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import httpx

PAGE = 256
TIMEOUT_S = 10.0


class CollectionError(RuntimeError):
    pass


def points(qdrant_url: str, collection: str) -> list[dict]:
    """Payloads of every point in the collection."""
    payloads, offset = [], None
    while True:
        body = {"limit": PAGE, "with_payload": True, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        try:
            response = httpx.post(f"{qdrant_url.rstrip('/')}/collections/{collection}/points/scroll", json=body,
                                  timeout=TIMEOUT_S)
            response.raise_for_status()
            result = response.json()["result"]
            page, offset = result["points"], result.get("next_page_offset")
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise CollectionError(f"cannot read collection {collection!r} at {qdrant_url}: {exc!r}") from exc
        payloads += [p.get("payload") or {} for p in page]
        if offset is None:
            return payloads


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def block_sha(payload: dict) -> str:
    return sha(f"[{payload.get('id')} : {payload.get('title')}]\n{payload.get('text')}")


def _key(payload: dict) -> tuple:
    return payload.get("id"), payload.get("title")


def _entry(payload: dict) -> tuple:
    return payload.get("id"), payload.get("title"), payload.get("chunk"), sha(str(payload.get("text")))


def digest(payloads: list[dict]) -> str:
    return sha(json.dumps(sorted(map(list, map(_entry, payloads)), key=str), ensure_ascii=False))


def _article_problems(name: str, payloads: list[dict], key: tuple, expected_sha: str, label: str) -> list[str]:
    found = [p for p in payloads if _key(p) == key]
    if len(found) != 1:
        return [f"{name}: {key} {label} has {len(found)} point(s), expected exactly 1 (not split, not missing)"]
    point = found[0]
    if point.get("chunk") != 0:
        return [f"{name}: {key} is chunk {point.get('chunk')!r}, expected chunk 0"]
    if block_sha(point) != expected_sha:
        return [f"{name}: {key} block sha256 differs from the manifest {label}_block_sha256"]
    return []


def check(manifest: dict, poisoned: list[dict], clean: list[dict], names=("poisoned", "clean")) -> list[str]:
    problems = [f"{n}: collection is empty" for n, p in zip(names, (poisoned, clean)) if not p]
    s2_keys = set()
    for rel, article in sorted(manifest.items()):
        key = (article["id"], article["title"])
        s2_keys.add(key)
        problems += _article_problems(names[0], poisoned, key, article["poisoned_block_sha256"], "poisoned")
        problems += _article_problems(names[1], clean, key, article["clean_block_sha256"], "clean")
    shared_p = Counter(_entry(p) for p in poisoned if _key(p) not in s2_keys)
    shared_c = Counter(_entry(p) for p in clean if _key(p) not in s2_keys)
    if shared_p != shared_c:
        only_p, only_c = shared_p - shared_c, shared_c - shared_p
        problems.append(f"shared KB differs: only in {names[0]} {sorted(k[:3] for k in only_p)[:10]}, "
                        f"only in {names[1]} {sorted(k[:3] for k in only_c)[:10]}")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        print(__doc__, file=sys.stderr)
        return 2
    url, manifest_path, poisoned_name, clean_name, out = argv
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    try:
        poisoned, clean = points(url, poisoned_name), points(url, clean_name)
    except CollectionError as exc:
        problems, summary = [str(exc)], {}
    else:
        problems = check(manifest, poisoned, clean, (poisoned_name, clean_name))
        summary = {poisoned_name: {"points": len(poisoned), "digest": digest(poisoned)},
                   clean_name: {"points": len(clean), "digest": digest(clean)}}
    result = {"ok": not problems, "problems": problems, "collections": summary, "manifest": manifest_path,
              "manifest_sha256": sha(Path(manifest_path).read_text(encoding="utf-8"))}
    Path(out).write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    print(f"collections {'match' if not problems else 'DO NOT match'} the manifest -> {out}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
