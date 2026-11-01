# 02_run_simulator.py
# TASER-EV simulator, command-line version (ROADMAP Section 2). Asks for the operating temperature
# (or a profile) and the parts, then prints and saves every output with 95% CIs.
#   Mode 1  evaluate one configuration of library parts
#   Mode 2  compare two configurations
#   Mode 3  supplier selection: the user's own candidates from their reliability reports, put on the
#           user's condition, checked against a reliability target, with warranty exposure
#
# Interactive:   .venv/Scripts/python code/02_run_simulator.py
# One command:   .venv/Scripts/python code/02_run_simulator.py --temp 55
#                .venv/Scripts/python code/02_run_simulator.py --temp "40:50,70:30,105:20"
#                .venv/Scripts/python code/02_run_simulator.py --temp 55 --compare "ECU MCU=R7F7016903AFP-C"
# --compare gives the slots that B changes from A (A is the default all-TI configuration).
# Mode 3 from a file:
#                .venv/Scripts/python code/02_run_simulator.py --temp 200 --candidates data/examples/candidates_example.csv
#                    --mission-hours 1000 --target-r 0.999 --fleet 100000 --cost 1000
# Mode 3 always requires 95% confidence that the target is met (A13); it is not an input.

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
from functions.candidates import (CONFIDENCE, DEFAULT_TARGET_R, library_candidate,  # noqa: E402
                                  select)
from functions.interface import (DEFAULT_CONFIG, candidate_table, combination_table, reliability_table,  # noqa: E402
                                 component_table, describe_profile, difference_table, parse_profile,
                                 read_candidates, system_table)
from functions.library import SLOTS, load_library  # noqa: E402
from functions.simulator import (DEFAULT_WARRANTY_HOURS, N_DRAWS, SEED, compare,  # noqa: E402
                                 draw_library, evaluate)

TABLES = ROOT / "results" / "tables" / "runs"
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_colwidth", 45)


def ask(prompt, default=None):
    text = input(f"{prompt}" + (f" [{default}]" if default is not None else "") + ": ").strip()
    return text if text else ("" if default is None else str(default))


def ask_number(prompt, default=None, kind=float, optional=False):
    while True:
        text = ask(prompt, default)
        if text == "" and optional:
            return None
        try:
            return kind(text)
        except ValueError:
            print("  Enter a number" + (" (or press Enter to skip)" if optional else "") + ".")


def ask_profile():
    while True:
        text = ask("Operating temperature in C (e.g. 55), or a profile 'T:share, ...' "
                   "(e.g. 40:50,70:30,105:20)", 55)
        try:
            return parse_profile(text)
        except ValueError:
            print("  Not understood. Enter a number, or temperature:share pairs separated by commas.")


def ask_config(lib, label, start):
    """Pick a part for each slot; Enter keeps the default, 0 leaves the slot empty."""
    print(f"\nConfiguration {label}: choose a part for each slot "
          "(Enter = keep the shown default, 0 = leave the slot empty).")
    config = {}
    for slot in SLOTS:
        parts = lib[(lib["slot"] == slot) & lib["usable"]].reset_index(drop=True)
        print(f"\n  {slot}:")
        for i, r in parts.iterrows():
            print(f"    {i + 1}. {r['part']:20s} {r['supplier']}")
        default = start.get(slot)
        default_no = int(parts.index[parts["part"] == default][0]) + 1 if default in set(parts["part"]) else 0
        while True:
            choice = ask(f"  Part number for {slot}", default_no)
            if choice.isdigit() and 0 <= int(choice) <= len(parts):
                break
            print("  Enter one of the numbers listed.")
        if int(choice) > 0:
            config[slot] = parts.loc[int(choice) - 1, "part"]
    if not config:
        print("  At least one slot is needed; using the default configuration.")
        return dict(start)
    return config


def ask_candidates(lib):
    """Mode 3: as many candidates per slot as the user likes; 0 skips the slot (left out of the system)."""
    print("\nEnter your candidate suppliers. For each slot, give how many candidates you have "
          "(0 = skip the slot; skipped slots are left out of the system).")
    candidates = []
    for slot in SLOTS:
        k = ask_number(f"\n  How many candidates for {slot}?", 0, int)
        for i in range(1, k + 1):
            print(f"\n  {slot}, candidate {i}:")
            how = ask("    Data source: 1 = part from our library, 2 = raw test data from a report, "
                      "3 = FIT or MTTF from a report", 2)
            if how == "1":
                parts = lib[(lib["slot"] == slot) & lib["usable"]].reset_index(drop=True)
                for j, r in parts.iterrows():
                    print(f"      {j + 1}. {r['part']:20s} {r['supplier']}")
                j = ask_number("    Library part number", 1, int)
                candidates.append(library_candidate(parts.loc[j - 1, "part"], lib))
                continue
            c = {"slot": slot, "name": ask("    Name (supplier / part)", f"{slot} candidate {i}"),
                 "test_temp_c": ask_number("    Test (stress) temperature, C", 125)}
            if how == "3":
                kind = ask("    Report gives: 1 = FIT, 2 = MTTF/MTBF in hours", 1)
                if kind == "2":
                    c["mttf_hours"] = ask_number("    MTTF/MTBF, hours")
                else:
                    c["fit"] = ask_number("    FIT (failures per 1e9 h)")
                c["ref_temp_c"] = ask_number("    Temperature that value refers to, C", c["test_temp_c"])
                c["conf_level"] = ask_number("    Confidence level of that value (0-1)", 0.6)
                c["failures"] = ask_number("    Failures in the test", 0, int)
            else:
                c["test_hours"] = ask_number("    Test duration per device, hours", 1000)
                c["sample_size"] = ask_number("    Sample size (devices)", 231)
                c["failures"] = ask_number("    Failures", 0, int)
            c["ea_ev"] = ask_number("    Activation energy Ea in eV, if the report states one "
                                    "(Enter = library default)", None, optional=True)
            candidates.append(c)
    return candidates


def show_evaluation(ev, title):
    print(f"\n=== {title} ===")
    print("Components (median, 95% CI in brackets):")
    print(component_table(ev).to_string(index=False))
    print("\nSystem (series of the selected slots):")
    print(system_table(ev).to_string(index=False))


def run_selection(candidates, profile, mission, target, t_w, fleet, cost, n_draws, seed):
    conf = CONFIDENCE
    sel = select(candidates, profile, mission, target, warranty_hours=t_w, fleet_size=fleet,
                 cost_per_failure=cost, n_draws=n_draws, seed=seed)
    print(f"\nOperating condition: {describe_profile(profile)} | mission {mission:,.0f} h | "
          f"target R(mission) >= {target} with {conf:.0%} confidence | {n_draws:,} draws, seed {seed}")
    if fleet:
        print(f"Warranty exposure: {fleet:,} vehicles over {sel.settings['warranty_hours']:,.0f} h"
              + (f", {cost:,.0f} per failure" if cost else ""))
    for w in sel.warnings:
        print(f"Note: {w}")
    print(f"\n=== 1. Reliability of each candidate at {describe_profile(profile)} "
          "(moved from its own test temperature by AF; median and 95% CI) ===")
    print(reliability_table(sel).to_string(index=False))
    print(f"\n=== 2. Requirement check and ranking within each slot (target R >= {target}, {conf:.0%} confidence) ===")
    print(candidate_table(sel).to_string(index=False))
    print("\n=== 3. Best combinations (one candidate per entered slot, series system) ===")
    print(combination_table(sel).to_string(index=False))
    best = sel.combinations.iloc[0]
    print(f"\nBest combination: {best['combination']}\n"
          f"  System R({mission:,.0f} h) = {best['system_r_mission_median']:.5f} "
          f"(95% CI {best['system_r_mission_lower']:.5f} - {best['system_r_mission_upper']:.5f}), "
          f"{conf:.0%} lower bound {best['system_r_lower_bound']:.5f}\n"
          f"  Target R >= {target}: {'met' if best['meets_target_at_confidence'] else 'not met'} "
          f"at {conf:.0%} confidence | P(best combination) = {best['p_best_combination']:.3f}")
    return sel


def save(stem, frames):
    TABLES.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, df in frames.items():
        path = TABLES / f"{stem}_{name}.csv"
        df.to_csv(path, index=False)
        paths.append(path)
    print(f"\nSaved {len(paths)} tables to {TABLES.relative_to(ROOT)}/{stem}_*.csv")
    return paths


def parse_changes(text):
    """'ECU MCU=R7F7016903AFP-C; Gate driver=ADuM4135' -> dict; 'Gate driver=' empties a slot."""
    changes = {}
    for item in filter(None, (s.strip() for s in text.split(";"))):
        slot, part = (x.strip() for x in item.split("="))
        changes[slot] = part
    return changes


def apply_changes(base, changes):
    config = dict(base)
    for slot, part in changes.items():
        if part:
            config[slot] = part
        else:
            config.pop(slot, None)
    return config


def main(argv=None):
    ap = argparse.ArgumentParser(description="TASER-EV reliability simulator")
    ap.add_argument("--temp", help="operating temperature in C, or a profile 'T:share,...'")
    ap.add_argument("--compare", help="Mode 2: slots B changes from A, e.g. 'ECU MCU=R7F7016903AFP-C'")
    ap.add_argument("--warranty-hours", type=float, default=None,
                    help=f"Modes 1-2: warranty in operating hours (default {DEFAULT_WARRANTY_HOURS:g}); "
                         "Mode 3: warranty period for exposure (default = mission hours)")
    ap.add_argument("--candidates", help="Mode 3: CSV of candidate suppliers (see data/examples/)")
    ap.add_argument("--mission-hours", type=float, default=1000, help="Mode 3: hours the part must survive")
    ap.add_argument("--target-r", type=float, default=DEFAULT_TARGET_R, help="Mode 3: required R(mission)")
    ap.add_argument("--fleet", type=int, help="Mode 3: vehicles in the fleet, for warranty exposure")
    ap.add_argument("--cost", type=float, help="Mode 3: cost per warranty failure")
    ap.add_argument("--draws", type=int, default=N_DRAWS)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args(argv)

    lib = load_library()
    stem = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    if args.temp is None:
        print("TASER-EV reliability simulator")
        print("------------------------------")
        profile = ask_profile()
        mode = ask("Mode: 1 = evaluate one configuration, 2 = compare two configurations, "
                   "3 = choose between your own candidate suppliers", 1)
        if mode == "3":
            mission = ask_number("Mission: hours the part must survive at this condition", 1000)
            target = ask_number("Required reliability over the mission (e.g. 0.999)", DEFAULT_TARGET_R)
            fleet = ask_number("Warranty exposure: vehicles in the fleet (Enter = skip)", None, int, optional=True)
            cost = ask_number("Cost per warranty failure (Enter = skip)", None, optional=True) if fleet else None
            t_w = ask_number("Warranty period in operating hours (Enter = mission hours)", None,
                             optional=True) if fleet else None
            sel = run_selection(ask_candidates(lib), profile, mission, target, t_w, fleet, cost,
                                args.draws, args.seed)
            save(stem, {"candidates": sel.candidates, "combinations": sel.combinations})
            return
        t_w = float(ask("Warranty in operating hours (A7)", f"{DEFAULT_WARRANTY_HOURS:g}"))
        config_a = ask_config(lib, "A" if mode == "2" else "", DEFAULT_CONFIG)
        config_b = ask_config(lib, "B", config_a) if mode == "2" else None
    else:
        profile = parse_profile(args.temp)
        if args.candidates:
            sel = run_selection(read_candidates(args.candidates), profile, args.mission_hours, args.target_r,
                                args.warranty_hours, args.fleet, args.cost,
                                args.draws, args.seed)
            save(stem, {"candidates": sel.candidates, "combinations": sel.combinations})
            return
        t_w = DEFAULT_WARRANTY_HOURS if args.warranty_hours is None else args.warranty_hours
        config_a = dict(DEFAULT_CONFIG)
        config_b = apply_changes(config_a, parse_changes(args.compare)) if args.compare else None

    draws = draw_library(lib, n_draws=args.draws, seed=args.seed)
    print(f"\nOperating condition: {describe_profile(profile)} | warranty {t_w:,.0f} h | "
          f"{draws.n_draws:,} Monte Carlo draws, seed {draws.seed}")

    if config_b is None:
        ev = evaluate(config_a, profile, t_w, draws, lib)
        show_evaluation(ev, "Mode 1: evaluate")
        save(stem, {"components": ev.components, "system": ev.system})
    else:
        cmp = compare(config_a, config_b, profile, t_w, draws, lib)
        show_evaluation(cmp.a, "Configuration A")
        show_evaluation(cmp.b, "Configuration B")
        print("\n=== Mode 2: B - A (paired draws) ===")
        print(difference_table(cmp).to_string(index=False))
        print(f"\nP(B outlasts A) = {cmp.p_b_outlasts_a:.3f}")
        save(stem, {"a_components": cmp.a.components, "a_system": cmp.a.system,
                    "b_components": cmp.b.components, "b_system": cmp.b.system,
                    "differences": cmp.differences.assign(p_b_outlasts_a=cmp.p_b_outlasts_a)})


if __name__ == "__main__":
    main()
