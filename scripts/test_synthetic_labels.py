
"""Tests for synthetic housing option labels (Task #21).

Run with:
    python scripts/test_synthetic_labels.py
"""

import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DATA_PATH = _ROOT / "data" / "area_options.csv"
LABEL = "NOT A REAL LISTING"


def load_options():
    """Read the synthetic demo options."""
    with DATA_PATH.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def test_every_option_has_a_label():
    """Every synthetic option must say it is not real."""
    options = load_options()

    assert options, "No synthetic options found"

    for option in options:
        assert LABEL in option["disclaimer"], option["option_id"]
        assert "synthetic" in option["disclaimer"].lower(), option["option_id"]


def test_option_ids_are_unique():
    """Each synthetic option needs its own ID."""
    options = load_options()
    ids = [option["option_id"] for option in options]

    assert len(ids) == len(set(ids))
    assert all(option_id.startswith("SYN-") for option_id in ids)


def test_disclaimers_are_not_empty():
    """Every option must have a readable disclaimer."""
    for option in load_options():
        assert option["disclaimer"].strip()

def test_ethics_tool_labels_synthetic_options():
    """Check that the ethics tool clearly labels demo options."""
    from scripts import mcp_tools

    result = mcp_tools.ethics()

    demo = next(
        item for item in result["data_limitations"]
        if item["id"] == "synthetic_demo_options"
    )

    assert result["status"] == "ok"
    assert LABEL in demo["description"]
    assert "synthetic" in demo["description"].lower()
    assert "not real apartments" in demo["description"].lower()
    assert "current availability" in demo["description"].lower()

def test_agent_flags_missing_synthetic_label():
    """Check that an unlabeled synthetic option is flagged."""
    from scripts import agent

    calls = [{
        "tool": "demo",
        "args": {},
        "result": {
            "status": "ok",
            "options": [{
                "option_id": "SYN-33132",
                "disclaimer": "NOT A REAL LISTING — synthetic demo only.",
            }],
        },
    }]

    missing = "Option SYN-33132 is available."
    labeled = "Option SYN-33132 — NOT A REAL LISTING — synthetic demo only."

    assert agent.synthetic_label_issues(missing, calls)
    assert agent.synthetic_label_issues(labeled, calls) == []


def test_grounding_checker_flags_missing_label():
    """Check that the main grounding checker catches missing labels."""
    from scripts import agent

    calls = [{
        "tool": "demo",
        "args": {},
        "result": {
            "status": "ok",
            "options": [{
                "option_id": "SYN-33132",
                "disclaimer": "NOT A REAL LISTING — synthetic demo only.",
            }],
        },
    }]

    reply = "Option SYN-33132 is available."

    issues = agent.grounding_issues(reply, calls)

    assert any("missing" in issue.lower() for issue in issues)


def test_each_synthetic_option_needs_a_label():
    """Check that one label does not cover multiple options."""
    from scripts import agent

    calls = [{
        "tool": "demo",
        "args": {},
        "result": {
            "status": "ok",
            "options": [
                {
                    "option_id": "SYN-33132",
                    "disclaimer": "NOT A REAL LISTING — synthetic demo only.",
                },
                {
                    "option_id": "SYN-33139",
                    "disclaimer": "NOT A REAL LISTING — synthetic demo only.",
                },
            ],
        },
    }]

    reply = (
        "SYN-33132 — NOT A REAL LISTING — synthetic demo only.\n"
        "SYN-33139 is available."
    )

    issues = agent.synthetic_label_issues(reply, calls)

    assert len(issues) == 1
    assert "SYN-33139" in issues[0]


def test_real_neighborhoods_do_not_need_synthetic_labels():
    """Normal ZIP recommendations should not be treated as demo listings."""
    from scripts import agent

    calls = [{
        "tool": "recommend",
        "args": {},
        "result": {
            "status": "ok",
            "recommendations": [
                {"rank": 1, "zip": "33128", "area_name": "Downtown"}
            ],
        },
    }]

    reply = "Downtown (33128) is a neighborhood recommendation."

    assert agent.synthetic_label_issues(reply, calls) == []


def test_synthetic_label_edge_cases():
    """Check tricky cases that could cause missing or incorrect labels."""
    from scripts import agent

    calls = [{
        "tool": "demo",
        "args": {},
        "result": {
            "status": "ok",
            "options": [
                {
                    "option_id": "SYN-33132",
                    "disclaimer": "NOT A REAL LISTING — synthetic demo only.",
                },
                {
                    "option_id": "SYN-33139",
                    "disclaimer": "NOT A REAL LISTING — synthetic demo only.",
                },
            ],
        },
    }]

    cases = [
        ("SYN-33132 — NOT A REAL LISTING.", False),
        ("NOT A REAL LISTING — SYN-33132 is a demo.", False),
        ("SYN-33132\nNOT A REAL LISTING — synthetic demo only.", False),
        ("SYN-33132 is available.", True),
        (
            "SYN-33132 — NOT A REAL LISTING.\n"
            "SYN-33139 is available.",
            True,
        ),
        (
            "SYN-33132 — NOT A REAL LISTING.\n"
            "SYN-33132 is available.",
            True,
        ),
        (
            "SYN-33132 — NOT A REAL LISTING. "
            "This apartment is available now.",
            True,
        ),
        (
            "SYN-33132 — NOT A REAL LISTING. "
            "This apartment is not available for rent.",
            False,
        ),
        (
            "SYN-33132 — NOT A REAL LISTING. "
            "Availability is not confirmed.",
            False,
        ),
    ]

    for reply, should_flag in cases:
        issues = agent.synthetic_label_issues(reply, calls)

        assert bool(issues) == should_flag, (
            f"Unexpected result for: {reply}\nIssues: {issues}"
        )

def test_malformed_synthetic_tool_results():
    """Bad tool data should not crash the label checker."""
    from scripts import agent

    bad_calls = [
        None,
        {},
        {"result": None},
        {"result": {"options": None}},
        {"result": {"options": "not a list"}},
        {"result": {"options": [None, 123, {}]}},
        {"result": {"options": [{"option_id": None}]}},
        {"result": {"options": [{"option_id": "SYN-33132"}]}},
    ]

    for call in bad_calls:
        calls = [call]
        issues = agent.synthetic_label_issues(
            "SYN-33132 is available now.",
            calls,
        )

        assert isinstance(issues, list)


def test_synthetic_option_grounding_stress_cases():
    """Check that demo options cannot be shown as real housing."""
    from scripts import agent

    calls = [{
        "tool": "demo",
        "args": {},
        "result": {
            "status": "ok",
            "options": [
                {"option_id": "SYN-33132", "disclaimer": LABEL},
                {"option_id": "SYN-33139", "disclaimer": LABEL},
            ],
        },
    }]

    cases = [
        ("SYN-33132 — NOT A REAL LISTING.", False),
        ("SYN-33132 is a demo apartment.", True),
        ("SYN-33132 — NOT A REAL LISTING.\nSYN-33139 is a demo.", True),
        ("SYN-33132 — NOT A REAL LISTING. SYN-33139 is a demo.", True),
        ("SYN-33132 — NOT A REAL LISTING.\nSYN-33132 is a demo.", True),
        ("SYN-33132 — NOT A REAL LISTING. This apartment is available now.", True),
        ("SYN-33132 — NOT A REAL LISTING. This apartment is not available for rent.", False),
        ("SYN-33132 — NOT A REAL LISTING. This apartment isn't available for rent.", False),
        ("SYN-33132 — NOT A REAL LISTING. You can book this apartment today.", True),
        ("SYN-33132 — NOT A REAL LISTING. Move in tomorrow!", True),
        ("SYN-99999 — NOT A REAL LISTING.", True),
        ("SYN-33132-EXTRA — NOT A REAL LISTING.", True),
        ("I can compare ZIP codes using your preferences.", False),
    ]

    for reply, should_flag in cases:
        issues = agent.synthetic_label_issues(reply, calls)

        assert bool(issues) == should_flag, (
            f"Unexpected result for: {reply}\nIssues: {issues}"
        )


def test_agent_blocks_unsafe_synthetic_reply():
    """Check that the agent replaces an unsafe demo listing response."""
    from google import genai
    from google.genai import types
    from scripts import agent

    # Create a fake Gemini answer.
    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text="SYN-33132 is available now."
                        )
                    ],
                )
            )
        ]
    )

    # Simulate a tool result from an earlier chat turn.
    demo_call = {
        "tool": "demo",
        "args": {},
        "result": {
            "status": "ok",
            "options": [
                {
                    "option_id": "SYN-33132",
                    "disclaimer": "NOT A REAL LISTING — synthetic demo only.",
                }
            ],
        },
    }

    saved_client = agent._CLIENT
    agent._CLIENT = genai.Client(api_key="offline-test")

    try:
        chat = agent.new_chat()

        # Make the fake tool result available to the grounding checker.
        agent._CHAT_CALLS[id(chat)] = [demo_call]

        # Return our fake response without calling Gemini.
        chat._modules._generate_content = (
            lambda model, contents, config: response
        )

        turn = agent.ask(chat, "Tell me about that demo option.")

    finally:
        agent._CHAT_CALLS.pop(id(chat), None)
        agent._CHAT_USER_TEXT.pop(id(chat), None)
        agent._CLIENT = saved_client

    # The unsafe answer should not be shown unchanged.
    assert turn["reply"] != "SYN-33132 is available now."

    # The replacement must clearly explain that it is not real.
    assert "NOT A REAL LISTING" in turn["reply"]
    assert "do not confirm availability" in turn["reply"]

    # Keep the original problem in the grounding report.
    assert any(
        "SYN-33132" in issue
        for issue in turn["grounding_issues"]
    )


def test_agent_keeps_safe_synthetic_reply():
    """A correctly labeled demo response should stay unchanged."""
    from google import genai
    from google.genai import types
    from scripts import agent

    reply = "SYN-33132 — NOT A REAL LISTING — synthetic demo only."

    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=reply)],
                )
            )
        ]
    )

    demo_call = {
        "tool": "demo",
        "args": {},
        "result": {
            "status": "ok",
            "options": [
                {
                    "option_id": "SYN-33132",
                    "disclaimer": "NOT A REAL LISTING — synthetic demo only.",
                }
            ],
        },
    }

    saved_client = agent._CLIENT
    agent._CLIENT = genai.Client(api_key="offline-test")

    try:
        chat = agent.new_chat()
        agent._CHAT_CALLS[id(chat)] = [demo_call]
        chat._modules._generate_content = (
            lambda model, contents, config: response
        )

        turn = agent.ask(chat, "Tell me about that demo option.")

    finally:
        agent._CHAT_CALLS.pop(id(chat), None)
        agent._CHAT_USER_TEXT.pop(id(chat), None)
        agent._CLIENT = saved_client

    # A safe answer should not be replaced.
    assert turn["reply"] == reply
    assert turn["grounding_issues"] == []


def test_agent_keeps_normal_neighborhood_reply():
    """Normal neighborhood answers should not need synthetic labels."""
    from google import genai
    from google.genai import types
    from scripts import agent

    reply = "I can compare neighborhoods using your budget and preferences."

    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=reply)],
                )
            )
        ]
    )

    saved_client = agent._CLIENT
    agent._CLIENT = genai.Client(api_key="offline-test")

    try:
        chat = agent.new_chat()
        chat._modules._generate_content = (
            lambda model, contents, config: response
        )

        turn = agent.ask(chat, "Can you help me compare neighborhoods?")

    finally:
        agent._CHAT_CALLS.pop(id(chat), None)
        agent._CHAT_USER_TEXT.pop(id(chat), None)
        agent._CLIENT = saved_client

    assert turn["reply"] == reply
    assert turn["grounding_issues"] == []


def test_mixed_availability_claims():
    """Check that negative statements do not hide misleading claims."""
    from scripts import agent

    calls = [{
        "tool": "demo",
        "args": {},
        "result": {
            "status": "ok",
            "options": [{
                "option_id": "SYN-33132",
                "disclaimer": LABEL,
            }],
        },
    }]

    cases = [
        ("You can rent this apartment today.", True),
        ("You cannot rent this apartment.", False),
        ("This unit is open for applications.", True),
        ("This unit is not open for applications.", False),
        ("Schedule a viewing tomorrow.", True),
        ("You cannot schedule a viewing.", False),
        (
            "You cannot rent this apartment, but you can book this apartment today.",
            True,
        ),
        (
            "This unit is not open for applications, but schedule a viewing tomorrow.",
            True,
        ),
        (
            "You can book this apartment, but you cannot rent it.",
            True,
        ),
        (
            "You cannot book this apartment, and it is not available for rent.",
            False,
        ),
    ]

    for sentence, should_flag in cases:
        reply = "SYN-33132 — NOT A REAL LISTING. " + sentence
        issues = agent.synthetic_label_issues(reply, calls)

        assert bool(issues) == should_flag, (
            f"Unexpected result for: {sentence}\nIssues: {issues}"
        )


if __name__ == "__main__":
    tests = [
        (name, fn)
        for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    ]

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
