"""Edge-case checks for the tools the agent calls (Task #25).

Each test states the expected behavior in its docstring. Calls go through
tool_contracts.call_tool, the same path the MCP server and the agent use, so
these check what the agent actually receives.

The agent-level cases at the bottom drive scripts/agent.py with a fake Gemini
chat (no API key, no requests): a Gemini timeout mid-conversation, a tool that
times out, an unstated housing preference, an unknown ZIP and a no-match budget.
How the live model words these replies is checked in the agent transcripts.

Run from the repo root (also collected by pytest if it is installed):

    python scripts/test_edge_cases.py
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts import mcp_tools as t
from scripts import tool_contracts as c
from scripts.recommender import recommend as engine_recommend

PROFILE = {"budget_max": 2500, "household": "alone", "housing_preference": "own_apartment", "tags": ["transit"]}


def _call(tool: str, arguments: dict) -> dict:
    """Call a tool the way the agent does, and check the result meets its contract."""
    result = c.call_tool(tool, getattr(t, tool), arguments)
    assert c.validate_output(tool, result) == [], (tool, arguments, result)
    return result


def _cheapest_rent() -> float:
    """The lowest rent any ZIP can qualify at, read from the engine so a data refresh can't break this."""
    everything = engine_recommend({**PROFILE, "budget_max": 1_000_000}, top_k=10_000)
    return min(r["budget_rent_usd"] for r in everything["recommendations"])


# --- budget below anything / zero ZIPs pass the filter ---------------------------

def test_budget_below_every_zip_returns_an_explicit_no_match():
    """Expected: status no_areas_within_budget, no recommendations, the user's inputs echoed back."""
    out = _call("recommend", {**PROFILE, "budget_max": _cheapest_rent() - 1})
    assert out["status"] == "no_areas_within_budget"
    assert out["recommendations"] == [] and out["candidate_count"] == 0
    assert (out["household"], out["housing_preference"]) == ("alone", "own_apartment")


def test_budget_exactly_at_the_cheapest_rent_qualifies():
    """Expected: the budget filter is inclusive, so a budget equal to a ZIP's rent keeps that ZIP."""
    out = _call("recommend", {**PROFILE, "budget_max": _cheapest_rent()})
    assert out["status"] == "ok" and out["candidate_count"] >= 1


def test_fewer_candidates_than_k_returns_all_of_them_not_padding():
    """Expected: if only a few ZIPs fit, return just those; never pad the list with over-budget ZIPs."""
    out = _call("recommend", {**PROFILE, "budget_max": _cheapest_rent(), "k": 10})
    assert len(out["recommendations"]) == out["candidate_count"] < 10
    assert all(r["budget_rent_usd"] <= out["budget_max"] for r in out["recommendations"])


def test_invalid_budgets_are_rejected_not_guessed():
    """Expected: zero, negative or non-numeric budgets come back as invalid_input naming budget_max."""
    for bad in (0, -500, "2500"):
        out = _call("recommend", {**PROFILE, "budget_max": bad})
        assert out["status"] == "invalid_input", bad
        assert [e["field"] for e in out["errors"]] == ["budget_max"], bad


def test_k_outside_one_to_ten_is_rejected():
    """Expected: k must be 1-10; 0 or 11 is invalid_input naming k."""
    for bad in (0, 11):
        out = _call("recommend", {**PROFILE, "k": bad})
        assert out["status"] == "invalid_input" and out["errors"][0]["field"] == "k", bad


# --- unknown or out-of-scope ZIPs ------------------------------------------------

def test_zips_outside_our_data_are_not_found_in_both_tools():
    """Expected: a made-up ZIP, an out-of-area ZIP (NYC) or a PO-box-only Miami ZIP is not_found
    in area_stats and crowd_themes, never "no reviews" as if the area existed."""
    for zip_code in ("99999", "10001", "33090"):
        stats = _call("area_stats", {"zip_code": zip_code})
        themes = _call("crowd_themes", {"zip_code": zip_code})
        assert stats["status"] == "not_found" and stats["areas"] == [], zip_code
        assert themes["status"] == "not_found" and themes["snippets"] == [], zip_code
        assert themes["extracted"]["count"] == 0, zip_code


def test_a_zip_we_cover_with_no_reviews_is_no_snippets_not_not_found():
    """Expected: one of our ZIPs without reviews is no_snippets, so the agent says
    "no reviews yet" rather than "unknown area"."""
    reviewed = set(t.pd.read_csv(t.CROWD_PATH, dtype={"zip": str})["zip"])
    ours = set(t.pd.read_csv(t.AREA_PATH, dtype={"zip": str})["zip"])
    zip_code = sorted(ours - reviewed)[0]
    assert _call("crowd_themes", {"zip_code": zip_code})["status"] == "no_snippets"
    assert _call("area_stats", {"zip_code": zip_code})["status"] == "ok"


def test_a_reviewed_zip_is_never_hidden_as_not_found():
    """Expected: if reviews exist for a ZIP that isn't in the area data yet (e.g. after the review
    corpus grows), crowd_themes still returns them instead of not_found."""
    folder = Path(tempfile.mkdtemp())
    reviews = t.pd.read_csv(t.CROWD_PATH, dtype={"zip": str})
    extra = reviews.iloc[[0]].assign(zip="33999", snippet_id="X1")
    t.pd.concat([reviews, extra]).to_csv(folder / "crowd.csv", index=False)
    real = t.CROWD_PATH
    t.CROWD_PATH = folder / "crowd.csv"
    try:
        out = _call("crowd_themes", {"zip_code": "33999"})
    finally:
        t.CROWD_PATH = real
    assert out["status"] == "ok" and out["snippets"][0]["snippet_id"] == "X1"


def test_malformed_zips_are_invalid_input_and_padding_is_tolerated():
    """Expected: "1234" or "abcde" is invalid_input naming zip_code; " 33130 " is trimmed and works."""
    for bad in ("1234", "abcde", "331301"):
        for tool in ("area_stats", "crowd_themes"):
            out = _call(tool, {"zip_code": bad})
            assert out["status"] == "invalid_input" and out["errors"][0]["field"] == "zip_code", (tool, bad)
    assert _call("area_stats", {"zip_code": " 33130 "})["zip_code"] == "33130"


def test_unknown_theme_is_invalid_input():
    """Expected: a theme we don't track (e.g. "safety") is rejected, not silently ignored."""
    out = _call("crowd_themes", {"zip_code": "33130", "theme": "safety"})
    assert out["status"] == "invalid_input" and out["errors"][0]["field"] == "theme"


# --- conflicting inputs ------------------------------------------------------------

def test_co_living_tag_with_own_apartment_keeps_the_users_choice():
    """Expected: a co_living tag never overrides housing_preference=own_apartment. The choice is
    echoed unchanged and co_living is reported as an unscored tag."""
    out = _call("recommend", {**PROFILE, "tags": ["co_living", "transit"]})
    assert out["status"] == "ok"
    assert out["housing_preference"] == "own_apartment"
    assert "co_living" in out["unscored_tags"]


def test_nothing_scorable_is_invalid_input_with_the_reason():
    """Expected: if every tag is unscored (only co_living with own_apartment, or walkable/pets),
    the tool refuses to rank and names the unscored tags instead of returning arbitrary ZIPs."""
    for tags in (["co_living"], ["walkable", "pet_friendly"]):
        out = _call("recommend", {**PROFILE, "tags": tags})
        assert out["status"] == "invalid_input", tags
        assert all(tag in out["error"] for tag in tags), out["error"]


def test_household_and_housing_preference_combine_freely():
    """Expected: every household x housing_preference pair is valid and echoed unchanged."""
    for household in ("alone", "with_co_leaser"):
        for housing in ("own_apartment", "co_living"):
            out = _call("recommend", {**PROFILE, "household": household, "housing_preference": housing})
            assert (out["household"], out["housing_preference"]) == (household, housing)


def test_duplicate_tags_count_once():
    """Expected: repeating a tag doesn't change the ranking."""
    once = _call("recommend", PROFILE)
    twice = _call("recommend", {**PROFILE, "tags": ["transit", "transit"]})
    assert [r["zip"] for r in once["recommendations"]] == [r["zip"] for r in twice["recommendations"]]


def test_empty_or_unknown_tags_are_rejected():
    """Expected: no tags, or a tag we don't know, is invalid_input naming the tags field."""
    assert _call("recommend", {**PROFILE, "tags": []})["errors"][0]["field"] == "tags"
    assert _call("recommend", {**PROFILE, "tags": ["nightlife"]})["errors"][0]["field"].startswith("tags")


# --- missing household or housing_preference ---------------------------------------

def test_missing_household_or_housing_preference_is_never_filled_in():
    """Expected: a missing household or housing_preference is invalid_input naming the missing
    field. The tool never picks a default, so the agent has to ask the user."""
    for missing in ("household", "housing_preference"):
        args = {k: v for k, v in PROFILE.items() if k != missing}
        out = _call("recommend", args)
        assert out["status"] == "invalid_input" and missing in out["error"], missing


def test_unknown_household_value_is_rejected():
    """Expected: a household outside alone / with_co_leaser (e.g. "family") is invalid_input."""
    out = _call("recommend", {**PROFILE, "household": "family"})
    assert out["status"] == "invalid_input" and out["errors"][0]["field"] == "household"


# --- a tool failing mid-conversation ---------------------------------------------------

def test_a_tool_that_crashes_or_times_out_returns_tool_error():
    """Expected: if a tool raises (including a timeout), the agent gets status tool_error and a
    reason, never a traceback or a partial result. The agent-level Gemini timeout is tested
    with the agent once Task #19 is on main."""
    def times_out(**_):
        raise TimeoutError("data source did not respond")

    started = time.monotonic()
    out = c.call_tool("recommend", times_out, PROFILE)
    assert out["status"] == "tool_error" and "TimeoutError" in out["error"]
    assert c.validate_output("recommend", out) == []
    assert time.monotonic() - started < 5


# --- agent level, with a fake Gemini chat ------------------------------------------------

import json  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import contextlib  # noqa: E402
import io  # noqa: E402

import httpx  # noqa: E402

from scripts import agent  # noqa: E402


def _reply(text: str):
    """A Gemini response with visible text and no tool calls."""
    part = SimpleNamespace(text=text, thought=False)
    return SimpleNamespace(function_calls=None, candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])


def _wants(name: str, args: dict):
    """A Gemini response asking to call one tool."""
    call = SimpleNamespace(name=name, args=args, id=f"call-{name}")
    return SimpleNamespace(function_calls=[call], candidates=[SimpleNamespace(content=SimpleNamespace(parts=[]))])


class FakeChat:
    """Plays back a script: each item is a response to return, or an exception to raise."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.sent = []
        # The agent remembers each chat by id(); new_chat() clears that memory, so do the same
        # here, or a reused id could carry an earlier test's messages into this one.
        agent._CHAT_CALLS[id(self)] = []
        agent._CHAT_USER_TEXT[id(self)] = []

    def send_message(self, message):
        self.sent.append(message)
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


def _tool_results(message) -> list[dict]:
    """The tool results the agent sent back to Gemini in one message."""
    return [part.function_response.response["result"] for part in message]


class _NoSleep:
    """Replace time.sleep in the agent so retries don't actually wait, and hide its progress prints."""

    def __enter__(self):
        self.waits, self.real = [], agent.time.sleep
        agent.time.sleep = self.waits.append
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        return self

    def __exit__(self, *exc):
        self.quiet.__exit__(*exc)
        agent.time.sleep = self.real


def _timeout():
    return httpx.ReadTimeout("Gemini did not answer in time")


def test_agent_retries_a_gemini_timeout_and_then_answers():
    """Expected: a slow Gemini request is retried after a pause, and the user still gets the answer."""
    chat = FakeChat(_timeout(), _reply("Here is what I found."))
    with _NoSleep() as s:
        turn = agent.ask(chat, "what data do you have?")
    assert turn["reply"] == "Here is what I found."
    assert s.waits == [agent.RETRY_WAITS[0]]


def test_gemini_timing_out_mid_conversation_gives_no_partial_answer():
    """Expected: if Gemini times out after a tool already ran (mid-conversation), the agent retries
    each wait in RETRY_WAITS, then raises instead of showing a half-finished reply, and resets the
    housing-preference context so the next message starts clean."""
    stuck = [_timeout() for _ in range(len(agent.RETRY_WAITS) + 1)]
    chat = FakeChat(_wants("ethics", {}), *stuck)
    with _NoSleep() as s:
        try:
            agent.ask(chat, "what are your rules?")
        except httpx.TimeoutException:
            pass
        else:
            raise AssertionError("a Gemini that never answers should surface as an error, not a reply")
    assert s.waits == list(agent.RETRY_WAITS)
    assert len(chat.sent) == 1 + len(stuck)  # the question, then the tool result sent each attempt
    assert agent._USER_TEXT is None


def test_scripted_run_records_a_timeout_and_moves_on():
    """Expected: in a test-conversation run, a conversation that times out is marked "Gemini error,
    rerun this one" in the transcript, and the run continues with the next conversation."""
    chats = iter([FakeChat(*[_timeout() for _ in range(len(agent.RETRY_WAITS) + 1)]),
                  FakeChat(_reply("Second conversation answered."))])
    real_new_chat = agent.new_chat
    agent.new_chat = lambda: next(chats)
    folder = Path(tempfile.mkdtemp())
    script = folder / "convs.json"
    script.write_text(json.dumps([
        {"id": "T1", "title": "times out", "expected": "error recorded", "turns": ["hello"]},
        {"id": "T2", "title": "works", "expected": "answers", "turns": ["hello again"]},
    ]))
    try:
        with _NoSleep():
            agent.run_script(script, folder / "out.md")
    finally:
        agent.new_chat = real_new_chat
    transcript = (folder / "out.md").read_text()
    assert "Gemini error" in transcript and "Rerun this one" in transcript
    assert "Second conversation answered." in transcript


def test_a_tool_that_times_out_goes_back_to_gemini_as_tool_error():
    """Expected: if a tool times out while the agent is answering, Gemini receives status tool_error
    (so it can say the lookup failed) and the conversation continues."""
    real = t.area_stats
    t.area_stats = lambda *a, **k: (_ for _ in ()).throw(TimeoutError("census lookup timed out"))
    chat = FakeChat(_wants("area_stats", {"zip_code": "33130"}), _reply("That lookup failed, try again soon."))
    try:
        turn = agent.ask(chat, "stats for 33130?")
    finally:
        t.area_stats = real
    sent = _tool_results(chat.sent[1])
    assert sent[0]["status"] == "tool_error" and "TimeoutError" in sent[0]["error"]
    assert turn["reply"] == "That lookup failed, try again soon."


def test_agent_cannot_recommend_with_a_housing_preference_the_user_never_gave():
    """Expected: if Gemini guesses own_apartment from "co-leaser", recommend is blocked with
    invalid_input telling it to ask the user, and the recommender never runs."""
    ran = []
    real = t.recommend
    t.recommend = lambda *a, **k: ran.append(1) or real(*a, **k)
    guess = _wants("recommend", {"budget_max": 2500, "household": "with_co_leaser",
                                 "housing_preference": "own_apartment", "tags": ["transit"]})
    chat = FakeChat(guess, _reply("Do you want your own apartment or co-living?"))
    try:
        agent.ask(chat, "Moving with my co-leaser, budget $2500, we like transit.")
    finally:
        t.recommend = real
    sent = _tool_results(chat.sent[1])
    assert sent[0]["status"] == "invalid_input" and "not stated" in sent[0]["error"]
    assert ran == []


def test_agent_gets_not_found_for_a_zip_outside_our_data():
    """Expected: asking about an out-of-area ZIP gives Gemini not_found, and a reply that then names
    a ZIP no tool returned is flagged by the grounding check."""
    chat = FakeChat(_wants("crowd_themes", {"zip_code": "10001"}), _reply("Try 33130 instead, it's great."))
    turn = agent.ask(chat, "what do people say about 10001?")
    assert _tool_results(chat.sent[1])[0]["status"] == "not_found"
    assert any("33130" in issue for issue in turn["grounding_issues"])


def test_agent_no_match_budget_reaches_gemini_and_invented_zips_are_flagged():
    """Expected: a budget below every ZIP reaches Gemini as no_areas_within_budget with an empty list,
    and any ZIP the reply makes up anyway is flagged."""
    ask_for = _wants("recommend", {"budget_max": 500, "household": "alone",
                                   "housing_preference": "own_apartment", "tags": ["transit"]})
    chat = FakeChat(ask_for, _reply("Nothing fits $500, but 33150 is close."))
    turn = agent.ask(chat, "I want my own apartment, budget $500, transit please.")
    result = _tool_results(chat.sent[1])[0]
    assert result["status"] == "no_areas_within_budget" and result["recommendations"] == []
    assert any("33150" in issue for issue in turn["grounding_issues"])


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
