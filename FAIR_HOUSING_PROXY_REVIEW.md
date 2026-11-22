# Task #20: Fair-Housing Proxy Review

## Purpose

This review examines the features used in our neighborhood recommendation system for possible demographic proxy risks.

The goal is to support recommendations based on users' budgets, housing preferences, and lifestyle priorities without using protected demographic characteristics to steer housing choices.

This review builds on the feature schema from Task #5 and evaluates the current recommender implementation.

## 1. Feature Review and Decisions

The following table summarizes the potential risks and decisions for all 13 columns in `data/area_features_clean.csv`.

| Feature | Potential Risk | Decision | Reason |
|---|---|---|---|
| `transit` | Transit access may reflect differences in infrastructure and neighborhood demographics. | Keep provisionally | It supports an explicit user preference, but the original score needs further validation. |
| `social` | Social activity scores may reflect uneven access to amenities or subjective neighborhood descriptions. | Keep provisionally | It supports a user-selected preference, but its source and possible demographic effects are not fully validated. |
| `quiet` | Quietness scores may reflect subjective neighborhood judgments. | Keep provisionally | It represents a user-selected preference, but the score's construction and potential bias require further review. |
| `co_living_friendly` | Co-living suitability may reflect assumptions about residents or overlap with social activity. | Keep provisionally, conditional | It is used only when co-living is selected. Its source and possible proxy risks need further validation. |
| `walkable` | The current score was derived from rent rather than a reliable walkability measure. | Exclude from scoring | The feature does not reliably measure walkability and could introduce rent-related proxy effects. |
| `pet_friendly` | The score is constant across all ZIP codes. | Exclude from scoring | It cannot meaningfully distinguish neighborhoods. |
| `migration_score` | Migration patterns may indirectly reflect demographic changes. | Exclude from scoring | It is not linked to a supported user preference and could introduce unnecessary proxy risks. |
| `single_family_friendly` | The score may reflect assumptions about household or family composition. | Exclude from scoring | Single-family housing is not a supported housing preference. |
| `median_rent_usd` | Rent differences may be associated with neighborhood demographics. | Keep for rent-reference calculations | Rent supports budget eligibility but is not included in similarity scoring. The current recommender uses the lower usable ACS/Zillow estimate for filtering. |
| `rent_band` | Illustrative rent categories may be mistaken for verified housing prices. | Exclude from scoring | Numerical rent estimates are used for budget eligibility instead. |
| `zip` | Geographic identifiers may indirectly reflect demographic patterns. | Keep as identifier | ZIP codes identify results and break exact similarity ties but are not similarity features. |
| `area_name` | Neighborhood names may carry subjective associations. | Keep for display | Names are used to identify areas, not calculate rankings. Some labels are illustrative. |
| `median_rent_usd_suppressed` | Missing or suppressed rent data may affect neighborhood coverage. | Keep as data-quality information | The flag helps identify unusable ACS rent values and is not included in similarity scoring. |

The four scored lifestyle features are retained provisionally for the current prototype. This is not a finding that they are free from demographic proxy risks.

### Additional Public-Data Features Exposed Through `area_stats`

The review above covers the 13 columns in the recommender's cleaned feature dataset. However, the MCP `area_stats` tool also returns Census and Zillow statistics that are not used directly in similarity scoring.

These fields need to be considered because the agent may use them when answering neighborhood questions.

| Fields | Potential Risk | Decision |
|---|---|---|
| `B25003_002E`, `B25003_003E` (owner/renter counts) | Housing tenure may be associated with income, demographic patterns, and neighborhood composition. | Keep for factual aggregate information. Do not use tenure or renter share to steer users toward or away from neighborhoods based on assumptions about residents. |
| `B25077_001E`, `zillow_home_value_index` (home values) | Property values may reflect neighborhood wealth and historical inequalities. | Keep for factual reference only. Do not use home values as a substitute for demographic characteristics or neighborhood desirability. |
| `B07003_001E`, `B07003_004E`, `B07003_008E`, `B07003_010E`, `moved_different_house_pct` (mobility) | Residential mobility may indirectly reflect population characteristics. | Keep for factual aggregate information. Do not use migration patterns to infer who belongs in a neighborhood. |
| `B01003_001E`, `population` (population) | Population counts may be misused to make assumptions about residents. | Keep for factual information, not demographic steering. |
| `B11016_001E` (households) | Household counts may be mistaken for information about family composition. | Keep for factual information. Do not infer family suitability or preferences. |
| `B25064_001E`, `median_rent_usd`, `zillow_rent_index` (rent) | Rent differences may be associated with socioeconomic and demographic patterns. | Keep for factual reference and supported budget calculations. Do not use rent as a demographic substitute. |
| `NAME`, `zip` (identifiers) | Geographic identifiers may indirectly reflect demographic patterns. | Keep for identifying areas, not demographic targeting. |
| `*_suppressed`, `*_missing` (data-quality flags) | Missing data may affect neighborhood coverage and interpretation. | Keep for transparency about unavailable or imputed values, not ranking. |

`B07003_008E` specifically represents male residents who moved within the same county. It should not be interpreted as the total number of people who moved.

**Housing tenure is a particular concern.** Reporting owner-occupied or renter-occupied housing counts as public statistics is different from using those counts to decide where someone should live.

For example, the agent may explain a ZIP's renter share when asked for factual information. It should not recommend or exclude neighborhoods based on assumptions about the people who rent or own homes there.

These are recommended usage limits for the prototype. This review does not establish that the LLM agent consistently enforces them.


## 2. Existing Safeguards

The current implementation includes the following safeguards:

- The similarity calculation does not directly use protected demographic characteristics.
- Household type and housing preference are validated independently.
- Household type is not a similarity feature.
- Co-living suitability is included only when co-living is selected.
- Budget filtering is separate from similarity scoring.
- Unreliable and unsupported lifestyle features are excluded from scoring.
- The MCP ethics tool defines rules against demographic filtering, demographic steering, and tenant scoring. Enforcement by the LLM agent requires separate verification.

These safeguards reduce some risks but do not establish that the recommendation system is free from demographic bias.

Task #18 introduced structured fair-housing rules covering demographic filtering, tenant scoring, inferred housing preferences, and prohibited-request routing. These rules are consistent with this feature review. Their enforcement by the LLM agent requires separate integration testing.

## 3. Feature Risks and Limitations

### Feature Sources

The lifestyle scores come from the project's blended starter dataset. The documentation describes their intended purposes but does not fully explain how the scores were originally calculated.

Their accuracy and possible demographic effects remain unverified.

### Feature Correlations

We independently checked correlations using `data/area_features_clean.csv`.

Notable results include:

| Features | Correlation |
|---|---:|
| `social` and `quiet` | -0.825 |
| `social` and `co_living_friendly` | 0.778 |
| `transit` and `social` | 0.551 |
| `transit` and `walkable` | 0.662 |

The relationships between `social`, `quiet`, and `co_living_friendly` may affect how much influence related neighborhood characteristics have in the similarity calculation.

However, these are correlations between neighborhood features, not measurements of demographic discrimination.

### Housing Tenure and Feature Correlations

I also checked whether the four scored lifestyle features are related to neighborhood renter share.

Renter share was calculated using Census owner-occupied (`B25003_002E`) and renter-occupied (`B25003_003E`) housing counts:

`renter_share = renter_occupied / (owner_occupied + renter_occupied)`

The analysis included 78 ZIP codes with usable tenure data out of 80 rows in the cleaned public dataset. No missingness or suppression flags were recorded for the two tenure columns.

| Feature | Correlation with Renter Share |
|---|---:|
| `transit` | +0.643 |
| `co_living_friendly` | +0.599 |
| `social` | +0.324 |
| `quiet` | +0.004 |

The strongest relationships were for `transit` and `co_living_friendly`. Neighborhoods with higher scores on these features also tended to have higher renter shares.

These findings are useful for identifying possible proxy risks, but renter share is not itself a protected demographic characteristic. The correlations do not establish demographic discrimination.

The results support keeping housing-tenure information separate from recommendation scoring and avoiding assumptions about residents based on whether they rent or own their homes.

### Similarity Calculation

The recommender uses fixed-dimensional cosine similarity.

Even when a user does not select a feature, the neighborhood's score on that feature can still affect similarity through the neighborhood vector's magnitude.

This means unselected features may influence rankings.

### Geographic Proxy Risks

ZIP-level features can be associated with protected demographic characteristics even when demographic information is not directly included.

The current dataset and tests do not establish whether the recommendations produce unequal outcomes across protected groups.

### Data Limitations

The system uses neighborhood-level data and rent reference estimates rather than verified available housing listings.

Neighborhood review coverage is also limited, so review-based descriptions may not represent all ZIP codes equally.

## 4. Household Comparison Tests

We compared otherwise-identical user profiles while changing only `household` between `alone` and `with_co_leaser`.

All other inputs remained unchanged.

| Test | Profile Pairs | Result |
|---|---:|---|
| Both housing preferences | 2 | Passed |
| Different budgets | 4 | Passed |
| Different lifestyle preferences | 6 | Passed |
| Co-living preference combinations | 5 | Passed |
| **Total** | **17** | **All passed** |

The tests confirmed that household changes did not affect candidate counts, recommendation status, ZIP rankings, or similarity scores in the tested scenarios.

This verifies household-input independence for these scenarios, not demographic fairness.

## 5. Excluded-Feature Verification

We tested whether changing four excluded feature columns affected recommendations:

- `walkable`
- `pet_friendly`
- `migration_score`
- `single_family_friendly`

The test modified these values in a temporary copy of the dataset and compared recommendation results for both apartment and co-living profiles.

**Result:** The excluded-feature test passed. Recommendation results remained unchanged in both tested scenarios.

The original dataset was not modified.

## 6. Feature Sensitivity Analysis

We examined how setting one neighborhood feature column to zero at a time affected recommendation rankings. The analysis used the existing `recommend()` function with a temporary copy of the dataset, keeping the user profile and other feature values unchanged.

The analysis used the existing 20 evaluation profiles and preserved the original budget filter.

For each feature, we compared the original top-five ZIP recommendations with results obtained after setting that feature's neighborhood scores to zero.

### Results

| Feature Zeroed | Selected by User? | Comparable Profiles | Top-5 Membership Changed | Average ZIP Overlap |
|---|---|---:|---:|---:|
| `transit` | Yes | 7 | 4 | 4.14 |
| `transit` | No | 8 | 8 | 3.00 |
| `social` | Yes | 6 | 6 | 3.17 |
| `social` | No | 12 | 12 | 1.92 |
| `quiet` | Yes | 5 | 5 | 3.20 |
| `quiet` | No | 11 | 10 | 1.45 |
| `co_living_friendly` | Yes | 6 | 5 | 2.17 |

Average overlap measures how many ZIP codes appear in both the original and modified top-five results.

Profiles without affordable ZIPs or without remaining active features were excluded from the relevant comparisons. When the feature being zeroed is the user's only active preference, the comparison is marked as not applicable. This avoids interpreting a result where the selected preference no longer has a usable neighborhood score.

### Findings

The analysis showed that setting neighborhood feature scores to zero can change recommendations even when users did not select those features.

For example, setting quiet scores to zero changed the top-five membership in 10 of 11 comparable profiles where quietness was not selected.

This confirms that unselected features can influence rankings through the baseline cosine-similarity calculation.

The analysis also showed that `co_living_friendly` has a meaningful effect on co-living rankings.

These results measure feature influence, not demographic discrimination.

Setting a feature's neighborhood scores to zero is a diagnostic experiment. It does not necessarily have the same effect as removing that feature from the scoring calculation, and it does not mean the feature should be removed from the production system.

### Downtown Quiet-Score Example

The influence of unselected features is not always a problem. In some cases, considering other neighborhood characteristics may produce a more realistic recommendation.

For a quiet-only profile with a $2,500 budget, Downtown (33128) ranks 2nd out of 67 affordable ZIP codes when sorted by its quietness score alone. However, it ranks 35th under the current cosine-similarity recommender.

Downtown has a high quietness score (0.937), but it also has high transit (0.919) and social (0.800) scores. These additional features affect its cosine similarity, even though the user only selected `quiet`.

This example suggests that the quietness score may not fully represent the neighborhood's characteristics. The lower cosine ranking may be more realistic, but neither ranking has been independently validated as the better recommendation.

This example describes the current baseline recommender. The rankings may change if the scoring method is updated.

## 7. Testing Summary

The following checks were completed:

| Check | Result |
|---|---|
| Household comparison tests | 4 passed |
| Excluded-feature test | 1 passed |
| Sensitivity-analysis tests | 6 passed |
| Full project test suite (previous run, before these review changes) | 102 passed |
| Baseline evaluation profiles | 20 completed |
| Budget filter pass rate | 100% |

The sensitivity tests confirmed that the analysis reproduced the original recommendation rankings, handled no-budget scenarios, and respected the conditional co-living feature.

The Task #20 tests and sensitivity analysis were run using:

`python scripts/test_fair_housing.py`
`python scripts/test_feature_sensitivity.py`
`python scripts/feature_sensitivity.py`

The two test files passed without pytest (5/5 fair-housing tests and 6/6 sensitivity tests). Both test files were also run successfully from outside the repository directory to verify that their imports and file paths work correctly.

### Compatibility With the Tuned Recommender

I also tested the sensitivity analysis against the current implementation of Frank's tuned recommender from Task #15.

The analysis completed all 80 feature comparisons across the 20 evaluation profiles without errors. Of these, 55 were comparable, 3 had no affordable ZIPs, and 8 had no active features remaining. The other comparisons involved features not used by the corresponding housing preference.

The analysis used the tuned recommender's own scoring function rather than independently calculating cosine similarity. This confirms that the updated analysis can run with the current tuned implementation without changing the production recommender.

The ranking results differed from the baseline, as expected, because the tuned recommender uses a different scoring method. The sensitivity results in Section 6 describe the current baseline and may change when the tuned scoring method is integrated.

## 8. Final Decisions and Recommendations

Based on the current implementation and testing:

- Keep `transit`, `social`, and `quiet` provisionally as baseline similarity features.
- Keep `co_living_friendly` only for explicitly selected co-living preferences.
- Continue excluding `walkable`, `pet_friendly`, `migration_score`, and `single_family_friendly` from similarity scoring.
- Keep rent information for budget filtering rather than similarity scoring.
- Keep identifiers and data-quality fields outside similarity scoring.
- Document the influence of unselected features and the limitations of fixed-dimensional cosine similarity.
- Validate feature sources and possible demographic impacts before considering real-world deployment.

The scored lifestyle features are retained for the current prototype because they represent supported user preferences and are already part of the baseline recommender. However, their original construction is not fully documented, and the sensitivity analysis shows that even unselected features can influence rankings. These findings support further validation before deployment rather than treating the current feature set as fully verified.

No additional feature removal is proposed for the current prototype. The available tests identify ranking sensitivity but do not establish whether retained features create discriminatory outcomes.

The retained features therefore require further validation rather than being treated as confirmed safe.

## 9. Conclusion

This review documents potential demographic proxy risks, feature-selection decisions, and the results of comparison and sensitivity tests.

The current system includes safeguards that support preference-based recommendations, but the underlying feature scores and possible demographic effects still need further validation.

This is a technical review and does not establish legal compliance with fair-housing requirements.