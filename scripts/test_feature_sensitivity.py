
"""Tests for the feature sensitivity analysis."""

import json

from scripts.feature_sensitivity import (
    FEATURES,
    PROFILES_PATH,
    analyze,
    analyze_profile,
    count_overlap,
    get_ranked_zips,
)

from scripts.recommender import (
    filter_by_budget,
    load_area_features,
    recommend,
    validate_profile,
)




def load_profiles():
    """Load the existing evaluation profiles."""
    return json.loads(PROFILES_PATH.read_text())


def test_baseline_rankings_match_recommender():
    """Check that our ranking calculation matches the recommender."""
    areas = load_area_features()

    for profile in load_profiles():
        checked = validate_profile(profile)
        candidates = filter_by_budget(areas, checked["budget_max"])
        expected = [
            item["zip"]
            for item in recommend(profile)["recommendations"]
        ]

        if candidates.empty:
            assert expected == []
            continue

        actual = get_ranked_zips(
            candidates,
            checked["vector_features"],
            checked["active_features"],
            checked["top_k"],
        )

        assert actual == expected, profile["profile_id"]


def test_feature_removal_results():
    """Check that each feature comparison has valid results."""
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
    """Check that profiles without affordable ZIPs are handled."""
    areas = load_area_features()

    profile = {
        "profile_id": "no_budget_match",
        "household": "alone",
        "housing_preference": "own_apartment",
        "budget_max": 1,
        "tags": ["transit"],
    }

    results = analyze_profile(profile, areas)

    for row in results:
        if row["feature"] == "co_living_friendly":
            assert row["status"] == "not_used"
        else:
            assert row["status"] == "no_candidates"


def test_co_living_feature_is_conditional():
    """Check that co-living only affects co-living profiles."""
    areas = load_area_features()

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

    own_results = analyze_profile(own_profile, areas)
    co_living_results = analyze_profile(co_living_profile, areas)

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

def test_unselected_features_can_affect_rankings():
    """Check the known influence of unselected features."""
    results = analyze()

    unselected = [
        row for row in results
        if row["status"] == "ok"
        and not row["selected"]
    ]

    assert unselected
    assert any(not row["same_order"] for row in unselected)
    assert any(
        row["overlap"] < row["original_count"]
        for row in unselected
    )

def test_count_overlap():
    """Check that overlap counts shared ZIPs, regardless of order."""
    original = ["33127", "33128", "33130", "33132", "33136"]

    changed = ["33130", "33128", "33137", "33139", "33140"]
    assert count_overlap(original, changed) == 2

    # Changing only the order should not change membership.
    reordered = list(reversed(original))
    assert count_overlap(original, reordered) == 5

    # Lists with no shared ZIPs should have zero overlap.
    unrelated = ["33010", "33012"]
    assert count_overlap(original, unrelated) == 0

    # An empty recommendation list has no overlap.
    assert count_overlap(original, []) == 0
