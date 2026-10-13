# BACKLOG — noticed along the way, not part of the current task

- README Reproduction (S2/S1): temperature 0 is a literal in the bot's `llm.py` (recorded clean stand commit for S2), not an env default; only `LLM_SEED` / `LLM_THINK` depend on env and were not recorded. Wording "code defaults" can be made precise. (2026-10-12)
- README S1 (T-39): "37 reached retrieval and got no answer" is imprecise — L3_generator_no_answer means the answer model was called and returned NO_ANSWER; of the 40 not stopped before generation, 39 reached the answer model (37 NO_ANSWER, 2 rejected by L4) and 1 stopped at service status. (2026-10-12)
