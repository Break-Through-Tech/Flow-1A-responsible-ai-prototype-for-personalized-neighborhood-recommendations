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


def clean_public_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Remove Census suppression sentinels from a public-features dataframe.

    For every numeric column that contains the suppression sentinel:
      - flag which rows were suppressed in a new `<column>_suppressed` column
      - replace the sentinel with NaN
      - impute the NaN with the column's median (computed after removing the
        sentinel, so the sentinel can't skew it)

    Returns (cleaned_df, report_df) where report_df has one row per affected
    column describing what was done.
    """
    df = df.copy()
    numeric_cols = df.select_dtypes(include="number").columns
    report_rows = []

    for col in numeric_cols:
        mask = df[col] == SUPPRESSED_VALUE
        n_suppressed = int(mask.sum())
        if n_suppressed == 0:
            continue

        df[f"{col}_suppressed"] = mask
        df.loc[mask, col] = np.nan
        imputed_value = df[col].median()
        df[col] = df[col].fillna(imputed_value)

        report_rows.append(
            {
                "column": col,
                "suppressed_count": n_suppressed,
                "strategy": "flag_and_impute_median",
                "imputed_value": imputed_value,
            }
        )

    # Keep derived duplicate columns in sync with their now-cleaned source,
    # otherwise the sentinel would still leak through under the alias name.
    for derived_col, source_col in DERIVED_ALIASES.items():
        if derived_col in df.columns and source_col in df.columns:
            df[derived_col] = df[source_col]

    leaked = (df[numeric_cols] == SUPPRESSED_VALUE).any().any()
    assert not leaked, "suppression sentinel leaked into cleaned data"

    report = pd.DataFrame(report_rows)
    return df, report


if __name__ == "__main__":
    input_path = os.path.join("data", "miami_dade_public_features.csv")
    output_path = os.path.join("data", "miami_dade_public_features_clean.csv")

    raw = pd.read_csv(input_path)
    cleaned, report = clean_public_features(raw)

    print(f"Loaded {len(raw)} rows from {input_path}")
    if report.empty:
        print("No suppressed cells found.")
    else:
        print("Suppressed cells handled per column:")
        print(report.to_string(index=False))

    cleaned.to_csv(output_path, index=False)
    print(f"Wrote cleaned data to {output_path}")
