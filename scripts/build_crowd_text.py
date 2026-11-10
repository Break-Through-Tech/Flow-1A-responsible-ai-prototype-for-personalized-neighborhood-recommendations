"""Build data/crowd_text_snippets.csv from Google Local Data (2021) (Task #13).

Source: https://mcauleylab.ucsd.edu/public_datasets/gdrive/googlelocal/
Download the Florida "reviews" and "metadata" files (complete data). They are
large, so keep them outside the repo.

Three steps, run from the repo root:

1. filter: keep reviews of businesses in the chosen ZIPs. Reviewer names, user
   IDs, photos and business replies are dropped. For reviews that Google
   auto-translated, only the English translation is kept and the row is marked
   translated=True.

    python -m scripts.build_crowd_text filter META.json.gz REVIEWS.json.gz reviews.csv

   Add --start-line N to skip the first N review lines (to finish a stopped run).

2. candidates: list sentences that may be about the area, per ZIP and theme,
   to help pick excerpts by hand. Sentences that call an area unsafe or
   describe who lives there are left out, and so are translated reviews unless
   you add --include-translated.

    python -m scripts.build_crowd_text candidates reviews.csv --zip 33128 --theme quiet

3. build: write the CSV from data/crowd_text_selection.json, the hand-picked
   excerpts. With --check, every excerpt is first confirmed to appear word for
   word in a review of the same business and ZIP. Excerpts marked
   "translated": true get the source google_local_2021_translated.

    python -m scripts.build_crowd_text build --check reviews.csv more_reviews.csv

To cover more ZIPs later: run filter with --zips, pick excerpts with
candidates, add them to the selection file, then run build.
"""
from __future__ import annotations

import argparse
import ast
import csv
import gzip
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
SELECTION_PATH = _ROOT / "data" / "crowd_text_selection.json"
OUTPUT_PATH = _ROOT / "data" / "crowd_text_snippets.csv"
SOURCE = "google_local_2021"

ANCHOR_ZIPS = ("33127", "33128", "33130")
THEMES = ("transit", "walkable", "social", "quiet", "pet_friendly")
TRANSLATED = "(Translated by Google)"

csv.field_size_limit(10_000_000)

# Sentences with these words are never used: they describe an area as unsafe
# or by who lives there, which the agent could use to steer users.
FAIR_HOUSING_EXCLUDE = re.compile(
    r"\b(un)?safe\b|sketch|ghetto|homeless|vagrant|crime|criminal|danger|shady|"
    r"bad (neighbo|area)|\bhood\b|thug|drug|police|scary|robbed|stolen|resident|"
    r"moving (here|in)|\bgay\b|lesbian|families|family[- ]friendly|children|\bkids\b|immigrant|hispanic|latin[oa]|\bblack\b|"
    r"\bwhite\b|asian|jewish|christian|muslim|racial|\brace\b",
    re.I,
)
# A sentence must mention the area, not only the business.
AREA = re.compile(
    r"neighbo|\barea\b|location|walking distance|walk to|walk around|nearby|close by|"
    r"around here|blocks? away|street|metro|trolley|wynwood|brickell|downtown|midtown|"
    r"little havana|district|the city",
    re.I,
)
THEME_WORDS = {
    "transit": r"metromover|metro ?mover|metrorail|metro rail|metro station|trolley|bus|train|"
               r"brightline|public transport|uber|lyft|scooter|bike",
    "walkable": r"walking distance|walkable|walk to|walk around|on foot|don.t need a car|"
                r"without a car|everything (is )?(close|near)",
    "social": r"nightlife|night life|neighborhood|community|vibrant|lively|bars|art walk|scene|"
              r"things to do",
    "quiet": r"nois|loud|quiet|peaceful|sirens?|horns?|music|construction",
    "pet_friendly": r"\bdogs?\b|\bpets?\b|\bpup(s|py|pies)?\b|canine|fur bab",
}
_CONTACT = re.compile(r"\S+@\S+\.\w+|\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}|https?://\S+", re.I)
_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def _normal(text: str) -> str:
    return " ".join((text or "").split())


def _english(text: str) -> tuple[str, bool]:
    """(review text, was it translated). For a Google translation, keep only the English part."""
    text = text or ""
    if TRANSLATED not in text:
        return _normal(text), False
    m = re.search(r"\(Translated by Google\)\s*(.*?)\s*\(Original\)", text, re.S)
    return _normal(m.group(1) if m else text.split(TRANSLATED, 1)[1]), True


def _is_translated(row: dict) -> bool:
    return row.get("translated") == "True" or TRANSLATED in row.get("text", "")


def _parse(path: str, skip: int = 0):
    """Yield one record per line. The first `skip` lines are passed over without parsing."""
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if n <= skip:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                yield ast.literal_eval(line)


def cmd_filter(args) -> None:
    zips = set(args.zips)
    zip_in_address = re.compile(r"\bFL (\d{5})\b")
    businesses = {}
    for b in _parse(args.meta):
        m = zip_in_address.search(b.get("address") or "")
        if m and m.group(1) in zips:
            businesses[b["gmap_id"]] = (m.group(1), b.get("name"), "; ".join(b.get("category") or []))
    print(f"{len(businesses):,} businesses in {sorted(zips)}")

    kept = 0
    if args.start_line:
        print(f"skipping the first {args.start_line:,} review lines (no parsing, this part is fast)...")
    with open(args.out, "w", newline="", encoding="utf-8") as out:
        w = csv.writer(out)
        w.writerow(["gmap_id", "zip", "business_name", "category", "rating", "year", "translated", "text"])
        for i, r in enumerate(_parse(args.reviews, args.start_line), args.start_line + 1):
            biz = businesses.get(r.get("gmap_id"))
            text, translated = _english(r.get("text"))
            if biz and text:
                year = datetime.fromtimestamp(r["time"] / 1000, tz=timezone.utc).year if r.get("time") else ""
                w.writerow([r["gmap_id"], biz[0], biz[1], biz[2], r.get("rating"), year, translated, text])
                kept += 1
            if i % 1_000_000 == 0:
                print(f"  {i:,} reviews read, {kept:,} kept")
    print(f"{kept:,} reviews written to {args.out}")


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def cmd_candidates(args) -> None:
    theme = re.compile(THEME_WORDS[args.theme], re.I)
    seen, shown = set(), 0
    with open(args.reviews, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["zip"] != args.zip or (_is_translated(row) and not args.include_translated):
                continue
            for s in _sentences(_english(row["text"])[0]):
                if (s not in seen and 30 <= len(s) <= 320 and theme.search(s) and AREA.search(s)
                        and not FAIR_HOUSING_EXCLUDE.search(s)):
                    seen.add(s)
                    print(f"[{row['gmap_id']}] ({row['business_name']}) {s}")
                    shown += 1
                    if shown >= args.limit:
                        return


def _problems(item: dict) -> list[str]:
    text = " ".join(item["excerpt"])
    out = []
    if not re.fullmatch(r"\d{5}", item["zip"]):
        out.append("ZIP must be 5 digits")
    if item["theme"] not in THEMES:
        out.append(f"unknown theme {item['theme']}")
    if FAIR_HOUSING_EXCLUDE.search(text):
        out.append("uses unsafe/resident wording")
    if _CONTACT.search(text):
        out.append("contains an email, phone number or link")
    return out


def cmd_build(args) -> None:
    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))

    errors = []
    for n, item in enumerate(selection, 1):
        errors += [f"item {n} ({item['gmap_id']}): {p}" for p in _problems(item)]

    if args.check:
        by_business: dict[tuple, list[tuple[str, bool]]] = {}
        for path in args.check:
            with open(path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    text = _english(row["text"])[0]
                    by_business.setdefault((row["gmap_id"], row["zip"]), []).append((text, _is_translated(row)))
        for n, item in enumerate(selection, 1):
            want = bool(item.get("translated", False))
            reviews = [t for t, tr in by_business.get((item["gmap_id"], item["zip"]), []) if tr == want]
            if not any(all(part in t for part in item["excerpt"]) for t in reviews):
                kind = "translated" if want else "untranslated"
                errors.append(f"item {n} ({item['gmap_id']}): excerpt not found word for word in a {kind} review")

    if errors:
        print("\n".join(errors))
        sys.exit(f"{len(errors)} problem(s); CSV not written")

    order = {t: i for i, t in enumerate(THEMES)}
    selection.sort(key=lambda s: (s["zip"], order[s["theme"]]))
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["snippet_id", "zip", "source", "theme", "text"])
        for k, item in enumerate(selection, 1):
            source = SOURCE + ("_translated" if item.get("translated") else "")
            w.writerow([f"G{k:03d}", item["zip"], source, item["theme"], " ".join(item["excerpt"]).translate(_QUOTES)])
    print(f"wrote {len(selection)} snippets to {args.out}" + (" (all excerpts verified)" if args.check else ""))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("filter", help="keep reviews of businesses in the chosen ZIPs")
    f.add_argument("meta"), f.add_argument("reviews"), f.add_argument("out")
    f.add_argument("--zips", nargs="+", default=list(ANCHOR_ZIPS))
    f.add_argument("--start-line", type=int, default=0,
                   help="skip this many review lines first, e.g. to finish a run that was stopped")
    f.set_defaults(run=cmd_filter)

    c = sub.add_parser("candidates", help="list possible area sentences for one ZIP and theme")
    c.add_argument("reviews")
    c.add_argument("--zip", required=True)
    c.add_argument("--theme", required=True, choices=THEMES)
    c.add_argument("--limit", type=int, default=40)
    c.add_argument("--include-translated", action="store_true", help="also show Google-translated reviews")
    c.set_defaults(run=cmd_candidates)

    b = sub.add_parser("build", help="write the CSV from the selection file")
    b.add_argument("--selection", default=SELECTION_PATH)
    b.add_argument("--out", default=OUTPUT_PATH)
    b.add_argument("--check", metavar="REVIEWS_CSV", nargs="+",
                   help="verify every excerpt against one or more filtered review files")
    b.set_defaults(run=cmd_build)

    args = ap.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
