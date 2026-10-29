"""Checks for the MCP tools and server (Task #16).

Run from the repo root (also collected by pytest if it is installed):

    python scripts/test_mcp_tools.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
from mcp import Client, StdioServerParameters

from scripts import mcp_tools as t
from scripts.clean_data import SUPPRESSED_VALUE
from scripts.mcp_server import server

TOOL_NAMES = ["schema", "area_stats", "crowd_themes", "recommend", "ethics"]
STARTER_CSVS = {
    "miami_dade_public_features.csv",
    "area_features.csv",
    "crowd_text_snippets.csv",
    "area_options.csv",
}
PROFILE = {
    "budget_max": 2500,
    "household": "with_co_leaser",
    "housing_preference": "own_apartment",
    "tags": ["transit", "walkable"],
}


def _all_values(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _all_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_values(v)
    else:
        yield obj


def test_every_tool_returns_json_with_a_status():
    outputs = [
        t.schema(),
        t.area_stats(),
        t.area_stats("33127"),
        t.crowd_themes("33130"),
        t.recommend(**PROFILE),
        t.ethics(),
    ]
    for out in outputs:
        assert out["status"] == "ok", out.get("status")
        json.dumps(out, allow_nan=False)


def test_schema_lists_columns_for_all_starter_csvs():
    datasets = {d["file"]: d for d in t.schema()["datasets"]}
    assert STARTER_CSVS <= set(datasets)
    for name in STARTER_CSVS:
        expected = list(pd.read_csv(t.DATA_DIR / name, nrows=0).columns)
        assert [c["name"] for c in datasets[name]["columns"]] == expected
    rent = next(c for c in datasets["area_features.csv"]["columns"] if c["name"] == "median_rent_usd")
    assert rent["description"]


def test_area_stats_returns_null_not_the_imputed_value_for_suppressed_cells():
    out = t.area_stats("33101")
    area = out["areas"][0]
    assert area["stats"]["median_rent_usd"] is None
    assert "median_rent_usd" in area["unavailable"]
    clean = pd.read_csv(t.PUBLIC_PATH, dtype={"zip": str}).set_index("zip")
    assert not pd.isna(clean.at["33101", "median_rent_usd"])  # the file holds an imputed number


def test_area_stats_never_leaks_the_sentinel_or_nan():
    values = list(_all_values(t.area_stats()))
    assert SUPPRESSED_VALUE not in values
    assert not any(isinstance(v, float) and v != v for v in values)


def test_area_stats_one_zip_all_zips_and_bad_input():
    assert t.area_stats("33127")["areas"][0]["zip"] == "33127"
    assert t.area_stats()["count"] == t.area_stats("")["count"] == 80
    assert t.area_stats("99999")["status"] == "not_found"
    assert t.area_stats("3312")["status"] == "invalid_input"
    assert t.area_stats(33127)["status"] == "invalid_input"


def test_area_stats_marks_top_coded_medians_as_floors():
    rent = t.area_stats("33149")["areas"][0]
    assert rent["stats"]["median_rent_usd"] == 3501  # the value is kept
    notes = {n["column"]: n for n in rent["top_coded"]}
    assert set(notes) == {"median_rent_usd", "B25064_001E"}
    assert notes["median_rent_usd"]["floor"] == 3500
    home = t.area_stats("33109")["areas"][0]
    assert [n["column"] for n in home["top_coded"]] == ["B25077_001E"]
    assert home["top_coded"][0]["floor"] == 2000000
    assert t.area_stats("33127")["areas"][0]["top_coded"] == []


def test_recommend_marks_a_top_coded_rent():
    out = t.recommend(**{**PROFILE, "budget_max": 5000}, k=80)
    by_zip = {r["zip"]: r for r in out["recommendations"]}
    assert by_zip["33149"]["top_coded"]["floor"] == 3500
    assert all(r["top_coded"] is None for z, r in by_zip.items() if z != "33149")


def test_crowd_themes_returns_text_for_a_known_zip_and_filters_by_theme():
    out = t.crowd_themes("33130")
    assert out["count"] > 0 and all(s["text"] for s in out["snippets"])
    transit = t.crowd_themes("33130", theme="transit")
    assert transit["count"] >= 1 and {s["theme"] for s in transit["snippets"]} == {"transit"}
    assert t.crowd_themes("99999")["status"] == "no_snippets"
    assert t.crowd_themes("x")["status"] == "invalid_input"


def test_recommend_returns_three_to_five_zips_within_budget():
    for k in (3, 5):
        out = t.recommend(**PROFILE, k=k)
        recs = out["recommendations"]
        assert len(recs) == k
        assert all(r["median_rent_usd"] <= PROFILE["budget_max"] for r in recs)


def test_recommend_reports_bad_input_instead_of_raising():
    assert t.recommend(**{**PROFILE, "housing_preference": "house"})["status"] == "invalid_input"
    assert t.recommend(**{**PROFILE, "budget_max": -1})["status"] == "invalid_input"
    assert t.recommend(**PROFILE, k=0)["status"] == "invalid_input"


def test_ethics_returns_rules():
    out = t.ethics()
    assert out["principles"] and out["prohibited_uses"]


def test_server_registers_the_five_tools_and_returns_structured_output():
    async def run():
        async with Client(server) as client:
            names = [tool.name for tool in (await client.list_tools()).tools]
            assert names == TOOL_NAMES
            result = await client.call_tool("recommend", PROFILE)
            assert not result.is_error
            assert result.structured_content == t.recommend(**PROFILE)

    asyncio.run(run())


def test_server_starts_over_stdio():
    params = StdioServerParameters(command=sys.executable, args=["-m", "scripts.mcp_server"], cwd=str(_ROOT))

    async def run():
        async with Client(params) as client:
            assert [tool.name for tool in (await client.list_tools()).tools] == TOOL_NAMES
            result = await client.call_tool("crowd_themes", {"zip_code": "33127"})
            assert result.structured_content["count"] > 0

    asyncio.run(run())


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok    {name}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
