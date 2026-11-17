# 01_results.py
# Rough draft: results of the simulator (method v4, the course exponential method; ROADMAP Section 9d).
# Writes reports/rough_draft/results/{tables,figures}/ and key_numbers.md. Only calls functions/ through
# case_study.py and functions.validation. The Preliminary Results (reports/preliminary_results/) are not
# touched.
#   R1  every part on one basis (55 C, 2,920 h): AF, D, FIT estimate and 2.5th-97.5th percentile, 95% maximum,
#       60% bound, FIT per vehicle, meets target                                      (E2-E5, E17-E18, A10)
#   R2  validation 1: our 60% bound vs the published FIT                               (E4, A11, Section 11)
#   R3  validation 2: known-truth coverage of the course interval                       (E4, Section 11)
#   R4  the three picks and the least reliable combination                              (E8, A13)
#   R5  temperature sweep of the after/before systems                                   (E2, E6)
#   R6  sensitivity table: one baseline, one change per row                             (method item 6)
#   R7  what the tests can demonstrate: ppm per part and the data 1 ppm would need      (A13)
#   R8  life models tried (lognormal, Weibull): do the picks change?                    (E24-E26, A16)
#   .venv/Scripts/python analysis/rough_draft/01_results.py

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2

HERE = Path(__file__).resolve().parent
sys.path.extend([str(HERE), str(HERE.parent)])
import case_study as cs  # noqa: E402
import plots  # noqa: E402
from functions.arrhenius import accel_factor  # noqa: E402
from functions.library import load_library  # noqa: E402
from functions.life_models import LOGNORMAL_SIGMA, WEIBULL_BETA  # noqa: E402
from functions.validation import coverage_by_evidence, coverage_study, supplier_check  # noqa: E402

OUT = cs.OUT / "results"
TABLES, FIGURES = OUT / "tables", OUT / "figures"
PICKS = {"most_reliable": "Most reliable", "safest": "Safest", "cheapest": "Cheapest meeting target"}


def fmt(x, nd=3):
    if x == 0:
        return "0"
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    return f"{x:.{nd}g}"


# --- R1 ----------------------------------------------------------------------------------------------
def r1_parts(sel, lib):
    info = lib.set_index("part")
    mission = sel.settings["mission_hours"]
    t = sel.candidates
    out = pd.DataFrame({
        "slot": t["slot"].astype(str), "supplier": t["supplier"], "part": t["name"],
        "test_temp_c": t["test_temp_c"], "sample_size": [info.loc[p, "sample_size"] for p in t["name"]],
        "test_hours": [info.loc[p, "test_hours"] for p in t["name"]], "failures": t["failures"],
        "af": t["af_eff"], "device_hours_use": t["device_hours_use"],
        "fit_estimate": t["fit_estimate"], "fit_lower": t["fit_lower"], "fit_upper": t["fit_upper"],
        "fit_95_max": t["fit_upper_one_sided"], "fit_60_bound": t["fit_upper_60"],
        "qty_per_vehicle": t["qty_per_vehicle"], "fit_per_vehicle": t["fit_per_vehicle_estimate"],
        "rank_in_slot": t["rank_in_slot"], "meets_target": t["meets_target_at_confidence"],
        "unit_price_usd": t["unit_price_usd"]})
    # E7: probability one part fails within the mission, in parts per million
    for col, src in (("ppm_estimate", "fit_estimate"), ("ppm_95_max", "fit_95_max")):
        out[col] = 1e6 * (1 - np.exp(-out[src] / 1e9 * mission))
    return out


# --- R2 ----------------------------------------------------------------------------------------------
def r2_validation(lib):
    v = supplier_check(lib)
    v = v[v["part"].isin(cs.PARTS)]
    return v[["slot", "supplier", "part", "ref_temp_c", "ref_conf_level", "fit_published", "fit_published_status",
              "fit_calculated", "ratio", "verdict", "af_published", "af_calculated"]].reset_index(drop=True)


# --- R3 ----------------------------------------------------------------------------------------------
def r3_coverage(n=10_000, seed=11):
    return coverage_by_evidence(coverage_study(n_suppliers=n, seed=seed)).reset_index()


# --- R4 ----------------------------------------------------------------------------------------------
def combo_summary(label, c, settings):
    return {"pick": label, "combination": c["combination"],
            "system_fit_estimate": c["system_fit_estimate"], "system_fit_lower": c["system_fit_lower"],
            "system_fit_upper": c["system_fit_upper"], "system_fit_95_max": c["system_fit_upper_one_sided"],
            "target_fit": settings["target_fit"], "meets_target": c["meets_target_at_confidence"],
            "r_mission_estimate": c["system_r_mission_estimate"], "r_mission_95_lower_bound": c["system_r_lower_bound"],
            "failures_per_1000_estimate": c["warranty_failures_estimate"],
            "failures_per_1000_lower": c["warranty_failures_lower"],
            "failures_per_1000_upper": c["warranty_failures_upper"],
            "purchase_per_1000": c["purchase_cost"], "total_cost_per_1000": c["total_cost_estimate"]}


def r4_picks(sel):
    rows = [combo_summary(name, sel.picks[k], sel.settings) for k, name in PICKS.items() if sel.picks[k]]
    rows.append(combo_summary("Least reliable (the 'before' choice)", cs.least_reliable(sel), sel.settings))
    return pd.DataFrame(rows)


# --- R5 ----------------------------------------------------------------------------------------------
def r5_sweep(after, before, temps=range(25, 151, 5)):
    rows = []
    for temp in temps:
        sel = cs.run(temp)
        combos = sel.combinations.set_index("combination")
        for label, name in (("after: most reliable", after), ("before: least reliable", before)):
            c = combos.loc[name]
            rows.append({"temperature_c": temp, "system": label, "combination": name,
                         "fit_estimate": c["system_fit_estimate"], "fit_lower": c["system_fit_lower"],
                         "fit_upper": c["system_fit_upper"], "fit_95_max": c["system_fit_upper_one_sided"],
                         "meets_target": c["meets_target_at_confidence"], "target_fit": sel.settings["target_fit"]})
    sw = pd.DataFrame(rows)
    sw["fit_lower_plot"] = sw["fit_lower"].clip(lower=sw["fit_estimate"].min() / 10)
    return sw


def max_meeting_temperature(sw, system):
    ok = sw[(sw["system"] == system) & sw["meets_target"]]
    return float(ok["temperature_c"].max()) if len(ok) else None


# --- R6 ----------------------------------------------------------------------------------------------
def r6_sensitivity(base):
    b_rel, b_cheap = base.picks["most_reliable"]["combination"], base.picks["cheapest"]["combination"]

    def row(setting, sel, case="estimate", note=""):
        c = sel.picks["most_reliable"]
        cheap = sel.picks["cheapest"]
        return {"setting": setting, "most_reliable": c["combination"],
                "system_fit_estimate": c[f"system_fit_{case}"],
                "system_fit_lower": c["system_fit_lower"], "system_fit_upper": c["system_fit_upper"],
                "system_fit_95_max": c["system_fit_upper_one_sided"], "target_fit": sel.settings["target_fit"],
                "meets_target": c["meets_target_at_confidence"],
                "combinations_meeting_target": sel.picks["n_meeting_target"],
                "combinations": sel.picks["n_combinations"],
                "same_most_reliable": c["combination"] == b_rel,
                "same_cheapest_meeting": ("yes" if cheap["combination"] == b_cheap else "no") if cheap
                else "none meets the target", "note": note}

    ea = cs.run(ea_range=True)
    c = ea.picks["most_reliable"]
    rows = [row("Baseline: 55 C, 2,920 h, Ea 0.7 eV, estimate", base),
            row("Every part at its 2.5th percentile rate", base, "lower", "lower bound 0 for zero-failure parts"),
            row("Every part at its 97.5th percentile rate", base, "upper"),
            row("Ea 0.5 eV", cs.run(ea_ev=0.5)), row("Ea 0.9 eV", cs.run(ea_ev=0.9)),
            row("Ea 0.5-0.9 eV (Monte Carlo, 5,000 draws)", ea,
                note=f"system FIT {fmt(c['system_fit_ea_lower'])}-{fmt(c['system_fit_ea_upper'])} over the Ea draws; "
                     f"target met at the unfavourable Ea: {'yes' if c['system_meets_target_at_ea_worst'] else 'NO'}"),
            row("Mission 1,460 h (half)", cs.run(mission=cs.MISSION / 2)),
            row("Mission 5,840 h (double)", cs.run(mission=cs.MISSION * 2)),
            row(f"Mission {cs.TI_DESIGN_LIFE_H:,.0f} h (TI design life, 15 yr x 12%)", cs.run(mission=cs.TI_DESIGN_LIFE_H)),
            row("Temperature band 40-105 C", cs.run(cs.BAND),
                note="worst case at 105 C reported by the simulator"),
            row("Target 0.9999", cs.run(target=0.9999)),
            row("One part per slot (no quantities)", cs.run(qty=False))]
    for model, shape, label in LIFE_MODELS[1:]:
        rows.append(row(f"Life model: {label}", cs.run(life_model=model, shape=shape),
                        note="average failure rate over the mission (E26)"))
    return pd.DataFrame(rows)


# --- R7 ----------------------------------------------------------------------------------------------
def r7_ppm(r1, mission):
    # Zero-failure demonstration of 1 ppm over the mission at 95%: D = chi2(0.95; 2) / 2 / lambda_1ppm (E18)
    lam_1ppm = -np.log(1 - 1e-6) / mission
    d_needed = chi2.ppf(0.95, 2) / 2 / lam_1ppm
    out = r1[["slot", "supplier", "part", "ppm_estimate", "ppm_95_max", "device_hours_use"]].copy()
    out["meets_1ppm_at_95"] = out["ppm_95_max"] <= 1
    out["use_device_hours_needed_for_1ppm"] = d_needed
    out["test_size_multiple_needed"] = d_needed / out["device_hours_use"]
    return out


# --- R8 ----------------------------------------------------------------------------------------------
LIFE_MODELS = [("exponential", None, "exponential (final model)"),
               ("lognormal", LOGNORMAL_SIGMA["defects"], f"lognormal sigma {LOGNORMAL_SIGMA['defects']:g} (defects)"),
               ("lognormal", LOGNORMAL_SIGMA["wear-out"], f"lognormal sigma {LOGNORMAL_SIGMA['wear-out']:g} (wear-out)"),
               ("weibull", WEIBULL_BETA["defects"], f"Weibull beta {WEIBULL_BETA['defects']:g} (defects)"),
               ("weibull", WEIBULL_BETA["wear-out"], f"Weibull beta {WEIBULL_BETA['wear-out']:g} (wear-out)")]


def r8_life_models():
    rows, ref = [], None
    for model, shape, label in LIFE_MODELS:
        sel = cs.run(life_model=model, shape=shape)
        picks = {k: (sel.picks[k]["combination"] if sel.picks[k] else "(none meets the target)") for k in PICKS}
        ref = picks if ref is None else ref
        row = {"model": label}
        for k, name in PICKS.items():
            row[name] = picks[k]
            row[f"{name}: same as exponential"] = picks[k] == ref[k]
        row["most reliable system AFR (FIT)"] = sel.picks["most_reliable"]["system_fit_estimate"]
        row["combinations meeting target"] = sel.picks["n_meeting_target"]
        rows.append(row)
    return pd.DataFrame(rows)


def key_numbers(sel, r1, r2, r3, r4, sw, sens, r7, r8):
    s = sel.settings
    after, before = r4.iloc[0], r4.iloc[-1]
    ti = r2[r2["supplier"] == "Texas Instruments"]
    cov_all = r3.set_index("expected_failures").loc["all"]
    lines = [
        "# Rough draft: results key numbers (generated by analysis/rough_draft/01_results.py)", "",
        "Method v4: the course exponential method (Lesson 12, Recitation 12). Baseline: 55 C, mission 2,920 h "
        "(8-year EV battery warranty x 1 h/day, A7), Ea 0.7 eV, target R(mission) >= 0.999 with 95% confidence "
        f"(at most {s['target_fit']:.0f} FIT for the system). Every number is the estimate with its 2.5th-97.5th "
        "percentile unless it is a bound. Case study: all six slots, realistic quantities per vehicle (A17), "
        "Sheet2 prices.", "",
        "## Data caveat",
        "Results show the reliability **demonstrated by the qualification tests in our parameter table**. The RH850 "
        "has one 231-device test here, while Renesas's published FIT rests on far more data, so it is probably more "
        "reliable than shown. Our table gives the ADI parts lower FITs than ADI publishes, so they may be optimistic "
        "(R2).", "",
        "## R1 Parts on one basis (55 C)",
    ]
    for _, r in r1.iterrows():
        lines.append(f"- {r['slot']}, {r['part']} ({r['supplier']}, x{r['qty_per_vehicle']} per vehicle): FIT "
                     f"{fmt(r['fit_estimate'])} ({fmt(r['fit_lower'])}-{fmt(r['fit_upper'])}); 95% max {fmt(r['fit_95_max'])}; "
                     f"60% bound {fmt(r['fit_60_bound'])}; per vehicle {fmt(r['fit_per_vehicle'])}; AF {r['af']:.1f}; "
                     f"rank {r['rank_in_slot']} in slot")
    lines += ["", "## R2 Validation against published FITs",
              f"- TI parts: our 60% bound / published = {ti['ratio'].min():.2f}-{ti['ratio'].max():.2f} "
              f"({len(ti)} parts; 1 = reproduced). C2000: {fmt(ti.loc[ti['part'] == 'F280049CPZQR', 'fit_calculated'].iloc[0])} "
              f"vs published {fmt(ti.loc[ti['part'] == 'F280049CPZQR', 'fit_published'].iloc[0])}."]
    for _, r in r2[r2["supplier"] != "Texas Instruments"].iterrows():
        lines.append(f"- {r['part']}: calculated {fmt(r['fit_calculated'])} vs published {fmt(r['fit_published'])} "
                     f"({r['fit_published_status']}): {r['verdict']}")
    lines += ["", "## R3 Coverage of the course 95% interval (10,000 synthetic suppliers with known true FIT)",
              f"- Central 95% interval contains the true FIT: {100 * cov_all['central_95_coverage']:.1f}%; "
              f"true FIT below the 97.5th percentile: {100 * cov_all['upper_975_coverage']:.1f}%; "
              f"{100 * cov_all['share_zero_failures']:.0f}% of the synthetic tests had zero failures."]
    lines += ["", "## R4 Picks (55 C, 2,920 h, per 1,000 vehicles)"]
    for _, r in r4.iterrows():
        lines.append(f"- {r['pick']}: {r['combination']}: system FIT {fmt(r['system_fit_estimate'])} "
                     f"({fmt(r['system_fit_lower'])}-{fmt(r['system_fit_upper'])}); 95% max {fmt(r['system_fit_95_max'])} "
                     f"vs {r['target_fit']:.0f} -> meets target: {'yes' if r['meets_target'] else 'NO'}; failures per "
                     f"1,000 {fmt(r['failures_per_1000_estimate'])} ({fmt(r['failures_per_1000_lower'])}-"
                     f"{fmt(r['failures_per_1000_upper'])}); purchase ${r['purchase_per_1000']:,.0f}")
    lines.append(f"- Combinations evaluated: {sel.picks['n_combinations']}; meeting the target: "
                 f"{sel.picks['n_meeting_target']}. Least reliable / most reliable system FIT: "
                 f"{before['system_fit_estimate'] / after['system_fit_estimate']:.2f}x.")
    lines += ["", "## R5 Temperature",
              f"- Highest temperature (5 C steps) at which the target is still demonstrated: after (most reliable) "
              f"{max_meeting_temperature(sw, 'after: most reliable')} C; before (least reliable) "
              f"{max_meeting_temperature(sw, 'before: least reliable')} C."]
    lines += ["", "## R6 Sensitivity (most reliable combination; 'same' = same pick as the baseline)"]
    for _, r in sens.iterrows():
        lines.append(f"- {r['setting']}: system FIT {fmt(r['system_fit_estimate'])}, 95% max {fmt(r['system_fit_95_max'])} "
                     f"vs {r['target_fit']:.0f}, meets: {'yes' if r['meets_target'] else 'NO'}, "
                     f"{r['combinations_meeting_target']}/{r['combinations']} meet; same most reliable: "
                     f"{'yes' if r['same_most_reliable'] else 'NO'}; same cheapest meeting: "
                     f"{r['same_cheapest_meeting']}" + (f" ({r['note']})" if r["note"] else ""))
    lines += ["", "## R7 What the tests can demonstrate (per part, over 2,920 h at 55 C)",
              f"- Parts demonstrating under 1 ppm at 95%: {int(r7['meets_1ppm_at_95'].sum())} of {len(r7)}; on the "
              f"estimate: {int((r7['ppm_estimate'] < 1).sum())} of {len(r7)}.",
              f"- 1 ppm with zero failures needs {r7['use_device_hours_needed_for_1ppm'].iloc[0]:.3g} equivalent "
              f"device-hours at 55 C; our tests are {r7['test_size_multiple_needed'].min():.1f}-"
              f"{r7['test_size_multiple_needed'].max():,.0f} times too small."]
    lines += ["", "## R8 Life models tried (internal comparison, shown as one table)"]
    for _, r in r8.iterrows():
        same = [n for n in PICKS.values() if r[f"{n}: same as exponential"]]
        lines.append(f"- {r['model']}: most reliable {r['Most reliable']}; same picks as the exponential: "
                     f"{len(same)} of 3 ({', '.join(same) if same else 'none'}); most reliable system AFR "
                     f"{fmt(r['most reliable system AFR (FIT)'])} FIT")
    return "\n".join(lines) + "\n"


def main():
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    lib = load_library()
    sel = cs.run(lib=lib)
    r1, r2, r3, r4 = r1_parts(sel, lib), r2_validation(lib), r3_coverage(), r4_picks(sel)
    after, before = r4.iloc[0]["combination"], r4.iloc[-1]["combination"]
    sw = r5_sweep(after, before)
    sens = r6_sensitivity(sel)
    r7, r8 = r7_ppm(r1, sel.settings["mission_hours"]), r8_life_models()
    for name, t in (("r1_parts_common_basis", r1), ("r2_validation_published_fit", r2), ("r3_coverage", r3),
                    ("r4_picks", r4), ("r5_temperature_sweep", sw), ("r6_sensitivity", sens), ("r7_ppm", r7),
                    ("r8_life_models", r8)):
        t.to_csv(TABLES / f"{name}.csv", index=False)
    plots.rd_fig1_parts(r1, FIGURES / "figure1_parts_fit.png")
    plots.rd_fig2_temperature(sw, FIGURES / "figure2_temperature.png", sel.settings["target_fit"])
    plots.rd_fig3_sensitivity(sens, FIGURES / "figure3_sensitivity.png", sens.iloc[0]["system_fit_estimate"])
    (OUT / "key_numbers.md").write_text(key_numbers(sel, r1, r2, r3, r4, sw, sens, r7, r8), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(cs.ROOT)}")


if __name__ == "__main__":
    main()
