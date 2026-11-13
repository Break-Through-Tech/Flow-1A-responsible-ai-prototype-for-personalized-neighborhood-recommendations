"""Offline checks for the Task #19 agent (no API key or network needed).

Run from the repo root (also collected by pytest if it is installed):

    python scripts/test_agent.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts import agent  # noqa: E402

REC_CALL = {
    "tool": "recommend",
    "args": {},
    "result": {
        "status": "ok",
        "budget_max": 2500.0,
        "recommendations": [
            {"rank": 1, "zip": "33128", "median_rent_usd": 1191.0},
            {"rank": 2, "zip": "33127", "median_rent_usd": 1283.0},
            {"rank": 3, "zip": "33130", "median_rent_usd": 1553.0},
        ],
    },
}


def test_tools_match_the_mcp_server():
    assert [t.__name__ for t in agent.TOOLS] == ["schema", "area_stats", "crowd_themes", "recommend", "ethics"]


def test_grounded_reply_has_no_issues():
    reply = "1. Downtown (33128), median rent $1,191\n2. Wynwood (33127), $1,283\n3. Brickell (33130), $1,553"
    assert agent.grounding_issues(reply, [REC_CALL]) == []


def test_invented_zip_and_rent_are_flagged():
    reply = "Try 33139 at about $1,400."
    issues = agent.grounding_issues(reply, [REC_CALL])
    assert any("33139" in i for i in issues) and any("$1,400" in i for i in issues)


def test_links_are_flagged():
    issues = agent.grounding_issues("See https://example.com/unit-504 for details.", [REC_CALL])
    assert any("link" in i for i in issues)


def test_reordered_recommendations_are_flagged():
    reply = "Brickell (33130) first, then Downtown (33128) and Wynwood (33127)."
    assert any("rank order" in i for i in agent.grounding_issues(reply, [REC_CALL]))


def test_values_the_user_typed_are_allowed():
    reply = "Nothing in 33128 fits a $500 budget."
    no_match = {"tool": "recommend", "args": {}, "result": {"status": "no_areas_within_budget", "recommendations": []}}
    issues = agent.grounding_issues(reply, [no_match], user_text="Budget $500, I like 33128")
    assert issues == []


def test_reply_with_no_tool_call_cannot_state_zips():
    assert agent.grounding_issues("Wynwood is 33127.", []) == ["ZIP 33127 was not returned by any tool"]


def test_wrappers_record_real_tool_output():
    agent._CALLS.clear()
    result = agent.crowd_themes("33130", "transit")
    assert agent._CALLS[-1]["tool"] == "crowd_themes" and agent._CALLS[-1]["result"] is result
    assert result["status"] in {"ok", "no_snippets"}
    bad = agent.recommend(2500, "nobody", "own_apartment", ["transit"])
    assert bad["status"] == "invalid_input"


def test_load_env_does_not_override_existing_values():
    path = Path(tempfile.mkdtemp()) / ".env"
    path.write_text('﻿GEMINI_MODEL="from-file"\n# comment\nFLOW1A_TEST_ONLY=x\n', encoding="utf-8")
    saved = os.environ.get("GEMINI_MODEL")
    os.environ.pop("FLOW1A_TEST_ONLY", None)
    os.environ["GEMINI_MODEL"] = "already-set"
    try:
        agent.load_env(path)
        assert os.environ["GEMINI_MODEL"] == "already-set" and os.environ["FLOW1A_TEST_ONLY"] == "x"
    finally:
        if saved is None:
            os.environ.pop("GEMINI_MODEL", None)
        else:
            os.environ["GEMINI_MODEL"] = saved
        os.environ.pop("FLOW1A_TEST_ONLY", None)


def test_tool_loop_runs_calls_without_args_and_hides_thoughts():
    """A fake Gemini asks for ethics (no arguments) and recommend, then answers."""
    from google import genai
    from google.genai import types

    def reply(*parts):
        return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))])

    answers = [
        reply(
            types.Part(text="private thinking", thought=True),
            types.Part(function_call=types.FunctionCall(id="c1", name="ethics", args=None)),
            types.Part(function_call=types.FunctionCall(
                id="c2", name="recommend",
                args={"budget_max": 2500, "household": "with_co_leaser", "housing_preference": "own_apartment", "tags": ["transit"]},
            )),
        ),
        reply(types.Part(text="Here are the areas.")),
    ]
    saved = agent._CLIENT
    agent._CLIENT = genai.Client(api_key="offline-test")  # never used to reach Google
    try:
        chat = agent.new_chat()
        chat._modules._generate_content = lambda model, contents, config: answers.pop(0)
        turn = agent.ask(chat, "We have $2500 and want transit.")
    finally:
        agent._CLIENT = saved
    assert turn["reply"] == "Here are the areas."
    assert [c["tool"] for c in turn["tool_calls"]] == ["ethics", "recommend"]

    # A later turn that repeats those results without calling a tool is not flagged.
    rec = turn["tool_calls"][1]["result"]
    if rec.get("status") == "ok" and rec["recommendations"]:
        first = rec["recommendations"][0]["zip"]
        answers.append(reply(types.Part(text=f"The top area is still {first}.")))
        chat._modules._generate_content = lambda model, contents, config: answers.pop(0)
        later = agent.ask(chat, "Re-rank those.")
        assert later["tool_calls"] == [] and later["grounding_issues"] == []


def test_conversation_script_is_valid():
    convs = json.loads((_ROOT / "eval" / "agent_conversations.json").read_text(encoding="utf-8"))
    assert len(convs) == 10
    assert all({"id", "title", "turns", "expected"} <= set(c) and c["turns"] for c in convs)


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