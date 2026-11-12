# Setup

## Requirements

- Python 3.11
- Git
- VS Code with the Python and Jupyter extensions

## 1. Clone

```
git clone https://github.com/Break-Through-Tech/Flow-1A-responsible-ai-prototype-for-personalized-neighborhood-recommendations.git flow1a
cd flow1a
```

## 2. Virtual environment

Windows (PowerShell):
```
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Mac / Linux:
```
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt should now start with `(.venv)`.

## 3. Install packages

```
pip install -r requirements.txt
```

## 4. Set up .env

Copy `.env.example` to `.env` and fill in your keys.

Windows: `copy .env.example .env`
Mac / Linux: `cp .env.example .env`

`GEMINI_API_KEY` and `CENSUS_API_KEY` are only needed for October. `.env` is gitignored.

## 5. Check it worked

Open `notebooks/Flow-1A-project-notebook.ipynb`. Click "Select Kernel" (top right) → "Python Environments..." → pick `.venv`. Run the first cell. You should see the Python/pandas/numpy/scikit-learn versions print with no errors.

## 6. Data audit, suppression handling & EDA (Tasks #2-#4)

The starter data in `data/` has been audited, cleaned of Census suppression sentinels, and explored for the anchor ZIPs (Wynwood 33127, Downtown 33128, Brickell 33130). This work lives in one notebook plus two standalone scripts:

- **`notebooks/Flow-1A-project-notebook.ipynb`**: the main notebook. Run cells top to bottom (or "Run All"); it covers, in order: Task #2 (row/column audit against `data_dictionary.md`, anchor-ZIP confirmation), Task #3 (suppression-sentinel handling), and Task #4 (distributions, correlation matrix, anchor-ZIP profile, NLP corpus coverage, demographic-proxy check). It imports the reusable checks from `scripts/eda.py`, so the repo root has to be on `sys.path`; the Task #3 cell already does this (`sys.path.append(str(Path("..").resolve()))`).
- **`scripts/clean_data.py`**: Task #3's sentinel handling as a standalone script. Run from the repo root:
  ```
  python scripts/clean_data.py
  ```
  It cleans both `data/miami_dade_public_features.csv` and `data/area_features.csv`: any cell equal to the Census suppression sentinel (`-666666666`, see `data_dictionary.md`) or a plain null is flagged (`<col>_suppressed` / `<col>_missing`) and median-imputed. It writes `data/miami_dade_public_features_clean.csv` and `data/area_features_clean.csv` and prints a per-column report. The raw CSVs are left untouched, so the recommender should read the `_clean` files. Re-running rewrites the `_clean` files; if git shows them as modified only by line endings, `git checkout -- data/` restores them.
- **`scripts/eda.py`**: Task #4's reusable checks and chart builders (`describe_numeric`, `missingness_report`, `correlated_pairs`, `plot_rent_distribution`, etc.), used by the notebook but also runnable on its own. Because it imports from `scripts.clean_data`, run it as a module from the repo root, not `python scripts/eda.py` directly:
  ```
  python -m scripts.eda
  ```
  This prints the same checks the notebook shows and (re)writes the five presentation charts to `notebooks/figures/`.
- **`scripts/validate_data.py`**: a lighter sanity check (Task #1/#2 support). Run from the repo root:
  ```
  python scripts/validate_data.py
  ```
  It lists each CSV in `data/`, prints shape/dtypes, and confirms all three anchor ZIPs are present in every file.

The closing "Takeaways for Task #5 and Task #6" cell of the notebook summarizes what Task #4 found: `walkable` is a sentinel artifact rather than a real feature and must be recomputed or dropped, `pet_friendly` is constant, several feature pairs are redundant, tenure mix carries demographic-proxy risk, and the NLP corpus is thin. Read it before starting Task #5 (feature schema). Several of these need a decision before that work begins.

### Refreshing the Census data (Task #11)

`scripts/pull_census.py` rebuilds `data/miami_dade_public_features.csv` from the Census API, with the same columns in the same order. It needs `CENSUS_API_KEY` in `.env`. Census emails an activation link after signup, and the key is rejected until you click it.

```bash
python scripts/pull_census.py --sync-area-rent   # 2020-2024 ACS 5-year, the default
python scripts/clean_data.py                     # re-flag suppression in the new pull
python eval/run_eval.py                          # see how the rec-engine baseline moved
```

`--sync-area-rent` copies the new `median_rent_usd` into `data/area_features.csv`. Without it, `clean_data.py` stops, because it checks that the two files agree on rent. `--year 2022 --out <path>` reproduces the starter file, which is how its vintage was confirmed. The script prints any ACS annotation codes in the pull and flags the ones `clean_data.py` does not handle.

## 7. Feature vector schema (Task #5)

Task #5 defines which columns are used for similarity, how the selected features are scaled, and how user preferences map to dataset columns.

- **`scripts/feature_schema.py`**: contains the reusable feature schema, preference-to-column mapping, and validation helpers for the baseline recommender.
- **`FEATURE_SCHEMA.md`**: documents the feature-selection decisions, scaling approach, tag mapping, validation results, and handoff notes for Task #6.

The baseline uses `transit`, `social`, and `quiet` as similarity features. `co_living_friendly` is added only when the user selects `co_living`.

Budget is handled separately as a hard filter using `median_rent_usd`; it is not part of the similarity vector.

Task #4 found that the current `walkable` and `pet_friendly` columns do not provide usable baseline signals, so those preferences remain recognized but are not scored.

### Validate the schema

From the repo root:

```bash
python -c "import pandas as pd; from scripts.feature_schema import validate_feature_schema; df=pd.read_csv('data/area_features_clean.csv'); validate_feature_schema(df); print('Feature schema validation passed')"
```

Expected output:

```text
Feature schema validation passed
```

Before starting Task #6, read `FEATURE_SCHEMA.md` and use `scripts/feature_schema.py` rather than redefining the feature rules.

## 8. Rec-engine eval harness (Task #8)

Layer 1 of `EVAL_FRAMEWORK.md`. One command produces all three rec-engine metrics against the profiles in `eval/recommendation_profiles.json`:

```bash
python eval/run_eval.py
```

It reports Precision@3, Precision@5, mean cosine similarity, and budget filter pass rate, plus per-profile diagnostics explaining what limits each score.

Budget filter pass rate is a correctness check rather than a score. The target is 100%, so the script **exits non-zero** if any returned ZIP is outside its profile's budget. That makes it usable as a CI gate. Rent is checked against `data/area_features_clean.csv` directly rather than the value the engine echoes back, and a disagreement between the two is reported separately.

Useful flags:

```bash
python eval/run_eval.py --json eval/results/baseline_sep.json   # machine-readable, for the README scorecard
python eval/run_eval.py --top-k 10                              # rank deeper; P@3 and P@5 still reported
python eval/run_eval.py --profiles path/to/other_profiles.json  # run against a different profile set
```

Mean cosine similarity averages over every returned ZIP, so it changes with `--top-k`. Record and compare baselines at the default of 5.

Exit codes: `0` when every profile ran and stayed within budget, `1` when a returned ZIP is over budget, a profile errored, or a profile is stale (below), `2` when the profile file or data file could not be read. A profile whose budget is below every ZIP's rent is not an error as long as it expects no ZIPs: it scores 0 and is called out in the diagnostics.

**Stale profiles.** If a profile expects a ZIP the engine can never return, the run fails and the profile is marked `[STALE PROFILE]`. That happens when the ZIP's rent is over the profile's budget, when its rent is suppressed, or when it is not in the data. This usually follows a data refresh that moves rents past a budget set by hand, for example a budget pinned to one ZIP's exact rent. The fix is to update the budget or the expected ZIPs, not the harness. When a budget is tied to a specific ZIP's rent, say so in the profile's `description` so the next person knows what to update.

In the profile file, `not_relevant_zips` is optional and ZIPs may be written as strings or bare numbers. A profile missing any other field is rejected with a message naming the profile and the field.

The harness has its own checks:

```bash
python eval/test_run_eval.py
```

Requires `scripts/recommender.py` from Task #6.

### Reading the precision numbers

The evaluation set now contains 20 profiles, including different budgets, household and housing preferences, and edge cases. Some profiles have fewer than 5 expected relevant ZIPs, so their Precision@5 ceiling is below 1.0. The harness prints the ceiling next to each score and the percentage achieved to help interpret the results.

The diagnostics block also lists each unreachable expected ZIP with the reason, tags the user expressed that the schema does not score, and profiles with a single active feature. That last one matters: with one active feature, cosine ranks by how *concentrated* a ZIP is on that feature rather than how *high* it scores.

## 9. NLP theme extraction and theme coverage (Task #14)

`scripts/theme_extraction.py` reads the review text in `data/crowd_text_snippets.csv` and finds which of the five lifestyle themes (`transit`, `social`, `quiet`, `walkable`, `pet_friendly`) each review talks about. It does not trust the hand-written `theme` column, since one review often covers several themes and some argue against their label. Each match becomes a structured snippet:

| Column | Meaning |
|--------|---------|
| `theme` | One of the five themes |
| `stance` | `supports` if the review speaks for the theme, `contradicts` if against ("street noise is real" contradicts `quiet`), `mentions` if it only names the topic ("I took the bus") |
| `evidence` | The exact phrase that matched, so any claim can be traced back to the text |
| `labeled_theme` | The hand label, kept for comparison |

The extractor is a keyword list in the same file, not a model, so every match can be explained. Words that judge a theme on their own (walkable, quiet, noisy) set the stance directly. Plain topic words (bus, sidewalks, dogs, bars) are only a `mention` until the nearest qualifier in the same clause says otherwise: "poor bus service" contradicts transit, "easy bus access" supports it, and in "the bus is great, the sidewalks are dangerous" each word takes its own qualifier. A clause ends at `.` `;` `!` `?` or "but". A negation up to three words before a cue or qualifier flips its stance ("not walkable", "no bus", "not the best city for transit", "the station is not far"). "Not only", "not just", "no problem" and "never a dull moment" are read as emphasis or praise, not negation. Reviews with no ZIP are skipped. If a review says both, `contradicts` wins, so the theme is never overstated. Nothing is generated or paraphrased.

```bash
python scripts/theme_extraction.py                    # counts per theme, reviews with no theme, labels the text never mentions
python scripts/theme_extraction.py --out themes.csv   # also write the structured snippets
```

`themes_for_zip()` returns one ZIP's themes in a shape ready for the `crowd_themes` tool (Task #17).

**Theme coverage** is the NLP row of the scorecard. For every profile in `eval/recommendation_profiles.json`, it takes the ZIPs the engine recommends and checks whether each one has a review about at least one of the profile's tags:

```bash
python eval/theme_coverage.py
python eval/theme_coverage.py --json eval/results/theme_coverage.json
```

It uses the same recommendations as `eval/run_eval.py` and accepts the same `--profiles`, `--data` and `--top-k` flags, plus `--snippets`. Profiles with no extractable tag (e.g. only `co_living`) are skipped rather than scored as 0. Coverage counts a review whether it agrees, disagrees or only mentions the topic; the `supported` rate counts only reviews that speak for the tag. The output also reports, separately, how many recommended ZIPs have any reviews at all (counted from the raw snippets) and how many have a theme match. If few ZIPs have reviews, coverage is limited by the corpus; if many have reviews but few matches, it is limited by the extractor.

Checks: `python eval/test_theme_coverage.py`. The tests use made-up sentences, so they keep passing when the corpus changes.

Known limits: the keyword list was tuned on a small corpus and will miss phrasing it has not seen. It reads words, not intent: "you have to stay super quiet" (a house rule) counts as supporting `quiet` just like "the street is quiet" (a description). "Busy area, but I can't hear any noise" reads as `contradicts`, because the contradicting cue wins. Words like Uber or scooters are not counted as transit, which here means public transit.
