# interface.py
# Input parsing and output formatting for the user-facing simulator (code/02_run_simulator.py) and
# a possible later web front end. Every number comes from candidates.select(); this file only reads inputs
# and writes readable text and tables.

import re

import numpy as np
import pandas as pd

# Columns a candidates file may have (data/examples/candidates_example.csv); see data/codebook.md
CANDIDATE_COLUMNS = ("slot", "name", "supplier", "test_temp_c", "test_hours", "sample_size", "failures",
                     "fit", "mttf_hours", "ref_temp_c", "conf_level", "ea_ev", "unit_price_usd")
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


def ci(x, lo, hi, f="{:.3g}"):
    return f"{f.format(x)} ({f.format(lo)} - {f.format(hi)})"


def money(x):
    return f"${x:,.0f}"


# summary_text(): the first thing the user reads. Plain sentences: one recommendation per slot,
# the most reliable combination, the cheapest combination (purchase + warranty), and the basis.
# Every number is the estimate with its 95% interval (E4); the target check uses the one-sided 95% bound.
def summary_text(sel):
    s = sel.settings
    hours, target, conf, fleet = s["mission_hours"], s["target_r"], s["confidence"], s["fleet_size"]
    lines = [f"Condition: {describe_condition(s['condition'])} for {hours:,.0f} h | target: reliability "
             f">= {target} with {conf:.0%} confidence",
             f"Warranty exposure per {fleet:,} vehicles over {s['warranty_hours']:,.0f} h; cost per failure = "
             + ("each failed part is replaced at its unit price" if s["replacement_cost"] is None
                else f"{money(s['replacement_cost'])} per replacement (your value)")]
    lines.append("Activation energy for parts whose report states none: "
                 + (f"0.5-0.9 eV range (Monte Carlo, {s['n_draws']:,} draws, "
                    + ("one draw shared by all parts)" if s["ea_shared"] else "a separate draw per part)")
                    if s["ea_range"] else f"{s['default_ea']:g} eV"))
    lines += [f"Note: {w}" for w in sel.warnings]

    lines.append("\nBest candidate in each slot (lowest estimated failure rate):")
    t = sel.candidates
    for slot in t["slot"].unique():
        rows = t[t["slot"] == slot]
        b = rows.iloc[0]
        verdict = "meets the target" if b["meets_target_at_confidence"] else "does NOT meet the target"
        lines.append(f"  {slot}: {b['name']}  R({hours:,.0f} h) = {b['r_mission_estimate']:.5f} "
                     f"(95% CI {b['r_mission_lower']:.5f} - {b['r_mission_upper']:.5f}); {verdict}"
                     + (f"; best of {len(rows)} candidates" if len(rows) > 1 else "; only candidate"))

    best = sel.combinations.iloc[0]
    verdict = "meets" if best["meets_target_at_confidence"] else "does NOT meet"
    lines.append(f"\nMost reliable system: {best['combination']}")
    lines.append(f"  System R({hours:,.0f} h) = {best['system_r_mission_estimate']:.5f} (all parts at their 95% "
                 f"bounds: {best['system_r_mission_lower']:.5f} - {best['system_r_mission_upper']:.5f}); "
                 f"{verdict} the target (95% lower bound {best['system_r_lower_bound']:.6f})")
    if s["ea_range"]:
        lines.append(f"  System FIT {best['system_fit_estimate']:.3g}; over the Ea range {best['system_fit_ea_lower']:.3g}"
                     f" - {best['system_fit_ea_upper']:.3g}; full range {best['system_fit_full_lower']:.3g} - "
                     f"{best['system_fit_full_upper']:.3g}; target still met at the unfavourable Ea: "
                     f"{'yes' if best['system_meets_target_at_ea_worst'] else 'NO'}")
    if not np.isscalar(s["condition"]):
        lines.append(f"  Worst case, all the time at {s['max_temperature']:g} C: system FIT "
                     f"{best['system_fit_at_max_temp']:.3g} (vs {best['system_fit_estimate']:.3g} over the band)")
    lines.append(f"  Per {fleet:,} vehicles: {best['warranty_failures_estimate']:,.2f} expected warranty failures "
                 f"({best['warranty_failures_lower']:,.2f} - {best['warranty_failures_upper']:,.2f}); "
                 f"purchase {money(best['purchase_cost'])} + warranty {money(best['warranty_cost_estimate'])} "
                 f"= total {money(best['total_cost_estimate'])}")
    cheap = sel.cheapest
    if cheap and cheap["combination"] != best["combination"]:
        lines.append(f"\nLowest total cost: {cheap['combination']}")
        lines.append(f"  Total {money(cheap['total_cost_estimate'])} per {fleet:,} vehicles "
                     f"({money(best['total_cost_estimate'] - cheap['total_cost_estimate'])} less than the most "
                     f"reliable system); system R({hours:,.0f} h) = {cheap['system_r_mission_estimate']:.5f}")
    elif cheap:
        lines.append("  It is also the lowest total cost.")
    return "\n".join(lines)


# key_table(): one row per candidate with the outputs needed to decide
def key_table(sel):
    t = sel.candidates
    hours = sel.settings["mission_hours"]
    return pd.DataFrame([{
        "Slot": r["slot"], "Rank": r["rank_in_slot"], "Candidate": r["name"],
        "FIT (95% CI)": ci(r["fit_estimate"], r["fit_lower"], r["fit_upper"]),
        **({"FIT over Ea range": ci(r["fit_estimate"], r["fit_ea_lower"], r["fit_ea_upper"])}
           if sel.settings["ea_range"] else {}),
        f"R({hours:,.0f} h) (95% CI)": ci(r["r_mission_estimate"], r["r_mission_lower"], r["r_mission_upper"], "{:.5f}"),
        "Meets target": "yes" if r["meets_target_at_confidence"] else "no",
        "Warranty failures": ci(r["warranty_failures_estimate"], r["warranty_failures_lower"],
                                r["warranty_failures_upper"], "{:,.2f}"),
        "Total cost": money(r["total_cost_estimate"]),
    } for _, r in t.iterrows()])


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
        **({"FIT full range (Ea + 95% CI)": ci(r["fit_estimate"], r["fit_full_lower"], r["fit_full_upper"])}
           if sel.settings["ea_range"] else {}),
        **({f"FIT at {sel.settings['max_temperature']:g} C": f"{r['fit_at_max_temp']:.3g}"}
           if not np.isscalar(sel.settings["condition"]) else {}),
        "MTTF (h)": ci(r["mttf_hours_estimate"], r["mttf_hours_lower"], r["mttf_hours_upper"], "{:,.0f}"),
        "B0.1 (h)": ci(r["b01_hours_estimate"], r["b01_hours_lower"], r["b01_hours_upper"], "{:,.0f}"),
    } for _, r in t.iterrows()])


# candidate_table(): requirement check, ranking and warranty exposure per candidate
def candidate_table(sel):
    t = sel.candidates
    conf = sel.settings["confidence"]
    return pd.DataFrame([{
        "Slot": r["slot"], "Rank": r["rank_in_slot"], "Candidate": r["name"],
        f"FIT upper bound ({conf:.0%})": f"{r['fit_upper_one_sided']:.3g}",
        f"R lower bound ({conf:.0%})": f"{r['r_mission_lower_bound']:.6f}",
        "Meets target": "yes" if r["meets_target_at_confidence"] else "no",
        "Unit price": f"${r['unit_price_usd']:,.2f} ({r['price_source']})",
        "Warranty failures": ci(r["warranty_failures_estimate"], r["warranty_failures_lower"],
                                r["warranty_failures_upper"], "{:,.2f}"),
        "Warranty cost": ci(r["warranty_cost_estimate"], r["warranty_cost_lower"], r["warranty_cost_upper"], "{:,.0f}"),
        "Purchase cost": money(r["purchase_cost"]),
        "Total cost": ci(r["total_cost_estimate"], r["total_cost_lower"], r["total_cost_upper"], "{:,.0f}"),
    } for _, r in t.iterrows()])


# combination_table(): ranked slot combinations (series system); ranges put every part at its 95% bound
def combination_table(sel):
    t = sel.combinations
    conf = sel.settings["confidence"]
    return pd.DataFrame([{
        "Rank": r["rank"], "Combination": r["combination"],
        "System FIT": ci(r["system_fit_estimate"], r["system_fit_lower"], r["system_fit_upper"]),
        **({"System FIT over Ea range": ci(r["system_fit_estimate"], r["system_fit_ea_lower"],
                                           r["system_fit_ea_upper"]),
            "Meets target at unfavourable Ea": "yes" if r["system_meets_target_at_ea_worst"] else "no"}
           if sel.settings["ea_range"] else {}),
        **({f"System FIT at {sel.settings['max_temperature']:g} C": f"{r['system_fit_at_max_temp']:.3g}"}
           if not np.isscalar(sel.settings["condition"]) else {}),
        "System R(mission)": ci(r["system_r_mission_estimate"], r["system_r_mission_lower"],
                                r["system_r_mission_upper"], "{:.5f}"),
        f"R lower bound ({conf:.0%})": f"{r['system_r_lower_bound']:.6f}",
        "Meets target": "yes" if r["meets_target_at_confidence"] else "no",
        "System B0.1 (h)": ci(r["system_b01_hours_estimate"], r["system_b01_hours_lower"],
                              r["system_b01_hours_upper"], "{:,.0f}"),
        "Warranty failures": ci(r["warranty_failures_estimate"], r["warranty_failures_lower"],
                                r["warranty_failures_upper"], "{:,.2f}"),
        "Warranty cost": ci(r["warranty_cost_estimate"], r["warranty_cost_lower"], r["warranty_cost_upper"], "{:,.0f}"),
        "Total cost": ci(r["total_cost_estimate"], r["total_cost_lower"], r["total_cost_upper"], "{:,.0f}"),
        "Total cost vs #1": money(r["extra_cost_vs_best"]),
    } for _, r in t.iterrows()])
