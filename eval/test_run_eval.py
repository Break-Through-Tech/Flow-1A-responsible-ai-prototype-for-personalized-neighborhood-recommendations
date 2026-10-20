"""Checks for the Layer 1 eval harness.

Run from the repo root (also collected by pytest if it is installed):

    python eval/test_run_eval.py
"""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval import run_eval as h

BASE = {
    "profile_id": "T1",
    "budget_max": 2500,
    "household": "with_co_leaser",
    "housing_preference": "own_apartment",
    "tags": ["transit", "walkable"],
    "expected_relevant_zips": ["33130", "33128", "33127"],
    "not_relevant_zips": ["33186", "33156"],
}


def _profile(**changes) -> dict:
    p = dict(BASE, **changes)
    return {k: v for k, v in p.items() if v is not ...}


def _write(profiles) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    f.write(profiles if isinstance(profiles, str) else json.dumps(profiles))
    f.close()
    return Path(f.name)


def _load(*profiles) -> list[dict]:
    return h.load_profiles(_write(list(profiles)))


def _rejects(profiles, fragment: str) -> None:
    try:
        h.load_profiles(_write(profiles))
    except ValueError as exc:
        assert fragment in str(exc), f"expected {fragment!r} in {exc}"
    else:
        raise AssertionError(f"accepted a fixture that should fail on {fragment!r}")


def _ref():
    return h.load_reference(h.AREA_PATH, h.PUBLIC_PATH)


def _run(*profiles, top_k: int = 5) -> tuple[list[dict], dict, str]:
    rows = [h.evaluate_profile(p, _ref(), top_k, None) for p in _load(*profiles)]
    summary = h.summarize(rows, top_k)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        h.render(rows, summary, top_k)
    return rows, summary, out.getvalue()


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_ROOT / "eval" / "run_eval.py"), *args],
        capture_output=True, text=True,
    )


def test_precision_at_k():
    rel = {"a", "b"}
    assert h.precision_at_k(["a", "b", "c"], rel, 3) == 2 / 3
    assert h.precision_at_k(["c", "d", "a"], rel, 3) == 1 / 3
    assert h.precision_at_k(["a", "b", "c", "d", "e"], rel, 5) == 0.4
    assert h.precision_at_k(["c", "d", "e", "a"], rel, 3) == 0.0   # hit below the cutoff
    assert h.precision_at_k(["a"], rel, 5) == 0.2                  # short list keeps k as the denominator
    assert h.precision_at_k([], rel, 3) == 0.0
    assert h.precision_at_k(["a", "b"], set(), 3) == 0.0


def test_fixture_zips_are_normalised():
    (p,) = _load(_profile(expected_relevant_zips=[33130, "33128", 33130], not_relevant_zips=[33186]))
    assert p["expected_relevant_zips"] == ["33130", "33128"]
    assert p["not_relevant_zips"] == ["33186"]


def test_integer_zips_score_the_same_as_strings():
    as_str, _, _ = _run(_profile())
    as_int, _, _ = _run(_profile(expected_relevant_zips=[33130, 33128, 33127], not_relevant_zips=[33186, 33156]))
    assert as_int[0]["precision"] == as_str[0]["precision"]
    assert as_int[0]["precision_ceiling"] == as_str[0]["precision_ceiling"] == {3: 1.0, 5: 0.6}


def test_not_relevant_zips_is_optional():
    (p,) = _load(_profile(not_relevant_zips=...))
    assert p["not_relevant_zips"] == []
    rows, _, _ = _run(_profile(not_relevant_zips=...))
    assert rows[0]["status"] == "ok" and rows[0]["false_positives"] == []


def test_malformed_fixtures_are_rejected():
    _rejects("{not json", "not valid JSON")
    _rejects([], "non-empty list")
    _rejects({"profile_id": "T1"}, "non-empty list")
    _rejects(["T1"], "must be an object")
    _rejects([_profile(profile_id=...)], "missing profile_id")
    _rejects([_profile(), _profile()], "duplicate profile_id")
    _rejects([_profile(expected_relevant_zips=...)], "missing keys ['expected_relevant_zips']")
    _rejects([_profile(budget_max=...)], "missing keys ['budget_max']")
    _rejects([_profile(budget_max="2500")], "budget_max must be a number")
    _rejects([_profile(budget_max=True)], "budget_max must be a number")
    _rejects([_profile(tags="transit")], "tags must be a list")
    _rejects([_profile(expected_relevant_zips="33130")], "must be a list of ZIP codes")
    _rejects([_profile(expected_relevant_zips=[33130.0])], "non-ZIP value")


def test_profile_with_nothing_in_budget_does_not_crash():
    rows, summary, text = _run(_profile(budget_max=1))
    r = rows[0]
    assert r["status"] == "ok" and r["returned_zips"] == []
    assert r["mean_cosine"] is None and r["precision"] == {3: 0.0, 5: 0.0}
    assert r["budget_pass"] is True
    assert summary["mean_cosine"] is None and summary["budget_filter_pass_rate"] == 1.0
    assert "no ZIP is within budget" in text


def test_empty_profile_does_not_skew_mean_cosine():
    alone, alone_summary, _ = _run(_profile())
    _, mixed_summary, _ = _run(_profile(), _profile(profile_id="T2", budget_max=1))
    assert mixed_summary["mean_cosine"] == alone_summary["mean_cosine"] == alone[0]["mean_cosine"]
    assert mixed_summary["precision"][3] == alone_summary["precision"][3] / 2


def test_budget_violation_is_caught_against_the_reference():
    (p,) = _load(_profile())
    ref = _ref()
    clean = h.evaluate_profile(p, ref, 5, None)
    assert clean["budget_pass"] is True and not clean["rent_echo_mismatches"]

    victim = clean["returned_zips"][0]
    ref.at[victim, "rent"] = p["budget_max"] + 1
    doctored = h.evaluate_profile(p, ref, 5, None)
    assert doctored["budget_pass"] is False
    assert [v["zip"] for v in doctored["budget_violations"]] == [victim]
    assert [m["zip"] for m in doctored["rent_echo_mismatches"]] == [victim]
    assert h.has_budget_violation([doctored]) and not h.has_budget_violation([clean])
    assert h.summarize([clean, doctored], 5)["budget_filter_pass_rate"] == 0.5


def test_rent_exactly_at_budget_passes():
    (p,) = _load(_profile())
    ref = _ref()
    top = h.evaluate_profile(p, ref, 5, None)["returned_zips"][0]
    (edge,) = _load(_profile(budget_max=float(ref.at[top, "rent"])))
    row = h.evaluate_profile(edge, ref, 5, None)
    assert top in row["returned_zips"] and row["budget_pass"] is True
    assert h.is_reachable(top, edge["budget_max"], ref)
    assert not h.is_reachable(top, edge["budget_max"] - 0.01, ref)


def test_errored_profile_counts_as_not_passing():
    rows, summary, text = _run(_profile(), _profile(profile_id="T2", household="nobody"))
    assert [r["status"] for r in rows] == ["ok", "ValueError"]
    assert summary["profiles_scored"] == 1 and summary["profiles_errored"] == 1
    assert summary["budget_filter_pass_rate"] == 0.5
    assert summary["precision"][3] == rows[0]["precision"][3]
    assert "[INCOMPLETE]" in text and "[BUG]" not in text


def test_every_profile_errored_still_renders():
    _, summary, text = _run(_profile(household="nobody"))
    assert summary["precision"] == {3: None, 5: None} and summary["mean_cosine"] is None
    assert summary["budget_filter_pass_rate"] == 0.0 and "n/a" in text


def test_unknown_expected_zip_is_flagged():
    rows, _, text = _run(_profile(expected_relevant_zips=["33130", "99999"]))
    assert rows[0]["unknown_relevant"] == ["99999"] and rows[0]["n_reachable_relevant"] == 1
    assert "not in the data" in text


def test_suppressed_rent_zip_is_unreachable():
    ref = _ref()
    suppressed = ref.index[ref["rent_imputed"]]
    assert len(suppressed) > 0
    assert not any(h.is_reachable(z, 10**9, ref) for z in suppressed)
    assert not h.is_reachable("99999", 10**9, ref)


def test_cli_exit_codes():
    assert _cli().returncode == 0
    assert _cli("--top-k", "3").returncode == 2
    assert _cli("--profiles", str(_write([_profile(budget_max=1)]))).returncode == 0
    assert _cli("--profiles", str(_write([_profile(household="nobody")]))).returncode == 1

    for bad in (_write("{not json"), _write([_profile(budget_max=...)]), Path("no_such_file.json")):
        res = _cli("--profiles", str(bad))
        assert res.returncode == 2 and res.stderr.startswith("error: "), res.stderr
        assert "Traceback" not in res.stderr


def test_cli_json_output_matches_the_printed_run():
    out = Path(tempfile.mkdtemp()) / "nested" / "result.json"
    assert _cli("--json", str(out)).returncode == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["profiles_total"] == len(payload["profiles"]) == 5
    assert set(payload["summary"]["precision"]) == {"3", "5"}


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
