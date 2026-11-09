"""Co-leaser vs co-living guardrail.

household and housing_preference stay independent inputs. A co-leaser shares
a private lease. Co-living is a housing type. Neither value is inferred from
the other, including when both columns are read from the same data row.

All four combinations are valid:

- alone + own_apartment
- alone + co_living
- with_co_leaser + own_apartment
- with_co_leaser + co_living

A pair missing from the data is a coverage gap. It is still a valid input.
"""

from __future__ import annotations

from scripts.feature_schema import VALID_HOUSING_PREFERENCES

# The only household list. scripts/recommender.py imports it and calls
# validate_household_housing from validate_profile. Housing types are not
# copied here; they come from feature_schema.VALID_HOUSING_PREFERENCES.
VALID_HOUSEHOLDS = ("alone", "with_co_leaser")


def household_housing_combinations() -> list[tuple[str, str]]:
    """Return every household x housing_preference pair, with none dropped.

    The pairs follow the two allowed lists. A new value added to either list
    becomes a valid pair here instead of being rejected for not fitting a
    fixed count of four.
    """
    return [
        (household, housing_preference)
        for household in VALID_HOUSEHOLDS
        for housing_preference in sorted(VALID_HOUSING_PREFERENCES)
    ]


def validate_household_housing(
    household: str, housing_preference: str
) -> tuple[str, str]:
    """Check each input on its own and return both unchanged.

    Unknown values raise ValueError. A known household never rewrites
    housing_preference, and a known housing preference never rewrites household.
    """
    if household not in VALID_HOUSEHOLDS:
        raise ValueError(f"Unknown household: {household}")
    if housing_preference not in VALID_HOUSING_PREFERENCES:
        raise ValueError(f"Unknown housing preference: {housing_preference}")
    return household, housing_preference


def validate_household_housing_row(row: dict) -> tuple[str, str]:
    """Read household and housing_preference from one data row.

    The two columns are checked separately. The pair returned is the pair
    that was stored. Nothing is filled in from the other column.
    """
    if "household" not in row or "housing_preference" not in row:
        raise ValueError(
            "Data row must include household and housing_preference as separate columns."
        )
    return validate_household_housing(row["household"], row["housing_preference"])


def missing_combinations(rows: list[dict]) -> list[tuple[str, str]]:
    """Return valid pairs that are absent from the data rows.

    Missing does not mean forbidden. with_co_leaser + co_living stays valid
    even when the data has no row for it.
    """
    present = {
        validate_household_housing_row(row)
        for row in rows
    }
    return [pair for pair in household_housing_combinations() if pair not in present]
