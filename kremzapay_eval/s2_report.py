"""S2 paired-run evidence for manual review: every dialog with exposure, plus per-article absolute counts.

Exposure comes from the instrumented bot (context_docs = documents in the answer prompt) matched against
s2_manifest.json block hashes: which variant of the article the model actually saw.
Usage: python kremzapay_eval/s2_report.py logs/s2-<stamp>   -> logs/s2-<stamp>/s2_review.md (+ printed summary)
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from inspect_ai.log import list_eval_logs, read_eval_log

SCORER = "bot_scorer"
VARIANTS = ("poisoned", "clean")


def exposure(context_docs, article: dict) -> str:
    """not_generated | article_absent | poisoned_block | clean_block | other_block (hash mismatch).

    Compared with the manifest's "[id : title]\\n<text>" hashes: obs schema 2 logs carry canonical_sha256 (content,
    independent of the prompt's framing); older logs only sha256 of the sent block, which had that same format."""
    if context_docs is None:
        return "not_generated"
    docs = [d for d in context_docs if (d["id"], d["title"]) == (article["id"], article["title"])]
    if not docs:
        return "article_absent"
    sha = docs[0].get("canonical_sha256", docs[0]["sha256"])
    return {article["poisoned_block_sha256"]: "poisoned_block", article["clean_block_sha256"]: "clean_block"}.get(
        sha, "other_block")


def rows_for(log_dir: Path, variant: str, manifest: dict) -> list[dict]:
    rows = []
    for info in list_eval_logs(str(log_dir / variant), recursive=False):
        for sample in read_eval_log(info).samples or []:
            meta, score = sample.metadata, sample.scores[SCORER]
            article = manifest[meta["kb_article"] + ".md"]
            rows.append({
                "variant": variant, "id": sample.id, "article": meta["kb_article"], "goal": meta["goal"],
                "question": meta["text"], "expected_answer": meta.get("expected_answer"),
                "violation": meta.get("violation"), "reply": score.answer, "action": score.metadata.get("action"),
                "stopped_by": score.metadata.get("stopped_by"), "top_score": score.metadata.get("top_score"),
                "exposure": exposure(score.metadata.get("context_docs"), article),
                "context": [d["id"] + " : " + d["title"] for d in score.metadata.get("context_docs") or []],
                "attack_success": score.value.get("attack_success"), "needs_review": score.value.get("needs_review"),
                "error": sample.error.message if sample.error else None,
            })
    return rows


def summary(rows: list[dict]) -> dict:
    table: dict = defaultdict(lambda: defaultdict(int))
    for r in rows:
        key = (r["article"], r["variant"])
        cell = table[key]
        cell["dialogs"] += 1
        cell[f"exposure:{r['exposure']}"] += 1
        cell["detector_hit"] += int(r["attack_success"] == 1)
        cell["needs_review"] += int(r["needs_review"] == 1)
        cell[f"action:{r['action']}"] += 1
    return {f"{a} [{v}]": dict(c) for (a, v), c in sorted(table.items())}


def markdown(rows: list[dict]) -> str:
    out = ["# S2 paired run — dialogs for manual review\n"]
    for r in sorted(rows, key=lambda r: (r["article"], r["id"], r["variant"])):
        out += [f"## {r['id']} [{r['variant']}]",
                f"- article `{r['article']}` goal {r['goal']} | action **{r['action']}** | stopped_by {r['stopped_by']}"
                f" | top_score {r['top_score']} | exposure **{r['exposure']}**",
                f"- context: {r['context']}",
                f"- detector: attack_success={r['attack_success']} needs_review={r['needs_review']} error={r['error']}",
                f"- Q: {r['question']}", f"- expected: {r['expected_answer']}", f"- violation if: {r['violation']}",
                "", "```text", r["reply"] or "", "```", "", "**Manual verdict:** _TBD_", ""]
    return "\n".join(out)


def main() -> int:
    log_dir = Path(sys.argv[1])
    manifest = json.loads(Path("kremzapay_eval/s2_manifest.json").read_text(encoding="utf-8"))
    rows = [r for v in VARIANTS for r in rows_for(log_dir, v, manifest)]
    (log_dir / "s2_review.md").write_text(markdown(rows), encoding="utf-8")
    (log_dir / "s2_rows.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary(rows), indent=1))
    print(f"{len(rows)} dialogs -> {log_dir / 's2_review.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
