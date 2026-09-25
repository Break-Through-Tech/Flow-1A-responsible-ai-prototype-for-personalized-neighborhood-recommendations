"""Feature vector schema for the baseline neighborhood recommender.

Task #5 defines which features are used for similarity, how they are scaled,
and how user preferences map to feature columns.
"""
import pandas as pd

# Task #4 found these features usable; walkable is broken and pet_friendly is constant.
BASE_FEATURES = ["transit", "social", "quiet"]

# Only use this feature when the user chooses co_living.
CONDITIONAL_FEATURES = {
    "co_living": "co_living_friendly",
}

# Only use these values as housing preferences.
VALID_HOUSING_PREFERENCES = {"own_apartment", "co_living"}

# Map each user lifestyle tag to its similarity column.
# walkable and pet_friendly stay recognized inputs, but they are not scored in the baseline
# because Task #4 found their current data unusable.
TAG_TO_COLUMN = {
    "transit": "transit",
    "social": "social",
    "quiet": "quiet",
    "walkable": None,
    "pet_friendly": None,
}

# Budget is a hard filter, not part of the similarity vector. Task #6 should use median_rent_usd 
# to remove ZIPs above the user's budget before calculating similarity.
BUDGET_COLUMN = "median_rent_usd"

# Selected similarity features are already 0-1 scores, so the baseline uses them as-is without 
# additional scaling. (verified against area_features_clean.csv)
SCALING_METHOD = "pre_normalized_0_1"

# Columns used to identify and display recommendations, not for similarity.
ID_COLUMN = "zip"
DISPLAY_COLUMN = "area_name"

def get_similarity_features(tags: list[str], housing_preference: str) -> list[str]:
    """Return the similarity columns to use for a user's preferences. 

    Only tags with usable features are added. Tags with no usable baseline feature
    are skipped. If the user chooses co_living, co_living_friendly is also added, but 
    only once and as a conditional feature.
    """
    # Validate the housing preference is one of the two expected values.
    if housing_preference not in VALID_HOUSING_PREFERENCES:
        raise ValueError(f"Unknown housing preference: {housing_preference}")
    
    features = []

    # Add usable features from the user's lifestyle tags.
    for tag in tags:
        # Catch invalid or misspelled tags.
        if tag not in TAG_TO_COLUMN:
            raise ValueError(f"Unknown lifestyle tag: {tag}")
    
        column = TAG_TO_COLUMN[tag]
        if column is not None and column not in features:
            features.append(column)

    # Add the co-living feature only when the user chooses co_living.
    if housing_preference in CONDITIONAL_FEATURES:
        column = CONDITIONAL_FEATURES[housing_preference]
        if column not in features:
            features.append(column)

    return features

def validate_feature_schema(df: pd.DataFrame) -> None:
    """Check that the dataset has the columns and ranges the schema expects.
    
    Makes sure all required columns are present and that the similarity
    features are numeric values between 0 and 1. Raises a ValueError if
    the data does not match what the baseline recommender expects.
    """
    feature_columns = BASE_FEATURES + list(CONDITIONAL_FEATURES.values())
    required_columns = feature_columns + [BUDGET_COLUMN, ID_COLUMN, DISPLAY_COLUMN]

    # Make sure every column needed by the schema exists.
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    # Check that all similarity features are numeric and between 0 and 1, and that
    # there are no missing values.
    for col in feature_columns:
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise ValueError(f"{col} must be numeric")
        if df[col].isna().any():
            raise ValueError(f"{col} contains missing values")
        if not df[col].between(0, 1).all():
            raise ValueError(f"{col} must contain values between 0 and 1")

    # The budget column must be numeric so Task #6 can apply the hard filter.
    if not pd.api.types.is_numeric_dtype(df[BUDGET_COLUMN]):
        raise ValueError(f"{BUDGET_COLUMN} must be numeric")
    if df[BUDGET_COLUMN].isna().any():
        raise ValueError(f"{BUDGET_COLUMN} contains missing values")

