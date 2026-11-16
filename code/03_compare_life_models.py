# 03_compare_life_models.py
# INTERNAL tool for the team (ROADMAP Section 7, E24-E26, A16): runs the simulator on the same inputs
# under the exponential, lognormal and Weibull life models and prints, per model, the three best
# combinations and the best part in each slot, then whether the picks agree across the models.
# Users never see this; the simulator they run (02_run_simulator.py) uses the exponential.
#
# Default candidates: the parameter table's usable parts, one per qualification family (A9), at their
# Sheet2 prices (A15). Or give a candidates file as for the simulator.
#   .venv/Scripts/python code/03_compare_life_models.py --temp 55 --hours 2920
#   .venv/Scripts/python code/03_compare_life_models.py --temp 40-105 --hours 2920 --candidates file.csv

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
from functions.candidates import DEFAULT_TARGET_R, library_candidate, select  # noqa: E402
from functions.interface import describe_condition, num, parse_condition, read_candidates  # noqa: E402
from functions.library import load_library  # noqa: E402
from functions.life_models import LOGNORMAL_SIGMA, WEIBULL_BETA  # noqa: E402

pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 80)

MODELS = [("exponential", None, "exponential"),
          ("lognormal", LOGNORMAL_SIGMA["defects"], f"lognormal, sigma {LOGNORMAL_SIGMA['defects']:g} (defects)"),
          ("lognormal", LOGNORMAL_SIGMA["wear-out"], f"lognormal, sigma {LOGNORMAL_SIGMA['wear-out']:g} (wear-out)"),
          ("weibull", WEIBULL_BETA["defects"], f"Weibull, beta {WEIBULL_BETA['defects']:g} (defects)"),
          ("weibull", WEIBULL_BETA["wear-out"], f"Weibull, beta {WEIBULL_BETA['wear-out']:g} (wear-out)")]
PICKS = {"most_reliable": "Most reliable", "safest": "Safest", "cheapest": "Cheapest meeting target"}


def library_candidates():
    """The parameter table's usable parts, one per family (A9), priced from the table (A15)."""
    lib = load_library()
    usable = lib[lib["usable"]].drop_duplicates("family")
    out = []
    for _, r in usable.iterrows():
        c = library_candidate(r["part"], lib)
        if pd.notna(r["unit_price_usd"]):
            c["unit_price_usd"] = float(r["unit_price_usd"])
        out.append(c)
    return out


def compare(candidates, condition, hours, target=DEFAULT_TARGET_R):
    picks, parts = [], []
    for model, shape, label in MODELS:
        sel = select(candidates, condition, hours, target, life_model=model, shape=shape)
        for key, name in PICKS.items():
            c = sel.picks[key]
            picks.append({"model": label, "pick": name,
                          "combination": "(none meets the target)" if c is None else c["combination"],
                          "system AFR, FIT (2.5th-97.5th %)": "" if c is None else
                          f"{num(c['system_fit_estimate'])} ({num(c['system_fit_lower'])} - {num(c['system_fit_upper'])})",
                          "failures/1,000": "" if c is None else num(c["warranty_failures_estimate"]),
                          "meets target": "" if c is None else ("yes" if c["meets_target_at_confidence"] else "NO"),
                          "total cost": "" if c is None else f"${c['total_cost_estimate']:,.0f}"})
        best = sel.candidates[sel.candidates["rank_in_slot"] == 1]
        for _, r in best.iterrows():
            parts.append({"model": label, "slot": r["slot"], "best part": r["name"],
                          "AFR, FIT": num(r["fit_estimate"])})
    return pd.DataFrame(picks), pd.DataFrame(parts)


def agreement(picks):
    rows = []
    for name in PICKS.values():
        combos = picks.loc[picks["pick"] == name, "combination"]
        rows.append({"pick": name, "same under every model": "yes" if combos.nunique() == 1 else "NO",
                     "different combinations": combos.nunique()})
    return pd.DataFrame(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Internal: compare the exponential, lognormal and Weibull models")
    ap.add_argument("--temp", required=True, help="operating temperature in C, or a band min-max")
    ap.add_argument("--hours", type=float, required=True, help="mission hours")
    ap.add_argument("--candidates", help="candidates file (default: the parameter table's parts)")
    ap.add_argument("--target", type=float, default=DEFAULT_TARGET_R)
    args = ap.parse_args(argv)
    cands = read_candidates(args.candidates) if args.candidates else library_candidates()
    condition = parse_condition(args.temp)
    picks, parts = compare(cands, condition, args.hours, args.target)
    print(f"Life-model comparison (internal) | {describe_condition(condition)} for {args.hours:,.0f} h | "
          f"target R >= {args.target} with 95% confidence")
    print("AFR = average failure rate over the mission (Lesson 12); for the exponential it is the FIT.\n")
    print(picks.to_string(index=False))
    print("\nBest part in each slot\n" + parts.pivot(index="slot", columns="model", values="best part")
          .reindex(columns=[m[2] for m in MODELS]).to_string())
    print("\nDo the picks agree across the models?\n" + agreement(picks).to_string(index=False))


if __name__ == "__main__":
    main()
