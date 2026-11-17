# interface.py
# Input parsing and output formatting for the user-facing simulator (code/02_run_simulator.py) and
# a possible later web front end. Every number comes from candidates.select(); this file only reads inputs
# and writes readable text and tables.

import re

import numpy as np
import pandas as pd

# Columns a candidates file may have (data/examples/candidates_example.csv); see data/codebook.md
CANDIDATE_COLUMNS = ("slot", "name", "supplier", "test_temp_c", "test_hours", "sample_size", "failures",
                     "fit", "mttf_hours", "ref_temp_c", "conf_level", "ea_ev", "unit_price_usd", "qty_per_vehicle")
REQUIRED_COLUMNS = ("slot", "name", "test_temp_c")
GROUP_COLUMNS = ("test_temp_c", "test_hours", "sample_size", "failures")


# parse_condition(): the operating temperature: "55" -> 55.0; a band the part runs across,
# "40-105" or "40 to 105" -> (40.0, 105.0) (team decision 2026-11-15). Negative temperatures are
# allowed ("-20-85" -> (-20.0, 85.0)).
def parse_condition(text):
    text = text.strip().replace(" to ", ",")
    m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*(?:-|,)\s*(-?\d+(?:\.\d+)?)\s*", text)
    if m:
        lo, hi = sorted(float(x) for x in m.groups())
        return lo if lo == hi else (lo, hi)
    return float(text)


# parse_quantities(): parts per vehicle by slot, "Gate driver=6, BMS AFE=12" -> {"Gate driver": 6, ...}
# (A10); slot names are matched to the six slots by select()
def parse_quantities(text):
    out = {}
    for item in filter(None, (x.strip() for x in text.split(","))):
        if "=" not in item:
            raise ValueError(f"quantity {item!r}: write slot=number, e.g. Gate driver=6")
        slot, n = (x.strip() for x in item.split("=", 1))
        out[slot] = int(n)
    return out


def describe_condition(condition):
    if np.isscalar(condition):
        return f"{condition:g} C"
    if len(condition) == 2 and all(np.isscalar(x) for x in condition):
        return f"{condition[0]:g}-{condition[1]:g} C (time spread evenly over the band)"
    return ", ".join(f"{t:g} C for {100 * w:g}%" for t, w in condition)


# read_candidates(): candidates from a CSV file, one row per candidate. Several rows with the same
# slot and name are that part's test groups (test_temp_c, test_hours, sample_size, failures each);
# the other columns are taken from the first of its rows.
def read_candidates(path):
    df = pd.read_csv(path)
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {', '.join(sorted(missing))}")
    out = []
    for _, rows in df.groupby(["slot", "name"], sort=False):
        recs = [{k: (None if pd.isna(v) else v) for k, v in r.items() if k in CANDIDATE_COLUMNS}
                for r in rows.to_dict("records")]
        c = dict(recs[0])
        if len(recs) > 1:
            c["groups"] = [{k: r.get(k) for k in GROUP_COLUMNS} for r in recs]
        out.append(c)
    return out


# num(): a readable number: 3 significant figures below 1,000, whole numbers with commas from 1,000 up
# (never "1.38e+03"); 0 and infinity written out
def num(x):
    x = float(x)
    if x == 0:
        return "0"
    if np.isinf(x):
        return "inf"
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    return f"{x:.3g}"


def ci(x, lo, hi, f=None):
    fmt = num if f is None else f.format
    return f"{fmt(x)} ({fmt(lo)} - {fmt(hi)})"


def money(x):
    return f"${x:,.0f}"


# fit_range(): "37.4 (0* - 199)": estimate with its 2.5th-97.5th percentile; * marks a lower bound of 0
def fit_range(est, lo, hi):
    return f"{num(est)} ({'0*' if lo == 0 else num(lo)} - {num(hi)})"


# combination_block(): the lines printed for one of the best combinations
def combination_block(sel, c):
    s = sel.settings
    fleet = s["fleet_size"]
    met = "yes" if c["meets_target_at_confidence"] else "NO"
    lines = [f"  {c['combination']}",
             f"  System FIT {num(c['system_fit_estimate'])}   if every part is at its 2.5th / 97.5th percentile: "
             f"{'0*' if c['system_fit_lower'] == 0 else num(c['system_fit_lower'])} / "
             f"{num(c['system_fit_upper'])}",
             f"  Failures per {fleet:,} vehicles: {num(c['warranty_failures_estimate'])}   Meets target: {met} "
             f"(95% maximum {num(c['system_fit_upper_one_sided'])} FIT {'<=' if met == 'yes' else '>'} "
             f"{s['target_fit']:.0f})"]
    if not np.isscalar(s["condition"]):
        lines.append(f"  Worst case, all the time at {s['max_temperature']:g} C: system FIT "
                     f"{num(c['system_fit_at_max_temp'])}")
    if s["ea_range"]:
        lines.append(f"  Over the Ea range 0.5-0.9 eV: system FIT {num(c['system_fit_ea_lower'])} - "
                     f"{num(c['system_fit_ea_upper'])} (with the 95% bounds: {num(c['system_fit_full_lower'])} - "
                     f"{num(c['system_fit_full_upper'])}); target still met at the unfavourable Ea: "
                     f"{'yes' if c['system_meets_target_at_ea_worst'] else 'NO'}")
    lines.append(f"  Total cost per {fleet:,} vehicles: {money(c['total_cost_estimate'])} (purchase "
                 f"{money(c['purchase_cost'])} + warranty {money(c['warranty_cost_estimate'])})")
    return lines


# summary_text(): the first thing the user reads (team decision 2026-11-16): the condition, then the
# three best combinations (most reliable, safest, cheapest that meets the target), then the best part in
# each slot. Failure rates are FIT with their 2.5th-97.5th percentile (E4); R(mission), MTTF and B0.1 are
# in the saved CSVs and the details.
def summary_text(sel):
    s = sel.settings
    hours, target, conf, fleet = s["mission_hours"], s["target_r"], s["confidence"], s["fleet_size"]
    p = sel.picks
    lines = [f"Condition: {describe_condition(s['condition'])} for {hours:,.0f} h | target: R({hours:,.0f} h) "
             f">= {target} with {conf:.0%} confidence",
             f"           (at most {s['target_fit']:.0f} FIT for the whole system)",
             *([f"Mission: {hours:,.0f} h = 8-year EV battery warranty x 1 powered-on hour per day (the default)"]
               if s.get("default_mission") else []),
             "Activation energy for parts whose report states none: "
             + (f"0.5-0.9 eV range (Monte Carlo, {s['n_draws']:,} draws, "
                + ("one draw shared by all parts)" if s["ea_shared"] else "a separate draw per part)")
                if s["ea_range"] else f"{s['default_ea']:g} eV"),
             f"Warranty exposure per {fleet:,} vehicles; each failure "
             + ("replaces the part at its unit price" if s["replacement_cost"] is None
                else f"costs {money(s['replacement_cost'])} (your value)"),
             f"{p['n_combinations']:,} combinations evaluated ({p['n_meeting_target']:,} meet the target)"]
    t = sel.candidates
    if (t["qty_per_vehicle"] != 1).any():
        parts = []
        for slot, g in t.groupby("slot", observed=True, sort=False):
            qs = g["qty_per_vehicle"].unique()
            parts.append(f"{slot} {qs[0]}" if len(qs) == 1 else
                         f"{slot}: " + ", ".join(f"{n} {q}" for n, q in zip(g["name"], g["qty_per_vehicle"])))
        lines.append("Parts per vehicle: " + "; ".join(parts)
                     + ". System rate, failures and costs count every part.")
    lines += [f"Note: {w}" for w in sel.warnings]

    lines += ["", "BEST COMBINATIONS", "-" * 84, "Most reliable (lowest estimated failure rate)"]
    lines += combination_block(sel, p["most_reliable"])
    lines += ["", "Safest (lowest 95% maximum failure rate)"]
    lines += (["  Same as most reliable"] if p["safest"]["combination"] == p["most_reliable"]["combination"]
              else combination_block(sel, p["safest"]))
    lines += ["", "Cheapest that meets the target"]
    if p["cheapest"] is None:
        lines.append("  No combination meets the target. Closest: the safest combination above.")
    elif p["cheapest"]["combination"] == p["most_reliable"]["combination"]:
        lines.append("  Same as most reliable")
    elif p["cheapest"]["combination"] == p["safest"]["combination"]:
        lines.append("  Same as safest")
    else:
        lines += combination_block(sel, p["cheapest"])
    if (sel.candidates["fit_lower"] == 0).any():
        lines += ["", "* lower bound 0: with zero failures the test cannot rule out a failure rate of 0"]

    lines += ["", "BEST PART IN EACH SLOT", "-" * 84, best_parts_table(sel).to_string(index=False)]
    return "\n".join(lines)


# best_parts_table(): the rank-1 candidate of each slot
def best_parts_table(sel):
    t = sel.candidates
    return key_table(sel).loc[t["rank_in_slot"].to_numpy() == 1].drop(columns=["Rank", "Unit price"])


# key_table(): one row per candidate with the outputs needed to decide
def key_table(sel):
    t = sel.candidates
    fleet = sel.settings["fleet_size"]
    multi = (t["qty_per_vehicle"] != 1).any()          # A10: quantities shown only when one isn't 1
    return pd.DataFrame([{
        "Slot": r["slot"], "Rank": r["rank_in_slot"], "Part": r["name"],
        ("FIT per part (2.5th-97.5th %)" if multi else "FIT (2.5th-97.5th %)"):
            fit_range(r["fit_estimate"], r["fit_lower"], r["fit_upper"]),
        **({"Per vehicle": int(r["qty_per_vehicle"]),
            "FIT per vehicle": fit_range(r["fit_per_vehicle_estimate"], r["fit_per_vehicle_lower"],
                                         r["fit_per_vehicle_upper"])} if multi else {}),
        **({"FIT over Ea range": (f"{num(r['fit_ea_lower'])} - {num(r['fit_ea_upper'])}"
                                  if r["ea_source"] != "report" else f"fixed (report Ea {r['ea_ev']:g} eV)")}
           if sel.settings["ea_range"] else {}),
        **({f"FIT at {sel.settings['max_temperature']:g} C": f"{num(r['fit_at_max_temp'])}"}
           if not np.isscalar(sel.settings["condition"]) else {}),
        f"Failures/{fleet:,}": f"{num(r['warranty_failures_estimate'])}",
        "Meets target": "yes" if r["meets_target_at_confidence"] else "NO",
        "Unit price": f"${r['unit_price_usd']:,.2f}",
    } for _, r in t.iterrows()])


# best_reliability_table(): R(mission), MTTF and B0.1 of the best combinations (shown with --details)
def best_reliability_table(sel):
    hours = sel.settings["mission_hours"]
    rows, seen = [], set()
    for label, key in (("Most reliable", "most_reliable"), ("Safest", "safest"), ("Cheapest meeting target", "cheapest")):
        c = sel.picks.get(key)
        if c is None or c["combination"] in seen:
            continue
        seen.add(c["combination"])
        rows.append({"Pick": label, "Combination": c["combination"],
                     f"R({hours:,.0f} h)": ci(c["system_r_mission_estimate"], c["system_r_mission_lower"],
                                              c["system_r_mission_upper"], "{:.6f}"),
                     "95% lower bound on R": f"{c['system_r_lower_bound']:.6f}",
                     "B0.1 (h)": ci(c["system_b01_hours_estimate"], c["system_b01_hours_lower"],
                                    c["system_b01_hours_upper"], "{:,.0f}")})
    return pd.DataFrame(rows)


# --- Details (shown on request, always saved to CSV) ---------------------------------------------

# reliability_table(): each candidate's reliability at the user's condition, after its AF moved it
# from its own test temperature (in either direction)
def reliability_table(sel):
    t = sel.candidates
    hours = sel.settings["mission_hours"]
    return pd.DataFrame([{
        "Slot": r["slot"], "Candidate": r["name"], "Test C": f"{r['test_temp_c']}", "Evidence": r["evidence"],
        "Failures": r["failures"], "AF to your condition": f"{r['af_eff']:.3g}",
        f"R({hours:,.0f} h)": ci(r["r_mission_estimate"], r["r_mission_lower"], r["r_mission_upper"], "{:.5f}"),
        "FIT": ci(r["fit_estimate"], r["fit_lower"], r["fit_upper"]),
        "FIT 60% upper bound": num(r["fit_upper_60"]),
        **({"FIT full range (Ea + 95% CI)": ci(r["fit_estimate"], r["fit_full_lower"], r["fit_full_upper"])}
           if sel.settings["ea_range"] else {}),
        **({f"FIT at {sel.settings['max_temperature']:g} C": f"{num(r['fit_at_max_temp'])}"}
           if not np.isscalar(sel.settings["condition"]) else {}),
        "MTTF (h)": ci(r["mttf_hours_estimate"], r["mttf_hours_lower"], r["mttf_hours_upper"], "{:,.0f}"),
        "B0.1 (h)": ci(r["b01_hours_estimate"], r["b01_hours_lower"], r["b01_hours_upper"], "{:,.0f}"),
    } for _, r in t.iterrows()])
