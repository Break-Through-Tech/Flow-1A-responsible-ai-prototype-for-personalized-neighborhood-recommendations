"""Checks for the MCP tool JSON contracts (Task #17).

Covers well-formed, malformed, empty and no-match calls for every tool, the
ranking reasons in recommend, and that the server publishes and enforces the
contracts in scripts/tool_contracts.py.

Run from the repo root (also collected by pytest if it is installed):

    python scripts/test_tool_contracts.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mcp import Client

from scripts import mcp_tools as t
from scripts import tool_contracts as c
from scripts.feature_schema import BUDGET_COLUMN
from scripts.mcp_server import server
from scripts.recommender import filter_by_budget, load_area_features

PROFILE = {
    "budget_max": 2500,
    "household": "with_co_leaser",
    "housing_preference": "own_apartment",
    "tags": ["transit", "walkable"],
}
CO_LIVING = {"budget_max": 1800, "household": "alone", "housing_preference": "co_living", "tags": ["co_living", "transit"]}



def _few_candidates_budget(k: int = 5) -> float:
    """The lowest budget that leaves between 1 and k-1 ZIPs, read from the data."""
    rents = sorted(filter_by_budget(load_area_features(), float("inf"))[BUDGET_COLUMN])
    return float(rents[min(2, k - 2)])


FEW_BUDGET = _few_candidates_budget()

# (tool, arguments, status) for calls that meet the input contract.
WELL_FORMED = [
    ("schema", {}, "ok"),
    ("area_stats", {}, "ok"),
    ("area_stats", {"zip_code": ""}, "ok"),
    ("area_stats", {"zip_code": "33127"}, "ok"),
    ("area_stats", {"zip_code": "33101"}, "ok"),  # suppressed rent comes back as null
    ("crowd_themes", {"zip_code": "33130"}, "ok"),
    ("crowd_themes", {"zip_code": "33130", "theme": "transit"}, "ok"),
    ("recommend", PROFILE, "ok"),
    ("recommend", {**PROFILE, "k": 1}, "ok"),
    ("recommend", {**PROFILE, "k": c.MAX_K}, "ok"),
    ("recommend", CO_LIVING, "ok"),
    ("recommend", {**PROFILE, "budget_max": FEW_BUDGET}, "ok"),  # fewer candidates than k
    ("ethics", {}, "ok"),
    # Empty and no-match results are valid, just empty.
    ("area_stats", {"zip_code": "99999"}, "not_found"),
    ("crowd_themes", {"zip_code": "99999"}, "no_snippets"),
    ("crowd_themes", {"zip_code": "33186", "theme": "quiet"}, "no_snippets"),
    ("recommend", {**PROFILE, "budget_max": 1}, "no_areas_within_budget"),
]

# (tool, arguments, field the error must name) for calls that break it.
MALFORMED = [
    ("schema", {"extra": 1}, "(root)"),
    ("ethics", {"extra": 1}, "(root)"),
    ("area_stats", {"zip_code": 33127}, "zip_code"),
    ("area_stats", {"zip_code": "3312"}, "zip_code"),
    ("area_stats", {"zip_code": "abcde"}, "zip_code"),
    ("crowd_themes", {}, "(root)"),
    ("crowd_themes", {"zip_code": ["33130"]}, "zip_code"),
    ("crowd_themes", {"zip_code": "33130", "theme": "nonsense"}, "theme"),
    ("recommend", {}, "(root)"),
    ("recommend", {k: v for k, v in PROFILE.items() if k != "budget_max"}, "(root)"),
    ("recommend", {**PROFILE, "budget_max": "2500"}, "budget_max"),
    ("recommend", {**PROFILE, "budget_max": 0}, "budget_max"),
    ("recommend", {**PROFILE, "budget_max": -100}, "budget_max"),
    ("recommend", {**PROFILE, "budget_max": True}, "budget_max"),
    ("recommend", {**PROFILE, "household": "couple"}, "household"),
    ("recommend", {**PROFILE, "household": "co_living"}, "household"),
    ("recommend", {**PROFILE, "housing_preference": "house"}, "housing_preference"),
    ("recommend", {**PROFILE, "tags": "transit"}, "tags"),
    ("recommend", {**PROFILE, "tags": []}, "tags"),
    ("recommend", {**PROFILE, "tags": ["trasnit"]}, "tags.0"),
    ("recommend", {**PROFILE, "k": 0}, "k"),
    ("recommend", {**PROFILE, "k": c.MAX_K + 1}, "k"),
    ("recommend", {**PROFILE, "k": 2.5}, "k"),
    ("recommend", {**PROFILE, "k": "5"}, "k"),
]

TOOL_FUNCTIONS = {fn.__name__: fn for fn in t.TOOLS}


def _call(tool: str, arguments: dict) -> dict:
    return c.call_tool(tool, TOOL_FUNCTIONS[tool], arguments)


def test_every_schema_is_valid_json_schema():
    assert set(c.INPUT_SCHEMAS) == set(c.OUTPUT_SCHEMAS) == set(TOOL_FUNCTIONS)
    # tool_contracts runs check_schema() on import; this pins the vocabularies.
    assert c.HOUSEHOLDS == ["alone", "with_co_leaser"]
    assert c.HOUSING_PREFERENCES == ["co_living", "own_apartment"]
    assert set(c.TAGS) == {"transit", "social", "quiet", "walkable", "pet_friendly", "co_living"}


def test_well_formed_calls_meet_both_contracts():
    for tool, arguments, status in WELL_FORMED:
        assert c.validate_input(tool, arguments) == [], (tool, arguments)
        result = TOOL_FUNCTIONS[tool](**arguments)
        assert result["status"] == status, (tool, arguments, result.get("status"), result.get("error"))
        assert c.validate_output(tool, result) == [], (tool, arguments, c.validate_output(tool, result))
        assert _call(tool, arguments) == result


def test_malformed_calls_return_structured_invalid_input():
    for tool, arguments, field in MALFORMED:
        result = _call(tool, arguments)
        assert result["status"] == "invalid_input", (tool, arguments, result)
        assert field in [e["field"] for e in result["errors"]], (tool, arguments, result["errors"])
        assert result["error"]
        assert c.validate_output(tool, result) == []


def test_tools_reject_malformed_input_even_without_the_contract_layer():
    """Direct callers (notebooks, the eval harness) get invalid_input too, never an exception."""
    for tool, arguments, _ in MALFORMED:
        if tool == "recommend" and arguments.get("k") == c.MAX_K + 1:
            continue  # MAX_K limits agent calls only; Python callers may rank deeper
        try:
            result = TOOL_FUNCTIONS[tool](**arguments)
        except TypeError:
            continue  # missing or unexpected keyword: Python rejects the call itself
        assert result["status"] == "invalid_input", (tool, arguments, result)


def test_semantically_empty_preferences_are_invalid_input():
    # Passes the schema (walkable is a known tag) but nothing is scorable.
    result = _call("recommend", {**PROFILE, "tags": ["walkable", "pet_friendly"]})
    assert result["status"] == "invalid_input"
    assert "No scored preferences" in result["error"]


def test_no_match_results_have_empty_lists_and_keep_the_echo():
    result = _call("recommend", {**PROFILE, "budget_max": 1})
    assert result["status"] == "no_areas_within_budget"
    assert result["recommendations"] == [] and result["candidate_count"] == 0
    assert result["budget_max"] == 1 and result["active_features"] == ["transit"]
    assert _call("area_stats", {"zip_code": "99999"})["areas"] == []
    none = _call("crowd_themes", {"zip_code": "33186", "theme": "quiet"})
    assert none["snippets"] == [] and none["count"] == 0 and "quiet" not in none["available_themes"]


def test_every_recommendation_explains_its_rank_from_the_data():
    for profile in (PROFILE, CO_LIVING):
        result = _call("recommend", profile)
        assert "cosine similarity" in result["rank_basis"]
        for rec in result["recommendations"]:
            reasons = rec["ranking_reasons"]
            budget = reasons[0]
            assert budget["code"] == "within_budget"
            assert budget["median_rent_usd"] == rec["median_rent_usd"] <= profile["budget_max"]
            assert budget["headroom_usd"] == profile["budget_max"] - rec["median_rent_usd"]
            by_feature = {r["feature"]: r for r in reasons[1:]}
            assert list(by_feature) == result["vector_features"]
            for feature, reason in by_feature.items():
                assert reason["area_score"] == rec["feature_scores"][feature]
                expected = "selected_feature" if feature in result["active_features"] else "unselected_feature"
                assert reason["code"] == expected
            assert rec["zip"] in rec["summary"] and f"#{rec['rank']}" in rec["summary"]


def test_recommend_is_ranked_by_similarity_with_zip_tiebreak():
    recs = _call("recommend", {**PROFILE, "k": c.MAX_K})["recommendations"]
    assert [r["rank"] for r in recs] == list(range(1, len(recs) + 1))
    keys = [(-r["similarity"], r["zip"]) for r in recs]
    assert keys == sorted(keys)


def test_top_coded_rent_is_flagged_in_the_reasons_and_summary():
    recs = t.recommend(**{**PROFILE, "budget_max": 5000}, k=80)["recommendations"]
    capped = [r for r in recs if r["top_coded"]]
    assert capped, "expected at least one ZIP with the ACS rent top code"
    for rec in recs:
        assert c.validate_output("recommend", {**t.recommend(**{**PROFILE, "budget_max": 5000}, k=1),
                                               "recommendations": [rec]}) == []
        budget = rec["ranking_reasons"][0]
        assert budget["rent_is_top_coded"] is (rec["top_coded"] is not None)
    for rec in capped:
        assert "more than $3,500" in rec["summary"] and "may exceed" in rec["summary"]
        assert "$3,501" not in rec["summary"]


def test_fewer_candidates_than_k_returns_all_of_them():
    result = _call("recommend", {**PROFILE, "budget_max": FEW_BUDGET, "k": 5})
    assert result["status"] == "ok"
    assert len(result["recommendations"]) == result["candidate_count"] < 5


def test_output_contract_catches_a_broken_result():
    good = _call("recommend", PROFILE)
    broken = {**good, "recommendations": [{**good["recommendations"][0], "zip": 33130}]}
    assert any(e["field"] == "recommendations.0.zip" for e in c.validate_output("recommend", broken))
    assert c.validate_output("recommend", {**good, "status": "great"})
    empty_but_ok = {**good, "recommendations": []}
    assert c.validate_output("recommend", empty_but_ok)  # "ok" must have at least one match
    themes = _call("crowd_themes", {"zip_code": "33130"})
    entry = next(iter(themes["extracted"]["themes"].values()))[0]
    bad_stance = {**themes, "extracted": {**themes["extracted"],
                  "themes": {"quiet": [{**entry, "stance": "positive"}]}}}
    assert any("stance" in e["field"] for e in c.validate_output("crowd_themes", bad_stance))
    no_extracted = {k: v for k, v in themes.items() if k != "extracted"}
    assert c.validate_output("crowd_themes", no_extracted)
    assert c.validate_output("area_stats", {"status": "ok", "zip_code": None, "count": 1,
                                            "areas": [{"zip": "33127", "area_name": None,
                                                       "stats": {"rent": float("nan")}, "unavailable": []}]})


def test_contract_violation_is_returned_instead_of_the_bad_result():
    result = c.call_tool("ethics", lambda: {"status": "ok", "principles": []}, {})
    assert result["status"] == "contract_violation"
    assert result["tool"] == "ethics" and result["errors"]
    assert "principles" not in result


def test_tool_error_is_returned_instead_of_raising():
    def broken(zip_code=None):
        raise KeyError("median_rent_usd")

    result = c.call_tool("area_stats", broken, {"zip_code": "33130"})
    assert result["status"] == "tool_error" and result["tool"] == "area_stats"
    assert "KeyError" in result["error"]
    assert c.validate_output("area_stats", result) == []


def test_server_publishes_the_contracts():
    async def run():
        async with Client(server) as client:
            for tool in (await client.list_tools()).tools:
                assert tool.input_schema == c.INPUT_SCHEMAS[tool.name], tool.name
                assert tool.output_schema == c.OUTPUT_SCHEMAS[tool.name], tool.name

    asyncio.run(run())


def test_server_returns_structured_results_for_good_bad_and_empty_calls():
    async def run():
        async with Client(server) as client:
            for tool, arguments, status in WELL_FORMED:
                result = await client.call_tool(tool, arguments)
                assert not result.is_error and result.structured_content["status"] == status, (tool, arguments)
            for tool, arguments, field in MALFORMED:
                result = await client.call_tool(tool, arguments)
                content = result.structured_content
                if tool in ("schema", "ethics"):
                    # The SDK drops arguments a tool does not declare before the contract sees them.
                    assert content["status"] == "ok", (tool, arguments)
                    continue
                assert not result.is_error, (tool, arguments, result.content)
                assert content["status"] == "invalid_input", (tool, arguments, content)
                assert field in [e["field"] for e in content["errors"]], (tool, arguments)
            # A list sent as a JSON string (Claude Desktop does this) is parsed first.
            result = await client.call_tool("recommend", {**PROFILE, "tags": '["transit"]'})
            assert result.structured_content["status"] == "ok"

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
