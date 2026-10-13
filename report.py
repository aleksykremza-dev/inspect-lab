"""Re-score saved injection logs with the current judge_answer() and print a results table with stderr.

Model answers are taken from the logs, so no model is called. Usage:  python report.py [log_dir]
"""
import math
import sys

from inspect_ai.log import list_eval_logs, read_eval_log

from injection import judge_answer


def mean_and_stderr(values: list[int]) -> tuple[float, float]:
    n = len(values)
    if n == 0:
        return float("nan"), float("nan")
    p = sum(values) / n
    return p, math.sqrt(p * (1 - p) / n)


def fmt(values: list[int]) -> str:
    p, se = mean_and_stderr(values)
    return f"{p:.2f} ± {se:.2f}"


def summarize(log) -> dict:
    injected, clean = [], []
    for sample in log.samples:
        verdict = judge_answer(sample.output.completion, sample.metadata["canary"])
        stored = sample.scores["injection_scorer"].value
        row = {"new": verdict, "old": stored}
        (injected if sample.metadata["injected"] else clean).append(row)
    return {
        "asr": [r["new"]["attack_success"] for r in injected],
        "asr_old": [r["old"]["attack_success"] for r in injected],
        "td_inj": [r["new"]["task_done_proxy"] for r in injected],
        "td_clean": [r["new"]["task_done_proxy"] for r in clean],
    }


def main(log_dir: str = "./logs") -> None:
    print("| run (UTC) | model | defense | N inj/clean | ASR | ASR (old scorer) | task_done_proxy injected | task_done_proxy clean |")
    print("|---|---|---|---|---|---|---|---|")
    for info in sorted(list_eval_logs(log_dir), key=lambda i: i.name):
        log = read_eval_log(info)
        if log.eval.task != "injection" or log.status != "success" or log.eval.model.startswith("mockllm/"):
            continue
        s = summarize(log)
        print(
            f"| {log.eval.created[:16]} | {log.eval.model} | {log.eval.task_args.get('with_defense', False)} "
            f"| {len(s['asr'])}/{len(s['td_clean'])} | {fmt(s['asr'])} | {fmt(s['asr_old'])} "
            f"| {fmt(s['td_inj'])} | {fmt(s['td_clean'])} |"
        )


if __name__ == "__main__":
    main(*sys.argv[1:])
