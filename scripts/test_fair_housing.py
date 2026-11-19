"""Fair-housing comparison tests for the neighborhood recommender."""

from scripts.recommender import recommend


def test_household_does_not_change_rankings():
    for housing in ["own_apartment", "co_living"]:
        base_profile = {
            "housing_preference": housing,
            "budget_max": 2500,
            "tags": ["transit", "quiet"],
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