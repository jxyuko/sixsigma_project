# interface.py
# Input parsing and output formatting for the user-facing simulator (code/02_run_simulator.py) and
# a possible later web front end. Every number comes from candidates.select(); this file only reads inputs
# and writes readable text and tables.

import pandas as pd

# Columns a candidates file may have (data/examples/candidates_example.csv); see data/codebook.md
CANDIDATE_COLUMNS = ("slot", "name", "supplier", "test_temp_c", "test_hours", "sample_size", "failures",
                     "fit", "mttf_hours", "ref_temp_c", "conf_level", "ea_ev", "unit_price_usd")
REQUIRED_COLUMNS = ("slot", "name", "test_temp_c")


# parse_profile(): "55" -> 55.0; "40:0.5, 70:0.3, 105:0.2" -> [(40, 0.5), (70, 0.3), (105, 0.2)]
# Fractions may also be given in percent ("40:50, 70:30, 105:20"). Validity is checked by E6 code.
def parse_profile(text):
    text = text.strip()
    if ":" not in text:
        return float(text)
    bins = []
    for chunk in text.split(","):
        t, w = chunk.split(":")
        bins.append((float(t), float(w)))
    if sum(w for _, w in bins) > 1.5:          # given in percent
        bins = [(t, w / 100) for t, w in bins]
    return bins


def describe_profile(profile):
    if isinstance(profile, (int, float)):
        return f"{profile:g} C"
    return ", ".join(f"{t:g} C for {100 * w:g}%" for t, w in profile)


# read_candidates(): candidates from a CSV file, one row per candidate
def read_candidates(path):
    df = pd.read_csv(path)
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {', '.join(sorted(missing))}")
    return [{k: (None if pd.isna(v) else v) for k, v in row.items() if k in CANDIDATE_COLUMNS}
            for row in df.to_dict("records")]


def ci(x, lo, hi, f="{:.3g}"):
    return f"{f.format(x)} ({f.format(lo)} - {f.format(hi)})"


def money(x):
    return f"${x:,.0f}"


# summary_text(): the first thing the user reads. Plain sentences: one recommendation per slot,
# the most reliable combination, the cheapest combination (purchase + warranty), and the basis.
def summary_text(sel):
    s = sel.settings
    hours, target, conf, fleet = s["mission_hours"], s["target_r"], s["confidence"], s["fleet_size"]
    lines = [f"Condition: {describe_profile(s['profile'])} for {hours:,.0f} h | target: reliability "
             f">= {target} with {conf:.0%} confidence",
             f"Warranty exposure per {fleet:,} vehicles over {s['warranty_hours']:,.0f} h; cost per failure = "
             + ("each failed part is replaced at its unit price" if s["replacement_cost"] is None
                else f"{money(s['replacement_cost'])} per replacement (your value)")]
    lines += [f"Note: {w}" for w in sel.warnings]

    lines.append("\nBest candidate in each slot:")
    t = sel.candidates
    for slot in t["slot"].unique():
        rows = t[t["slot"] == slot]
        b = rows.iloc[0]
        others = len(rows) - 1
        verdict = "meets the target" if b["meets_target_at_confidence"] else "does NOT meet the target"
        lines.append(f"  {slot}: {b['name']}  R({hours:,.0f} h) = {b['r_mission_median']:.5f} "
                     f"(95% CI {b['r_mission_lower']:.5f} - {b['r_mission_upper']:.5f}); {verdict}"
                     + (f"; best of {others + 1} candidates in {b['p_best_in_slot']:.0%} of simulations"
                        if others else "; only candidate"))

    best = sel.combinations.iloc[0]
    verdict = "meets" if best["meets_target_at_confidence"] else "does NOT meet"
    lines.append(f"\nMost reliable system: {best['combination']}")
    lines.append(f"  System R({hours:,.0f} h) = {best['system_r_mission_median']:.5f} (95% CI "
                 f"{best['system_r_mission_lower']:.5f} - {best['system_r_mission_upper']:.5f}); "
                 f"{verdict} the target (95% lower bound {best['system_r_lower_bound']:.6f})")
    lines.append(f"  Per {fleet:,} vehicles: {best['warranty_failures_median']:,.1f} expected warranty failures "
                 f"(95% CI {best['warranty_failures_lower']:,.1f} - {best['warranty_failures_upper']:,.1f}); "
                 f"purchase {money(best['purchase_cost'])} + warranty {money(best['warranty_cost_median'])} "
                 f"= total {money(best['total_cost_median'])}")
    cheap = sel.cheapest
    if cheap and cheap["combination"] != best["combination"]:
        lines.append(f"\nLowest total cost: {cheap['combination']}")
        lines.append(f"  Total {money(cheap['total_cost_median'])} per {fleet:,} vehicles "
                     f"({money(best['total_cost_median'] - cheap['total_cost_median'])} less than the most "
                     f"reliable system); system R({hours:,.0f} h) = {cheap['system_r_mission_median']:.5f}")
    elif cheap:
        lines.append("  It is also the lowest total cost.")
    return "\n".join(lines)


# key_table(): one row per candidate with the outputs needed to decide
def key_table(sel):
    t = sel.candidates
    hours = sel.settings["mission_hours"]
    return pd.DataFrame([{
        "Slot": r["slot"], "Candidate": r["name"],
        f"R({hours:,.0f} h) (95% CI)": ci(r["r_mission_median"], r["r_mission_lower"], r["r_mission_upper"], "{:.5f}"),
        "Meets target": "yes" if r["meets_target_at_confidence"] else "no",
        "Chance best in slot": f"{r['p_best_in_slot']:.0%}",
        "Warranty failures": ci(r["warranty_failures_median"], r["warranty_failures_lower"],
                                r["warranty_failures_upper"], "{:,.1f}"),
        "Total cost": money(r["total_cost_median"]),
    } for _, r in t.iterrows()])


# --- Details (shown on request, always saved to CSV) ---------------------------------------------

# reliability_table(): each candidate's reliability at the user's condition, after its AF moved it
# from its own test temperature (in either direction)
def reliability_table(sel):
    t = sel.candidates
    hours = sel.settings["mission_hours"]
    return pd.DataFrame([{
        "Slot": r["slot"], "Candidate": r["name"], "Test C": f"{r['test_temp_c']:g}", "Evidence": r["evidence"],
        "AF to your condition": f"{r['af_eff_median']:.3g}",
        f"R({hours:,.0f} h)": ci(r["r_mission_median"], r["r_mission_lower"], r["r_mission_upper"], "{:.5f}"),
        "FIT": ci(r["fit_median"], r["fit_lower"], r["fit_upper"]),
        "MTTF (h)": ci(r["mttf_hours_median"], r["mttf_hours_lower"], r["mttf_hours_upper"], "{:,.0f}"),
        "B0.1 (h)": ci(r["b01_hours_median"], r["b01_hours_lower"], r["b01_hours_upper"], "{:,.0f}"),
    } for _, r in t.iterrows()])


# candidate_table(): requirement check, ranking and warranty exposure per candidate
def candidate_table(sel):
    t = sel.candidates
    return pd.DataFrame([{
        "Slot": r["slot"], "Rank": r["rank_in_slot"], "Candidate": r["name"],
        f"R lower bound ({sel.settings['confidence']:.0%})": f"{r['r_mission_lower_bound']:.6f}",
        "P(R >= target)": f"{r['p_meets_target']:.3f}",
        "Meets target": "yes" if r["meets_target_at_confidence"] else "no",
        "P(best in slot)": f"{r['p_best_in_slot']:.3f}",
        "Unit price": f"${r['unit_price_usd']:,.2f} ({r['price_source']})",
        "Warranty failures": ci(r["warranty_failures_median"], r["warranty_failures_lower"],
                                r["warranty_failures_upper"], "{:,.1f}"),
        "Warranty cost": ci(r["warranty_cost_median"], r["warranty_cost_lower"], r["warranty_cost_upper"], "{:,.0f}"),
        "Purchase cost": money(r["purchase_cost"]),
        "Total cost": ci(r["total_cost_median"], r["total_cost_lower"], r["total_cost_upper"], "{:,.0f}"),
    } for _, r in t.iterrows()])


# combination_table(): ranked slot combinations (series system)
def combination_table(sel):
    t = sel.combinations
    return pd.DataFrame([{
        "Rank": r["rank"], "Combination": r["combination"],
        "System FIT": ci(r["system_fit_median"], r["system_fit_lower"], r["system_fit_upper"]),
        "System R(mission)": ci(r["system_r_mission_median"], r["system_r_mission_lower"],
                                r["system_r_mission_upper"], "{:.5f}"),
        f"R lower bound ({sel.settings['confidence']:.0%})": f"{r['system_r_lower_bound']:.6f}",
        "P(R >= target)": f"{r['p_meets_target']:.3f}",
        "Meets target": "yes" if r["meets_target_at_confidence"] else "no",
        "P(best)": f"{r['p_best_combination']:.3f}",
        "System B0.1 (h)": ci(r["system_b01_hours_median"], r["system_b01_hours_lower"],
                              r["system_b01_hours_upper"], "{:,.0f}"),
        "Warranty failures": ci(r["warranty_failures_median"], r["warranty_failures_lower"],
                                r["warranty_failures_upper"], "{:,.1f}"),
        "Warranty cost": ci(r["warranty_cost_median"], r["warranty_cost_lower"], r["warranty_cost_upper"], "{:,.0f}"),
        "Total cost": ci(r["total_cost_median"], r["total_cost_lower"], r["total_cost_upper"], "{:,.0f}"),
        "Total cost vs #1": ci(r["extra_cost_vs_best_median"], r["extra_cost_vs_best_lower"],
                               r["extra_cost_vs_best_upper"], "{:,.0f}"),
    } for _, r in t.iterrows()])
