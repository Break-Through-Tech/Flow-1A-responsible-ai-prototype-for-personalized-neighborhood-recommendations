"""Reusable EDA checks and chart builders for Task #4.

Each check is independently testable and callable from the notebook or a plain
Python shell, covers inspection, summary stats, missingness, distributions,
correlation/redundancy, and the anchor-ZIP-specific checks Task #4 asks for.

The loader pins `zip` to str at read time so a leading-zero ZIP or an
int/str mismatch can never silently break a join or a set comparison.
The notebook's Task #2/#3 cells predate this module and read the same CSVs
with plain read_csv, so their `zip` is int64. The two halves never join to
each other, but any future merge across that line has to cast first.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure

from scripts.clean_data import SUPPRESSED_VALUE

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
FIGURES_DIR = ROOT / "notebooks" / "figures"

ANCHOR_ZIPS = {"33127": "Wynwood", "33128": "Downtown", "33130": "Brickell"}

# ACS top-codes owner-occupied home value at $2,000,000 and encodes it as
# 2000001. Unlike the suppression sentinel this is a plausible-looking number,
# so it passes every range check and silently caps the top of the
# distribution. Pass it to find_suppressed_cells() as the sentinel to locate.
TOP_CODED_VALUE = 2000001

# Validated categorical palette (see dataviz skill, references/palette.md).
# Fixed slot order is the CVD-safety mechanism, never cycled or reassigned.
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # blue, orange, aqua, yellow
SEQUENTIAL_BLUE = "#2a78d6"
DIVERGING_BLUE, DIVERGING_GRAY, DIVERGING_RED = "#184f95", "#f0efec", "#e34948"
INK_PRIMARY, INK_SECONDARY, INK_MUTED, GRIDLINE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
CHART_SURFACE = "#fcfcfb"


@dataclass
class DataBundle:
    area_features: pd.DataFrame
    area_options: pd.DataFrame
    crowd_text: pd.DataFrame
    public_features: pd.DataFrame


def load_data(data_dir: Path | None = None) -> DataBundle:
    """Load the four starter CSVs with `zip` pinned to str across all of them."""
    base = data_dir or DATA_DIR
    return DataBundle(
        area_features=pd.read_csv(base / "area_features.csv", dtype={"zip": str}),
        area_options=pd.read_csv(base / "area_options.csv", dtype={"zip": str}),
        crowd_text=pd.read_csv(base / "crowd_text_snippets.csv", dtype={"zip": str}),
        public_features=pd.read_csv(
            base / "miami_dade_public_features.csv", dtype={"zip": str}
        ),
    )


def describe_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Standard describe() table (count/mean/std/min/quartiles/max), transposed to one row per column.

    Column order matches df, not alphabetical: easier to scan against the
    data dictionary while reading top to bottom.
    """
    numeric = df.select_dtypes(include="number")
    return numeric.describe().T.reindex(numeric.columns)


def missingness_report(df: pd.DataFrame) -> pd.DataFrame:
    """Per-column dtype, missing count/pct, and unique-value count.

    Genuine NaNs only. The Census suppression sentinel (-666666666) is a
    valid-looking int, not a NaN, so it never shows up here; see
    find_suppressed_cells() for that check instead.
    """
    n = len(df)
    rows = [
        {
            "column": col,
            "dtype": str(df[col].dtype),
            "n_missing": int(df[col].isna().sum()),
            "pct_missing": round(100 * df[col].isna().mean(), 1),
            "n_unique": int(df[col].nunique(dropna=True)),
        }
        for col in df.columns
    ]
    return pd.DataFrame(rows).set_index("column").loc[list(df.columns)].reset_index()


def categorical_summary(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Value counts for a set of categorical/text columns, stacked into one long table."""
    rows = []
    for col in columns:
        if col not in df.columns:
            continue
        counts = df[col].value_counts(dropna=False)
        for value, count in counts.items():
            rows.append(
                {
                    "column": col,
                    "value": value,
                    "count": int(count),
                    "pct": round(100 * count / len(df), 1),
                }
            )
    return pd.DataFrame(rows)


def find_suppressed_cells(
    df: pd.DataFrame, sentinel: int = SUPPRESSED_VALUE
) -> pd.DataFrame:
    """Which numeric columns still carry the raw Census sentinel, and in which ZIPs.

    Unlike scripts/clean_data.py (which only ever runs against
    miami_dade_public_features.csv), this takes any DataFrame, so it can
    also catch the sentinel surviving in a file clean_data.py never touches,
    such as area_features.csv.
    """
    numeric_cols = df.select_dtypes(include="number").columns
    rows = []
    for col in numeric_cols:
        mask = df[col] == sentinel
        if not mask.any():
            continue
        zips = df.loc[mask, "zip"].tolist() if "zip" in df.columns else []
        rows.append({"column": col, "suppressed_count": int(mask.sum()), "zips": zips})
    return pd.DataFrame(rows, columns=["column", "suppressed_count", "zips"])


def constant_columns(df: pd.DataFrame, tol: float = 1e-9) -> list[str]:
    """Numeric columns with ~zero variance, dead weight in any similarity feature set."""
    numeric = df.select_dtypes(include="number")
    return [col for col in numeric.columns if numeric[col].std(skipna=True) <= tol]


def near_constant_columns(df: pd.DataFrame, tol: float = 1e-3) -> pd.DataFrame:
    """Numeric columns whose middle 90% spans less than `tol`, degenerate in practice.

    Uses the 5th-95th percentile spread rather than std, because std is the
    wrong instrument here: a column can be constant across the bulk of its
    rows and still post a healthy std off a handful of outliers. `walkable`
    is exactly that shape (std 0.19, but 77 of 80 ZIPs sit within 4e-06 of
    each other), so constant_columns()'s std test lets it through.
    """
    numeric = df.select_dtypes(include="number")
    rows = []
    for col in numeric.columns:
        values = numeric[col].dropna()
        if values.empty:
            continue
        spread = float(values.quantile(0.95) - values.quantile(0.05))
        if spread > tol:
            continue
        dominant_share = float(values.round(6).value_counts(normalize=True).iloc[0])
        rows.append(
            {
                "column": col,
                "p5_p95_spread": spread,
                "full_range": float(values.max() - values.min()),
                "dominant_value_share": round(dominant_share, 3),
            }
        )
    return pd.DataFrame(rows, columns=["column", "p5_p95_spread", "full_range", "dominant_value_share"])


def exact_duplicate_columns(df: pd.DataFrame) -> list[tuple[str, str]]:
    """Column pairs that are byte-identical, not merely correlated."""
    cols = list(df.columns)
    return [
        (a, b)
        for i, a in enumerate(cols)
        for b in cols[i + 1 :]
        if df[a].equals(df[b])
    ]


def correlated_pairs(df: pd.DataFrame, threshold: float = 0.7) -> pd.DataFrame:
    """Numeric column pairs at or above |r| >= threshold.

    Drops constant columns first: pandas' .corr() returns NaN for them, and
    silently dropping NaN correlations would hide a "no signal at all"
    column behind a "not correlated" report row.
    """
    numeric = df.select_dtypes(include="number").drop(
        columns=constant_columns(df), errors="ignore"
    )
    if numeric.shape[1] < 2:
        return pd.DataFrame(columns=["col_a", "col_b", "r"])

    corr = numeric.corr()
    cols = list(corr.columns)
    rows = [
        {"col_a": a, "col_b": b, "r": round(float(corr.loc[a, b]), 3)}
        for i, a in enumerate(cols)
        for b in cols[i + 1 :]
        if pd.notna(corr.loc[a, b]) and abs(corr.loc[a, b]) >= threshold
    ]
    if not rows:
        return pd.DataFrame(columns=["col_a", "col_b", "r"])
    return pd.DataFrame(rows).sort_values("r", key=lambda s: s.abs(), ascending=False).reset_index(drop=True)


def anchor_zip_profile(
    df: pd.DataFrame, columns: list[str], anchors: dict[str, str] = ANCHOR_ZIPS
) -> pd.DataFrame:
    """Side-by-side view of the anchor ZIPs on the given columns, labeled by neighborhood name."""
    present = [z for z in anchors if z in set(df["zip"])]
    subset = df[df["zip"].isin(present)].copy()
    subset["area_label"] = subset["zip"].map(anchors)
    ordered_cols = [c for c in ["zip", "area_label", *columns] if c in subset.columns]
    return subset[ordered_cols].reset_index(drop=True)


def theme_totals(crowd_text: pd.DataFrame) -> pd.DataFrame:
    """Snippet count per theme, across all ZIPs, flags a thin or lopsided NLP corpus."""
    return (
        crowd_text.groupby("theme")
        .size()
        .rename("snippet_count")
        .reset_index()
        .sort_values("snippet_count", ascending=False)
        .reset_index(drop=True)
    )


def anchor_theme_coverage(
    crowd_text: pd.DataFrame, anchors: dict[str, str] = ANCHOR_ZIPS
) -> pd.DataFrame:
    """Which themes each anchor ZIP actually has a snippet for."""
    by_zip = (
        crowd_text[crowd_text["zip"].isin(anchors)]
        .groupby(["zip", "theme"])
        .size()
        .rename("snippet_count")
        .reset_index()
    )
    by_zip["area_label"] = by_zip["zip"].map(anchors)
    return by_zip[["zip", "area_label", "theme", "snippet_count"]]


def option_combo_coverage(
    area_options: pd.DataFrame,
    valid_combos: list[tuple[str, str]],
    anchors: dict[str, str] = ANCHOR_ZIPS,
) -> pd.DataFrame:
    """For each anchor ZIP, which household x housing_preference combos are missing from area_options.csv."""
    rows = []
    for zip_code, label in anchors.items():
        present = set(
            map(
                tuple,
                area_options.loc[
                    area_options["zip"] == zip_code, ["household", "housing_preference"]
                ].values,
            )
        )
        for household, housing_preference in valid_combos:
            rows.append(
                {
                    "zip": zip_code,
                    "area_label": label,
                    "household": household,
                    "housing_preference": housing_preference,
                    "present": (household, housing_preference) in present,
                }
            )
    return pd.DataFrame(rows)


def _new_figure(figsize: tuple[float, float]) -> tuple[Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=figsize, facecolor=CHART_SURFACE)
    ax.set_facecolor(CHART_SURFACE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(GRIDLINE)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    return fig, ax


def save_fig(fig: Figure, name: str, out_dir: Path | None = None) -> Path:
    """Save a figure as PNG under notebooks/figures/, creating the dir if needed."""
    base = out_dir or FIGURES_DIR
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{name}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    return path


def plot_numeric_distributions(
    df: pd.DataFrame, columns: list[str], title: str, ncols: int = 4
) -> Figure:
    """Small-multiples histogram grid, one panel per numeric column, same sequential hue throughout.

    A general-purpose distributions view (every column, not just rent), so a
    teammate scanning this can see each feature's range and shape before
    deciding how to scale or filter on it.
    """
    nrows = -(-len(columns) // ncols)  # ceil division
    fig, axes = plt.subplots(
        nrows, ncols, figsize=(3.2 * ncols, 2.6 * nrows), facecolor=CHART_SURFACE
    )
    axes = axes.flatten() if len(columns) > 1 else [axes]
    for ax, col in zip(axes, columns):
        ax.set_facecolor(CHART_SURFACE)
        ax.hist(df[col].dropna(), bins=12, color=SEQUENTIAL_BLUE, alpha=0.6, edgecolor=DIVERGING_BLUE)
        ax.set_title(col, color=INK_PRIMARY, fontsize=9)
        ax.tick_params(colors=INK_MUTED, labelsize=7)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color(GRIDLINE)
    for ax in axes[len(columns):]:
        ax.axis("off")
    fig.suptitle(title, color=INK_PRIMARY, fontsize=13, y=1.02)
    fig.tight_layout()
    return fig


def plot_correlation_heatmap(
    df: pd.DataFrame, title: str, annotate: bool = True
) -> Figure:
    """Diverging correlation matrix, a matrix of r-values is a polarity job (-1..0..+1), not a magnitude one."""
    numeric = df.select_dtypes(include="number").drop(
        columns=constant_columns(df), errors="ignore"
    )
    corr = numeric.corr()
    cmap = LinearSegmentedColormap.from_list(
        "diverging", [DIVERGING_BLUE, DIVERGING_GRAY, DIVERGING_RED]
    )

    fig, ax = plt.subplots(
        figsize=(max(6, 0.5 * len(corr.columns) + 2), max(5, 0.5 * len(corr.columns) + 1)),
        facecolor=CHART_SURFACE,
    )
    ax.set_facecolor(CHART_SURFACE)
    im = ax.imshow(corr.values, cmap=cmap, vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr.columns)))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right", color=INK_SECONDARY, fontsize=8)
    ax.set_yticks(range(len(corr.columns)))
    ax.set_yticklabels(corr.columns, color=INK_SECONDARY, fontsize=8)
    if annotate:
        for i in range(len(corr.columns)):
            for j in range(len(corr.columns)):
                r = corr.values[i, j]
                text_color = "white" if abs(r) > 0.6 else INK_PRIMARY
                ax.text(j, i, f"{r:.2f}", ha="center", va="center", color=text_color, fontsize=7)
    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("Pearson r", color=INK_SECONDARY, fontsize=9)
    cbar.ax.tick_params(colors=INK_MUTED, labelsize=8)
    ax.set_title(title, color=INK_PRIMARY, fontsize=12, pad=12)
    fig.tight_layout()
    return fig


def plot_rent_distribution(
    df: pd.DataFrame,
    anchors: dict[str, str] = ANCHOR_ZIPS,
    sentinel: int = SUPPRESSED_VALUE,
) -> Figure:
    """Where the anchor ZIPs sit within the full median-rent distribution.

    Excludes the suppression sentinel first, otherwise a single -666666666
    cell would collapse the histogram's x-axis around one outlier bin.
    """
    clean = df[df["median_rent_usd"] != sentinel]
    fig, ax = _new_figure((7, 4.5))
    ax.hist(
        clean["median_rent_usd"],
        bins=15,
        color=SEQUENTIAL_BLUE,
        alpha=0.35,
        edgecolor=DIVERGING_BLUE,
    )
    # Anchor rents can land close together (Wynwood/Downtown are ~$90 apart),
    # so labels are stacked at staggered heights, in rent order, rather than
    # all pinned to the same y: otherwise close values collide and overlap.
    color_by_zip = {z: CATEGORICAL[i % len(CATEGORICAL)] for i, z in enumerate(anchors)}
    present = [
        (zip_code, label, clean.loc[clean["zip"] == zip_code, "median_rent_usd"].iloc[0])
        for zip_code, label in anchors.items()
        if not clean.loc[clean["zip"] == zip_code, "median_rent_usd"].empty
    ]
    present.sort(key=lambda item: item[2])
    y_top = ax.get_ylim()[1] * 1.12
    ax.set_ylim(0, y_top)
    for i, (zip_code, label, rent) in enumerate(present):
        color = color_by_zip[zip_code]
        ax.axvline(rent, color=color, linewidth=2)
        ax.text(
            rent, y_top * (0.98 - 0.12 * i), label,
            color=color, fontsize=9, ha="center", va="top", fontweight="bold",
            bbox=dict(facecolor=CHART_SURFACE, edgecolor="none", pad=1.5),
        )
    ax.set_xlabel("Median rent (USD)", color=INK_SECONDARY, fontsize=10)
    ax.set_ylabel("ZIP count", color=INK_SECONDARY, fontsize=10)
    ax.set_title(
        f"Median rent distribution across {len(clean)} Miami-Dade ZIPs\n"
        "(sentinel-suppressed ZIPs excluded)",
        color=INK_PRIMARY, fontsize=11,
    )
    ax.grid(axis="y", color=GRIDLINE, linewidth=0.6)
    fig.tight_layout()
    return fig


def plot_anchor_lifestyle_comparison(
    df: pd.DataFrame,
    columns: list[str],
    anchors: dict[str, str] = ANCHOR_ZIPS,
) -> Figure:
    """Grouped bar: the five lifestyle-proxy scores, side by side per anchor ZIP."""
    profile = anchor_zip_profile(df, columns, anchors)
    x = range(len(columns))
    width = 0.8 / len(profile)

    fig, ax = _new_figure((7.5, 4.5))
    for i, (_, row) in enumerate(profile.iterrows()):
        offsets = [xi + i * width for xi in x]
        ax.bar(
            offsets, [row[c] for c in columns], width=width,
            color=CATEGORICAL[i % len(CATEGORICAL)], label=row["area_label"],
        )
    ax.set_xticks([xi + width * (len(profile) - 1) / 2 for xi in x])
    ax.set_xticklabels(columns, color=INK_SECONDARY, fontsize=9)
    ax.set_ylabel("Proxy score (0-1)", color=INK_SECONDARY, fontsize=10)
    ax.set_title("Lifestyle-proxy scores by anchor ZIP", color=INK_PRIMARY, fontsize=12, pad=36)
    ax.set_ylim(0, 1.15)
    # Several groups (walkable) peak at 1.0, so the legend sits above the
    # plot area entirely rather than in a corner where it would collide.
    ax.legend(
        frameon=False, labelcolor=INK_SECONDARY, fontsize=9,
        loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=len(profile),
    )
    ax.grid(axis="y", color=GRIDLINE, linewidth=0.6)
    fig.tight_layout()
    return fig


def plot_theme_totals(crowd_text: pd.DataFrame) -> Figure:
    """Horizontal bar of NLP snippet counts per theme, sorted low to high, flags the thin/lopsided corpus."""
    totals = theme_totals(crowd_text).sort_values("snippet_count")
    fig, ax = _new_figure((6.5, 4))
    bars = ax.barh(totals["theme"], totals["snippet_count"], color=SEQUENTIAL_BLUE)
    for bar, count in zip(bars, totals["snippet_count"]):
        ax.text(
            bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2, str(count),
            va="center", color=INK_PRIMARY, fontsize=9,
        )
    ax.set_xlabel("Snippet count", color=INK_SECONDARY, fontsize=10)
    ax.set_title("NLP crowd-text snippets per theme (20 total, 80 ZIPs)", color=INK_PRIMARY, fontsize=12)
    ax.grid(axis="x", color=GRIDLINE, linewidth=0.6)
    fig.tight_layout()
    return fig


def plot_anchor_tenure_mix(
    public_features: pd.DataFrame,
    anchors: dict[str, str] = ANCHOR_ZIPS,
    owner_col: str = "B25003_002E",
    renter_col: str = "B25003_003E",
) -> Figure:
    """Stacked bar: owner- vs renter-occupied share per anchor ZIP, the demographic-proxy risk finding."""
    subset = public_features[public_features["zip"].isin(anchors)].copy()
    subset["area_label"] = subset["zip"].map(anchors)
    total = subset[owner_col] + subset[renter_col]
    subset["owner_share"] = subset[owner_col] / total
    subset["renter_share"] = subset[renter_col] / total
    subset = subset.sort_values("renter_share")

    fig, ax = _new_figure((6.5, 4))
    ax.barh(subset["area_label"], subset["owner_share"], color=CATEGORICAL[0], label="Owner-occupied")
    ax.barh(
        subset["area_label"], subset["renter_share"], left=subset["owner_share"],
        color=CATEGORICAL[1], label="Renter-occupied",
    )
    for y, (_, row) in enumerate(subset.iterrows()):
        ax.text(
            0.02, y, f"{row['owner_share']:.1%} owner", va="center", ha="left",
            color="white", fontsize=8, fontweight="bold",
        )
        ax.text(
            0.98, y, f"{row['renter_share']:.1%} renter", va="center", ha="right",
            color="white", fontsize=8, fontweight="bold",
        )
    ax.set_xlim(0, 1)
    ax.set_xlabel("Share of occupied units", color=INK_SECONDARY, fontsize=10)
    ax.set_title(
        "Owner- vs renter-occupied share, anchor ZIPs\n(tenure as a socioeconomic proxy)",
        color=INK_PRIMARY, fontsize=11,
    )
    ax.legend(frameon=False, labelcolor=INK_SECONDARY, fontsize=9, loc="lower right")
    fig.tight_layout()
    return fig


def main() -> None:
    bundle = load_data()

    print("=== describe(): area_features.csv ===")
    print(describe_numeric(bundle.area_features).round(2).to_string())

    print("\n=== Missingness: miami_dade_public_features.csv ===")
    print(missingness_report(bundle.public_features).to_string(index=False))

    print("\n=== Suppression sentinel check (all files, not just miami_dade_public_features.csv) ===")
    for name, df in (
        ("area_features.csv", bundle.area_features),
        ("miami_dade_public_features.csv", bundle.public_features),
    ):
        report = find_suppressed_cells(df)
        print(f"\n{name}:")
        print("  none found" if report.empty else report.to_string(index=False))

    print("\n=== Zero-variance columns (area_features.csv) ===")
    print(constant_columns(bundle.area_features) or "none")

    # Run against the cleaned file too: that's what Task #5/#6 read, and
    # `walkable` is degenerate in *both*: cleaning median_rent_usd doesn't
    # recompute the column that was derived from it.
    clean_area = pd.read_csv(DATA_DIR / "area_features_clean.csv", dtype={"zip": str})
    print("\n=== Near-constant columns (middle 90% spans < 1e-3) ===")
    for name, df in (("area_features.csv", bundle.area_features), ("area_features_clean.csv", clean_area)):
        report = near_constant_columns(df)
        print(f"\n{name}:")
        print("  none found" if report.empty else report.to_string(index=False))

    print("\n=== Exact duplicate columns (miami_dade_public_features.csv) ===")
    print(exact_duplicate_columns(bundle.public_features) or "none")

    print("\n=== Correlated pairs, |r| >= 0.7 (area_features.csv) ===")
    print(correlated_pairs(bundle.area_features, threshold=0.7).to_string(index=False))

    print("\n=== Correlated pairs, |r| >= 0.7 (miami_dade_public_features.csv) ===")
    print(correlated_pairs(bundle.public_features, threshold=0.7).to_string(index=False))

    print("\n=== NLP theme totals ===")
    print(theme_totals(bundle.crowd_text).to_string(index=False))

    print("\n=== Saving charts for the final presentation ===")
    lifestyle_cols = ["transit", "social", "quiet", "pet_friendly", "walkable"]
    charts = {
        "01_area_features_correlation_heatmap": plot_correlation_heatmap(
            bundle.area_features, "area_features.csv correlation matrix"
        ),
        "02_anchor_rent_distribution": plot_rent_distribution(bundle.area_features),
        "03_anchor_lifestyle_comparison": plot_anchor_lifestyle_comparison(
            bundle.area_features, lifestyle_cols
        ),
        "04_nlp_theme_coverage": plot_theme_totals(bundle.crowd_text),
        "05_anchor_tenure_mix": plot_anchor_tenure_mix(bundle.public_features),
    }
    for name, fig in charts.items():
        path = save_fig(fig, name)
        plt.close(fig)
        print(f"  wrote {path}")


if __name__ == "__main__":
    main()
