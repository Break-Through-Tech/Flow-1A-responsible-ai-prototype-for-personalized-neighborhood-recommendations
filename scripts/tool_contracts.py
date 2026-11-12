"""JSON contracts for the five MCP tools (Task #17).

One JSON Schema per tool for its arguments (INPUT_SCHEMAS) and one for its
result (OUTPUT_SCHEMAS). The server in scripts/mcp_server.py publishes both
and routes every call through call_tool(), so:

- arguments that break the input schema come back as structured
  {"status": "invalid_input", "errors": [...]} instead of a free-text error;
- a result that breaks the output schema comes back as
  {"status": "contract_violation", ...} instead of reaching the agent;
- a tool that raises comes back as {"status": "tool_error", ...} instead of
  an SDK error.

Every result has a "status". The output schemas pin the shape of each status,
for example "no_areas_within_budget" always has an empty recommendations list.

Vocabularies (households, housing preferences, tags, crowd themes) are read
from the modules and data that own them, so the contract cannot drift from
what the tools accept.

Run from the repo root to print every schema:

    python scripts/tool_contracts.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from jsonschema import Draft202012Validator

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.feature_schema import TAG_TO_COLUMN, VALID_HOUSING_PREFERENCES
from scripts.recommender import DEFAULT_TOP_K, VALID_HOUSEHOLDS

CROWD_PATH = _ROOT / "data" / "crowd_text_snippets.csv"

MAX_K = 10  # README asks for 3-5 matches; 10 leaves room for deeper ranking
TAGS = list(TAG_TO_COLUMN)
HOUSEHOLDS = sorted(VALID_HOUSEHOLDS)
HOUSING_PREFERENCES = sorted(VALID_HOUSING_PREFERENCES)
CROWD_THEMES = sorted(pd.read_csv(CROWD_PATH)["theme"].dropna().unique().tolist())

ZIP_PATTERN = r"^\s*\d{5}\s*$"
_ZIP = {"type": "string", "pattern": r"^\d{5}$"}
_STR_OR_NULL = {"type": ["string", "null"]}
_SCORE = {"type": "number", "minimum": 0, "maximum": 1}
_STRINGS = {"type": "array", "items": {"type": "string"}}


def _no_args() -> dict:
    return {"type": "object", "properties": {}, "additionalProperties": False}


INPUT_SCHEMAS: dict[str, dict] = {
    "schema": _no_args(),
    "area_stats": {
        "type": "object",
        "properties": {
            "zip_code": {
                "type": ["string", "null"],
                "pattern": r"^\s*(\d{5})?\s*$",
                "description": "5-digit Miami ZIP. Omit, null or empty string for every ZIP.",
            },
        },
        "additionalProperties": False,
    },
    "crowd_themes": {
        "type": "object",
        "properties": {
            "zip_code": {"type": "string", "pattern": ZIP_PATTERN, "description": "5-digit Miami ZIP."},
            "theme": {
                "type": ["string", "null"],
                "enum": [*CROWD_THEMES, None],
                "description": "Only return snippets with this theme.",
            },
        },
        "required": ["zip_code"],
        "additionalProperties": False,
    },
    "recommend": {
        "type": "object",
        "properties": {
            "budget_max": {
                "type": "number",
                "exclusiveMinimum": 0,
                "description": "Monthly rent ceiling in USD. ZIPs above it are never returned.",
            },
            "household": {
                "enum": HOUSEHOLDS,
                "description": "with_co_leaser means a partner or friend on the same private lease. It is not co-living.",
            },
            "housing_preference": {
                "enum": HOUSING_PREFERENCES,
                "description": "Picked by the user. Never infer it from household.",
            },
            "tags": {
                "type": "array",
                "items": {"enum": TAGS},
                "minItems": 1,
                "description": "Lifestyle priorities. walkable and pet_friendly are accepted but not scored yet.",
            },
            "k": {"type": "integer", "minimum": 1, "maximum": MAX_K, "default": DEFAULT_TOP_K},
        },
        "required": ["budget_max", "household", "housing_preference", "tags"],
        "additionalProperties": False,
    },
    "ethics": _no_args(),
}


# Shapes shared by every tool's output.
_INVALID_INPUT = {
    "type": "object",
    "properties": {
        "status": {"const": "invalid_input"},
        "error": {"type": "string", "minLength": 1},
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"field": {"type": "string"}, "message": {"type": "string"}},
                "required": ["field", "message"],
            },
        },
    },
    "required": ["status", "error"],
}
_CONTRACT_VIOLATION = {
    "type": "object",
    "properties": {
        "status": {"const": "contract_violation"},
        "tool": {"type": "string"},
        "error": {"type": "string"},
        "errors": _INVALID_INPUT["properties"]["errors"],
    },
    "required": ["status", "tool", "error", "errors"],
}
_TOOL_ERROR = {
    "type": "object",
    "properties": {
        "status": {"const": "tool_error"},
        "tool": {"type": "string"},
        "error": {"type": "string", "minLength": 1},
    },
    "required": ["status", "tool", "error"],
}


def _result(*variants: dict) -> dict:
    """A tool output: one of its own variants, invalid_input, contract_violation or tool_error."""
    return {"type": "object", "oneOf": [*variants, _INVALID_INPUT, _CONTRACT_VIOLATION, _TOOL_ERROR]}


def _variant(status: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {"status": {"const": status}, **properties},
        "required": ["status", *required],
    }


_COLUMN = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "dtype": {"type": "string"},
        "documented_type": _STR_OR_NULL,
        "description": _STR_OR_NULL,
    },
    "required": ["name", "dtype", "documented_type", "description"],
}
_DATASET = {
    "type": "object",
    "properties": {
        "file": {"type": "string"},
        "derived_from": _STR_OR_NULL,
        "description": _STR_OR_NULL,
        "columns": {"type": "array", "items": _COLUMN, "minItems": 1},
    },
    "required": ["file", "derived_from", "description", "columns"],
}

_TOP_CODED = {
    "type": "object",
    "properties": {
        "column": {"type": "string"},
        "value": {"type": "number"},
        "floor": {"type": "number"},
        "meaning": {"type": "string", "minLength": 1},
    },
    "required": ["column", "value", "floor", "meaning"],
}

_AREA = {
    "type": "object",
    "properties": {
        "zip": _ZIP,
        "area_name": _STR_OR_NULL,
        "stats": {"type": "object", "additionalProperties": {"type": ["number", "string", "null"]}},
        "unavailable": _STRINGS,
        "top_coded": {"type": "array", "items": _TOP_CODED},
    },
    "required": ["zip", "area_name", "stats", "unavailable", "top_coded"],
}

_SNIPPET = {
    "type": "object",
    "properties": {
        "snippet_id": {"type": "string"},
        "theme": {"type": "string"},
        "source": {"type": "string"},
        "text": {"type": "string", "minLength": 1},
    },
    "required": ["snippet_id", "theme", "source", "text"],
}
_CROWD_COMMON = {
    "zip_code": _ZIP,
    "theme": _STR_OR_NULL,
    "available_themes": _STRINGS,
    "count": {"type": "integer", "minimum": 0},
}

_REASON = {
    "type": "object",
    "oneOf": [
        {
            "properties": {
                "code": {"const": "within_budget"},
                "median_rent_usd": {"type": "number"},
                "budget_max": {"type": "number"},
                "headroom_usd": {"type": "number", "minimum": 0},
                "rent_is_top_coded": {"type": "boolean"},
            },
            "required": ["code", "median_rent_usd", "budget_max", "headroom_usd", "rent_is_top_coded"],
        },
        {
            "properties": {
                "code": {"const": "selected_feature"},
                "feature": {"type": "string"},
                "area_score": _SCORE,
            },
            "required": ["code", "feature", "area_score"],
        },
        {
            "properties": {
                "code": {"const": "unselected_feature"},
                "feature": {"type": "string"},
                "area_score": _SCORE,
                "effect": {"enum": ["lowers_similarity", "none"]},
            },
            "required": ["code", "feature", "area_score", "effect"],
        },
    ],
}
_RECOMMENDATION = {
    "type": "object",
    "properties": {
        "rank": {"type": "integer", "minimum": 1},
        "zip": _ZIP,
        "area_name": {"type": "string"},
        "median_rent_usd": {"type": "number"},
        "similarity": {"type": "number", "minimum": 0},
        "matched_features": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"feature": {"type": "string"}, "area_score": _SCORE},
                "required": ["feature", "area_score"],
            },
        },
        "feature_scores": {"type": "object", "additionalProperties": _SCORE},
        "top_coded": {"oneOf": [_TOP_CODED, {"type": "null"}]},
        "ranking_reasons": {"type": "array", "items": _REASON, "minItems": 2},
        "summary": {"type": "string", "minLength": 1},
    },
    "required": [
        "rank", "zip", "area_name", "median_rent_usd", "similarity",
        "matched_features", "feature_scores", "top_coded", "ranking_reasons", "summary",
    ],
}
_RECOMMEND_COMMON = {
    "household": {"enum": HOUSEHOLDS},
    "housing_preference": {"enum": HOUSING_PREFERENCES},
    "budget_max": {"type": "number", "exclusiveMinimum": 0},
    "tags": {"type": "array", "items": {"enum": TAGS}},
    "vector_features": _STRINGS,
    "active_features": _STRINGS,
    "unscored_tags": _STRINGS,
    "user_vector": {"type": "object", "additionalProperties": {"enum": [0.0, 1.0]}},
    "candidate_count": {"type": "integer", "minimum": 0},
    "rank_basis": {"type": "string", "minLength": 1},
}
_RECOMMEND_REQUIRED = [*_RECOMMEND_COMMON, "recommendations"]

OUTPUT_SCHEMAS: dict[str, dict] = {
    "schema": _result(
        _variant("ok", {"datasets": {"type": "array", "items": _DATASET, "minItems": 1}}, ["datasets"]),
    ),
    "area_stats": _result(
        _variant(
            "ok",
            {
                "zip_code": {"type": ["string", "null"]},
                "count": {"type": "integer", "minimum": 1},
                "areas": {"type": "array", "items": _AREA, "minItems": 1},
            },
            ["zip_code", "count", "areas"],
        ),
        _variant("not_found", {"zip_code": _ZIP, "areas": {"type": "array", "maxItems": 0}}, ["zip_code", "areas"]),
    ),
    "crowd_themes": _result(
        _variant(
            "ok",
            {**_CROWD_COMMON, "count": {"type": "integer", "minimum": 1},
             "snippets": {"type": "array", "items": _SNIPPET, "minItems": 1}},
            [*_CROWD_COMMON, "snippets"],
        ),
        _variant(
            "no_snippets",
            {**_CROWD_COMMON, "count": {"const": 0}, "snippets": {"type": "array", "maxItems": 0}},
            [*_CROWD_COMMON, "snippets"],
        ),
    ),
    "recommend": _result(
        _variant(
            "ok",
            {**_RECOMMEND_COMMON, "candidate_count": {"type": "integer", "minimum": 1},
             "recommendations": {"type": "array", "items": _RECOMMENDATION, "minItems": 1, "maxItems": MAX_K}},
            _RECOMMEND_REQUIRED,
        ),
        _variant(
            "no_areas_within_budget",
            {**_RECOMMEND_COMMON, "candidate_count": {"const": 0},
             "recommendations": {"type": "array", "maxItems": 0}},
            _RECOMMEND_REQUIRED,
        ),
    ),
    "ethics": _result(
        _variant(
            "ok",
            {
                "principles": {**_STRINGS, "minItems": 1},
                "prohibited_uses": {**_STRINGS, "minItems": 1},
                "data_limitations": {**_STRINGS, "minItems": 1},
                "when_to_refuse": {"type": "string", "minLength": 1},
            },
            ["principles", "prohibited_uses", "data_limitations", "when_to_refuse"],
        ),
    ),
}

for _schema in (*INPUT_SCHEMAS.values(), *OUTPUT_SCHEMAS.values()):
    Draft202012Validator.check_schema(_schema)

_INPUT_VALIDATORS = {name: Draft202012Validator(s) for name, s in INPUT_SCHEMAS.items()}
_OUTPUT_VALIDATORS = {name: Draft202012Validator(s) for name, s in OUTPUT_SCHEMAS.items()}


def _field(path) -> str:
    return ".".join(str(part) for part in path) or "(root)"


def _errors(validator: Draft202012Validator, instance: Any) -> list[dict]:
    found = []
    for error in sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path)):
        # For oneOf failures, report the variant matching the payload's status.
        if error.validator == "oneOf" and isinstance(instance, dict) and error.context:
            status = instance.get("status")
            matching = [e for e in error.context if not _status_mismatch(e, status)]
            if matching:
                found.extend(
                    {"field": _field(e.absolute_path), "message": e.message} for e in matching
                )
                continue
        found.append({"field": _field(error.absolute_path), "message": error.message})
    return found


def _status_mismatch(error, status) -> bool:
    """A oneOf sub-error that only says the variant's status const differs."""
    return list(error.absolute_path) == ["status"] and error.validator == "const" and error.instance == status


def validate_input(tool: str, arguments: dict) -> list[dict]:
    """Field-level errors for these arguments, or [] if they meet the contract."""
    return _errors(_INPUT_VALIDATORS[tool], arguments)


def validate_output(tool: str, result: dict) -> list[dict]:
    """Field-level errors for this result, or [] if it meets the contract."""
    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError) as exc:
        return [{"field": "(root)", "message": f"not JSON-serializable: {exc}"}]
    return _errors(_OUTPUT_VALIDATORS[tool], result)


def call_tool(tool: str, fn: Callable[..., dict], arguments: dict) -> dict:
    """Validate arguments, call fn, validate the result. Always returns a status, never raises."""
    errors = validate_input(tool, arguments)
    if errors:
        summary = "; ".join(f"{e['field']}: {e['message']}" for e in errors)
        return {"status": "invalid_input", "error": summary, "errors": errors}

    try:
        result = fn(**arguments)
    except Exception as exc:
        return {
            "status": "tool_error",
            "tool": tool,
            "error": f"{tool} failed ({type(exc).__name__}: {exc}); nothing from it is safe to show.",
        }
    errors = validate_output(tool, result)
    if errors:
        return {
            "status": "contract_violation",
            "tool": tool,
            "error": f"{tool} returned a result that breaks its output contract; nothing from it is safe to show.",
            "errors": errors,
        }
    return result


if __name__ == "__main__":
    print(json.dumps({"input": INPUT_SCHEMAS, "output": OUTPUT_SCHEMAS}, indent=2))
