# Agent test conversations (Task #19)

Model: `gemini-3.6-flash`. Run: 2026-11-16 21:22 UTC.

For each turn, check every fact in the reply against the tool output and fill in **Verified**.

## C2: Co-living, alone

Expected: Calls recommend with alone + co_living + 1800. Lists results in rank order, only values from the tool.

**User:** I live alone and want co-living under $1800 near transit.

**Agent:** Here are the top ZIP codes matching your co-living preference, transit tag, and $1,800 monthly budget, listed in order of rank:

1. **Brickell (33130)**
   - **Median Rent:** $1,792
   - **Transit Score:** 0.85
   - **Co-Living Score:** 0.90

2. **Wynwood (33127)**
   - **Median Rent:** $1,455
   - **Transit Score:** 0.85
   - **Co-Living Score:** 0.92

3. **Downtown (33128)**
   - **Median Rent:** $1,452
   - **Transit Score:** 0.92
   - **Co-Living Score:** 0.88

4. **Allapattah (33142)**
   - **Median Rent:** $1,366
   - **Transit Score:** 0.92
   - **Co-Living Score:** 0.55

5. **Riverside (33125)**
   - **Median Rent:** $1,535
   - **Transit Score:** 0.88
   - **Co-Living Score:** 0.54

*(Note: Rents shown are ZIP-level median rents, not individual listings.)*

- Tool `recommend` args `{"budget_max": 1800, "household": "alone", "housing_preference": "co_living", "tags": ["transit", "co_living"], "k": 5}`
  - Result: `{"household": "alone", "housing_preference": "co_living", "budget_max": 1800.0, "tags": ["transit", "co_living"], "vector_features": ["transit", "social", "quiet", "co_living_friendly"], "active_features": ["transit", "co_living_friendly"], "unscored_tags": [], "user_vector": {"transit": 1.0, "social": 0.0, "quiet": 0.0, "co_living_friendly": 1.0}, "candidate_count": 31, "recommendations": [{"rank": 1, "zip": "33130", "area_name": "Brickell", "median_rent_usd": 1792.0, "similarity": 0.7444795288866192, "matched_features": [{"feature": "transit", "area_score": 0.85}, {"feature": "co_living_friendly", "area_score": 0.9}], "feature_scores": {"transit": 0.85, "social": 0.8, "quiet": 0.7682731262660365, "co_living_friendly": 0.9}, "top_coded": null, "ranking_reasons": [{"code": "within_budget", "median_rent_usd": 1792.0, "budget_max": 1800.0, "headroom_usd": 8.0, "rent_is_top_coded": false}, {"code": "selected_feature", "feature": "transit", "area_score": 0.85}, {"code": "unselected_feature", "feature": "social", "area_score": 0.8, "effect": "lowers_similarity"}, {"code": "unselected_feature", "feature": "quiet", "area_score": 0.7682731262660365, "effect": "lowers_similarity"}, {"code": "selected_feature", "feature": "co_living_friendly", "area_score": 0.9}], "summary": "#1 Brickell (33130): median rent $1,792, within the $1,800 budget. Similarity 0.744; selected-feature scores: transit 0.85, co_living_friendly 0.90."}, {"rank": 2, "zip": "33127", "area_name": "Wynwood", "median_r ...(cut)`

Grounding check: none

**Verified:** Yes. Same 5 ZIPs, order and rents as before; all transit and co-living scores match the tool.

---

## C6: No ZIP within budget

Expected: Calls recommend, gets no_areas_within_budget, says no ZIP fits that budget and suggests raising it. Names no ZIPs or rents.

**User:** I live alone, want my own apartment, budget $500 a month, I like quiet areas.

**Agent:** No ZIP codes were found within your monthly budget of $500. 

To see available ZIP codes, you would need to increase your monthly budget.

- Tool `recommend` args `{"budget_max": 500, "household": "alone", "housing_preference": "own_apartment", "tags": ["quiet"], "k": 5}`
  - Result: `{"household": "alone", "housing_preference": "own_apartment", "budget_max": 500.0, "tags": ["quiet"], "vector_features": ["transit", "social", "quiet"], "active_features": ["quiet"], "unscored_tags": [], "user_vector": {"transit": 0.0, "social": 0.0, "quiet": 1.0}, "candidate_count": 0, "recommendations": [], "status": "no_areas_within_budget", "rank_basis": "ZIPs above budget_max are removed first. The rest are ranked by cosine similarity between the user vector and each ZIP's scores on transit, social, quiet; ties go to the lower ZIP."}`

Grounding check: none

**Verified:** Yes. Tool returned no_areas_within_budget through the contract; agent named no ZIPs and suggested raising the budget.

---

## C7: Only unscored preferences

Expected: recommend returns invalid_input (no scored preferences). The agent explains that pets and walkability are not used for ranking and asks for transit, social or quiet. No invented ZIPs.

**User:** I live alone, want my own apartment, budget $2200. I only care about pets and walkability.

**Agent:** The search could not rank ZIP codes because **walkable** and **pet_friendly** are unscored preferences and do not affect the ranking system. Only **transit**, **social**, and **quiet** (plus co-living fit for co-living preferences) are used to score and rank areas.

To get ranked ZIP recommendations within your $2,200 budget for living alone in your own apartment, please specify if you have any preferences for **transit**, **social**, or **quiet**.

- Tool `recommend` args `{"budget_max": 2200, "household": "alone", "housing_preference": "own_apartment", "tags": ["walkable", "pet_friendly"], "k": 5}`
  - Result: `{"status": "invalid_input", "error": "No scored preferences: cosine similarity is undefined for a zero user vector. Unscored tags: ['walkable', 'pet_friendly']."}`

Grounding check: none

**Verified:** Yes. Tool returned invalid_input; agent explained walkable and pets aren't scored and asked for transit, social or quiet.

---

## C8: Missing housing preference, then a request to re-rank

Expected: Turn 1: asks whether they want their own apartment or co-living instead of guessing. Turn 2: calls recommend. Turn 3: keeps the recommender's order and does not name a new best match; may point out the rents.

**User:** We're a couple with a co-leaser, budget $2500, we like social areas. What do you recommend?

**Agent:** To help recommend the best ZIP codes for you, could you please specify your housing preference? 

Do you prefer an **own apartment** (a traditional private lease) or **co-living** (a private bedroom in a shared building with communal amenities)?

- No tool called

Grounding check: none

**User:** We want our own apartment.

**Agent:** Here are the top 5 recommended ZIP codes matching your budget ($2,500/month), household (with a co-leaser), housing preference (own apartment), and social preference, listed in exact rank order:

1. **Kendall (33186)**
   - **Median Rent:** $2,224
   - **Social Score:** 0.97

2. **33015**
   - **Median Rent:** $1,936
   - **Social Score:** 0.96

3. **33012**
   - **Median Rent:** $1,665
   - **Social Score:** 1.00

4. **33033**
   - **Median Rent:** $1,766
   - **Social Score:** 0.96

5. **Palmetto Bay (33157)**
   - **Median Rent:** $1,653
   - **Social Score:** 0.97

*Note: Rent prices are ZIP-level median rents, not specific rental listings.*

- Tool `recommend` args `{"budget_max": 2500, "household": "with_co_leaser", "housing_preference": "own_apartment", "tags": ["social"], "k": 5}`
  - Result: `{"household": "with_co_leaser", "housing_preference": "own_apartment", "budget_max": 2500.0, "tags": ["social"], "vector_features": ["transit", "social", "quiet"], "active_features": ["social"], "unscored_tags": [], "user_vector": {"transit": 0.0, "social": 1.0, "quiet": 0.0}, "candidate_count": 67, "recommendations": [{"rank": 1, "zip": "33186", "area_name": "Kendall", "median_rent_usd": 2224.0, "similarity": 0.7861134606384429, "matched_features": [{"feature": "social", "area_score": 0.967111186135494}], "feature_scores": {"transit": 0.5581047013481981, "social": 0.967111186135494, "quiet": 0.5164444069322529}, "top_coded": null, "ranking_reasons": [{"code": "within_budget", "median_rent_usd": 2224.0, "budget_max": 2500.0, "headroom_usd": 276.0, "rent_is_top_coded": false}, {"code": "unselected_feature", "feature": "transit", "area_score": 0.5581047013481981, "effect": "lowers_similarity"}, {"code": "selected_feature", "feature": "social", "area_score": 0.967111186135494}, {"code": "unselected_feature", "feature": "quiet", "area_score": 0.5164444069322529, "effect": "lowers_similarity"}], "summary": "#1 Kendall (33186): median rent $2,224, within the $2,500 budget. Similarity 0.786; selected-feature scores: social 0.97."}, {"rank": 2, "zip": "33015", "area_name": "ZCTA5 33015", "median_rent_usd": 1936.0, "similarity": 0.7614515552497831, "matched_features": [{"feature": "social", "area_score": 0.963833558406482}], "feature_scores": {"transit": 0.6362585869862369, "social":  ...(cut)`

Grounding check: none

**User:** Re-rank those by cheapest rent and tell me which one is the best match.

**Agent:** I cannot re-rank the areas or label a different ZIP as the best match, as the ranking order must stay fixed according to the recommendation model. **Kendall (33186)** remains the top match (#1) for your overall preferences.

However, pointing out the median rents across the recommended areas:

1. **Kendall (33186)**: $2,224/month (Rank 1 – Top Match)
2. **33015**: $1,936/month (Rank 2)
3. **33012**: $1,665/month (Rank 3)
4. **33033**: $1,766/month (Rank 4)
5. **Palmetto Bay (33157)**: $1,653/month (Rank 5 – Lowest Median Rent)

**Palmetto Bay (33157)** has the lowest median rent ($1,653/month), followed closely by **33012** ($1,665/month).

- No tool called

Grounding check: none

**Verified:** Yes. Turns 2 and 3 correct: ranks, rents and social scores match the tool, and the order was kept. Turn 1 described co-living in words no tool gave; fixed in rule 11 and retested.

---
