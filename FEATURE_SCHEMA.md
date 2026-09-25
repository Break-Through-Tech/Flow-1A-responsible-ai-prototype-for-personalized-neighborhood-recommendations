# Task #5: Feature Vector Schema

This document defines the feature vector schema for the September baseline
neighborhood recommender.

Task #5 has three responsibilities:

1. Choose which columns should be used for similarity.
2. Choose how the selected numerical features should be scaled.
3. Define how user preferences map to dataset columns.

Budget is handled separately as a hard filter and is not part of the
similarity vector.

The implementation of these decisions is in `scripts/feature_schema.py`.

---

## 1. Feature selection

The cleaned area dataset, `data/area_features_clean.csv`, contains 13 columns.
Not every column should affect neighborhood similarity.

For the baseline, the main similarity features are:

- `transit`
- `social`
- `quiet`

`co_living_friendly` is also available, but only when the user selects
`co_living` as their housing preference.

`median_rent_usd` is kept outside the similarity vector and is used for the
hard budget filter.

### Feature decisions

| Column | Decision | Role |
|---|---|---|
| `transit` | Include | Similarity feature |
| `social` | Include | Similarity feature |
| `quiet` | Include | Similarity feature |
| `co_living_friendly` | Conditional | Similarity feature only for `co_living` |
| `median_rent_usd` | Keep outside similarity | Hard budget filter |
| `zip` | Keep outside similarity | ZIP identifier |
| `area_name` | Keep outside similarity | Display label |
| `walkable` | Exclude from similarity | Current signal is broken/untrustworthy |
| `pet_friendly` | Exclude from similarity | Constant across all ZIPs |
| `migration_score` | Exclude from similarity | No current user preference maps to it |
| `single_family_friendly` | Exclude from similarity | Left over from an older product design |
| `rent_band` | Exclude from similarity | Illustrative rent bucket |
| `median_rent_usd_suppressed` | Exclude from similarity | Data-quality flag |

### Why these decisions were made

#### `transit` — included

`transit` directly represents a preference that users can select. The dataset
provides a 0–1 transit-access score that varies across ZIPs, so it can help
distinguish neighborhoods.

For example, if transit is important to a user, a ZIP with a stronger transit
score can be a better match for that preference than a ZIP with a weaker
score. Task #4 did not flag `transit` as broken or constant.

#### `social` — included

`social` represents another preference users can explicitly select, and its
values vary across ZIPs.

Task #4 found that `social` and `quiet` are strongly negatively correlated.
This means ZIPs with higher social scores often have lower quiet scores.
However, they still represent different user preferences. A user can care
specifically about social activity, so `social` remains in the baseline
schema while the correlation is documented as a limitation.

#### `quiet` — included

`quiet` is also a supported user preference with usable variation across
ZIPs.

Although Task #4 found a strong relationship between `quiet` and `social`,
quietness represents a different preference from social activity. A user
looking for a calmer neighborhood may explicitly prioritize `quiet`, so it
remains a baseline similarity feature.

#### `walkable` — excluded from the baseline

`walkable` is a valid user preference, but the current column is not a
trustworthy walkability signal.

Task #4 found that it was created by normalizing `median_rent_usd` while the
Census suppression sentinel was still present. This pushed the three
suppressed ZIPs to 0 and compressed almost all other ZIPs very close to 1.

Recomputing the column from cleaned rent would fix the suppression problem,
but it would still make the feature a rent proxy rather than an independent
measure of walkability. For the baseline, it is safer to leave this feature
out than to treat rent as walkability.

#### `pet_friendly` — excluded from the baseline

`pet_friendly` is also a valid user preference, but the current feature is
constant at 0.6 across all 80 ZIPs.

Because every ZIP receives the same value, the feature cannot help the
recommender distinguish one neighborhood from another. The preference remains
recognized, but it is not scored until a better pet-friendly signal is
available.

#### `co_living_friendly` — conditionally included

`co_living_friendly` measures how suitable a ZIP is for co-living. It should
not affect recommendations for users who want their own apartment.

When `housing_preference = "co_living"`, this feature is added to the
similarity dimensions once. If `co_living` also appears in the user's tag
list, it is not counted a second time.

#### `single_family_friendly` — excluded

Git history shows that `single_family_friendly` was introduced when an older
version of the project supported single-family homes as a housing choice.

The current project supports only `own_apartment` and `co_living`. Because
users can no longer select a single-family-home preference, this column should
not influence current recommendations.

#### `migration_score` — excluded

`migration_score` represents in-migration activity, but the current product
does not provide a migration-related user preference.

Including it would allow a characteristic the user never selected to affect
their similarity score. It therefore remains outside the baseline vector.

#### `median_rent_usd` — budget filter only

`median_rent_usd` is intentionally excluded from cosine similarity.

Task #5 specifies that budget is a hard filter. If a user's maximum budget is
$2,000, ZIPs above that amount should be removed before similarity is
calculated. A cheaper ZIP should not automatically receive a better
similarity score simply because it costs less.

#### Metadata columns

`zip` is kept as the identifier and `area_name` is kept for displaying the
recommended neighborhood.

`rent_band` is not used for similarity because affordability is already
handled with continuous `median_rent_usd`, and Task #4 found that the rent
bucket could not distinguish the three anchor ZIPs.

`median_rent_usd_suppressed` is a data-quality flag from cleaning. It is useful
for transparency, but suppression history should not affect neighborhood
similarity.

---

## 2. Scaling decision

### Decision

The baseline uses the existing 0–1 feature scores without applying additional
scaling.

The similarity features are:

- `transit`
- `social`
- `quiet`
- `co_living_friendly` when co-living is selected

I verified their ranges directly in `data/area_features_clean.csv`:

| Feature | Minimum | Maximum | Role |
|---|---:|---:|---|
| `transit` | 0.00 | 1.00 | Similarity |
| `social` | 0.00 | 1.00 | Similarity |
| `quiet` | 0.50 | 1.00 | Similarity |
| `co_living_friendly` | 0.15 | 0.92 | Conditional similarity |

### Why no additional scaling?

All selected similarity features are already represented as scores within the
same 0–1 range. The similarity vector does not mix these scores with values on
very different scales, such as rent in dollars or population counts.

For example, `median_rent_usd` is not included in the similarity vector. It is
handled separately by the budget filter.

Because the selected features are already on a common scale, applying another
min-max transformation would add another transformation without solving a
current units or range problem.

The observed ranges are not identical. For example, `quiet` currently ranges
from 0.50 to 1.00 while `transit` ranges from 0.00 to 1.00. For the September
baseline, the existing proxy scores are preserved rather than stretching each
column independently to fill the full 0–1 range.

In `scripts/feature_schema.py`, this decision is recorded as:

`SCALING_METHOD = "pre_normalized_0_1"`

---

## 3. User preference to feature mapping

User preferences arrive as readable inputs such as `transit` or `quiet`, while
the recommender needs numerical dataset columns for similarity.

The baseline mapping is:

| User input | Feature column | Baseline behavior |
|---|---|---|
| `transit` | `transit` | Supported |
| `social` | `social` | Supported |
| `quiet` | `quiet` | Supported |
| `walkable` | None | Recognized, but not scored in the baseline |
| `pet_friendly` | None | Recognized, but not scored in the baseline |
| `housing_preference = "co_living"` | `co_living_friendly` | Added conditionally once |

### Supported lifestyle tags

`transit`, `social`, and `quiet` map directly to their corresponding feature
columns because those columns provide usable numerical signals.

### Recognized but currently unsupported tags

`walkable` and `pet_friendly` remain recognized user preferences. They are not
treated as invalid inputs.

However, both map to `None` in the baseline schema because the current dataset
does not provide a usable signal for them:

- `walkable` is excluded because Task #4 found that the current column does not
  reliably measure walkability.
- `pet_friendly` is excluded because every ZIP currently has the same value.

This lets the project keep recognizing these product preferences without
pretending that the current data can score them reliably.

### Co-living

Co-living is primarily handled through `housing_preference`, rather than as an
additional lifestyle dimension.

When:

`housing_preference = "co_living"`

the schema adds:

`co_living_friendly`

once.

One evaluation profile currently includes `co_living` both as the housing
preference and inside its tags. The schema does not count the same preference
twice.

### Invalid inputs

A completely unknown or misspelled tag is different from a recognized but
unsupported preference.

For example:

- `walkable` → recognized, currently not scored
- `pet_friendly` → recognized, currently not scored
- `trasnit` → invalid input and raises a `ValueError`

The same rule applies to housing preferences. The supported values are
`own_apartment` and `co_living`; an unknown value raises a `ValueError`.

---

## 4. Implementation and validation

The schema is implemented in `scripts/feature_schema.py`.

### `get_similarity_features()`

This function takes the user's lifestyle tags and housing preference and returns
the feature columns that should be used for similarity.

It also:

- skips recognized preferences that do not have a usable baseline feature
- adds `co_living_friendly` once when co-living is selected
- rejects unknown or misspelled lifestyle tags
- rejects unknown housing preferences

### `validate_feature_schema()`

This function checks that the cleaned dataset still matches the assumptions
made by Task #5.

It checks that:

- all required columns exist
- similarity features are numeric
- similarity features have no missing values
- similarity features remain between 0 and 1
- `median_rent_usd` is numeric and has no missing values

The validation only checks the data. It does not modify the CSV.

---

## 5. Testing

The schema was tested against `data/area_features_clean.csv` and with
intentional invalid inputs.

| Check | Result |
|---|---|
| Supported tags map correctly | Passed |
| `walkable` is recognized but skipped for similarity | Passed |
| Co-living activates `co_living_friendly` once | Passed |
| Cleaned dataset passes schema validation | Passed |
| Unknown lifestyle tag raises `ValueError` | Passed |
| Invalid housing preference raises `ValueError` | Passed |
| Missing required column raises `ValueError` | Passed |
| Similarity value outside 0–1 raises `ValueError` | Passed |
| Missing similarity value raises `ValueError` | Passed |
| `python -m py_compile scripts/feature_schema.py` | Passed |

Failure tests were performed on temporary in-memory copies of the data. The
source CSV files were not modified.

---

## Takeaways for Task #6

Task #5 defines the feature contract used by the baseline recommender.

- Read `data/area_features_clean.csv`, not the raw `area_features.csv`.
- Use `median_rent_usd` as the hard budget filter. Do not include budget in
  cosine similarity.
- Use `get_similarity_features(tags, housing_preference)` to get the active
  similarity columns.
- `transit`, `social`, and `quiet` are the baseline similarity features.
- Add `co_living_friendly` only when `housing_preference = "co_living"`, and
  only once.
- Use the existing 0–1 feature scores without additional scaling.
- `walkable` and `pet_friendly` are recognized preferences but are not scored
  in the baseline because their current signals are unusable.
- `zip` is the identifier and `area_name` is for display; neither belongs in
  similarity.
- Run `validate_feature_schema()` when loading the cleaned area-feature data.

Task #6 owns the actual budget filtering, cosine-similarity calculation,
top-k ZIP ranking, and the features returned to explain each match.