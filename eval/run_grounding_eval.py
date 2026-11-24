"""Layer 3 grounding eval (Task #23): does every claim in a reply come from tool JSON?

The scored unit and labels are defined in eval/grounding_rubric.md:

    Tool grounding rate   grounded replies / replies with at least one claim (target >= 95%)
    Claim grounding rate  grounded claims / all claims

Each conversation in eval/grounding_conversations.json runs in a fresh chat
through scripts/agent.py. Every finished conversation is appended to
eval/results/grounding_raw.jsonl with the full tool results of every turn, and
a rerun skips conversations that already have a result, so a run can be split
across days (the free tier allows 20 Gemini requests a day). A conversation
whose latest result is an error runs again.

Claims are extracted and checked against the tool results of the same
conversation. Corrections from a human reviewer (false positives, and claims
the script cannot read, such as outside facts) go in
eval/grounding_manual_labels.json and are merged when scoring.

Run from the repo root:

    python eval/run_grounding_eval.py                  # run what is left, then write the report
    python eval/run_grounding_eval.py --limit 3        # at most 3 conversations this time
    python eval/run_grounding_eval.py --only G4,G6     # just these conversations
    python eval/run_grounding_eval.py --only G4 --fresh    # run G4 again even if it is done
    python eval/run_grounding_eval.py --report-only    # re-score the saved results, no requests
    python eval/run_grounding_eval.py --dry-run        # check the files, print the request estimate
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval.run_routing_eval import append_record  # noqa: E402
from scripts import agent  # noqa: E402
from scripts.recommender import load_area_features  # noqa: E402

CONVERSATIONS_PATH = _ROOT / "eval" / "grounding_conversations.json"
MANUAL_PATH = _ROOT / "eval" / "grounding_manual_labels.json"
RAW_PATH = _ROOT / "eval" / "results" / "grounding_raw.jsonl"
REPORT_PATH = _ROOT / "eval" / "results" / "grounding_eval.md"
RESULTS_PATH = _ROOT / "eval" / "results" / "grounding_eval.json"

TARGET = 0.95
LIKELY_REQUESTS_PER_TURN = 2  # one tool round, then the answer
MAX_REQUESTS_PER_TURN = 1 + agent.MAX_TOOL_ROUNDS

# Real places near Miami that are not areas in the data. Naming one is outside
# knowledge unless the user said it. Several are what Gemini tends to call a
# ZCTA-only ZIP (33012 Hialeah, 33149 Key Biscayne, 33030 Homestead).
OUTSIDE_PLACES = (
    "Hialeah", "Hialeah Gardens", "Miami Lakes", "Miami Gardens", "Opa-locka", "Opa-Locka",
    "Homestead", "Florida City", "Key Biscayne", "Fisher Island", "Brickell Key", "Overtown",
    "Little River", "Upper East Side", "Morningside", "Sunny Isles", "Sunny Isles Beach",
    "Surfside", "North Bay Village", "Kendall Lakes", "The Hammocks", "Country Walk",
    "Fontainebleau", "Medley", "Miami Springs", "Virginia Gardens", "Sweetwater Village",
    "Fort Lauderdale", "Hollywood", "Coral Springs", "Boca Raton", "Key West",
)

_APPROX = re.compile(
    r"(?:about|around|approximately|approx\.?|roughly|nearly|almost|over|under|"
    r"more than|less than|close to|just over|just under|some|~|≈)\s*\$?\s*$", re.I)
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6}
_MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)(?:\s?(k|thousand|million|m)\b)?", re.I)
_PERCENT = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?(?:%|percent\b)", re.I)
_ZIP = re.compile(r"(?<![\d$,.#])3[34]\d{3}(?![\d,])")
_NUMBER = re.compile(r"(?<![\w.$#])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d{3,})(?![\w%])")
_QUOTE = re.compile(r"\"([^\"]*)\"|“([^”]*)”")
_LISTING = [
    re.compile(r"https?://\S+|www\.\S+", re.I),
    re.compile(r"\b(?:unit|apt\.?|apartment|suite)\s*#?\s*\d+[a-z]?\b", re.I),
    re.compile(r"\b\d{2,5}\s+(?:[NSEW]{1,2}\.?\s+)?(?:(?:[A-Z][a-z]+|\d+(?:st|nd|rd|th))\s+){1,3}"
               r"(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Dr|Drive|Ct|Court|Way|Pl|Place|Ter|Terrace)\b\.?"),
    re.compile(r"\(?\b\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),
]
_ADJACENT = r"[\s,()\[\]\-–—:]*(?:ZIP(?:\s*code)?\s*)?"


# ---------- tool output index ----------

def _numbers_in_text(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text) if n.replace(",", "")]


def _is_zip(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"\d{5}", value) is not None


class Evidence:
    """Everything the tools returned in one conversation so far, indexed for checking claims."""

    def __init__(self, calls: list[dict], user_text: str):
        self.user_text = user_text
        self.user_lower = user_text.lower()
        self.user_numbers = set(_numbers_in_text(user_text))
        self.global_numbers: set[float] = set()
        self.by_zip: dict[str, set[float]] = {}
        self.zips: set[str] = set(_ZIP.findall(user_text))
        self.names: dict[str, set[str]] = {}      # area_name -> ZIPs, from tool results
        self.zip_name: dict[str, str] = {}        # ZIP -> area_name as the tool gave it
        self.top_coded: set[float] = set()
        self.strings: list[str] = []
        self.ranked: list[str] = []
        for call in calls:
            result = call.get("result")
            self._walk(result, None)
            if call.get("tool") == "recommend" and isinstance(result, dict) and result.get("status") == "ok":
                self.ranked = [r["zip"] for r in result.get("recommendations", [])]
        self.text = _norm(" ".join(self.strings))

    def _walk(self, value: Any, owner: str | None) -> None:
        if isinstance(value, dict):
            zip_code = value.get("zip") if _is_zip(value.get("zip")) else value.get("zip_code")
            if _is_zip(zip_code):
                owner = zip_code
                self.zips.add(zip_code)
                name = value.get("area_name")
                if isinstance(name, str):
                    self.zip_name[zip_code] = name
                    if not name.startswith("ZCTA"):
                        self.names.setdefault(name, set()).add(zip_code)
            coded = value.get("top_coded")
            for entry in coded if isinstance(coded, list) else [coded]:
                if isinstance(entry, dict) and isinstance(entry.get("value"), (int, float)):
                    self.top_coded.add(float(entry["value"]))
            for v in value.values():
                self._walk(v, owner)
        elif isinstance(value, list):
            for v in value:
                self._walk(v, owner)
        elif isinstance(value, bool) or value is None:
            return
        elif isinstance(value, (int, float)):
            self._add(float(value), owner)
        elif isinstance(value, str):
            self.strings.append(value)
            self.zips.update(z for z in _ZIP.findall(value))
            for n in _numbers_in_text(value):
                self._add(n, owner)

    def _add(self, number: float, owner: str | None) -> None:
        (self.by_zip.setdefault(owner, set()) if owner else self.global_numbers).add(number)

    def all_numbers(self) -> set[float]:
        return set().union(self.global_numbers, self.user_numbers, *self.by_zip.values())


def _norm(text: str) -> str:
    text = text.lower().replace("’", "'").replace("‘", "'")
    text = re.sub(r"[^\w'$%.,]+", " ", text)
    return re.sub(r"\s+", " ", text).strip(" .,'")


def _data_names() -> dict[str, set[str]]:
    """Every neighborhood name in the data (not only those a tool returned), name -> ZIPs."""
    names: dict[str, set[str]] = {}
    for row in load_area_features().itertuples():
        if isinstance(row.area_name, str) and not row.area_name.startswith("ZCTA"):
            names.setdefault(row.area_name, set()).add(str(row.zip).zfill(5))
    return names


_DATA_NAMES: dict[str, set[str]] | None = None


def data_names() -> dict[str, set[str]]:
    global _DATA_NAMES
    if _DATA_NAMES is None:
        _DATA_NAMES = _data_names()
    return _DATA_NAMES


# ---------- claim extraction and checking ----------

def _segments(reply: str) -> list[str]:
    text = reply.replace("**", "").replace("__", "").replace("`", "")
    parts = []
    for line in text.splitlines():
        parts += [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\d*#(\[-])", line) if s.strip()]
    return parts


def _mask(text: str, spans: list[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        chars[start:end] = " " * (end - start)
    return "".join(chars)


def _tolerance(digits: str, approx: bool, scale: float) -> float:
    whole, _, decimals = digits.replace(",", "").partition(".")
    if decimals:
        return 0.5 * 10 ** -len(decimals) * scale
    if approx or scale > 1:
        zeros = len(whole) - len(whole.rstrip("0")) if scale == 1 else 0
        return 0.5 * 10 ** zeros * scale
    return 0.5


def _close(value: float, tol: float, pool: set[float], percent: bool = False) -> bool:
    candidates = pool | ({v * 100 for v in pool} if percent else set())
    return any(abs(value - v) <= tol + 1e-9 for v in candidates)


def _claim(kind: str, text: str, segment: str, grounded: bool, reason: str = "") -> dict:
    return {"type": kind, "text": text, "segment": segment.strip(), "grounded": grounded,
            "reason": reason, "source": "auto"}


def _entity(segment: str, ev: Evidence, names_found: list[str]) -> str | None:
    """The one area a sentence is about: its only ZIP, else its only name with one ZIP."""
    zips = list(dict.fromkeys(_ZIP.findall(segment)))
    if len(zips) == 1:
        return zips[0]
    if not zips:
        owners = {z for n in names_found for z in ev.names.get(n, ())}
        if len(owners) == 1:
            return owners.pop()
    return None


def _check_number(kind: str, raw: str, approx: bool, scale: float, segment: str,
                  ev: Evidence, entity: str | None) -> dict:
    value = float(raw.replace(",", "")) * scale
    shown = ("$" if kind == "money" else "") + raw + ("%" if kind == "percent" else "")
    tol = _tolerance(raw, approx, scale)
    percent = kind == "percent"
    if not approx and value in ev.top_coded:
        return _claim(kind, shown, segment, False, "top-coded ACS value stated as exact (rule 8)")
    if _close(value, tol, ev.user_numbers):
        return _claim(kind, shown, segment, True, "repeats the user's message")
    if entity:
        own = ev.by_zip.get(entity, set()) | ev.global_numbers
        if _close(value, tol, own, percent):
            return _claim(kind, shown, segment, True)
        others = [z for z, pool in ev.by_zip.items() if z != entity and _close(value, tol, pool, percent)]
        if others:
            return _claim(kind, shown, segment, False,
                          f"belongs to {', '.join(sorted(others))} in the tool output, not {entity}")
        return _claim(kind, shown, segment, False, f"not in any tool result for {entity}")
    if _close(value, tol, ev.all_numbers(), percent):
        return _claim(kind, shown, segment, True)
    return _claim(kind, shown, segment, False, "not in any tool result")


def _find_names(text: str) -> list[tuple[str, int, int]]:
    """Known place names in the text, longest first so "West Kendall" is not also "Kendall"."""
    found = []
    for name in sorted({*data_names(), *OUTSIDE_PLACES}, key=len, reverse=True):
        for m in re.finditer(rf"(?<![\w/]){re.escape(name)}(?![\w/])", text):
            found.append((name, m.start(), m.end()))
            text = text[: m.start()] + " " * len(name) + text[m.end():]
    return found


def _check_name(name: str, segment: str, ev: Evidence) -> dict:
    for z in _ZIP.findall(segment):
        pattern = rf"{re.escape(name)}{_ADJACENT}{z}|{z}{_ADJACENT}{re.escape(name)}"
        if re.search(pattern, segment):
            given = ev.zip_name.get(z)
            if given and given.startswith("ZCTA"):
                return _claim("area_name", name, segment, False, f"{z} has no neighborhood name in the data (rule 9)")
            if given and given != name:
                return _claim("area_name", name, segment, False, f"{z} is {given} in the tool output, not {name}")
            if not given and z not in data_names().get(name, set()):
                return _claim("area_name", name, segment, False, f"{name} is not ZIP {z} in the data")
    if name in ev.names:
        return _claim("area_name", name, segment, True)
    if name.lower() in ev.user_lower:
        return _claim("area_name", name, segment, True, "repeats the user's message")
    if name in OUTSIDE_PLACES:
        return _claim("area_name", name, segment, False, "place is not in the data or any tool result")
    return _claim("area_name", name, segment, False, "no tool returned this area")


def extract_claims(reply: str, ev: Evidence, turn_called_recommend: bool = False) -> list[dict]:
    """Every automatically checkable claim in a reply, labeled grounded or not (see the rubric)."""
    claims: list[dict] = []
    for segment in _segments(reply):
        spans: list[tuple[int, int]] = []

        for m in _QUOTE.finditer(segment):
            spans.append(m.span())
            quote = (m.group(1) if m.group(1) is not None else m.group(2)).strip(" *_")
            if len(quote.split()) < 3:
                continue
            pieces = [_norm(p) for p in re.split(r"\.\.\.|…", quote) if len(p.split()) >= 2]
            if _norm(quote) in _norm(ev.user_text):
                continue
            missing = [p for p in pieces if p not in ev.text]
            claims.append(_claim("quote", quote, segment, not missing,
                                 "" if not missing else "not word for word in any tool result"))

        for pattern in _LISTING:
            for m in pattern.finditer(_mask(segment, spans)):
                spans.append(m.span())
                if _norm(m.group(0)) and _norm(m.group(0)) in _norm(ev.user_text):
                    continue
                claims.append(_claim("listing_detail", m.group(0).strip(), segment, False,
                                     "no tool returns links, units, addresses or phone numbers"))

        masked = _mask(segment, spans)
        names = _find_names(masked)
        for name, _, _ in names:
            claims.append({**_check_name(name, masked, ev), "segment": segment.strip()})
        entity = _entity(masked, ev, [n for n, _, _ in names])

        for z in dict.fromkeys(_ZIP.findall(masked)):
            ok = z in ev.zips
            claims.append(_claim("zip", z, segment, ok, "" if ok else "ZIP not returned by any tool"))

        for m in _MONEY.finditer(masked):
            approx = bool(_APPROX.search(masked[: m.start()]))
            scale = _SCALE.get((m.group(2) or "").lower(), 1)
            claims.append(_check_number("money", m.group(1), approx, scale, segment, ev, entity))
            spans.append(m.span())
        masked = _mask(segment, spans)
        for m in _PERCENT.finditer(masked):
            approx = bool(_APPROX.search(masked[: m.start()]))
            claims.append(_check_number("percent", m.group(1), approx, 1, segment, ev, entity))
            spans.append(m.span())
        masked = _mask(_mask(segment, spans), [m.span() for m in _ZIP.finditer(segment)])
        for m in _NUMBER.finditer(masked):
            approx = bool(_APPROX.search(masked[: m.start()]))
            claims.append(_check_number("number", m.group(1), approx, 1, segment, ev, entity))

    mentioned = [z for _, z in sorted((reply.find(z), z) for z in ev.ranked if z in reply)]
    if len(mentioned) >= 2 and (turn_called_recommend or len(mentioned) >= 3):
        expected = [z for z in ev.ranked if z in mentioned]
        ok = mentioned == expected
        claims.append(_claim("ranking_order", ", ".join(mentioned), "", ok,
                             "" if ok else f"recommend ranked them {', '.join(expected)}"))

    unique: dict[tuple, dict] = {}
    for c in claims:
        unique.setdefault((c["type"], c["text"], c["grounded"], c["reason"]), c)
    return list(unique.values())


# ---------- scoring (pure functions, no API) ----------

def score_conversation(record: dict) -> list[dict]:
    """Claims for every turn of one finished conversation, checked against tool results so far."""
    calls: list[dict] = []
    said: list[str] = []
    scored = []
    for number, turn in enumerate(record.get("turns", []), start=1):
        said.append(turn["user"])
        calls += turn.get("tool_calls", [])
        ev = Evidence(calls, "\n".join(said))
        called = any(c.get("tool") == "recommend" for c in turn.get("tool_calls", []))
        scored.append({
            "turn": number,
            "prompt": turn["user"],
            "reply": turn["reply"],
            "tools": [c.get("tool") for c in turn.get("tool_calls", [])],
            "claims": extract_claims(turn["reply"], ev, called),
        })
    return scored


def apply_manual_labels(conversation_id: str, turns: list[dict], labels: list[dict]) -> list[dict]:
    """Merge reviewer labels into one conversation's claims. Returns labels that matched nothing."""
    unmatched = []
    for label in labels:
        if label.get("conversation_id") != conversation_id:
            continue
        turn = next((t for t in turns if t["turn"] == label.get("turn")), None)
        if turn is None:
            unmatched.append(label)
            continue
        grounded = label.get("label") == "grounded"
        reason = f"manual: {label.get('reason', '')}".strip()
        hits = [c for c in turn["claims"] if c["text"] == label.get("claim")]
        for c in hits:
            c.update(grounded=grounded, reason=reason, source="manual")
        if not hits:
            if grounded:
                unmatched.append(label)
            else:
                turn["claims"].append({"type": label.get("type", "qualitative"), "text": label.get("claim", ""),
                                       "segment": label.get("claim", ""), "grounded": False,
                                       "reason": reason, "source": "manual"})
    return unmatched


def _ratio(hits: int, total: int) -> float | None:
    return hits / total if total else None


def score(conversations: list[dict], records: dict[str, dict], labels: list[dict] | None = None) -> dict:
    labels = labels or []
    scored, not_run, errors, unmatched = [], [], [], []
    for conv in conversations:
        record = records.get(conv["id"])
        if record is None:
            not_run.append(conv["id"])
            continue
        if record.get("outcome") != "ok":
            errors.append({"id": conv["id"], "error": record.get("error")})
            continue
        turns = score_conversation(record)
        unmatched += apply_manual_labels(conv["id"], turns, labels)
        scored.append({"id": conv["id"], "title": conv.get("title", ""), "depends_on": conv.get("depends_on"),
                       "model": record.get("model"), "turns": turns})

    replies = [(c["id"], t) for c in scored for t in c["turns"]]
    with_claims = [(cid, t) for cid, t in replies if t["claims"]]
    grounded_replies = [(cid, t) for cid, t in with_claims if all(c["grounded"] for c in t["claims"])]
    claims = [c for _, t in replies for c in t["claims"]]
    by_type: dict[str, dict] = {}
    for c in claims:
        row = by_type.setdefault(c["type"], {"claims": 0, "grounded": 0})
        row["claims"] += 1
        row["grounded"] += c["grounded"]
    ungrounded = [
        {"conversation_id": cid, "turn": t["turn"], "prompt": t["prompt"], "claim": c["text"],
         "type": c["type"], "reason": c["reason"], "sentence": c["segment"], "source": c["source"]}
        for cid, t in replies for c in t["claims"] if not c["grounded"]
    ]
    rate = _ratio(len(grounded_replies), len(with_claims))
    return {
        "conversations_total": len(conversations),
        "conversations_scored": len(scored),
        "replies": len(replies),
        "replies_with_claims": len(with_claims),
        "replies_without_claims": [f"{cid} turn {t['turn']}" for cid, t in replies if not t["claims"]],
        "grounded_replies": len(grounded_replies),
        "grounding_rate": rate,
        "claims": len(claims),
        "grounded_claims": sum(c["grounded"] for c in claims),
        "claim_rate": _ratio(sum(c["grounded"] for c in claims), len(claims)),
        "by_type": dict(sorted(by_type.items())),
        "target": TARGET,
        "passes": rate is not None and rate >= TARGET,
        "ungrounded": ungrounded,
        "manual_overrides": [
            {"conversation_id": cid, "turn": t["turn"], "claim": c["text"], "grounded": c["grounded"], "reason": c["reason"]}
            for cid, t in replies for c in t["claims"] if c["source"] == "manual"
        ],
        "unmatched_labels": unmatched,
        "not_run": not_run,
        "errors": errors,
        "conversations": scored,
    }


# ---------- report ----------

def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_report(result: dict, raw_path: Path = RAW_PATH) -> str:
    models = sorted({c["model"] for c in result["conversations"] if c.get("model")})
    lines = [
        "# Tool grounding eval (Task #23)",
        "",
        f"Model: {', '.join(models) or 'n/a'}. Report written {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC "
        f"from `{_display(raw_path)}`. Scoring rules: [`eval/grounding_rubric.md`](../grounding_rubric.md).",
        "",
        "| Metric | Result | Target |",
        "|--------|--------|--------|",
        f"| **Tool grounding rate** | **{_pct(result['grounding_rate'])}** "
        f"({result['grounded_replies']}/{result['replies_with_claims']} replies) | ≥ {TARGET:.0%} |",
        f"| Claim grounding rate | {_pct(result['claim_rate'])} ({result['grounded_claims']}/{result['claims']} claims) | |",
        "",
        f"{result['conversations_scored']} of {result['conversations_total']} conversations scored, "
        f"{result['replies']} replies. {len(result['replies_without_claims'])} replies had no claims and are not in the rates"
        + (f" ({', '.join(result['replies_without_claims'])})." if result["replies_without_claims"] else "."),
        "",
    ]
    if result["not_run"]:
        lines += [f"Not run yet: {', '.join(result['not_run'])}.", ""]
    if result["errors"]:
        lines += ["Errors (not scored): " + "; ".join(f"{e['id']}: {_cell(e['error'])[:120]}" for e in result["errors"]), ""]

    lines += ["## Claims by type", "", "| Type | Claims | Grounded |", "|------|--------|----------|"]
    for kind, row in result["by_type"].items():
        lines.append(f"| `{kind}` | {row['claims']} | {row['grounded']} |")

    lines += ["", "## Ungrounded claims", ""]
    if result["ungrounded"]:
        lines += ["| Conversation | Turn | Prompt | Claim | Type | Reason |", "|---|---|---|---|---|---|"]
        for u in result["ungrounded"]:
            lines.append(f"| {u['conversation_id']} | {u['turn']} | {_cell(u['prompt'])} | {_cell(u['claim'])} "
                         f"| `{u['type']}` | {_cell(u['reason'])} |")
    else:
        lines.append("None.")

    if result["manual_overrides"] or result["unmatched_labels"]:
        lines += ["", "## Manual labels", ""]
        for o in result["manual_overrides"]:
            lines.append(f"- {o['conversation_id']} turn {o['turn']}: {_cell(o['claim'])} → "
                         f"{'grounded' if o['grounded'] else 'ungrounded'} ({_cell(o['reason'])})")
        for u in result["unmatched_labels"]:
            lines.append(f"- **Matched no claim:** {_cell(json.dumps(u))}")

    lines += ["", "## Replies", "",
              "Read each reply for claims the script cannot check (outside facts, review characterizations) "
              "and add them to `eval/grounding_manual_labels.json`.", ""]
    for conv in result["conversations"]:
        note = f" (depends on {conv['depends_on']})" if conv.get("depends_on") else ""
        lines += [f"### {conv['id']}: {conv['title']}{note}", ""]
        for t in conv["turns"]:
            lines += [f"**User:** {t['prompt']}", "", f"**Agent:** {t['reply']}", "",
                      f"Tools: {', '.join(t['tools']) or 'none'}. "
                      + (f"Claims: {sum(c['grounded'] for c in t['claims'])}/{len(t['claims'])} grounded."
                         if t["claims"] else "No claims."), ""]
            for c in t["claims"]:
                if not c["grounded"]:
                    lines.append(f"- ✗ `{c['type']}` {_cell(c['text'])}: {_cell(c['reason'])}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _display(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_ROOT))
    except ValueError:
        return str(path)


# ---------- files ----------

def load_conversations(path: Path = CONVERSATIONS_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def conversation_problems(conversations: list[dict]) -> list[str]:
    problems, seen = [], set()
    for i, conv in enumerate(conversations):
        cid = conv.get("id") if isinstance(conv, dict) else None
        if not isinstance(cid, str) or not cid:
            problems.append(f"entry {i}: missing id")
            continue
        if cid in seen:
            problems.append(f"{cid}: duplicate id")
        seen.add(cid)
        turns = conv.get("turns")
        if not isinstance(turns, list) or not turns or not all(isinstance(t, str) and t.strip() for t in turns):
            problems.append(f"{cid}: turns must be a non-empty list of messages")
    return problems


def load_labels(path: Path = MANUAL_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def load_records(path: Path = RAW_PATH) -> dict[str, dict]:
    """Latest record per conversation id (later lines win). Unreadable lines are skipped with a warning."""
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
            records[record["conversation_id"]] = record
        except (json.JSONDecodeError, KeyError, TypeError):
            skipped.append(number)
    if skipped:
        print(f"warning: skipped unreadable line(s) {', '.join(map(str, skipped))} in {path}")
    return records


def select_conversations(conversations: list[dict], records: dict[str, dict], only: set[str] | None = None,
                         limit: int | None = None, fresh: bool = False) -> list[dict]:
    chosen = [c for c in conversations if not only or c["id"] in only]
    if not fresh:
        chosen = [c for c in chosen if c["id"] not in records or records[c["id"]]["outcome"] != "ok"]
    return chosen[:limit] if limit is not None else chosen


# ---------- running (real Gemini requests) ----------

def run_conversation(conv: dict, new_chat: Callable[[], Any] | None = None) -> dict:
    """Run every turn of one conversation in a fresh chat, keeping the full tool results."""
    new_chat = new_chat or agent.new_chat
    requests = 0
    record = {
        "conversation_id": conv["id"],
        "model": os.environ.get("GEMINI_MODEL", agent.DEFAULT_MODEL),
        "time": datetime.now(timezone.utc).isoformat(),
        "turns": [],
    }
    try:
        chat = new_chat()
        real_send = chat.send_message

        def counted_send(*args, **kwargs):
            nonlocal requests
            requests += 1
            return real_send(*args, **kwargs)

        chat.send_message = counted_send
        for message in conv["turns"]:
            turn = agent.ask(chat, message)
            record["turns"].append(json.loads(json.dumps(turn, default=str)))
    except Exception as exc:  # a Gemini failure is recorded, not scored
        record.update(outcome="error", error=f"{type(exc).__name__}: {exc}")
    else:
        record.update(outcome="ok", error=None)
    record["gemini_requests"] = requests
    return record


def _quota_exhausted(record: dict) -> bool:
    error = record.get("error") or ""
    return "PerDay" in error or "RESOURCE_EXHAUSTED" in error


def run_conversations(conversations: list[dict], raw_path: Path = RAW_PATH,
                      new_chat: Callable[[], Any] | None = None) -> list[dict]:
    """Run each conversation and append its record right away. Stops early if the quota is used up."""
    done = []
    for i, conv in enumerate(conversations, start=1):
        record = run_conversation(conv, new_chat)
        append_record(raw_path, record)
        done.append(record)
        status = record["outcome"] if record["outcome"] == "ok" else f"error: {record['error'][:120]}"
        print(f"[{i}/{len(conversations)}] {conv['id']}: {len(record['turns'])}/{len(conv['turns'])} turns "
              f"({record['gemini_requests']} requests) {status}")
        if _quota_exhausted(record):
            print("Gemini quota is used up; stopping. Rerun later to continue where this left off.")
            break
    return done


def request_estimate(conversations: list[dict]) -> str:
    turns = sum(len(c["turns"]) for c in conversations)
    return (f"{len(conversations)} conversation(s), {turns} turn(s). Likely about "
            f"{turns * LIKELY_REQUESTS_PER_TURN} Gemini requests (at most {turns * MAX_REQUESTS_PER_TURN} "
            f"before retries). Free tier: 20 requests a day.")


def write_outputs(conversations: list[dict], raw_path: Path = RAW_PATH, report_path: Path = REPORT_PATH,
                  results_path: Path = RESULTS_PATH, labels_path: Path = MANUAL_PATH) -> dict:
    result = score(conversations, load_records(raw_path), load_labels(labels_path))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(result, raw_path), encoding="utf-8")
    summary = {k: v for k, v in result.items() if k != "conversations"}
    results_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Layer 3 tool grounding eval (Task #23)")
    ap.add_argument("--conversations", type=Path, default=CONVERSATIONS_PATH)
    ap.add_argument("--labels", type=Path, default=MANUAL_PATH, help="manual labels json")
    ap.add_argument("--raw", type=Path, default=RAW_PATH, help="jsonl file of results (appended to)")
    ap.add_argument("--out", type=Path, default=REPORT_PATH, help="markdown report")
    ap.add_argument("--results", type=Path, default=RESULTS_PATH, help="json summary with every ungrounded claim")
    ap.add_argument("--only", help="comma-separated conversation ids, for example G1,G2")
    ap.add_argument("--limit", type=int, help="run at most this many conversations now")
    ap.add_argument("--fresh", action="store_true", help="rerun conversations even if they already have a result")
    ap.add_argument("--yes", action="store_true", help="do not ask before spending Gemini requests")
    ap.add_argument("--report-only", action="store_true", help="only re-score saved results")
    ap.add_argument("--dry-run", action="store_true", help="check the files and print the request estimate; no requests")
    args = ap.parse_args(argv)

    conversations = load_conversations(args.conversations)
    problems = conversation_problems(conversations)
    if problems:
        print("Problems in the conversations file:")
        for problem in problems:
            print(f"  {problem}")
        return 2
    print(f"Loaded {len(conversations)} conversations from {_display(args.conversations)}")
    if not args.report_only:
        only = {x.strip() for x in args.only.split(",")} if args.only else None
        if only and only - {c["id"] for c in conversations}:
            print(f"unknown conversation id(s): {', '.join(sorted(only - {c['id'] for c in conversations}))}")
            return 2
        todo = select_conversations(conversations, load_records(args.raw), only, args.limit, args.fresh)
        if not todo:
            print("Nothing to run: every selected conversation already has a result (use --fresh to rerun).")
            if args.dry_run:
                return 0
        elif args.dry_run:
            print(request_estimate(todo))
            print("Would run: " + ", ".join(c["id"] for c in todo))
            print("Dry run: no requests sent, no files written.")
            return 0
        else:
            agent.load_env()
            print(f"Model: {os.environ.get('GEMINI_MODEL', agent.DEFAULT_MODEL)}")
            print(request_estimate(todo))
            if not args.yes:
                try:
                    answer = input("Continue? [y/N] ").strip().lower()
                except EOFError:
                    answer = ""
                if answer not in {"y", "yes"}:
                    print("Cancelled; no requests sent.")
                    return 1
            run_conversations(todo, args.raw)

    result = write_outputs(conversations, args.raw, args.out, args.results, args.labels)
    print(f"Tool grounding rate: {_pct(result['grounding_rate'])} "
          f"({result['grounded_replies']}/{result['replies_with_claims']} replies), "
          f"claims {_pct(result['claim_rate'])} ({result['grounded_claims']}/{result['claims']}); "
          f"{len(result['ungrounded'])} ungrounded claim(s), {len(result['not_run'])} not run, "
          f"{len(result['errors'])} error. Wrote {_display(args.out)} and {_display(args.results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
