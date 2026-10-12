"""NLP theme coverage for the Layer 1 scorecard.

EVAL_FRAMEWORK.md: for each recommended ZIP, % with themes matching user
priority tags. A recommended ZIP counts as covered when crowd_text_snippets.csv
has at least one snippet for that ZIP whose theme is one of the profile's tags.

Themes are topic labels, not sentiment: a "quiet" snippet can say the area is
noisy. Coverage measures whether there is crowd text to explain a match, not
whether the text agrees with it.

Run from the repo root:

    python eval/theme_coverage.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.recommender import recommend

PROFILES_PATH = _ROOT / "eval" / "recommendation_profiles.json"
SNIPPETS_PATH = _ROOT / "data" / "crowd_text_snippets.csv"


def load_zip_themes(path: Path = SNIPPETS_PATH) -> dict[str, set[str]]:
    snippets = pd.read_csv(path, dtype={"zip": str})
    return snippets.groupby("zip")["theme"].apply(set).to_dict()


def main() -> int:
    profiles = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    zip_themes = load_zip_themes()

    covered_total = returned_total = 0
    print(f"{'profile':<26}{'covered':>9}  covered ZIPs")
    for p in profiles:
        request = {k: p[k] for k in ("household", "housing_preference", "budget_max", "tags")}
        zips = [r["zip"] for r in recommend(request)["recommendations"]]
        tags = set(p["tags"])
        covered = [z for z in zips if zip_themes.get(z, set()) & tags]
        covered_total += len(covered)
        returned_total += len(zips)
        print(f"{p['profile_id']:<26}{len(covered):>4}/{len(zips):<4}  {covered or '-'}")

    rate = covered_total / returned_total if returned_total else 0.0
    print(f"\nTheme coverage {rate:.1%} ({covered_total}/{returned_total} recommended ZIPs)")
    print(f"Snippets cover {len(zip_themes)} ZIPs in total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
