"""Is a sample's stand observability record (obs schema 1) complete for the stages the dialog actually went through?

Every record needs the effective config (all keys) and a well-formed list of model calls. Each call needs purpose,
attempt, model, options with temperature / seed / num_predict, the prompt hash, and either a response record or an
error. What else is required follows from the layer that ended the dialog (stopped_by, from the bot's own DB):

  L5_answered             a successful answer call, a candidate (not NO_ANSWER), an L4 record with passed = true
  L4_judge                if the answer model was called: a candidate record; a candidate that went to L4 needs an
                          L4 record with passed = false. No answer call is allowed only when no document was found
                          (context_docs == []), which the bot also reports as generation_not_grounded.
  L3_generator_no_answer  a successful answer call and a candidate with no_answer = true
  other layers            nothing beyond config + calls; an empty call list is fine (stopped before generation)

Schema 2 additionally requires every context_docs entry to carry sha256 (block as sent) and canonical_sha256
(content, independent of prompt framing) — exposure is computed from the canonical hash.
"""
SCHEMA = 2
SCHEMAS = (1, 2)
DOC_KEYS = ("id", "title", "sha256", "canonical_sha256")
PURPOSES = ("classifier", "answer", "judge")
CONFIG_KEYS = ("answer_model", "ollama_url", "llm_seed", "llm_think", "llm_retries", "top_k", "top_n",
               "retrieval_ok", "chunk_size", "embed_model", "collection")
OPTION_KEYS = ("temperature", "seed", "num_predict")
GENERATION_KEYS = ("candidate_raw", "no_answer", "cited", "error")
JUDGE_KEYS = ("verdict_raw", "passed", "chunks_sha256", "error")
RESPONSE_KEYS = ("response_sha256", "response_chars", "done_reason")


def _missing(record, keys) -> list[str]:
    return [k for k in keys if k not in record]


def _call_problems(i: int, call) -> list[str]:
    if not isinstance(call, dict):
        return [f"model call {i} is not an object"]
    problems = []
    if call.get("purpose") not in PURPOSES:
        problems.append(f"model call {i}: purpose {call.get('purpose')!r}")
    if not call.get("model") or not isinstance(call.get("attempt"), int) or not call.get("prompt_sha256"):
        problems.append(f"model call {i}: model/attempt/prompt_sha256 missing")
    options = call.get("options")
    if not isinstance(options, dict) or _missing(options, OPTION_KEYS):
        problems.append(f"model call {i}: options must hold {OPTION_KEYS}, got {options!r}")
    if "error" not in call and _missing(call, RESPONSE_KEYS):
        problems.append(f"model call {i}: neither a response record nor an error")
    return problems


def _record_problems(name: str, record, keys) -> list[str]:
    if record is None:
        return []
    if not isinstance(record, dict) or _missing(record, keys):
        return [f"{name} record must hold {keys}, got {record!r}"]
    return []


def _stage_problems(layer: str, calls: list, generation, judge, context_docs) -> list[str]:
    answered = [c for c in calls if isinstance(c, dict) and c.get("purpose") == "answer" and "error" not in c]
    tried_answer = any(isinstance(c, dict) and c.get("purpose") == "answer" for c in calls)
    candidate = generation.get("candidate_raw") if isinstance(generation, dict) else None
    no_answer = isinstance(generation, dict) and generation.get("no_answer") is True
    went_to_l4 = candidate is not None and not no_answer
    problems = []
    if tried_answer and generation is None:
        problems.append("answer model was called but no candidate record")
    if layer == "L5_answered":
        if not answered or not went_to_l4:
            problems.append("L5_answered without a successful answer call and a candidate")
        if not (isinstance(judge, dict) and judge.get("passed") is True):
            problems.append("L5_answered without an L4 record with passed = true")
    elif layer == "L4_judge":
        if not tried_answer and context_docs != []:
            problems.append("L4_judge without an answer call although documents were found")
        if went_to_l4 and not (isinstance(judge, dict) and judge.get("passed") is False):
            problems.append("L4_judge: candidate went to L4 but no L4 record with passed = false")
    elif layer == "L3_generator_no_answer":
        if not answered or not no_answer:
            problems.append("L3_generator_no_answer without a successful answer call and a NO_ANSWER candidate")
    if went_to_l4 and judge is None and layer not in ("L5_answered", "L4_judge"):
        problems.append(f"{layer}: candidate went to L4 but no L4 record")
    return problems


def sample_obs_problems(sample_id: str, meta: dict, schema: int = SCHEMA) -> list[str]:
    """Every gap in one sample's obs record; meta = the scorer's metadata (obs, stopped_by, context_docs)."""
    obs = meta.get("obs")
    if not isinstance(obs, dict):
        return [f"{sample_id}: no obs record"]
    if obs.get("schema") != schema:
        return [f"{sample_id}: obs schema {obs.get('schema')!r} != {schema}"]
    config = obs.get("config")
    problems = [] if isinstance(config, dict) and not _missing(config, CONFIG_KEYS) else \
        [f"config must hold {CONFIG_KEYS}, got {config!r}"]
    calls = obs.get("llm_calls")
    if not isinstance(calls, list):
        return [f"{sample_id}: {p}" for p in problems + ["llm_calls missing"]]
    for i, call in enumerate(calls):
        problems += _call_problems(i, call)
    generation, judge = obs.get("generation"), obs.get("judge")
    problems += _record_problems("generation", generation, GENERATION_KEYS)
    problems += _record_problems("judge", judge, JUDGE_KEYS)
    problems += _stage_problems(str(meta.get("stopped_by")), calls, generation, judge, meta.get("context_docs"))
    if schema >= 2:
        problems += [f"context_docs entry {i} must hold {DOC_KEYS}" for i, doc in
                     enumerate(meta.get("context_docs") or []) if not isinstance(doc, dict) or _missing(doc, DOC_KEYS)]
    return [f"{sample_id}: {p}" for p in problems]
