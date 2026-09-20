import os

import numpy as np
import pandas as pd

# Census ACS sentinel for suppressed/missing cells (see data_dictionary.md)
SUPPRESSED_VALUE = -666666666

# Columns that are exact duplicates of an underlying ACS column and must be
# re-synced after that column is cleaned, so the sentinel doesn't survive
# under a different name.
DERIVED_ALIASES = {
    "median_rent_usd": "B25064_001E",
    "population": "B01003_001E",
}


def _clean_frame(
    df: pd.DataFrame, aliases: dict[str, str] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Flag and impute both suppression sentinels and plain nulls.

    Two distinct causes of missingness are tracked separately, because they
    mean different things: a sentinel is the Census actively withholding a
    value, a null is a value that was never present in the source at all.

      - `<column>_suppressed` marks rows that held the sentinel
      - `<column>_missing` marks rows that were already NaN

    Both are replaced with the column median, computed after removing the
    sentinel and the nulls so neither can skew it.
    """
    df = df.copy()
    aliases = aliases or {}
    numeric_cols = df.select_dtypes(include="number").columns
    report_rows = []

    for col in numeric_cols:
        sentinel_mask = df[col] == SUPPRESSED_VALUE
        null_mask = df[col].isna()
        n_suppressed = int(sentinel_mask.sum())
        n_null = int(null_mask.sum())
        if n_suppressed == 0 and n_null == 0:
            continue

        if n_suppressed:
            df[f"{col}_suppressed"] = sentinel_mask
        if n_null:
            df[f"{col}_missing"] = null_mask

        df.loc[sentinel_mask, col] = np.nan
        imputed_value = df[col].median()
        df[col] = df[col].fillna(imputed_value)

        report_rows.append(
            {
                "column": col,
                "suppressed_count": n_suppressed,
                "null_count": n_null,
                "strategy": "flag_and_impute_median",
                "imputed_value": imputed_value,
            }
        )

    # Keep derived duplicate columns in sync with their now-cleaned source,
    # otherwise the sentinel would still leak through under the alias name.
    for derived_col, source_col in aliases.items():
        if derived_col in df.columns and source_col in df.columns:
            df[derived_col] = df[source_col]

    leaked = (df[numeric_cols] == SUPPRESSED_VALUE).any().any()
    assert not leaked, "suppression sentinel leaked into cleaned data"
    still_null = df[numeric_cols].isna().any().any()
    assert not still_null, "null survived imputation in cleaned data"

    report = pd.DataFrame(report_rows)
    return df, report


def clean_public_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean the raw ACS public-features frame.

    Returns (cleaned_df, report_df) where report_df has one row per affected
    column describing what was done.
    """
    return _clean_frame(df, aliases=DERIVED_ALIASES)


def clean_area_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean the blended area-features frame the recommender scores on.

    `area_features.csv` carries its own copy of `median_rent_usd` joined from
    the public data, so the sentinel reaches the model through this file even
    though the public file has been cleaned. Issue #7 requires that no
    sentinel reach the model, so this file has to be cleaned too.
    """
    return _clean_frame(df)


def _report(label: str, path: str, raw: pd.DataFrame, report: pd.DataFrame) -> None:
    print(f"\n{label}: loaded {len(raw)} rows from {path}")
    if report.empty:
        print("  No suppressed or missing cells found.")
    else:
        print(report.to_string(index=False))


if __name__ == "__main__":
    public_in = os.path.join("data", "miami_dade_public_features.csv")
    public_out = os.path.join("data", "miami_dade_public_features_clean.csv")
    area_in = os.path.join("data", "area_features.csv")
    area_out = os.path.join("data", "area_features_clean.csv")

    raw_public = pd.read_csv(public_in)
    clean_public, public_report = clean_public_features(raw_public)
    _report("public features", public_in, raw_public, public_report)

    raw_area = pd.read_csv(area_in)
    clean_area, area_report = clean_area_features(raw_area)
    _report("area features", area_in, raw_area, area_report)

    # The two files carry the same median_rent_usd per ZIP, so cleaning them
    # independently must land on the same number. If this trips, the files
    # have drifted and the recommender is scoring on different rent than the
    # public data reports.
    merged = clean_public[["zip", "median_rent_usd"]].merge(
        clean_area[["zip", "median_rent_usd"]], on="zip", suffixes=("_public", "_area")
    )
    mismatched = merged["median_rent_usd_public"] != merged["median_rent_usd_area"]
    assert not mismatched.any(), (
        "median_rent_usd disagrees between cleaned public and area features for "
        f"ZIPs {merged.loc[mismatched, 'zip'].tolist()}"
    )

    clean_public.to_csv(public_out, index=False)
    clean_area.to_csv(area_out, index=False)
    print(f"\nWrote cleaned data to {public_out} and {area_out}")
