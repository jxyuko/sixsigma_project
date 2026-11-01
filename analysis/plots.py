# plots.py
# All report figures, drawn with plotnine (ggplot2's grammar in Python, as in the course's Python track).
# Each function takes a results table (the same CSVs written to reports/preliminary_results/tables/),
# returns the ggplot object and saves it as a PNG. Used by analysis/01_preliminary_results.py and
# analysis/02_significance.py.

import numpy as np
import pandas as pd
from plotnine import (aes, annotate, coord_flip, element_blank, element_line, element_rect, element_text,
                      geom_abline, geom_col, geom_hline, geom_line, geom_linerange, geom_point,
                      geom_pointrange, geom_ribbon, geom_text, ggplot, guide_legend, guides, labs,
                      facet_wrap, position_dodge, scale_color_manual, scale_fill_manual, scale_shape_manual,
                      scale_x_log10, scale_y_continuous, scale_y_log10, theme, theme_classic)

from functions.library import SLOTS

# Reference palette: categorical colours in fixed order (by supplier), text and surface tokens
SUPPLIER_COLORS = {"Texas Instruments": "#2a78d6", "Analog Devices": "#eb6834", "Renesas Electronics": "#1baf7a"}
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK_2, GRID, SURFACE, MUTED = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#a3a29c"


def theme_taser(width=8, height=5, grid="x"):
    """theme_classic() with a light surface, recessive axes and one set of grid lines."""
    t = theme_classic(base_size=10) + theme(
        figure_size=(width, height), dpi=200,
        plot_background=element_rect(fill=SURFACE, color=SURFACE),
        panel_background=element_rect(fill=SURFACE),
        legend_background=element_rect(fill=SURFACE),
        axis_line=element_line(color=INK_2), axis_ticks=element_line(color=INK_2),
        axis_text=element_text(color=INK_2), axis_title=element_text(color=INK, size=9),
        plot_title=element_text(color=INK, size=11, ha="left"),
        plot_subtitle=element_text(color=INK_2, size=9, ha="left"),
        legend_position="top", legend_title=element_blank(), legend_text=element_text(size=8),
        legend_key=element_rect(fill=SURFACE, color=SURFACE))
    grid_line = element_line(color=GRID, size=0.5)
    if grid in ("x", "both"):
        t += theme(panel_grid_major_x=grid_line)
    if grid in ("y", "both"):
        t += theme(panel_grid_major_y=grid_line)
    return t


def slot_order(d, label_col, value_col, ascending=True):
    """Order rows by slot (top to bottom in SLOTS order after coord_flip), then by value."""
    d = d.copy()
    d["slot"] = pd.Categorical(d["slot"], categories=SLOTS, ordered=True)
    d = d.sort_values(["slot", value_col], ascending=[False, not ascending])
    d[label_col] = pd.Categorical(d[label_col], categories=list(dict.fromkeys(d[label_col])), ordered=True)
    return d


def save(p, path):
    p.save(path, verbose=False)
    return p


# --- Preliminary Results (analysis/01_preliminary_results.py) ---------------------------------------

def figure1_forest(t1, path):
    d = t1.assign(label=t1["slot"] + ": " + t1["part"])
    d = slot_order(d, "label", "fit_median", ascending=False)
    p = (ggplot(d, aes(x="label", y="fit_median", ymin="fit_lower", ymax="fit_upper", color="supplier"))
         + geom_pointrange(size=0.7, fatten=3)
         + coord_flip() + scale_y_log10()
         + scale_color_manual(values=SUPPLIER_COLORS, limits=list(SUPPLIER_COLORS))
         + labs(x="", y="FIT at 55 C, median and 95% CI (log scale)",
                title="Figure 1. Every candidate on one basis: 55 C")
         + theme_taser(8, 5.4, "x"))
    return save(p, path)


def figure2a_failures(sw, path, target_failures, mission):
    d = sw.assign(system=sw["system"] + " system")
    p = (ggplot(d, aes(x="temperature_c", y="failures_per_1000_median", color="system", fill="system"))
         + geom_ribbon(aes(ymin="failures_per_1000_lower", ymax="failures_per_1000_upper"), alpha=0.15, color="none")
         + geom_line(size=1.2)
         + geom_hline(yintercept=target_failures, linetype="dashed", color=INK_2)
         + annotate("text", x=27, y=target_failures * 1.6, label="target: 1 per 1,000", color=INK_2, size=8, ha="left")
         + scale_y_log10()
         + scale_color_manual(values=[BLUE, ORANGE], limits=["most reliable system", "least reliable system"])
         + scale_fill_manual(values=[BLUE, ORANGE], limits=["most reliable system", "least reliable system"])
         + labs(x="Operating temperature (C)", y=f"Failures per 1,000 vehicles in {mission:,.0f} h (log)",
                title="Figure 2a. Expected failures vs temperature (median, 95% CI)")
         + theme_taser(7, 4.6, "y"))
    return save(p, path)


def figure2b_probability(sw, path, confidence):
    d = sw.assign(system=sw["system"] + " system", p_pct=100 * sw["p_meets_target"])
    p = (ggplot(d, aes(x="temperature_c", y="p_pct", color="system"))
         + geom_line(size=1.2)
         + geom_hline(yintercept=100 * confidence, linetype="dashed", color=INK_2)
         + annotate("text", x=150, y=100 * confidence - 5, label="95% confidence needed", color=INK_2, size=8,
                    ha="right")
         + scale_y_continuous(limits=(0, 100))
         + scale_color_manual(values=[BLUE, ORANGE], limits=["most reliable system", "least reliable system"])
         + labs(x="Operating temperature (C)", y="P(system meets R >= 0.999), %",
                title="Figure 2b. Chance of meeting the target vs temperature")
         + theme_taser(7, 4.6, "y"))
    return save(p, path)


def figure3_tornado(sens, path, mission):
    d = sens.copy()
    d["lo"] = d[["low_setting", "high_setting"]].min(axis=1)
    d["hi"] = d[["low_setting", "high_setting"]].max(axis=1)
    d = d.sort_values("swing")
    d["assumption"] = pd.Categorical(d["assumption"], categories=list(d["assumption"]), ordered=True)
    d["label"] = d.apply(lambda r: f"  {r['lo']:.3f} - {r['hi']:.3f}", axis=1)
    base = d["base"].iloc[0]
    p = (ggplot(d, aes(x="assumption"))
         + geom_linerange(aes(ymin="lo", ymax="hi"), size=9, color=BLUE)
         + geom_hline(yintercept=base, color=INK)
         + geom_text(aes(y="hi", label="label"), ha="left", size=8, color=INK_2)
         + annotate("text", x=len(d) + 0.45, y=base, label=f" base {base:.3f}", ha="left", size=8, color=INK)
         + coord_flip()
         + scale_y_continuous(expand=(0.05, 0, 0.25, 0))
         + labs(x="", y=f"Median failures per 1,000 vehicles in {mission:,.0f} h, most reliable system",
                title="Figure 3. Sensitivity: one assumption changed at a time")
         + theme_taser(8, 3.8, "x"))
    return save(p, path)


# --- Significance and confidence (analysis/02_significance.py) -----------------------------------------

def sig_1a_chi_square(a, path):
    lo, hi = a["chi_square_fit95"].min() / 2, a["chi_square_fit95"].max() * 2
    p = (ggplot(a, aes(x="chi_square_fit95", y="simulator_fit95_mean", color="supplier"))
         + geom_abline(intercept=0, slope=1, linetype="dashed", color=INK_2)
         + geom_point(size=3.5)
         + annotate("text", x=hi / 1.4, y=hi / 1.1, label="simulator = formula", color=INK_2, size=8, ha="right")
         + scale_x_log10(limits=(lo, hi)) + scale_y_log10(limits=(lo, hi))
         + scale_color_manual(values=SUPPLIER_COLORS, limits=list(SUPPLIER_COLORS))
         + labs(x="95% maximum FIT, course chi-square formula",
                y="95% FIT from the simulator (mean of 20 seeds)",
                title=f"1a. Simulator vs chi-square: max difference {a['difference_pct'].abs().max():.2f}%")
         + theme_taser(6, 5.4, "both"))
    return save(p, path)


def sig_1b_published(fam, summary, path):
    s = summary.iloc[0]
    d = fam.sort_values("log10_ratio").copy()
    d["family"] = pd.Categorical(d["family"], categories=list(d["family"]), ordered=True)
    d["basis"] = np.where(d["same_basis"], "TI: same test data as published",
                          "published value rests on other data (Section 14)")
    p = (ggplot(d, aes(x="family", y="ratio", color="basis", shape="basis"))
         + annotate("rect", xmin=-np.inf, xmax=np.inf, ymin=s["ratio_lower"], ymax=s["ratio_upper"],
                    fill=BLUE, alpha=0.12)
         + geom_hline(yintercept=1, linetype="dashed", color=INK_2)
         + geom_point(size=3.5, stroke=1.2, fill=SURFACE)
         + coord_flip() + scale_y_log10()
         + scale_color_manual(values=[BLUE, MUTED], limits=["TI: same test data as published",
                                                             "published value rests on other data (Section 14)"])
         + scale_shape_manual(values=["o", "o"], limits=["TI: same test data as published",
                                                         "published value rests on other data (Section 14)"])
         + guides(color=guide_legend(nrow=2), shape=guide_legend(nrow=2))
         + labs(x="", y="Simulated / published FIT at 55 C, 60% (log scale; 1 = identical; band = 95% CI of TI mean)",
                title="1b. Simulator vs published FIT",
                subtitle=f"TI mean ratio {s['mean_ratio']:.2f} (95% CI {s['ratio_lower']:.2f}-{s['ratio_upper']:.2f}), "
                         f"one-sample t-test p = {s['p_value']:.2f}")
         + theme_taser(8, 5, "x"))
    return save(p, path)


def sig_1c_coverage(cov, path):
    d = cov[(cov["truth"] == "log-uniform") & (cov["expected_failures"] != "all")]
    order = [f"{b}\n({n} suppliers)" for b, n in zip(d["expected_failures"], d["suppliers"])]
    long = pd.concat([
        pd.DataFrame({"bin": order, "interval": "central 95% interval", "coverage": 100 * d["central_95_coverage"].values,
                      "lower": 100 * d["central_lower"].values, "upper": 100 * d["central_upper"].values}),
        pd.DataFrame({"bin": order, "interval": "upper 97.5% bound", "coverage": 100 * d["upper_975_coverage"].values,
                      "lower": 100 * d["upper_lower"].values, "upper": 100 * d["upper_upper"].values})])
    long["bin"] = pd.Categorical(long["bin"], categories=order, ordered=True)
    p = (ggplot(long, aes(x="bin", y="coverage", ymin="lower", ymax="upper", color="interval"))
         + geom_hline(yintercept=95, linetype="dashed", color=BLUE)
         + geom_hline(yintercept=97.5, linetype="dotted", color=ORANGE)
         + geom_pointrange(position=position_dodge(width=0.4), size=0.7, fatten=3)
         + scale_y_continuous(limits=(0, 102))
         + scale_color_manual(values=[BLUE, ORANGE], limits=["central 95% interval", "upper 97.5% bound"])
         + labs(x="Failures the test was expected to see", y="Coverage of the true FIT, % (exact 95% CI)",
                title="1c. Do the simulator's intervals contain the truth? (1,000 known-truth suppliers)",
                subtitle="Nominal: 95% (dashed) for the central interval, 97.5% (dotted) for the upper bound")
         + theme_taser(8, 4.8, "y"))
    return save(p, path)


def sig_1d_calibration(bins, briers, path):
    b = briers.set_index("truth")
    names = {t: f"true FIT {t}: Brier {b.loc[t, 'brier']:.2f} ({b.loc[t, 'brier_lower']:.2f}-{b.loc[t, 'brier_upper']:.2f})"
             for t in ("uniform", "log-uniform")}
    d = bins.assign(world=bins["truth"].map(names))
    p = (ggplot(d, aes(x="mean_p_b_outlasts_a", y="share_b_truly_better", ymin="lower", ymax="upper", color="world"))
         + geom_abline(intercept=0, slope=1, linetype="dashed", color=INK_2)
         + geom_line(size=1) + geom_pointrange(size=0.6, fatten=3)
         + scale_color_manual(values=[BLUE, ORANGE], limits=[names["uniform"], names["log-uniform"]])
         + guides(color=guide_legend(nrow=2))
         + labs(x="Simulator's P(B outlasts A), binned", y="Share of pairs where B is truly better (95% CI)",
                title="1d. Calibration of P(B outlasts A); a coin flip scores 0.25")
         + theme_taser(6, 5.6, "both"))
    return save(p, path)


def sig_2a_max_rate(parts, path):
    d = parts.assign(label=parts["slot"] + ": " + parts["part"])
    d = slot_order(d, "label", "fit95_max", ascending=False)
    target = d["target_fit"].iloc[0]
    p = (ggplot(d, aes(x="label", y="fit95_max", color="supplier"))
         + geom_hline(yintercept=target, linetype="dashed", color=INK_2)
         + geom_point(size=3.5)
         + annotate("text", x=len(d) + 0.3, y=target, label=f"target {target:.0f} FIT ", ha="right", size=8,
                    color=INK_2)
         + coord_flip() + scale_y_log10()
         + scale_color_manual(values=SUPPLIER_COLORS, limits=list(SUPPLIER_COLORS))
         + labs(x="", y="95% maximum failure rate at 55 C, FIT (chi-square; left of the line = target demonstrated)",
                title=f"2a. Every part demonstrates the target at 55 C (all p < 0.001)")
         + theme_taser(8, 5.2, "x"))
    return save(p, path)


def sig_2b_max_temp(parts, sysrows, path, t_ref=55):
    d = parts.assign(label=parts["slot"] + ": " + parts["part"], group=parts["supplier"])
    d = slot_order(d, "label", "max_demonstrated_temp_c", ascending=True)
    s = pd.DataFrame({"label": "SYSTEM, " + sysrows["system"], "max_demonstrated_temp_c": sysrows["max_demonstrated_temp_c"],
                      "group": "system (Monte Carlo)"})
    labels = list(d["label"].cat.categories) + list(s["label"][::-1])
    d = pd.concat([d[["label", "max_demonstrated_temp_c", "group"]].astype({"label": str}), s])
    d["label"] = pd.Categorical(d["label"], categories=labels, ordered=True)
    d["text"] = d["max_demonstrated_temp_c"].map(lambda v: f" {v:.0f} C")
    colors = {**SUPPLIER_COLORS, "system (Monte Carlo)": INK_2}
    p = (ggplot(d, aes(x="label", y="max_demonstrated_temp_c", fill="group"))
         + geom_col(width=0.6)
         + geom_text(aes(label="text"), ha="left", size=8, color=INK_2)
         + geom_hline(yintercept=t_ref, color=INK)
         + geom_hline(yintercept=150, linetype="dashed", color=INK_2)
         + annotate("text", x=len(labels) + 0.45, y=t_ref, label=" 55 C reference", ha="left", size=8, color=INK)
         + annotate("text", x=len(labels) + 0.45, y=150, label="150 C: usual automotive limit ", ha="right",
                    size=8, color=INK_2)
         + coord_flip()
         + scale_y_continuous(limits=(0, 205))
         + scale_fill_manual(values=colors, limits=list(colors))
         + labs(x="", y="Highest temperature (C) at which R(2,920 h) >= 0.999 is demonstrated with 95% confidence",
                title="2b. Maximum demonstrated temperature")
         + theme_taser(9, 6, "x"))
    return save(p, path)


# --- Financial impacts (analysis/03_financial_impacts.py) -------------------------------------------

SCENARIO_COLORS = {"before: least reliable suppliers": ORANGE, "after: recommended suppliers": BLUE}


def fin_1_failures(ba, path, fleet):
    """Expected warranty failures per fleet, before vs after, per condition (median, 95% CI)."""
    d = ba[ba["quantity"] == "failures"].copy()
    d["condition"] = pd.Categorical(d["condition"], categories=list(dict.fromkeys(d["condition"])), ordered=True)
    p = (ggplot(d, aes(x="condition", y="estimate", ymin="lower", ymax="upper", color="scenario"))
         + geom_pointrange(position=position_dodge(width=0.4), size=0.8, fatten=3)
         + scale_y_log10()
         + scale_color_manual(values=SCENARIO_COLORS, limits=list(SCENARIO_COLORS))
         + labs(x="", y=f"Expected warranty failures per {fleet:,} vehicles (log scale)",
                title="Financial 1. Warranty failures before vs after the supplier change",
                subtitle="Median and 95% CI over 5,000 simulated draws; mission 2,920 h")
         + theme_taser(7.5, 4.8, "y"))
    return save(p, path)


PRICE_CASE_COLORS = {"Sheet2 prices (MCU family proxies)": BLUE, "equal MCU prices (Sheet2 ECU average)": ORANGE}


def usd(v):
    return f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


def fin_2_saving(savings, path, fleet):
    """Saving from the change (before - after) per fleet, by cost component, condition and price case."""
    d = savings[savings["quantity"].isin(["purchase_cost", "warranty_cost", "total_cost"])].copy()
    names = {"purchase_cost": "Purchase", "warranty_cost": "Warranty (parts-only)", "total_cost": "Total"}
    d["component"] = pd.Categorical(d["quantity"].map(names), categories=["Total", "Warranty (parts-only)", "Purchase"],
                                    ordered=True)
    d["condition"] = pd.Categorical(d["condition"], categories=list(dict.fromkeys(d["condition"])), ordered=True)
    d["text"] = np.where(d["quantity"] == "warranty_cost", "", d["estimate"].map(usd))
    w = d[d["quantity"] == "warranty_cost"]
    wtxt = "; ".join(f"{c}: USD {r['estimate']:.2f}" for c, r in
                     w[w["price_case"] == list(PRICE_CASE_COLORS)[0]].set_index("condition").iterrows())
    p = (ggplot(d, aes(x="component", y="estimate", ymin="lower", ymax="upper", color="price_case"))
         + geom_hline(yintercept=0, color=INK_2)
         + geom_pointrange(position=position_dodge(width=0.5), size=0.7, fatten=3)
         + geom_text(aes(label="text"), position=position_dodge(width=0.5), nudge_x=0.22, size=7, color=INK_2)
         + coord_flip()
         + facet_wrap("~condition", ncol=1)
         + scale_color_manual(values=PRICE_CASE_COLORS, limits=list(PRICE_CASE_COLORS))
         + guides(color=guide_legend(nrow=2))
         + labs(x="", y=f"Saving from the change, USD per {fleet:,} vehicles (before - after; median, 95% CI)",
                title="Financial 2. What the supplier change saves (negative = costs more)",
                subtitle=f"Before: least reliable suppliers. After: recommended. 2,920 h mission.\n"
                         f"Warranty saving (parts-only) is too small to see: {wtxt}")
         + theme_taser(8.5, 6.2, "x") + theme(strip_background=element_rect(fill=SURFACE, color=SURFACE),
                                              strip_text=element_text(color=INK, size=9, ha="left")))
    return save(p, path)


def fin_3_break_even(be, path):
    """Break-even cost of one warranty repair (equal-MCU-price case), per condition (median, 95% CI)."""
    d = be.copy()
    d["condition"] = pd.Categorical(d["condition"], categories=list(dict.fromkeys(d["condition"])), ordered=True)
    d["text"] = d["estimate"].map(lambda v: f"  median ${v:,.0f}")
    p = (ggplot(d, aes(x="condition", y="estimate", ymin="lower", ymax="upper"))
         + geom_pointrange(color=ORANGE, size=0.8, fatten=3)
         + geom_text(aes(label="text"), ha="left", nudge_x=0.15, size=8, color=INK_2)
         + coord_flip() + scale_y_log10(labels=lambda b: [usd(v) for v in b])
         + labs(x="", y="Cost of ONE warranty repair needed for the reliability gain to repay the extra purchase cost "
                          "(USD, log scale)",
                title="Financial 3. Break-even repair cost (equal MCU prices)",
                subtitle="Median and 95% CI over the draws in which the change avoids failures")
         + theme_taser(8.5, 3.6, "x"))
    return save(p, path)
