# Eval Fixtures

Starter test cases for [EVAL_FRAMEWORK.md](../EVAL_FRAMEWORK.md).

| File | Layer | Purpose |
|------|-------|---------|
| `recommendation_profiles.json` | 1 — Rec engine | User profiles + expected relevant ZIPs |
| `agent_routing_prompts.json` | 2 — MCP routing | Prompt → expected tool (+ args and must-not-call constraints) |
| `prohibited_prompts.json` | 3 — LLM refusals | Must refuse; no harmful compliance |

Task #18 adds ethics routing cases for demographic targeting, tenant scoring,
inferred housing preferences, and data limitations. This repository publishes
those expectations through MCP instructions, tool descriptions, and fixtures;
a downstream agent runner should measure its actual tool calls against them.
