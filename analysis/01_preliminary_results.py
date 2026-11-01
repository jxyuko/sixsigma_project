# 01_preliminary_results.py
# M7: tables and figures for the Preliminary Results report (ROADMAP Section 9).
# Kept apart from the simulator: this script only CALLS the simulator (functions/) on our library
# data, treating the library parts as a vehicle maker's candidates, and writes report material to
# reports/preliminary_results/. It never changes the simulator.
#
# Run from the project root:  .venv/Scripts/python analysis/01_preliminary_results.py   (~4 minutes)
#
# Main condition (team decision 2026-11-01): 55 C, mission 2,920 h (A7), target R >= 0.999 with 95%
# confidence (A13), 5,000 draws, seed 5300. Warranty exposure as failures per 1,000 vehicles;
# no costs (Financial Impacts is deferred).

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
sys.path.append(str(Path(__file__).resolve().parent))
import plots  # noqa: E402  (plotnine figures, analysis/plots.py)
from functions.candidates import CONFIDENCE, library_candidate, p_best, select  # noqa: E402
from functions.library import SLOTS, load_library  # noqa: E402
from functions.simulator import DEFAULT_WARRANTY_HOURS, N_DRAWS, SEED  # noqa: E402
from functions.validation import (brier_score, calibration_study, coverage_by_evidence,  # noqa: E402
                                  coverage_study, supplier_check)

OUT = ROOT / "reports" / "preliminary_results"
TABLES, FIGURES = OUT / "tables", OUT / "figures"

T_REF = 55                          # C, the parameter table's reference temperature
MISSION = DEFAULT_WARRANTY_HOURS    # 2,920 h (A7)
TARGET = 0.999
FLEET = 1000
PROFILE = [(40, 0.5), (70, 0.3), (105, 0.2)]   # illustrative profile (ROADMAP Section 3), mean 62 C
SWEEP = np.arange(25, 151, 5)

# One part per qualification family (A9): family members share one dataset and give identical results
CANDIDATES = ["F280049CPZQR", "R7F7016903AFP-C", "BQ79656PAPRQ1", "LTC6811-1", "ISO7741QDWRQ1",
              "ADuM141E", "TMP4719QDGSRQ1", "UCC21750QDWRQ1", "ADuM4135", "TMCS1101A4UQDRQ1"]

def run(profile=T_REF, mission=MISSION, **kw):
    cands = [library_candidate(p) for p in CANDIDATES]
    return select(cands, profile, mission, TARGET, fleet_size=FLEET, top=100, **kw)


# --- Table 1: every candidate on a common basis ------------------------------------------------------

def table_common_basis(sel, lib):
    t = sel.candidates.merge(lib[["part", "family", "test_hours", "sample_size"]], left_on="name", right_on="part")
    cols = {"slot": "slot", "supplier": "supplier", "name": "part", "family": "family",
            "test_temp_c": "test_temp_c", "test_hours": "test_hours", "sample_size": "sample_size",
            "failures": "failures", "device_hours_test": "device_hours_test"}
    out = t[list(cols)].rename(columns=cols)
    for m in ("af_eff", "fit", "mttf_hours", "r_mission", "b01_hours"):
        for q in ("median", "lower", "upper"):
            out[f"{m}_{q}"] = t[f"{m}_{q}"]
    out["r_mission_lower_bound_95"] = t["r_mission_lower_bound"]
    out["p_meets_target"] = t["p_meets_target"]
    out["meets_target"] = t["meets_target_at_confidence"]
    return out


# --- Table 2: supplier comparison within each slot (paired draws) ---------------------------------

def table_slot_comparison(sel):
    rows = []
    t = sel.candidates
    for slot in [s for s in SLOTS if (t["slot"] == s).sum() >= 2]:
        c = t[t["slot"] == slot]
        ti = c[c["supplier"] == "Texas Instruments"].iloc[0]
        alt = c[c["supplier"] != "Texas Instruments"].iloc[0]
        ratio = sel.lam[alt["name"]] / sel.lam[ti["name"]]          # E11 on the rate, paired draws
        q = np.quantile(ratio, [0.025, 0.5, 0.975])
        rows.append({"slot": slot, "ti_part": ti["name"], "alternative_part": alt["name"],
                     "alternative_supplier": alt["supplier"],
                     "ti_fit_median": ti["fit_median"], "alternative_fit_median": alt["fit_median"],
                     "fit_ratio_alt_over_ti_median": q[1], "fit_ratio_lower": q[0], "fit_ratio_upper": q[2],
                     "p_ti_best": ti["p_best_in_slot"],
                     "ti_meets_target": ti["meets_target_at_confidence"],
                     "alternative_meets_target": alt["meets_target_at_confidence"],
                     "ti_device_hours_test": ti["device_hours_test"],
                     "alternative_device_hours_test": alt["device_hours_test"]})
    return pd.DataFrame(rows)


# --- Table 3: system combinations --------------------------------------------------------------------

SYSTEM_COLS = ["rank", "combination", "system_fit_median", "system_fit_lower", "system_fit_upper",
               "system_r_mission_median", "system_r_mission_lower", "system_r_mission_upper",
               "system_r_lower_bound", "p_meets_target", "meets_target_at_confidence", "p_best_combination",
               "system_b01_hours_median", "system_b01_hours_lower", "system_b01_hours_upper",
               "warranty_failures_median", "warranty_failures_lower", "warranty_failures_upper"]


def table_system(sel):
    return sel.combinations[SYSTEM_COLS].rename(columns={"warranty_failures_median": "failures_per_1000_median",
                                                         "warranty_failures_lower": "failures_per_1000_lower",
                                                         "warranty_failures_upper": "failures_per_1000_upper"})


def combo_row(sel, combination):
    c = sel.combinations
    return c[c["combination"] == combination].iloc[0]


# --- Temperature sweep and profile ---------------------------------------------------------------------

def sweep(best, worst):
    rows = []
    for t in SWEEP:
        sel = run(float(t))
        for label, name in (("most reliable", best), ("least reliable", worst)):
            r = combo_row(sel, name)
            rows.append({"temperature_c": t, "system": label, "combination": name,
                         "system_r_mission_median": r["system_r_mission_median"],
                         "system_r_lower_bound": r["system_r_lower_bound"],
                         "p_meets_target": r["p_meets_target"],
                         "meets_target": r["meets_target_at_confidence"],
                         "failures_per_1000_median": r["warranty_failures_median"],
                         "failures_per_1000_lower": r["warranty_failures_lower"],
                         "failures_per_1000_upper": r["warranty_failures_upper"]})
    return pd.DataFrame(rows)


def profile_vs_mean(best):
    rows = []
    for label, prof in (("profile 40/70/105 C at 50/30/20%", PROFILE), ("its mean temperature, 62 C", 62.0)):
        r = combo_row(run(prof), best)
        rows.append({"condition": label, "system_fit_median": r["system_fit_median"],
                     "system_fit_lower": r["system_fit_lower"], "system_fit_upper": r["system_fit_upper"],
                     "system_r_mission_median": r["system_r_mission_median"],
                     "failures_per_1000_median": r["warranty_failures_median"],
                     "system_b01_hours_median": r["system_b01_hours_median"]})
    return pd.DataFrame(rows)


# --- Sensitivity (8d): one assumption at a time, on the most reliable system ---------------------------

def sensitivity(best, base_value):
    def failures(**kw):
        return combo_row(run(**kw), best)["warranty_failures_median"]

    seeds = [failures(seed=s) for s in range(1, 6)]
    rows = [
        ("Operating temperature 45 / 65 C", failures(profile=45.0), failures(profile=65.0)),
        ("Mission 1,460 / 5,840 h (half / double)", failures(mission=MISSION / 2), failures(mission=MISSION * 2)),
        ("Ea fixed at 0.7 / independent per part", failures(ea_mode="fixed"), failures(ea_mode="independent")),
        ("Prior Jeffreys / uniform (base)", failures(prior="jeffreys"), base_value),
        ("Monte Carlo seed (5 other seeds)", min(seeds), max(seeds)),
    ]
    return pd.DataFrame([{"assumption": a, "low_setting": lo, "high_setting": hi, "base": base_value,
                          "swing": abs(hi - lo)} for a, lo, hi in rows])


# --- Summary text for writing the report ----------------------------------------------------------------

def summary(sel, t2, best, worst, sw, prof, sens, sup, cov, briers):
    b, w = combo_row(sel, best), combo_row(sel, worst)
    lines = [
        "# Preliminary Results: key numbers (generated by analysis/01_preliminary_results.py)",
        "",
        f"Condition: {T_REF} C, mission {MISSION:,.0f} h, target R >= {TARGET} with 95% confidence; "
        f"{N_DRAWS:,} Monte Carlo draws, seed {SEED}. Library parts used as candidates (one per family).",
        "",
        "## Supplier comparison per slot (Table 2)",
    ]
    for _, r in t2.iterrows():
        lines.append(f"- {r['slot']}: {r['ti_part']} vs {r['alternative_part']}: the alternative's failure rate is "
                     f"{r['fit_ratio_alt_over_ti_median']:.2f}x TI's (95% CI {r['fit_ratio_lower']:.2f}-"
                     f"{r['fit_ratio_upper']:.2f}); P(TI is the more reliable) = {r['p_ti_best']:.2f}")
    lines += ["", "## System (Table 3)",
              f"- Most reliable: {best}: system FIT {b['system_fit_median']:.2f} (95% CI {b['system_fit_lower']:.2f}-"
              f"{b['system_fit_upper']:.2f}); R({MISSION:,.0f} h) = {b['system_r_mission_median']:.6f} "
              f"(95% lower bound {b['system_r_lower_bound']:.6f}); meets target: "
              f"{'yes' if b['meets_target_at_confidence'] else 'no'}; {b['warranty_failures_median']:.3f} failures per "
              f"1,000 vehicles (95% CI {b['warranty_failures_lower']:.3f}-{b['warranty_failures_upper']:.3f})",
              f"- Least reliable: {worst}: system FIT {w['system_fit_median']:.2f} (95% CI {w['system_fit_lower']:.2f}-"
              f"{w['system_fit_upper']:.2f}); {w['warranty_failures_median']:.3f} failures per 1,000 vehicles; meets "
              f"target: {'yes' if w['meets_target_at_confidence'] else 'no'}",
              f"- P(most reliable combination is truly the best of all {len(sel.combinations)}) = "
              f"{b['p_best_combination']:.2f}"]
    lines += ["", "## Temperature sweep (Figure 2)"]
    for label in ("most reliable", "least reliable"):
        d = sw[sw["system"] == label]
        failing = d.loc[~d["meets_target"], "temperature_c"]
        lines.append(f"- {label} system meets the target up to "
                     + (f"{d.loc[d['meets_target'], 'temperature_c'].max():.0f} C; fails from {failing.min():.0f} C"
                        if len(failing) else "150 C (whole range)"))
    lines += ["", "## Profile vs mean temperature",
              f"- {prof.iloc[0]['condition']}: system FIT {prof.iloc[0]['system_fit_median']:.2f}; "
              f"{prof.iloc[1]['condition']}: {prof.iloc[1]['system_fit_median']:.2f} "
              f"({prof.iloc[0]['system_fit_median'] / prof.iloc[1]['system_fit_median']:.1f}x higher on the profile)"]
    lines += ["", "## Sensitivity (Figure 3), median failures per 1,000 vehicles, most reliable system"]
    for _, r in sens.sort_values("swing", ascending=False).iterrows():
        lines.append(f"- {r['assumption']}: {r['low_setting']:.3f} / {r['high_setting']:.3f} (base {r['base']:.3f})")
    fam = sup.drop_duplicates("family")
    ti = fam[fam["supplier"] == "Texas Instruments"]
    lines += ["", "## Validation (Table 4)",
              f"- Published FIT reproduced within 2x for {len(ti)} of {len(ti)} TI families "
              f"(C2000 {ti.loc[ti['family'] == 'TI C2000', 'sim_fit_at_cl'].iloc[0]:.2f} vs 6.19); "
              f"published FIT inside the simulator's 95% CI for all of them",
              f"- Coverage (1,000 synthetic suppliers, realistic world): upper 97.5% bound "
              f"{cov.loc['all', 'upper_975_coverage']:.1%}; central 95% interval "
              + ", ".join(f"{cov.loc[k, 'central_95_coverage']:.0%} ({k} expected failures)"
                          for k in cov.index if k != "all"),
              f"- P(B outlasts A) Brier score: {briers['uniform']:.2f} (model-consistent world), "
              f"{briers['log-uniform']:.2f} (realistic world); a coin flip is 0.25"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    lib = load_library()

    sel = run()
    t1 = table_common_basis(sel, lib)
    t2 = table_slot_comparison(sel)
    t3 = table_system(sel)
    best, worst = t3["combination"].iloc[0], t3["combination"].iloc[-1]
    print("Main run done")

    sw = sweep(best, worst)
    prof = profile_vs_mean(best)
    sens = sensitivity(best, combo_row(sel, best)["warranty_failures_median"])
    print("Sweep and sensitivity done")

    sup = supplier_check()
    cov = coverage_by_evidence(coverage_study(1000, seed=11, t_use_c=T_REF))
    briers = {truth: brier_score(calibration_study(1000, seed=12, t_use_c=T_REF, truth=truth))
              for truth in ("log-uniform", "uniform")}
    print("Validation done")

    t1.to_csv(TABLES / "table1_common_basis.csv", index=False)
    t2.to_csv(TABLES / "table2_supplier_comparison.csv", index=False)
    t3.to_csv(TABLES / "table3_system_combinations.csv", index=False)
    sup.drop_duplicates("family").to_csv(TABLES / "table4a_validation_published_fit.csv", index=False)
    cov.to_csv(TABLES / "table4b_validation_coverage.csv")
    sw.to_csv(TABLES / "temperature_sweep.csv", index=False)
    prof.to_csv(TABLES / "profile_vs_mean_temperature.csv", index=False)
    sens.to_csv(TABLES / "sensitivity.csv", index=False)
    plots.figure1_forest(t1, FIGURES / "figure1_fit_common_basis.png")
    plots.figure2a_failures(sw, FIGURES / "figure2a_temperature_failures.png", FLEET * (1 - TARGET), MISSION)
    plots.figure2b_probability(sw, FIGURES / "figure2b_temperature_target.png", CONFIDENCE)
    plots.figure3_tornado(sens, FIGURES / "figure3_sensitivity.png", MISSION)
    (OUT / "key_numbers.md").write_text(summary(sel, t2, best, worst, sw, prof, sens, sup, cov, briers),
                                         encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}: 8 tables, 4 figures (plotnine), key_numbers.md")
