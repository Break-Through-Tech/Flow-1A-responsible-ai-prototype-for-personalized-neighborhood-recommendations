"""Checks that household and housing preference stay independent.

Run from the repo root (also collected by pytest if it is installed):

    python scripts/test_co_leaser_guardrail.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.co_leaser_guardrail import validate_household_housing
from scripts.recommender import validate_profile

COMBINATIONS = (
    ("alone", "own_apartment"),
    ("alone", "co_living"),
    ("with_co_leaser", "own_apartment"),
    ("with_co_leaser", "co_living"),
)


def test_household_and_housing_stay_independent():
    for household, housing in COMBINATIONS:
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


def test_guardrail_returns_each_combination_unchanged():
    for household, housing in COMBINATIONS:
        assert validate_household_housing(household, housing) == (household, housing)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
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
