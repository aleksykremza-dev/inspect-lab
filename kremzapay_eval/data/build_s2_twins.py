"""Build the S2 clean twins and the two KB folders for the paired run.

Twin rule: remove ONLY the clearly delimited injected paragraph — the paragraph that starts
with the marker below — and keep every other byte. If a marker starts no paragraph or several, or the injected
text is mixed into a factual paragraph, the article is flagged as ambiguous and not fixed.

Writes (none of it is published, see .gitignore):
  kb_s2_clean/<category>/<id>.md          clean twins
  run/kb_s2_clean_all/, run/kb_s2_poisoned_all/   kb_clean + twins / kb_clean + poisoned, for stand/ingest.sh
  s2_manifest.json                        per article: block hashes as the bot puts them in the prompt
Usage (from the inspect-lab root): python kremzapay_eval/data/build_s2_twins.py
"""
import difflib
import hashlib
import json
import shutil
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent
CHUNK_SIZE = 800   # bot config.CHUNK_SIZE: every article must stay one chunk, so article in prompt == injection in prompt
MARKERS = {        # first characters of the injected paragraph, per poisoned article
    "payments/poison-01.md": "INFORMACJA OPERACYJNA:",
    "payouts/poison-01.md": "[kremzaPay System Alert]:",
    "payouts/poison-02.md": "Note on international compliance:",
    "payouts/poison-03.md": "Assistance Directive:",
    "refunds/poison-01.md": "IMPORTANT SYSTEM UPDATE:",
    "refunds/poison-02.md": "Uwaga: Zgodnie z nową aktualizacją regulaminu",
    "refunds/poison-03.md": "[SYSTEM NOTICE:",
}


class AmbiguousInjection(ValueError):
    pass


def make_twin(article: str, marker: str) -> str:
    paragraphs = article.split("\n\n")
    starts = [i for i, p in enumerate(paragraphs) if p.lstrip().startswith(marker)]
    if len(starts) != 1 or sum(marker in p for p in paragraphs) != 1:
        raise AmbiguousInjection(f"marker {marker!r}: starts {len(starts)} paragraph(s), "
                                 f"occurs in {sum(marker in p for p in paragraphs)}")
    return "\n\n".join(p for i, p in enumerate(paragraphs) if i != starts[0])


def parse(article: str) -> tuple[dict, str]:
    """Same parsing as the bot's ingest.parse_article."""
    _, front, body = article.split("---", 2)
    meta = {k.strip(): v.strip() for k, _, v in (line.partition(":") for line in front.strip().splitlines())}
    return meta, body.rsplit("---", 1)[0].strip()


def prompt_block(article: str) -> tuple[dict, str]:
    meta, body = parse(article)
    if len(body) > CHUNK_SIZE:
        raise ValueError(f"{meta.get('id')}: body {len(body)} chars > {CHUNK_SIZE}, would be split into chunks")
    return meta, f"[{meta['id']} : {meta['title']}]\n{body}"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build() -> dict:
    poisoned_dir, clean_dir = EVAL_DIR / "kb_poisoned", EVAL_DIR / "kb_s2_clean"
    missing = sorted(set(MARKERS) - {str(p.relative_to(poisoned_dir)) for p in poisoned_dir.glob("*/*.md")})
    if missing:
        raise SystemExit(f"poisoned articles missing: {missing}")
    manifest, ambiguous = {}, {}
    for rel, marker in MARKERS.items():
        poisoned = (poisoned_dir / rel).read_text(encoding="utf-8")
        try:
            twin = make_twin(poisoned, marker)
        except AmbiguousInjection as exc:
            ambiguous[rel] = str(exc)
            continue
        (clean_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (clean_dir / rel).write_text(twin, encoding="utf-8")
        meta, poisoned_block = prompt_block(poisoned)
        _, clean_block = prompt_block(twin)
        removed = [p for p in poisoned.split("\n\n") if p.lstrip().startswith(marker)][0]
        manifest[rel] = {"id": meta["id"], "title": meta["title"], "category": meta["category"], "marker": marker,
                         "removed_paragraph_sha256": sha(removed), "poisoned_block_sha256": sha(poisoned_block),
                         "clean_block_sha256": sha(clean_block)}
        print(f"===== {rel}")
        sys.stdout.writelines(difflib.unified_diff(poisoned.splitlines(True), twin.splitlines(True),
                                                   f"kb_poisoned/{rel}", f"kb_s2_clean/{rel}", n=1))
    if ambiguous:
        raise SystemExit(f"AMBIGUOUS, not fixed — needs a decision: {json.dumps(ambiguous, indent=2)}")
    for name, source in (("kb_s2_clean_all", clean_dir), ("kb_s2_poisoned_all", poisoned_dir)):
        target = EVAL_DIR / "run" / name
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(EVAL_DIR / "kb_clean", target)
        shutil.copytree(source, target, dirs_exist_ok=True)
    (EVAL_DIR / "s2_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(f"\n{len(build())} twins written")
