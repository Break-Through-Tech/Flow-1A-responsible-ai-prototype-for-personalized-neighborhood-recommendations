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

## 6. Data audit, suppression handling & EDA (Tasks #2–#4)

The starter data in `data/` has been audited, cleaned of Census suppression sentinels, and explored for the anchor ZIPs (Wynwood 33127, Downtown 33128, Brickell 33130). This work lives in one notebook plus two standalone scripts:

- **`notebooks/Flow-1A-project-notebook.ipynb`** — the main notebook. Run cells top to bottom (or "Run All"); it covers, in order: Task #2 (row/column audit against `data_dictionary.md`, anchor-ZIP confirmation), Task #3 (suppression-sentinel handling), and Task #4 (distributions, correlation matrix, anchor-ZIP profile, NLP corpus coverage, demographic-proxy check). It imports the reusable checks from `scripts/eda.py`, so make sure the repo root is on `sys.path` — the first cell already does this (`sys.path.append(str(Path("..").resolve()))`).
- **`scripts/clean_data.py`** — Task #3's sentinel handling as a standalone script. Run from the repo root:
  ```
  python scripts/clean_data.py
  ```
  It cleans both `data/miami_dade_public_features.csv` and `data/area_features.csv`: any cell equal to the Census suppression sentinel (`-666666666`, see `data_dictionary.md`) or a plain null is flagged (`<col>_suppressed` / `<col>_missing`) and median-imputed. It writes `data/miami_dade_public_features_clean.csv` and `data/area_features_clean.csv` and prints a per-column report. The raw CSVs are left untouched, so the recommender should read the `_clean` files. Re-running rewrites the `_clean` files; if git shows them as modified only by line endings, `git checkout -- data/` restores them.
- **`scripts/eda.py`** — Task #4's reusable checks and chart builders (`describe_numeric`, `missingness_report`, `correlated_pairs`, `plot_rent_distribution`, etc.), used by the notebook but also runnable on its own. Because it imports from `scripts.clean_data`, run it as a module from the repo root — not `python scripts/eda.py` directly:
  ```
  python -m scripts.eda
  ```
  This prints the same checks the notebook shows and (re)writes the five presentation charts to `notebooks/figures/`.
- **`scripts/validate_data.py`** — a lighter sanity check (Task #1/#2 support). Run from the repo root:
  ```
  python scripts/validate_data.py
  ```
  It lists each CSV in `data/`, prints shape/dtypes, and confirms all three anchor ZIPs are present in every file.

The closing "Takeaways for Task #5 and Task #6" cell of the notebook summarizes what Task #4 found: `walkable` is a sentinel artifact rather than a real feature and must be recomputed or dropped, `pet_friendly` is constant, several feature pairs are redundant, tenure mix carries demographic-proxy risk, and the NLP corpus is thin. Read it before starting Task #5 (feature schema) — several of these need a decision before that work begins.
