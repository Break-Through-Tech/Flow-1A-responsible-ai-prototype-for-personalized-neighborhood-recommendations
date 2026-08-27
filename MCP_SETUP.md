# MCP Server Setup

An **MCP server** lets your AI agent call your recommender and data functions directly — instead of guessing answers.

Think of it like a waiter who can only bring items from the kitchen menu. If it's not on the menu (your tools), the agent shouldn't serve it.

---

## The five tools you need to build

| Tool | You pass in… | You get back… |
|------|--------------|---------------|
| `schema` | Nothing | Column names and notes about each dataset |
| `area_stats` | A ZIP code (optional) | Public stats for that ZIP, or all ZIPs if blank |
| `crowd_themes` | A ZIP code | Review theme snippets (transit, quiet, social, etc.) |
| `recommend` | Budget, tags, `household`, `housing_preference`, `k` | Top neighborhood matches as structured JSON |
| `ethics` | Nothing | Rules for fair, responsible use |

---

## Tool contract rules

Every tool must:
- Return **structured JSON** — not natural language
- Only surface data that exists in your dataset — never generate or infer values
- Be callable independently so it can be tested without the LLM

The LLM must:
- Only answer using what the tools return
- Never rank, score, or create facts outside of tool output
- Call `ethics` when the user asks about limitations or prohibited uses

---

## See a working example

The reference prototype has all of this already built:

**Repo:** https://github.com/karlarey/miami-newcomer-explorer

Study it to understand how the tools connect to the recommender and how the agent is constrained. How you structure your own implementation is part of the challenge.

---

## Your team's deliverable (October)

By end of October, your team should:

1. Build your MCP server using this repo's `data/` files
2. Confirm the agent only uses tool outputs (**tool grounding rate**)
3. Confirm bad requests get refused (**refusal rate**)
4. Document how to run your server in the team README

---

## Quick test checklist

- [ ] `schema` lists columns for all starter CSVs
- [ ] `recommend` returns 3–5 ZIPs for a sample budget + tags
- [ ] `crowd_themes` returns text for a ZIP you know exists
- [ ] `ethics` returns the fair-use rules
- [ ] Agent does **not** invent rents, listings, or neighborhoods when tools are available
