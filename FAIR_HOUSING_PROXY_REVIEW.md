# Task #20: Fair-Housing Proxy Review

## Purpose

This review examines the features used in our neighborhood recommendation system to identify possible demographic proxy risks.

The goal is to ensure that recommendations are based on users' budgets, housing choices, and lifestyle preferences rather than protected demographic characteristics.

This review builds on the feature schema developed in Task #5.

## 1. Feature Review and Decisions

The table below summarizes each feature, its potential risk, and whether it should remain in the recommendation system.

| Feature | Potential Risk | Decision | Reason |
|---|---|---|---|
| `transit` | Transit access may be related to differences in neighborhood demographics and infrastructure. | Keep with caution | It represents a user-selected preference, but the source and fairness of the score need further validation. |
| `social` | Social activity scores may reflect uneven access to amenities or subjective neighborhood descriptions. | Keep with caution | It supports a user-selected preference, but the score may not represent all neighborhoods equally. |
| `quiet` | Quietness scores may reflect subjective judgments about neighborhoods. | Keep with caution | It represents a user-selected preference, but its measurement and possible biases need further review. |
| `co_living_friendly` | Co-living scores may reflect assumptions about neighborhood residents and overlap with social activity. | Keep with caution | It is used only when the user selects co-living. Its source and potential bias still need validation. |
| `walkable` | The existing score was calculated using rent data rather than a reliable walkability measure. | Exclude | The feature does not accurately measure walkability and could introduce rent-related bias. |
| `pet_friendly` | The score is identical across all ZIP codes. | Exclude | It cannot meaningfully distinguish neighborhoods. |
| `migration_score` | Migration patterns may indirectly reflect demographic changes. | Exclude | It is not linked to a supported user preference and may introduce unnecessary demographic proxy risks. |
| `single_family_friendly` | The score may reflect assumptions about household or family composition. | Exclude | Single-family housing is not a supported housing preference in the current system. |
| `median_rent_usd` | Rent differences may be associated with neighborhood demographics. | Keep for rent estimates only | Rent information supports budget filtering and is not used in similarity scoring. The current system uses the lower usable ACS/Zillow rent estimate for eligibility. |
| `rent_band` | Illustrative rent categories may be mistaken for actual housing prices. | Exclude from scoring | The system uses numerical rent estimates for budget eligibility instead. |
| `zip` | ZIP codes may indirectly reflect demographic patterns. | Keep as identifier | ZIP codes identify recommendation results but are not used to calculate similarity. |
| `area_name` | Neighborhood names may carry subjective associations. | Keep for display | Names are used to identify neighborhoods, not rank them. Some names are illustrative. |
| `median_rent_usd_suppressed` | Missing rent data may affect some neighborhoods more than others. | Keep as data-quality information | This flag identifies suppressed Census values and is not used in similarity scoring. |

The decisions above reflect the current implementation. Features marked "Keep with caution" require further validation before real-world use.

## 2. Existing Fair-Housing Safeguards

The recommendation system already includes several safeguards:

- Recommendations use selected lifestyle preferences rather than explicit demographic information.
- Household type and housing preference are treated as separate inputs.
- Household type does not directly affect similarity scores.
- Co-living suitability is scored only when the user selects co-living.
- Budget filtering is separate from similarity scoring.
- Unreliable or unsupported features are excluded from scoring.
- The MCP ethics tool includes rules against demographic filtering, housing discrimination, tenant scoring, and demographic steering.

These safeguards help reduce risks, but they do not guarantee that recommendations are free from demographic bias.

## 3. Risks and Limitations

### Feature Data Sources

The lifestyle scores come from the project's starter dataset. Although their intended purposes are documented, the available documentation does not fully explain how the scores were originally calculated.

Further validation is needed to confirm that these features accurately represent neighborhood characteristics.

### Correlated Features

Previous exploratory analysis identified strong correlations between:

- `social` and `quiet`: approximately -0.83.
- `social` and `co_living_friendly`: approximately 0.78.

These relationships may cause similar neighborhood characteristics to influence rankings through multiple features.

However, correlation between features does not necessarily indicate demographic discrimination.

### Similarity Calculation

The recommender uses cosine similarity with fixed feature dimensions.

Even when a user does not select a particular feature, that feature can still influence the similarity score through the neighborhood vector.

This is an existing limitation of the baseline recommendation approach.

### Geographic Proxy Risks

Neighborhood characteristics and ZIP codes may be associated with demographic patterns, even when demographic information is not directly used.

The current review does not establish whether these relationships cause unequal outcomes across protected groups.

### Data Limitations

The system uses neighborhood-level data and estimated rent ranges rather than verified available housing listings.

Some neighborhood review data also has limited coverage, which may affect how accurately certain areas are represented.

## 4. Fair-Housing Comparison Tests

To check whether household type affects recommendations, we will compare profiles that have the same:

- Budget.
- Housing preference.
- Lifestyle preferences.

The only difference will be the household input: `alone` or `with_co_leaser`.

The tests will compare:

- Number of eligible neighborhoods.
- Recommendation status.
- Recommended ZIP code rankings.
- Similarity scores.

We expect the results to remain the same when only household type changes.

This test checks that household type does not directly affect recommendation rankings. It does not prove that the underlying neighborhood features are free from demographic bias.

**Test status:** Pending execution.

## 5. Final Decisions and Recommendations

Based on the current code and documentation:

- Keep `transit`, `social`, and `quiet` as baseline features, with further validation required.
- Keep `co_living_friendly` only when co-living is explicitly selected.
- Continue excluding `walkable`, `pet_friendly`, `migration_score`, and `single_family_friendly` from similarity scoring.
- Keep rent information for budget eligibility, not similarity scoring.
- Keep identifiers and data-quality fields outside similarity scoring.
- Document the limitations of the starter feature scores and their possible demographic proxy risks.

No additional feature removal is recommended at this stage because the available evidence does not establish that the retained features cause demographic discrimination. However, their safety has not been established either.

Before using the system for real-world housing decisions, the team should validate feature sources, review possible demographic impacts, and assess whether the recommendation results create unfair differences.

## 6. Conclusion

This review identifies potential demographic proxy risks and documents the reasons for keeping or excluding each feature.

The current system includes useful safeguards, but further testing and data validation are necessary.

The goal is to provide transparent, preference-based neighborhood recommendations while reducing the risk of discriminatory housing guidance.

This document is a technical review and does not establish legal compliance with fair-housing requirements.