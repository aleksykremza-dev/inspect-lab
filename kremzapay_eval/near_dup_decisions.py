"""Reviewed decisions about near-duplicate attack texts (one JSON object per line).

    {"ids": ["A", "B"], "hashes": {"A": "<sha256>", "B": "<sha256>"}, "action": "keep_both", "reason": "..."}
    {"ids": ["A", "B"], "hashes": {...}, "action": "drop", "drop_id": "B", "reason": "..."}

A decision covers the exact records it was made for: hashes are sha256 of the whole record (canonical JSON),
so any later edit of either record makes the decision stale and the pair has to be reviewed again.
"""
import hashlib
import json
from pathlib import Path

ACTIONS = {"keep_both", "drop"}


def record_hash(record: dict) -> str:
    canonical = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def decision_errors(d: object) -> list[str]:
    if not isinstance(d, dict):
        return ["decision must be a JSON object"]
    ids, hashes, action = d.get("ids"), d.get("hashes"), d.get("action")
    errors = []
    if not (isinstance(ids, list) and len(ids) == 2 and all(isinstance(i, str) and i for i in ids) and ids[0] != ids[1]):
        return ["ids must be two different record ids"]
    if not (isinstance(hashes, dict) and set(hashes) == set(ids) and all(isinstance(h, str) and h for h in hashes.values())):
        errors.append("hashes must give a sha256 for both ids")
    if not isinstance(action, str) or action not in ACTIONS:   # type first: a list/dict action is unhashable
        errors.append(f"action must be one of {sorted(ACTIONS)}")
    elif action == "drop" and not (isinstance(d.get("drop_id"), str) and d["drop_id"] in ids):
        errors.append("drop needs drop_id = one of ids")
    elif action == "keep_both" and "drop_id" in d:
        errors.append("keep_both must not have drop_id")
    if not isinstance(d.get("reason"), str) or not d["reason"].strip():
        errors.append("reason must be a non-empty string")
    return errors


def load_decisions(path: Path) -> dict[frozenset, dict]:
    """Decisions keyed by the unordered id pair. Raises ValueError listing every malformed line."""
    decisions: dict[frozenset, dict] = {}
    problems = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"line {n}: invalid JSON: {exc}")
            continue
        errors = decision_errors(d)
        if errors:
            problems += [f"line {n}: {e}" for e in errors]
            continue
        key = frozenset(d["ids"])
        if key in decisions:
            problems.append(f"line {n}: second decision for pair {sorted(key)}")
        decisions[key] = d
    if problems:
        raise ValueError(f"{path}: " + "; ".join(problems))
    return decisions


def stale_ids(decision: dict, by_id: dict[str, dict]) -> list[str]:
    """Ids whose current record no longer matches the hash the decision was made for (or is missing)."""
    return [i for i in decision["ids"] if i in by_id and record_hash(by_id[i]) != decision["hashes"][i]]


def pair_errors(id_a: str, id_b: str, ratio: float, decisions: dict | None, by_id: dict[str, dict]) -> list[str]:
    """Validator errors for one near-duplicate pair present in the campaign."""
    undecided = f"near-duplicate text {id_a!r} ~ {id_b!r} (ratio {ratio:.2f}) — needs a reviewed decision"
    decision = (decisions or {}).get(frozenset((id_a, id_b)))
    if decision is None:
        return [undecided]
    stale = stale_ids(decision, by_id)
    if stale:
        return [f"stale decision for {id_a!r} ~ {id_b!r}: record(s) {stale} changed since review — review again"]
    if decision["action"] == "drop":
        return [f"decision says drop {decision['drop_id']!r}, but it is still in the campaign (rebuild it)"]
    return []
