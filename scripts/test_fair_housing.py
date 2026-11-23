"""Tests for household independence and excluded recommender features.

Run from the repository root:

    python scripts/test_fair_housing.py
"""

import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.recommender import recommend


def compare_household_results(budget, housing, tags):
    """Check that household type does not change recommendations."""
    base_profile = {
        "housing_preference": housing,
        "budget_max": budget,
        "tags": tags,
    }

    alone = recommend({
        **base_profile,
        "household": "alone",
    })

    with_co_leaser = recommend({
        **base_profile,
        "household": "with_co_leaser",
    })

    assert alone["candidate_count"] == with_co_leaser["candidate_count"]
    assert alone["status"] == with_co_leaser["status"]

    alone_results = [
        (item["zip"], item["similarity"])
        for item in alone["recommendations"]
    ]

    co_leaser_results = [
        (item["zip"], item["similarity"])
        for item in with_co_leaser["recommendations"]
    ]

    assert alone_results == co_leaser_results


def test_household_does_not_change_rankings():
    """Check both housing preferences with the same budget and tags."""
    for housing in ["own_apartment", "co_living"]:
        compare_household_results(2500, housing, ["transit", "quiet"])


def test_household_independence_across_budgets():
    """Check different budgets, including one with no affordable ZIPs."""
    for budget in [1000, 1600, 2500, 5000]:
        compare_household_results(
            budget,
            "own_apartment",
            ["transit"],
        )


def test_household_independence_across_preferences():
    """Check that different lifestyle preferences do not change this rule."""
    preferences = [
        ["transit"],
        ["social"],
        ["quiet"],
        ["transit", "social"],
        ["social", "quiet"],
        ["transit", "social", "quiet"],
    ]

    for tags in preferences:
        compare_household_results(2500, "own_apartment", tags)


def test_household_independence_for_co_living():
    """Check household independence when co-living is selected."""
    preferences = [
        ["transit"],
        ["social"],
        ["quiet"],
        ["transit", "quiet"],
        ["co_living", "transit"],
    ]

    for tags in preferences:
        compare_household_results(2500, "co_living", tags)


def test_excluded_features_do_not_change_rankings():
    """Check that excluded features do not affect recommendations."""
    data_path = _ROOT / "data" / "area_features_clean.csv"

    original = pd.read_csv(data_path, dtype={"zip": str})
    modified = original.copy()

    excluded_features = [
        "walkable",
        "pet_friendly",
        "migration_score",
        "single_family_friendly",
    ]

    # Change the excluded scores without changing the real dataset.
    for feature in excluded_features:
        modified[feature] = 1.0 - modified[feature]

    profiles = [
        {
            "household": "alone",
            "housing_preference": "own_apartment",
            "budget_max": 2500,
            "tags": ["transit", "quiet"],
        },
        {
            "household": "with_co_leaser",
            "housing_preference": "co_living",
            "budget_max": 2500,
            "tags": ["social", "co_living"],
        },
    ]

    # Use a temporary CSV so the project's data stays unchanged.
    with TemporaryDirectory() as temp_dir:
        modified_path = Path(temp_dir) / "area_features_clean.csv"
        modified.to_csv(modified_path, index=False)

        # Keep the same ACS metadata so only excluded feature scores change.
        metadata_path = data_path.with_suffix(".metadata.json")
        if metadata_path.exists():
            shutil.copy(
                metadata_path,
                modified_path.with_suffix(".metadata.json"),
            )

        for profile in profiles:
            original_result = recommend(profile, data_path=data_path)
            modified_result = recommend(profile, data_path=modified_path)

            assert original_result["candidate_count"] == modified_result["candidate_count"]
            assert original_result["status"] == modified_result["status"]
            assert original_result["recommendations"] == modified_result["recommendations"]

if __name__ == "__main__":
    tests = [
        (name, fn)
        for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    ]

    failed = 0

    for name, fn in tests:
        try:
            fn()
        except Exception as exc:
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok    {name}")

    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)