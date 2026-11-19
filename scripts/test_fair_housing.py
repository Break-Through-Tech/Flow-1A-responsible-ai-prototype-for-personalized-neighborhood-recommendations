"""Fair-housing comparison tests for the neighborhood recommender."""

from scripts.recommender import recommend


def compare_household_results(budget, housing, tags):
    """Check that changing only household does not affect recommendations."""
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
    for housing in ["own_apartment", "co_living"]:
        compare_household_results(2500, housing, ["transit", "quiet"])


def test_household_independence_across_budgets():
    for budget in [1000, 1600, 2500, 5000]:
        compare_household_results(
            budget,
            "own_apartment",
            ["transit"],
        )


def test_household_independence_across_preferences():
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
    preferences = [
        ["transit"],
        ["social"],
        ["quiet"],
        ["transit", "quiet"],
        ["co_living", "transit"],
    ]

    for tags in preferences:
        compare_household_results(2500, "co_living", tags)