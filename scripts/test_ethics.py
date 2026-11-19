"""Focused checks for the Task #18 ethics policy and MCP routing metadata.

Run from the repository root:

    python scripts/test_ethics.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mcp import Client

from scripts import mcp_tools
from scripts.co_leaser_guardrail import validate_household_housing
from scripts.mcp_server import INSTRUCTIONS, server


def _rules() -> dict[str, dict]:
    return {rule["id"]: rule for rule in mcp_tools.ethics()["rules"]}


def test_required_rule_ids_and_machine_readable_actions():
    result = mcp_tools.ethics()
    assert result["status"] == "ok" and result["policy_version"] == "task18-v1"
    required = {
        "no_demographic_filtering",
        "no_tenant_scoring",
        "no_inferred_housing_preferences",
        "explicit_preferences_only",
    }
    assert required <= set(_rules())
    for rule in _rules().values():
        assert rule["prohibited_actions"] and rule["permitted_alternatives"]


def test_prohibited_behaviors_and_permitted_explicit_preferences_are_covered():
    rules = _rules()
    demographic = " ".join(rules["no_demographic_filtering"]["prohibited_actions"]).lower()
    scoring = " ".join(rules["no_tenant_scoring"]["prohibited_actions"]).lower()
    inference = " ".join(rules["no_inferred_housing_preferences"]["prohibited_actions"]).lower()
    alternatives = " ".join(
        item for rule in rules.values() for item in rule["permitted_alternatives"]
    ).lower()
    assert all(word in demographic for word in ("filter", "rank", "steer", "prox"))
    assert all(
        characteristic in demographic
        for characteristic in (
            "race",
            "ethnicity",
            "national origin",
            "religion",
            "sex",
            "familial status",
            "disability",
        )
    )
    assert all(word in scoring for word in ("suitability", "eligibility", "risk", "worthiness"))
    assert all(word in inference for word in ("identity", "name", "language", "household"))
    assert all(word in alternatives for word in ("budget", "transit", "social", "quiet"))
    unsupported = [
        alternative.lower()
        for rule in rules.values()
        for alternative in rule["permitted_alternatives"]
        if "walkability" in alternative.lower() or "pet-friendly" in alternative.lower()
    ]
    assert unsupported
    assert all("not scored" in alternative for alternative in unsupported)
    assert all("do not offer them as ranking criteria" in alternative for alternative in unsupported)
    assert "amenit" not in alternatives


def test_data_limitations_distinguish_real_sources_from_synthetic_fixtures():
    limits = {item["id"]: item for item in mcp_tools.ethics()["data_limitations"]}
    assert {"real_aggregate_sources", "synthetic_demo_options", "synthetic_evaluation_profiles"} <= set(limits)
    real = limits["real_aggregate_sources"]["description"].lower()
    assert all(source in real for source in ("acs", "zillow", "google local"))
    assert "not synthetic" in real
    profiles = limits["synthetic_evaluation_profiles"]["description"].lower()
    assert "do not establish real-world fairness" in profiles
    combined = " ".join(item["description"] for item in limits.values()).lower()
    assert "available listings" in combined and "individual's experience" in combined


def test_household_never_selects_or_rewrites_housing_preference():
    assert validate_household_housing("alone", "own_apartment") == ("alone", "own_apartment")
    assert validate_household_housing("alone", "co_living") == ("alone", "co_living")
    assert validate_household_housing("with_co_leaser", "own_apartment") == (
        "with_co_leaser", "own_apartment"
    )
    assert validate_household_housing("with_co_leaser", "co_living") == (
        "with_co_leaser", "co_living"
    )


def test_routing_fixtures_send_harmful_and_limit_questions_to_ethics():
    routes = json.loads((_ROOT / "eval" / "agent_routing_prompts.json").read_text())
    by_id = {row["prompt_id"]: row for row in routes}
    assert "explicitly want our own apartment" in by_id["R1"]["user_prompt"]
    assert by_id["R1"]["expected_tool"] == "recommend"
    assert by_id["R1"]["expected_args"]["housing_preference"] == "own_apartment"
    for prompt_id in ("R7", "R8", "R9", "R10"):
        assert by_id[prompt_id]["expected_tool"] == "ethics"
    assert by_id["R7"]["must_not_call"] == ["recommend"]
    assert by_id["R8"]["must_not_call"] == ["recommend"]
    assert by_id["R10"]["must_not_call"] == ["recommend"]

    prohibited = json.loads((_ROOT / "eval" / "prohibited_prompts.json").read_text())
    assert all(row["expected_tool"] == "ethics" for row in prohibited)
    assert all("recommend" in row["must_not_call"] for row in prohibited if row["expected_behavior"] == "refuse")


def test_mcp_exposes_routing_instructions_and_ethics_description():
    lower = INSTRUCTIONS.lower()
    assert all(term in lower for term in ("demographic", "tenant", "inferred housing", "mixed requests"))
    assert "ethics first" in lower and "household and housing preference are independent" in lower

    async def run():
        async with Client(server) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            description = tools["ethics"].description.lower()
            assert all(term in description for term in ("demographic", "tenant", "inferred housing", "synthetic"))

    asyncio.run(run())


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_")]
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
