# Responsible AI for Personalized Neighborhood Recommendations

**Break Through Tech AI Studio — Fall 2026**
**Challenge Advisor:** Karla Reyes, AI Engineer @ Flow Miami
**AI Studio Coach:** Harshini Donepudi, harshini.donepudi@breakthroughtech.org

> This project is hosted by the Challenge Advisor independently. Flow is the affiliated org on the BTT submission only — this is not a Flow corporate product.

---

## Why this problem matters

In residential real estate, two metrics drive everything: **occupancy** (filling units) and **renewals** (residents staying). A bad neighborhood match hurts both:

- A prospect who moves to the wrong area leaves at renewal — turnover cost goes up, NOI goes down
- A slow, confusing search loses the prospect before they sign — vacancy rises
- A poorly matched resident won't refer others or renew — lifetime value drops

A good recommender narrows a search to 3–5 well-matched neighborhoods quickly and confidently. That gives the prospect the information to commit, and gives the operator a faster, higher-quality lease. That's the business case behind this prototype.

For residential operators evaluating AI tooling, the critical difference is **grounded vs. hallucinated answers**. An agent that invents a $1,400 Brickell studio creates legal exposure and destroys trust. An agent that can only narrate what its tools return is defensible, auditable, and scalable.

---

## The problem you're solving

Moving to Miami is overwhelming — neighborhoods are hard to compare, listings are scattered, and AI tools often invent facts. Your job is to build a **grounded personalization engine** that helps newcomers find the right fit, with measurable quality at every layer of the stack.

**Primary use case:** "I'm moving from NYC with a co-leaser. We want our own apartment — not a co-living facility — in Wynwood, Downtown, or Brickell."

### Co-leaser vs. co-living — critical distinction

| Term | Meaning |
|------|---------|
| **Co-leaser** | A partner or friend sharing the same private lease — still your own apartment |
| **Co-living** | A separate housing preference: shared/stranger roommate setup |

Never infer one from the other. A couple wanting their own apartment is not the same as someone who wants co-living.

### Anchor neighborhoods

| Neighborhood | ZIP |
|--------------|-----|
| Wynwood | 33127 |
| Downtown Miami | 33128 |
| Brickell | 33130 |

---

## What you'll build

A three-layer system:

| Layer | What it does |
|-------|--------------|
| **Rec engine** | Ranks 3–5 ZIP codes from user inputs: budget, household, housing preference, lifestyle tags |
| **MCP server** | Exposes your engine as structured tools an AI agent can call |
| **LLM agent** | Narrates tool results — never invents listings, rents, or neighborhoods |

**Golden rule:** Ranking happens in Python. The LLM explains results only.

### User inputs

| Field | Options |
|-------|---------|
| `household` | `alone`, `with_co_leaser` |
| `housing_preference` | `own_apartment`, `co_living` |
| Budget | Rent ceiling in USD |
| Lifestyle tags | transit, social, quiet, walkable, pet_friendly |

### MCP tools to build

| Tool | What it returns |
|------|----------------|
| `schema` | Column definitions for all datasets |
| `recommend` | Ranked ZIPs for a given preference profile |
| `area_stats` | Public stats for a ZIP or all ZIPs |
| `crowd_themes` | Review theme snippets for a ZIP |
| `ethics` | Fair-use rules and prohibited uses |

See `MCP_SETUP.md` for the full contract.

---

## Responsible AI — non-negotiables

- Recommend neighborhoods, never score tenants or applicants
- User explicitly picks household and housing preference — no demographic inference
- All synthetic demo listings must be labeled clearly as not real
- Refuse any prompt that asks for demographic filtering, tenant scoring, or anything that violates fair housing spirit

---

## Data

Starter files are in `data/`. Column definitions are in `data_dictionary.md`.

| File | Real or demo? | Use |
|------|---------------|-----|
| `miami_dade_public_features.csv` | Real public data | Census + Zillow-style indices by ZIP |
| `area_features.csv` | Mixed starter | Preference scores for the recommender |
| `crowd_text_snippets.csv` | Demo | Replace with real review corpora in October |
| `area_options.csv` | Synthetic only | UI demo cards — NOT real listings |

Census suppression values show as `-666666666` — decide how to handle those in cleaning.

---

## How you'll know it's working

Three layers, measured. See `EVAL_FRAMEWORK.md` for full metric definitions. Starter test cases are in `eval/`.

| Layer | Metric | Target |
|-------|--------|--------|
| Rec engine | Precision@3, Precision@5 | Higher is better |
| Rec engine | Mean cosine similarity | Higher is better |
| Rec engine | Budget filter pass rate | 100% expected |
| MCP | Tool selection accuracy | ≥ 90% |
| LLM | Tool grounding rate | ≥ 95% |
| LLM | Refusal rate on prohibited prompts | 100% |

Use these metrics from day one — not just at the end. They're your GPS, not your report card.

### End-of-semester scorecard *(fill in as you go)*

| Layer | Metric | Baseline (Sep) | Final (Nov) | Pass? |
|-------|--------|----------------|-------------|-------|
| Rec engine | Precision@3 | | | |
| Rec engine | Mean cosine similarity | | | |
| MCP | Tool selection accuracy | | | |
| LLM | Tool grounding rate | | | |
| LLM | Refusal rate | | | |
| NLP | Theme coverage | | | |

---

## Monthly milestones

| Month | Focus | Main tasks |
|-------|-------|------------|
| **September** | Understand the data | Explore CSVs, handle missing values, build baseline recommender, record first scores |
| **October** | Build and improve | Better public data (Census API, Zillow), tune model, add NLP themes, build MCP server |
| **November** | Evaluate and present | Full scorecard, edge cases, refusal testing, final README and presentation |

---

## What's in this repo

| File or folder | What's inside |
|----------------|---------------|
| `data/` | Starter dataset |
| `data_dictionary.md` | Column definitions for all data files |
| `eval/` | Starter test profiles and routing prompts |
| `EVAL_FRAMEWORK.md` | Metric definitions and scorecard |
| `MCP_SETUP.md` | MCP server tool contract and setup guide |
| `RESOURCES.md` | Curated links: Miami data, ML, NLP, MCP, responsible AI |
| `notebooks/` | Your team's Jupyter notebooks |
| `requirements.txt` | Python packages your project uses |

**Reference prototype (study, don't copy):** [Miami Newcomer Housing Explorer](https://github.com/karlarey/miami-newcomer-explorer)

---

## Team members *(your team fills this in)*

| Name | GitHub | What they worked on |
|------|--------|---------------------|
| | | |

---

## Project highlights *(your team fills this in)*

---

## Data exploration *(your team fills this in)*

---

## Model development *(your team fills this in)*

---

## Results *(your team fills this in)*

---

## Next steps *(your team fills this in)*

---

*MIT License. Questions: Karla Reyes, AI Engineer @ Flow Miami — k.reyes@outlook.com*
