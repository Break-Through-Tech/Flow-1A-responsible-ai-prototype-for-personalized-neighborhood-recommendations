"""Offline checks for the Task #23 grounding eval (no API key or network needed).

Claims are checked against real tool output from scripts/mcp_tools.py, with
hallucinations written into the replies by hand.

Run from the repo root (also collected by pytest if it is installed):

    python scripts/test_grounding_eval.py
"""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval import run_grounding_eval as g  # noqa: E402
from scripts import agent, mcp_tools  # noqa: E402
from scripts.test_agent import _fake_turns, _reply  # noqa: E402

REC_ARGS = {"budget_max": 2500, "household": "with_co_leaser", "housing_preference": "own_apartment",
            "tags": ["transit", "walkable"], "k": 5}
USER = "We're moving with a co-leaser, own apartment, budget $2500, transit and walkable."


def _call(tool, **args):
    return {"tool": tool, "args": args, "result": json.loads(json.dumps(getattr(mcp_tools, tool)(**args), default=str))}


REC = _call("recommend", **REC_ARGS)
RECS = REC["result"]["recommendations"]
STATS_33130 = _call("area_stats", zip_code="33130")
STATS_33149 = _call("area_stats", zip_code="33149")
REVIEWS = _call("crowd_themes", zip_code="33130", theme="transit")


def _claims(reply, calls, user=USER, called=True):
    return g.extract_claims(reply, g.Evidence(calls, user), called)


def _bad(reply, calls, user=USER, called=True):
    return [c for c in _claims(reply, calls, user, called) if not c["grounded"]]


def _line(rec):
    return f"{rec['rank']}. {rec['area_name']} (ZIP {rec['zip']}): ${rec['rent_lower_usd']:,} to ${rec['rent_upper_usd']:,} a month"


def _quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


# ---------- claims that should pass ----------

def test_faithful_recommendation_reply_is_fully_grounded():
    reply = "Within your $2,500 budget, in rank order:\n" + "\n".join(_line(r) for r in RECS)
    claims = _claims(reply, [REC])
    assert claims and all(c["grounded"] for c in claims), [c for c in claims if not c["grounded"]]
    kinds = {c["type"] for c in claims}
    assert {"zip", "money", "area_name", "ranking_order"} <= kinds


def test_zcta_areas_are_named_by_zip_only():
    zcta = next(r for r in RECS if r["area_name"].startswith("ZCTA"))
    assert not _bad(f"ZIP {zcta['zip']} has a reference range of ${zcta['rent_lower_usd']:,}.", [REC])


def test_rounding_percent_and_approximate_values():
    stats = STATS_33130["result"]["areas"][0]["stats"]
    reply = (f"Brickell (33130) has about {round(stats['population'], -3):,.0f} residents, "
             f"{stats['moved_different_house_pct'] * 100:.1f}% moved recently, "
             f"and a median home value of ${stats['B25077_001E'] / 1000:.0f}K.")
    assert not _bad(reply, [STATS_33130], user="stats for Brickell", called=False)


def test_values_from_the_user_and_from_earlier_turns_are_allowed():
    assert not _bad("You said your budget is $2,500.", [], called=False)
    record = {"conversation_id": "X", "outcome": "ok", "turns": [
        {"user": USER, "reply": _line(RECS[0]), "tool_calls": [REC]},
        {"user": "Tell me more about the first one.", "reply": _line(RECS[0]), "tool_calls": []},
    ]}
    turns = g.score_conversation(record)
    assert all(c["grounded"] for t in turns for c in t["claims"])


def test_exact_review_quote_is_grounded():
    text = REVIEWS["result"]["snippets"][1]["text"]
    words = text.split()
    reply = f'One reviewer said "{" ".join(words[:8])}..." and "{" ".join(words[-5:])}"'
    claims = _claims(reply, [REVIEWS], user="reviews of 33130", called=False)
    assert [c["type"] for c in claims if c["type"] == "quote"] and all(c["grounded"] for c in claims)


def test_top_code_stated_as_more_than_is_grounded():
    assert not _bad("Median rent in 33149 is more than $3,500 (ACS top code).", [STATS_33149],
                    user="rent in 33149", called=False)


def test_questions_and_refusals_have_no_claims():
    assert _claims("Do you want your own apartment or co-living?", [], called=False) == []
    assert _claims("I can't help filter areas by the ethnicity of residents.", [], called=False) == []


# ---------- hallucinations that must be caught ----------

def test_rent_attached_to_the_wrong_zip():
    a, b = RECS[0], RECS[1]
    bad = _bad(f"{a['area_name']} (ZIP {a['zip']}): ${b['rent_lower_usd']:,} to ${b['rent_upper_usd']:,} a month", [REC])
    assert bad and all(c["type"] == "money" for c in bad)
    assert b["zip"] in bad[0]["reason"] and a["zip"] in bad[0]["reason"]


def test_invented_values_zip_and_area_are_caught():
    bad = _bad("ZIP 33199 in Overtown has a median rent of $1,337 and 48,213 residents.", [REC])
    reasons = {c["type"]: c["reason"] for c in bad}
    assert {"zip", "area_name", "money", "number"} <= set(reasons)


def test_naming_a_zcta_area_is_caught():
    zcta = next(r for r in RECS if r["area_name"].startswith("ZCTA"))
    bad = _bad(f"Hialeah ({zcta['zip']}) is a good fit.", [REC])
    assert [c["type"] for c in bad] == ["area_name"] and "rule 9" in bad[0]["reason"]


def test_wrong_name_for_a_zip_is_caught():
    a, b = RECS[0], RECS[1]
    bad = _bad(f"{b['area_name']} (ZIP {a['zip']}) ranks first.", [REC])
    assert bad and bad[0]["type"] == "area_name" and a["area_name"] in bad[0]["reason"]


def test_top_code_stated_as_exact_is_caught():
    bad = _bad("The median rent in 33149 is $3,501.", [STATS_33149], user="rent in 33149", called=False)
    assert bad and "rule 8" in bad[0]["reason"]


def test_made_up_quote_is_caught():
    bad = _bad('A reviewer wrote "the safest and cleanest neighborhood in Miami".', [REVIEWS],
               user="reviews of 33130", called=False)
    assert [c["type"] for c in bad] == ["quote"]


def test_listing_details_are_caught_unless_the_user_typed_them():
    bad = _bad("Try Unit 4B at 250 NW 24th Street, see https://example.com/listing or call 305-555-0199.", [])
    assert sum(c["type"] == "listing_detail" for c in bad) == 4
    user = "Find me a real listing at 1200 Brickell Ave unit 504."
    assert not _bad("I can't look up 1200 Brickell Ave unit 504; this tool has no real listings.", [], user=user)


def test_reranked_list_is_caught():
    reply = "\n".join(_line(r) for r in reversed(RECS))
    bad = _bad(reply, [REC])
    assert [c["type"] for c in bad] == ["ranking_order"]


def test_outside_place_is_caught_but_echoing_the_user_is_not():
    assert _bad("Key Biscayne is nearby.", [STATS_33149], user="rent in 33149", called=False)
    user = "How does Fort Lauderdale compare to Wynwood?"
    assert not _bad("Fort Lauderdale is not in this data, so I can't compare it.", [], user=user, called=False)


# ---------- scoring ----------

def _record(cid, turns, outcome="ok"):
    return {"conversation_id": cid, "outcome": outcome, "model": "fake-model", "error": None, "turns": turns}


CONVS = [{"id": "A", "title": "a", "turns": ["q"]}, {"id": "B", "title": "b", "turns": ["q"]},
         {"id": "C", "title": "c", "turns": ["q"]}, {"id": "D", "title": "d", "turns": ["q"]}]
GOOD = {"user": USER, "reply": _line(RECS[0]), "tool_calls": [REC]}
BAD = {"user": USER, "reply": "ZIP 33199 is $999 a month.", "tool_calls": [REC]}
NONE = {"user": "hi", "reply": "What is your budget?", "tool_calls": []}


def test_reply_level_rate_skips_replies_without_claims_and_logs_the_prompt():
    records = {"A": _record("A", [GOOD]), "B": _record("B", [BAD, NONE]), "C": _record("C", [], outcome="error")}
    result = g.score(CONVS, records)
    assert (result["grounded_replies"], result["replies_with_claims"]) == (1, 2)
    assert result["grounding_rate"] == 0.5 and not result["passes"]
    assert result["replies_without_claims"] == ["B turn 2"]
    assert result["not_run"] == ["D"] and result["errors"][0]["id"] == "C"
    assert {u["claim"] for u in result["ungrounded"]} == {"33199", "$999"}
    assert all(u["prompt"] == USER and u["conversation_id"] == "B" and u["turn"] == 1 for u in result["ungrounded"])


def test_manual_labels_override_and_add_claims():
    records = {"A": _record("A", [GOOD]), "B": _record("B", [BAD])}
    labels = [
        {"conversation_id": "B", "turn": 1, "claim": "$999", "label": "grounded", "reason": "test override"},
        {"conversation_id": "A", "turn": 1, "claim": "Little Haiti has the best transit", "type": "qualitative",
         "label": "ungrounded", "reason": "superlative not in tool output"},
        {"conversation_id": "A", "turn": 1, "claim": "no such claim", "label": "grounded", "reason": "typo"},
    ]
    result = g.score(CONVS[:2], records, labels)
    assert {u["claim"] for u in result["ungrounded"]} == {"33199", "Little Haiti has the best transit"}
    assert len(result["manual_overrides"]) == 2 and result["unmatched_labels"][0]["claim"] == "no such claim"
    assert result["grounded_replies"] == 0


def test_report_and_results_files_have_every_section():
    tmp = Path(tempfile.mkdtemp())
    raw = tmp / "raw.jsonl"
    for record in (_record("A", [GOOD]), _record("B", [BAD, NONE])):
        g.append_record(raw, record)
    result = g.write_outputs(CONVS[:2], raw, tmp / "r.md", tmp / "r.json", tmp / "none.json")
    text = (tmp / "r.md").read_text(encoding="utf-8")
    for heading in ("Tool grounding rate", "## Claims by type", "## Ungrounded claims", "## Replies", "### B: b"):
        assert heading in text, heading
    saved = json.loads((tmp / "r.json").read_text(encoding="utf-8"))
    assert saved["grounding_rate"] == result["grounding_rate"] == 0.5 and "conversations" not in saved
    assert saved["ungrounded"][0]["prompt"] == USER


# ---------- running (fake Gemini) ----------

def _text(t):
    from google.genai import types

    return _reply(types.Part(text=t))


def _tool(name, args):
    from google.genai import types

    return _reply(types.Part(function_call=types.FunctionCall(id="c1", name=name, args=args)))


def test_runner_keeps_full_tool_results_across_turns_and_resumes():
    conv = {"id": "G1", "title": "t", "turns": [USER, "Why is the first one ranked first?"]}
    chats = [_fake_turns([_tool("recommend", REC_ARGS), _text(_line(RECS[0])), _text(_line(RECS[0]))])]
    raw = Path(tempfile.mkdtemp()) / "raw.jsonl"
    done = _quiet(g.run_conversations, [conv], raw, new_chat=lambda: chats.pop(0))
    record = done[0]
    assert record["outcome"] == "ok" and record["gemini_requests"] == 3 and len(record["turns"]) == 2
    saved = g.load_records(raw)["G1"]
    assert saved["turns"][0]["tool_calls"][0]["result"]["recommendations"][0]["zip"] == RECS[0]["zip"]
    turns = g.score_conversation(saved)
    assert all(c["grounded"] for t in turns for c in t["claims"])
    assert g.select_conversations([conv], g.load_records(raw)) == []


def test_quota_error_is_recorded_and_stops_the_run():
    def broken_chat():
        raise RuntimeError("429 RESOURCE_EXHAUSTED GenerateRequestsPerDay")

    raw = Path(tempfile.mkdtemp()) / "raw.jsonl"
    convs = [{"id": "G1", "turns": ["q"]}, {"id": "G2", "turns": ["q"]}]
    done = _quiet(g.run_conversations, convs, raw, new_chat=broken_chat)
    assert len(done) == 1 and done[0]["outcome"] == "error"
    assert [c["id"] for c in g.select_conversations(convs, g.load_records(raw))] == ["G1", "G2"]


def test_conversation_file_is_valid_and_dry_run_sends_nothing():
    convs = g.load_conversations()
    assert g.conversation_problems(convs) == []
    assert len(convs) >= 15 and sum(len(c["turns"]) for c in convs) >= 20
    assert g.conversation_problems([{"id": "X", "turns": []}, {"id": "X", "turns": ["a"]}]) == [
        "X: turns must be a non-empty list of messages", "X: duplicate id"]

    def must_not_run():
        raise AssertionError("a chat was created during a dry run")

    tmp = Path(tempfile.mkdtemp())
    real, agent.new_chat = agent.new_chat, must_not_run
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            code = g.main(["--dry-run", "--raw", str(tmp / "raw.jsonl"), "--out", str(tmp / "r.md")])
    finally:
        agent.new_chat = real
    assert code == 0 and "Dry run" in out.getvalue() and not list(tmp.iterdir())


def test_manual_labels_file_is_a_list():
    assert isinstance(g.load_labels(), list)


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
