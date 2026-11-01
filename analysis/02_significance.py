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

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
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

SUPPLIER_COLORS = {"Texas Instruments": "#2a78d6", "Analog Devices": "#eb6834", "Renesas Electronics": "#1baf7a"}
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK_2, GRID, SURFACE, MUTED = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#a3a29c"


def style(ax, grid_axis="y"):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK_2)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def title(ax, text, pad=6):
    ax.set_title(text, color=INK, fontsize=11, loc="left", pad=pad)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIGURES / name, dpi=200)
    plt.close(fig)


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


# ===================================== Figures ================================================

def fig_chi_square(a):
    fig, ax = plt.subplots(figsize=(5.6, 5.2), facecolor=SURFACE)
    style(ax, "both")
    ax.set_xscale("log")
    ax.set_yscale("log")
    lo, hi = a["chi_square_fit95"].min() / 2, a["chi_square_fit95"].max() * 2
    ax.plot([lo, hi], [lo, hi], color=INK_2, linestyle="--", linewidth=1)
    ax.text(hi / 1.3, hi / 1.05, "simulator = formula", color=INK_2, fontsize=8, ha="right", va="top", rotation=45)
    for _, r in a.iterrows():
        ax.plot(r["chi_square_fit95"], r["simulator_fit95_mean"], "o", color=SUPPLIER_COLORS[r["supplier"]],
                markersize=8, markeredgecolor=SURFACE, markeredgewidth=2)
    handles = [plt.Line2D([], [], color=c, marker="o", linestyle="", markersize=7, label=n)
               for n, c in SUPPLIER_COLORS.items()]
    ax.legend(handles=handles, frameon=False, fontsize=8, loc="upper left")
    ax.set_xlabel("95% maximum FIT, course chi-square formula", color=INK, fontsize=9)
    ax.set_ylabel("95% FIT from the simulator (mean of 20 seeds)", color=INK, fontsize=9)
    title(ax, f"1a. Simulator vs chi-square: max difference {a['difference_pct'].abs().max():.1f}%")
    save(fig, "sig_1a_simulator_vs_chi_square.png")


def fig_published(fam, summary):
    f = fam.sort_values("log10_ratio").reset_index(drop=True)
    s = summary.iloc[0]
    fig, ax = plt.subplots(figsize=(7.5, 4.4), facecolor=SURFACE)
    style(ax, "x")
    ax.set_xscale("log")
    ax.axvspan(s["ratio_lower"], s["ratio_upper"], color=BLUE, alpha=0.12, linewidth=0)
    ax.axvline(1, color=INK_2, linestyle="--", linewidth=1)
    for i, r in f.iterrows():
        if r["same_basis"]:
            ax.plot(r["ratio"], i, "o", color=BLUE, markersize=8, markeredgecolor=SURFACE, markeredgewidth=2)
        else:
            ax.plot(r["ratio"], i, "o", markerfacecolor=SURFACE, markeredgecolor=MUTED, markersize=7, markeredgewidth=1.5)
    ax.set_yticks(range(len(f)), f["family"])
    handles = [plt.Line2D([], [], color=BLUE, marker="o", linestyle="", markersize=7,
                          label="TI: same test data as published"),
               plt.Line2D([], [], color=MUTED, marker="o", linestyle="", markerfacecolor=SURFACE, markersize=7,
                          label="published value rests on other data (Section 14)"),
               plt.Rectangle((0, 0), 1, 1, color=BLUE, alpha=0.12, label="95% CI of the TI mean ratio")]
    ax.legend(handles=handles, frameon=False, fontsize=8, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=1)
    ax.set_xlabel("Simulated / published FIT at 55 C, 60% (log scale; 1 = identical)", color=INK, fontsize=9)
    title(ax, f"1b. Simulator vs published FIT\nTI mean ratio {s['mean_ratio']:.2f} (95% CI "
              f"{s['ratio_lower']:.2f}-{s['ratio_upper']:.2f}), one-sample t-test p = {s['p_value']:.2f}", pad=58)
    save(fig, "sig_1b_simulator_vs_published.png")


def fig_coverage(cov):
    d = cov[(cov["truth"] == "log-uniform") & (cov["expected_failures"] != "all")].reset_index(drop=True)
    x = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(7.5, 4.4), facecolor=SURFACE)
    style(ax)
    for off, col, key, label in ((-0.12, BLUE, "central", "central 95% interval"),
                                 (0.12, ORANGE, "upper", "upper 97.5% bound")):
        y = 100 * d[f"{key}_95_coverage" if key == "central" else "upper_975_coverage"]
        lo, hi = 100 * d[f"{key}_lower"], 100 * d[f"{key}_upper"]
        ax.errorbar(x + off, y, yerr=[y - lo, hi - y], fmt="o", color=col, markersize=7, capsize=3,
                    linewidth=1.5, markeredgecolor=SURFACE, label=label)
    ax.axhline(95, color=BLUE, linestyle="--", linewidth=1)
    ax.axhline(97.5, color=ORANGE, linestyle=":", linewidth=1)
    ax.text(0.45, 89, "nominal 95% (dashed) / 97.5% (dotted)", color=INK_2, fontsize=8, ha="center")
    ax.set_xticks(x, [f"{b}\n({n} suppliers)" for b, n in zip(d["expected_failures"], d["suppliers"])])
    ax.set_xlim(-0.5, len(d) - 0.5)
    ax.set_ylim(0, 105)
    ax.set_xlabel("Failures the test was expected to see", color=INK, fontsize=9)
    ax.set_ylabel("Coverage of the true FIT, % (exact 95% CI)", color=INK, fontsize=9)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    title(ax, "1c. Do the simulator's intervals contain the truth? (1,000 known-truth suppliers)")
    save(fig, "sig_1c_coverage.png")


def fig_calibration(bins, briers):
    fig, ax = plt.subplots(figsize=(5.6, 5.2), facecolor=SURFACE)
    style(ax, "both")
    ax.plot([0, 1], [0, 1], color=INK_2, linestyle="--", linewidth=1)
    for (truth, col), off in zip((("uniform", BLUE), ("log-uniform", ORANGE)), (-0.006, 0.006)):
        d = bins[bins["truth"] == truth]
        b = briers.set_index("truth").loc[truth]
        y = d["share_b_truly_better"]
        ax.errorbar(d["mean_p_b_outlasts_a"] + off, y, yerr=[y - d["lower"], d["upper"] - y], fmt="o-", color=col,
                    markersize=6, capsize=3, linewidth=1.5, markeredgecolor=SURFACE,
                    label=f"true FIT {truth}: Brier {b['brier']:.2f} ({b['brier_lower']:.2f}-{b['brier_upper']:.2f})")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Simulator's P(B outlasts A), binned", color=INK, fontsize=9)
    ax.set_ylabel("Share of pairs where B is truly better (95% CI)", color=INK, fontsize=9)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    title(ax, "1d. Calibration of P(B outlasts A); a coin flip scores 0.25")
    save(fig, "sig_1d_calibration.png")


def fig_parts(p):
    d = p.copy()
    d["slot"] = pd.Categorical(d["slot"], categories=SLOTS, ordered=True)
    d = d.sort_values(["slot", "fit95_max"], ascending=[False, False]).reset_index(drop=True)
    target = d["target_fit"].iloc[0]
    fig, ax = plt.subplots(figsize=(8, 5), facecolor=SURFACE)
    style(ax, "x")
    ax.set_xscale("log")
    for i, r in d.iterrows():
        ax.plot(r["fit95_max"], i, "o", color=SUPPLIER_COLORS[r["supplier"]], markersize=8,
                markeredgecolor=SURFACE, markeredgewidth=2)
    ax.axvline(target, color=INK_2, linestyle="--", linewidth=1)
    ax.text(target, len(d) - 0.4, f"target: {target:.0f} FIT \n(R = 0.999 over 2,920 h) ", color=INK_2, fontsize=8,
            va="top", ha="right")
    ax.set_yticks(range(len(d)), [f"{r['slot']}: {r['part']}" for _, r in d.iterrows()])
    ax.set_xlim(right=target * 4)
    handles = [plt.Line2D([], [], color=c, marker="o", linestyle="", markersize=7, label=n)
               for n, c in SUPPLIER_COLORS.items()]
    ax.legend(handles=handles, frameon=False, fontsize=8, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3)
    ax.set_xlabel("95% maximum failure rate at 55 C, FIT (chi-square; left of the line = target demonstrated)",
                  color=INK, fontsize=9)
    title(ax, "2a. Every part demonstrates the target at 55 C (all p < 0.001)", pad=26)
    save(fig, "sig_2a_max_failure_rate.png")


def fig_max_temp(p, sysrows):
    d = p.copy()
    d["slot"] = pd.Categorical(d["slot"], categories=SLOTS, ordered=True)
    d = d.sort_values(["slot", "max_demonstrated_temp_c"], ascending=[False, True]).reset_index(drop=True)
    labels = [f"{r['slot']}: {r['part']}" for _, r in d.iterrows()]
    values = list(d["max_demonstrated_temp_c"])
    colors = [SUPPLIER_COLORS[s] for s in d["supplier"]]
    for _, r in sysrows.iloc[::-1].iterrows():
        labels.append(f"SYSTEM, {r['system']}")
        values.append(r["max_demonstrated_temp_c"])
        colors.append(INK_2)
    fig, ax = plt.subplots(figsize=(9, 5.8), facecolor=SURFACE)
    style(ax, "x")
    y = np.arange(len(values))
    ax.barh(y, values, color=colors, height=0.6)
    for i, v in enumerate(values):
        ax.text(v, i, f" {v:.0f} C", va="center", color=INK_2, fontsize=8)
    ax.axvline(T_REF, color=INK, linewidth=1)
    ax.text(T_REF, len(values) - 0.3, " 55 C reference", color=INK, fontsize=8)
    ax.axvline(150, color=INK_2, linestyle="--", linewidth=1)
    ax.text(150, len(values) - 0.3, "150 C: usual automotive limit ", color=INK_2, fontsize=8, ha="right")
    ax.axhline(len(d) - 0.5, color=GRID, linewidth=1)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, max(values) * 1.15)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c, label=n) for n, c in SUPPLIER_COLORS.items()] + \
              [plt.Rectangle((0, 0), 1, 1, color=INK_2, label="system (Monte Carlo)")]
    ax.legend(handles=handles, frameon=False, fontsize=8, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=4)
    ax.set_xlabel("Highest temperature (C) at which R(2,920 h) >= 0.999 is demonstrated with 95% confidence",
                  color=INK, fontsize=9)
    title(ax, "2b. Maximum demonstrated temperature", pad=26)
    save(fig, "sig_2b_max_demonstrated_temperature.png")


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
    fig_chi_square(a)
    fig_published(fam, pub_sum)
    fig_coverage(cov)
    fig_calibration(cal_bins, briers)
    fig_parts(parts)
    fig_max_temp(parts, sysrows)
    (OUT / "key_numbers_significance.md").write_text(
        key_numbers(a, pub_sum, cov, briers, mc, parts, sysrows, sup, prof), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}: 11 tables, 6 figures, key_numbers_significance.md")
