"""Co-leaser vs co-living guardrail.

household and housing_preference are independent user inputs. A co-leaser is
someone on the same private lease; co-living is a housing type. Neither value
is ever inferred from the other, so all four combinations are valid.
"""

from __future__ import annotations

VALID_HOUSEHOLDS = ("alone", "with_co_leaser")
VALID_HOUSING_PREFERENCES = ("own_apartment", "co_living")


def household_housing_combinations() -> list[tuple[str, str]]:
    """Return every household x housing_preference pair, with none excluded."""
    return [
        (household, housing_preference)
        for household in VALID_HOUSEHOLDS
        for housing_preference in VALID_HOUSING_PREFERENCES
    ]


def validate_household_housing(
    household: str, housing_preference: str
) -> tuple[str, str]:
    """Check each input on its own and return both unchanged.

    Unknown values raise ValueError. A valid value is never rewritten based on
    the other field.
    """
    if household not in VALID_HOUSEHOLDS:
        raise ValueError(
            f"Unknown household: {household}. Expected one of {list(VALID_HOUSEHOLDS)}."
        )
    if housing_preference not in VALID_HOUSING_PREFERENCES:
        raise ValueError(
            "Unknown housing preference: "
            f"{housing_preference}. Expected one of {list(VALID_HOUSING_PREFERENCES)}."
        )
    return household, housing_preference
