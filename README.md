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
## System Architecture

![System Architecture](img/architect.png)


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

### Running the MCP server

The tools are plain functions in `scripts/mcp_tools.py`, so you can call and test them without the server or an LLM. `scripts/mcp_server.py` registers them with the `mcp` SDK (v2, `MCPServer`).

From the repo root, with the `.venv` active:

```bash
python -m scripts.mcp_server          # starts the server over stdio
python scripts/test_mcp_tools.py      # tool + server checks (also runs under pytest)
```

You don't normally start the server by hand. An MCP client launches it. To connect a client such as Claude Desktop or the MCP Inspector, point it at the venv's Python:

```json
{
  "mcpServers": {
    "flow1a-neighborhoods": {
      "command": "/absolute/path/to/repo/.venv/bin/python",
      "args": ["-m", "scripts.mcp_server"],
      "cwd": "/absolute/path/to/repo"
    }
  }
}
```

Every tool returns JSON with a `status` field (`ok`, `invalid_input`, `not_found`, `no_snippets`, or `no_areas_within_budget` from `recommend`). `area_stats` returns Census values that were suppressed or missing as `null` and lists them under `unavailable`. It never returns the median that `clean_data.py` imputed, so the agent can't present that as a real statistic. Top-coded ACS medians (rent `3501` = more than $3,500, home value `2000001` = more than $2,000,000) are kept but listed under `top_coded` with their floor, in both `area_stats` and `recommend`. `ethics` currently returns the README non-negotiables as placeholder rules until Task #18 replaces them.

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
| Rec engine | Precision@3 | 0.283 (ceiling 0.867) | | |
| Rec engine | Precision@5 | 0.200 (ceiling 0.520) | | |
| Rec engine | Mean cosine similarity | 0.810 | | |
| Rec engine | Budget filter pass rate | 100% (20/20) | | |
| MCP | Tool selection accuracy | Not built yet (October) | | |
| LLM | Tool grounding rate | Not built yet (October) | | |
| LLM | Refusal rate | Not built yet (October) | | |
| NLP | Theme coverage | Not built yet (Task #14, PR #45) | | |

Baseline recorded for Task #10 from the Task #6 recommender, run on commit [`b6a4dfd`](https://github.com/Break-Through-Tech/Flow-1A-responsible-ai-prototype-for-personalized-neighborhood-recommendations/commit/b6a4dfd) of `main`. See [Baseline results](#baseline-results-task-10) for how to reproduce it and what the numbers mean.

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
| Azizbek Olimov | [@azizbekolimov](https://github.com/azizbekolimov) | Shared dev environment (Task #1), real review corpus (Task #13), LLM agent wiring (Task #19) |
| Frank Quintero | [@FrankQuintero](https://github.com/FrankQuintero) | Starter CSV audit (Task #2), co-leaser vs co-living guardrail (Task #7), recommender tuning and ablation (Task #15) |
| Prisha Agarwal | [@prisha-agarwal](https://github.com/prisha-agarwal) | Census suppression handling (Task #3), MCP server (Task #16), team table (Task #11) |
| Ayo | [@avisink](https://github.com/avisink) | Anchor ZIP EDA (Task #4), rec-engine eval harness (Task #8), live Census ACS pulls (Task #11), NLP theme extraction (Task #14) |
| Shruti Timalsina | [@shrutimalsina](https://github.com/shrutimalsina) | Feature vector schema (Task #5), eval profile set (Task #9), fair-housing proxy review (Task #20), synthetic-option labeling (Task #21) |
| Nikesh Paudyal | [@Natroness](https://github.com/Natroness) | Baseline recommender v0 (Task #6), rent index (Task #12), ethics tool (Task #18) |
| Mourede Otchere | [@Mourede](https://github.com/Mourede) | September baseline scores (Task #10), tool JSON contracts (Task #17) |

---

## Project highlights *(your team fills this in)*

---

## Data exploration *(your team fills this in)*

---

## Model development *(your team fills this in)*

---

## Results *(your team fills this in)*

### Baseline results (Task #10)

Baseline recommender from Task #6: hard budget filter (ZIPs with suppressed rent excluded), then cosine similarity over `transit`, `social`, `quiet` (+ `co_living_friendly` for co-living). Scored on all 20 profiles in `eval/recommendation_profiles.json` (Task #9), top 5 per profile, so the November final can be scored on the same set.

Numbers are from commit [`b6a4dfd`](https://github.com/Break-Through-Tech/Flow-1A-responsible-ai-prototype-for-personalized-neighborhood-recommendations/commit/b6a4dfd), which includes the live Census ACS data from Task #11 and the 20 profiles from Task #9. The commit is also stored under `run` in `eval/results/baseline_sep.json`. Reproduce from the repo root:

```bash
python eval/run_eval.py --json eval/results/baseline_sep.json   # Precision@k, cosine, budget pass rate
```

| Profile | P@3 | P@5 | Mean cosine | Top 5 returned |
|---------|-----|-----|-------------|----------------|
| P1 couple, own apt, transit + walkable | 0.00 | 0.00 | 0.709 | Little Haiti, Little Havana, 33054, 33030, 33010 |
| P2 solo, own apt, social + walkable | 0.00 | 0.00 | 0.725 | 33015, 33012, 33033, Palmetto Bay, 33032 |
| P3 solo, co-living, transit | 0.67 | 0.40 | 0.722 | **Brickell**, Wynwood, **Downtown**, Allapattah, Riverside |
| P4 couple, own apt, quiet + pets | 0.00 | 0.00 | 0.807 | West Kendall, Sweetwater, Mid-Beach, 33035, Cutler Bay |
| P5 couple, own apt, transit + social | 0.00 | 0.00 | 0.908 | 33012, Palmetto Bay, 33033, Allapattah, 33015 |

The table shows the original five profiles (P1–P5); the headline numbers above cover all 20, and `eval/results/baseline_sep.json` has every profile. Bold marks an expected relevant ZIP. ZIPs shown as a bare number are listed as `ZCTA5 xxxxx` in the data, with no neighborhood name yet.

**What the baseline shows**

- **The budget filter is correct.** Every returned ZIP is within budget in all 20 profiles. P12 ($1,000) correctly returns nothing, since no ZIP is that cheap.
- **Ranking is weak.** Half the profiles (10 of 20) get no expected ZIP into the top 3, and only 4 (P3, P6, P10, P20) reach their P@3 ceiling. Precision is about a third of what these profiles allow (33% at P@3, 38% at P@5): some list fewer than 3 relevant ZIPs and P12 lists none, so P@3 tops out at 0.867 and P@5 at 0.520, not 1.0.
- **Cosine ranks how concentrated a ZIP is on the chosen features, not how strong it is on them.** The anchors score high on transit, social *and* quiet, so a user who picks one feature is matched to ZIPs that are high on it and low on everything else. In P4 (quiet), Downtown has the second-highest quiet score of the 60 candidates (0.94) but ranks 32nd, while West Kendall (0.86) ranks 1st because it is low on transit and social. Unselected features still count toward a ZIP's vector length.
- **Mean cosine looks high (0.81) but does not track quality.** It measures closeness to the user vector, not whether the right ZIPs were returned.
- **`walkable` and `pet_friendly` are not scored** because their data is unusable (Task #4), so P1, P2, P4 and P19 lose part of what the user asked for.
- **The expected ZIPs for P6–P20 were chosen from the same feature scores the engine ranks on** (Task #9 notes they are dataset-based and not yet confirmed by the advisor). Precision on those profiles measures agreement with the feature scores, not real-world fit, so a gain from a scoring change should be read with that in mind.

**Priorities for October:** score only the selected features (or use a weighted sum) so strong all-round ZIPs are not penalized, rebuild `walkable` and `pet_friendly` from real data, and replace the demo crowd text with a real review corpus (Task #13). Theme coverage is measured in Task #14.

---

## Next steps *(your team fills this in)*

---

*MIT License. Questions: Karla Reyes, AI Engineer @ Flow Miami — k.reyes@outlook.com*
