"""The five MCP tools as plain functions (Task #16).

Each tool takes JSON-friendly arguments and returns a JSON-serializable dict,
so it can be called and tested without the MCP server or an LLM. The server in
scripts/mcp_server.py only registers these functions.

Every tool returns a "status" field. Bad input comes back as
{"status": "invalid_input", "error": ...} instead of raising, so the agent sees
a structured reason rather than a crash.

Contract rules from MCP_SETUP.md: return structured JSON only, and surface only
values that exist in data/. In area_stats that means a suppressed or missing
Census value is returned as null, not as the median that clean_data.py imputed.
"""
import math
import re
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.feature_schema import ID_COLUMN
from scripts.pull_census import TOP_CODES as _CENSUS_TOP_CODES
from scripts.recommender import DEFAULT_TOP_K
from scripts.recommender import recommend as _recommend
from scripts.theme_extraction import STANCES, THEMES as EXTRACTED_THEMES, extract_themes

DATA_DIR = _ROOT / "data"
DICTIONARY_PATH = _ROOT / "data_dictionary.md"
PUBLIC_PATH = DATA_DIR / "miami_dade_public_features_clean.csv"
AREA_PATH = DATA_DIR / "area_features_clean.csv"
CROWD_PATH = DATA_DIR / "crowd_text_snippets.csv"

# clean_data.py adds one of these boolean flags next to each column it imputed.
FLAG_SUFFIXES = ("_suppressed", "_missing")

# ACS top-codes some medians: 3501 means "more than $3,500" and 2000001 means
# "more than $2,000,000". These are floors, not the real median, so tools
# return them with a top_coded note instead of as a plain number.
# The codes come from pull_census.TOP_CODES ({column: code}); the floor is
# code - 1. median_rent_usd is an alias of B25064_001E (see
# clean_data.DERIVED_ALIASES), so it shares that column's code.
TOP_CODES = {column: (code, code - 1) for column, code in _CENSUS_TOP_CODES.items()}
TOP_CODES["median_rent_usd"] = TOP_CODES["B25064_001E"]
_ZIP_PATTERN = re.compile(r"^\d{5}$")

ETHICS_RULES = {
    "policy_version": "task18-v1",
    "scope": (
        "Neighborhood recommendation guidance for this prototype; not tenant screening, "
        "listing search, legal advice, or a certification of fair-housing compliance."
    ),
    "rules": [
        {
            "id": "no_demographic_filtering",
            "title": "No demographic filtering or steering",
            "prohibited_actions": [
                (
                    "Filter, rank, exclude, or steer neighborhoods using protected characteristics, "
                    "including race, ethnicity, national origin, religion, sex, familial status, "
                    "and disability."
                ),
                "Use demographic proxies to accomplish demographic targeting or exclusion.",
                "Recommend an area based on who lives there or who the user should live near or avoid.",
            ],
            "permitted_alternatives": [
                (
                    "Use an explicitly supplied budget as the hard eligibility filter and explicit "
                    "transit, social, and quiet preferences as ranking features."
                ),
                (
                    "Walkability and pet-friendly indicators are recognized inputs but are not scored; "
                    "do not offer them as ranking criteria."
                ),
                "Describe available aggregate data without using it to target or exclude people or neighborhoods.",
            ],
        },
        {
            "id": "no_tenant_scoring",
            "title": "No tenant or applicant scoring",
            "prohibited_actions": [
                "Evaluate a person's suitability, eligibility, risk, or worthiness as a tenant.",
                "Generate screening scores, hidden landlord criteria, approval predictions, or leasing decisions.",
            ],
            "permitted_alternatives": [
                "Recommend neighborhoods from the user's explicit preferences.",
                "Explain that property-specific eligibility and screening are outside this tool's scope.",
            ],
        },
        {
            "id": "no_inferred_housing_preferences",
            "title": "Do not infer housing preferences",
            "prohibited_actions": [
                "Infer housing preference from identity, name, language, background, household characteristics, or protected characteristics.",
                "Convert living alone into co-living or having a co-leaser into own-apartment preference.",
            ],
            "permitted_alternatives": [
                "Ask the user to choose own_apartment or co_living explicitly.",
                "Keep household and housing_preference as independent inputs and return each unchanged.",
            ],
        },
        {
            "id": "explicit_preferences_only",
            "title": "Use explicit, relevant preferences",
            "prohibited_actions": [
                "Invent a budget, housing preference, household value, or lifestyle priority.",
            ],
            "permitted_alternatives": [
                (
                    "Use a user-supplied budget as the hard eligibility filter and explicit transit, "
                    "social, and quiet preferences as ranking features."
                ),
                (
                    "Use the user's explicit housing preference; co_living adds the "
                    "co_living_friendly ranking feature, while household remains independent."
                ),
                (
                    "Walkability and pet-friendly indicators are recognized inputs but are not scored; "
                    "do not offer them as ranking criteria."
                ),
                "Ask for missing required recommendation inputs instead of inferring them.",
            ],
        },
        {
            "id": "no_listing_or_affordability_guarantees",
            "title": "Do not overstate recommendation outputs",
            "prohibited_actions": [
                "Present a neighborhood recommendation as tenant screening or a leasing decision.",
                "Claim that a listing is available or that the user is guaranteed to afford or obtain housing.",
                "Present synthetic area_options rows as real listings.",
            ],
            "permitted_alternatives": [
                "Describe rent values as area-level reference estimates with their source and period.",
                "Label listing-style demo rows as NOT A REAL LISTING and direct users to current listing sources for availability.",
            ],
        },
    ],
    "data_limitations": [
        {
            "id": "real_aggregate_sources",
            "description": (
                "The project uses real aggregate sources: 2020-2024 ACS five-year estimates, "
                "a September 2026 Zillow ZORI snapshot covering 75 of 80 project ZIPs, and "
                "selected Google Local review excerpts. These sources are not synthetic."
            ),
            "references": [
                "data/area_features_clean.metadata.json",
                "data/zillow_rent_snapshot.metadata.json",
                "data_dictionary.md",
                "ATTRIBUTION.md",
            ],
        },
        {
            "id": "synthetic_demo_options",
            "description": (
                "data/area_options.csv contains synthetic listing-style demo cards. "
                "Every option is labeled NOT A REAL LISTING. These are not real "
                "apartments or evidence of current availability."
            ),
            "references": ["data/README.md", "data_dictionary.md"],
        },
        {
            "id": "synthetic_evaluation_profiles",
            "description": (
                "eval/recommendation_profiles.json contains test profiles for evaluation. "
                "They do not establish real-world fairness, representativeness, or performance."
            ),
            "references": ["eval/README.md", "EVAL_FRAMEWORK.md"],
        },
        {
            "id": "indicator_limits",
            "description": (
                "ZIP-level neighborhood indicators are aggregate or proxy features and cannot "
                "guarantee an individual's experience; walkability and pet-friendly inputs are "
                "recognized but are not scored in the current recommender."
            ),
            "references": ["FEATURE_SCHEMA.md", "data_dictionary.md"],
        },
        {
            "id": "review_sample_limits",
            "description": (
                "The review corpus is a selected, non-representative sample for three anchor ZIPs, "
                "including some Google-provided translations. It does not represent every resident "
                "or guarantee an individual's experience."
            ),
            "references": ["data_dictionary.md", "data/crowd_text_selection.json"],
        },
        {
            "id": "rent_reference_limits",
            "description": (
                "ACS and Zillow values form area-level reference ranges from different measures "
                "and periods. They are not guaranteed market bounds, current-market affordability, "
                "property-specific prices, or available listings."
            ),
            "references": ["data/zillow_rent_snapshot.metadata.json", "data_dictionary.md"],
        },
    ],
    "routing": {
        "call_ethics_for": [
            "fairness, discrimination, fair-housing, or demographic-targeting questions",
            "tenant or applicant scoring, screening, eligibility, risk, or worthiness requests",
            "requests to infer housing preferences or use household composition as a substitute",
            "questions about synthetic, demo, sampled, provenance, or data limitations",
        ],
        "prohibited_request_action": (
            "Call ethics, refuse the prohibited action, offer a permitted alternative, and do not call recommend."
        ),
        "mixed_request_action": (
            "Call ethics first and refuse the prohibited portion. Continue to recommend only when "
            "the remaining criteria are permissible and the user explicitly supplies every required input."
        ),
    },
}


def _invalid(message: str) -> dict:
    return {"status": "invalid_input", "error": message}


def _check_zip(zip_code) -> str | None:
    """Return an error message, or None if zip_code is a 5-digit string."""
    if not isinstance(zip_code, str) or not _ZIP_PATTERN.match(zip_code.strip()):
        return f"zip_code must be a 5-digit string, got {zip_code!r}"
    return None


def _json_value(value):
    """NaN becomes None and numpy scalars become Python numbers."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if hasattr(value, "item"):
        value = value.item()
        if isinstance(value, float) and math.isnan(value):
            return None
    return value


def _read_dictionary(path: Path = DICTIONARY_PATH) -> dict[str, dict]:
    """Parse data_dictionary.md into {file name: {"description", "columns"}}.

    The dictionary stays the single source of truth for column notes, so
    schema() does not carry a second copy that could drift.
    """
    sections: dict[str, dict] = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"^## (\S+\.(?:csv|txt))\s*$", line)
        if heading:
            current = {"description": "", "columns": {}}
            sections[heading.group(1)] = current
            continue
        if line.startswith("## "):
            current = None
            continue
        if current is None:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) == 3 and cells[0] not in ("Column", "") and not set(cells[0]) <= {"-"}:
            current["columns"][cells[0]] = {"type": cells[1], "description": cells[2]}
        elif line.strip() and not line.startswith("|") and not current["description"]:
            current["description"] = line.strip()
    return sections


def _top_coded(column: str, value) -> dict | None:
    """A top_coded note if value is the ACS top code for column, else None."""
    if column not in TOP_CODES or value is None:
        return None
    code, floor = TOP_CODES[column]
    if value != code:
        return None
    return {
        "column": column,
        "value": code,
        "floor": floor,
        "meaning": f"ACS top code: the real median is more than {floor:,}, exact value unknown.",
    }


def _flag_source(flag: str) -> str:
    """median_rent_usd_suppressed -> median_rent_usd."""
    for suffix in FLAG_SUFFIXES:
        if flag.endswith(suffix):
            return flag[: -len(suffix)]
    return flag


def _flag_note(column: str) -> str | None:
    if not column.endswith(FLAG_SUFFIXES):
        return None
    kind = column[len(_flag_source(column)) + 1 :]
    return f"True where {_flag_source(column)} was {kind} in the source data and clean_data.py imputed it."


def schema() -> dict:
    """Column names, types and notes for every CSV in data/."""
    dictionary = _read_dictionary()
    datasets = []
    for path in sorted(DATA_DIR.glob("*.csv")):
        # A *_clean.csv file shares its notes with the raw file it was built from.
        base_name = path.name.replace("_clean.csv", ".csv")
        entry = dictionary.get(base_name, {"description": "", "columns": {}})
        df = pd.read_csv(path, dtype={ID_COLUMN: str}, nrows=200)
        columns = []
        for column in df.columns:
            documented = entry["columns"].get(column, {})
            columns.append(
                {
                    "name": column,
                    "dtype": str(df[column].dtype),
                    "documented_type": documented.get("type"),
                    "description": documented.get("description") or _flag_note(column),
                }
            )
        datasets.append(
            {
                "file": path.name,
                "derived_from": base_name if base_name != path.name else None,
                "description": entry["description"] or None,
                "columns": columns,
            }
        )
    return {"status": "ok", "datasets": datasets}


def area_stats(zip_code: str | None = None) -> dict:
    """Public Census/Zillow stats for one ZIP, or for every ZIP if zip_code is empty.

    A value that was suppressed or missing in the source is returned as null and
    its column is listed under "unavailable", never as the imputed median.
    A top-coded value (e.g. rent 3501) is kept and explained under "top_coded".
    """
    if zip_code is not None and str(zip_code).strip() == "":
        zip_code = None
    if zip_code is not None:
        error = _check_zip(zip_code)
        if error:
            return _invalid(error)
        zip_code = zip_code.strip()

    public = pd.read_csv(PUBLIC_PATH, dtype={ID_COLUMN: str})
    names = pd.read_csv(AREA_PATH, dtype={ID_COLUMN: str}).set_index(ID_COLUMN)["area_name"]
    flags = [c for c in public.columns if c.endswith(FLAG_SUFFIXES)]
    value_columns = [c for c in public.columns if c not in flags and c != ID_COLUMN]

    if zip_code is not None:
        public = public[public[ID_COLUMN] == zip_code]
        if public.empty:
            return {"status": "not_found", "zip_code": zip_code, "areas": []}

    areas = []
    for _, row in public.iterrows():
        unavailable = [_flag_source(flag) for flag in flags if bool(row[flag])]
        stats = {}
        for column in value_columns:
            stats[column] = None if column in unavailable else _json_value(row[column])
        top_coded = [note for column, value in stats.items() if (note := _top_coded(column, value))]
        areas.append(
            {
                "zip": row[ID_COLUMN],
                "area_name": _json_value(names.get(row[ID_COLUMN])),
                "stats": stats,
                "unavailable": sorted(unavailable),
                "top_coded": top_coded,
            }
        )
    return {"status": "ok", "zip_code": zip_code, "count": len(areas), "areas": areas}


def crowd_themes(zip_code: str, theme: str | None = None) -> dict:
    """Review snippets for a ZIP, optionally narrowed to one theme.

    `snippets` filters on the hand-written theme label. `extracted` reads the
    themes from the review text itself (scripts/theme_extraction.py), with a
    stance per review and the phrase that matched, so the agent can say how
    many reviews speak for or against a theme and quote the evidence.
    """
    error = _check_zip(zip_code)
    if error:
        return _invalid(error)
    zip_code = zip_code.strip()

    snippets = pd.read_csv(CROWD_PATH, dtype={ID_COLUMN: str})
    if theme and theme not in set(snippets["theme"].dropna()):
        known = sorted(snippets["theme"].dropna().unique().tolist())
        return _invalid(f"Unknown theme: {theme!r}. Expected one of {known}.")
    rows = snippets[snippets[ID_COLUMN] == zip_code]
    extracted = _extracted(rows, theme)
    available = sorted(rows["theme"].dropna().unique().tolist())
    if theme:
        rows = rows[rows["theme"] == theme]

    return {
        "status": "ok" if len(rows) else "no_snippets",
        "zip_code": zip_code,
        "theme": theme or None,
        "available_themes": available,
        "count": int(len(rows)),
        "snippets": [
            {
                "snippet_id": row["snippet_id"],
                "theme": row["theme"],
                "source": row["source"],
                "text": row["text"],
            }
            for _, row in rows.iterrows()
        ],
        "extracted": extracted,
    }


def _extracted(zip_rows: pd.DataFrame, theme: str | None) -> dict:
    """Themes read from the review text, not the hand label, narrowed to `theme` if given.

    Every entry quotes an existing review (snippet_id, text, source) plus the
    phrase that set its stance; nothing is generated. This can find reviews
    the hand label misses, so `extracted.count` can be above 0 even when the
    labeled `snippets` are empty. Only the themes in `themes_supported` are
    extracted; a hand-label theme outside them always comes back empty here.
    """
    # A blank id or source would serialize as NaN and break the whole result.
    rows = zip_rows.assign(
        snippet_id=zip_rows["snippet_id"].fillna("").astype(str),
        source=zip_rows["source"].fillna("").astype(str),
    )
    found: dict[str, list[dict]] = {}
    for r in extract_themes(rows).itertuples(index=False):
        if theme and r.theme != theme:
            continue
        found.setdefault(r.theme, []).append(
            {"snippet_id": r.snippet_id, "stance": r.stance, "evidence": r.evidence,
             "text": r.text, "source": r.source}
        )
    found = dict(sorted(found.items()))
    return {
        "method": (
            "Keyword lexicon over the review text (scripts/theme_extraction.py). Stance is "
            "supports, contradicts or mentions (names the topic without judging it). "
            "Independent of the hand label that `status`, `count` and `snippets` use."
        ),
        "themes_supported": list(EXTRACTED_THEMES),
        "count": sum(len(v) for v in found.values()),
        "summary": {t: {s: sum(r["stance"] == s for r in v) for s in STANCES} for t, v in found.items()},
        "themes": found,
    }


def recommend(
    budget_max: float,
    household: str,
    housing_preference: str,
    tags: list[str],
    k: int = DEFAULT_TOP_K,
) -> dict:
    """Ranked ZIP matches from the baseline recommender (scripts/recommender.py).

    Each recommendation keeps the recommender's rent-range contract, plus
    ranking_reasons and a summary built only from returned values.
    """
    profile = {
        "budget_max": budget_max,
        "household": household,
        "housing_preference": housing_preference,
        "tags": tags,
    }
    try:
        result = _recommend(profile, top_k=k)
    except ValueError as exc:
        return _invalid(str(exc))

    features = ", ".join(result["vector_features"])
    result["rank_basis"] = (
        f"ZIPs whose lower usable rent estimate exceeds budget_max are removed first. "
        f"The rest are ranked by cosine similarity "
        f"between the user vector and each ZIP's scores on {features}; ties go to the lower ZIP."
    )
    for rec in result["recommendations"]:
        rec["ranking_reasons"] = _ranking_reasons(rec, result)
        rec["summary"] = _summary(rec, result)
    return result


def _ranking_reasons(rec: dict, result: dict) -> list[dict]:
    """Why a ZIP got its rank, using only values already in the recommend result.

    Cosine similarity rises with the scores on the selected features and falls
    with the scores on the unselected ones, so both are listed.
    """
    reasons = [
        {
            "code": "within_budget",
            "budget_rent_usd": rec["budget_rent_usd"],
            "rent_lower_usd": rec["rent_lower_usd"],
            "rent_upper_usd": rec["rent_upper_usd"],
            "rent_basis": rec["rent_basis"],
            "budget_position": rec["budget_position"],
            "budget_max": result["budget_max"],
            "headroom_usd": round(result["budget_max"] - rec["budget_rent_usd"]),
        }
    ]
    for feature in result["vector_features"]:
        score = rec["feature_scores"][feature]
        if feature in result["active_features"]:
            reasons.append({"code": "selected_feature", "feature": feature, "area_score": score})
        else:
            reasons.append(
                {
                    "code": "unselected_feature",
                    "feature": feature,
                    "area_score": score,
                    "effect": "lowers_similarity" if score > 0 else "none",
                }
            )
    return reasons


def _summary(rec: dict, result: dict) -> str:
    name = rec["area_name"] or rec["zip"]
    selected = ", ".join(f"{f['feature']} {f['area_score']:.2f}" for f in rec["matched_features"])
    budget = f"${result['budget_max']:,.0f}"
    if rec["rent_basis"] == "acs_and_zori":
        rent = (
            f"rent reference range ${rec['rent_lower_usd']:,.0f}–${rec['rent_upper_usd']:,.0f}; "
            f"budget position: {rec['budget_position'].replace('_', ' ')}"
        )
    else:
        source = "ACS" if rec["rent_basis"] == "acs_only" else "Zillow ZORI"
        rent = f"single-source {source} rent estimate ${rec['rent_lower_usd']:,.0f}"
    return (
        f"#{rec['rank']} {name} ({rec['zip']}): {rent}, within the {budget} budget. "
        f"Similarity {rec['similarity']:.3f}; "
        f"selected-feature scores: {selected}."
    )


def ethics() -> dict:
    """Structured fair-housing rules, permitted alternatives, routing, and data limits."""
    return {"status": "ok", **ETHICS_RULES}


TOOLS = (schema, area_stats, crowd_themes, recommend, ethics)
