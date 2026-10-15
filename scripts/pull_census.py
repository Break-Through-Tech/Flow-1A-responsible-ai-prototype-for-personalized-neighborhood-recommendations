"""Pull Census ACS 5-year estimates for the Miami-Dade ZCTAs (Task #11).

Rebuilds `data/miami_dade_public_features.csv` from the Census API with the
same columns, in the same order, as the starter file, so `clean_data.py`,
`eda.py` and the notebook keep working unchanged.

    python scripts/pull_census.py                  # 2024 ACS 5-year (2020-2024)
    python scripts/pull_census.py --year 2022 --out data/raw/acs2022.csv

Needs CENSUS_API_KEY in `.env` (free: https://api.census.gov/data/key_signup.html).

The starter file was built by the CA's reference prototype from
https://api.census.gov/data/2022/acs/acs5 (karlarey/miami-newcomer-explorer,
scripts/download_data.py). Pulling `--year 2022` and diffing against the
starter confirms that.

Only the ACS columns are refreshed. The two Zillow columns are not Census data,
so they are carried over per ZIP from the file being replaced.

`area_features.csv` holds its own copy of `median_rent_usd` and `clean_data.py`
asserts the two agree. Pass `--sync-area-rent` to copy the new rent across;
without it, `clean_data.py` will stop on that assertion after a new pull.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PUBLIC_PATH = DATA_DIR / "miami_dade_public_features.csv"
AREA_PATH = DATA_DIR / "area_features.csv"
ZCTA_PATH = DATA_DIR / "miami_dade_zctas.txt"

DEFAULT_YEAR = 2024
ENDPOINT = "https://api.census.gov/data/{year}/acs/acs5"
ZCTA_GEO = "zip code tabulation area"
CHUNK = 40

# Same variables, in the same order, as the starter file. Labels are the
# Census API's own. B07003_008E is the male subtotal only: it is kept so the
# file's columns do not change, but it is not a total of same-county movers.
ACS_VARIABLES = {
    "B01003_001E": "Total population",
    "B25064_001E": "Median gross rent (dollars)",
    "B25077_001E": "Median value, owner-occupied housing units (dollars)",
    "B07003_001E": "Population 1 year and over (migration universe)",
    "B07003_004E": "Same house 1 year ago",
    "B07003_008E": "Moved within same county, male",
    "B07003_010E": "Moved from different county within same state",
    "B11016_001E": "Total households",
    "B25003_002E": "Owner-occupied housing units",
    "B25003_003E": "Renter-occupied housing units",
}
ZILLOW_COLUMNS = ["zillow_home_value_index", "zillow_rent_index"]
COLUMN_ORDER = (
    ["NAME", *ACS_VARIABLES, "zip", "moved_different_house_pct", "median_rent_usd", "population"]
    + ZILLOW_COLUMNS
)

# ACS annotation values: negative codes that stand in for an estimate. Only
# -666666666 is handled by clean_data.py, so any other one is reported loudly.
ACS_SPECIAL_CODES = {
    -999999999: "too few sample observations",
    -888888888: "not applicable",
    -666666666: "suppressed / could not be computed",
    -555555555: "controlled estimate",
    -333333333: "median falls in open-ended interval",
    -222222222: "too few sample observations for a median",
}
HANDLED_CODE = -666666666

# Plausible-looking values the ACS uses for "this much or more". They pass any
# range check, so they are listed rather than treated as measurements.
TOP_CODES = {"B25077_001E": 2000001}

ANCHOR_ZIPS = {"33127": "Wynwood", "33128": "Downtown", "33130": "Brickell"}


def load_api_key() -> str:
    """CENSUS_API_KEY from the environment, falling back to the repo's .env."""
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    env_path = ROOT / ".env"
    if not key and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "CENSUS_API_KEY":
                key = value.strip().strip('"').strip("'")
    if not key or key == "your_census_api_key_here":
        raise SystemExit(
            "CENSUS_API_KEY is not set. Copy .env.example to .env and add a key from "
            "https://api.census.gov/data/key_signup.html"
        )
    return key


def load_zctas(path: Path = ZCTA_PATH) -> list[str]:
    zctas = [z.strip() for z in path.read_text(encoding="utf-8").splitlines() if z.strip()]
    return list(dict.fromkeys(zctas))


def fetch_chunk(year: int, zctas: list[str], key: str) -> list[list[str]]:
    params = {
        "get": ",".join(["NAME", *ACS_VARIABLES]),
        "for": f"{ZCTA_GEO}:{','.join(zctas)}",
        "key": key,
    }
    # ZCTAs are not nested under state or county: adding `in=` makes the API
    # reject the request as an unsupported hierarchy.
    resp = requests.get(ENDPOINT.format(year=year), params=params, timeout=120, allow_redirects=False)
    if resp.is_redirect:
        raise SystemExit(f"Census API redirected to {resp.headers.get('Location')}: check the API key")
    if resp.status_code == 204 or not resp.text.strip():
        return []  # none of these ZIPs is a ZCTA
    if resp.status_code != 200:
        # Never echo resp.url: it carries the key.
        raise SystemExit(f"Census API returned HTTP {resp.status_code} for {year}: {resp.text[:300]}")
    try:
        return resp.json()
    except ValueError:
        raise SystemExit(f"Census API did not return JSON for {year}: {resp.text[:300]}")


def fetch_acs(year: int, zctas: list[str], key: str) -> pd.DataFrame:
    header, rows = None, []
    for i in range(0, len(zctas), CHUNK):
        table = fetch_chunk(year, zctas[i:i + CHUNK], key)
        if table:
            header = header or table[0]
            rows.extend(table[1:])
    if header is None:
        raise SystemExit("Census API returned no rows: check the ZIP list and the year")
    return pd.DataFrame(rows, columns=header)


def build_public_features(raw: pd.DataFrame, previous: pd.DataFrame | None) -> pd.DataFrame:
    """Shape an API response into the starter file's columns."""
    df = raw.rename(columns={ZCTA_GEO: "zip"}).copy()
    df["zip"] = df["zip"].astype(str).str.zfill(5)
    for col in ACS_VARIABLES:
        df[col] = pd.to_numeric(df[col], errors="raise").astype("int64")

    # Same formula as the starter. Blank when the migration universe is 0 or
    # either input is an annotation code.
    total, same = df["B07003_001E"], df["B07003_004E"]
    valid = (total > 0) & (same >= 0)
    df["moved_different_house_pct"] = ((total - same) / total).clip(0, 1).where(valid)
    df["median_rent_usd"] = df["B25064_001E"]
    df["population"] = df["B01003_001E"]

    if previous is not None and set(ZILLOW_COLUMNS) <= set(previous.columns):
        carried = previous[["zip", *ZILLOW_COLUMNS]]
        df = df.merge(carried, on="zip", how="left")
    else:
        for col in ZILLOW_COLUMNS:
            df[col] = pd.NA

    # Keep the replaced file's row order so a diff shows changed values, not
    # reshuffled rows. ZIPs it did not have go at the end.
    order = list(previous["zip"]) if previous is not None else []
    rank = {z: i for i, z in enumerate(order)}
    df["_order"] = df["zip"].map(lambda z: rank.get(z, len(order)))
    df = df.sort_values(["_order", "zip"]).drop(columns="_order")
    return df[COLUMN_ORDER].reset_index(drop=True)


def special_value_report(df: pd.DataFrame) -> list[str]:
    lines = []
    for col in ACS_VARIABLES:
        for code, meaning in ACS_SPECIAL_CODES.items():
            zips = df.loc[df[col] == code, "zip"].tolist()
            if zips:
                note = "" if code == HANDLED_CODE else "  NOT HANDLED by clean_data.py"
                lines.append(f"{col} = {code} ({meaning}): {zips}{note}")
        top = TOP_CODES.get(col)
        if top is not None:
            zips = df.loc[df[col] == top, "zip"].tolist()
            if zips:
                lines.append(f"{col} = {top} (top-coded, true value is higher): {zips}")
    return lines


def comparison_report(new: pd.DataFrame, old: pd.DataFrame) -> list[str]:
    """Anchor ZIPs side by side, then a summary across every ZIP in both files."""
    cols = ["B01003_001E", "B25064_001E", "B25077_001E", "B25003_003E", "moved_different_house_pct"]
    both = old.merge(new, on="zip", suffixes=("_old", "_new"))
    lines = ["Anchor ZIPs (old -> new):"]
    for z, name in ANCHOR_ZIPS.items():
        row = both[both["zip"] == z]
        if row.empty:
            lines.append(f"  {z} {name}: missing from one of the files")
            continue
        row = row.iloc[0]
        lines.append(f"  {z} {name}")
        for c in cols:
            o, n = row[f"{c}_old"], row[f"{c}_new"]
            if c == "moved_different_house_pct":
                lines.append(f"    {c:<26} {o:>10.3f} -> {n:>10.3f}")
            else:
                pct = f"{(n - o) / o:+.1%}" if o > 0 and n >= 0 else ""
                lines.append(f"    {c:<26} {o:>10,.0f} -> {n:>10,.0f}  {pct}")

    measured = both[(both["B25064_001E_old"] > 0) & (both["B25064_001E_new"] > 0)]
    change = (measured["B25064_001E_new"] - measured["B25064_001E_old"]) / measured["B25064_001E_old"]
    lines += [
        "",
        f"ZIPs in old file: {len(old)}, new file: {len(new)}, both: {len(both)}",
        f"Only in old: {sorted(set(old['zip']) - set(new['zip']))}",
        f"Only in new: {sorted(set(new['zip']) - set(old['zip']))}",
        f"Median gross rent, ZIPs measured in both ({len(measured)}): "
        f"median {measured['B25064_001E_old'].median():,.0f} -> {measured['B25064_001E_new'].median():,.0f}, "
        f"median change {change.median():+.1%}, range {change.min():+.1%} to {change.max():+.1%}",
        f"Suppressed rent (-666666666): {int((old['B25064_001E'] == HANDLED_CODE).sum())} -> "
        f"{int((new['B25064_001E'] == HANDLED_CODE).sum())} ZIPs",
    ]
    return lines


def area_with_new_rent(public: pd.DataFrame, area_path: Path) -> tuple[pd.DataFrame, int]:
    """area_features with median_rent_usd copied from the new pull, and how many ZIPs changed.

    Every column is read as text so the others are written back untouched.
    """
    area = pd.read_csv(area_path, dtype=str, keep_default_na=False)
    rent = public.set_index("zip")["median_rent_usd"]
    missing = sorted(set(area["zip"]) - set(rent.index))
    if missing:
        raise SystemExit(f"{area_path} has ZIPs the new pull does not: {missing}")
    new_rent = area["zip"].map(rent).astype("int64").astype(str)
    changed = int((area["median_rent_usd"] != new_rent).sum())
    area["median_rent_usd"] = new_rent
    return area, changed


def main() -> int:
    ap = argparse.ArgumentParser(description="Pull Census ACS 5-year estimates for Miami-Dade ZCTAs")
    ap.add_argument("--year", type=int, default=DEFAULT_YEAR, help="ACS 5-year vintage (end year)")
    ap.add_argument("--out", type=Path, default=PUBLIC_PATH)
    ap.add_argument("--compare", type=Path, default=PUBLIC_PATH,
                    help="file to compare against and carry the Zillow columns from")
    ap.add_argument("--sync-area-rent", action="store_true",
                    help="also copy median_rent_usd into data/area_features.csv")
    args = ap.parse_args()

    key = load_api_key()
    zctas = load_zctas()
    # Zillow columns are read as text so they are carried over exactly, not re-rounded.
    text_cols = {"zip": str, **{c: str for c in ZILLOW_COLUMNS}}
    previous = pd.read_csv(args.compare, dtype=text_cols) if args.compare.exists() else None

    print(f"Pulling ACS 5-year {args.year - 4}-{args.year} for {len(zctas)} ZCTAs "
          f"from {ENDPOINT.format(year=args.year)} on {date.today().isoformat()}")
    raw = fetch_acs(args.year, zctas, key)
    df = build_public_features(raw, previous)

    returned = set(df["zip"])
    not_returned = [z for z in zctas if z not in returned]
    if not_returned:
        # PO-box-only ZIPs have no ZCTA, so a few gaps are expected. A ZIP the
        # previous file had is not.
        had = set(previous["zip"]) if previous is not None else set()
        lost = [z for z in not_returned if z in had]
        print(f"\nNo ZCTA row for {not_returned} (PO-box-only ZIPs have none)")
        if lost:
            print(f"WARNING: {lost} were in {args.compare} but are missing from this pull")

    print("\n--- special values ---")
    print("\n".join(special_value_report(df)) or "none")
    if previous is not None:
        print(f"\n--- comparison with {args.compare} ---")
        print("\n".join(comparison_report(df, previous)))

    # Build the area update before writing anything, so a failure cannot leave
    # one file replaced and the other not.
    area = area_with_new_rent(df, AREA_PATH) if args.sync_area_rent else None

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"\nwrote {args.out} ({len(df)} ZIPs)")
    if area is not None:
        area[0].to_csv(AREA_PATH, index=False)
        print(f"updated median_rent_usd in {AREA_PATH} ({area[1]} ZIPs changed)")

    if any("NOT HANDLED" in line for line in special_value_report(df)):
        print("\nWARNING: annotation codes other than -666666666 are present; "
              "clean_data.py will not catch them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
