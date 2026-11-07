"""NLP theme coverage for the scorecard (Task #14).

EVAL_FRAMEWORK.md defines it as: for each recommended ZIP, % with themes
matching the user's priority tags. Concretely:

- A profile's *theme tags* are its tags that are one of the five extracted
  themes (transit, social, quiet, walkable, pet_friendly). A profile with none
  is skipped, since no review can match it.
- Each (profile, recommended ZIP) pair is *covered* when the ZIP has at least
  one review that mentions one of those tags, as found by
  scripts/theme_extraction.py in the review text (not the hand label).
- Theme coverage = covered pairs / all pairs across scored profiles.

Coverage asks whether there is crowd text to explain a match, not whether
the text agrees with it, so a review saying an area is noisy still covers a
"quiet" tag. The `supported` rate counts only pairs with a review that speaks
for the tag, and `contradicted` lists pairs where every review on the tag
speaks against it.

Recommendations come from eval/run_eval.py's evaluate_profile, so this
reports on exactly the ZIPs the Layer 1 eval scores, with the same --data and
--top-k options.

Run from the repo root:

    python3 eval/theme_coverage.py
    python3 eval/theme_coverage.py --json eval/results/theme_coverage.json

Exit codes: 0 when every profile ran, 1 when a profile errored, 2 when an
input file could not be read.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval import run_eval as h
from scripts.theme_extraction import SNIPPETS_PATH, THEMES, extract_themes, load_snippets


def zip_theme_stances(themes: pd.DataFrame) -> dict[str, dict[str, set[str]]]:
    """{zip: {theme: {stances seen}}} from extracted theme rows."""
    out: dict[str, dict[str, set[str]]] = {}
    for r in themes.itertuples(index=False):
        out.setdefault(r.zip, {}).setdefault(r.theme, set()).add(r.stance)
    return out


def score_profile(profile_id: str, tags: list[str], returned_zips: list[str],
                  stances: dict[str, dict[str, set[str]]]) -> dict:
    """Coverage for one profile's recommendations."""
    theme_tags = [t for t in dict.fromkeys(tags) if t in THEMES]
    row = {
        "profile_id": profile_id,
        "theme_tags": theme_tags,
        "returned_zips": list(returned_zips),
        "pairs": [],
    }
    if not theme_tags:
        return row
    for z in returned_zips:
        found = {t: sorted(stances.get(z, {}).get(t, set())) for t in theme_tags}
        found = {t: s for t, s in found.items() if s}
        row["pairs"].append({
            "zip": z,
            "covered": bool(found),
            "supported": any("supports" in s for s in found.values()),
            "themes_found": found,
        })
    return row


def summarize(rows: list[dict], stances: dict[str, dict[str, set[str]]]) -> dict:
    scored = [r for r in rows if r["theme_tags"] and not r.get("error")]
    pairs = [p for r in scored for p in r["pairs"]]
    covered = sum(p["covered"] for p in pairs)
    supported = sum(p["supported"] for p in pairs)

    per_tag = {}
    for tag in THEMES:
        tag_pairs = [p for r in scored if tag in r["theme_tags"] for p in r["pairs"]]
        if tag_pairs:
            hit = sum(tag in p["themes_found"] for p in tag_pairs)
            per_tag[tag] = {"covered": hit, "total": len(tag_pairs), "rate": hit / len(tag_pairs)}

    recommended = {p["zip"] for p in pairs}
    return {
        "theme_coverage": covered / len(pairs) if pairs else None,
        "supported_rate": supported / len(pairs) if pairs else None,
        "covered_pairs": covered,
        "supported_pairs": supported,
        "total_pairs": len(pairs),
        "per_tag": per_tag,
        "contradicted": [
            {"profile_id": r["profile_id"], "zip": p["zip"]}
            for r in scored for p in r["pairs"] if p["covered"] and not p["supported"]
        ],
        "profiles_scored": len(scored),
        "profiles_skipped": [r["profile_id"] for r in rows if not r["theme_tags"] and not r.get("error")],
        "profiles_errored": [r["profile_id"] for r in rows if r.get("error")],
        "zips_with_reviews": len(stances),
        "recommended_zips": len(recommended),
        "recommended_zips_with_reviews": len(recommended & set(stances)),
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1%}"


def render(rows: list[dict], summary: dict) -> None:
    w = max([len("profile")] + [len(r["profile_id"]) for r in rows]) + 2
    print(f"{'profile':<{w}}{'covered':>9}  theme tags")
    for r in rows:
        if r.get("error"):
            print(f"{r['profile_id']:<{w}}{'ERROR':>9}  {r['error']}")
            continue
        if not r["theme_tags"]:
            print(f"{r['profile_id']:<{w}}{'skip':>9}  no extractable theme tags")
            continue
        n = sum(p["covered"] for p in r["pairs"])
        print(f"{r['profile_id']:<{w}}{n:>4}/{len(r['pairs']):<4}  {', '.join(r['theme_tags'])}")

    s = summary
    print(f"\nTheme coverage   {_pct(s['theme_coverage'])} ({s['covered_pairs']}/{s['total_pairs']} recommended ZIPs)")
    print(f"Supported rate   {_pct(s['supported_rate'])} ({s['supported_pairs']}/{s['total_pairs']} have a review speaking for the tag)")
    if s["per_tag"]:
        print("\nBy tag:")
        for tag, v in s["per_tag"].items():
            print(f"  {tag:<14}{_pct(v['rate']):>7}  ({v['covered']}/{v['total']})")
    print(
        f"\nReviews cover {s['zips_with_reviews']} ZIPs; "
        f"{s['recommended_zips_with_reviews']} of the {s['recommended_zips']} recommended ZIPs have any."
    )
    if s["contradicted"]:
        print("Covered only by reviews speaking against the tag: "
              + ", ".join(f"{c['profile_id']}@{c['zip']}" for c in s["contradicted"]))
    if s["profiles_skipped"]:
        print(f"Skipped (no theme tags): {', '.join(s['profiles_skipped'])}")


def main() -> int:
    ap = argparse.ArgumentParser(description="NLP theme coverage of the rec engine's recommendations")
    ap.add_argument("--profiles", type=Path, default=h.PROFILES_PATH)
    ap.add_argument("--data", type=Path, default=None, help="override the ZIP feature CSV")
    ap.add_argument("--snippets", type=Path, default=SNIPPETS_PATH)
    ap.add_argument("--top-k", type=int, default=max(h.PRECISION_KS))
    ap.add_argument("--json", type=Path, default=None, help="also write the full result as JSON")
    args = ap.parse_args()
    if args.top_k < 1:
        ap.error("--top-k must be at least 1")

    try:
        profiles = h.load_profiles(args.profiles)
        ref = h.load_reference(args.data or h.AREA_PATH, h.PUBLIC_PATH)
        snippets = load_snippets(args.snippets)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    stances = zip_theme_stances(extract_themes(snippets))
    rows = []
    for p in profiles:
        evaluated = h.evaluate_profile(p, ref, args.top_k, args.data)
        row = score_profile(p["profile_id"], p["tags"], evaluated["returned_zips"], stances)
        if evaluated["error"]:
            row["error"] = f"{evaluated['status']}: {evaluated['error']}"
        rows.append(row)
    summary = summarize(rows, stances)
    render(rows, summary)

    if args.json:
        try:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            payload = {"summary": summary, "profiles": rows}
            args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"error: could not write {args.json}: {exc}", file=sys.stderr)
            return 2
        print(f"\nwrote {args.json}")

    if summary["profiles_errored"]:
        print(f"\nFAILED: {len(summary['profiles_errored'])} profile(s) errored, so the run is incomplete.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
