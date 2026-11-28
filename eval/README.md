# Eval Fixtures

Starter test cases for [EVAL_FRAMEWORK.md](../EVAL_FRAMEWORK.md).

| File | Layer | Purpose |
|------|-------|---------|
| `recommendation_profiles.json` | 1 — Rec engine | User profiles + expected relevant ZIPs |
| `agent_routing_prompts.json` | 2 — MCP routing | Prompt → expected tool (+ args and must-not-call constraints) |
| `prohibited_prompts.json` | 3 — LLM refusals | Must refuse; no harmful compliance |
| `grounding_conversations.json` | 3 — LLM grounding | Fixed conversations that tempt the agent to state facts no tool returned |
| `grounding_rubric.md` | 3 — LLM grounding | Scored unit (the claim), labels and edge-case rules for tool grounding rate |
| `grounding_manual_labels.json` | 3 — LLM grounding | Reviewer corrections merged when scoring (false positives, outside facts) |

### Tool grounding rate (Task #23)

```bash
python eval/run_grounding_eval.py --dry-run       # check the files, print the request estimate
python eval/run_grounding_eval.py                 # run what is left (resumable), then score
python eval/run_grounding_eval.py --report-only   # re-score saved results, e.g. after adding manual labels
python scripts/test_grounding_eval.py             # offline tests, no API key needed
```

Each conversation runs through `scripts/agent.py` and is saved to `results/grounding_raw.jsonl` with the full tool results. Every claim in every reply is checked against the tool results of its conversation (see `grounding_rubric.md`). `results/grounding_eval.md` shows the rate, every ungrounded claim with the prompt that produced it, and each reply for manual review. `results/grounding_eval.json` holds the same summary for other scripts. G14 checks synthetic-option labels. Its saved run is from before Task #21 merged, so rerun it with `--only G14 --fresh`.

Task #18 adds ethics routing cases for demographic targeting, tenant scoring,
inferred housing preferences, and data limitations. This repository publishes
those expectations through MCP instructions, tool descriptions, and fixtures;
a downstream agent runner should measure its actual tool calls against them.
