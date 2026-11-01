# 02_significance.py
# Preliminary Results, significance and confidence (ROADMAP Section 9b). Kept apart from the
# simulator: it only CALLS functions/ and writes to reports/preliminary_results/.
#
# Part 1: statistics ABOUT the simulator (is it trustworthy?)
#   1a simulator vs the course chi-square formula (E18), per part, with Monte Carlo error
#   1b simulator vs published TI FIT: one-sample t-test on log10(simulated / published)
#   1c coverage of the 95% intervals: exact proportion CIs and binomial tests vs nominal
#   1d calibration of P(B better): Brier score with a bootstrap CI, calibration bins with CIs
#   1e Monte Carlo precision across 20 seeds
# Part 2: statistics the simulator PRODUCES on our data (55 C, 2,920 h, target R >= 0.999)
#   2a per part: 95% maximum failure rate and the target test (E18, E19), max demonstrated temperature (E20)
#   2b system: 95% lower bound on R and the target test, max demonstrated temperature (Monte Carlo)
#   2c supplier differences: exact two-rate test (E21) and the simulation p-value
#   2d temperature profile vs its mean temperature: paired ratio with 95% CI
#
# Run from the project root:  .venv/Scripts/python analysis/02_significance.py   (~4 minutes)

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
sys.path.append(str(Path(__file__).resolve().parent))
import plots  # noqa: E402  (plotnine figures, analysis/plots.py)
from functions.arrhenius import accel_factor  # noqa: E402
from functions.candidates import library_candidate, select  # noqa: E402
from functions.library import SLOTS  # noqa: E402
from functions.significance import (bootstrap_ci, max_demonstrated_temp, max_failure_rate,  # noqa: E402
                                    mc_standard_error, one_sample_t, proportion_ci, target_rate,
                                    target_test, two_rate_test)
from functions.simulator import DEFAULT_WARRANTY_HOURS, N_DRAWS, SEED  # noqa: E402
from functions.validation import (EVIDENCE_BINS, EVIDENCE_LABELS, calibration_study,  # noqa: E402
                                  coverage_study, supplier_check)

OUT = ROOT / "reports" / "preliminary_results"
TABLES, FIGURES = OUT / "tables", OUT / "figures"

T_REF, MISSION, TARGET, ALPHA, EA = 55, DEFAULT_WARRANTY_HOURS, 0.999, 0.05, 0.7
PROFILE = [(40, 0.5), (70, 0.3), (105, 0.2)]
SEEDS = range(1, 21)
CANDIDATES = ["F280049CPZQR", "R7F7016903AFP-C", "BQ79656PAPRQ1", "LTC6811-1", "ISO7741QDWRQ1",
              "ADuM141E", "TMP4719QDGSRQ1", "UCC21750QDWRQ1", "ADuM4135", "TMCS1101A4UQDRQ1"]

def candidates():
    return [library_candidate(p) for p in CANDIDATES]


def run(profile=T_REF, **kw):
    return select(candidates(), profile, MISSION, TARGET, top=100, **kw)


def d_use(c, temp=T_REF):
    """Device-hours at the use temperature with the suppliers' Ea (the chi-square method's known Ea)."""
    return c["test_hours"] * c["sample_size"] * accel_factor(temp, c["test_temp_c"], EA)


# ===================================== Part 1 =================================================

def p1a_chi_square_agreement():
    cands = candidates()
    sims = {c["name"]: [] for c in cands}
    for s in SEEDS:
        sel = run(ea_mode="fixed", seed=s)
        for c in cands:
            sims[c["name"]].append(np.quantile(sel.lam[c["name"]] * 1e9, 0.95))
    rows = []
    for c in cands:
        exact = float(max_failure_rate(c["failures"], d_use(c), 0.95)) * 1e9
        mc = mc_standard_error(sims[c["name"]])
        rows.append({"slot": c["slot"], "part": c["name"], "supplier": c["supplier"], "failures": c["failures"],
                     "chi_square_fit95": exact, "simulator_fit95_mean": mc["mean"],
                     "simulator_fit95_se_per_run": mc["se"],
                     "difference_pct": 100 * (mc["mean"] - exact) / exact,
                     "z": (mc["mean"] - exact) / (mc["se"] / np.sqrt(mc["runs"]))})
    return pd.DataFrame(rows)


def p1b_published(sup):
    fam = sup.drop_duplicates("family").copy()
    fam["log10_ratio"] = np.log10(fam["ratio"])
    fam["same_basis"] = fam["supplier"] == "Texas Instruments"
    t = one_sample_t(fam.loc[fam["same_basis"], "log10_ratio"])
    summary = pd.DataFrame([{"group": "TI families (same test data as published)", **t,
                             "mean_ratio": 10 ** t["mean"], "ratio_lower": 10 ** t["lower"],
                             "ratio_upper": 10 ** t["upper"]}])
    return fam[["family", "supplier", "fit_published", "sim_fit_at_cl", "ratio", "log10_ratio", "same_basis",
                "published_inside_sim_95ci"]], summary


def p1c_coverage(covs):
    rows = []
    for truth, cov in covs.items():
        groups = pd.cut(cov["expected_failures"], EVIDENCE_BINS, labels=EVIDENCE_LABELS)
        for label in EVIDENCE_LABELS + ["all"]:
            d = cov if label == "all" else cov[groups == label]
            c = proportion_ci(int(d["in_central_95"].sum()), len(d), p0=0.95)
            u = proportion_ci(int(d["below_upper_975"].sum()), len(d), p0=0.975, alternative="less")
            rows.append({"truth": truth, "expected_failures": label, "suppliers": len(d),
                         "central_95_coverage": c["proportion"], "central_lower": c["lower"],
                         "central_upper": c["upper"], "central_p_vs_95": c["p_value"],
                         "upper_975_coverage": u["proportion"], "upper_lower": u["lower"],
                         "upper_upper": u["upper"], "upper_p_below_975": u["p_value"]})
    return pd.DataFrame(rows)


def p1d_calibration(cals, rng):
    briers, bins = [], []
    edges = np.linspace(0, 1, 6)
    for truth, cal in cals.items():
        sq = (cal["p_b_outlasts_a"] - cal["b_truly_better"].astype(float)).to_numpy() ** 2
        b = bootstrap_ci(sq, np.mean, rng)
        briers.append({"truth": truth, "pairs": len(cal), "brier": b["estimate"], "brier_lower": b["lower"],
                       "brier_upper": b["upper"], "coin_flip": 0.25})
        groups = pd.cut(cal["p_b_outlasts_a"], edges, include_lowest=True)
        for interval, d in cal.groupby(groups, observed=True):
            ci = proportion_ci(int(d["b_truly_better"].sum()), len(d))
            bins.append({"truth": truth, "p_bin": str(interval), "pairs": len(d),
                         "mean_p_b_outlasts_a": d["p_b_outlasts_a"].mean(),
                         "share_b_truly_better": ci["proportion"], "lower": ci["lower"], "upper": ci["upper"]})
    return pd.DataFrame(briers), pd.DataFrame(bins)


def p1e_mc_precision(best):
    out = {"system FIT (median), most reliable system": [],
           "system R(2,920 h) 95% lower bound, most reliable system": [],
           "failures per 1,000 vehicles (median), most reliable system": [],
           "FIT (median), TI C2000": []}
    for s in SEEDS:
        sel = run(seed=s)
        r = sel.combinations[sel.combinations["combination"] == best].iloc[0]
        out["system FIT (median), most reliable system"].append(r["system_fit_median"])
        out["system R(2,920 h) 95% lower bound, most reliable system"].append(r["system_r_lower_bound"])
        out["failures per 1,000 vehicles (median), most reliable system"].append(r["warranty_failures_median"])
        out["FIT (median), TI C2000"].append(sel.candidates.set_index("name").loc["F280049CPZQR", "fit_median"])
    return pd.DataFrame([{"output": k, **mc_standard_error(v)} for k, v in out.items()])


# ===================================== Part 2 =================================================

def p2a_parts():
    rows = []
    for c in candidates():
        res = target_test(c["failures"], d_use(c), TARGET, MISSION, ALPHA)
        rows.append({"slot": c["slot"], "part": c["name"], "supplier": c["supplier"],
                     "test_temp_c": c["test_temp_c"], "failures": c["failures"],
                     "device_hours_at_55c": d_use(c), "fit95_max": res["lambda_max"] * 1e9,
                     "target_fit": res["lambda_target"] * 1e9, "mttf_min_hours": res["mttf_min_hours"],
                     "r_mission_min": res["r_mission_min"], "p_value": res["p_value"],
                     "demonstrated": res["demonstrated"],
                     "max_demonstrated_temp_c": max_demonstrated_temp(
                         c["failures"], c["test_hours"] * c["sample_size"], c["test_temp_c"], EA, TARGET, MISSION,
                         ALPHA)})
    return pd.DataFrame(rows)


def system_lower_bound(combination, temp):
    sel = run(float(temp))
    return sel.combinations.set_index("combination").loc[combination, "system_r_lower_bound"]


def system_max_temp(combination, lo=25.0, hi=150.0, tol=0.5):
    """Bisection for the temperature where the system's 95% lower bound on R(mission) = target."""
    if system_lower_bound(combination, hi) >= TARGET:
        return hi
    if system_lower_bound(combination, lo) < TARGET:
        return np.nan
    while hi - lo > tol:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if system_lower_bound(combination, mid) >= TARGET else (lo, mid)
    return (lo + hi) / 2


def p2b_system(sel):
    c = sel.combinations
    rows = []
    for label, r in (("most reliable", c.iloc[0]), ("least reliable", c.iloc[-1])):
        rows.append({"system": label, "combination": r["combination"],
                     "r_lower_bound_95": r["system_r_lower_bound"],
                     "p_value": 1 - r["p_meets_target"],            # simulation p-value: P(R < target)
                     "demonstrated": r["meets_target_at_confidence"],
                     "max_demonstrated_temp_c": system_max_temp(r["combination"])})
    return pd.DataFrame(rows)


def p2c_suppliers(sel):
    t = sel.candidates.set_index("name")
    rows = []
    cands = {c["name"]: c for c in candidates()}
    for slot in SLOTS:
        names = [n for n, c in cands.items() if c["slot"] == slot]
        if len(names) < 2:
            continue
        ti = next(n for n in names if cands[n]["supplier"] == "Texas Instruments")
        alt = next(n for n in names if n != ti)
        res = two_rate_test(cands[ti]["failures"], d_use(cands[ti]), cands[alt]["failures"], d_use(cands[alt]))
        rows.append({"slot": slot, "ti_part": ti, "alternative_part": alt,
                     "ti_failures": cands[ti]["failures"], "alt_failures": cands[alt]["failures"],
                     "ti_device_hours_55c": d_use(cands[ti]), "alt_device_hours_55c": d_use(cands[alt]),
                     "exact_p_one_sided": res["p_one_sided"], "exact_p_two_sided": res["p_two_sided"],
                     "simulation_p": 1 - t.loc[ti, "p_best_in_slot"],
                     "significant_at_05": min(res["p_one_sided"], 1 - t.loc[ti, "p_best_in_slot"]) < ALPHA})
    return pd.DataFrame(rows)


def p2d_profile(best):
    parts = best.split(" + ")
    prof, mean = run(PROFILE), run(62.0)                            # same seed: paired draws
    ratio = sum(prof.lam[p] for p in parts) / sum(mean.lam[p] for p in parts)
    q = np.quantile(ratio, [0.025, 0.5, 0.975])
    return pd.DataFrame([{"comparison": "system failure rate, 40/70/105 C profile / its 62 C mean",
                          "ratio_median": q[1], "ratio_lower": q[0], "ratio_upper": q[2],
                          "p_ratio_le_1": float(np.mean(ratio <= 1))}])


# ===================================== Key numbers ============================================

def key_numbers(a, pub_sum, cov, briers, mc, parts, sysrows, sup, prof):
    s = pub_sum.iloc[0]
    lines = ["# Preliminary Results: significance and confidence (generated by analysis/02_significance.py)", "",
             f"Condition: {T_REF} C, mission {MISSION:,.0f} h, target R >= {TARGET}; tests at alpha = {ALPHA}; "
             f"seed {SEED} (20 seeds for Monte Carlo error).", "",
             "## Part 1: is the simulator trustworthy?",
             f"- 1a Simulator vs course chi-square formula (95% max FIT, 10 parts, Ea 0.7): largest difference "
             f"{a['difference_pct'].abs().max():.2f}%; all |z| < {a['z'].abs().max():.1f} (within Monte Carlo error).",
             f"- 1b Simulator vs published TI FIT (6 families): mean ratio {s['mean_ratio']:.3f} (95% CI "
             f"{s['ratio_lower']:.3f}-{s['ratio_upper']:.3f}); one-sample t-test on log10 ratio t = {s['t']:.2f}, "
             f"p = {s['p_value']:.2f}: not significantly different from the published values."]
    for truth in ("log-uniform", "uniform"):
        d = cov[cov["truth"] == truth].set_index("expected_failures")
        lines.append(f"- 1c Coverage ({truth} truth): central 95% interval " + "; ".join(
            f"{k}: {d.loc[k, 'central_95_coverage']:.1%} ({d.loc[k, 'central_lower']:.1%}-"
            f"{d.loc[k, 'central_upper']:.1%}, p = {d.loc[k, 'central_p_vs_95']:.2g})" for k in d.index))
        lines.append(f"  upper 97.5% bound overall {d.loc['all', 'upper_975_coverage']:.1%} "
                     f"(95% CI {d.loc['all', 'upper_lower']:.1%}-{d.loc['all', 'upper_upper']:.1%}; "
                     f"test of coverage below 97.5%: p = {d.loc['all', 'upper_p_below_975']:.2g})")
    for _, b in briers.iterrows():
        lines.append(f"- 1d Brier score of P(B outlasts A), {b['truth']} truth: {b['brier']:.3f} (95% bootstrap CI "
                     f"{b['brier_lower']:.3f}-{b['brier_upper']:.3f}); coin flip 0.25")
    for _, r in mc.iterrows():
        lines.append(f"- 1e Monte Carlo error, {r['output']}: mean {r['mean']:.4g}, SE per run {r['se']:.2g} "
                     f"({r['relative_se']:.1%})")
    lines += ["", "## Part 2: what the simulator concludes on our data"]
    p = parts.sort_values("max_demonstrated_temp_c")
    lines.append(f"- 2a All {len(parts)} parts demonstrate the target at 55 C (largest p = {parts['p_value'].max():.2g}); "
                 f"95% max FIT from {parts['fit95_max'].min():.3g} to {parts['fit95_max'].max():.3g} "
                 f"vs the target {parts['target_fit'].iloc[0]:.0f} FIT")
    lines.append("- 2a Maximum demonstrated temperature: " + "; ".join(
        f"{r['part']} {r['max_demonstrated_temp_c']:.0f} C" for _, r in p.iterrows()))
    for _, r in sysrows.iterrows():
        pv = f"p < {1 / N_DRAWS:.4f}" if r["p_value"] == 0 else f"p = {r['p_value']:.3g}"
        lines.append(f"- 2b System, {r['system']} ({r['combination']}): 95% lower bound R = {r['r_lower_bound_95']:.6f}, "
                     f"{pv} (share of {N_DRAWS:,} draws with R < target), demonstrated up to "
                     f"{r['max_demonstrated_temp_c']:.0f} C")
    for _, r in sup.iterrows():
        lines.append(f"- 2c {r['slot']}: {r['ti_part']} ({r['ti_failures']} failures) vs {r['alternative_part']} "
                     f"({r['alt_failures']} failures): exact test p = {r['exact_p_one_sided']:.2f}, simulation "
                     f"p = {r['simulation_p']:.2f}; significant at 0.05: {'yes' if r['significant_at_05'] else 'no'}")
    q = prof.iloc[0]
    lines.append(f"- 2d {q['comparison']}: {q['ratio_median']:.2f}x (95% CI {q['ratio_lower']:.2f}-"
                 f"{q['ratio_upper']:.2f}); P(ratio <= 1) = {q['p_ratio_le_1']:.3f}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    main = run()
    best = main.combinations["combination"].iloc[0]
    a = p1a_chi_square_agreement()
    fam, pub_sum = p1b_published(supplier_check())
    covs = {t: coverage_study(1000, seed=11, t_use_c=T_REF, truth=t) for t in ("log-uniform", "uniform")}
    cals = {t: calibration_study(1000, seed=12, t_use_c=T_REF, truth=t) for t in ("log-uniform", "uniform")}
    cov = p1c_coverage(covs)
    briers, cal_bins = p1d_calibration(cals, rng)
    mc = p1e_mc_precision(best)
    print("Part 1 done")

    parts = p2a_parts()
    sysrows = p2b_system(main)
    sup = p2c_suppliers(main)
    prof = p2d_profile(best)
    print("Part 2 done")

    for name, df in {"sig_1a_simulator_vs_chi_square": a, "sig_1b_simulator_vs_published": fam,
                     "sig_1b_t_test": pub_sum, "sig_1c_coverage": cov, "sig_1d_brier": briers,
                     "sig_1d_calibration_bins": cal_bins, "sig_1e_monte_carlo_error": mc,
                     "sig_2a_parts_target_test": parts, "sig_2b_system_target_test": sysrows,
                     "sig_2c_supplier_tests": sup, "sig_2d_profile_vs_mean": prof}.items():
        df.to_csv(TABLES / f"{name}.csv", index=False)
    plots.sig_1a_chi_square(a, FIGURES / "sig_1a_simulator_vs_chi_square.png")
    plots.sig_1b_published(fam, pub_sum, FIGURES / "sig_1b_simulator_vs_published.png")
    plots.sig_1c_coverage(cov, FIGURES / "sig_1c_coverage.png")
    plots.sig_1d_calibration(cal_bins, briers, FIGURES / "sig_1d_calibration.png")
    plots.sig_2a_max_rate(parts, FIGURES / "sig_2a_max_failure_rate.png")
    plots.sig_2b_max_temp(parts, sysrows, FIGURES / "sig_2b_max_demonstrated_temperature.png", T_REF)
    (OUT / "key_numbers_significance.md").write_text(
        key_numbers(a, pub_sum, cov, briers, mc, parts, sysrows, sup, prof), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}: 11 tables, 6 figures (plotnine), key_numbers_significance.md")
