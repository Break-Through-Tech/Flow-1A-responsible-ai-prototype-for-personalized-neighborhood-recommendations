# System Architecture

**What you're building:** A recommendation engine hooked to an LLM — not a chatbot that guesses neighborhoods.

---

## High-level flow

The system has four layers that work together. Your team decides how to implement each one.

User preferences flow into a recommendation engine that ranks neighborhoods. Those rankings are exposed through an MCP server as structured tools. An LLM agent calls those tools and narrates the results — it never ranks or invents facts on its own.

---

## Layer responsibilities

| Layer | Owns | Must NOT do |
|-------|------|-------------|
| **Data** | ZIP features, review snippets, public stats | Live listing scrapes, PII |
| **Rec engine** | Rank 3–5 ZIPs from user preference vector | Natural language replies |
| **NLP** | Theme snippets per ZIP | Generate fake reviews |
| **MCP** | Expose tools with structured JSON I/O | Hide recommender logic from eval |
| **LLM** | Narrate tool outputs, ask clarifying questions | Invent rents, ZIPs, or listings |

**Golden rule:** Ranking happens in **Python**. The LLM **narrates** tool results.

---

## MCP tools (contract)

| Tool | When to call |
|------|--------------|
| `schema` | User asks about data columns or dataset structure |
| `recommend` | User wants area suggestions (budget + household + housing preference + tags) |
| `area_stats` | User asks about a specific ZIP or area statistics |
| `crowd_themes` | User asks what people say about a ZIP |
| `ethics` | User asks about limitations, fair housing, or prohibited uses |

Setup details: [MCP_SETUP.md](MCP_SETUP.md)

---

## Reference implementation

Study (do not copy blindly): [Miami Newcomer Housing Explorer](https://github.com/karlarey/miami-newcomer-explorer)

**Your deliverable:** Implement your version in **this repo** with tests from [eval/](eval/) and metrics in [EVAL_FRAMEWORK.md](EVAL_FRAMEWORK.md). How you structure your code is part of the challenge.

---

## Business link *(illustrative operator scenario)*

A better recommendation match leads to a faster lease decision (occupancy up), a happier resident, and a higher renewal rate.

Not a Flow corporate initiative — **hosted by Challenge Advisor alone**. See [ATTRIBUTION.md](ATTRIBUTION.md).

Stakeholder detail: [STAKEHOLDERS.md](STAKEHOLDERS.md)

---

## Getting started

1. Explore `data/` and [data_dictionary.md](data_dictionary.md)
2. Study the reference prototype to understand how the layers connect
3. Build your implementation in this repo
4. Run eval fixtures in [eval/](eval/)
5. Set your LLM API key via `.env.example` when you're ready to connect the agent
