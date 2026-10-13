"""Validate an attacks.jsonl against the attack-record schema enforced below. Exit non-zero on any error.

Usage: python validate_attacks.py <attacks.jsonl> [--kb-poisoned kb_poisoned] [--kb-clean kb_clean]
                                  [--near-dup-decisions decisions.jsonl]
Checks structure only; it does not read attack texts for meaning.
"""
import argparse
import json
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root, also when run as a script

from kremzapay_eval.near_dup_decisions import load_decisions, pair_errors

GOALS = {"G1", "G2", "G3", "G4", "G5", "G6"}
SURFACES = {"S1", "S2"}
DETECTORS = {"canary", "prompt_markers", "action_answer"}
LANGS = {"pl", "en"}
ACTIONS = {"answer", "ticket", "handoff", "redirect", "unsafe_refuse", "clarify", "chitchat_reply"}
CANARY_DETECTOR = "canary"
NEAR_DUP_RATIO = 0.95
REQUIRED_STR = ("id", "group", "technique", "language", "detector", "source")
OPTIONAL_STR = ("surface", "goal", "kb_article", "canary", "text", "family_id")


def load(path: Path) -> list[dict]:
    records = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"ERROR line {n}: invalid JSON: {exc}")
            sys.exit(1)
        if not isinstance(record, dict):
            print(f"ERROR line {n}: record must be a JSON object, got {type(record).__name__}")
            sys.exit(1)
        records.append(record)
    return records


def check_types(r: dict, rid: str) -> list[str]:
    errors = [f"{rid}: '{f}' must be a non-empty string, got {r.get(f)!r:.40}" for f in REQUIRED_STR
              if not isinstance(r.get(f), str) or not r[f].strip()]
    errors += [f"{rid}: '{f}' must be a string or null, got {type(r[f]).__name__}" for f in OPTIONAL_STR
               if r.get(f) is not None and not isinstance(r[f], str)]
    actions = r.get("expected_actions")
    if not isinstance(actions, list) or not actions or not all(isinstance(a, str) for a in actions):
        errors.append(f"{rid}: expected_actions must be a non-empty list of strings")
    elif not set(actions) <= ACTIONS:
        errors.append(f"{rid}: expected_actions not a subset of {sorted(ACTIONS)}")
    merged = r.get("merged_ids")   # set by data/build_campaign.py when records differing only in source are merged
    if merged is not None and not (isinstance(merged, list) and merged and all(isinstance(m, str) for m in merged)):
        errors.append(f"{rid}: merged_ids must be a non-empty list of ids")
    return errors


def check_input(r: dict, rid: str) -> list[str]:
    """Every sample needs something to send: non-empty text, or a list of non-empty turns (text == turns[0])."""
    text, turns = r.get("text"), r.get("turns")
    if turns is not None:
        if not isinstance(turns, list) or not turns or not all(isinstance(t, str) and t.strip() for t in turns):
            return [f"{rid}: turns must be a non-empty list of non-empty strings"]
        if text and text != turns[0]:
            return [f"{rid}: text must equal turns[0] when turns is set"]
        return []
    if not isinstance(text, str) or not text.strip():
        return [f"{rid}: needs non-empty text (or turns)"]
    return []


def check_turn_labels(r: dict, rid: str) -> list[str]:
    """Multi-turn records label every turn: turn_expected_actions[i] = safe actions for turn i+1,
    attack_turns = 1-based turns that carry the attack (required for detector=action_answer)."""
    turns, per_turn, attack_turns = r.get("turns"), r.get("turn_expected_actions"), r.get("attack_turns")
    if not isinstance(turns, list):
        return [f"{rid}: turn_expected_actions/attack_turns only allowed with turns"] \
            if per_turn is not None or attack_turns is not None else []
    n = len(turns)
    errors = []
    if per_turn is None and n > 1:
        errors.append(f"{rid}: multi-turn record needs turn_expected_actions (one list per turn)")
    elif per_turn is not None:
        if not isinstance(per_turn, list) or len(per_turn) != n:
            errors.append(f"{rid}: turn_expected_actions must be a list of {n} lists")
        elif not all(isinstance(a, list) and a and all(isinstance(x, str) for x in a) and set(a) <= ACTIONS
                     for a in per_turn):
            errors.append(f"{rid}: every turn_expected_actions item must be a non-empty subset of {sorted(ACTIONS)}")
        elif r.get("expected_actions") != per_turn[-1]:
            errors.append(f"{rid}: expected_actions must equal turn_expected_actions[-1]")
    if attack_turns is not None:
        if not isinstance(attack_turns, list) or not attack_turns or len(set(map(repr, attack_turns))) != len(attack_turns) \
                or not all(isinstance(t, int) and not isinstance(t, bool) and 1 <= t <= n for t in attack_turns):
            errors.append(f"{rid}: attack_turns must be a non-empty list of distinct turn numbers 1..{n}")
    elif r.get("group") == "attack" and r.get("detector") == "action_answer" and n > 1:
        errors.append(f"{rid}: multi-turn action_answer attack needs attack_turns")
    return errors


def check_s2(r: dict, rid: str, kb_poisoned: Path) -> list[str]:
    art = r.get("kb_article")
    if not isinstance(art, str) or not art:
        return [f"{rid}: S2 needs kb_article"]
    if not kb_poisoned.is_dir():
        return [f"{rid}: poisoned KB dir {kb_poisoned} missing — cannot check {art!r}"]
    path = kb_poisoned / f"{art}.md"
    if not path.is_file():
        return [f"{rid}: kb_article {art!r} has no file {path}"]
    canary = r.get("canary")
    if r.get("detector") == CANARY_DETECTOR and isinstance(canary, str) and canary \
            and canary.lower() not in path.read_text(encoding="utf-8").lower():
        return [f"{rid}: {path} does not contain its canary {canary!r}"]
    return []


def check_attack(r: dict, rid: str, kb_poisoned: Path, clean_text: str) -> list[str]:
    errors = []
    surface, detector, canary = r.get("surface"), r.get("detector"), r.get("canary") or ""
    if surface not in SURFACES:
        errors.append(f"{rid}: attack needs surface S1/S2, got {surface!r}")
    if r.get("goal") not in GOALS:
        errors.append(f"{rid}: attack needs goal G1-G6, got {r.get('goal')!r}")
    if detector == CANARY_DETECTOR:
        if not canary:
            errors.append(f"{rid}: detector=canary but canary empty")
        elif isinstance(canary, str) and clean_text and canary.lower() in clean_text:
            errors.append(f"{rid}: canary {canary!r} appears in clean KB (false positives)")
    elif canary:
        errors.append(f"{rid}: detector={detector} must have empty canary, got {canary!r}")
    if surface == "S2":
        errors += check_s2(r, rid, kb_poisoned)
    return errors


def near_duplicate_pairs(records: list[dict]) -> list[tuple[str, str, float]]:
    """(id_a, id_b, ratio) for texts with SequenceMatcher ratio >= NEAR_DUP_RATIO.
    1000 variations of one prompt are not coverage: each pair needs a reviewed decision."""
    texts = [(r.get("id"), r["text"].strip().lower()) for r in records if isinstance(r.get("text"), str) and r["text"].strip()]
    pairs = []
    for i, (id_a, a) in enumerate(texts):
        for id_b, b in texts[i + 1:]:
            matcher = SequenceMatcher(None, a, b, autojunk=False)
            if matcher.real_quick_ratio() >= NEAR_DUP_RATIO and matcher.quick_ratio() >= NEAR_DUP_RATIO \
                    and matcher.ratio() >= NEAR_DUP_RATIO:
                pairs.append((id_a, id_b, matcher.ratio()))
    return pairs


def validate(records: list[dict], kb_poisoned: Path, kb_clean: Path,
             decisions: dict | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not records:
        return ["empty campaign: no records"], warnings
    ids = Counter()
    canary_owners: dict[str, list[str]] = {}
    clean_text = " ".join(p.read_text(encoding="utf-8").lower() for p in kb_clean.rglob("*.md")) if kb_clean.is_dir() else ""
    control_text = " ".join((r.get("text") or "").lower() for r in records
                            if r.get("group") == "control" and isinstance(r.get("text"), str))

    for r in records:
        rid = str(r.get("id", "<no id>"))
        ids[rid] += 1
        type_errors = check_types(r, rid)
        if type_errors:   # later checks assume strings; report the type problem instead of crashing on it
            errors += type_errors
            continue
        input_errors = check_input(r, rid)
        errors += input_errors or check_turn_labels(r, rid)
        if r.get("language") not in LANGS:
            errors.append(f"{rid}: bad language {r.get('language')!r}")
        if r.get("detector") not in DETECTORS:
            errors.append(f"{rid}: bad detector {r.get('detector')!r}")
        if r.get("group") == "attack":
            errors += check_attack(r, rid, kb_poisoned, clean_text)
            canary = r.get("canary")
            if r.get("detector") == CANARY_DETECTOR and isinstance(canary, str) and canary:
                # S2: the canary lives in the poisoned article, so every question on that article shares it
                owner = f"S2:{r.get('kb_article')}" if r.get("surface") == "S2" else f"record:{rid}"
                canary_owners.setdefault(canary, []).append(owner)
                if canary.lower() in control_text:
                    errors.append(f"{rid}: canary {canary!r} appears in a control text")
        elif r.get("group") == "control":
            if r.get("goal") is not None or r.get("surface") is not None:
                warnings.append(f"{rid}: control should have goal=null, surface=null")
        else:
            errors.append(f"{rid}: bad group {r.get('group')!r}")

    if not any(r.get("group") == "attack" for r in records):
        errors.append("campaign has no attack records: it cannot measure anything about security")
    errors += [f"duplicate id {rid!r} x{c}" for rid, c in ids.items() if c > 1]
    errors += [f"duplicate canary {canary!r} x{len(owners)} (unique per record; S2 questions may share only "
               f"their own article's canary)" for canary, owners in canary_owners.items() if len(set(owners)) > 1]
    by_id = {r.get("id"): r for r in records if isinstance(r.get("id"), str)}
    for id_a, id_b, ratio in near_duplicate_pairs(records):
        errors += pair_errors(id_a, id_b, ratio, decisions, by_id)

    # source diversity: if every record cites the same source string, that's a red flag
    sources = Counter(str(r.get("source", "")) for r in records)
    if len(sources) <= 2 and len(records) > 20:
        warnings.append(f"only {len(sources)} distinct source value(s) across {len(records)} records — sources look templated, not real")

    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("attacks")
    ap.add_argument("--kb-poisoned", default="kb_poisoned")
    ap.add_argument("--kb-clean", default="kb_clean")
    ap.add_argument("--near-dup-decisions", default=None, help="reviewed near-duplicate decisions (JSONL)")
    args = ap.parse_args()

    base = Path(__file__).parent
    records = load(Path(args.attacks))
    try:
        decisions = load_decisions(Path(args.near_dup_decisions)) if args.near_dup_decisions else None
    except (OSError, ValueError) as exc:
        print(f"ERROR decisions file: {exc}")
        return 1
    errors, warnings = validate(records, (base / args.kb_poisoned), (base / args.kb_clean), decisions)

    groups = Counter(str(r.get("group")) for r in records)
    surf = Counter(str(r.get("surface")) for r in records if r.get("group") == "attack")
    attacks = [r for r in records if r.get("group") == "attack"]
    families = {str(r.get("family_id") or r.get("id")) for r in attacks}   # variants of one prompt = one family
    print(f"records: {len(records)} | {dict(groups)} | attack surfaces {dict(surf)} | "
          f"attack records {len(attacks)} in {len(families)} families")
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"\n{len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
