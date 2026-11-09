"""Task #14: extract lifestyle themes from crowd text as structured snippets.

Each snippet in data/crowd_text_snippets.csv carries one hand-written `theme`
label, but the text often talks about more than one thing ("easy bus access;
felt welcoming" is transit and social), and sometimes argues against its label
("street noise is real" is labeled quiet). This module reads the text itself
and returns one row per (snippet, theme) it mentions, with the phrase that
triggered it, so anything downstream can quote evidence instead of trusting
the label.

The extractor is a small keyword lexicon, not a model: every match traces to
a pattern in this file and a phrase in the snippet. A theme is a topic, and
`stance` records what the snippet says about it:

- "supports": the text speaks for the theme ("walkable", "easy bus access")
- "contradicts": the text speaks against it ("noisy", "poor bus service")
- "mentions": the text names the topic without saying whether it is good
  ("I took the bus"). It counts toward coverage but never as support.

Words that carry a judgement on their own (walkable, quiet, noisy) set the
stance directly. Plain topic words (bus, sidewalks, dogs, bars) are neutral
until a qualifier in the same clause says otherwise: "poor bus service" is
against transit, "easy bus access" is for it. Nothing here generates or
paraphrases text.

Run from the repo root to see what the lexicon finds in the current corpus:

    python3 scripts/theme_extraction.py
    python3 scripts/theme_extraction.py --out themes.csv   # also write the rows
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
SNIPPETS_PATH = _ROOT / "data" / "crowd_text_snippets.csv"

# The five lifestyle tags Task #14 extracts. co_living is a housing type, not a
# review theme, so it is handled by housing_preference instead.
THEMES = ("transit", "social", "quiet", "walkable", "pet_friendly")
STANCES = ("supports", "contradicts", "mentions")

# Per theme: phrases that judge it on their own ("supports" / "contradicts"),
# and plain topic words ("mentions") whose stance comes from a qualifier in the
# same clause. Matched case-insensitively on word boundaries.
LEXICON: dict[str, dict[str, list[str]]] = {
    "transit": {
        "supports": [r"without a car", r"get around"],
        "contradicts": [r"need(s|ed)? a car", r"car[- ]dependent"],
        "mentions": [
            r"bus(es)?", r"bus stops?", r"metro(rail|mover|bus)?", r"trains?", r"trolle(y|ys)",
            r"stations?", r"(public )?transit", r"(public )?transportation", r"commut\w*",
        ],
    },
    "social": {
        "supports": [
            r"social", r"vibrant", r"street life", r"meet(ing)? (people|up|roommates)",
            r"meeting up", r"connected", r"welcoming",
        ],
        "contradicts": [r"isolat\w*", r"lonely"],
        "mentions": [
            r"events?", r"night ?life", r"night ?clubs?", r"bars", r"restaurants",
            r"community", r"networking", r"scene",
        ],
    },
    "quiet": {
        "supports": [r"quiet(er|est)?", r"calm", r"peaceful"],
        "contradicts": [
            r"nois[ey]\w*", r"loud\w*", r"busy", r"sirens?", r"horns?", r"construction",
        ],
        "mentions": [],
    },
    "walkable": {
        "supports": [
            r"walkab(le|ility)", r"walking distance", r"on foot", r"(don't|do not) need a car",
        ],
        "contradicts": [],
        "mentions": [r"walk(s|ing)?", r"sidewalks?"],
    },
    "pet_friendly": {
        "supports": [r"pet[- ]friendly", r"dog[- ]friendly"],
        "contradicts": [],
        "mentions": [
            r"dogs?", r"pets?", r"cats?", r"canines?", r"pupp(y|ies)", r"fur bab(y|ies)",
        ],
    },
}

# A cue up to three words after one of these flips stance: "not walkable" and
# "no bus" speak against the theme; "not noisy" and "without the traffic and
# noise" speak for quiet. "not only" / "not just" add emphasis, not negation.
_NEGATION = re.compile(
    r"\b(not(?!\s+(only|just)\b)|no|never|isn't|wasn't|aren't|don't|doesn't|can't|cannot|without|hardly|lacks?|lacking)"
    r"(\s+[\w'-]+){0,3}\s+$",
    re.IGNORECASE,
)
_FLIP = {"supports": "contradicts", "contradicts": "supports"}

# Qualifiers that give a plain topic word its stance when they sit in the same
# clause ("poor bus service", "easy bus access"). A clause ends at . ; ! ? or
# "but", so "great bus access but dangerous sidewalks" splits correctly.
_POSITIVE = re.compile(
    r"\b(easy|easily|great|good|convenient|close|nearby|near|love[sd]?|plenty|lots of|many|"
    r"reliable|accessible|short|quick|fast|safe|best|perfect|amazing|nice|friendly|welcoming|fun)\b",
    re.IGNORECASE,
)
_NEGATIVE = re.compile(
    r"\b(poor|bad|terrible|awful|horrible|dangerous|unsafe|delayed|late|unreliable|lack\w*|"
    r"hard|difficult|no|never|limited|far|broken|dirty|nightmare|worst)\b",
    re.IGNORECASE,
)
_CLAUSE_BREAK = re.compile(r"[.;!?]|\bbut\b", re.IGNORECASE)

_COMPILED = {
    theme: {
        stance: [re.compile(rf"\b{p}\b", re.IGNORECASE) for p in patterns]
        for stance, patterns in cues.items()
    }
    for theme, cues in LEXICON.items()
}

THEME_COLUMNS = ["snippet_id", "zip", "source", "theme", "stance", "evidence", "labeled_theme", "text"]
SNIPPET_COLUMNS = ("snippet_id", "zip", "source", "theme", "text")


def _clause(text: str, start: int, end: int) -> str:
    """The clause around text[start:end], bounded by punctuation or "but"."""
    left = max((m.end() for m in _CLAUSE_BREAK.finditer(text, 0, start)), default=0)
    right = next((m.start() for m in _CLAUSE_BREAK.finditer(text, end)), len(text))
    return text[left:right]


def _qualifier_stance(clause: str) -> str:
    """Stance a clause gives a plain topic word, with negated qualifiers flipped.

    "poor bus service" -> contradicts; "easy bus access" -> supports;
    "not the best city for transit" -> contradicts; no qualifier -> mentions.
    """
    seen = set()
    for pattern, stance in ((_NEGATIVE, "contradicts"), (_POSITIVE, "supports")):
        for q in pattern.finditer(clause):
            negated = stance == "supports" and _NEGATION.search(clause[: q.start()])
            seen.add(_FLIP[stance] if negated else stance)
    if "contradicts" in seen:
        return "contradicts"
    return "supports" if "supports" in seen else "mentions"


def _matches(text: str, theme: str) -> list[tuple[int, str, str]]:
    """Every cue for one theme as (position, stance, evidence)."""
    found = []
    for stance, patterns in _COMPILED[theme].items():
        for pattern in patterns:
            for m in pattern.finditer(text):
                if stance == "mentions":
                    clause = _clause(text, m.start(), m.end())
                    qualified = _qualifier_stance(clause)
                    evidence = m.group(0) if qualified == "mentions" else clause.strip()
                    found.append((m.start(), qualified, evidence))
                    continue
                negated = _NEGATION.search(text[: m.start()])
                if negated:
                    found.append((negated.start(), _FLIP[stance], text[negated.start(): m.end()]))
                else:
                    found.append((m.start(), stance, m.group(0)))
    return sorted(found)


def extract_snippet_themes(text: str) -> list[dict]:
    """Themes one snippet mentions, each with its stance and the phrase that matched.

    A theme appears at most once per snippet. If the snippet speaks both for
    and against a theme, "contradicts" wins, since claiming the theme would
    then overstate what the text says. "supports" beats a bare mention.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    found = []
    for theme in THEMES:
        hits = _matches(text, theme)
        if not hits:
            continue
        for stance in ("contradicts", "supports", "mentions"):  # priority order
            chosen = [h for h in hits if h[1] == stance]
            if chosen:
                break
        _, stance, evidence = chosen[0]
        found.append({"theme": theme, "stance": stance, "evidence": evidence})
    return found


def load_snippets(path: Path = SNIPPETS_PATH) -> pd.DataFrame:
    """Read the crowd text CSV with ZIPs kept as strings, failing clearly on a schema change."""
    snippets = pd.read_csv(path, dtype={"zip": str, "snippet_id": str})
    missing = [c for c in SNIPPET_COLUMNS if c not in snippets.columns]
    if missing:
        raise ValueError(f"{path} is missing columns {missing}")
    snippets["zip"] = snippets["zip"].str.strip()
    return snippets


def extract_themes(snippets: pd.DataFrame) -> pd.DataFrame:
    """One row per (snippet, theme) the text mentions. Snippets that mention none drop out."""
    rows = []
    for s in snippets.itertuples(index=False):
        for hit in extract_snippet_themes(s.text):
            rows.append({
                "snippet_id": s.snippet_id,
                "zip": s.zip,
                "source": s.source,
                "theme": hit["theme"],
                "stance": hit["stance"],
                "evidence": hit["evidence"],
                "labeled_theme": s.theme,
                "text": s.text,
            })
    return pd.DataFrame(rows, columns=THEME_COLUMNS)


def label_disagreements(snippets: pd.DataFrame, themes: pd.DataFrame) -> pd.DataFrame:
    """Snippets whose hand label is one of the five themes but the text never mentions it."""
    mentioned = set(zip(themes["snippet_id"], themes["theme"]))
    labeled = snippets[snippets["theme"].isin(THEMES)]
    mask = [(sid, t) not in mentioned for sid, t in zip(labeled["snippet_id"], labeled["theme"])]
    return labeled.loc[mask, ["snippet_id", "zip", "theme", "text"]].reset_index(drop=True)


def themes_for_zip(zip_code: str, themes: pd.DataFrame) -> dict:
    """Structured themes for one ZIP, shaped for the crowd_themes tool. Only quotes existing text."""
    zip_code = str(zip_code).strip()
    rows = themes[themes["zip"] == zip_code]
    return {
        "zip": zip_code,
        "snippet_count": int(rows["snippet_id"].nunique()),
        "themes": {
            theme: [
                {"snippet_id": r.snippet_id, "stance": r.stance, "evidence": r.evidence,
                 "text": r.text, "source": r.source}
                for r in group.itertuples(index=False)
            ]
            for theme, group in rows.groupby("theme", sort=True)
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract structured themes from crowd text snippets")
    ap.add_argument("--snippets", type=Path, default=SNIPPETS_PATH)
    ap.add_argument("--out", type=Path, default=None, help="also write the extracted rows as CSV")
    args = ap.parse_args()

    try:
        snippets = load_snippets(args.snippets)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    themes = extract_themes(snippets)

    counts = (
        themes.groupby(["theme", "stance"]).size().unstack(fill_value=0)
        .reindex(index=THEMES, columns=list(STANCES), fill_value=0)
    )
    print(f"{len(snippets)} snippets, {themes['snippet_id'].nunique()} mention at least one theme\n")
    print(counts.to_string())

    unmatched = sorted(set(snippets["snippet_id"]) - set(themes["snippet_id"]))
    if unmatched:
        print(f"\nNo theme found in: {', '.join(unmatched)}")
    disagree = label_disagreements(snippets, themes)
    if not disagree.empty:
        print("\nHand label never mentioned in the text:")
        for r in disagree.itertuples(index=False):
            print(f"  {r.snippet_id} ({r.zip}) labeled {r.theme}: {r.text}")

    if args.out:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            themes.to_csv(args.out, index=False)
        except OSError as exc:
            print(f"error: could not write {args.out}: {exc}", file=sys.stderr)
            return 2
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
