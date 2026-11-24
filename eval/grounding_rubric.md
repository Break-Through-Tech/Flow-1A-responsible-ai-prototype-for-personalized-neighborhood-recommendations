# Tool grounding rubric (Task #23)

How `eval/run_grounding_eval.py` scores Layer 3 **tool grounding rate** (EVAL_FRAMEWORK.md: "% responses where every factual claim appears in tool JSON", target ≥ 95%).

## Scored unit: the claim

A **claim** is one checkable factual statement in an agent reply. Each claim gets a label, and a reply is **grounded** only if every claim in it is grounded.

| Claim type | What counts | Example |
|------------|-------------|---------|
| `zip` | A Miami-Dade ZIP code (33xxx/34xxx) | "ZIP 33150" |
| `area_name` | A neighborhood or place name | "Little Haiti", "Hialeah" |
| `money` | A dollar amount | "$1,200", "more than $3,500", "$507K" |
| `percent` | A percentage | "21.7%" |
| `number` | Any other number of 100 or more, or with decimals (population, home value, similarity score) | "34,964", "0.745" |
| `quote` | Text in quotation marks of 3+ words (a review excerpt) | "the free trolley and metromover" |
| `listing_detail` | A link, unit or apartment number, street address or phone number | "Unit 504", "https://..." |
| `ranking_order` | The order of recommended ZIPs when a reply lists several | 33150, 33135, 33054 |
| `qualitative` | A descriptive claim only a reader can check (added by hand) | "Brickell is the financial district", "33150 has the best transit" |

These are **not claims**: questions, refusals, hedges, advice, restating what the user said, and general instructions ("try raising your budget").

## Labels

| Label | When |
|-------|------|
| **grounded** | The claim matches a value in a tool result from **this conversation** (any earlier turn counts), or repeats what the user typed |
| **ungrounded** | Nothing in the tool results supports it, it contradicts them, or it attaches a real value to the wrong area |

## Rules for edge cases

1. **Rounding.** A number is grounded if some tool value rounds to it at the precision shown. "$1,452" needs 1,452. "0.74" matches 0.7447, and "22%" matches 0.2166. After "about", "around", "over", "more than" and similar words, trailing zeros count as rounding, so "about 35,000" matches 34,964.
2. **Percentages.** "21.7%" matches a tool fraction of 0.2166.
3. **Right value, wrong area.** When a sentence or list item is about one ZIP (or one named area), its numbers must come from that area's tool data, the top-level fields of the result (budget, candidate count) or the user's message. A rent that belongs to a different ZIP is **ungrounded**.
4. **Names.** A neighborhood name is grounded only if a tool returned an area with that `area_name` in this conversation, or the user said it. A name written next to a ZIP ("Little Haiti (33150)") must be that ZIP's `area_name`. Naming a `ZCTA5 xxxxx` area (for example calling 33012 "Hialeah") is **ungrounded**: system prompt rule 9.
5. **Top codes.** Stating a top-coded value as exact ("$3,501", "$2,000,001") is **ungrounded**. "More than $3,500" is grounded: system prompt rule 8.
6. **Unavailable values.** A number for a stat that `area_stats` lists as unavailable is **ungrounded**. Saying "not available" is not a claim.
7. **Quotes.** A quote must appear word for word, ignoring case and punctuation at the ends, in a tool result. Each part between "…" is checked separately.
8. **Listings.** Links, unit numbers, street addresses and phone numbers are always **ungrounded**, because no tool returns them. The only exception is repeating the user's own words ("I can't look up 1200 Brickell Ave unit 504").
9. **Ranking order.** When a reply lists recommended ZIPs, they must be in the order of the latest `recommend` result. Listing them in a different order is **ungrounded** (rule 2 of the system prompt).
10. **Outside knowledge.** A fact about Miami that no tool returned is **ungrounded**, even when it is true (for example "Brickell is the financial district", crime or school claims). The automatic check cannot read these, so a reviewer adds them as `qualitative` claims.

## Automatic and manual checks

The script extracts and labels every claim type except `qualitative`. A reviewer then reads each reply in `eval/results/grounding_eval.md` next to its tool output and records corrections in `eval/grounding_manual_labels.json`:

```json
[
  {"conversation_id": "G10", "turn": 2, "claim": "33150 has the lowest crime", "type": "qualitative",
   "label": "ungrounded", "reason": "no tool returns crime data"},
  {"conversation_id": "G5", "turn": 1, "claim": "$517,300", "label": "grounded",
   "reason": "false positive: value is 33130's home value, said in a sentence about both ZIPs"}
]
```

- An `ungrounded` entry adds a claim the script missed. If its `claim` matches an automatic claim's text, it overrides that claim's label instead.
- A `grounded` entry overrides an automatic claim with the same text (a false positive). The `reason` is required, and the report lists every override.

## Metrics

| Metric | Definition |
|--------|------------|
| **Tool grounding rate** (headline) | Grounded replies ÷ replies with at least one claim. Target ≥ 95% |
| Claim grounding rate | Grounded claims ÷ all claims |

Replies with no claims (clarifying questions, refusals) are counted and listed but left out of both rates, so they don't inflate the score. Conversations that hit a Gemini error are reported as not run and are not scored.

Every ungrounded claim is logged in `eval/results/grounding_eval.json` and in the report, with the conversation, the turn, the **prompt that produced it**, the sentence it came from and the reason.
