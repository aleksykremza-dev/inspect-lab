# Research: red-team eval methodology & reporting (2026-10-06)

Source: research agent, primary sources only. **V** = verified against the fetched source, **U** = unverified / agent's own derivation.
Used for: dataset schema (PLAN §5), report structure (PLAN §10), severity scale, statistics, unattended-run settings (PLAN §8).

---

## 1. How mature eval datasets are structured

| Dataset | Per-sample fields | Status / source |
|---|---|---|
| CyberSecEval 2/3 prompt_injection.json | `prompt_id`, `test_case_prompt` (system prompt stating a rule), `user_input`, `judge_question`, `injection_variant` (12: ignore_previous_instructions, indirect_reference, token_smuggling, system_mode, different_user_input_language, overload_with_information, few_shot_attack, many_shot_attack, repeated_token_attack, persuasion, payload_splitting, output_formatting_manipulation), `injection_type` (direct/indirect), `risk_category` (security-violating / logic-violating), `speaking_language` | V https://raw.githubusercontent.com/meta-llama/PurpleLlama/main/CybersecurityBenchmarks/datasets/prompt_injection/prompt_injection.json ; paper: "all tested models showed between 26% and 41% successful prompt injection tests" V https://arxiv.org/abs/2404.13161 |
| AgentDojo | `UserTask`: PROMPT, GROUND_TRUTH_OUTPUT, `utility()`; `InjectionTask`: GOAL, `security()`. 97 user tasks, 27 injection tasks, 629 security cases | V https://agentdojo.spylab.ai/concepts/task_suite_and_tasks/ , https://arxiv.org/html/2406.13352 |
| BIPIA | 5 tasks (Email QA 100, Web QA 1000, Table QA 1000, Summarization 1000, Code QA 100); 30 text + 20 code attack types × 5 instructions; categories task-irrelevant / task-relevant / targeted; position beginning/middle/end ("End placement achieves highest ASR") | V https://arxiv.org/html/2312.14197 , https://github.com/microsoft/BIPIA |
| Inspect `Sample` | `input`, `choices`, `target`, `id`, `metadata` (arbitrary; usable in filters and scorers via `state.metadata`), `sandbox`, `files`, `setup` | V https://inspect.aisi.org.uk/datasets.html |
| inspect_evals contribution | `eval.yaml` (fast, sandbox, requires.internet/gpu, kind); criteria: well-established, non-saturated, comparable baseline, credibly sourced; "Manually verify that the evaluation successfully runs e2e" | V https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/CONTRIBUTING.md |

A single canonical schema `technique / goal / surface / language / canary / expected_behavior / source` — **U** (no one source uses all); mapping: injection_variant→technique, GOAL/judge_question→goal, injection_type+BIPIA task→surface, speaking_language→language, CyberSecEval secret word→canary.

### Control group / utility under attack

| Dataset | Mechanism | |
|---|---|---|
| AgentDojo | **Benign utility** = user tasks solved with no attack; **Utility under attack** = user task solved AND no adversarial side effect; **Targeted ASR** = attacker goal met. Untargeted/DoS = 1 − utility under attack. Two functions per case: `utility()` and `security()` | V |
| BIPIA | ASR reported alongside original-task performance on **BIPIA-Clean** (same prompts, no injection) | V |
| CyberSecEval 2 | no in-set control; separate **False Refusal Rate** benchmark | V |
| Claude 4 system card | pairs violative-request evals (harmless rate) with benign-request evals (over-refusal); agentic coding 150 prohibited + 50 borderline + 50 benign | V (PDF pp.12–14, 21) |

**Takeaway:** every attacked sample needs a **clean twin** (same user question, no injection) and two independent scorers — `task_ok` and `attack_ok`. Report 2×2: benign utility, utility under attack, targeted ASR, untargeted degradation.

---

## 2. Reporting standards

| Source | Prescribes | |
|---|---|---|
| Microsoft — Planning red teaming for LLMs | per example: date, unique id of input/output pair, input, output; report: top issues, link to raw data, next-round plan; "make clear which endpoints were used"; **differentiate identification from measurement**; content warning | V https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/red-teaming |
| Microsoft AIRT "Lessons from 100 GenAI products" | finding ontology: **System / Actor / TTPs (MITRE) / Weakness / Impact**; "AI red teaming is not safety benchmarking" | V https://arxiv.org/html/2501.07238v1 |
| NIST AI 600-1 | MS-2.7-007 red-team for prompt injection; MS-2.8-002 document instructions given to red-teamers; MG-2.4-003 remediation timelines; results need "additional analysis before… governance" | V https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf |
| OWASP GenAI Red Teaming Guide v1.0 (Jan 2025) | RoE: testing environment, approved tools/techniques, documentation standards, escalation, data handling, rollback, permissions, ethical boundaries. Finding = "test case, evidence collected, impact assessment, specific recommendations". Metrics: ASR/JSR, detection rate. "Re-test after implementing fixes." | V https://genai.owasp.org/resource/genai-red-teaming-guide/ |
| UK AISI pre-deployment reports | domains, methods (QA, agent tasks, probing, red teaming), results vs baselines, caveat "smaller differences may fall within the margins of error" | V https://www.aisi.gov.uk/work/pre-deployment-evaluation-of-anthropics-upgraded-claude-3-5-sonnet |
| Anthropic Claude 4 system card | safeguards tables as point rates ("Attack prevention score without/with safeguards 71%→89%, ~600 scenarios"), explicit "does not cover all possible jailbreaks" | V |

### Report outline (synthesis — mapping is the agent's)

| # | Section | Content |
|---|---|---|
| 0 | Content warning + handling | policy for adversarial strings in the doc |
| 1 | Executive summary | top issues, headline ASR by severity, go/no-go |
| 2 | System under test | commit, model+version, KB snapshot, guardrails, **endpoint used** |
| 3 | Scope & rules of engagement | surfaces in/out, data handling, techniques, stop/rollback, permissions |
| 4 | Threat model | actors, assets, impacts |
| 5 | Methodology | task design, schema, clean-twin control, scorers, N per cell, determinism |
| 6 | Results — aggregate | 2×2 table + Wilson 95% CI per cell; by technique × surface × language |
| 7 | Findings (one card each) | id, title, severity, System/Actor/TTP/Weakness/Impact, reproduction (sample id + log + input), evidence, rate k/N + CI, remediation, retest |
| 8 | Identification vs measurement | which numbers are prevalence vs existence proofs |
| 9 | Limitations | coverage, judge error, dataset bias, time |
| 10 | Remediation plan & retest | owner, timeline, criteria |
| 11 | Appendices | log dir, dataset manifest, prompts, run config, CLI |

---

## 3. Severity

| Scale | Key points | |
|---|---|---|
| Microsoft MSRC AI bug bar | PI **Critical**: exfiltrate another user's data / privileged action, zero-click; **Important**: same with user interaction; **system-prompt extraction is NOT a vulnerability** | V https://www.microsoft.com/en-us/msrc/aibugbar |
| OWASP Risk Rating | likelihood × impact, 0–9 each; <3 Low, 3–6 Medium, 6–9 High | V https://community.owasp.org/OWASP_Risk_Rating_Methodology |
| OWASP GenAI RT Guide | Critical / High / Medium / Low by urgency | V |
| 0DIN | Low: single-turn unsafe output, no exfil; Medium: multi-turn, system-prompt extraction, reproducible across models; High: exfil of RAG sources/context, tool-call abuse, multi-step chain; Severe: RCE, cross-tenant | V https://0din.ai/marketing/bug_bounty |
| CVSS debate | arXiv 2412.20087: existing scoring yields minimal variation across 56 LLM attacks | V |

### Practical 4-level scale for a support RAG bot (agent synthesis — **U**)

| Level | Criteria | Our goals |
|---|---|---|
| **S1 Critical** | cross-customer data / unauthorised action, zero-click; RAG source or PII exfil to attacker sink | (not in scope of this bot — no tools) |
| **S2 High** | attacker-controlled **external link/contact** delivered as official; **false policy statement** creating liability | G2, G1 |
| **S3 Medium** | out-of-role behaviour; prompt/config leakage; refusal bypass without data exposure | G4, G3, G5 |
| **S4 Low** | harmless off-policy text; non-reproducible (<5%, CI includes 0) | — |

Adjust one step by likelihood: Wilson lower bound ≥ 0.5 → +1; attack requires privileged KB write → −1.

---

## 4. Statistics for small N

- Wald interval collapses to zero width at p̂=0 or 1 and can overshoot [0,1]; **Wilson** doesn't. Brown, Cai & DasGupta 2001: "recommend the Wilson interval… for small n". V https://projecteuclid.org/journals/statistical-science/volume-16/issue-2/Interval-Estimation-for-a-Binomial-Proportion/10.1214/ss/1009213286.full
- Inspect ships **`ci_wilson()`** ("Prefer this over ci() for binary scores… bounds always stay within [0,1]"), plus `stderr(cluster="key")` for clustered SE, `grouped()`, `bootstrap_stderr()`. V https://inspect.aisi.org.uk/metrics.html
- AgentDojo: 95% CI via `statsmodels proportion_confint`. V
- Anthropic "Adding Error Bars to Evals": CLT SE, clustered SE for grouped questions, paired differences when comparing two systems, power analysis. V https://arxiv.org/html/2411.00640v1
- Minimum N per cell: no authoritative source (**U**).

### Recipe (agent derivation — verify with `proportion_confint(k, n, method="wilson")`)
1. Every rate as **k/N with Wilson 95% CI**; `ci_wilson()` per cell; `stderr(cluster=technique or source_doc)` when samples share a template.
2. Widths: 0/20 → [0, 0.16]; 0/50 → [0, 0.07]; 0/100 → [0, 0.04]; 10/20 → [0.30, 0.70]; 50/100 → [0.40, 0.60].
3. Cell sizes: N=20 triage (detects ASR ≥ ~15%); N≥50 where a threshold matters; N≈100 for before/after comparison as **paired differences**.
4. Separate denominators: ASR over attacked only; utility over clean twins; publish `scored_samples`/`unscored_samples`.

---

## 5. Unattended runs with Inspect (official docs)

| Topic | Fact | Source |
|---|---|---|
| eval-set | auto-retries failed tasks, reuses completed samples, re-run = resume; one `--log-dir` per campaign; `--retry-attempts` 10, `--retry-wait` 30s exponential (max 1h); re-running a finished set is a no-op | V https://inspect.aisi.org.uk/eval-sets.html |
| Sample `id` | explicit id on every sample, else resume/shuffle breaks | V |
| fail_on_error | default True (fail on first error); `--fail-on-error=0.1` = fail if >10% errors; `--no-fail-on-error` | V https://inspect.aisi.org.uk/handling-errors.html |
| retry_on_error / score_on_error | `--retry-on-error=3`; errored unscored samples excluded from denominators, counted in `scored_samples`/`unscored_samples` | V https://inspect.aisi.org.uk/scoring-policy.html |
| eval-retry | `inspect eval-retry logs/<file>` reuses completed samples | V |
| limits | `--time-limit`, `--token-limit`, `--message-limit` per sample | V https://inspect.aisi.org.uk/tasks.html |
| connections | `--max-connections` (docs disagree: 10 vs adaptive up to 100 → **pin explicitly**); `max_samples` = max_connections+1 | V options.html, models-concurrency.html |
| logs | `--log-dir`/`INSPECT_LOG_DIR`; `.eval` default; `inspect log list --json --status error` | V eval-logs.html |
| preflight | no dry-run mode; use `--limit 3 --debug-errors`; inspect_evals rule "verify e2e on a few samples" | V |

Checklist (agent bundle — **U** as a whole): explicit ids → `--limit 3 --debug-errors` smoke → dedicated log-dir → `inspect eval-set … --fail-on-error=0.05 --retry-on-error=2 --max-connections 2 --time-limit …` → on wake-up `inspect log list --status error` then eval-retry → `--bundle-dir` for viewer → report scored/unscored counts.

---

## Not verified / gaps
AISI "Our approach to evaluations" page didn't render; PyRIT memory schema 404; CyberSecEval 3 version attribution; BIPIA per-record keys; Wilson widths and the 4-level scale are derivations; `max_connections` default conflict unresolved.
