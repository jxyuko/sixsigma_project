# interface.py
# Helpers shared by the command-line simulator (code/02_run_simulator.py) and the later UI (M9).
# They only parse inputs and format results; every number comes from evaluate() / compare().

import pandas as pd

from functions.library import SLOTS

# Default configuration: one TI part per slot (all six slots filled)
DEFAULT_CONFIG = {
    "ECU MCU": "F280049CPZQR",
    "BMS AFE": "BQ79656PAPRQ1",
    "Digital isolator": "ISO7741QDWRQ1",
    "Temperature sensor": "TMP4719QDGSRQ1",
    "Gate driver": "UCC21750QDWRQ1",
    "Current sensor": "TMCS1101A4UQDRQ1",
}

# Display names and number formats for each output metric
METRIC_LABELS = {
    "af_eff": ("Acceleration factor (AF_eff)", "{:,.1f}"),
    "device_hours": ("Equivalent device-hours D", "{:.3g}"),
    "fit": ("FIT (failures / 1e9 h)", "{:.3g}"),
    "fit_60pct_bound": ("FIT, 60% bound (datasheet style)", "{:.3g}"),
    "mttf_years_continuous": ("MTTF (years of 24/7 operation)", "{:,.0f}"),
    "r_warranty": ("R(warranty)", "{:.6f}"),
    "b01_hours": ("B0.1 life (hours)", "{:,.0f}"),
    "b01_years_continuous": ("B0.1 life (years of 24/7 operation)", "{:,.1f}"),
    "warranty_ratio": ("Warranty ratio B0.1 / t_w", "{:,.1f}"),
    "p_meets_warranty": ("P(meets warranty) = P(WR >= 1)", "{:.3f}"),
}


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


def fmt(metric, x):
    if pd.isna(x):
        return ""
    return METRIC_LABELS.get(metric, (metric, "{:.4g}"))[1].format(x)


# system_table(): readable system results (median and 95% CI) from an Evaluation
def system_table(ev):
    rows = []
    for _, r in ev.system.iterrows():
        rows.append({"Metric": METRIC_LABELS[r["metric"]][0], "Median": fmt(r["metric"], r["median"]),
                     "95% CI": "" if pd.isna(r["lower"]) else
                     f"{fmt(r['metric'], r['lower'])} - {fmt(r['metric'], r['upper'])}"})
    return pd.DataFrame(rows)


# component_table(): one row per slot, columns for the main component outputs
def component_table(ev):
    c = ev.components
    rows = []
    for slot in [s for s in SLOTS if s in ev.lam]:
        part = c[c["slot"] == slot]
        get = part.set_index("metric")
        row = {"Slot": slot, "Part": get["part"].iloc[0], "Supplier": get["supplier"].iloc[0]}
        for m in ("af_eff", "fit", "fit_60pct_bound", "mttf_years_continuous", "r_warranty"):
            label = METRIC_LABELS[m][0]
            med = fmt(m, get.loc[m, "median"])
            row[label] = med if pd.isna(get.loc[m, "lower"]) else \
                f"{med} ({fmt(m, get.loc[m, 'lower'])} - {fmt(m, get.loc[m, 'upper'])})"
        rows.append(row)
    return pd.DataFrame(rows)


# read_candidates(): Mode 3 candidates from a CSV with the columns of data/examples/candidates_example.csv
CANDIDATE_COLUMNS = ("slot", "name", "supplier", "test_temp_c", "test_hours", "sample_size", "failures",
                     "fit", "mttf_hours", "ref_temp_c", "conf_level", "ea_ev")


def read_candidates(path):
    df = pd.read_csv(path)
    missing = {"slot", "name", "test_temp_c"} - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {', '.join(sorted(missing))}")
    return [{k: (None if pd.isna(v) else v) for k, v in row.items() if k in CANDIDATE_COLUMNS}
            for row in df.to_dict("records")]


def ci(x, lo, hi, f="{:.3g}"):
    return f"{f.format(x)} ({f.format(lo)} - {f.format(hi)})"


# reliability_table(): the headline of Mode 3. Each candidate's reliability at the user's condition,
# after its AF moved it from its own test temperature (in either direction).
def reliability_table(sel):
    t = sel.candidates
    hours = sel.settings["mission_hours"]
    rows = []
    for _, r in t.iterrows():
        rows.append({"Slot": r["slot"], "Candidate": r["name"], "Test C": f"{r['test_temp_c']:g}",
                     "AF to your condition": f"{r['af_eff_median']:.3g}",
                     f"R({hours:,.0f} h)": f"{r['r_mission_median']:.5f}",
                     "95% CI": f"{r['r_mission_lower']:.5f} - {r['r_mission_upper']:.5f}",
                     "FIT": ci(r["fit_median"], r["fit_lower"], r["fit_upper"]),
                     "MTTF (h)": ci(r["mttf_hours_median"], r["mttf_hours_lower"], r["mttf_hours_upper"], "{:,.0f}"),
                     "B0.1 (h)": ci(r["b01_hours_median"], r["b01_hours_lower"], r["b01_hours_upper"], "{:,.0f}")})
    return pd.DataFrame(rows)


# warranty_columns(): the user's warranty exposure (E12), failures and cost, each with its 95% CI
def warranty_columns(r, columns):
    out = {}
    if "warranty_failures_median" in columns:
        out["Warranty failures"] = ci(r["warranty_failures_median"], r["warranty_failures_lower"],
                                      r["warranty_failures_upper"], "{:,.1f}")
    if "warranty_cost_median" in columns:
        out["Warranty cost"] = ci(r["warranty_cost_median"], r["warranty_cost_lower"],
                                  r["warranty_cost_upper"], "{:,.0f}")
    return out


# candidate_table(): readable Mode 3 candidate results, one row per candidate
def candidate_table(sel):
    t = sel.candidates
    rows = []
    for _, r in t.iterrows():
        row = {"Slot": r["slot"], "Rank": r["rank_in_slot"], "Candidate": r["name"], "Evidence": r["evidence"],
               f"R lower bound ({sel.settings['confidence']:.0%})": f"{r['r_mission_lower_bound']:.6f}",
               "P(R >= target)": f"{r['p_meets_target']:.3f}",
               "Meets target": "yes" if r["meets_target_at_confidence"] else "no",
               "P(best in slot)": f"{r['p_best_in_slot']:.3f}",
               **warranty_columns(r, t.columns)}
        rows.append(row)
    return pd.DataFrame(rows)


# combination_table(): readable Mode 3 ranking of slot combinations
def combination_table(sel):
    t = sel.combinations
    rows = []
    for _, r in t.iterrows():
        row = {"Rank": r["rank"], "Combination": r["combination"],
               "System FIT": ci(r["system_fit_median"], r["system_fit_lower"], r["system_fit_upper"]),
               "System R(mission)": ci(r["system_r_mission_median"], r["system_r_mission_lower"],
                                       r["system_r_mission_upper"], "{:.5f}"),
               f"R lower bound ({sel.settings['confidence']:.0%})": f"{r['system_r_lower_bound']:.6f}",
               "P(R >= target)": f"{r['p_meets_target']:.3f}",
               "Meets target": "yes" if r["meets_target_at_confidence"] else "no",
               "P(best)": f"{r['p_best_combination']:.3f}",
               "System B0.1 (h)": ci(r["system_b01_hours_median"], r["system_b01_hours_lower"],
                                     r["system_b01_hours_upper"], "{:,.0f}"),
               **warranty_columns(r, t.columns)}
        if "extra_cost_vs_best_median" in t.columns:
            row["Extra cost vs #1"] = ci(r["extra_cost_vs_best_median"], r["extra_cost_vs_best_lower"],
                                         r["extra_cost_vs_best_upper"], "{:,.0f}")
        rows.append(row)
    return pd.DataFrame(rows)


# difference_table(): readable Mode 2 differences B - A
def difference_table(cmp):
    rows = []
    for _, r in cmp.differences.iterrows():
        m = r["metric"]
        ci = "" if pd.isna(r.get("delta_lower")) else f"{fmt(m, r['delta_lower'])} - {fmt(m, r['delta_upper'])}"
        pct = "" if pd.isna(r.get("delta_pct_median")) else f"{r['delta_pct_median']:+.1f}%"
        rows.append({"Metric": METRIC_LABELS[m][0], "A": fmt(m, r["a_median"]), "B": fmt(m, r["b_median"]),
                     "B - A (median)": fmt(m, r["delta_median"]), "B - A 95% CI": ci, "B - A %": pct})
    return pd.DataFrame(rows)
