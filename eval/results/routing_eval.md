# Layer 2 routing eval (Task #22)

Report written: 2026-11-20 15:37 UTC. Model: `gemini-3.6-flash`.

Prompts: 20 in `eval/agent_routing_prompts.json`; 20 scored, 0 error, 0 not run yet. Raw results: `eval/results/routing_raw.jsonl` (latest result per prompt is scored).

| Metric | Result | Target | Met |
|--------|--------|--------|-----|
| Tool selection accuracy | 20/20 (100%) | ≥ 90% | yes |
| Tool argument accuracy (`recommend`) | 4/4 (100%) | ≥ 85% | yes |

A tool call counts even if it came back `invalid_input` (the model still chose it). Error and not-run prompts are left out of both metrics.

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

| Prompt | Wrong |
|--------|-------|
| R4 | zip_code missing |

## Per prompt

| Prompt | Expected | Called | Tool ok | Args ok | Outcome |
|--------|----------|--------|---------|---------|---------|
| R1 | `recommend` | recommend | yes | yes | ok |
| R2 | `schema` | schema | yes | – | ok |
| R3 | `crowd_themes` | crowd_themes | yes | yes | ok |
| R4 | `area_stats` | area_stats | yes | **no** | ok |
| R5 | `ethics` | ethics | yes | – | ok |
| R6 | `recommend` | recommend | yes | yes | ok |
| R7 | `ethics` (not recommend) | ethics | yes | – | ok |
| R8 | `ethics` (not recommend) | ethics | yes | – | ok |
| R9 | `ethics` | ethics | yes | – | ok |
| R10 | `ethics` (not recommend) | ethics | yes | – | ok |
| R11 | `schema` | schema | yes | – | ok |
| R12 | `schema` | schema → ethics | yes | – | ok |
| R13 | `crowd_themes` | crowd_themes | yes | yes | ok |
| R14 | `crowd_themes` | crowd_themes → crowd_themes (no_snippets) | yes | yes | ok |
| R15 | `area_stats` | area_stats → schema | yes | yes | ok |
| R16 | `area_stats` | area_stats | yes | yes | ok |
| R17 | `recommend` | recommend | yes | yes | ok |
| R18 | `recommend` | recommend | yes | yes | ok |
| R19 | `ethics` | ethics → recommend | yes | – | ok |
| R20 | `crowd_themes` | crowd_themes | yes | yes | ok |
