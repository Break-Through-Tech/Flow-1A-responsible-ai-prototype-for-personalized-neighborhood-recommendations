"""Layer 1 eval harness: Precision@3/@5, mean cosine similarity, budget filter pass rate.

Metric definitions follow EVAL_FRAMEWORK.md exactly:

    Precision@k            (# relevant ZIPs in top k) / k
    Mean cosine similarity average similarity(user vector, recommended ZIP vectors)
    Budget filter pass rate % of profiles where every returned ZIP is within budget

Budget pass rate is a correctness check, not a score: anything below 100% is a
bug and this script exits non-zero. So does a profile whose expected ZIPs the
engine can never return, since that profile is out of date with the data.

Run from the repo root:

    python eval/run_eval.py
    python eval/run_eval.py --json eval/results/baseline_sep.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.feature_schema import BUDGET_COLUMN, ID_COLUMN, TAG_TO_COLUMN
from scripts.recommender import recommend

PROFILES_PATH = _ROOT / "eval" / "recommendation_profiles.json"
AREA_PATH = _ROOT / "data" / "area_features_clean.csv"
PUBLIC_PATH = _ROOT / "data" / "miami_dade_public_features.csv"
PRECISION_KS = (3, 5)
REQUIRED_KEYS = ("household", "housing_preference", "budget_max", "tags", "expected_relevant_zips")


def _zip_list(pid: str, key: str, value) -> list[str]:
    """ZIPs as de-duplicated strings, so a fixture written with bare numbers still matches."""
    if not isinstance(value, list):
        raise ValueError(f"{pid}: {key} must be a list of ZIP codes")
    out = []
    for z in value:
        if isinstance(z, bool) or not isinstance(z, (str, int)):
            raise ValueError(f"{pid}: {key} holds a non-ZIP value: {z!r}")
        out.append(str(z).strip())
    return list(dict.fromkeys(out))


def load_profiles(path: Path) -> list[dict]:
    """Read and validate the fixture file, so a malformed profile fails here with a clear message.

    Values the engine itself validates (household, housing_preference, budget
    range) are left alone: a bad one shows up as an errored profile instead.
    """
    try:
        profiles = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(profiles, list) or not profiles:
        raise ValueError(f"{path} must hold a non-empty list of profiles")
    seen = set()
    cleaned = []
    for p in profiles:
        if not isinstance(p, dict):
            raise ValueError(f"every profile must be an object, got: {p!r}")
        pid = p.get("profile_id")
        if not pid or not isinstance(pid, str):
            raise ValueError(f"profile missing profile_id: {p}")
        if pid in seen:
            raise ValueError(f"duplicate profile_id: {pid}")
        seen.add(pid)
        missing = [k for k in REQUIRED_KEYS if k not in p]
        if missing:
            raise ValueError(f"{pid}: missing keys {missing}")
        budget = p["budget_max"]
        if isinstance(budget, bool) or not isinstance(budget, (int, float)):
            raise ValueError(f"{pid}: budget_max must be a number, got {budget!r}")
        if not isinstance(p["tags"], list) or not all(isinstance(t, str) for t in p["tags"]):
            raise ValueError(f"{pid}: tags must be a list of strings")
        p = dict(p)
        p["expected_relevant_zips"] = _zip_list(pid, "expected_relevant_zips", p["expected_relevant_zips"])
        p["not_relevant_zips"] = _zip_list(pid, "not_relevant_zips", p.get("not_relevant_zips", []))
        cleaned.append(p)
    return cleaned


def load_reference(area_path: Path, public_path: Path) -> pd.DataFrame:
    """Rent, population and the suppression flag per ZIP, read independently of the recommender."""
    area = pd.read_csv(area_path, dtype={ID_COLUMN: str})
    absent = [c for c in (ID_COLUMN, BUDGET_COLUMN) if c not in area.columns]
    if absent:
        raise ValueError(f"{area_path} is missing columns {absent}")
    area = area.set_index(ID_COLUMN)
    ref = pd.DataFrame(index=area.index)
    ref["rent"] = area[BUDGET_COLUMN]
    flag = f"{BUDGET_COLUMN}_suppressed"
    ref["rent_imputed"] = area[flag].astype(bool) if flag in area.columns else False
    if public_path.exists():
        pop = pd.read_csv(public_path, dtype={ID_COLUMN: str}).set_index(ID_COLUMN)["population"]
        ref["population"] = pop.reindex(ref.index)
    else:
        ref["population"] = pd.NA
    return ref


def precision_at_k(returned: list[str], relevant: set[str], k: int) -> float:
    return len([z for z in returned[:k] if z in relevant]) / k


def _usd(x: float) -> str:
    return f"${x:,.0f}" if float(x).is_integer() else f"${x:,.2f}"


def unreachable_reason(zip_code: str, budget: float, ref: pd.DataFrame) -> str | None:
    """Why the engine could never return this ZIP, or None if it could.

    Mirrors the engine's budget filter. The engine drops ZIPs whose rent was
    imputed rather than measured, so a ZIP with a suppressed rent is
    unreachable even when the imputed value fits.
    """
    if zip_code not in ref.index:
        return "not in the data (typo?)"
    if bool(ref.at[zip_code, "rent_imputed"]):
        return "rent is suppressed, so the engine never returns it"
    rent = float(ref.at[zip_code, "rent"])
    if rent > budget:
        return f"rent {_usd(rent)} is over the {_usd(budget)} budget"
    return None


def is_reachable(zip_code: str, budget: float, ref: pd.DataFrame) -> bool:
    """Whether the engine could return this ZIP at all."""
    return unreachable_reason(zip_code, budget, ref) is None


def unreachable_relevant(profile: dict, ref: pd.DataFrame) -> list[dict]:
    """Expected ZIPs the engine can never return: a stale or mistaken profile, not a ranking miss.

    These usually appear after a data refresh moves rents past a budget that
    was set by hand, so they fail the run rather than quietly lowering the
    precision ceiling.
    """
    out = []
    for z in profile["expected_relevant_zips"]:
        reason = unreachable_reason(z, profile["budget_max"], ref)
        if reason:
            out.append({"zip": z, "reason": reason})
    return out


def unscored_tags(profile: dict) -> list[str]:
    return [
        t for t in profile["tags"]
        if TAG_TO_COLUMN.get(t) is None and t != profile["housing_preference"]
    ]


def evaluate_profile(profile: dict, ref: pd.DataFrame, top_k: int, data_path: Path | None) -> dict:
    relevant = set(profile["expected_relevant_zips"])
    not_relevant = set(profile["not_relevant_zips"])
    budget = profile["budget_max"]
    unreachable = unreachable_relevant(profile, ref)

    row = {
        "profile_id": profile["profile_id"],
        "budget_max": budget,
        "n_relevant": len(relevant),
        "n_reachable_relevant": len(relevant) - len(unreachable),
        "unreachable_relevant": unreachable,
        "unknown_relevant": [z for z in profile["expected_relevant_zips"] if z not in ref.index],
        "unscored_tags": unscored_tags(profile),
        "status": "ok",
        "error": None,
        "returned_zips": [],
        "precision": {},
        "precision_ceiling": {},
        "mean_cosine": None,
        "budget_pass": None,
        "budget_violations": [],
        "rent_echo_mismatches": [],
        "false_positives": [],
        "unreachable_negatives": [],
        "recommended_with_imputed_rent": [],
        "recommended_zero_population": [],
    }

    request = {k: profile[k] for k in ("household", "housing_preference", "budget_max", "tags")}
    try:
        result = recommend(request, top_k=top_k, data_path=data_path)
    except Exception as exc:
        row["status"] = f"{type(exc).__name__}"
        row["error"] = str(exc)
        return row

    recs = result["recommendations"]
    zips = [r["zip"] for r in recs]
    row["returned_zips"] = zips
    row["engine_status"] = result["status"]
    row["candidate_count"] = result["candidate_count"]
    row["active_features"] = result["active_features"]

    for k in PRECISION_KS:
        row["precision"][k] = precision_at_k(zips, relevant, k)
        row["precision_ceiling"][k] = min(row["n_reachable_relevant"], k) / k

    sims = [r["similarity"] for r in recs]
    row["mean_cosine"] = statistics.fmean(sims) if sims else None

    # Budget is checked against the CSV, not the value the engine echoes back,
    # then the echo is compared separately so a mismatch cannot hide.
    for r in recs:
        z = r["zip"]
        true_rent = float(ref.at[z, "rent"]) if z in ref.index else None
        if true_rent is None:
            row["budget_violations"].append({"zip": z, "rent": None, "reason": "zip not in reference data"})
        elif true_rent > budget:
            row["budget_violations"].append({"zip": z, "rent": true_rent, "budget": budget})
        if true_rent is not None and abs(true_rent - r["median_rent_usd"]) > 1e-9:
            row["rent_echo_mismatches"].append(
                {"zip": z, "engine": r["median_rent_usd"], "reference": true_rent}
            )
        if z in ref.index and bool(ref.at[z, "rent_imputed"]):
            row["recommended_with_imputed_rent"].append(z)
        pop = ref.at[z, "population"] if z in ref.index else None
        if pop is not None and pd.notna(pop) and int(pop) == 0:
            row["recommended_zero_population"].append(z)

    row["budget_pass"] = not row["budget_violations"]
    row["false_positives"] = [z for z in zips if z in not_relevant]
    row["unreachable_negatives"] = [
        z for z in profile["not_relevant_zips"] if not is_reachable(z, budget, ref)
    ]
    return row


def summarize(rows: list[dict], top_k: int) -> dict:
    scored = [r for r in rows if r["status"] == "ok"]
    pooled = [s for r in scored for s in [r["mean_cosine"]] if s is not None]

    summary = {
        "profiles_total": len(rows),
        "profiles_scored": len(scored),
        "profiles_errored": len(rows) - len(scored),
        "top_k": top_k,
        "precision": {}, "precision_ceiling": {},
        "mean_cosine": statistics.fmean(pooled) if pooled else None,
        "budget_filter_pass_rate": None,
        "budget_profiles_passing": 0,
        "profiles_with_unreachable_expected": [r["profile_id"] for r in rows if r["unreachable_relevant"]],
    }
    for k in PRECISION_KS:
        vals = [r["precision"][k] for r in scored]
        ceil = [r["precision_ceiling"][k] for r in scored]
        summary["precision"][k] = statistics.fmean(vals) if vals else None
        summary["precision_ceiling"][k] = statistics.fmean(ceil) if ceil else None

    # Errored profiles count as failures: the engine returned nothing to check.
    passing = sum(1 for r in rows if r["status"] == "ok" and r["budget_pass"])
    summary["budget_profiles_passing"] = passing
    summary["budget_filter_pass_rate"] = passing / len(rows) if rows else None
    return summary


def has_budget_violation(rows: list[dict]) -> bool:
    return any(r["budget_violations"] for r in rows)


def render(rows: list[dict], summary: dict, top_k: int) -> None:
    print(f"Layer 1 eval: {summary['profiles_total']} profiles, top_k={top_k}\n")

    head = f"{'profile':<26}{'P@3':>7}{'P@5':>7}{'cosine':>9}{'budget':>9}{'cands':>7}  active"
    print(head)
    print("-" * len(head))
    for r in rows:
        if r["status"] != "ok":
            print(f"{r['profile_id']:<26}{'-':>7}{'-':>7}{'-':>9}{'ERROR':>9}{'-':>7}  {r['status']}")
            continue
        print(
            f"{r['profile_id']:<26}"
            f"{r['precision'][3]:>7.3f}{r['precision'][5]:>7.3f}"
            f"{(format(r['mean_cosine'], '.4f') if r['mean_cosine'] is not None else '-'):>9}"
            f"{('pass' if r['budget_pass'] else 'FAIL'):>9}"
            f"{r['candidate_count']:>7}  {','.join(r['active_features'])}"
        )

    print("\n--- headline metrics ---")
    for k in PRECISION_KS:
        got, ceil = summary["precision"][k], summary["precision_ceiling"][k]
        if got is None:
            print(f"  Precision@{k}            n/a   (no profile scored)")
            continue
        share = f"{got / ceil:.1%} of ceiling" if ceil else "n/a"
        print(f"  Precision@{k}            {got:.3f}   (ceiling {ceil:.3f}, {share})")
    cosine = summary["mean_cosine"]
    print(f"  Mean cosine similarity  {f'{cosine:.4f}' if cosine is not None else 'n/a'}")
    rate = summary["budget_filter_pass_rate"]
    verdict = "OK" if rate == 1.0 else "BUG" if has_budget_violation(rows) else "INCOMPLETE"
    print(f"  Budget filter pass rate {rate:.1%}   "
          f"({summary['budget_profiles_passing']}/{summary['profiles_total']} profiles)  [{verdict}]")
    if summary["profiles_errored"]:
        print(f"  {summary['profiles_errored']} profile(s) errored and count as not passing")
    stale = summary["profiles_with_unreachable_expected"]
    if stale:
        print(f"  {len(stale)} profile(s) expect ZIPs the engine can never return: "
              f"{', '.join(stale)}  [STALE PROFILE]")

    print("\n--- diagnostics ---")
    any_note = False
    for r in rows:
        notes = []
        if r["status"] != "ok":
            notes.append(f"errored: {r['status']}: {r['error']}")
        if r["status"] == "ok" and not r["returned_zips"]:
            notes.append(
                "no ZIP is within budget, so nothing was recommended: precision is 0, "
                "cosine is undefined, and the budget check passes with nothing to check"
            )
        elif r["status"] == "ok" and len(r["returned_zips"]) < top_k:
            notes.append(
                f"only {len(r['returned_zips'])} ZIPs are within budget, fewer than top_k={top_k}"
            )
        for u in r["unreachable_relevant"]:
            notes.append(f"EXPECTED ZIP UNREACHABLE: {u['zip']}: {u['reason']}")
        if r["budget_violations"]:
            notes.append(f"BUDGET VIOLATION: {r['budget_violations']}")
        if r["rent_echo_mismatches"]:
            notes.append(f"rent echo disagrees with CSV: {r['rent_echo_mismatches']}")
        if r["n_relevant"] < max(PRECISION_KS):
            notes.append(f"{r['n_relevant']} relevant ZIPs caps P@5 at {min(r['n_relevant'],5)/5:.2f}")
        if r["unscored_tags"]:
            notes.append(f"tags expressed but not scored: {r['unscored_tags']}")
        if r["status"] == "ok" and len(r["active_features"]) == 1:
            notes.append(
                "one active feature, so cosine ranks by how concentrated a ZIP is on that "
                "feature rather than how high it scores; restricted to that one dimension "
                "cosine would be 1.0 for every candidate"
            )
        if r["false_positives"]:
            notes.append(f"returned ZIPs marked not_relevant: {r['false_positives']}")
        if r["unreachable_negatives"]:
            notes.append(
                f"not_relevant ZIPs excluded by budget anyway, so they are weak negatives: "
                f"{r['unreachable_negatives']}"
            )
        if r["recommended_with_imputed_rent"]:
            notes.append(f"recommended on imputed rent: {r['recommended_with_imputed_rent']}")
        if r["recommended_zero_population"]:
            notes.append(f"ZERO-POPULATION ZIPs recommended: {r['recommended_zero_population']}")
        if notes:
            any_note = True
            print(f"  {r['profile_id']}")
            for n in notes:
                print(f"    - {n}")
    if not any_note:
        print("  none")


def main() -> int:
    ap = argparse.ArgumentParser(description="Layer 1 recommendation-engine eval")
    ap.add_argument("--profiles", type=Path, default=PROFILES_PATH)
    ap.add_argument("--data", type=Path, default=None, help="override the ZIP feature CSV")
    ap.add_argument("--top-k", type=int, default=max(PRECISION_KS),
                    help="rank deeper; mean cosine averages over all top-k, so compare runs at the same value")
    ap.add_argument("--json", type=Path, default=None, help="also write the full result as JSON")
    args = ap.parse_args()

    if args.top_k < max(PRECISION_KS):
        ap.error(f"--top-k must be at least {max(PRECISION_KS)} to compute Precision@{max(PRECISION_KS)}")

    try:
        profiles = load_profiles(args.profiles)
        ref = load_reference(args.data or AREA_PATH, PUBLIC_PATH)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    rows = [evaluate_profile(p, ref, args.top_k, args.data) for p in profiles]
    summary = summarize(rows, args.top_k)
    render(rows, summary, args.top_k)

    if args.json:
        payload = {"summary": summary, "profiles": rows}
        try:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"error: could not write {args.json}: {exc}", file=sys.stderr)
            return 2
        print(f"\nwrote {args.json}")

    failures = []
    if has_budget_violation(rows):
        failures.append("budget filter pass rate is below 100%, which is a bug rather than a metric.")
    if summary["profiles_errored"]:
        failures.append(f"{summary['profiles_errored']} profile(s) errored, so the run is incomplete.")
    if stale := summary["profiles_with_unreachable_expected"]:
        failures.append(
            f"{len(stale)} profile(s) expect ZIPs the engine can never return, usually because "
            "rents changed since the budget was set. Update the budget or the expected ZIPs."
        )
    if failures:
        print()
        for f in failures:
            print(f"FAILED: {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
