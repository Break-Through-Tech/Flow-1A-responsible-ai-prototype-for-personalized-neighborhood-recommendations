import pytest

from scripts.recommender import validate_profile


@pytest.mark.parametrize("household", ["alone", "with_co_leaser"])
@pytest.mark.parametrize("housing", ["own_apartment", "co_living"])
def test_household_and_housing_stay_independent(household, housing):
    profile = {
        "household": household,
        "housing_preference": housing,
        "budget_max": 2000,
        "tags": ["transit"],
    }
    result = validate_profile(profile)
    # neither value should get changed based on the other
    assert result["household"] == household
    assert result["housing_preference"] == housing
