
"""Check how changing one feature affects neighborhood recommendations.

Run from the repository root:

    python scripts/feature_sensitivity.py
"""

import json
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.feature_schema import BASE_FEATURES, CONDITIONAL_FEATURES
from scripts.recommender import recommend, validate_profile


ROOT = _ROOT
PROFILES_PATH = ROOT / "eval" / "recommendation_profiles.json"
DATA_PATH = ROOT / "data" / "area_features_clean.csv"
FEATURES = BASE_FEATURES + list(CONDITIONAL_FEATURES.values())


def count_overlap(original_zips, changed_zips):
    """Count ZIPs that appear in both recommendation lists."""
    return len(set(original_zips) & set(changed_zips))


def get_ranked_zips(profile, data_path=None):
    """Get ranked ZIPs from the recommender."""
    result = recommend(profile, data_path=data_path)
    return [item["zip"] for item in result["recommendations"]]


def analyze_profile(profile, areas):
    """Compare original rankings with rankings after zeroing each feature."""
    checked = validate_profile(profile)
    baseline = recommend(profile)
    original_zips = [item["zip"] for item in baseline["recommendations"]]

    results = []

    for feature in FEATURES:
        if feature not in checked["vector_features"]:
            status = "not_used"
        elif baseline["candidate_count"] == 0:
            status = "no_candidates"
        elif (
            feature in checked["active_features"]
            and len(checked["active_features"]) == 1
        ):
            status = "no_active_features"
        else:
            status = "ok"

        row = {
            "profile": profile["profile_id"],
            "feature": feature,
            "selected": feature in checked["active_features"],
            "status": status,
            "same_order": None,
            "overlap": None,
        }

        if status == "ok":
            modified = areas.copy()

            # Zero one feature while keeping all other data unchanged.
            modified[feature] = 0.0

            with TemporaryDirectory() as temp_dir:
                modified_path = Path(temp_dir) / "area_features_clean.csv"
                modified.to_csv(modified_path, index=False)

                # Keep the same ACS period in the temporary dataset.
                metadata_path = DATA_PATH.with_suffix(".metadata.json")
                if metadata_path.exists():
                    shutil.copy(
                        metadata_path,
                        modified_path.with_suffix(".metadata.json"),
                    )

                changed = recommend(profile, data_path=modified_path)

            changed_zips = [
                item["zip"] for item in changed["recommendations"]
            ]

            # Feature changes should not affect budget eligibility.
            assert changed["candidate_count"] == baseline["candidate_count"]
            assert changed["status"] == baseline["status"]

            row["same_order"] = original_zips == changed_zips
            row["overlap"] = count_overlap(original_zips, changed_zips)
            row["original_count"] = len(original_zips)

        results.append(row)

    return results


def analyze():
    """Run the analysis using the existing evaluation profiles."""
    profiles = json.loads(PROFILES_PATH.read_text())
    areas = pd.read_csv(DATA_PATH, dtype={"zip": str})

    results = []

    for profile in profiles:
        results.extend(analyze_profile(profile, areas))

    return results


def main():
    results = analyze()

    print("Feature sensitivity analysis")
    print("Using the existing evaluation profiles\n")

    for feature in FEATURES:
        print(f"Feature: {feature}")

        for selected in [True, False]:
            rows = [
                row for row in results
                if row["feature"] == feature
                and row["selected"] == selected
                and row["status"] == "ok"
            ]

            label = "Selected by user" if selected else "Not selected by user"

            if not rows:
                print(f"  {label}: no comparable profiles")
                continue

            changed_order = sum(not row["same_order"] for row in rows)
            changed_membership = sum(
                row["overlap"] < row["original_count"]
                for row in rows
            )
            average_overlap = sum(row["overlap"] for row in rows) / len(rows)

            print(f"  {label}:")
            print(f"    Comparable profiles: {len(rows)}")
            print(f"    Ranking order changed: {changed_order}")
            print(f"    Top-5 membership changed: {changed_membership}")
            print(f"    Average top-5 overlap: {average_overlap:.2f}")

        for status in ["not_used", "no_candidates", "no_active_features"]:
            count = sum(
                row["feature"] == feature and row["status"] == status
                for row in results
            )
            if count:
                print(f"  {status}: {count}")

        print()


if __name__ == "__main__":
    main()
