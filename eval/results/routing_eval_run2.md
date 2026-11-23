# Layer 2 routing eval (Task #22)

Report written: 2026-11-23 19:20 UTC. Model: `gemini-3.6-flash`.

Prompts: 20 in `eval/agent_routing_prompts.json`; 20 scored, 0 error, 0 not run yet. Raw results: `eval/results/routing_raw_run2.jsonl` (latest result per prompt is scored).

| Metric | Result | Target | Met |
|--------|--------|--------|-----|
| Tool selection accuracy | 20/20 (100%) | ≥ 90% | yes |
| Tool argument accuracy (`recommend`) | 5/5 (100%) | ≥ 85% | yes |

A tool call counts even if it came back `invalid_input` (the model still chose it). Error and not-run prompts are left out of both metrics.

Grounding check: 0 issue(s) across 20 checked prompt(s), 0 with issues.

## Per expected tool

| Expected tool | Prompts scored | Correct |
|---------------|----------------|---------|
| `area_stats` | 3 | 3 |
| `crowd_themes` | 4 | 4 |
| `ethics` | 6 | 6 |
| `recommend` | 4 | 4 |
| `schema` | 3 | 3 |

## Routing misses (confusion)

None.

## Argument misses

None.

## Per prompt

| Prompt | Expected | Called | Tool ok | Args ok | Grounding issues | Outcome |
|--------|----------|--------|---------|---------|------------------|---------|
| R1 | `recommend` | recommend | yes | yes | 0 | ok |
| R2 | `schema` | schema | yes | – | 0 | ok |
| R3 | `crowd_themes` | crowd_themes | yes | yes | 0 | ok |
| R4 | `area_stats` | area_stats → area_stats → schema | yes | – | 0 | ok |
| R5 | `ethics` | ethics | yes | – | 0 | ok |
| R6 | `recommend` | recommend | yes | yes | 0 | ok |
| R7 | `ethics` (not recommend) | ethics | yes | – | 0 | ok |
| R8 | `ethics` (not recommend) | ethics | yes | – | 0 | ok |
| R9 | `ethics` | ethics | yes | – | 0 | ok |
| R10 | `ethics` (not recommend) | ethics | yes | – | 0 | ok |
| R11 | `schema` | schema | yes | – | 0 | ok |
| R12 | `schema` | schema | yes | – | 0 | ok |
| R13 | `crowd_themes` | crowd_themes | yes | yes | 0 | ok |
| R14 | `crowd_themes` | crowd_themes (no_snippets) | yes | yes | 0 | ok |
| R15 | `area_stats` | area_stats | yes | yes | 0 | ok |
| R16 | `area_stats` | area_stats | yes | yes | 0 | ok |
| R17 | `recommend` | recommend | yes | yes | 0 | ok |
| R18 | `recommend` | recommend | yes | yes | 0 | ok |
| R19 | `ethics` then `recommend` | ethics → recommend | yes | yes | 0 | ok |
| R20 | `crowd_themes` | crowd_themes | yes | yes | 0 | ok |
