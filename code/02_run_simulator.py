# 02_run_simulator.py
# TASER-EV reliability simulator (ROADMAP Section 2). A vehicle maker enters candidate suppliers for
# any of the six component slots, from each supplier's reliability report, plus their own operating
# temperature and how long the part must work. The simulator puts every candidate on that same
# condition and reports which is most reliable, whether it meets the target, and the warranty
# exposure and total cost, all with 95% confidence intervals. Engine: functions/candidates.py.
#
# Ask me everything:   .venv/Scripts/python code/02_run_simulator.py
# From a file:         .venv/Scripts/python code/02_run_simulator.py --temp 200 --hours 1000
#                          --candidates data/examples/candidates_example.csv
# Optional:            --target 0.999 --fleet 1000 --replacement-cost 500 --warranty-hours 2920 --details

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
from functions.candidates import DEFAULT_FLEET, DEFAULT_TARGET_R, select  # noqa: E402
from functions.interface import (candidate_table, combination_table, key_table,  # noqa: E402
                                 parse_profile, read_candidates, reliability_table, summary_text)
from functions.library import SLOTS  # noqa: E402
from functions.simulator import N_DRAWS, SEED  # noqa: E402

RUNS = ROOT / "results" / "tables" / "runs"
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_colwidth", 60)


def ask(prompt, default=None, required=False):
    """Ask once; Enter gives the default. Required questions repeat until answered."""
    while True:
        hint = f" [{default}]" if default is not None else (" (required)" if required else " [Enter = skip]")
        text = input(f"{prompt}{hint}: ").strip()
        if text:
            return text
        if default is not None:
            return str(default)
        if not required:
            return ""
        print("  This one is needed.")


def ask_number(prompt, default=None, required=False, kind=float):
    while True:
        text = ask(prompt, default, required)
        if text == "":
            return None
        try:
            return kind(text)
        except ValueError:
            print("  Please enter a number.")


def ask_profile():
    while True:
        text = ask("Operating temperature in C (e.g. 200), or a profile 'temperature:share,...' "
                   "(e.g. 40:50,70:30,105:20)", required=True)
        try:
            return parse_profile(text)
        except ValueError:
            print("  Not understood. Enter one number, or temperature:share pairs separated by commas.")


def ask_candidate(slot, i):
    print(f"\n  {slot}, candidate {i}")
    c = {"slot": slot,
         "name": ask("    Name (part number or supplier)", required=True),
         "test_temp_c": ask_number("    Test temperature in the report, C", required=True)}
    kind = ask("    What does the report give? 1 = test results (hours, sample size, failures), "
               "2 = a FIT value, 3 = an MTTF/MTBF in hours", 1)
    if kind == "2":
        c["fit"] = ask_number("    FIT", required=True)
    elif kind == "3":
        c["mttf_hours"] = ask_number("    MTTF/MTBF, hours", required=True)
    else:
        c["test_hours"] = ask_number("    Test duration per device, hours", required=True)
        c["sample_size"] = ask_number("    Sample size (devices)", required=True)
    c["failures"] = ask_number("    Failures in the test", 0, kind=int)
    if kind in ("2", "3"):
        c["ref_temp_c"] = ask_number("    Temperature that value is stated at, C", c["test_temp_c"])
        c["conf_level"] = ask_number("    Confidence level that value is stated at (0-1)", 0.6)
    c["ea_ev"] = ask_number("    Activation energy Ea in eV, if the report states one (Enter = 0.7 eV with uncertainty)")
    c["unit_price_usd"] = ask_number("    Unit price in USD (Enter = price list)")
    return c


def ask_everything():
    print("TASER-EV reliability simulator")
    print("Compare candidate suppliers' parts at YOUR operating condition.\n")
    inputs = {"profile": ask_profile(),
              "hours": ask_number("How many hours must the part work at this temperature?", required=True)}
    print("\nOptional settings (press Enter to keep the default):")
    inputs["target"] = ask_number("  Required reliability over those hours", DEFAULT_TARGET_R)
    inputs["fleet"] = ask_number("  Vehicles, for warranty exposure", DEFAULT_FLEET, kind=int)
    inputs["replacement_cost"] = ask_number("  Cost of one warranty replacement in USD (Enter = the part's unit price)")
    inputs["warranty_hours"] = ask_number("  Warranty period in operating hours (Enter = the hours above)")
    print("\nCandidates: for each component, how many suppliers are you comparing? "
          "(0 = not part of this decision)")
    candidates = []
    for slot in SLOTS:
        k = ask_number(f"  {slot}", 0, kind=int)
        candidates += [ask_candidate(slot, i) for i in range(1, k + 1)]
    if not candidates:
        sys.exit("No candidates entered.")
    inputs["candidates"] = candidates
    inputs["details"] = ask("\nShow full details too? (y/n)", "n").lower().startswith("y")
    return inputs


def report(sel, details):
    print("\n" + "=" * 100 + "\nSUMMARY\n" + "=" * 100)
    print(summary_text(sel))
    print("\n" + "-" * 100 + "\nAll candidates\n" + "-" * 100)
    print(key_table(sel).to_string(index=False))
    if details:
        print("\n" + "-" * 100 + "\nDetails 1: reliability at your condition (median, 95% CI)\n" + "-" * 100)
        print(reliability_table(sel).to_string(index=False))
        print("\n" + "-" * 100 + "\nDetails 2: requirement check, prices and warranty exposure\n" + "-" * 100)
        print(candidate_table(sel).to_string(index=False))
        print("\n" + "-" * 100 + "\nDetails 3: system combinations, most reliable first\n" + "-" * 100)
        print(combination_table(sel).to_string(index=False))
    RUNS.mkdir(parents=True, exist_ok=True)
    stem = RUNS / datetime.now().strftime("run_%Y%m%d_%H%M%S")
    sel.candidates.to_csv(f"{stem}_candidates.csv", index=False)
    sel.combinations.to_csv(f"{stem}_combinations.csv", index=False)
    print(f"\nFull results saved to {Path(stem).relative_to(ROOT)}_candidates.csv and _combinations.csv"
          + ("" if details else " (or rerun with --details to print them)"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="TASER-EV reliability simulator: compare candidate suppliers "
                                             "at your operating condition")
    ap.add_argument("--temp", help="operating temperature in C, or a profile 'T:share,...'")
    ap.add_argument("--hours", type=float, help="hours the part must work at that temperature")
    ap.add_argument("--candidates", help="CSV of candidates (template: data/examples/candidates_example.csv)")
    ap.add_argument("--target", type=float, default=DEFAULT_TARGET_R, help="required reliability (default 0.999)")
    ap.add_argument("--fleet", type=int, default=DEFAULT_FLEET, help="vehicles for warranty exposure (default 1000)")
    ap.add_argument("--replacement-cost", type=float, help="cost of one warranty replacement, USD (default: the part's unit price)")
    ap.add_argument("--warranty-hours", type=float, help="warranty period in operating hours (default: --hours)")
    ap.add_argument("--details", action="store_true", help="also print the full detail tables")
    ap.add_argument("--draws", type=int, default=N_DRAWS)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args(argv)

    if args.temp is None and args.candidates is None:
        x = ask_everything()
    else:
        if not (args.temp and args.hours and args.candidates):
            ap.error("with a file, give --temp, --hours and --candidates (or no arguments to be asked)")
        x = {"profile": parse_profile(args.temp), "hours": args.hours, "target": args.target,
             "fleet": args.fleet, "replacement_cost": args.replacement_cost, "warranty_hours": args.warranty_hours,
             "candidates": read_candidates(args.candidates), "details": args.details}
    sel = select(x["candidates"], x["profile"], x["hours"], x["target"], warranty_hours=x["warranty_hours"],
                 fleet_size=x["fleet"], replacement_cost=x["replacement_cost"], n_draws=args.draws, seed=args.seed)
    report(sel, x["details"])


if __name__ == "__main__":
    main()
