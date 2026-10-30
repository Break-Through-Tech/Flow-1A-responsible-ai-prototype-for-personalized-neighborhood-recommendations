# Data Dictionary

## miami_dade_public_features.csv

**Real public aggregate data** for Miami-Dade ZIP codes (ZCTAs). Pulled from Census ACS, migration tables, and Zillow Research-style indices.

**Source and vintage (Task #11).** The `B*` columns are the **2020-2024 ACS 5-year estimates** from `https://api.census.gov/data/2024/acs/acs5`, at ZIP Code Tabulation Area level, pulled on 2026-10-15 by `scripts/pull_census.py`. The starter file this replaced was the 2018-2022 ACS 5-year: `pull_census.py --year 2022` reproduces it byte for byte. The two Zillow columns were not refreshed and still come from the starter file.

Five ZIPs in `miami_dade_zctas.txt` (33090, 33111, 33114, 33116, 33124) have no row: they are PO-box-only ZIPs with no ZCTA, so the Census publishes nothing for them.

In this vintage, median home value (`B25077_001E`) is suppressed for Downtown (33128), one of the anchor ZIPs, and `clean_data.py` imputes it. It was measured ($292,400) in the 2018-2022 file.

| Column | Type | Description |
|--------|------|-------------|
| NAME | string | Census ZCTA label |
| B01003_001E | int | Total population (ACS) |
| B25064_001E | int | Median gross rent (ACS); `-666666666` = missing/suppressed; `3501` is a top-code meaning "$3,500 or more", not a measurement (33149 and 33158 in this vintage) |
| B25077_001E | int | Median home value (ACS); `2000001` is a top-code meaning "$2,000,000 or more", not a measurement |
| B07003_001E | int | Total population 1 year and over (migration universe) |
| B07003_004E | int | Same house 1 year ago |
| B07003_008E | int | Moved within same county, **male only** (the Census label is "Total: Moved within same county: Male"; the total is `B07003_007E`, which this file does not include) |
| B07003_010E | int | Moved from different county within same state |
| B11016_001E | int | Total households |
| B25003_002E | int | Owner-occupied units |
| B25003_003E | int | Renter-occupied units |
| zip | string | 5-digit ZIP code |
| moved_different_house_pct | float | Share who moved to a different house (derived) |
| median_rent_usd | int | Median rent (ACS or derived) |
| population | int | Population count |
| zillow_home_value_index | float | Zillow Research-style home value index |
| zillow_rent_index | float | Zillow Research-style rent index |

## miami_dade_zctas.txt

Plain-text list of Miami-Dade ZIP codes used to scope the project.

## area_features.csv

**Blended starter file** for the recommender. Joins public rent/migration fields with normalized preference proxies (transit, social, quiet, pet-friendly, walkable). Some `area_name` labels are illustrative neighborhood names.

| Column | Type | Description |
|--------|------|-------------|
| zip | string | Miami ZIP code |
| area_name | string | Neighborhood or ZCTA label |
| rent_band | string | Illustrative rent range bucket |
| transit | float 0-1 | Transit access proxy |
| social | float 0-1 | Social activity proxy |
| quiet | float 0-1 | Quiet environment proxy |
| pet_friendly | float 0-1 | Pet-friendly proxy |
| walkable | float 0-1 | Walkability proxy |
| migration_score | float 0-1 | In-migration activity proxy (derived) |
| median_rent_usd | int | ACS median gross rent, copied from `miami_dade_public_features.csv` by `pull_census.py --sync-area-rent` |
| co_living_friendly | float 0-1 | How suitable the ZIP is for co-living (only used when user selects co_living) |

**Primary demo ZIPs:** Wynwood `33127`, Downtown `33128`, Brickell `33130`.

## area_options.csv

**Synthetic** demo cards. **NOT REAL LISTINGS.**

| Column | Type | Description |
|--------|------|-------------|
| option_id | string | Synthetic ID (SYN-*) |
| zip | string | Join key to area_features |
| rent_band | string | Illustrative band |
| housing_preference | string | `own_apartment` or `co_living` |
| household | string | `alone` or `with_co_leaser` (someone on the same private lease — not co-living) |
| tags | string | Comma-separated preference tags |
| summary | string | Short description (e.g. couple + own apartment in Wynwood) |
| disclaimer | string | Must display NOT A REAL LISTING |

## crowd_text_snippets.csv

Demo snippets mimicking public review/forum text for NLP themes. Replace with real filtered corpora during model development.

| Column | Type | Description |
|--------|------|-------------|
| snippet_id | string | Row ID |
| zip | string | Associated ZIP |
| source | string | e.g. kaggle_reviews (document real source when replaced) |
| theme | string | transit, social, quiet, co_living, etc. |
| text | string | Snippet text (aggregate use only) |

## Limitations

- Snapshot data only — not live market feeds.
- Census suppression codes must be handled explicitly in preprocessing.
- Synthetic options are for UI demonstration; never present them as real listings.
- Do not use outputs for leasing decisions or demographic steering.
- English-only text bias may apply when using real review corpora.


## Zillow rent index — Task #12

Source: Zillow Research, ZIP-level smoothed ZORI, all homes plus multifamily.
https://files.zillowstatic.com/research/public_csvs/zori/Zip_zori_uc_sfrcondomfr_sm_month.csv

Downloaded October 29, 2026. Observation month: September 2026.
Units: USD per month.

`data/zillow_rent_snapshot.csv` contains the project ZIPs and their
`zori_rent_usd`, availability, source, observation date, and units.
The accompanying metadata JSON records the source URL and raw-file SHA-256.

The budget filter uses ZORI, while ACS `median_rent_usd` remains unchanged.
Rent is not included in cosine similarity. Comparisons use unrounded values.

Coverage: 75 of 80 ZIPs. ZIPs 33101, 33109, 33158, 33031, and 33039 have
no usable value and are excluded, with no imputation or ACS fallback.

ZORI is an area-level rent index, not an available listing, guaranteed price,
co-living room price, or per-person rent. Household selection does not divide rent.
ACS and ZORI are separate measures, not established lower and upper bounds.

Validation: recommender self-check passed; 18/18 evaluation tests passed.
Existing evaluation budgets were retained. Budget pass rate is 100%;
Precision@3 and Precision@5 are both 0 on those five profiles following
the rent-source change. This does not establish recommendation quality.