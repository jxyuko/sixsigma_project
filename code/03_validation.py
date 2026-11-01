# 03_validation.py
# ROADMAP Section 11: 11b simulator vs the FIT/MTBF/AF published in the parameter table, and
# 11e known-truth coverage and calibration study.
# Writes results/tables/validation_*.csv and results/figures/validation_*.png.
# Run from the project root:  .venv/Scripts/python code/03_validation.py   (about 2 minutes)

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
from functions.validation import (TRUTHS, brier_score, calibration_study, calibration_table,  # noqa: E402
                                  coverage_by_evidence, coverage_study, supplier_check)

TABLES = ROOT / "results" / "tables"
FIGURES = ROOT / "results" / "figures"
N = 1000                       # synthetic suppliers per study, and pairs per calibration study
SEED_COVERAGE, SEED_CALIBRATION = 11, 12
T_USE_C = 55

# Reference palette: categorical slots 1-2, text and surface tokens
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK_2)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def coverage_figure(table, path):
    t = table.drop(index="all")
    x = np.arange(len(t))
    w = 0.36
    fig, ax = plt.subplots(figsize=(7, 4), facecolor=SURFACE)
    style(ax)
    ax.bar(x - w / 2 - 0.01, 100 * t["central_95_coverage"], w, color=BLUE, label="Central 95% interval")
    ax.bar(x + w / 2 + 0.01, 100 * t["upper_975_coverage"], w, color=ORANGE, label="Upper 97.5% bound")
    ax.axhline(95, color=INK_2, linestyle="--", linewidth=1)
    ax.text(-0.55, 96, "95% target", color=INK_2, fontsize=8, ha="left", va="bottom")
    for i, c in enumerate(t["central_95_coverage"]):
        ax.text(i - w / 2, 100 * c + 1.5, f"{100 * c:.0f}%", ha="center", fontsize=8, color=INK)
    ax.set_xticks(x, [f"{b}\n({n} suppliers)" for b, n in zip(t.index, t["suppliers"])])
    ax.set_xlim(-0.6, len(t) - 0.4)
    ax.set_ylim(0, 112)
    ax.set_xlabel("Failures the HTOL test was expected to see (true rate x device-hours)", color=INK, fontsize=9)
    ax.set_ylabel("Share of suppliers whose true FIT is covered (%)", color=INK, fontsize=9)
    ax.set_title("Coverage of the true FIT, 1,000 synthetic suppliers", color=INK, fontsize=11, loc="left", pad=18)
    ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, 1.0), ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def calibration_figure(tables, briers, path):
    fig, ax = plt.subplots(figsize=(5.2, 5), facecolor=SURFACE)
    style(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.plot([0, 1], [0, 1], color=INK_2, linestyle="--", linewidth=1)
    ax.text(0.97, 0.91, "perfect calibration", color=INK_2, fontsize=8, ha="right", rotation=45)
    for (truth, t), color in zip(tables.items(), (BLUE, ORANGE)):
        ax.plot(t["mean_p_b_outlasts_a"], t["share_b_truly_better"], color=color, linewidth=2,
                marker="o", markersize=7, markeredgecolor=SURFACE, markeredgewidth=2,
                label=f"True FIT {truth} (Brier {briers[truth]:.2f})")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Simulator's P(B outlasts A), binned", color=INK, fontsize=9)
    ax.set_ylabel("Share of pairs where B is truly better", color=INK, fontsize=9)
    ax.set_title("Calibration of P(B outlasts A), 1,000 pairs", color=INK, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def supplier_figure(check, path):
    fam = check.drop_duplicates("family").sort_values("ratio").reset_index(drop=True)
    y = np.arange(len(fam))
    fig, ax = plt.subplots(figsize=(7.5, 4.6), facecolor=SURFACE)
    style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_xscale("log")
    ax.hlines(y, fam["sim_fit_lower"], fam["sim_fit_upper"], color=BLUE, linewidth=2,
              label="Simulator 95% interval")
    ax.plot(fam["sim_fit_at_cl"], y, "o", color=BLUE, markersize=8, markeredgecolor=SURFACE,
            markeredgewidth=2, label="Simulator 60% bound")
    ax.plot(fam["fit_published"], y, "D", color=ORANGE, markersize=8, markeredgecolor=SURFACE,
            markeredgewidth=2, label="Published FIT")
    ax.set_yticks(y, fam["family"])
    ax.set_xlabel("FIT at 55 C (log scale)", color=INK, fontsize=9)
    ax.set_title("Simulator vs published FIT, same temperature and confidence", color=INK,
                 fontsize=11, loc="left", pad=28)
    ax.legend(frameon=False, fontsize=8, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3,
              handletextpad=0.3, columnspacing=1.0)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)

    # 11b: simulator vs published values (validation only; published values are not model inputs)
    check = supplier_check()
    check.to_csv(TABLES / "validation_supplier_fit.csv", index=False)
    supplier_figure(check, FIGURES / "validation_supplier_fit.png")
    fam = check.drop_duplicates("family")
    print("11b simulator vs published FIT:")
    print(fam[["family", "fit_published", "sim_fit_at_cl", "ratio", "published_inside_sim_95ci",
               "verdict"]].round(3).to_string(index=False))

    cov_tables, cal_tables, briers, summary = {}, {}, {}, []
    for truth in TRUTHS:
        cov = coverage_study(N, SEED_COVERAGE, T_USE_C, truth=truth)
        cov_tables[truth] = coverage_by_evidence(cov)
        cal = calibration_study(N, SEED_CALIBRATION, T_USE_C, truth=truth)
        cal_tables[truth] = calibration_table(cal)
        briers[truth] = brier_score(cal)
        informative = cal[~cal["both_zero_failures"]]
        summary.append({
            "truth": truth,
            "suppliers": N,
            "share_zero_failure_tests": float(np.mean(cov["failures"] == 0)),
            "central_95_coverage": cov["in_central_95"].mean(),
            "upper_975_coverage": cov["below_upper_975"].mean(),
            "pairs": N,
            "share_pairs_both_zero_failures": cal["both_zero_failures"].mean(),
            "brier_all_pairs": briers[truth],
            "brier_pairs_with_a_failure": brier_score(informative),
            "seed_coverage": SEED_COVERAGE, "seed_calibration": SEED_CALIBRATION, "t_use_c": T_USE_C,
        })
        print(f"\nTrue FIT {truth}:")
        print(cov_tables[truth].round(3).to_string())
        print(cal_tables[truth].round(3).to_string())
        print(f"Brier {briers[truth]:.3f} (pairs with a failure: {brier_score(informative):.3f})")

    pd.concat(cov_tables, names=["truth"]).to_csv(TABLES / "validation_coverage.csv")
    pd.concat(cal_tables, names=["truth"]).to_csv(TABLES / "validation_calibration.csv")
    pd.DataFrame(summary).to_csv(TABLES / "validation_summary.csv", index=False)
    coverage_figure(cov_tables["log-uniform"], FIGURES / "validation_coverage.png")
    calibration_figure(cal_tables, briers, FIGURES / "validation_calibration.png")
    print(f"\nWrote results/tables/validation_*.csv and results/figures/validation_*.png")
