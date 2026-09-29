import math  
import sys  
from pathlib import Path  

import numpy as np  
import pandas as pd  

_ROOT = Path(__file__).resolve().parents[1]  # project folder one level up
if str(_ROOT) not in sys.path:  # if Python cannot see the project yet
    sys.path.insert(0, str(_ROOT))  # add the project folder so imports work

from scripts.feature_schema import (  # use Task #5 instead of copying it
    BUDGET_COLUMN,  # rent column used for the hard budget filter
    CONDITIONAL_FEATURES,  # extra features that only apply to some housing types
    DISPLAY_COLUMN,  # neighborhood name shown to the user
    ID_COLUMN,  # ZIP code column
    TAG_TO_COLUMN,  # maps a lifestyle tag to a data column
    get_active_features,  # which features the user actually selected
    get_vector_features,  # full list of features used in cosine similarity
    validate_feature_schema,  # checks that the ZIP table looks right
)

_DATA_PATH = _ROOT / "data" / "area_features_clean.csv"  # cleaned ZIP data file
_REQUIRED_KEYS = ("household", "housing_preference", "budget_max", "tags")  
VALID_HOUSEHOLDS = {"alone", "with_co_leaser"}  
DEFAULT_TOP_K = 5  


def load_area_features(path: str | Path | None = None) -> pd.DataFrame:
    """Load cleaned area features and run Task #5 schema validation.

    ZIP codes stay strings. The source CSV is not written.
    """
    df = pd.read_csv(path or _DATA_PATH, dtype={ID_COLUMN: str})  # read CSV; keep ZIP as text
    validate_feature_schema(df)  # make sure the columns and values match Task #5
    return df  


def _unscored_tags(tags: list[str], housing_preference: str) -> list[str]:
    """Recognized tags that do not set a scored column for this profile.

    The co_living tag is left out when that housing preference already turns
    on co_living_friendly, so the same choice is not both scored and unscored.
    """
    unscored = []  # start with an empty list
    for tag in tags:  
        if TAG_TO_COLUMN[tag] is not None:  
            continue  # skip it; it is scored
        if tag in CONDITIONAL_FEATURES and housing_preference == tag:  # co_living is already scored by housing type
            continue  # skip it so we do not list it as unscored
        unscored.append(tag)  # keep tags that are known but not scored
    return unscored  


def validate_profile(profile: dict, top_k: int = DEFAULT_TOP_K) -> dict:
    """Validate a user profile and resolve the Task #5 feature lists.

    Duplicate tags collapse to one. Unknown tags and housing preferences
    raise through Task #5. No scored preference raises here: cosine
    similarity is undefined for a zero user vector.
    """
    if not isinstance(profile, dict):  # profile must be a dictionary
        raise ValueError("profile must be a dict")  # stop if it is not

    missing = [key for key in _REQUIRED_KEYS if key not in profile]  # find missing required fields
    if missing:  
        raise ValueError(f"Profile missing keys: {missing}")  # stop and name the missing fields

    household = profile["household"]  # who the user lives with
    if household not in VALID_HOUSEHOLDS:  # only two household values are allowed
        raise ValueError(f"Unknown household: {household}")  # stop if the value is unknown

    budget_max = profile["budget_max"]  # max rent the user will pay
    if (  
        isinstance(budget_max, bool)  # True/False should not count as a number
        or not isinstance(budget_max, (int, float))  # budget must be a number
        or not math.isfinite(budget_max)  # reject NaN and infinity
        or budget_max <= 0  # budget must be greater than 0
    ):
        raise ValueError("budget_max must be a finite number > 0")  

    tags = profile["tags"]  # lifestyle tags from the user
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):  
        raise ValueError("tags must be a list of strings")  
    tags = list(dict.fromkeys(tags))  

    housing_preference = profile["housing_preference"]  # own apartment or co-living
    vector_features = get_vector_features(housing_preference)  # full cosine vector from Task #5
    active_features = get_active_features(tags, housing_preference)  # scored tags the user picked
    outside = [feature for feature in active_features if feature not in vector_features]  # active features that do not belong
    if outside:  # Task #5 should never return this
        raise ValueError(f"Active features not in the Task #5 vector: {outside}")  

    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:  # top_k must be a whole number of 1 or more
        raise ValueError("top_k must be an integer >= 1")  # stop if top_k is bad

    if not active_features:  # no scored preference means a zero user vector
        raise ValueError(  # cosine similarity cannot run on a zero vector
            "No scored preferences: cosine similarity is undefined for a zero "
            f"user vector. Unscored tags: {_unscored_tags(tags, housing_preference) or 'none'}."
        )

    return {  # give back the cleaned profile plus Task #5 feature lists
        "household": household,  # checked household
        "housing_preference": housing_preference,  # checked housing type
        "budget_max": float(budget_max),  # budget as a float
        "tags": tags,  # tags with duplicates removed
        "vector_features": vector_features,  # full cosine dimensions
        "active_features": active_features,  # scored selected features
        "unscored_tags": _unscored_tags(tags, housing_preference),  # known tags we do not score
        "top_k": top_k,  # how many results to return
    }


def filter_by_budget(df: pd.DataFrame, budget_max: float) -> pd.DataFrame:
    """Keep ZIPs with median rent <= budget_max. Rent is not a similarity feature."""
    return df.loc[df[BUDGET_COLUMN] <= budget_max].reset_index(drop=True)  # keep only affordable ZIPs


def build_user_vector(vector_features: list[str], active_features: list[str]) -> np.ndarray:
    """1 on active preferences, 0 on the other fixed vector dimensions."""
    active = set(active_features)  # faster lookup for selected features
    return np.array(  # make the user vector
        [1.0 if feature in active else 0.0 for feature in vector_features],  # 1 if selected, else 0
        dtype=float,  # store as floats
    )


def build_area_matrix(candidates: pd.DataFrame, vector_features: list[str]) -> np.ndarray:
    """Candidate rows in the same order as the user vector."""
    return candidates.loc[:, vector_features].to_numpy(dtype=float)  # ZIP feature values in the same order


# Baseline limitation:
# Cosine similarity uses the full fixed-dimensional candidate vector.
# Therefore, features the user did not select can still affect the
# candidate vector's norm and influence the final similarity score.
# This matches the current reference baseline and may be revisited later.
def cosine_similarities(user_vector: np.ndarray, area_matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity between the user vector and each candidate row."""
    user_norm = float(np.linalg.norm(user_vector))  # length of the user vector
    if user_norm == 0.0:  # a zero user vector cannot be compared
        raise ValueError( 
            "Cosine similarity is undefined for a zero user vector "
            "(no scored preferences)."
        )

    dots = area_matrix @ user_vector  # one dot product per ZIP
    norms = np.linalg.norm(area_matrix, axis=1)  # length of each ZIP vector
    scores = np.zeros(len(area_matrix), dtype=float)  # start every ZIP at 0
    nonzero = norms > 0.0  # ZIPs that have a real vector length
    scores[nonzero] = dots[nonzero] / (norms[nonzero] * user_norm)  # cosine = dot / (lengths)
    return scores  # similarity for each ZIP


def rank_areas(
    candidates: pd.DataFrame,
    similarities: np.ndarray,
    vector_features: list[str],
    active_features: list[str],
    top_k: int,
) -> list[dict]:
    """Highest cosine first. Exact ties break by ZIP ascending."""
    if len(similarities) != len(candidates):  # one score is required for every ZIP
        raise ValueError( 
            f"Expected {len(candidates)} similarities, got {len(similarities)}"
        )

    zips = candidates[ID_COLUMN].astype(str).tolist()  # ZIP codes as text
    order = sorted(range(len(candidates)), key=lambda i: (-float(similarities[i]), zips[i]))  # high score first; ZIP breaks ties

    ranked = []  # list of top matches
    for rank, i in enumerate(order[:top_k], start=1):  # take the first top_k rows
        row = candidates.iloc[i]  # that ZIP's data
        feature_scores = {feature: float(row[feature]) for feature in vector_features}  # all vector scores for this ZIP
        area_name = row[DISPLAY_COLUMN]  # neighborhood name
        ranked.append(  # add this match
            {
                "rank": rank,  # 1 is the best match
                "zip": zips[i],  # ZIP code
                "area_name": "" if pd.isna(area_name) else str(area_name),  # name, or blank if missing
                "median_rent_usd": float(row[BUDGET_COLUMN]),  # rent used in the budget check
                "similarity": float(similarities[i]),  # cosine score
                "matched_features": [  # only scored selected features
                    {"feature": feature, "area_score": feature_scores[feature]}  # feature name and ZIP score
                    for feature in active_features  # one item per active feature
                ],
                "feature_scores": feature_scores,  # full vector scores for later explanation
            }
        )
    return ranked  # top matches in rank order


def recommend(
    profile: dict,
    top_k: int = DEFAULT_TOP_K,
    data_path: str | Path | None = None,
) -> dict:
    """Return up to top_k affordable ZIP matches for one user profile.

    Household is checked and echoed. It is not a similarity feature.
    Budget removes unaffordable ZIPs before scoring. Vector dimensions come
    from get_vector_features(); the 1/0 weights come from get_active_features().
    """
    checked = validate_profile(profile, top_k)  # check the user input
    candidates = filter_by_budget(load_area_features(data_path), checked["budget_max"])  # load data, then drop expensive ZIPs
    user_vector = build_user_vector(checked["vector_features"], checked["active_features"])  # make the 1/0 user vector

    result = {  # start the output
        "household": checked["household"],  # echo household
        "housing_preference": checked["housing_preference"],  # echo housing type
        "budget_max": checked["budget_max"],  # echo budget
        "tags": checked["tags"],  # echo tags
        "vector_features": checked["vector_features"],  # cosine dimensions
        "active_features": checked["active_features"],  # selected scored features
        "unscored_tags": checked["unscored_tags"],  # known tags we did not score
        "user_vector": {  # user weights in a readable form
            feature: float(weight)  # feature name and 1 or 0
            for feature, weight in zip(checked["vector_features"], user_vector)  # pair each feature with its weight
        },
        "candidate_count": int(len(candidates)),  # how many ZIPs passed the budget filter
        "recommendations": [],  # empty until we rank, or if none are affordable
        "status": "ok",  # default status
    }
    if candidates.empty:  # no ZIP is cheap enough
        result["status"] = "no_areas_within_budget"  # say why we have no matches
        return result  # return early with an empty list

    scores = cosine_similarities(  # score every affordable ZIP
        user_vector, build_area_matrix(candidates, checked["vector_features"])  # compare user vector to ZIP vectors
    )
    result["recommendations"] = rank_areas(  # sort and keep the top matches
        candidates,  # affordable ZIPs
        scores,  # their cosine scores
        checked["vector_features"],  # full vector names
        checked["active_features"],  # selected features for match info
        checked["top_k"],  # how many to keep
    )
    return result  # return the full recommendation payload


def _self_check() -> None:
    base = {  # a simple valid profile used by several checks
        "household": "alone",  # lives alone
        "housing_preference": "own_apartment",  # wants their own apartment
        "budget_max": 2500,  # $2500 rent cap
        "tags": ["transit"],  # cares about transit
    }

    def _raises(profile, **kwargs):  # helper that expects recommend() to fail
        try:  # try the bad input
            recommend(profile, **kwargs)  # this should raise
        except ValueError:  # a ValueError is the expected result
            return  # pass this check
        raise AssertionError(f"expected ValueError for {profile} {kwargs}")  # fail if it did not raise

    _raises({**base, "tags": ["trasnit"]})  # misspelled tag should fail
    _raises({**base, "housing_preference": "house"})  # unknown housing type should fail
    _raises({**base, "budget_max": 0})  # zero budget should fail
    _raises({**base, "budget_max": -5})  # negative budget should fail
    _raises({**base, "household": "family"})  # unknown household should fail
    _raises({**base, "tags": ["walkable"]})  # only unscored tags should fail
    _raises({**base, "tags": ["pet_friendly", "walkable"]})  # still no scored tag
    _raises(base, top_k=0)  # top_k of 0 should fail

    empty = recommend({**base, "budget_max": 1})  # $1 budget should match no ZIP
    assert empty["status"] == "no_areas_within_budget"  # check the empty-budget status
    assert empty["recommendations"] == []  # no rows should be returned

    areas = load_area_features()  # load the real cleaned table
    for budget in sorted(areas[BUDGET_COLUMN].unique()):  # try each unique rent from low to high
        n = int((areas[BUDGET_COLUMN] <= budget).sum())  # how many ZIPs fit this rent
        if 0 < n < DEFAULT_TOP_K:  # we want fewer matches than top_k
            few = recommend({**base, "budget_max": float(budget)})  # run recommend at that rent
            assert len(few["recommendations"]) == n  # return all remaining ZIPs
            assert all(row["median_rent_usd"] <= budget for row in few["recommendations"])  # all must be affordable
            break  # one such budget is enough
    else:  # no budget had fewer matches than top_k
        raise AssertionError("expected a budget with fewer matches than top_k")  # that should not happen

    dup = recommend({**base, "tags": ["transit", "walkable", "transit"]})  # duplicate transit plus unscored walkable
    assert dup["vector_features"] == ["transit", "social", "quiet"]  # own-apartment vector stays 3-D
    assert dup["active_features"] == ["transit"]  # only transit is scored
    assert dup["user_vector"] == {"transit": 1.0, "social": 0.0, "quiet": 0.0}  # 1 on transit, 0 on the rest
    assert dup["unscored_tags"] == ["walkable"]  # walkable is known but not scored
    assert [row["feature"] for row in dup["recommendations"][0]["matched_features"]] == ["transit"]  # only transit is a match reason
    assert all(row["median_rent_usd"] <= 2500 for row in dup["recommendations"])  # all rents stay under budget
    again = recommend({**base, "tags": ["transit", "walkable", "transit"]})  # run the same profile again
    assert [row["zip"] for row in dup["recommendations"]] == [  # ranking must stay the same
        row["zip"] for row in again["recommendations"]  # same ZIP order on the second run
    ]

    coliving = recommend(  # official-style co-living profile
        {
            "household": "alone",  # lives alone
            "housing_preference": "co_living",  # wants co-living
            "budget_max": 1800,  # $1800 rent cap
            "tags": ["co_living", "transit"],  # co-living tag plus transit
        }
    )
    assert coliving["vector_features"] == ["transit", "social", "quiet", "co_living_friendly"]  # extra co-living dimension
    assert coliving["vector_features"].count("co_living_friendly") == 1  # add that feature only once
    assert coliving["active_features"] == ["transit", "co_living_friendly"]  # both are scored
    assert coliving["unscored_tags"] == []  # co_living tag is not listed as unscored
    assert all(row["median_rent_usd"] <= 1800 for row in coliving["recommendations"])  # all rents stay under $1800

    quiet = recommend(  # official-style quiet plus pets profile
        {
            "household": "with_co_leaser",  # has a co-leaser
            "housing_preference": "own_apartment",  # wants their own apartment
            "budget_max": 2200,  # $2200 rent cap
            "tags": ["quiet", "pet_friendly"],  # quiet plus an unscored tag
        }
    )
    assert quiet["active_features"] == ["quiet"]  # only quiet is scored
    assert quiet["unscored_tags"] == ["pet_friendly"]  # pets stay recognized but unscored
    assert [row["feature"] for row in quiet["recommendations"][0]["matched_features"]] == ["quiet"]  # pets are not a match reason

    print("self-check ok")  


if __name__ == "__main__":  
    _self_check()  
