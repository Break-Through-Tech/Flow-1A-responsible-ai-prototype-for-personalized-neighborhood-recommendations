
"""Check how individual features affect neighborhood recommendations."""

import json
from pathlib import Path

from scripts.feature_schema import BASE_FEATURES, CONDITIONAL_FEATURES

from scripts.recommender import (
    build_area_matrix,
    build_user_vector,
    cosine_similarities,
    filter_by_budget,
    load_area_features,
    rank_areas,
    recommend,
    validate_profile,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILES_PATH = ROOT / "eval" / "recommendation_profiles.json"
FEATURES = BASE_FEATURES + list(CONDITIONAL_FEATURES.values())

def count_overlap(original_zips, changed_zips):
    """Count ZIP codes that appear in both recommendation lists."""
    return len(set(original_zips) & set(changed_zips))

def get_ranked_zips(candidates, vector_features, active_features, top_k):
    """Rank ZIPs using the given feature set."""
    user_vector = build_user_vector(vector_features, active_features)
    area_matrix = build_area_matrix(candidates, vector_features)
    scores = cosine_similarities(user_vector, area_matrix)

    ranked = rank_areas(
        candidates,
        scores,
        vector_features,
        active_features,
        top_k,
    )

    return [item["zip"] for item in ranked]


def analyze_profile(profile, areas):
    """Compare the original rankings with one feature removed at a time."""
    checked = validate_profile(profile)
    candidates = filter_by_budget(areas, checked["budget_max"])

    baseline = recommend(profile)
    original_zips = [item["zip"] for item in baseline["recommendations"]]

    # Check that our calculation matches the actual recommender.
    if candidates.empty:
        assert original_zips == []
    else:
        calculated_zips = get_ranked_zips(
            candidates,
            checked["vector_features"],
            checked["active_features"],
            checked["top_k"],
        )
        assert calculated_zips == original_zips

    results = []

    for feature in FEATURES:
        if feature not in checked["vector_features"]:
            status = "not_used"
        elif candidates.empty:
            status = "no_candidates"
        else:
            remaining_features = [
                name for name in checked["vector_features"]
                if name != feature
            ]
            remaining_active = [
                name for name in checked["active_features"]
                if name != feature
            ]

            if not remaining_active:
                status = "no_active_features"
            else:
                status = "ok"

        result = {
            "profile": profile["profile_id"],
            "feature": feature,
            "selected": feature in checked["active_features"],
            "status": status,
            "same_order": None,
            "overlap": None,
        }

        if status == "ok":
            changed_zips = get_ranked_zips(
                candidates,
                remaining_features,
                remaining_active,
                checked["top_k"],
            )

            result["same_order"] = original_zips == changed_zips
            result["overlap"] = count_overlap(original_zips, changed_zips)
            result["original_count"] = len(original_zips)

        results.append(result)

    return results


def analyze():
    """Run the comparison for all evaluation profiles."""
    profiles = json.loads(PROFILES_PATH.read_text())
    areas = load_area_features()

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
