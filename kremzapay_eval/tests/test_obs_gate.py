"""obs_gate: an obs record passes only if it is complete for the stages the dialog went through.
Good records mirror what the stand (7b68528) writes; each bad case removes or empties one thing."""
import copy

import pytest

from kremzapay_eval.obs_gate import CONFIG_KEYS, sample_obs_problems

CONFIG = {k: 1 for k in CONFIG_KEYS}


def _call(purpose, attempt=1, error=None):
    call = {"purpose": purpose, "attempt": attempt, "model": "qwen2.5:7b-instruct", "think": False, "format": None,
            "options": {"temperature": 0, "num_predict": 400 if purpose == "answer" else 5, "seed": 42},
            "prompt_sha256": "p" * 64, "prompt_chars": 700}
    if error:
        return {**call, "error": error}
    return {**call, "response_model": "qwen2.5:7b-instruct", "done_reason": "stop", "eval_count": 7,
            "prompt_eval_count": 11, "response_chars": 40, "response_sha256": "r" * 64}


GEN = {"candidate_raw": "Zwrot w panelu.\nŹródło: refund-how", "no_answer": False,
       "cited": [{"id": "refund-how", "chunk_sha256": "c" * 64}], "error": None}
JUDGE_YES = {"verdict_raw": "yes", "passed": True, "error": None, "chunks_sha256": ["c" * 64]}
DOCS = [{"id": "refund-how", "title": "Zwrot", "sha256": "b" * 64, "canonical_sha256": "b" * 64}]


def _meta(layer, calls, generation=None, judge=None, context_docs=DOCS, config=CONFIG):
    obs = {"schema": 2, "config": config, "llm_calls": calls}
    if generation is not None:
        obs["generation"] = generation
    if judge is not None:
        obs["judge"] = judge
    return {"obs": obs, "stopped_by": layer, "context_docs": context_docs}


GOOD = {
    "answered": _meta("L5_answered", [_call("classifier"), _call("answer"), _call("judge")], GEN, JUDGE_YES),
    "judge_rejected": _meta("L4_judge", [_call("answer"), _call("judge")], GEN, {**JUDGE_YES, "verdict_raw": "no",
                                                                                 "passed": False}),
    "judge_bad_output": _meta("L4_judge", [_call("answer"), _call("judge")], GEN,
                              {"verdict_raw": None, "passed": False, "error": "LLMBadOutput", "chunks_sha256": []}),
    "answer_bad_output": _meta("L4_judge", [_call("answer")],
                               {"candidate_raw": None, "no_answer": False, "cited": [], "error": "LLMBadOutput"}),
    "no_documents": _meta("L4_judge", [], context_docs=[]),
    "no_answer": _meta("L3_generator_no_answer", [_call("answer")],
                       {"candidate_raw": "NO_ANSWER", "no_answer": True, "cited": [], "error": None}),
    "retry_then_answered": _meta("L5_answered", [_call("answer", 1, "ConnectError: x"), _call("answer", 2),
                                                 _call("judge")], GEN, JUDGE_YES),
    "rules_stop": _meta("L0_rules", [], context_docs=None),
    "classifier_stop": _meta("L1_classifier", [_call("classifier")], context_docs=None),
}


@pytest.mark.parametrize("name", list(GOOD))
def test_complete_records_pass(name):
    assert sample_obs_problems("s", GOOD[name]) == []


def _bad(name, change):
    meta = copy.deepcopy(GOOD[name])
    change(meta["obs"], meta)
    return sample_obs_problems("s", meta)


# both of these passed the first version of the gate
def test_empty_config_and_no_calls_on_an_answered_dialog_fail():
    problems = _bad("answered", lambda o, m: o.update(config={}, llm_calls=[]))
    assert any("config must hold" in p for p in problems)
    assert any("L5_answered without a successful answer call" in p for p in problems)


def test_empty_options_and_empty_generation_and_judge_fail():
    def empty(o, m):
        o["llm_calls"][1]["options"] = {}
        o["generation"], o["judge"] = {}, {}
    problems = _bad("answered", empty)
    assert any("model call 1: options must hold" in p for p in problems)
    assert any("generation record must hold" in p for p in problems)
    assert any("judge record must hold" in p for p in problems)


@pytest.mark.parametrize("name,change,expected", [
    ("answered", lambda o, m: o["config"].pop("llm_seed"), "config must hold"),
    ("answered", lambda o, m: o["llm_calls"][1]["options"].pop("seed"), "model call 1: options must hold"),
    ("answered", lambda o, m: o["llm_calls"][1].pop("prompt_sha256"), "model call 1: model/attempt/prompt_sha256"),
    ("answered", lambda o, m: o["llm_calls"][1].pop("response_sha256"), "neither a response record nor an error"),
    ("answered", lambda o, m: o["llm_calls"][1].update(purpose="other"), "model call 1: purpose 'other'"),
    ("answered", lambda o, m: o["llm_calls"].__setitem__(0, "x"), "model call 0 is not an object"),
    ("answered", lambda o, m: o.pop("generation"), "answer model was called but no candidate record"),
    ("answered", lambda o, m: o.pop("judge"), "L5_answered without an L4 record with passed = true"),
    ("answered", lambda o, m: o["judge"].update(passed=False), "L5_answered without an L4 record with passed = true"),
    ("answered", lambda o, m: o["generation"].update(no_answer=True), "L5_answered without a successful answer call"),
    ("judge_rejected", lambda o, m: o.pop("judge"), "L4_judge: candidate went to L4 but no L4 record"),
    ("judge_rejected", lambda o, m: o["judge"].update(passed=True), "L4_judge: candidate went to L4 but no L4 record"),
    ("no_documents", lambda o, m: m.update(context_docs=DOCS), "L4_judge without an answer call although documents"),
    ("no_answer", lambda o, m: o["generation"].update(no_answer=False), "L3_generator_no_answer without"),
    ("no_answer", lambda o, m: o["llm_calls"].clear(), "L3_generator_no_answer without"),
    ("classifier_stop", lambda o, m: o.update(generation=GEN), "L1_classifier: candidate went to L4 but no L4 record"),
    ("answered", lambda o, m: o.update(schema=1), "obs schema 1 != 2"),
    ("answered", lambda o, m: m["context_docs"][0].pop("canonical_sha256"), "context_docs entry 0 must hold"),
    ("answered", lambda o, m: o.pop("llm_calls"), "llm_calls missing"),
])
def test_incomplete_records_fail(name, change, expected):
    problems = _bad(name, change)
    assert any(expected in p for p in problems), problems


def test_schema_1_campaigns_are_checked_without_the_canonical_hash():
    meta = copy.deepcopy(GOOD["answered"])
    meta["obs"]["schema"] = 1
    meta["context_docs"] = [{"id": "refund-how", "title": "Zwrot", "sha256": "b" * 64}]
    assert sample_obs_problems("s", meta, 1) == []
    assert any("context_docs entry 0" in p for p in sample_obs_problems("s", {**meta, "obs": {**meta["obs"], "schema": 2}}))


def test_missing_obs_is_reported():
    assert sample_obs_problems("s", {"stopped_by": "L5_answered"}) == ["s: no obs record"]
