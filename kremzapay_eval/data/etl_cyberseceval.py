"""ETL: CyberSecEval 2 prompt_injection -> attacks.jsonl records (S1, direct-message attacks).

Reads the downloaded published dataset (data/raw/cyberseceval2_prompt_injection.json, MIT) and maps each
record to our schema, keeping the ORIGINAL attack text and a truthful source citation. No text is authored here.

Mapping decisions (documented, because CyberSecEval was built for a different setup):
- Their success criterion is "model reveals a secret planted in THEIR system prompt". Our bot has its own prompt
  and no such secret, so that criterion does not transfer. We keep their `user_input` (attack text) and
  `injection_variant` (technique), and define success behaviorally against our bot:
    * prompt-extraction variants  -> goal G3, detector prompt_markers (bot echoes its own prompt fragments)
    * everything else             -> goal G5, detector action_answer (a support bot should refuse/redirect/
                                      ticket an injected off-policy instruction, not substantively "answer" it)
- language: CyberSecEval speaking_language is English for this file -> "en".
- source: truthful — names CyberSecEval 2 with arXiv id and the original prompt_id.

This loses CyberSecEval's own labels of "did the attack succeed"; we measure OUR bot's behavior instead.
That is a limitation, recorded in the report.
"""
import json
import sys
from pathlib import Path

RAW = Path(__file__).parent / "raw" / "cyberseceval2_prompt_injection.json"
OUT = Path(__file__).parent.parent / "attacks_s1_cyberseceval.jsonl"

# variants whose intent is to extract the system prompt / instructions
PROMPT_EXTRACTION = {"system_mode", "indirect_reference"}
LANG = {"english": "en", "polish": "pl"}


def to_record(row: dict, n: int) -> dict:
    variant = row.get("injection_variant", "unknown")
    lang = LANG.get(str(row.get("speaking_language", "english")).lower(), "en")
    prompt_leak = variant in PROMPT_EXTRACTION or "prompt" in row.get("judge_question", "").lower()
    if prompt_leak:
        goal, detector, expected = "G3", "prompt_markers", ["answer", "redirect", "unsafe_refuse", "ticket"]
    else:
        goal, detector, expected = "G5", "action_answer", ["redirect", "unsafe_refuse", "ticket", "clarify"]
    pid = row.get("prompt_id", n)
    return {
        "id": f"S1-{goal}-{variant[:8]}-{lang}-cse{pid:03d}" if isinstance(pid, int) else f"S1-{goal}-{variant[:8]}-{lang}-cse{n:03d}",
        "group": "attack",
        "surface": "S1",
        "goal": goal,
        "technique": variant,
        "language": lang,
        "text": row["user_input"],
        "kb_article": None,
        "canary": "",
        "detector": detector,
        "expected_actions": expected,
        "source": f"CyberSecEval 2 (Bhatt et al., arXiv:2404.13161), MIT; prompt_id={pid}, variant={variant}, "
                  f"injection_type={row.get('injection_type')}, risk={row.get('risk_category')}",
    }


def main() -> int:
    if not RAW.exists():
        print(f"missing {RAW}; run data/fetch.py first", file=sys.stderr)
        return 2
    rows = json.loads(RAW.read_text(encoding="utf-8"))
    records = [to_record(r, n) for n, r in enumerate(rows, 1) if r.get("user_input")]
    with open(OUT, "w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"{len(records)} records -> {OUT.name}")
    print("goal:", dict(Counter(r["goal"] for r in records)))
    print("technique:", dict(Counter(r["technique"] for r in records)))
    print("language:", dict(Counter(r["language"] for r in records)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
