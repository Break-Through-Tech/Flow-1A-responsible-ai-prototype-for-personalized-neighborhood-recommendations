
"""Tests for the feature sensitivity analysis.

Run directly without pytest:

    python scripts/test_feature_sensitivity.py
"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.feature_sensitivity import (
    FEATURES,
    PROFILES_PATH,
    analyze,
    analyze_profile,
    count_overlap,
    get_ranked_zips,
)
from scripts.recommender import recommend, validate_profile


def load_profiles():
    """Load the existing evaluation profiles."""
    return json.loads(PROFILES_PATH.read_text())


def test_baseline_rankings_match_recommender():
    """Check that baseline ZIPs come from the recommender."""
    for profile in load_profiles():
        expected = [
            item["zip"] for item in recommend(profile)["recommendations"]
        ]
        actual = get_ranked_zips(profile)

        assert actual == expected, profile["profile_id"]


def test_feature_removal_results():
    """Check that each feature comparison returns valid results."""
    results = analyze()

    assert len(results) == len(load_profiles()) * len(FEATURES)

    for row in results:
        assert row["status"] in {
            "ok",
            "not_used",
            "no_candidates",
            "no_active_features",
        }

        if row["status"] == "ok":
            assert isinstance(row["same_order"], bool)
            assert isinstance(row["overlap"], int)
            assert isinstance(row["original_count"], int)
            assert 0 <= row["overlap"] <= row["original_count"]
        else:
            assert row["same_order"] is None
            assert row["overlap"] is None


def test_no_budget_match_is_handled():
    """Check that a profile with no affordable ZIPs is handled."""
    profile = {
        "profile_id": "no_budget_match",
        "household": "alone",
        "housing_preference": "own_apartment",
        "budget_max": 1,
        "tags": ["transit"],
    }

    results = analyze_profile(profile, load_areas())

    for row in results:
        if row["feature"] == "co_living_friendly":
            assert row["status"] == "not_used"
        else:
            assert row["status"] == "no_candidates"


def load_areas():
    """Load the original neighborhood data for testing."""
    import pandas as pd

    return pd.read_csv(
        _ROOT / "data" / "area_features_clean.csv",
        dtype={"zip": str},
    )


def test_co_living_feature_is_conditional():
    """Check that co-living is only scored for co-living profiles."""
    base_profile = {
        "profile_id": "housing_test",
        "household": "alone",
        "budget_max": 2500,
        "tags": ["transit", "quiet"],
    }

    own_profile = {
        **base_profile,
        "housing_preference": "own_apartment",
    }
    co_living_profile = {
        **base_profile,
        "housing_preference": "co_living",
    }

    own_results = analyze_profile(own_profile, load_areas())
    co_living_results = analyze_profile(co_living_profile, load_areas())

    own_feature = next(
        row for row in own_results
        if row["feature"] == "co_living_friendly"
    )
    co_living_feature = next(
        row for row in co_living_results
        if row["feature"] == "co_living_friendly"
    )

    assert own_feature["status"] == "not_used"
    assert own_feature["selected"] is False

    assert co_living_feature["status"] == "ok"
    assert co_living_feature["selected"] is True


def test_unselected_features_are_reported():
    """Check that unselected features are included in the analysis."""
    results = analyze()

    unselected = [
        row for row in results
        if row["status"] == "ok"
        and not row["selected"]
    ]

    assert unselected

    for row in unselected:
        assert isinstance(row["same_order"], bool)
        assert isinstance(row["overlap"], int)


def test_count_overlap():
    """Check that shared ZIPs are counted correctly."""
    original = ["33127", "33128", "33130", "33132", "33136"]
    changed = ["33130", "33128", "33137", "33139", "33140"]

    assert count_overlap(original, changed) == 2
    assert count_overlap(original, list(reversed(original))) == 5
    assert count_overlap(original, ["33010", "33012"]) == 0
    assert count_overlap(original, []) == 0


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
