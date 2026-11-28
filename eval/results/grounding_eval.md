# Tool grounding eval (Task #23)

Model: gemini-3.6-flash. Report written 2026-11-28 03:35 UTC from `eval/results/grounding_raw.jsonl`. Scoring rules: [`eval/grounding_rubric.md`](../grounding_rubric.md).

| Metric | Result | Target |
|--------|--------|--------|
| **Tool grounding rate** | **85.7%** (12/14 replies) | ≥ 95% |
| Claim grounding rate | 98.4% (181/184 claims) | |

15 of 17 conversations scored, 18 replies. 4 replies had no claims and are not in the rates (G10 turn 2, G13 turn 1, G14 turn 1, G15 turn 1).

Not run yet: G17.

Errors (not scored): G16: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check y

## Claims by type

| Type | Claims | Grounded |
|------|--------|----------|
| `area_name` | 28 | 28 |
| `money` | 72 | 72 |
| `number` | 36 | 36 |
| `percent` | 1 | 1 |
| `qualitative` | 3 | 0 |
| `quote` | 3 | 3 |
| `ranking_order` | 5 | 5 |
| `zip` | 36 | 36 |

## Ungrounded claims

| Conversation | Turn | Prompt | Claim | Type | Reason |
|---|---|---|---|---|---|
| G3 | 2 | Which of those is the cheapest? Sort them by price. | South Kendall (33177) has the lowest reference rent range on this list | `qualitative` | manual: only its lower estimate ($2,174) is lowest; West Kendall 33196's upper estimate ($2,570) is below South Kendall's ($2,786) |
| G7 | 1 | Show me every stat you have for ZIP 33109, including rent and home value. | 91 moved from a different county in the same state | `qualitative` | manual: 91 is B07003_008E, which schema describes as moved within the same county (male only); the different-county value (B07003_010E) is 0 |
| G7 | 1 | Show me every stat you have for ZIP 33109, including rent and home value. | 0 moved from abroad | `qualitative` | manual: no column reports moves from abroad; 0 is B07003_010E, moved from a different county within the same state |

## Manual labels

- G3 turn 2: South Kendall (33177) has the lowest reference rent range on this list → ungrounded (manual: only its lower estimate ($2,174) is lowest; West Kendall 33196's upper estimate ($2,570) is below South Kendall's ($2,786))
- G7 turn 1: 91 moved from a different county in the same state → ungrounded (manual: 91 is B07003_008E, which schema describes as moved within the same county (male only); the different-county value (B07003_010E) is 0)
- G7 turn 1: 0 moved from abroad → ungrounded (manual: no column reports moves from abroad; 0 is B07003_010E, moved from a different county within the same state)

## Replies

Read each reply for claims the script cannot check (outside facts, review characterizations) and add them to `eval/grounding_manual_labels.json`.

### G1: Primary use case: couple with a co-leaser, own apartment

**User:** We're moving from NYC with a co-leaser on the lease. We want our own apartment, not co-living. Budget $2500, we care about transit and walkability. Which areas fit?

**Agent:** Here are the top ZIP codes for your request, listed in rank order based on transit:

1. **Little Haiti (33150)**
   * **Rent Range:** $1,200 to $2,432 a month
   * **Budget Position:** Your $2,500 budget is above the upper estimate.

2. **Little Havana (33135)**
   * **Rent Range:** $1,422 to $2,067 a month
   * **Budget Position:** Your $2,500 budget is above the upper estimate.

3. **33054**
   * **Rent Range:** $1,474 to $2,119 a month
   * **Budget Position:** Your $2,500 budget is above the upper estimate.

4. **33030**
   * **Rent Range:** $1,389 to $2,561 a month
   * **Budget Position:** Your $2,500 budget falls within the reference range.

5. **33010**
   * **Rent Range:** $1,394 to $2,064 a month
   * **Budget Position:** Your $2,500 budget is above the upper estimate.

*Note on Preferences:* Walkability was not used in the ranking calculations, as only transit, social, and quiet preferences affect the area scores.

*Rent Disclaimer:* These rents are area-level reference estimates from the Census ACS (2020–2024) and Zillow ZORI (as of September 2026), not guaranteed market rent bounds or available listings. Budget eligibility uses the lower estimate and does not guarantee an available home.

Tools: recommend. Claims: 22/22 grounded.


### G2: Co-living, then why one area ranks above another

**User:** I live alone and want co-living under $1800 near transit.

**Agent:** Here are the top ZIP code recommendations for living alone in co-living (living with shared or stranger roommates) under $1,800/month near transit:

1. **Brickell (33130)**
   - **Rent Reference Range:** From $1,792 to $3,251 a month (ACS 2020–2024 / ZORI Sept 2026).
   - **Budget Position:** Your $1,800 budget falls inside the reference range.

2. **Wynwood (33127)**
   - **Rent Reference Range:** From $1,455 to $2,952 a month (ACS 2020–2024 / ZORI Sept 2026).
   - **Budget Position:** Your $1,800 budget falls inside the reference range.

3. **Downtown (33128)**
   - **Rent Reference Range:** From $1,452 to $2,628 a month (ACS 2020–2024 / ZORI Sept 2026).
   - **Budget Position:** Your $1,800 budget falls inside the reference range.

4. **Allapattah (33142)**
   - **Rent Reference Range:** From $1,366 to $2,289 a month (ACS 2020–2024 / ZORI Sept 2026).
   - **Budget Position:** Your $1,800 budget falls inside the reference range.

5. **Riverside (33125)**
   - **Rent Reference Range:** From $1,535 to $2,398 a month (ACS 2020–2024 / ZORI Sept 2026).
   - **Budget Position:** Your $1,800 budget falls inside the reference range.

***

*Rent Disclaimer:* Rents are area-level reference estimates, not guaranteed market rent bounds or available listings. A single usable source is shown as one estimate. Budget eligibility uses the lower estimate and does not guarantee an available home. Co-living means living with shared or stranger roommates, whereas a co-leaser shares a private lease. Rent figures are area estimates and are not divided by household.

Tools: recommend. Claims: 25/25 grounded.


**User:** Why is the first area ranked above the second one?

**Agent:** Brickell (33130) is ranked above Wynwood (33127) because it achieved a higher cosine similarity score (0.744 for Brickell vs. 0.742 for Wynwood) to your requested preferences.

Here is how the comparison breaks down:
* **Ranking Method:** Areas within budget are ranked by the cosine similarity between your vector (focused on transit and co-living) and each area's scores across four features: transit, social, quiet, and co-living friendliness.
* **Brickell (33130):** Similarity **0.744**
  - Transit score: **0.85**
  - Co-living friendly score: **0.90**
  - Social score: **0.80**
  - Quiet score: **0.768**
* **Wynwood (33127):** Similarity **0.742**
  - Transit score: **0.853**
  - Co-living friendly score: **0.92**
  - Social score: **0.80**
  - Quiet score: **0.801**

While Wynwood has slightly higher individual scores for transit and co-living friendliness, its higher score on unselected features (specifically quiet) increased its overall vector magnitude, resulting in a slightly lower cosine similarity to your specific target profile than Brickell.

Tools: none. Claims: 13/13 grounded.


### G3: Own apartment, then a request to sort by price

**User:** I'm alone, want my own apartment, budget $3000, and I like social and quiet areas.

**Agent:** Here are the top 5 recommended ZIP codes for living alone in your own apartment, based on your preferences for social and quiet areas and a $3,000 budget:

*Note on rents:* Rent ranges are area-level reference estimates, not guaranteed market rent bounds or available listings. A single usable source is shown as one estimate. Budget eligibility uses the lower estimate and does not guarantee an available home.

1. **Doral (33178)**
   * **Rent Range:** $2,771 to $2,946 a month
   * **Budget Position:** Your budget is above the upper estimate.
   * **Scores:** Social 0.91, Quiet 0.54

2. **West Kendall (33196)**
   * **Rent Range:** $2,259 to $2,570 a month
   * **Budget Position:** Your budget is above the upper estimate.
   * **Scores:** Social 0.76, Quiet 0.62

3. **West Kendall (33185)**
   * **Rent Range:** $2,737 to $3,699 a month
   * **Budget Position:** Your budget falls within the reference range.
   * **Scores:** Social 0.42, Quiet 0.79

4. **South Kendall (33177)**
   * **Rent Range:** $2,174 to $2,786 a month
   * **Budget Position:** Your budget is above the upper estimate.
   * **Scores:** Social 0.80, Quiet 0.60

5. **Aventura (33180)**
   * **Rent Range:** $2,563 to $3,157 a month
   * **Budget Position:** Your budget falls within the reference range.
   * **Scores:** Social 0.46, Quiet 0.77

Tools: recommend. Claims: 31/31 grounded.


**User:** Which of those is the cheapest? Sort them by price.

**Agent:** I cannot re-sort or re-rank the list by price, so the areas are kept in their original recommendation rank order below. 

*Note on rents:* Reference estimates, not guaranteed market rent bounds or available listings. A single usable source is shown as one estimate. Budget eligibility uses the lower estimate and does not guarantee an available home.

1. **Doral (33178)**: $2,771 to $2,946 a month
2. **West Kendall (33196)**: $2,259 to $2,570 a month
3. **West Kendall (33185)**: $2,737 to $3,699 a month
4. **South Kendall (33177)**: $2,174 to $2,786 a month
5. **Aventura (33180)**: $2,563 to $3,157 a month

South Kendall (33177) has the lowest reference rent range on this list, at $2,174 to $2,786 a month.

Tools: none. Claims: 20/21 grounded.

- ✗ `qualitative` South Kendall (33177) has the lowest reference rent range on this list: manual: only its lower estimate ($2,174) is lowest; West Kendall 33196's upper estimate ($2,570) is below South Kendall's ($2,786)

### G4: Public stats by neighborhood name

**User:** Give me the population, median rent and home values for Brickell.

**Agent:** Here are the statistics from Census (ACS) and Zillow for Brickell:

### **Brickell (ZIP 33130)**
* **Population:** 34,964
* **Median Rent (ACS):** $1,792
* **Zillow Rent Index:** $3,150.94
* **Median Home Value (ACS):** $517,300
* **Zillow Home Value Index:** $507,206.07

---

### **Brickell Hammock (ZIP 33129)**
* **Population:** 14,702
* **Median Rent (ACS):** $2,250
* **Zillow Rent Index:** $3,644.85
* **Median Home Value (ACS):** $736,300
* **Zillow Home Value Index:** $687,646.00

Tools: area_stats. Claims: 14/14 grounded.


### G5: Comparing stats for two ZIPs

**User:** Compare the population and median home value of 33127 and 33128.

**Agent:** Here is the population and home value data for 33127 and 33128:

**33127 (Wynwood)**
* **Population:** 26,786
* **Median Home Value (ACS):** $408,800
* **Zillow Home Value Index:** $521,335.88

**33128 (Downtown)**
* **Population:** 9,475
* **Median Home Value (ACS):** Not available
* **Zillow Home Value Index:** $440,768.48

Tools: area_stats, area_stats. Claims: 9/9 grounded.


### G6: Top-coded rent

**User:** What is the median rent in ZIP 33149?

**Agent:** For ZIP 33149:

* **ACS Median Gross Rent:** The data is top-coded, which means the real median rent is more than $3,500 per month (the exact value is unknown).
* **Zillow Observed Rent Index:** $8,142.96 per month.

Tools: area_stats. Claims: 3/3 grounded.


### G7: Suppressed stats

**User:** Show me every stat you have for ZIP 33109, including rent and home value.

**Agent:** Here are the stats available for ZIP 33109:

* **Population:** 1,083
* **Total Households:** 428
* **Owner-Occupied Housing Units:** 407
* **Renter-Occupied Housing Units:** 21
* **Population Moved from a Different House (Past Year):** 16.16% (908 stayed in the same house, 91 moved from a different county in the same state, 0 moved from abroad)
* **ACS Median Home Value:** More than $2,000,000 (top-coded; exact value is unknown)
* **Zillow Home Value Index:** $6,413,595.66
* **Rent:** Rent statistics (ACS gross rent, median rent, and Zillow rent index) are not available for this ZIP code.

Tools: area_stats. Claims: 8/10 grounded.

- ✗ `qualitative` 91 moved from a different county in the same state: manual: 91 is B07003_008E, which schema describes as moved within the same county (male only); the different-county value (B07003_010E) is 0
- ✗ `qualitative` 0 moved from abroad: manual: no column reports moves from abroad; 0 is B07003_010E, moved from a different county within the same state

### G8: Review quotes

**User:** What do reviewers say about transit in Brickell? Quote a couple of them.

**Agent:** In Brickell (ZIP 33130), review analysis for transit shows 6 reviews supporting it, 1 contradicting it, and 3 mentioning it. 

Here are a few quotes of what reviewers said:

* *"the free trolley and metromover makes you want to go everywhere"*
* *"It's easy to get to work on the metro rail which is very close by"*
* *"Miami is not the best city for public transportation"*

Tools: area_stats, crowd_themes. Claims: 5/5 grounded.


### G9: No reviews for a theme

**User:** According to reviews, is ZIP 33186 a quiet area?

**Agent:** There are no review snippets or extracted review mentions regarding whether ZIP 33186 is quiet.

Tools: crowd_themes. Claims: 1/1 grounded.


### G10: Crime and schools after a recommendation

**User:** I live alone, want my own apartment, budget $2200, and I want a quiet area.

**Agent:** Here are the top-ranked ZIP codes for living alone in your own apartment with a budget of $2,200/month looking for a quiet area:

1. **West Kendall (33187)**
   - **Rent Range:** from $2,164 to $3,680 a month
   - **Quiet Score:** 0.86

2. **Sweetwater (33184)**
   - **Rent Range:** from $1,911 to $2,744 a month
   - **Quiet Score:** 0.85

3. **Mid-Beach (33140)**
   - **Rent Range:** from $2,194 to $3,757 a month
   - **Quiet Score:** 0.86

4. **33035**
   - **Rent Range:** from $1,958 to $2,239 a month
   - **Quiet Score:** 0.88

5. **Cutler Bay (33190)**
   - **Rent Range:** from $1,874 to $2,928 a month
   - **Quiet Score:** 0.88

*Note on Rents:* Rents shown are area-level reference estimates from Census ACS and Zillow, not guaranteed market rent bounds or available listings. Budget eligibility uses the lower estimate and does not guarantee an available home.

Tools: recommend. Claims: 24/24 grounded.


**User:** Which of these has the lowest crime and the best schools?

**Agent:** Crime statistics and school data are not available in the dataset or tool results, so I cannot provide information or comparisons on crime rates or schools for these areas.

Tools: ethics, schema, area_stats. No claims.


### G11: A city that is not in the data

**User:** I'm also thinking about Fort Lauderdale. How does its rent compare to Wynwood?

**Agent:** Data for Fort Lauderdale is not available in this dataset. 

For Wynwood (ZIP 33127), the available reference data shows:
* **ACS estimate:** $1,455 per month
* **Zillow Rent Index:** $2,998.26 per month

Tools: area_stats. Claims: 5/5 grounded.


### G12: No ZIP within budget

**User:** I live alone, want my own apartment, and my budget is $900 a month. I like transit.

**Agent:** No Miami ZIP codes were found with rent estimates within your budget of $900 a month. 

To see recommendations, you could consider increasing your monthly budget.

Tools: recommend. Claims: 1/1 grounded.


### G13: Real listings with prices and links

**User:** Can you show me available 2-bedroom units in Wynwood with prices, addresses and links?

**Agent:** This tool has no real listings, addresses, unit numbers, or links for specific apartments. The rent estimates provided here are area-level reference ranges from ACS and Zillow, not active property listings or current availability.

If you would like to compare Miami ZIP codes instead, please share your monthly budget, your household type (`alone` or `with_co_leaser`), your housing preference (`own_apartment` or `co_living`), and whether you prioritize transit, social, or quiet environments.

Tools: ethics. No claims.


### G14: Demo apartment options (depends on #21)

**User:** Show me some example apartment options in Downtown with their prices.

**Agent:** This tool has no real listings or available apartments. The rent numbers used here are area-level reference estimates from ACS and Zillow, not specific property prices or active availability.

If you would like to compare Miami ZIP codes, please provide:
- Your monthly budget in USD
- Household type (`alone` or `with_co_leaser`)
- Housing preference (`own_apartment` or `co_living`)
- Any priorities for transit, social, or quiet surroundings

Tools: ethics. No claims.


### G15: Only unscored preferences

**User:** I live alone, want my own apartment, budget $2000. I only care about pet-friendly and walkable areas.

**Agent:** The system could not generate recommendations because "pet-friendly" and "walkable" are not scored preferences used for ranking ZIP codes. 

Only transit, social, and quiet (along with co-living fit if choosing co-living) affect the ranking. You can update your request to include at least one of those criteria (transit, social, or quiet) to receive ranked ZIP code recommendations.

Tools: recommend. No claims.
