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
from scripts.recommender import DEFAULT_TOP_K
from scripts.recommender import recommend as _recommend

DATA_DIR = _ROOT / "data"
DICTIONARY_PATH = _ROOT / "data_dictionary.md"
PUBLIC_PATH = DATA_DIR / "miami_dade_public_features_clean.csv"
AREA_PATH = DATA_DIR / "area_features_clean.csv"
CROWD_PATH = DATA_DIR / "crowd_text_snippets.csv"

# clean_data.py adds one of these boolean flags next to each column it imputed.
FLAG_SUFFIXES = ("_suppressed", "_missing")
_ZIP_PATTERN = re.compile(r"^\d{5}$")

# Placeholder rules until Task #18 (issue #30) replaces them with the full
# fair-housing rule set. Taken from the README non-negotiables and the
# data_dictionary.md limitations.
ETHICS_RULES = {
    "principles": [
        "Recommend neighborhoods, never score tenants or applicants.",
        "The user explicitly picks household and housing preference; never infer them from demographics.",
        "Co-leaser (sharing a private lease) and co-living (shared/stranger roommates) are different; never infer one from the other.",
        "Only state rents, ZIPs and statistics that a tool returned; never invent listings, rents or neighborhoods.",
        "Synthetic demo options must be labeled NOT A REAL LISTING wherever they appear.",
    ],
    "prohibited_uses": [
        "Tenant or applicant scoring or screening.",
        "Filtering or ranking neighborhoods by race, ethnicity, national origin, religion, sex, familial status, disability or any other protected characteristic, or a proxy for one.",
        "Steering users toward or away from areas based on who lives there.",
        "Leasing decisions.",
        "Presenting synthetic demo options as real, available listings.",
    ],
    "data_limitations": [
        "Snapshot data only, not live market feeds.",
        "Census suppression codes (-666666666) are handled in preprocessing; area_stats returns those values as null.",
        "Crowd text snippets are demo data until they are replaced with a real review corpus.",
        "English-only text bias may apply when using real review corpora.",
    ],
    "when_to_refuse": "Refuse any request for demographic filtering, tenant scoring, or anything that violates the spirit of fair housing, and do not call recommend for it.",
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
        areas.append(
            {
                "zip": row[ID_COLUMN],
                "area_name": _json_value(names.get(row[ID_COLUMN])),
                "stats": stats,
                "unavailable": sorted(unavailable),
            }
        )
    return {"status": "ok", "zip_code": zip_code, "count": len(areas), "areas": areas}


def crowd_themes(zip_code: str, theme: str | None = None) -> dict:
    """Review snippets for a ZIP, optionally narrowed to one theme."""
    error = _check_zip(zip_code)
    if error:
        return _invalid(error)
    zip_code = zip_code.strip()

    snippets = pd.read_csv(CROWD_PATH, dtype={ID_COLUMN: str})
    rows = snippets[snippets[ID_COLUMN] == zip_code]
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
    }


def recommend(
    budget_max: float,
    household: str,
    housing_preference: str,
    tags: list[str],
    k: int = DEFAULT_TOP_K,
) -> dict:
    """Ranked ZIP matches from the baseline recommender (scripts/recommender.py)."""
    profile = {
        "budget_max": budget_max,
        "household": household,
        "housing_preference": housing_preference,
        "tags": tags,
    }
    try:
        return _recommend(profile, top_k=k)
    except ValueError as exc:
        return _invalid(str(exc))


def ethics() -> dict:
    """Fair-use rules, prohibited uses and data limitations."""
    return {"status": "ok", **ETHICS_RULES}


TOOLS = (schema, area_stats, crowd_themes, recommend, ethics)
