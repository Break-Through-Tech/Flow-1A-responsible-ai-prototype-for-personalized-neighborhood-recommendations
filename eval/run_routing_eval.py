"""Layer 2 routing eval (Task #22): does the agent call the right tool?

Metric definitions follow EVAL_FRAMEWORK.md (Layer 2):

    Tool selection accuracy   % scored prompts where the expected tool was called
                              (and no must_not_call tool was, and ethics came before recommend)
    Tool argument accuracy    % recommend prompts with expected_args whose first recommend
                              call has the expected budget, household, housing preference and tags

Each prompt runs in a fresh chat through scripts/agent.py, so it uses real
Gemini requests (about 2 per prompt; the free tier allows 20 a day). Every
result is appended to eval/results/routing_raw.jsonl as soon as it finishes,
and a rerun skips prompts that already have a result, so a run can be split
across days. A prompt whose latest result is an error is run again.

Run from the repo root:

    python eval/run_routing_eval.py                 # run what is left, then write the report
    python eval/run_routing_eval.py --limit 5       # at most 5 prompts this time
    python eval/run_routing_eval.py --only R4,R7    # just these prompts
    python eval/run_routing_eval.py --only R4 --fresh   # run R4 again even if it is done
    python eval/run_routing_eval.py --report-only   # re-score the saved results, no requests
    python eval/run_routing_eval.py --dry-run       # check prompts, print the request estimate, no requests

--fresh does not delete anything: the new result is appended and the latest
result for each prompt is the one scored.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts import agent  # noqa: E402

PROMPTS_PATH = _ROOT / "eval" / "agent_routing_prompts.json"
RAW_PATH = _ROOT / "eval" / "results" / "routing_raw.jsonl"
REPORT_PATH = _ROOT / "eval" / "results" / "routing_eval.md"

TOOL_TARGET = 0.90
ARGS_TARGET = 0.85
ROUND_CAP_MARK = "[stopped: too many tool calls"
IGNORED_ARGS = {"k"}

# Gemini requests per prompt: the first message, plus one per round of tool calls.
LIKELY_REQUESTS = 2   # one tool round, then the answer
HIGH_REQUESTS = 3     # ethics, then recommend, then the answer
MAX_REQUESTS = 1 + agent.MAX_TOOL_ROUNDS  # before retries


# ---------- scoring (pure functions, no API) ----------

def called_tools(calls: list[dict]) -> list[str]:
    """Tool names in the order Gemini asked for them."""
    return [c["tool"] for c in calls]


def tool_miss_reason(prompt: dict, calls: list[dict]) -> str | None:
    """Why the routing is wrong, or None if it is right.

    A call counts even if it came back invalid_input (for example recommend
    blocked by the housing-preference check): the model still chose that tool.
    """
    names = called_tools(calls)
    expected = prompt["expected_tool"]
    if expected not in names:
        return f"{expected} not called"
    forbidden = [t for t in prompt.get("must_not_call", []) if t in names]
    if forbidden:
        return "called must_not_call: " + ", ".join(forbidden)
    if "ethics" in names and "recommend" in names and names.index("ethics") > names.index("recommend"):
        return "ethics called after recommend"
    return None


def tool_match(prompt: dict, calls: list[dict]) -> bool:
    return tool_miss_reason(prompt, calls) is None


def _same(got: Any, want: Any) -> bool:
    """Equal, with numbers compared by value (2500 == 2500.0)."""
    numbers = (int, float)
    if isinstance(got, numbers) and isinstance(want, numbers) and not isinstance(got, bool) and not isinstance(want, bool):
        return float(got) == float(want)
    return got == want


def args_mismatches(prompt: dict, calls: list[dict]) -> list[str] | None:
    """Expected args that the first call to the expected tool got wrong.

    None if the prompt has no expected_args. tags_contains means args["tags"]
    holds every listed tag (extra tags are fine). Extra args and k are ignored.
    """
    expected = prompt.get("expected_args") or {}
    if not expected:
        return None
    first = next((c for c in calls if c["tool"] == prompt["expected_tool"]), None)
    if first is None:
        return [f"{prompt['expected_tool']} not called"]
    args = first.get("args") or {}
    wrong = []
    for key, want in expected.items():
        if key in IGNORED_ARGS:
            continue
        if key == "tags_contains":
            tags = args.get("tags")
            tags = list(tags) if isinstance(tags, (list, tuple)) else []
            missing = [t for t in want if t not in tags]
            if missing:
                wrong.append(f"tags missing {missing} (got {args.get('tags')!r})")
        elif key not in args:
            wrong.append(f"{key} missing")
        elif not _same(args[key], want):
            wrong.append(f"{key}={args[key]!r}, expected {want!r}")
    return wrong


def args_match(prompt: dict, calls: list[dict]) -> bool | None:
    """True/False for prompts with expected_args, None for prompts without."""
    wrong = args_mismatches(prompt, calls)
    return None if wrong is None else not wrong


def _ratio(hits: int, total: int) -> float | None:
    return hits / total if total else None


def score(prompts: list[dict], records: dict[str, dict]) -> dict:
    """Score the latest record of each prompt. Error and not-run prompts are left out of both metrics."""
    rows = []
    for prompt in prompts:
        pid = prompt["prompt_id"]
        record = records.get(pid)
        row = {
            "prompt_id": pid,
            "expected_tool": prompt["expected_tool"],
            "must_not_call": prompt.get("must_not_call", []),
            "calls": [],
            "outcome": "not_run",
            "tool_ok": None,
            "tool_reason": None,
            "args_ok": None,
            "args_wrong": None,
            "error": None,
        }
        if record is not None:
            row["outcome"] = record["outcome"]
            row["calls"] = record.get("calls", [])
            row["error"] = record.get("error")
            if record["outcome"] != "error":
                row["tool_reason"] = tool_miss_reason(prompt, row["calls"])
                row["tool_ok"] = row["tool_reason"] is None
                row["args_wrong"] = args_mismatches(prompt, row["calls"])
                row["args_ok"] = None if row["args_wrong"] is None else not row["args_wrong"]
        row["counts_for_args"] = prompt["expected_tool"] == "recommend" and bool(prompt.get("expected_args"))
        rows.append(row)

    scored = [r for r in rows if r["outcome"] not in {"error", "not_run"}]
    args_rows = [r for r in scored if r["counts_for_args"]]
    tool_hits = sum(r["tool_ok"] for r in scored)
    args_hits = sum(bool(r["args_ok"]) for r in args_rows)

    per_tool: dict[str, dict] = {}
    for r in scored:
        entry = per_tool.setdefault(r["expected_tool"], {"prompts": 0, "correct": 0})
        entry["prompts"] += 1
        entry["correct"] += int(r["tool_ok"])

    return {
        "rows": rows,
        "scored": len(scored),
        "tool_hits": tool_hits,
        "tool_accuracy": _ratio(tool_hits, len(scored)),
        "args_scored": len(args_rows),
        "args_hits": args_hits,
        "args_accuracy": _ratio(args_hits, len(args_rows)),
        "per_tool": per_tool,
        "confusion": [
            {"prompt_id": r["prompt_id"], "expected": r["expected_tool"],
             "called": called_tools(r["calls"]), "reason": r["tool_reason"]}
            for r in scored if not r["tool_ok"]
        ],
        "args_misses": [
            {"prompt_id": r["prompt_id"], "wrong": r["args_wrong"]}
            for r in scored if r["args_ok"] is False
        ],
        "errors": [{"prompt_id": r["prompt_id"], "error": r["error"]} for r in rows if r["outcome"] == "error"],
        "not_run": [r["prompt_id"] for r in rows if r["outcome"] == "not_run"],
    }


# ---------- report ----------

def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def _calls_text(calls: list[dict]) -> str:
    if not calls:
        return "none"
    parts = []
    for c in calls:
        status = c.get("status")
        parts.append(c["tool"] if status in (None, "ok") else f"{c['tool']} ({status})")
    return " → ".join(parts)


def _yes_no(value: bool | None) -> str:
    return "–" if value is None else ("yes" if value else "**no**")


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_report(result: dict, records: dict[str, dict], now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    models = sorted({r.get("model", "?") for r in records.values()}) or ["(none run)"]
    total = len(result["rows"])

    def met(value, target):
        return "n/a" if value is None else ("yes" if value >= target else "**no**")

    lines = [
        "# Layer 2 routing eval (Task #22)",
        "",
        f"Report written: {now:%Y-%m-%d %H:%M} UTC. Model: {', '.join(f'`{m}`' for m in models)}.",
        "",
        f"Prompts: {total} in `eval/agent_routing_prompts.json`; {result['scored']} scored, "
        f"{len(result['errors'])} error, {len(result['not_run'])} not run yet. "
        "Raw results: `eval/results/routing_raw.jsonl` (latest result per prompt is scored).",
        "",
        "| Metric | Result | Target | Met |",
        "|--------|--------|--------|-----|",
        f"| Tool selection accuracy | {result['tool_hits']}/{result['scored']} ({_pct(result['tool_accuracy'])}) "
        f"| ≥ {TOOL_TARGET:.0%} | {met(result['tool_accuracy'], TOOL_TARGET)} |",
        f"| Tool argument accuracy (`recommend`) | {result['args_hits']}/{result['args_scored']} "
        f"({_pct(result['args_accuracy'])}) | ≥ {ARGS_TARGET:.0%} | {met(result['args_accuracy'], ARGS_TARGET)} |",
        "",
        "A tool call counts even if it came back `invalid_input` (the model still chose it). "
        "Error and not-run prompts are left out of both metrics.",
        "",
        "## Per expected tool",
        "",
        "| Expected tool | Prompts scored | Correct |",
        "|---------------|----------------|---------|",
    ]
    for tool, entry in sorted(result["per_tool"].items()):
        lines.append(f"| `{tool}` | {entry['prompts']} | {entry['correct']} |")
    if not result["per_tool"]:
        lines.append("| – | 0 | 0 |")

    lines += ["", "## Routing misses (confusion)", ""]
    if result["confusion"]:
        lines += ["| Prompt | Expected | Called | Why |", "|--------|----------|--------|-----|"]
        for m in result["confusion"]:
            called = " → ".join(m["called"]) or "none"
            lines.append(f"| {m['prompt_id']} | `{m['expected']}` | {called} | {_cell(m['reason'])} |")
    else:
        lines.append("None.")

    lines += ["", "## Argument misses", ""]
    if result["args_misses"]:
        lines += ["| Prompt | Wrong |", "|--------|-------|"]
        for m in result["args_misses"]:
            lines.append(f"| {m['prompt_id']} | {_cell('; '.join(m['wrong']))} |")
    else:
        lines.append("None.")

    if result["errors"]:
        lines += ["", "## Errors (not scored, rerun these)", "", "| Prompt | Error |", "|--------|-------|"]
        for e in result["errors"]:
            lines.append(f"| {e['prompt_id']} | {_cell(e['error'])[:300]} |")

    lines += [
        "",
        "## Per prompt",
        "",
        "| Prompt | Expected | Called | Tool ok | Args ok | Outcome |",
        "|--------|----------|--------|---------|---------|---------|",
    ]
    for r in result["rows"]:
        expected = f"`{r['expected_tool']}`"
        if r["must_not_call"]:
            expected += " (not " + ", ".join(r["must_not_call"]) + ")"
        lines.append(
            f"| {r['prompt_id']} | {expected} | {_cell(_calls_text(r['calls']))} | "
            f"{_yes_no(r['tool_ok'])} | {_yes_no(r['args_ok'])} | {r['outcome']} |"
        )
    lines.append("")
    return "\n".join(lines)


# ---------- running prompts (uses Gemini) ----------

def load_prompts(path: Path = PROMPTS_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def prompt_problems(prompts: list[dict]) -> list[str]:
    """Fixture mistakes that would make a prompt unscorable (checked before any request)."""
    tools = {fn.__name__ for fn in agent.TOOLS}
    problems, seen = [], set()
    for i, p in enumerate(prompts):
        pid = p.get("prompt_id", f"#{i}")
        for key in ("prompt_id", "user_prompt", "expected_tool"):
            if not p.get(key):
                problems.append(f"{pid}: missing {key}")
        if pid in seen:
            problems.append(f"{pid}: duplicate prompt_id")
        seen.add(pid)
        if p.get("expected_tool") and p["expected_tool"] not in tools:
            problems.append(f"{pid}: unknown expected_tool {p['expected_tool']!r}")
        for t in p.get("must_not_call", []):
            if t not in tools:
                problems.append(f"{pid}: unknown must_not_call tool {t!r}")
        if not isinstance(p.get("expected_args", {}), dict):
            problems.append(f"{pid}: expected_args must be an object")
    return problems


def load_records(path: Path = RAW_PATH) -> dict[str, dict]:
    """Latest record per prompt_id from the jsonl file (later lines win).

    Blank lines are ignored. A line that is not a record with prompt_id and outcome
    (for example one cut off when a run was killed mid-write) is skipped with a
    warning, so that prompt simply runs again.
    """
    records: dict[str, dict] = {}
    if not path.exists():
        return records
    skipped = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict) or "outcome" not in record:
                raise KeyError("outcome")
            records[record["prompt_id"]] = record
        except (json.JSONDecodeError, KeyError, TypeError):
            skipped.append(number)
    if skipped:
        print(f"warning: skipped unreadable line(s) {', '.join(map(str, skipped))} in {path}")
    return records


def select_prompts(
    prompts: list[dict],
    records: dict[str, dict],
    only: set[str] | None = None,
    limit: int | None = None,
    fresh: bool = False,
) -> list[dict]:
    """Prompts to run now: filtered by --only, minus finished ones (unless --fresh), capped by --limit.

    A prompt whose latest record is an error is not finished.
    """
    chosen = [p for p in prompts if not only or p["prompt_id"] in only]
    if not fresh:
        chosen = [
            p for p in chosen
            if p["prompt_id"] not in records or records[p["prompt_id"]]["outcome"] == "error"
        ]
    return chosen[:limit] if limit is not None else chosen


def _plain(value: Any) -> Any:
    """JSON-safe copy of Gemini's arguments."""
    return json.loads(json.dumps(value, default=str))


def run_prompt(prompt: dict, new_chat: Callable[[], Any] | None = None) -> dict:
    """Ask one prompt in a fresh chat and record every tool call Gemini requested.

    agent._run_tool is wrapped for the duration, so calls that fail before a
    tool wrapper runs (unknown tool, bad argument name) are logged too, with
    Gemini's raw arguments. Gemini requests are counted at chat.send_message,
    so they include retries. new_chat defaults to agent.new_chat (tests pass a fake).
    """
    new_chat = new_chat or agent.new_chat
    calls: list[dict] = []
    requests = 0
    real_run_tool = agent._run_tool

    def logged_run_tool(name, args):
        entry = {"tool": name, "args": _plain(dict(args or {})), "status": None}
        calls.append(entry)
        result = real_run_tool(name, args)
        if isinstance(result, dict):
            entry["status"] = result.get("status")
            detail = result.get("error") or result.get("errors")
            if entry["status"] not in (None, "ok") and detail:
                entry["error"] = str(detail)[:300]
        return result

    record = {
        "prompt_id": prompt["prompt_id"],
        "user_prompt": prompt["user_prompt"],
        "model": os.environ.get("GEMINI_MODEL", agent.DEFAULT_MODEL),
        "time": datetime.now(timezone.utc).isoformat(),
    }
    agent._run_tool = logged_run_tool
    try:
        chat = new_chat()
        real_send = chat.send_message

        def counted_send(*args, **kwargs):
            nonlocal requests
            requests += 1
            return real_send(*args, **kwargs)

        chat.send_message = counted_send
        turn = agent.ask(chat, prompt["user_prompt"])
    except Exception as exc:  # a Gemini failure is recorded, not scored
        record.update(outcome="error", error=f"{type(exc).__name__}: {exc}", reply=None)
    else:
        outcome = "round_cap" if ROUND_CAP_MARK in turn["reply"] else "ok"
        record.update(outcome=outcome, error=None, reply=turn["reply"])
    finally:
        agent._run_tool = real_run_tool
    record.update(calls=calls, gemini_requests=requests)
    return record


def append_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # If the last line was cut off (no newline), start a new line so this record stays readable.
    needs_newline = path.exists() and path.stat().st_size > 0 and not path.read_bytes().endswith(b"\n")
    with path.open("a", encoding="utf-8") as f:
        f.write(("\n" if needs_newline else "") + json.dumps(record, default=str) + "\n")


def _quota_exhausted(record: dict) -> bool:
    error = record.get("error") or ""
    return "PerDay" in error or "RESOURCE_EXHAUSTED" in error


def run_prompts(
    prompts: list[dict],
    raw_path: Path = RAW_PATH,
    new_chat: Callable[[], Any] | None = None,
) -> list[dict]:
    """Run each prompt and append its record right away. Stops early if the quota is used up."""
    done = []
    for i, prompt in enumerate(prompts, start=1):
        record = run_prompt(prompt, new_chat)
        append_record(raw_path, record)
        done.append(record)
        status = record["outcome"] if record["outcome"] != "error" else f"error: {record['error'][:120]}"
        print(f"[{i}/{len(prompts)}] {prompt['prompt_id']}: {_calls_text(record['calls'])} "
              f"({record['gemini_requests']} requests) {status}")
        if _quota_exhausted(record):
            print("Gemini quota is used up; stopping. Rerun later to continue where this left off.")
            break
    return done


def write_report(prompts: list[dict], raw_path: Path = RAW_PATH, report_path: Path = REPORT_PATH) -> dict:
    records = load_records(raw_path)
    result = score(prompts, records)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(result, records), encoding="utf-8")
    return result


def request_estimate(n: int) -> str:
    return (
        f"{n} prompt(s) to run. Likely about {n * LIKELY_REQUESTS} Gemini requests "
        f"({LIKELY_REQUESTS} per prompt; {n * HIGH_REQUESTS} if prompts call ethics then recommend; "
        f"at most {n * MAX_REQUESTS} before retries). Free tier: 20 requests a day."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Layer 2 routing eval (Task #22)")
    ap.add_argument("--prompts", type=Path, default=PROMPTS_PATH)
    ap.add_argument("--raw", type=Path, default=RAW_PATH, help="jsonl file of results (appended to)")
    ap.add_argument("--out", type=Path, default=REPORT_PATH, help="markdown report")
    ap.add_argument("--only", help="comma-separated prompt ids, for example R1,R2")
    ap.add_argument("--limit", type=int, help="run at most this many prompts now")
    ap.add_argument("--fresh", action="store_true", help="rerun prompts even if they already have a result")
    ap.add_argument("--yes", action="store_true", help="do not ask before spending Gemini requests")
    ap.add_argument("--report-only", action="store_true", help="only re-score saved results")
    ap.add_argument("--dry-run", action="store_true",
                    help="check the prompts and print what would run and the request estimate; no requests")
    args = ap.parse_args(argv)

    prompts = load_prompts(args.prompts)
    problems = prompt_problems(prompts)
    if problems:
        print("Problems in the prompts file:")
        for problem in problems:
            print(f"  {problem}")
        return 2
    print(f"Loaded {len(prompts)} prompts from {args.prompts}")
    if not args.report_only:
        only = {x.strip() for x in args.only.split(",")} if args.only else None
        if only:
            unknown = only - {p["prompt_id"] for p in prompts}
            if unknown:
                print(f"unknown prompt id(s): {', '.join(sorted(unknown))}")
                return 2
        todo = select_prompts(prompts, load_records(args.raw), only, args.limit, args.fresh)
        if not todo:
            print("Nothing to run: every selected prompt already has a result (use --fresh to rerun).")
            if args.dry_run:
                return 0
        elif args.dry_run:
            print(request_estimate(len(todo)))
            print("Would run: " + ", ".join(p["prompt_id"] for p in todo))
            print("Dry run: no requests sent, no files written.")
            return 0
        else:
            agent.load_env()
            print(f"Model: {os.environ.get('GEMINI_MODEL', agent.DEFAULT_MODEL)}")
            print(request_estimate(len(todo)))
            print("Prompts: " + ", ".join(p["prompt_id"] for p in todo))
            if not args.yes:
                try:
                    answer = input("Continue? [y/N] ").strip().lower()
                except EOFError:
                    answer = ""
                if answer not in {"y", "yes"}:
                    print("Cancelled; no requests sent.")
                    return 1
            run_prompts(todo, args.raw)

    result = write_report(prompts, args.raw, args.out)
    print(
        f"Tool selection accuracy: {_pct(result['tool_accuracy'])} ({result['tool_hits']}/{result['scored']}), "
        f"argument accuracy: {_pct(result['args_accuracy'])} ({result['args_hits']}/{result['args_scored']}); "
        f"{len(result['errors'])} error, {len(result['not_run'])} not run. Wrote {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
