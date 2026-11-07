"""Checks for Task #14: theme extraction and the theme coverage metric.

The extractor tests use made-up sentences, so they keep passing when the
review corpus is replaced. Run from the repo root (also collected by pytest
if it is installed):

    python3 eval/test_theme_coverage.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval import theme_coverage as cov
from scripts import theme_extraction as te


def _themes(text: str) -> dict[str, tuple[str, str]]:
    return {h["theme"]: (h["stance"], h["evidence"]) for h in te.extract_snippet_themes(text)}


def _snippets(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=list(te.SNIPPET_COLUMNS))


# --- extraction ---------------------------------------------------------------

def test_one_snippet_can_mention_several_themes():
    found = _themes("Great walkability and easy bus access; felt welcoming.")
    assert set(found) == {"walkable", "transit", "social"}
    assert all(stance == "supports" for stance, _ in found.values())
    assert found["transit"][1] == "bus"


def test_matching_ignores_case_and_needs_whole_words():
    assert _themes("METRORAIL nearby")["transit"][0] == "supports"
    # "busy" is a quiet cue, and must not be read as "bus".
    assert "transit" not in _themes("A busy corner.")
    assert "pet_friendly" not in _themes("Lots of category options.")


def test_negation_flips_a_supporting_cue():
    assert _themes("The area is not walkable at all.")["walkable"] == ("contradicts", "not walkable")
    assert _themes("It isn't super walkable.")["walkable"][0] == "contradicts"
    assert _themes("There is no bus here.")["transit"][0] == "contradicts"


def test_negation_flips_a_contradicting_cue():
    assert _themes("This area is not noisy.")["quiet"] == ("supports", "not noisy")
    assert _themes("Close to downtown without the traffic and noise.")["quiet"][0] == "supports"
    assert _themes("You don't need a car here.")["walkable"][0] == "supports"


def test_negation_only_reaches_three_words():
    found = _themes("No one ever complains, but the music from the bars is loud.")
    assert found["quiet"][0] == "contradicts"


def test_contradicting_wins_when_a_snippet_says_both():
    assert _themes("Quiet streets, but loud on weekends.")["quiet"] == ("contradicts", "loud")


def test_text_with_no_theme_or_no_text_returns_nothing():
    assert te.extract_snippet_themes("Rent is high but you pay for location.") == []
    for empty in ("", "   ", None, float("nan")):
        assert te.extract_snippet_themes(empty) == []


def test_every_theme_has_a_lexicon_entry():
    assert set(te.LEXICON) == set(te.THEMES)
    assert "co_living" not in te.THEMES


def test_extract_themes_keeps_ids_and_zip_strings_and_one_row_per_theme():
    snippets = _snippets([
        ("S1", "01234", "src", "transit", "Bus, bus and more buses."),
        ("S2", "01234", "src", "quiet", "Rent is high."),
    ])
    out = te.extract_themes(snippets)
    assert list(out.columns) == te.THEME_COLUMNS
    assert out[["snippet_id", "zip", "theme"]].values.tolist() == [["S1", "01234", "transit"]]
    assert out.iloc[0]["labeled_theme"] == "transit"


def test_extract_themes_on_an_empty_corpus_has_the_right_columns():
    out = te.extract_themes(_snippets([]))
    assert out.empty and list(out.columns) == te.THEME_COLUMNS


def test_label_disagreements_lists_labels_the_text_never_mentions():
    snippets = _snippets([
        ("S1", "33130", "src", "quiet", "Street noise is real."),     # mentioned, against
        ("S2", "33130", "src", "transit", "Lovely murals."),          # never mentioned
        ("S3", "33130", "src", "co_living", "Shared lofts."),         # not one of the five
    ])
    out = te.label_disagreements(snippets, te.extract_themes(snippets))
    assert out["snippet_id"].tolist() == ["S2"]


def test_load_snippets_reads_zips_as_strings_and_rejects_a_changed_schema():
    d = Path(tempfile.mkdtemp())
    good = d / "good.csv"
    _snippets([("S1", " 01234 ", "src", "transit", "bus")]).to_csv(good, index=False)
    assert te.load_snippets(good)["zip"].tolist() == ["01234"]

    bad = d / "bad.csv"
    pd.DataFrame({"snippet_id": ["S1"], "zip": ["33130"], "text": ["bus"]}).to_csv(bad, index=False)
    try:
        te.load_snippets(bad)
    except ValueError as exc:
        assert "missing columns" in str(exc)
    else:
        raise AssertionError("a CSV without source/theme should be rejected")


def test_themes_for_zip_groups_by_theme_and_handles_unknown_zips():
    snippets = _snippets([
        ("S1", "33130", "src", "transit", "Metrorail nearby; quiet at night."),
        ("S2", "33130", "src", "quiet", "Very loud sirens."),
        ("S3", "33127", "src", "social", "Great nightlife."),
    ])
    out = te.themes_for_zip(" 33130 ", te.extract_themes(snippets))
    assert out["zip"] == "33130" and out["snippet_count"] == 2
    assert sorted(out["themes"]) == ["quiet", "transit"]
    assert sorted(s["stance"] for s in out["themes"]["quiet"]) == ["contradicts", "supports"]
    assert te.themes_for_zip("99999", te.extract_themes(snippets)) == {
        "zip": "99999", "snippet_count": 0, "themes": {},
    }


# --- coverage -----------------------------------------------------------------

STANCES = {
    "33130": {"transit": {"supports"}, "quiet": {"contradicts"}},
    "33127": {"social": {"supports"}},
}


def test_a_pair_is_covered_by_any_review_on_a_requested_tag():
    row = cov.score_profile("P", ["transit", "walkable"], ["33130", "33127", "99999"], STANCES)
    assert [p["covered"] for p in row["pairs"]] == [True, False, False]
    assert row["pairs"][0]["themes_found"] == {"transit": ["supports"]}


def test_a_review_against_the_tag_covers_but_does_not_support():
    row = cov.score_profile("P", ["quiet"], ["33130"], STANCES)
    pair = row["pairs"][0]
    assert pair["covered"] and not pair["supported"]
    s = cov.summarize([row], STANCES)
    assert s["contradicted"] == [{"profile_id": "P", "zip": "33130"}]


def test_profiles_without_theme_tags_are_skipped_not_scored_as_zero():
    rows = [
        cov.score_profile("A", ["co_living"], ["33130"], STANCES),
        cov.score_profile("B", ["transit"], ["33130", "33127"], STANCES),
    ]
    s = cov.summarize(rows, STANCES)
    assert s["profiles_skipped"] == ["A"] and s["profiles_scored"] == 1
    assert s["theme_coverage"] == 0.5 and s["total_pairs"] == 2


def test_summary_rates_and_per_tag_breakdown():
    rows = [
        cov.score_profile("A", ["transit", "social"], ["33130", "33127"], STANCES),
        cov.score_profile("B", ["social"], ["33130"], STANCES),
    ]
    s = cov.summarize(rows, STANCES)
    assert (s["covered_pairs"], s["total_pairs"]) == (2, 3)
    assert s["per_tag"]["transit"] == {"covered": 1, "total": 2, "rate": 0.5}
    assert s["per_tag"]["social"]["covered"] == 1 and s["per_tag"]["social"]["total"] == 3
    assert "quiet" not in s["per_tag"]
    assert (s["recommended_zips"], s["recommended_zips_with_reviews"]) == (2, 2)


def test_empty_and_errored_runs_do_not_divide_by_zero():
    errored = dict(cov.score_profile("E", ["transit"], [], STANCES), error="ValueError: bad")
    s = cov.summarize([errored], STANCES)
    assert s["theme_coverage"] is None and s["profiles_errored"] == ["E"]


def test_duplicate_tags_count_once():
    row = cov.score_profile("P", ["transit", "transit"], ["33130"], STANCES)
    assert row["theme_tags"] == ["transit"]


# --- command line -------------------------------------------------------------

def _cli(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_ROOT / script), *args],
        capture_output=True, text=True, cwd=_ROOT,
    )


def test_coverage_cli_runs_on_the_repo_data_and_writes_json():
    out = Path(tempfile.mkdtemp()) / "nested" / "coverage.json"
    res = _cli("eval/theme_coverage.py", "--json", str(out))
    assert res.returncode == 0, res.stdout + res.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["total_pairs"] > 0
    assert len(payload["profiles"]) == len(json.loads(
        (_ROOT / "eval" / "recommendation_profiles.json").read_text(encoding="utf-8")))


def test_cli_exit_codes_for_bad_inputs():
    for script in ("eval/theme_coverage.py", "scripts/theme_extraction.py"):
        res = _cli(script, "--snippets", "no_such_file.csv")
        assert res.returncode == 2 and res.stderr.startswith("error: "), res.stderr
        assert "Traceback" not in res.stderr


def test_extraction_cli_only_writes_when_asked():
    res = _cli("scripts/theme_extraction.py")
    assert res.returncode == 0 and "wrote" not in res.stdout
    out = Path(tempfile.mkdtemp()) / "themes.csv"
    assert _cli("scripts/theme_extraction.py", "--out", str(out)).returncode == 0
    assert list(pd.read_csv(out).columns) == te.THEME_COLUMNS


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
