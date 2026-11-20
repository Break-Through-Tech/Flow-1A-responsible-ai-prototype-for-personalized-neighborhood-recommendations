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
    assert bad["status"] == "invalid_input" and bad["errors"]  # field errors come from tool_contracts


def test_recommend_returns_rent_range_through_the_contract():
    """After #43, recommend gives a rent range and budget position, and passes the contract."""
    result = agent.recommend(2500, "alone", "own_apartment", ["transit"])
    assert result["status"] == "ok"
    for rec in result["recommendations"]:
        assert rec["rent_lower_usd"] <= rec["rent_upper_usd"]
        assert rec["budget_position"] in {"within_reference_range", "above_upper_estimate"}
        assert "median_rent_usd" not in rec


def test_prompt_describes_rent_as_a_range():
    """Rule 3 must describe the range and forbid treating the lower bound as affordable."""
    prompt = agent.SYSTEM_PROMPT
    assert "rent_lower_usd" in prompt and "rent_upper_usd" in prompt and "budget_position" in prompt
    assert "never the lower bound alone" in prompt and "never say the user can afford" in prompt
    assert "Rents are ZIP-level median rents" not in prompt


def test_ethics_description_matches_the_mcp_server():
    """After #50, the ethics description Gemini reads must match scripts/mcp_server.py."""
    import inspect

    from scripts import mcp_server

    assert inspect.getdoc(agent.ethics) == inspect.getdoc(mcp_server.ethics)


def test_prompt_has_ethics_first_routing():
    """Rule 14 must carry #50's routing: ethics first for mixed requests, never infer missing inputs."""
    prompt = agent.SYSTEM_PROMPT
    assert "For mixed requests, call ethics first, refuse the prohibited portion" in prompt
    assert "every required recommend input is present" in prompt
    assert "tenant screening or scoring, inferred housing preferences" in prompt


def test_ethics_result_has_the_new_policy_shape():
    """The real ethics tool (from #50) passes the contract and has rules and routing."""
    result = agent.ethics()
    assert result["status"] == "ok"
    assert result["rules"] and result["routing"]["mixed_request_action"]


def test_prompt_forbids_a_re_sorted_list():
    """Rule 2: asked to sort by rent, the agent keeps rank order instead of listing a re-sorted copy."""
    assert "do not give a re-sorted list: keep the areas in rank order" in agent.SYSTEM_PROMPT


def _fake_turns(chat_answers):
    """A chat whose Gemini replies are scripted (no request reaches Google)."""
    from google import genai

    saved = agent._CLIENT
    agent._CLIENT = genai.Client(api_key="offline-test")  # never used to reach Google
    chat = agent.new_chat()
    agent._CLIENT = saved
    chat._modules._generate_content = lambda model, contents, config: chat_answers.pop(0)
    return chat


def _reply(*parts):
    from google.genai import types

    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))])


def _recommend_call(housing):
    from google.genai import types

    return types.Part(function_call=types.FunctionCall(
        id="r1", name="recommend",
        args={"budget_max": 2500, "household": "with_co_leaser", "housing_preference": housing, "tags": ["social"]},
    ))


def test_inferred_housing_preference_is_blocked():
    """C8 on lite: user never said own apartment, Gemini guessed it. recommend must not run."""
    from google.genai import types
    from scripts import mcp_tools

    real = mcp_tools.recommend

    def must_not_run(*args, **kwargs):
        raise AssertionError("recommend ran without a stated housing preference")

    mcp_tools.recommend = must_not_run
    try:
        chat = _fake_turns([_reply(_recommend_call("own_apartment")), _reply(types.Part(text="Own apartment or co-living?"))])
        turn = agent.ask(chat, "We're a couple with a co-leaser, budget $2500, we like social areas.")
    finally:
        mcp_tools.recommend = real
    result = turn["tool_calls"][0]["result"]
    assert result["status"] == "invalid_input" and "not stated" in result["error"]


def test_stated_housing_preference_is_allowed_from_an_earlier_turn():
    """Once the user says it (even in an earlier message), recommend runs normally."""
    from google.genai import types

    chat = _fake_turns([
        _reply(types.Part(text="Own apartment or co-living?")),
        _reply(_recommend_call("own_apartment")),
        _reply(types.Part(text="Here are the areas.")),
    ])
    agent.ask(chat, "We're a couple with a co-leaser, budget $2500, we like social areas.")
    turn = agent.ask(chat, "We want our own apartment.")
    assert turn["tool_calls"][0]["result"]["status"] == "ok"


def test_housing_check_is_off_outside_a_chat():
    """Direct calls (tests, scripts) are not blocked, and the check resets after a chat turn."""
    assert agent._USER_TEXT is None
    assert agent.recommend(2500, "alone", "own_apartment", ["transit"])["status"] == "ok"


def test_negated_or_unrelated_housing_words_do_not_count():
    """Review on #47: "my own budget" or "not co-living" must not count as stating that option."""
    cases = [
        ("my own budget is $2,000", "own_apartment", False),
        ("I don't want my own apartment, I want co-living", "own_apartment", False),
        ("I don't want my own apartment, I want co-living", "co_living", True),
        ("own apartment\u2026 not a co-living facility", "co_living", False),
        ("own apartment\u2026 not a co-living facility", "own_apartment", True),
        ("We want our own apartment, not co-living.", "own_apartment", True),
        ("We want our own apartment, not co-living.", "co_living", False),
    ]
    try:
        for text, housing, allowed in cases:
            agent._USER_TEXT = text
            assert (agent._housing_not_stated(housing) is None) == allowed, (text, housing)
    finally:
        agent._USER_TEXT = None


def test_prompt_lets_mixed_requests_continue():
    """Rule 13 must not block rule 14: a mixed request with every input continues after the refusal."""
    prompt = agent.SYSTEM_PROMPT
    assert "If the whole request is prohibited, do not call recommend" in prompt
    assert "follow rule 14 for mixed requests" in prompt


def test_tool_crash_becomes_tool_error():
    """A tool that raises (e.g. a KeyError after a data change) must not end the chat."""
    from scripts import mcp_tools

    real = mcp_tools.crowd_themes
    mcp_tools.crowd_themes = lambda zip_code, theme=None: {}["missing_column"]
    try:
        result = agent.crowd_themes("33130")
    finally:
        mcp_tools.crowd_themes = real
    assert result["status"] == "tool_error" and "KeyError" in result["error"]


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
        turn = agent.ask(chat, "We have $2500, want our own apartment and transit.")
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


def test_broken_tool_result_becomes_contract_violation():
    """A result that breaks its output contract never reaches Gemini."""
    from scripts import mcp_tools

    real = mcp_tools.ethics
    mcp_tools.ethics = lambda: {"status": "ok"}  # missing every required field
    try:
        result = agent.ethics()
    finally:
        mcp_tools.ethics = real
    assert result["status"] == "contract_violation" and result["errors"]
    assert "principles" not in result


def test_whole_number_k_sent_as_float_is_accepted():
    """Gemini can send k as 5.0; the contract wants an integer."""
    result = agent.recommend(2500, "alone", "own_apartment", ["transit"], k=5.0)
    assert result["status"] == "ok" and len(result["recommendations"]) == 5
    assert agent._CALLS[-1]["args"]["k"] == 5 and isinstance(agent._CALLS[-1]["args"]["k"], int)


def test_unexpected_error_in_a_wrapper_becomes_tool_error():
    """Backstop in _run_tool: even if something outside the tool fails, the chat gets a status."""
    from scripts import tool_contracts

    real = tool_contracts.call_tool

    def broken(*args, **kwargs):
        raise RuntimeError("simulated failure outside the tool")

    tool_contracts.call_tool = broken
    try:
        result = agent._run_tool("ethics", {})
    finally:
        tool_contracts.call_tool = real
    assert result["status"] == "tool_error" and "RuntimeError" in result["error"]


def test_requests_have_a_time_limit():
    """Every Gemini request has a timeout and no hidden library retries."""
    from google import genai

    saved = agent._CLIENT
    agent._CLIENT = genai.Client(api_key="offline-test")  # never used to reach Google
    try:
        chat = agent.new_chat()
    finally:
        agent._CLIENT = saved
    options = chat._config.http_options
    assert options.timeout == agent.REQUEST_TIMEOUT_MS
    assert options.retry_options.attempts == 1


def test_slow_request_is_retried_then_succeeds():
    """A timeout is retried with a visible message instead of hanging."""
    import httpx

    class SlowThenOk:
        calls = 0

        def send_message(self, message):
            SlowThenOk.calls += 1
            if SlowThenOk.calls < 3:
                raise httpx.ReadTimeout("simulated slow Gemini")
            return "ok"

    real_sleep = agent.time.sleep
    agent.time.sleep = lambda seconds: None
    try:
        assert agent._send(SlowThenOk(), "hi") == "ok"
    finally:
        agent.time.sleep = real_sleep
    assert SlowThenOk.calls == 3


def test_chat_continues_after_a_tool_crash():
    """A fake Gemini calls a crashing tool, then answers; the turn still completes."""
    from google import genai
    from google.genai import types
    from scripts import mcp_tools

    def reply(*parts):
        return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))])

    answers = [
        reply(types.Part(function_call=types.FunctionCall(id="c1", name="crowd_themes", args={"zip_code": "33130"}))),
        reply(types.Part(text="That tool failed, so I can't show reviews right now.")),
    ]
    saved_client, real = agent._CLIENT, mcp_tools.crowd_themes
    agent._CLIENT = genai.Client(api_key="offline-test")  # never used to reach Google
    mcp_tools.crowd_themes = lambda zip_code, theme=None: {}["missing_column"]
    try:
        chat = agent.new_chat()
        chat._modules._generate_content = lambda model, contents, config: answers.pop(0)
        turn = agent.ask(chat, "What do people say about 33130?")
    finally:
        agent._CLIENT, mcp_tools.crowd_themes = saved_client, real
    assert turn["reply"].startswith("That tool failed")
    assert turn["tool_calls"][0]["result"]["status"] == "tool_error"


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