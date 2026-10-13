"""Build a campaign file from attacks.jsonl without touching the source.

1. Records identical in every field except id and source are merged: the first is kept, every source is
   kept (joined with " || ") and merged_ids lists all original ids. A different prompt_id alone is
   provenance, not a new test case.
   Near-duplicate variants get one family_id (connected near-duplicate pairs; first id in file order).
   Families are counted apart from records: variants of one prompt are not independent coverage.
2. Reviewed decisions (kremzapay_eval/near_dup_decisions.py) are applied: "drop" removes drop_id. A decision
   whose hashes no longer match the merged records is stale and stops the build.
3. Remaining near-duplicate pairs go to a TSV for manual review, with record hashes to copy into a decision.
   The threshold is not relaxed here — the validator stays red until every pair has a valid decision.

Usage (from the inspect-lab root):
    python kremzapay_eval/data/build_campaign.py kremzapay_eval/attacks.jsonl \
        kremzapay_eval/campaign_s1.jsonl kremzapay_eval/near_dups_review.tsv [kremzapay_eval/near_dup_decisions.jsonl]
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # repo root

from kremzapay_eval.near_dup_decisions import load_decisions, record_hash, stale_ids
from kremzapay_eval.validate_attacks import load, near_duplicate_pairs

SOURCE_SEP = " || "
REVIEW_COLUMNS = ("id_a", "id_b", "hash_a", "hash_b", "ratio", "differing_fields", "text_a", "text_b", "decision")


def content_key(record: dict) -> str:
    return json.dumps({k: v for k, v in record.items() if k not in ("id", "source")}, sort_keys=True,
                      ensure_ascii=False)


def merge_duplicates(records: list[dict]) -> tuple[list[dict], list[tuple[str, str]]]:
    """Returns (records with duplicates merged into their first occurrence, [(merged id, kept id)])."""
    first: dict[str, int] = {}
    kept: list[dict] = []
    merged: list[tuple[str, str]] = []
    for record in records:
        key = content_key(record)
        if key not in first:
            first[key] = len(kept)
            kept.append(record)
            continue
        base = kept[first[key]]
        sources = base["source"].split(SOURCE_SEP)
        kept[first[key]] = {
            **base,
            "source": SOURCE_SEP.join(sources + [record["source"]] if record["source"] not in sources else sources),
            "merged_ids": base.get("merged_ids", [base["id"]]) + [record["id"]],
        }
        merged.append((record["id"], base["id"]))
    return kept, merged


def assign_families(records: list[dict]) -> list[dict]:
    """family_id = first id (file order) of each connected group of near-duplicate records."""
    order = {r["id"]: n for n, r in enumerate(records)}
    parent = {r["id"]: r["id"] for r in records}

    def root(i: str) -> str:
        while parent[i] != i:
            i = parent[i]
        return i

    for id_a, id_b, _ in near_duplicate_pairs(records):
        ra, rb = root(id_a), root(id_b)
        if ra != rb:
            first, second = sorted((ra, rb), key=order.get)
            parent[second] = first
    return [{**r, "family_id": root(r["id"])} for r in records]


def apply_decisions(records: list[dict], decisions: dict) -> tuple[list[dict], list[str]]:
    """Every decision whose two records are in the campaign must still match their hashes (keep_both too),
    otherwise the build stops before any file is written."""
    by_id = {r["id"]: r for r in records}
    applicable = [d for d in decisions.values() if all(i in by_id for i in d["ids"])]
    stale = [f"{d['action']} {sorted(d['ids'])}: {stale_ids(d, by_id)}" for d in applicable if stale_ids(d, by_id)]
    if stale:
        raise ValueError("stale decision(s), records changed since review: " + "; ".join(stale))
    dropped = sorted({d["drop_id"] for d in applicable if d["action"] == "drop"})
    return [r for r in records if r["id"] not in dropped], dropped


def current_decision(decisions: dict, id_a: str, id_b: str, by_id: dict) -> str:
    d = decisions.get(frozenset((id_a, id_b)))
    if d is None:
        return ""
    return "STALE" if stale_ids(d, by_id) else d["action"]


def review_rows(records: list[dict], decisions: dict) -> list[list[str]]:
    by_id = {r["id"]: r for r in records}
    clean = lambda text: " ".join(str(text).split())   # TSV-safe: no tabs/newlines inside a cell
    rows = []
    for id_a, id_b, ratio in near_duplicate_pairs(records):
        a, b = by_id[id_a], by_id[id_b]
        differing = sorted(k for k in (a.keys() | b.keys()) - {"id"} if a.get(k) != b.get(k))
        rows.append([id_a, id_b, record_hash(a), record_hash(b), f"{ratio:.3f}", ",".join(differing),
                     clean(a.get("text")), clean(b.get("text")), current_decision(decisions, id_a, id_b, by_id)])
    return rows


def build(source: Path, out: Path, review: Path, decisions_path: Path | None = None) -> dict:
    if source.resolve() in (out.resolve(), review.resolve()):
        raise ValueError("refusing to overwrite the source file")
    records = load(source)
    decisions = load_decisions(decisions_path) if decisions_path else {}
    merged_records, merged = merge_duplicates(records)
    kept, dropped = apply_decisions(assign_families(merged_records), decisions)   # hashes cover family_id
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")
    rows = review_rows(kept, decisions)
    review.write_text("\n".join("\t".join(row) for row in [list(REVIEW_COLUMNS), *rows]) + "\n", encoding="utf-8")
    attacks = [r for r in kept if r.get("group") == "attack"]
    return {"source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "records": len(records), "kept": len(kept), "attack_records": len(attacks),
            "attack_families": len({r["family_id"] for r in attacks}),
            "merged": merged, "dropped_by_decision": dropped, "near_duplicate_pairs": len(rows),
            "pairs_without_valid_decision": sum(row[-1] in ("", "STALE") for row in rows)}


def main() -> int:
    if len(sys.argv) not in (4, 5):
        print(__doc__)
        return 2
    paths = [Path(arg) for arg in sys.argv[1:]]
    try:
        summary = build(*paths)
    except ValueError as exc:
        print(f"ERROR {exc}")
        return 1
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
